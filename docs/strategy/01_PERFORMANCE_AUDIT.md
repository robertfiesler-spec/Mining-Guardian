Mining Guardian — Performance & Capability Audit

**MINING GUARDIAN**

**Performance ****&**** Capability Audit**

Prepared for: Rob Fiesler, BiXBiT USA  ·  Repo: robertfiesler-spec/Mining-Guardian @ 6919e2a

**Scope**

Pre-cutover read-only audit of the Mining Guardian repository, conducted on Saturday May 9 2026 ahead of the Mac Mini cutover scheduled for 8:00 AM Sunday May 10. The objective: identify whether the system is using its hardware and architecture to full capability, and surface gaps the operator may not have considered. No code was modified; this report is reference material only. Action plan deferred to the week of May 11.

# **Executive Summary**

Mining Guardian is a substantial, well-architected system: 200 Python files, ~72,000 lines, two cooperating Postgres databases, a four-pass AI learning chain, and nine scheduled or always-on launchd services. The architectural decisions are sound — local-first, no cloud-only dependencies, operator-in-the-loop, NOTIFY-driven feedback between databases.

The performance gaps are concentrated in three categories. First, classic database hygiene that was deferred during the SQLite-to-Postgres migration: there is no connection pool on the Postgres side, and timestamp comparisons are routed through string casts that defeat the index planner. Second, capacity mismatch in the install-time decisions for a 16GB Mac Mini: the auto-selected local LLM (llama3.2:3b) is roughly an order of magnitude smaller than the model the prompts were tuned for (Qwen 2.5 32B). Third, sequential execution patterns where pipelining I/O against compute would yield meaningful headroom — particularly in the daily deep dive, which is single-threaded across roughly 50 miners at 2-4 minutes each.

None of these are showstoppers for Sunday's cutover. The recommended action set is: address the highest-impact items in the first week post-cutover, do nothing pre-cutover beyond a small list of verification steps, and let the system stabilize on the Mini before refactoring.

# **Tier 1 — Pre-Cutover Verification**

Items in this tier are not code changes. They are verification steps to run during or just after cutover so the install lands in a known-good state. Each takes seconds to minutes.

## **1.1  Override the install-time LLM model selection**

The installer detects RAM at install time and chooses the local LLM accordingly. On a 16GB Mini, the default selection is llama3.2:3b. The operational AI prompts in this repo — specifically the per-miner prompt builder in ai/daily_deep_dive.py — were developed and tuned against Qwen 2.5 32B running on ROBS-PC with 24GB of GPU memory. The 3B parameter model is roughly an order of magnitude smaller and weaker at structured technical reasoning, which is the dominant workload.

The installer README explicitly notes the user may override the auto-selection during install. It is recommended to exercise that override in favor of qwen2.5:14b-instruct-q4_K_M (approximately 9-10GB resident), and if memory pressure becomes a problem under the combined load of Postgres + Grafana + Prometheus + 9 Python services, fall back to qwen2.5:7b-instruct-q4_K_M (approximately 5GB resident). Both retain Qwen-family reasoning quality at meaningfully higher fidelity than llama3.2:3b.

If post-cutover analysis quality is observably degraded, a hybrid configuration is supported: keep ROBS-PC online and point OLLAMA_URL for the daily deep dive specifically back at the Tailscale endpoint, while letting the per-scan local analyzer run on the Mini. The runtime currently refuses non-loopback OLLAMA_URL by design (per Vision Anchor 7), so this fallback requires either a configuration override or a temporary patch.

## **1.2  Disable Mac Mini sleep before launchd schedules begin**

All twelve scheduled launchd plists fire via StartCalendarInterval. On macOS, this mechanism does not wake the system from sleep — only pmset repeat wake does. If the Mini sleeps at any point between 4:00 PM (deep dive) and 1:00 AM (refinement chain), those jobs miss their fire window silently. The failure mode is invisible until you notice that a daily deep dive analysis hasn't appeared in knowledge.json for several days.

Two acceptable resolutions:

- Fully disable sleep with sudo pmset -a sleep 0 disksleep 0. Simplest and recommended for this hardware role.

- Configure pmset repeat wakeorpoweron MTWRFSU 03:55:00 so the Mac wakes five minutes before the earliest scheduled job. More elegant but requires keeping the wake schedule synchronized with the launchd schedule.

Either approach should be in the post-install smoke test.

## **1.3  Confirm all nine launchd services load and stay loaded**

The deployment checklist at DEPLOYMENT_CHECKLIST.md §2.1 already specifies this verification, but it is worth repeating because the failure mode is silent: a service that crashes on first launch shows PID '-' in launchctl list output and does not retry. The post-install verification should confirm the count is exactly nine, no PIDs are dashes, and each service's last_exit_status is 0.

launchctl list | grep com.miningguardian | wc -l    # expected: 9

launchctl list | grep com.miningguardian             # all PIDs numeric, no '-'

## **1.4  Verify backup destination is configured**

scripts/daily_backup.sh runs at 4:00 AM. The script's destination must not be the same SSD as the live data, or it is a copy and not a backup. Until the cutover, the Mac Mini is a single point of failure. If the SSD fails in the first week, you lose everything written since cutover. Catalog data in particular cannot be recovered by re-scanning — it took months to assemble.

Recommended pre-cutover decision: confirm where backups land. Practical options on the existing infrastructure:

- rsync to ROBS-PC over Tailscale on a daily cron. ROBS-PC remains online during the transition window, has ample disk, and is already on the network.

- External USB drive auto-mounted at /Volumes/. Cheapest, least automated.

- Time Machine to a NAS, if one is available.

Cloud destinations are out of scope per Vision Anchor 7.

# **Tier 2 — High-Impact Performance Work (Week 1 Post-Cutover)**

Each item below is meaningful in isolation. Address them in priority order. None require pre-cutover changes.

## **2.1  Add a Postgres connection pool to GuardianPGDB**

File: core/database_pg.py. The current implementation opens a brand-new psycopg2 connection on every call to _connect(). The header docstring is honest about it: "conn is checked out per-call (no pool today — simple for correctness)" and "Connection pooling (add when we deploy)." The Mini IS the deploy target, and the pool was never added.

The cost is concrete. A typical hourly scan invokes the database hundreds of times: per-miner reads in daily_deep_dive, predictor, fingerprint_builder, outcome_checker, hvac_correlator; dashboard API on every HTTP request; the Slack listener on every interaction; the alert listener polling every fifteen seconds. Postgres connection setup over loopback on macOS is approximately 5-15ms each. Math: 15ms × ~500 calls/hour just from one scan cycle = approximately 7.5 seconds of pure connection overhead per scan, plus sustained load from the six other always-on services. On the Mini, where idle CPU during scans is what Ollama needs for inference, wasting cycles on connection setup steals from the LLM.

The fix is small. Drop a psycopg2.pool.ThreadedConnectionPool with minconn=2, maxconn=10 into GuardianPGDB.__init__. Change _connect to call getconn / putconn instead of psycopg2.connect / close. The previous SQLite-side codebase already had this pattern; the PG migration just didn't carry it over.

## **2.2  Stop casting timestamps through TO_CHAR**

The schema declares scanned_at as TIMESTAMPTZ NOT NULL. The query side, however, compares it like this:

WHERE scanned_at >= TO_CHAR(NOW() - INTERVAL '24 hours', 'YYYY-MM-DD"T"HH24:MI:SS.US')

This pattern appears throughout ai/daily_deep_dive.py, ai/predictor.py, and several other files. The insert side passes datetime.now().isoformat() — a naive Python string — which Postgres parses into a TIMESTAMPTZ. The read side then converts NOW() back into a string with TO_CHAR for the comparison. The result is a string comparison on what was stored as a timestamp, which the planner cannot fully optimize and which is brittle to timezone drift.

The clean version is:

WHERE scanned_at >= NOW() - INTERVAL '24 hours'

Combined with switching the insert side to pass datetime.now() directly (or better, datetime.now(timezone.utc) for DST safety), the index works fully and the queries get TIMESTAMPTZ semantics including correct cross-timezone behavior.

The reason this is Tier 2 and not Tier 1 is that the leading-column index on (miner_id, scanned_at) bounds the range scan to one miner's slice, which keeps current performance acceptable even with the cast. On the fresh Mini install with empty tables it will not bite for weeks. On the eventual 5-10M row table, it bites hard.

## **2.3  Tune Postgres for a 16GB shared host**

Default Homebrew Postgres on macOS uses approximately 128MB shared_buffers. On a 16GB Mini that is also running Ollama (5-10GB), Grafana (~500MB), Prometheus (~300MB), nine Python services (~50MB each, ~450MB total), and OS overhead (~3GB), there is realistically 2-3GB safely available for Postgres. Without explicit configuration, Postgres will under-allocate and over-fight neighbors that will lose memory contention to it.

Recommended postgresql.conf settings for this hardware:

- shared_buffers = 1GB

- effective_cache_size = 2GB

- work_mem = 32MB

- maintenance_work_mem = 256MB

- max_connections = 50  (you do not need 100+ on a single-host install)

- random_page_cost = 1.1  (SSD)

- effective_io_concurrency = 200  (SSD)

- shared_preload_libraries = 'pg_stat_statements'  — for free query observability

After enabling pg_stat_statements: CREATE EXTENSION pg_stat_statements; gives you a queryable view of what is actually slow without instrumenting every call site. On the Mini, with everything sharing one Postgres instance, this is the single highest-leverage observability addition.

## **2.4  Change ProcessType for always-on services**

Every plist in installer/macos-pkg/resources/launchd/ sets <key>ProcessType</key><string>Background</string>. On macOS, ProcessType: Background causes the scheduler to aggressively de-prioritize the process — reduced CPU shares, lower I/O priority, more aggressive throttling under load. This is correct for batch jobs (daily deep dive, weekly training), but wrong for the always-on responsive services.

Recommended:

- scanner, alert listener, approval API, dashboard API, slack listener: ProcessType: Standard

- daily-deep-dive, weekly-training, refinement-chain, db-maintenance, knowledge-backup, log-collection, log-failure-report, operator-review, ams-cleanup, catalog-import, benchmark, morning-briefing: leave as Background

The change is a one-line edit per plist and requires a launchctl bootout/bootstrap cycle on the affected service. Meaningful for response latency on the always-on services.

## **2.5  Split daily_deep_analyses out of knowledge.json**

knowledge.json is currently 3.57MB and rewritten as a whole on every save under exclusive flock. Of that, daily_deep_analyses alone is 2.1MB — an array of recent deep dive reports that is append-mostly. The hot writers (per-scan: local_llm_analyzer, predictor, fingerprint_builder, hvac_correlator, outcome_checker, knowledge_manager) and the daily writers (daily_deep_dive itself, combine_knowledge, backup_knowledge) all serialize on the same file lock.

Two complementary fixes:

- Move daily_deep_analyses to its own JSON file (knowledge_deep_dives.json) with its own lock. The other writers do not read it; only the weekly trainer does. This drops the hot-path file size from 3.57MB to approximately 1.5MB.

- Tighten retention: keep the last 7 daily dives and 4 weekly chains rather than 17 and 10. The trainer only reads back roughly 7 days of history. Tightening cuts another ~1MB and reduces memory pressure on the merge.

The architecturally correct fix is to migrate analysis history out of JSON entirely and into the operational Postgres llm_analysis table, but that is a multi-day refactor and out of scope for the first week.

## **2.6  Pipeline DB I/O against LLM compute in daily deep dive**

ai/daily_deep_dive.py:1034 is fully serial: for each online miner, gather data from the database, build the prompt, call Ollama, wait 2-4 minutes, write the WIP file, loop. The Ollama call dominates wall time. During those 2-4 minutes, the database is idle and the next miner's data could be prefetching.

Pattern: a concurrent.futures.ThreadPoolExecutor with two workers prefetches (daily_log + 24h trends + hardware + past_analyses + fingerprint) for miner N+1 while miner N is in-flight to Ollama. The LLM call itself stays sequential — Metal cannot run two Qwen inferences at once. With 50 miners at 3 minutes each, baseline is 150 minutes; pipelining cuts roughly 10-15 minutes by getting prompt-build off the critical path. Larger fleets benefit proportionally more.

## **2.7  Promote the AMS WebSocket from one-shot to persistent**

clients/ams_client.py::_ws_fetch creates a brand-new websocket.WebSocketApp, starts a fresh daemon thread, takes one message, and closes — every single page request. With 50 miners per page, that is 2-3 handshakes per scan just for _fetch_miner_page plus one for get_dashboard. TLS handshake to AMS over the public internet is roughly 80-200ms each, so approximately 500ms per scan goes to WebSocket setup.

On the current 1-scan-per-hour cadence this is not catastrophic — 500ms out of 3600 seconds is rounding error. At production cadence, where a Mini-per-container will be running 30-minute or alert-driven scans, it accumulates. The fix is a singleton AMSClient with one persistent WebSocket connection that handles request/response with message IDs. It is a meaningful refactor (~200 lines) and not pre-cutover work.

# **Tier 3 — Things You May Not Have Considered**

These are observations rather than ranked findings. Each is a small to medium piece of work. Pick what resonates.

### **Postgres autovacuum tuning for high-churn tables**

miner_readings, chain_readings, pool_readings, and log_metrics receive heavy inserts. The default autovacuum_vacuum_scale_factor of 0.2 means autovacuum does not run until 20% of rows are dead. On a 1M-row table that is 200,000 dead tuples accumulating before cleanup. On the Mini, with limited RAM, table bloat directly hurts query plans because the planner stops trusting its statistics. Per-table override:

ALTER TABLE miner_readings SET (autovacuum_vacuum_scale_factor = 0.05);ALTER TABLE log_metrics SET (autovacuum_vacuum_scale_factor = 0.05);

### **Range partitioning on the timeseries tables**

The previous SQLite timeseries.db carried 18.1M rows. Once the Mini's Postgres operational DB accumulates six months of equivalent telemetry, miner_readings will be in the 5-10M row range. Range-partitioning on scanned_at by month gives several wins simultaneously: dropping old partitions is O(1) instead of DELETE WHERE scanned_at < ... causing massive vacuum churn; hot indexes stay small (current month only) so they fit in shared_buffers; per-partition VACUUM FULL runs during quiet hours instead of locking the whole table. Not a first-week task, but should be done before three months of data accumulate.

### **Watchdog-of-the-watchdog**

The nine launchd services use KeepAlive: { Crashed: true } which handles process crashes. It does not handle: a service running but stuck (deadlocked DB lock, hung WebSocket, infinite retry loop), a service running but with a lost DB connection silently no-oping, or Postgres itself being down. A simple ~100-line watchdog service that pings /health on each API service every 60 seconds and runs SELECT 1 against Postgres, posting to Slack on first failure and paging on three consecutive failures, gives you the monitoring of the monitoring.

### **Time zone consistency**

ai/daily_deep_dive.py runs at 16:00 via launchd's StartCalendarInterval — local time. Inserts use datetime.now().isoformat() — naive local time. Queries use NOW() — server time. As long as the Mini stays in CDT and you only ever care about CDT, this works. The minute someone does DST math, sets the Mini to UTC, or you ship to a customer in a different timezone, things will go wrong silently. The defense is to standardize on datetime.now(timezone.utc) plus TIMESTAMPTZ everywhere; the schema is already correct, it is just the Python side that needs updating.

### **Health monitoring of the Perplexity research feed**

Detailed in Report 2. Briefly: there is no signal that the four external Perplexity scheduled tasks delivered findings today. If the subscription lapses or a task breaks, the feedback loop into the catalog has no way to know. A daily "did we hear from each watcher in the last 36 hours" check belongs in the morning briefing.

### **Backup architecture for two databases on one host**

Both mining_guardian and mining_guardian_catalog live in the same Postgres process. If the data directory corrupts or the SSD has issues, both are lost simultaneously. The catalog assembly took months. Operational data is recoverable by re-scanning. If you back up only one, prioritize the catalog: pg_dump mining_guardian_catalog | gzip > backup-$(date +%Y%m%d).sql.gz. With the master node living on your PC per the current plan, the master is a separate failure domain — but the Mini's catalog will still drift between master sync points.

### **knowledge_backup.json checked into git**

A 3.57MB backup copy of knowledge.json sits at the repo root and is tracked in version control. Every backup commit grows the git history by approximately the file size. Either the path should be in .gitignore (current knowledge.json appears to be), or backups should write outside the working tree. As-is, it bloats the repo over time.

### **grafana_summary.db at the repo root**

12KB SQLite file at the project root. Either it should be in .gitignore and recreated locally per host, or it should be in a data/ subdirectory. Sharing it between installs causes confusion.

### **Operator approval timeouts and the OpenClaw socket**

Memory notes say interactive Slack buttons must route via OpenClaw socket to the localhost approval API. OpenClaw configuration is not visible anywhere in the repo. Either it is deployed separately on the Mini (in which case the install needs to include it), or this is a known-unfinished piece. A short pre-cutover check: the Slack app's interactivity Request URL needs to point at something the Mini exposes. If it currently points at the VPS, that flips to a dead URL on Sunday.

# **Suggested Q****&****A Topics**

Rather than a prescriptive plan, here are open questions worth talking through Monday before any code moves:

- Mac Mini exact hardware spec — base M4 vs Pro, exact RAM size — to choose between qwen2.5:7b and qwen2.5:14b decisively.

- ROBS-PC role post-cutover. Hard-retire, or leave online as a hot Tailscale fallback for the daily deep dive only?

- Backup destination decision. ROBS-PC over Tailscale? External drive? Both?

- Whether the 4-pass refinement chain stays as currently implemented, or whether Pass 2 should also read the catalog (separate consideration covered in Report 2).

- Priority order for the seven Tier-2 items. Connection pool is the highest-leverage; the others are roughly comparable.

- Whether to invest in pgvector for semantic past-analysis matching, or defer until the operational llm_analysis table is large enough to warrant it.

- Test discipline for changes to core/database_pg.py — the connection pool change touches every call site. Unit tests, integration test in dev, then rolling deploy.

- How to schedule the actual upgrade work alongside live operations. The system is running 24/7; some changes (Postgres tuning requires restart, ProcessType change requires service reload) need a maintenance window.

*End of report. Companion document: Mining Guardian — Two-Database Deep Dive (Report 2).*

Page   ·  Prepared May 9, 2026