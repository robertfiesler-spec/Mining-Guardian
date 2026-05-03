# Mining Guardian — Locked Decisions

This is the canonical log of decisions that are committed and not subject to re-litigation without an explicit reversal entry. Each entry has the date it was locked, the question that was on the table, what was decided, and who decided it.

> Format borrowed from ADR-style records but kept lightweight. Append-only. To reverse a decision, add a new entry that references the old number.

---

## D-1 — `MG_DB_PASSWORD` rotation
- **Date locked:** 2026-04-24
- **Decided by:** Operator (Bobby) + agent
- **Decision:** New operational Postgres password is `tX-fhG#iJdm{V?>uuZ35G-Y)O5<UeN=5` (192-bit). Stored in `.env` files only, chmod 600. Never committed to git in any form.
- **Why:** Old password `MiningGuardian2026!` had leaked across at least 29 source locations including `docs/SESSION_HANDOFF_2026-04-24.md` (now archived under `docs/archive/2026-04/`). Hard-rotation required.
- **Implementation status (as of 2026-04-26):** 🔴 Pending — applies during CRIT-1 purge on Monday 2026-04-27.

---

## D-2 — `auto_approve_enabled` default
- **Date locked:** 2026-04-24
- **Decided by:** Operator + agent
- **Decision:** `auto_approve_enabled` defaults to `False` in all config templates and example envs. Customers must explicitly opt in.
- **Why:** Auto-approving miner restarts and config writes without human-in-the-loop is a customer-trust problem on first install. Default-deny matches the operator philosophy.
- **Implementation status (as of 2026-04-26):** ⏸ Status unknown — verify during Monday cleanup.

---

## D-3 — `outcome_checker.py` rewrite via psycopg
- **Date locked:** 2026-04-25
- **Decided by:** Operator + agent
- **Decision:** Replace the SQLite-era `outcome_checker.py` with a clean psycopg implementation. No shim, no compat layer.
- **Why:** Original module assumed SQLite quoting and column types. Half-shimming it produced two follow-up GROUP BY bugs (CR-5 phases 1 and 1B). Cleaner to rewrite.
- **Implementation status (as of 2026-04-26):** ✅ Done in PR #4 (commit `bcfbd58`).

---

## D-4 — `mg_import` session TTL
- **Date locked:** 2026-04-24
- **Decided by:** Operator + agent
- **Decision:** `MG_IMPORT_SESSION_TTL_SECONDS=28800` (8 hours).
- **Why:** Customer-side log import sessions need to survive a working day but expire overnight. 8 hours is the working compromise.
- **Implementation status (as of 2026-04-26):** 🔴 Pending — applies during CRIT-3 on Monday 2026-04-27.

---

## D-5 — `mg_import` HTML password input + handoff doc
- **Date locked:** 2026-04-24
- **Decided by:** Operator + agent
- **Decision:**
  - 5a: `mg_import` HTML password input value attribute = `""` (empty). No pre-fill.
  - 5b: `docs/archive/2026-04/SESSION_HANDOFF_2026-04-24.md` (archived 2026-04-29) keeps the literal old password for historical accuracy AND has a top-of-file note explaining it's been rotated and is non-functional.
  - 5c: Run `grep` for the old password literal one more time at apply time to catch anything new that leaked between then and now.
- **Why:** Avoids accidentally pre-filling a known string while preserving forensic value of the handoff doc.
- **Implementation status (as of 2026-04-26):** 🔴 Pending CRIT-1.

---

## D-6 — `migrate_to_postgres.py` import guard
- **Date locked:** 2026-04-24
- **Decided by:** Operator + agent
- **Decision:** `migrations/migrate_sqlite_to_postgres.py` raises an exception on import unless environment variable `MG_ALLOW_MIGRATION=1` is set.
- **Why:** Prevents accidental re-runs that could overwrite live Postgres data with stale SQLite contents.
- **Implementation status (as of 2026-04-26):** ⏸ Verify in current code — defer hard-deletion of the script to post-Mac-Mini.

---

## D-7 — Ollama hosting
- **Date locked:** 2026-04-26
- **Decided by:** Operator
- **Decision:** Ollama runs on the Mac Mini exclusively. Removed from `robs-pc`. Mac Mini hosts the entire customer install.
- **Why:** Operator quote: "Real quick ollama will now be on the Mac mini, no longer on the pc, it will all be contained on the new mac." Reduces moving parts, eliminates a cross-host dependency, makes the customer install self-contained.
- **Implementation status (as of 2026-04-26):** Built into installer rebuild and Section 7 of the unified to-do.

---

## D-8 — Ollama model on Mac Mini
- **Date locked:** 2026-04-26
- **Decided by:** Operator + agent recommendation accepted
- **Decision:** Ollama model = `qwen2.5:14b-instruct-q4_K_M`. NOT `qwen2.5:32b`.
- **Why:** Mac Mini envelope is 16 GB unified RAM. The 32b quant would eat ~20 GB resident and force swap, making inference too slow for the operational loop. The 14b q4 quant fits comfortably with headroom for the rest of the stack.
- **Implementation status (as of 2026-04-26):** Locked in installer Phase 8.

---

## D-9 — Mac Mini network and remote access
- **Date locked:** 2026-04-26
- **Decided by:** Operator + agent
- **Decision:**
  - Mac Mini sits on the miner LAN `192.168.188.0/24`
  - Tailscale installed for remote operator access only — data plane stays local
  - `OLLAMA_URL=http://localhost:11434/api/generate`
  - `CATALOG_DB_HOST=localhost`
- **Why:** Local-only data plane keeps inference and DB traffic off Tailscale (latency, exit-node concerns). Tailscale is purely for SSH/remote ops convenience.
- **Implementation status (as of 2026-04-26):** Encoded in installer Phase 12.

---

## D-10 — Mac Mini install date
- **Date locked:** 2026-04-26
- **Decided by:** Operator
- **Decision:** Mac Mini install moves to **Monday 2026-05-05**. Previously planned for Tuesday/Wednesday 2026-04-28/29.
- **Why:** Operator quote: "I would like everything done before we install on the Mac Mini. I truly want this to be a 100% representative of what customer would receive and load. All patches all fixes done. Paper written. I want to be our first customer. So if we push loading on the mini out that is fine. We were planing on May 5 anyway. I did not realize how far out we were. Remember slow and steady. I would rather be late and perfect than early and wrong."
- **Implementation status (as of 2026-04-26):** Active — see `docs/ROADMAP_TO_MAC_MINI_2026-05-05.md` for day-by-day plan.

---

## D-11 — Cutover gate (customer-grade exit criteria)
- **Date locked:** 2026-04-26
- **Decided by:** Operator's customer-#1 framing
- **Decision:** Mac Mini install does not happen until all 8 exit criteria in `docs/ROADMAP_TO_MAC_MINI_2026-05-05.md` are green:
  1. No leaked secrets in repo
  2. No hardcoded passwords or default API keys
  3. No dead code shipping (OpenClaw + orphan tables removed)
  4. One canonical catalog schema (N6 done)
  5. AI has data (C4 + C1/C3 done)
  6. Installer creates a working system from a blank Mac in one pass
  7. Daily paper trail in `SESSION_LOG_YYYY-MM-DD.md`
  8. Customer-facing docs done (Setup Manual + Program Instructions + Brochure)
- **Why:** Customer-#1 framing requires the install path to match what a paying customer receives.
- **Implementation status:** Active gate.

---

## D-12 — Documentation cadence
- **Date locked:** 2026-04-26
- **Decided by:** Operator
- **Decision:** Every working day from now through cutover gets a `SESSION_LOG_YYYY-MM-DD.md` committed. Decisions are appended to this file. Roadmap (`docs/ROADMAP_TO_MAC_MINI_2026-05-05.md`) is updated at end of day if scope shifted.
- **Why:** Operator quote: "I believe in over-documentation so we know what each day brings."
- **Implementation status:** Active.

---

## D-13 - Ollama model selection: install-time RAM auto-detect (supersedes D-8)
- **Date locked:** 2026-04-28
- **Decided by:** Operator + agent
- **Decision:** Installer detects host RAM at install time and selects the Ollama model accordingly. Customer can override via prompt.
  - **16 GB RAM** (e.g., base Mac Mini M4) picks `llama3.2:3b` (q4 default)
  - **24 GB RAM or more** picks `qwen2.5:14b-instruct-q4_K_M`
  - **Override:** Installer surfaces the auto-detected pick and lets the customer choose a different supported model before download.
- **Why:** D-8 hard-coded `qwen2.5:14b-instruct-q4_K_M` on the assumption every Mac Mini in the deployment fleet would be 16 GB. That assumption no longer holds. We now expect a mix of 16 GB and 24 GB+ Minis at customer sites, and 14b q4 on a 16 GB host pushes the working set close to swap once Postgres, Colima, and the MG app are also resident. `llama3.2:3b` keeps the 16 GB envelope responsive; the 14b model becomes the default the moment there is headroom for it.
- **Supersedes:** D-8 (Ollama model on Mac Mini). D-8 stays in this file as the historical record; D-13 is the live policy.
- **Implementation status (as of 2026-04-28):** Pending. Encoded in `mg/pr26-mac-mini-installer` (Phase 8: model selection step).

---

## D-14 — Operational ↔ Catalog: live-reference architecture, no scheduled refresh
- **Date locked:** 2026-04-28
- **Decided by:** Operator + agent
- **Decision:** The two databases on the Mac Mini — `mining_guardian` (operational) and `intelligence_catalog` (reference) — communicate as a **live reference**, not on a schedule. Five sub-locks make this concrete:
  1. **Both DBs are always reachable, no client-side cache.** Both databases run in the same Postgres 16 container on the Mini. Every Mining Guardian process — the scan daemon (`core/mining_guardian.py`), the AI analysis paths (`ai/daily_deep_dive.py`, `ai/train_cohort.py`, `ai/deep_analysis_claude.py`, `core/llm_analyzer.py`, `ai/local_llm_analyzer.py`), the dashboard API, the briefing scripts — opens a connection to BOTH at startup and holds it open for the life of the process. There is no client-side TTL cache between any reader and the catalog. The current 5-minute cache in `ai/catalog_context.py` is removed as part of D-14 implementation.
  2. **The hourly scan must consult the catalog.** Today, `core/mining_guardian.py` (verified 2026-04-28 on commit `ffc687c`) has zero references to the catalog — no `catalog_context` import, no `hardware.*` / `ops.*` / `market.*` / `knowledge.*` queries. That is the live gap. After D-14 implementation, before the scanner evaluates any miner it reads `hardware.miner_models` for the spec, `ops.failure_patterns` for known patterns matching this model, `hardware.model_known_issues` for documented defects, and `market.war_stories` for field-observed comparisons. The scanner is no longer blind to the reference.
  3. **Operational outcomes flow back to the catalog continuously, not on a schedule.** Every operational write to `public.action_audit_log`, `public.miner_restarts`, and `public.llm_analysis` fires a Postgres `NOTIFY catalog_feedback`. A `feedback_loop_daemon` (managed by launchd on the Mini) `LISTEN`s for those notifications and runs the existing C5 sync logic (`intelligence-catalog/db/feedback_loop.py`, PR #22, 30 KB, on `main` today) within ~100 ms of the operational write. There is no cron, no scheduled refresh, no batch window. The catalog is effectively-current to the moment any reader opens it.
  4. **A catalog read failure is loud, not silent.** If the catalog DB is unreachable or any catalog query raises, the scanner / AI / briefing logs at ERROR and refuses to proceed for that miner rather than continuing with an empty catalog context. This replaces the current `ai/catalog_context.py` circuit-breaker that silently returns `""` after three failures — a B-4-class silent-failure mode that hides catalog outages from the operator.
  5. **The HTTP catalog-api layer is retired post-cutover.** Today, AI consumers reach the catalog via HTTP to `intelligence-catalog/catalog-api` running on ROBS-PC at `100.110.87.1:8420`. After May 5 cutover scope γ, ROBS-PC is decommissioned. On the Mini, AI consumers talk to the catalog DB directly via psycopg, not via HTTP to a localhost catalog-api. Same machine, same Postgres, no round-trip.
- **Why:** Operator quote 2026-04-28: *"they should always be able to reference each other, so when you are talking to the llm to ask questions everything is live for it to reference"* and *"when the hourly scans happen it will be able to access it whenever it is needed it will be there, as a reference to look things up and learn correct."* The original C5 design treated the operational→catalog feedback as a cron job (intelligence-catalog/db/feedback_loop.py header documents "running this hourly (or daily) is safe"). That design produces a stale catalog — every reader is reading wisdom up to one cron-interval old. The corrected D-14 design makes the catalog effectively-current: every operational outcome is folded into catalog wisdom within ~100 ms, every read of the catalog returns whatever the catalog knew at that exact moment, and the LLM is never working from a stale snapshot of fleet history. The reference is always open.
- **Code-grounded findings that motivated this lock (verified on `main` at `ffc687c`, 2026-04-28):**
  - `core/mining_guardian.py` (128 KB, the scan daemon started by `deploy/mining-guardian.service` as `python core/mining_guardian.py --loop`) has **zero** catalog references. Verified by full-file grep for `catalog_context|catalog_api|CATALOG_API|hardware\.miner_models|hardware\.manufacturers|ops\.failure_patterns|market\.war_stories|knowledge\.field_registry|knowledge\.sources` — match count = 0.
  - `ai/daily_deep_dive.py` has 15 catalog references and **does** consult the catalog through `ai/catalog_context.py`.
  - `ai/catalog_context.py` enforces a 5-minute TTL cache and a 3-failure circuit-breaker that silently returns `""`.
  - `intelligence-catalog/db/feedback_loop.py` (PR #22, 30 KB) is fully implemented and tested but is not currently invoked by any cron, daemon, trigger, or systemd unit. The aggregation loop exists in code but does not run.
- **Supersedes:** Implicit prior assumption that C5 is a scheduled job. D-14 makes C5 event-driven.
- **Implementation plan:** Delivered across small per-PR increments per Option β branch cadence, in this order:
  1. Drop the 5-minute cache in `ai/catalog_context.py` (`_CACHE_TTL = 0`).
  2. Wire `core/mining_guardian.py` to consult the catalog on every miner evaluation.
  3. Make catalog read failure raise / log at ERROR rather than silently return `""`.
  4. Build the C5 daemon: NOTIFY triggers on the three operational tables, `feedback_loop_daemon.py` that LISTENs and runs the existing sync functions, launchd plist on the Mini.
  5. On the Mini install, point AI consumers at psycopg-direct and retire the HTTP catalog-api round-trip.
- **Implementation status (as of 2026-04-28):** Locked, no implementation yet. Implementation PRs to follow per the plan above.

---

## D-15 — Handoff protocol: every session ends with a handoff, every session starts by reading one
- **Date locked:** 2026-05-02
- **Decided by:** Operator + agent
- **Decision:** At the end of every Mining Guardian work session the agent writes a handoff document at `docs/handoffs/HANDOFF_<YYYY-MM-DD>.md` using the canonical template at `docs/handoffs/HANDOFF_TEMPLATE.md`. At the start of every new session the agent's first action is to read the latest handoff before proposing or executing any change. If a session begins with a fix proposal that did not first read the prior handoff, that is a protocol violation the operator can invoke at any time to halt the session and force a rewind.
- **Why:** On the morning of 2026-05-02 the agent lost roughly an hour of paid time proposing fixes for problems that did not exist (split-brain framing on a system where split-brain had already been closed by PR #15 and PR #22, password rotation panic, near-miss `docker volume rm` against the live catalog volume) because the session started with confident assertions instead of reading the existing record. The over-documentation discipline the operator already enforces only pays back if the next session is required to read what the prior session wrote. D-15 closes that loop.
- **Mandatory handoff sections** (template enforces order): YAML header (date, session_id, last_commit_on_main); Open questions for operator at top; Mantras and standing rules in effect; Host topology — what is LIVE right now; Do not touch list; Things I currently believe that need re-verification; Today's PRs / branches / commits; Open work in priority order; Decisions made today; Costs / credits burned; Files created/modified; Failure modes spotted; Next session start checklist ending with the rule that anything stale must be confirmed with the operator before action.
- **Hard failsafe:** the operator can stop the session at any moment by saying the current proposal violates D-15. The agent rewinds to the handoff read step.
- **Implementation status:** Implemented in commit `fa6adbc` on branch `docs/handoff-protocol-state-of-system-2026-05-02`. README, template, and 2026-05-02 first handoff all created. Active starting next session.

---

## D-16 — Post-cutover masters on ROBS-PC; Mini fully self-contained at runtime
- **Date locked:** 2026-05-02
- **Decided by:** Operator + agent
- **Decision:** Once the Mac Mini cutover is verified green (target: Monday morning 2026-05-04), ROBS-PC retains the masters of the catalog Postgres database and the enrichment file artifacts (`unified_miner_index.json`, `miner_enrichment_master.csv`, `cron_tracking/` outputs) purely as a backup and as the source from which future-customer DBs are cloned. The Mac Mini does not pull anything from ROBS-PC at runtime; it is fully self-contained per cutover scope Option γ in its purest form. Once the Mini is verified self-contained, the ROBS-PC Docker container `mining-guardian-db` is shut down, the Hostinger VPS is decommissioned, and the next project (the customer-facing app) begins.
- **Why:** Operator quote 2026-05-02: *"we will only be keep the masters on robs pc, it will not be pulling anything from anywhere that is the purpose of the design fully self contained, we can then shut down the container and the vps and move on to the app"*. The earlier phrasing in `INTEL_CATALOG_FULL_BRIEF_2026-05-02.md` calling ROBS-PC "superseded" was correct in spirit but lost the master-archive role that ROBS-PC keeps. D-16 records the master-archive role explicitly so future sessions do not propose deleting ROBS-PC's catalog volume on the assumption that "superseded" means "erasable."
- **Reconciles with D-14:** D-14 sub-lock 1 says both DBs run in the same Postgres 16 container on the Mini post-cutover. That remains true. D-16 only addresses what happens to the *previous* hosts — ROBS-PC keeps an offline master copy, then its Docker container shuts down; the VPS is decommissioned. Neither is a runtime dependency of the Mini.
- **Reconciles with cutover scope γ:** D-16 is cutover scope γ in execution detail. The Mini replaces both VPS and ROBS-PC for runtime. ROBS-PC continues to exist as a development workstation and master-archive box, not as part of the Mining Guardian data plane.
- **Implementation plan:**
  1. Land installer fixes B-1, B-2, B-3, B-7, B-8, B-9, B-10 (Saturday 2026-05-02).
  2. Build, sign, and notarize v1.0.2 .pkg (Saturday evening into Sunday).
  3. Smoke-test v1.0.2 .pkg on a clean Tahoe Mac (Sunday morning).
  4. Install on the customer-site Mini via .pkg double-click with screenshots at every screen (Sunday afternoon).
  5. Verify Mini full-auto: Postgres reachable, Grafana up, Ollama responding, scheduled tasks loaded, Tailscale solid (Sunday evening).
  6. Finalize installation PDF from screenshots (Monday morning).
  7. Shut down ROBS-PC Docker container `mining-guardian-db` (Monday morning, after Mini verified).
  8. Decommission Hostinger VPS (Monday morning, after Mini verified).
  9. Begin app project (Monday onward).
- **Implementation status:** Locked 2026-05-02. Step 1 in progress on branch `docs/handoff-protocol-state-of-system-2026-05-02` (PR landing immediately after D-15 doc).

---

## D-17 — Monthly catalog sync deferred until post-cutover
- **Date locked:** 2026-05-02 (verbally, by Rob)
- **Decided by:** Operator
- **Decision:** The monthly catalog sync protocol (per D-16, ROBS-PC retains catalog masters) is deferred until after the Mac Mini cutover is verified green. The Mini ships with the current 320-row baseline catalog seed (Bitaxe import 2026-04-26, PR #102). Once the Mini is verified live (Postgres + Grafana + 9 launchd services running, miner scans flowing), the monthly sync runs on ROBS-PC, then re-clones to the Mini Postgres over Tailscale.
- **Why:**
  - Cutover is the priority — touching live catalog data on the critical path is unnecessary risk.
  - Cron jobs on the Mini write JSON/CSV files in `cron_tracking/`, NOT directly to the Postgres catalog. The catalog DB has not grown since 2026-04-26 (this is by design, not a bug).
  - Per D-16, ROBS-PC retains catalog masters post-cutover anyway, so the monthly-sync protocol is satisfied either way.
  - Operator quote 2026-05-02: "I agree with you, with this work it may take a couple of times to get it right".
- **Reconciles with D-16:** D-16 says ROBS-PC retains catalog masters post-cutover and is the source from which future-customer DBs are cloned. D-17 only sequences the recurring sync — Mini ships with the 320-row baseline seed at install time, recurring ROBS-PC → Mini sync is a post-cutover work item, not a cutover gate.
- **Implementation plan:**
  1. Mini ships with `seed_miner_models.sql` at 320 rows.
  2. Cutover proceeds Sunday 2026-05-03 via `setup.sh`.
  3. Once Mini is verified green, schedule monthly sync on ROBS-PC (separate work item, post-cutover).
  4. ROBS-PC syncs to Mini Postgres over Tailscale on schedule.
- **Implementation status:** Locked 2026-05-02. No implementation yet — first sync runs only after Mini is verified live.

---

## D-18 — v1.0.3 installer scope: feature-parity .pkg, no Mini install before then
- **Date locked:** 2026-05-03
- **Decided by:** Operator (Rob), after v1.0.2 .pkg audit (`docs/audits/PKG_AUDIT_v1.0.2_FINDINGS_2026-05-03.md`)
- **Decision:** v1.0.2 .pkg is **incomplete** — partial operations installer, not the customer-grade .pkg the operator vision requires. v1.0.3 will close ALL audit gaps. The Mini will NOT be installed (via .pkg or setup.sh) until v1.0.3 is built, signed, notarized, AND smoke-tested green on a clean Mac VM. The Hostinger VPS continues running production until v1.0.3 is verified. D-16's Monday-morning decommission timeline slips by however many days v1.0.3 takes — accepted explicitly by operator: "if we keep things for a couple of days so be it, lets get it right this time."
- **Why:** Three consecutive ".pkg" releases (v1.0.0, v1.0.1, v1.0.2) shipped as "release-grade" but were progressively closer approximations of the vision, none of which actually delivered the customer-experience goal: "install easy enough for someone who barely knows a computer." The audit found v1.0.2 .pkg would produce an Apple-confirmed "install completed" dialog with a non-functional Mini (every LaunchDaemon crash-loops within seconds, no catalog DB, no Grafana, no scheduled tasks, no customer-info collection). Apparent success, real silence — the operator's worst-case scenario.
- **Reconciles with D-16:** D-16 step 4 ("Install on the customer-site Mini via .pkg double-click with screenshots at every screen — Sunday afternoon") is amended. Replace with: "Install on the customer-site Mini via v1.0.3 .pkg double-click with screenshots at every screen — when v1.0.3 is verified green on a clean Mac VM." D-16 Monday morning sequencing (VPS decommission, ROBS-PC container shutdown) is deferred until v1.0.3 ships. ROBS-PC + VPS continue running.
- **Reconciles with INSTALL_PATHS_2026-05-02.md:** That doc's "viewer-only" framing is FACTUALLY WRONG per audit. INSTALL_PATHS is rewritten in this PR to reflect audit reality.
- **v1.0.3 scope (closes all 5 audit gaps + 4 user-facing copy bugs + 4 integration bugs):**
  - **Gap 1 — Customer-info collection — SHIPPED (PR `mg/v103-gap1-customer-info-conf`, 2026-05-04):** Postinstall reads `/Users/${SUDO_USER}/Desktop/MiningGuardian.conf` (operator hands customer a USB or AirDrop with the pre-filled .conf; customer drops on Desktop, double-clicks .pkg), validates per B-2 rules (mirrors `scripts/setup.sh::mg_validate_site_config`), and aborts BEFORE any system change with a Cocoa dialog (`osascript display dialog`) on missing or invalid input. Implementation: `installer/macos-pkg/scripts/postinstall.sh::step_collect_customer_info` (runs before `step_layout_install_root`), helpers `_conf_source` / `_conf_validate` / `_conf_fail` / `_cocoa_alert`, exit code 41 reserved for customer-info failures. Step `step_drop_dotenv` rewritten to consume the validated values + generate per-install secrets via `openssl rand -hex 32` + emit a full `.env` matching `setup.sh::phase_07_secrets` shape (closes Integration bugs 1, 2, 4 — see below). Tests: `tests/installer/test_postinstall_customer_info.sh` (76 assertions, all green; covers static checks, ordering, .env shape, exit codes, runtime validation against synthetic conf files). Avoids InstallerPane plugin complexity for v1.0.3; revisited if customer feedback demands GUI form.
  - **Gap 2 — Catalog DB + 320-row seed — SHIPPED (PR mg/v103-gap2-catalog-db-and-seed, 2026-05-04):** Postinstall creates `mining_guardian_catalog` DB in the Colima container, applies the canonical catalog schema bundle (`intelligence-catalog/seed-data/deploy_schema.sql`, which `\ir`-includes v1/v2/v3 + `staging_schema.sql`), and seeds the 320-row Bitcoin SHA-256 baseline (`seed_miner_models.sql`). Implementation: `installer/macos-pkg/scripts/postinstall.sh::step_provision_catalog_db_and_seed`, `installer/macos-pkg/scripts/build_pkg.sh` step 4g (post-assembly assertion that seed files are staged in payload), `tests/installer/test_postinstall_catalog_seed.sh` (24 assertions). Exit code 39 reserved for catalog-provisioning failures; exit code 44 reserved at build time for missing catalog seed in payload. D-20 importer-payload reconciliation (drop `mg_import_tool/***` from the .pkg payload + relocate importer migrations to canonical `migrations/`) shipped in P-004 (PR `mg/v103-d20-importer-payload-reconciliation`, 2026-05-04) — see D-20 implementation status below for details.
  - **Gap 3 — Grafana:** Vendor `grafana.app` and provisioning yaml into the .pkg payload. Postinstall installs to `/Applications/Grafana.app`, drops provisioning into `/usr/local/etc/grafana/provisioning/`, registers as 11th LaunchDaemon (`com.miningguardian.grafana.plist` if not auto-managed by .app), exposes :3000.
  - **Gap 4 — Scheduled tasks via launchd — SHIPPED (PR `mg/v103-gap4-scheduled-launchd`, 2026-05-04, P-007):** 11 launchd plists landed at `installer/macos-pkg/resources/launchd/scheduled/com.miningguardian.scheduled.<task-key-hyphenated>.plist`, one per cron entry the legacy `setup.sh::phase_10_cron` used to install. 10 plists use `StartCalendarInterval`; the hourly benchmark uses `StartInterval=3600`. One generic launcher (`installer/macos-pkg/resources/launchd/launchers/scheduled_job_launcher.sh`) sources `.env`, dispatches by file extension (`.py` → venv python, `.sh` → bash), and writes a per-run JSON stamp at `${INSTALL_ROOT}/logs/scheduled/<task_key>.last-run.json` so the operator console (D-19) can show "last run" status without a DB write at job-fire time. Implementation: new `step_install_scheduled_plists_and_bootstrap` in `installer/macos-pkg/scripts/postinstall.sh` (called after the 10 service plists; exit code 40 reserved); new `step 4i` source-tree assertion in `installer/macos-pkg/scripts/build_pkg.sh` (exit code 47 reserved) so a missing scheduled plist hard-fails the build before notarization. `scripts/setup.sh::phase_10_cron` rewritten to `phase_10_scheduled` — installs the same 11 launchd plists, removes the old `crontab -` install path entirely. `console/task_registry.py` extended with a `refinement_chain` row that P-006 had folded into `weekly_training`'s description (the cron schedule has both as separate entries; the operator console must show them separately so Pass 3+4 status is visible independently of Pass 2). Tests: `tests/installer/test_postinstall_scheduled_jobs.sh` (115 assertions covering plist file count, plist XML validity, scheduling primitive, launcher invocation, postinstall ordering, build_pkg assertion, setup.sh cron-removal, console label drift, and per-job log routing). All other installer tests still green (24+24+76+32). Console suite still 63/63. Shellcheck baselines unchanged. **Note for the v1.0.3 verification gate:** the Mac-VM smoke test should add `launchctl list | grep com.miningguardian.scheduled.` returning 11 lines, one per scheduled job, after a clean install.
  - **Gap 5 — Python venv + pip install — SHIPPED (PR mg/v103-gap5-postinstall-venv, 2026-05-04):** Postinstall creates `${MG_INSTALL_ROOT}/venv` and runs `pip install -r requirements.txt` from the vendored payload (no network for pip — vendor wheels in the payload). Implementation: `installer/macos-pkg/scripts/postinstall.sh::step_create_venv`, `installer/macos-pkg/scripts/build_pkg.sh` step 4e+4f, `installer/macos-pkg/payload-requirements.txt`, `tests/installer/test_postinstall_venv.sh`. Exit code 38 reserved for venv failures.
  - **Copy bug 1 — SHIPPED (PR `mg/v103-p008-installer-copy-and-uninstall`, 2026-05-04, P-008):** `welcome.html` updated from "four background services" → "ten background services" (9 + console). Added a sibling line documenting the eleven scheduled jobs (nightly briefings, weekly training, hourly benchmark, log collection) registered with launchd — wording deliberately avoids the literal `crontab` token so the test forbids any future regression to cron wording. Customer-facing Desktop `MiningGuardian.conf` hand-off bullet added under "What you'll need" so the customer knows to look for the file the operator hands them.
  - **Copy bug 2 — SHIPPED (PR `mg/v103-p008-installer-copy-and-uninstall`, 2026-05-04, P-008):** `welcome.html` + `conclusion.html` dashboard URL `:8080` → `:8585`. `conclusion.html` quick-link grid now shows three explicit URLs: dashboard `http://127.0.0.1:8585/`, approval API `http://127.0.0.1:8686/`, operator console `http://127.0.0.1:8787/` (D-19 / P-006 chose 8787 to avoid collision with `:8686` approval-api). Stale `:8080` / `:8081` log lines in `installer/macos-pkg/scripts/postinstall.sh::main()` corrected to the same three ports.
  - **Copy bug 3 — SHIPPED (option a, PR `mg/v103-p008-installer-copy-and-uninstall`, 2026-05-04, P-008):** New `installer/macos-pkg/resources/uninstall.sh` (mode 0755, shellcheck-clean). Covers all 10 service LaunchDaemons + 11 scheduled-job LaunchDaemons via `launchctl bootout` then plist `rm`, removes `mining-guardian-db` Postgres container (best-effort), stops the `mining-guardian` Colima profile (best-effort, never fatal), removes `/Library/Application Support/MiningGuardian/` (preserving the `postgres-data/` subdir by default), removes `/etc/mining-guardian/install-receipt.json`. Flags: `--help` / `--dry-run` / `--yes` / `--purge-data` / `--purge-logs`. **Default behavior preserves `postgres-data` and `/var/log/mining-guardian` — data deletion is opt-in via `--purge-data` per the §"Critical Safety Rules" entry forbidding bulk deletes from `mining_guardian` without an explicit step.** Refuses to run as non-root (exit 1); refuses non-TTY without `--yes` (exit 1); rejects unknown flags with exit 2; reserves exit codes 10/11/12/13 for hard failures. Wired into `postinstall.sh` via new `step_install_uninstall_script` (installs to `${MG_INSTALL_ROOT}/bin/uninstall.sh` mode 0755 root:wheel) and `build_pkg.sh` step 4j source-tree assertion (exit 48 reserved). Tests: `tests/installer/test_uninstall_script.sh` (50 assertions, all green).
  - **Copy bug 4 — SHIPPED (PR `mg/v103-p008-installer-copy-and-uninstall`, 2026-05-04, P-008):** `conclusion.html` verify-services code block now enumerates all 10 service labels (`scanner`, `dashboard-api`, `approval-api`, `slack-listener`, `slack-commands`, `overnight-automation`, `alerts`, `intelligence-report`, `console`, `feedback-loop-daemon`) and adds a `launchctl list | grep com.miningguardian.scheduled.` hint for verifying the 11 scheduled-job daemons.
  - **Integration bug 1 — SHIPPED (PR `mg/v103-gap1-customer-info-conf`, 2026-05-04):** `MG_DB_PASSWORD` flow — postinstall generates a fresh `MG_DB_PASSWORD` (and `CATALOG_API_KEY`, `INTERNAL_API_SECRET`) via `openssl rand -hex 32` directly in `step_drop_dotenv`. The old out-of-band `/tmp/mg_install_env_secret` staging step is gone; the file is defensively scrubbed if a stale v1.0.2 build left one behind.
  - **Integration bug 2 — SHIPPED (PR `mg/v103-gap1-customer-info-conf`, 2026-05-04):** `GUARDIAN_PG_USER` vs `PGUSER` mismatch — postinstall `.env` writes BOTH keys with value `mg` (matching `lib/install_colima.sh` L172 `POSTGRES_USER=mg`). Tracked as tech debt in MG_UNIFIED_TODO_LIST §3 — codebase migration to a single key name pending; both keys removed once Python codebase converges.
  - **Integration bug 3:** Tailscale handling — postinstall checks if Tailscale is already up; if yes, no-op; if no, surfaces a Cocoa dialog telling operator to run `tailscale up` separately. Tailscale auth is operator-side, not part of v1.0.2/v1.0.3 .pkg responsibility.
  - **Integration bug 4 — SHIPPED (PR `mg/v103-gap1-customer-info-conf`, 2026-05-04):** `AMS_*`, `SLACK_*`, `CATALOG_API_KEY`, `INTERNAL_API_SECRET`, `AUTHORIZED_SLACK_USER_IDS`, `AUTO_APPROVE_ENABLED` keys — written to `.env` by `step_drop_dotenv` from the customer's Desktop conf file (Gap 1) plus generated secrets. `.env` shape matches `scripts/setup.sh::phase_07_secrets` line-for-line so both install paths produce the same env surface for the Python codebase.
- **v1.0.3 verification gate (HARD, not skippable):**
  1. Build, sign, notarize, staple v1.0.3 .pkg on operator's laptop.
  2. Smoke-test on a clean macOS 14 VM (UTM/Tart). Required pass criteria:
     - Postgres container up, all 3 DBs created (`mining_guardian`, `mining_guardian_test`, `mining_guardian_catalog`).
     - `SELECT count(*) FROM hardware.miner_models;` against `mining_guardian_catalog` returns 320.
     - Grafana :3000 reachable, returns healthy JSON, AI & Learning dashboard renders.
     - All 10 LaunchDaemons (9 + console) loaded via `launchctl list | grep miningguardian`.
     - All scheduled-task launchd plists registered.
     - `~/Desktop/MiningGuardian.conf` validation passes for valid input, fails-with-Cocoa-dialog for invalid input.
     - Console reachable at `http://127.0.0.1:8787/`, displays task list + automation toggles + approval queue (D-19; port moved from :8686 → :8787 in P-006 to avoid collision with `api/approval_api.py`).
     - Cloudflare Tunnel routes `mg.fieslerfamily.com` → console (D-19).
     - Welcome + conclusion HTML show correct service counts and ports.
     - `bin/uninstall.sh` cleanly tears down everything.
  3. Only AFTER VM smoke-test passes, install on the Mini.
- **Implementation plan:**
  1. New chat session opens — agent reads PROGRAM_STATE.md, this D-18, D-19, D-20, INSTALL_PATHS_2026-05-03.md, audit findings, HANDOFF_2026-05-04_NEW_CHAT.md.
  2. Discovery task — verify what `mg_import_tool/` exposes, what the Grafana "Live Action Queue" panel does, whether approval data exists in Postgres or only in Slack today.
  3. PR train: scope-locking docs (this PR, already done), then per-gap PRs in dependency order: venv first, then catalog seed, then customer-info conf flow, then Grafana, then scheduled-tasks plists, then console (D-19), then copy-bug fixes, then uninstall.sh, then version bump + release notes.
  4. Build v1.0.3 .pkg, sign, notarize, staple.
  5. Smoke-test on clean VM. Iterate until ALL gate criteria pass.
  6. Install on Mini. Screenshots throughout.
  7. Verify Mini green per D-16 criteria.
  8. Then and only then: VPS decommission + ROBS-PC container shutdown.
- **Implementation status:**
  - Locked 2026-05-03.
  - **2026-05-04 — Source-tree closure SHIPPED across P-001 through P-009.** P-001 = discovery (PR #117, `8405d21`). P-002 = Gap 5 venv (PR #118, `ef89fff`). P-003 = Gap 2 catalog seed (PR #119, `5842f3c`). P-004 = D-20 importer reconciliation (PR #120, `b76907f`). P-005 = Gap 1 customer info conf (PR #121, `f63b9fe`). P-006 = D-19 console foundation (PR #122, `9d53856`). P-007 = Gap 4 scheduled-job launchd plists (PR #123, `ade63ef`). P-008 = Copy bugs 1-4 + real `bin/uninstall.sh` (PR #124, `c450d12`). **P-009 = version bump + release notes + pre-build readiness audit (PR `mg/v103-version-bump-and-release-notes`, 2026-05-04):** `pyproject.toml` 1.0.2 → 1.0.3 (single source of truth for `build_pkg.sh::step_3_stamp_build`); new `docs/RELEASE_NOTES_v1.0.3.md` (full P-001..P-009 record with PR cross-links + merge SHAs + build/install/verify instructions + deferred-items table + remaining gates checklist); new `docs/PRE_BUILD_READINESS_v1.0.3_2026-05-04.md` (static-analysis audit of source tree, build pipeline, test surface, plist-label and port-table drift checks — verdict: zero source-tree blockers); new `tests/installer/test_release_notes_version_drift.sh` (9 assertions, all green — guards `pyproject.toml` ↔ `RELEASE_NOTES_vX.Y.Z.md` ↔ `build_pkg.sh` SSOT coupling); MG_UNIFIED_TODO_LIST row 10 flipped 🔴 → ✅ in the same commit. **Two items deferred from v1.0.3 by explicit operator direction:** Gap 3 (Grafana vendoring + provisioning + 11th LaunchDaemon) tracked at MG_UNIFIED_TODO_LIST row 4; Cloudflare Tunnel + Access auto-provisioning (D-19 step 5) tracked at row 9. **Remaining v1.0.3 gates are operator-side and HARD per this D-18:** row 11 (build/sign/notarize/staple on operator's laptop), row 12 (clean macOS 14 VM smoke test — UTM/Tart, must pass ALL criteria in §"v1.0.3 verification gate" above), row 13 (install on Mini with screenshots per D-16 step 4 as amended), row 14 (VPS decommission + ROBS-PC container shutdown only after Mini verified green per D-16 + D-18). Until row 12 passes, the Mini is not installed; until row 13 verifies green, the Hostinger VPS keeps running production and ROBS-PC's catalog volume stays intact.

---

## D-19 — Customer operator console (10th service, Cloudflare-fronted, temporary scaffolding)
- **Date locked:** 2026-05-03
- **Decided by:** Operator (Rob)
- **Decision:** Mining Guardian v1.0.3 ships with a customer-facing operator console as the 10th LaunchDaemon. The console exposes:
  - Task registry view: every scheduled task (the 11 from setup.sh phase_10, now launchd plists per D-18) with status (running / paused / last run / next run / last result).
  - Toggles: turn each scheduled task on/off; toggle automation switches (auto-approve, alerts, overnight automation).
  - Time editing: change the schedule time of each task (e.g., morning briefing 7:00 → 8:00). Writes back to the launchd plist and reboots the daemon.
  - Approval queue: pending miner-restart and other approval items. [Approve] / [Deny] / [Snooze] buttons. The Grafana "Live Action Queue" panel at `grafana.fieslerfamily.com/d/llm_learning_001` displays the same queue but its interactive Approve/Deny is unverified — discovery task at start of v1.0.3 work confirms whether to extend the existing flow or build new.
  - Read-only system-state panel: Postgres / Grafana / Ollama / Tailscale up indicators, last successful scan timestamp, miner reachability summary.
- **Console v1 explicitly does NOT include:** creating new task types from scratch, custom alert-rule editor, miner config push, customer-info editing, multi-tenant tenant-switching, importer functionality (importer is operator-only per D-20).
- **Tech stack (locked, no bikeshedding):**
  - Backend: Python FastAPI under `console/` in repo. Reuses existing `intelligence/` and `core/` modules. Talks to Postgres + launchd via `launchctl` shell-out and `.plist` rewrites.
  - Frontend: Server-rendered Jinja2 + HTMX. No React, no node, no build step.
  - Auth: Cloudflare Access (email-based). Console binds to 127.0.0.1:8686 only — never exposed on a public IP. Cloudflare Tunnel fronts it at `mg.fieslerfamily.com` (operator's first-customer hostname; multi-tenant deferred).
- **Why:** The customer-experience vision requires a non-Slack, non-Terminal way for the customer to operate the system day-to-day. The Grafana Live Action Queue panel is a step in that direction but its interactivity is unverified. Until the phone-app project takes over (post-cutover work item), the console serves as the bridge.
- **Temporary scaffolding clause:** This console is explicitly temporary. Once the phone-app project ships, the console is retired. The phone app talks to the same launchd / Postgres surfaces, just with a better UX.
- **Cloudflare Tunnel + Access setup:**
  - Operator's `fieslerfamily.com` zone, operator's API token, operator's tunnel.
  - Hostname: `mg.fieslerfamily.com` (fiesler-family branding will be removed when customer-facing brand is locked, per operator quote 2026-05-03: "we are taking fiesler family away from the program soon as this is done").
  - Tunnel config + Access policy written by v1.0.3 postinstall step (operator pastes Cloudflare API token into Desktop conf at install time; postinstall calls `cloudflared service install` with the tunnel token).
- **Implementation plan:**
  1. Discovery: read existing approval-queue code paths (`grep -r "approval" core/ intelligence/ clients/`), determine where pending actions live (Postgres table? JSON file? Slack-only?). Result drives whether console reads from existing surface or adds a new persistent queue.
  2. Build console under `console/` — FastAPI app, routes for tasks/automation/approvals/system-state, Jinja2 templates with HTMX.
  3. Add `com.miningguardian.console.plist` to `installer/macos-pkg/resources/launchd/`.
  4. Add console to v1.0.3 postinstall bootstrapping (10th service after the 9 existing ones).
  5. Add Cloudflare Tunnel + Access setup to v1.0.3 postinstall (gated on Cloudflare token in Desktop conf).
  6. Update welcome.html + conclusion.html to mention the console URL.
  7. Document console operations in a new `docs/CONSOLE_OPERATIONS_GUIDE.md`.
- **Implementation status:**
  - Locked 2026-05-03.
  - **2026-05-04 — FOUNDATION PR (P-006) on branch `mg/v103-d19-console-foundation`.** New `console/` package: FastAPI app (`console/main.py`), task registry of the 9 services + 11 scheduled jobs (`console/task_registry.py`), launchctl wrapper (`console/launchd_controls.py`), system-state probes (`console/system_state.py`), pending-approvals helpers (`console/approvals.py`), Jinja2 templates + HTMX, static CSS. 10th LaunchDaemon plist (`com.miningguardian.console.plist`) and launcher (`console_launcher.sh`) added under `installer/macos-pkg/resources/launchd/`. `installer/macos-pkg/scripts/postinstall.sh` PLIST_LABELS + LAUNCHER_FILES extended (now lists 10 services); `installer/macos-pkg/scripts/build_pkg.sh` rsync include list extended with `console/***`. **Port note:** D-19 originally requested 8686, but `api/approval_api.py` already owns 8686 (Slack approve/deny + Bucket 9 §10.1 `/ui` GUI). Console binds to **8787** instead — documented in `docs/CONSOLE_OPERATIONS_GUIDE.md` with the full v1.0.3 port table. The follow-up copy PR for welcome.html/conclusion.html (MG_UNIFIED_TODO_LIST item 7) must use `:8787` for the console reference, NOT `:8686`. **Approval queue scope (v1):** Approve/Deny update `pending_approvals.status` directly with audit (`responded_by`); remediation execution (RESTART / PDU_CYCLE) stays with the existing Slack approval flow until a unified execution library lands as a post-cutover work item. **`INTERNAL_API_SECRET` never leaks to the browser** — verified by `test_internal_secret_never_appears_in_html` which sets a sentinel into the env and walks every public GET route. Tests: 59/59 green (`tests/console/`). **Grafana UI explicitly untouched in this PR** — Grafana is the visibility surface; the console is the control surface (per operator clarification 2026-05-04). Items still deferred from this PR: Cloudflare Tunnel + Access auto-provisioning (D-19 step 5), Gap 4 plist generators for the 11 scheduled tasks (MG_UNIFIED_TODO_LIST item 5), welcome/conclusion copy update (item 7), real `bin/uninstall.sh` covering 10 services (item 8).

---

## D-20 — Importer stays with operator forever (single-source-of-truth catalog model)
- **Date locked:** 2026-05-03
- **Decided by:** Operator (Rob)
- **Decision:** The hardware-catalog importer (`mg_import_tool/`) stays on the operator's workstation forever. It is NOT shipped to customers. The customer .pkg will not include `mg_import_tool/` in its payload (or if it does for code-coupling reasons, no LaunchDaemon or console UI surfaces it).
- **Catalog distribution model:**
  - Operator runs the importer monthly on their workstation (or ROBS-PC per D-16) → catalog DB updated → knowledge JSON regenerated.
  - Operator pushes a delta (or full snapshot) to all customer Minis over Tailscale.
  - Customer Minis are read-only consumers of the catalog. They never run the importer.
  - "Single source of truth" — one master catalog, one operator, N read-only customer copies.
- **Why:** Operator quote 2026-05-03: "the importer does not go to the customer that stays with me, once a month we will go a update of the intelligence db and the knowledge json for customers that way there is only 1 truth."
- **Reconciles with D-16:** D-16 says ROBS-PC retains catalog masters post-cutover. D-20 confirms the importer is the tool that maintains those masters, and ROBS-PC (or operator's laptop) is where it runs. Never on a customer Mini.
- **Reconciles with D-17:** D-17 deferred the monthly catalog sync to post-cutover. D-20 specifies the architecture (operator-runs-importer → Tailscale push to customer Minis) but does NOT change the deferral. First sync runs only after Mini is verified green.
- **Implementation plan:**
  1. v1.0.3 .pkg payload audit: confirm `mg_import_tool/` is NOT bundled into the customer .pkg, OR if it is (for shared-code reasons), no UI surfaces it.
  2. Post-cutover work item: build the operator-side delta-push tool (Tailscale rsync or postgres dump-restore) — separate work, not v1.0.3 scope.
  3. Document the catalog distribution model in `docs/CATALOG_DISTRIBUTION_MODEL.md` (separate PR, post-cutover).
- **Implementation status:**
  - Locked 2026-05-03.
  - **2026-05-04 — RECONCILED in PR `mg/v103-d20-importer-payload-reconciliation` (P-004).** `installer/macos-pkg/scripts/build_pkg.sh` step 4a no longer includes `mg_import_tool/***` in the rsync include list, and the cross-directory `mg_import_tool/sql/migrations/` rsync at the old 4b is removed. Runtime-relevant importer migrations (field-log bootstrap + layer-2 resolver) were relocated to `migrations/006_field_log_bootstrap.sql` and `migrations/007_layer2_resolver.sql` (next free numeric prefixes after the existing 001/003/004/004/005), with body content byte-identical to the importer-side originals so idempotency is preserved on Minis that already had 000/002 applied via earlier .pkg builds. New `step 4h` post-assembly assertion runs `find "$PAYLOAD_DIR" -name 'mg_import*'` and aborts the build with exit 43 if any match — belt-and-suspenders against future regression. Operator-side originals at `mg_import_tool/sql/migrations/000_bootstrap_field_log_tables.sql` and `mg_import_tool/sql/migrations/002_layer2_and_learning_foundation.sql` are intentionally retained as the importer's own bootstrap source on the operator workstation (D-20 footnote — importer is operator-only forever; the importer needs its own copy). Tests: `tests/installer/test_d20_importer_payload_reconciliation.sh` (32 assertions, all green); existing `tests/installer/test_postinstall_catalog_seed.sh` (24/24) and `tests/installer/test_postinstall_venv.sh` (24/24) still green; build_pkg.sh shellcheck warnings: 5 → 2 (improvement). End-to-end smoke test (clean macOS 14 VM install) is the v1.0.3 D-18 verification gate, run AFTER this PR + the rest of the PR train merge.

---

*Append new decisions below this line. Do not edit history.*
