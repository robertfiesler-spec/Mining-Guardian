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
  - **2026-05-04 — P-015 (preinstall arch gate Rosetta-safe) landed in PR `mg/v103-d18-p015-arch-gate-rosetta-safe`.** Bobby ran the corrected v1.0.3 build (`MiningGuardian-1.0.3-2b48f98e6b77.pkg`, source main `2b48f98`, P-013 + P-014 in) on the customer Mac mini and the install hard-failed at `gate_apple_silicon`: `/var/log/mining-guardian/install-preinstall.log` showed `OK gate_root` + `OK gate_macos_version: 26.4.1 >= 13.0` + `FATAL (12) this build supports Apple Silicon (arm64) only; detected 'x86_64'` on a documented M-series Mac mini. Root cause: the gate compared `/usr/bin/uname -m` against `arm64`. `uname -m` reports the architecture of the calling process, NOT the hardware. On Apple Silicon, if Installer.app spawns the preinstall under a Rosetta-translated `/bin/bash` (Terminal.app set to "Open using Rosetta", or `arch -x86_64 sudo installer ...`), `uname -m` returns `x86_64` even though the Mac is M-series. The kernel-authoritative hardware indicator is `sysctl hw.optional.arm64`, which the kernel sets from the SoC and which does NOT change under Rosetta translation. Fix: `gate_apple_silicon` now reads `sysctl -n hw.optional.arm64` first and short-circuits accept on `=1` regardless of `uname -m`; logs `sysctl.proc_translated` for diagnostics with a Rosetta-context warning if `=1`; falls back to `uname -m` only when sysctl is unreadable, accepting only when uname agrees with `arm64` (defensive — never accept x86_64 in the absence of authoritative arm64 evidence). Intel-only support remains explicitly out of scope (CLAUDE.md / D-18 / Vision Anchor 2). Tests: new `tests/installer/test_preinstall_arch_gate.sh` (11 assertions, all green) — 6 static drift guards covering `bash -n`, sysctl reads, the `hw_arm64` decision branch, the `fail 12` rejection path, and the P-015 audit marker; 5 functional scenarios using a PATH-shadowed sysctl/uname mock harness (native arm64 → 0; arm64 under Rosetta with uname=x86_64 → 0, the bug being fixed; Intel rejected → 12; sysctl-missing+uname-x86_64 defensive reject → 12; sysctl-missing+uname-arm64 defensive accept → 0). All prior installer suites still green. **No build_pkg.sh, payload, or notarization-relevant code touched** — purely preinstall logic, so the rebuilt .pkg's payload is byte-identical to 2b48f98 modulo the script-archive bytes for `preinstall`. The existing `MiningGuardian-1.0.3-2b48f98e6b77.pkg` is NOT a shippable artifact (will hit the same false-negative on any host whose Terminal.app or invoking shell is Rosetta-translated); cleanup + rebuild + reinstall path is in the PR description and the runbook.
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

---

## D-21 — Build-time re-signing of Mach-O inside vendored Python wheels

- **Date locked:** 2026-05-04
- **Decided by:** Operator (Rob), implemented by P-011 PR train
- **Decision:** Mach-O binaries inside vendored Python wheels (`<payload>/python-wheels/*.whl/**/*.so` and `*.dylib`) MUST be re-signed at .pkg build time with the Developer ID Application identity, hardened runtime, and a secure timestamp. The wheel's `*.dist-info/RECORD` manifest MUST be rewritten with the new sha256 + size for every modified file so that pip still accepts the wheel as a valid install source on the customer Mac (offline `--no-index` install).
- **Why this exists:** Apple notary submission `750c089f-f0a1-4d40-bf15-e8c295828027` (v1.0.3 first build, sha `295aec38f2ee`, 2026-05-04) returned `Invalid` with rejections inside aiohttp, bcrypt (universal2), matplotlib, and other wheels. PyPI wheels ship binaries signed by the package maintainer's certificate, NOT with our Developer ID, AND without a secure timestamp, AND without hardened runtime. Apple notary walks every Mach-O including those embedded inside zip archives, so vendored wheels with C extensions break notarization unless we re-sign them at build time.
- **Why we own the re-signing in `build_pkg.sh`, not on the customer Mac:**
  - The Developer ID Application private key lives only on the build host. Re-signing at install time would require shipping the key (security regression) or signing with an ad-hoc identity (still rejected by notary since notary runs at build time, not install time).
  - The customer Mac is the consumer of an already-notarized .pkg; once stapled, no further signing happens at install time.
- **Why we rewrite RECORD in place rather than mark wheels as un-installable:**
  - pip verifies sha256 + size of every file in RECORD on install. A naive zip edit breaks pip install. The only correct approaches are (a) rewrite RECORD, or (b) bypass pip and unpack manually. (b) loses pip's metadata layer (entry points, console scripts, dist-info installation tracking) and would diverge from the upstream `pip install` contract that postinstall expects.
  - Approach (a) is what `installer/macos-pkg/scripts/lib/resign_wheel.py` implements, with a post-rewrite verify pass that catches RECORD/contents drift before the .pkg is signed.
- **Why we keep this stdlib-only Python and not a .sh script:**
  - sha256 + base64-urlsafe-no-pad encoding (PEP 376) and zip read/write are clean in `hashlib` + `zipfile`. Doing the same in shell would need `openssl dgst -sha256 -binary | base64 | tr +/ -_ | tr -d =` per file — error-prone and slow.
  - We use `/usr/bin/python3` (the OS-stub Python that ships with macOS) so we don't add a second dependency on the Homebrew `python@3.12` install path that postinstall already pins.
- **Out of scope for this decision:**
  - Re-signing Mach-O inside .app or .framework bundles embedded inside wheels — wheels do not currently ship those, and even if they did, the bundle would need `--deep` re-sealing which differs from per-file signing. Add a guard if/when the case appears.
  - Pure-Python wheels (no Mach-O) — RECORD is left byte-identical.
- **Files touched:**
  - `installer/macos-pkg/scripts/build_pkg.sh` — new `step_4c_resign_inner_wheels`, ordering 4 → 4b → 4c → 5; `step_6_notarize` auto-fetches detail log on failure; new exit code 49.
  - `installer/macos-pkg/scripts/lib/resign_wheel.py` — new helper, stdlib-only.
  - `tests/installer/test_wheel_resign.sh` — new regression test (15 assertions).
  - `docs/RUNBOOK_PKG_REBUILD.md`, `docs/MG_UNIFIED_TODO_LIST.md`, `docs/LATENT_BUGS.md` — updates.
- **Verification gate:** D-18's "clean macOS 14 VM smoke test" remains the gate. After this PR merges, the operator must:
  1. `git pull` on the build host.
  2. Re-run `make pkg` per `docs/RUNBOOK_PKG_REBUILD.md` Block A. The new step 4c runs automatically; expect a new `[resign_wheel]` summary line in the build log.
  3. Watch for `notarization status: Accepted` in step 6.
  4. Smoke-test the resulting .pkg on a clean macOS 14 VM before re-running on the Mini.
- **Rollback plan:** If P-011 itself misbehaves (e.g., RECORD rewrite breaks a wheel that was previously fine), the operator can revert the PR and rebuild — but the v1.0.3 .pkg `MiningGuardian-1.0.3-295aec38f2ee.pkg` already exists on disk in a notary-rejected state, and the wheel re-signing approach is the only forward path for a vendored-wheels payload. An alternative would be to replace every C-extension wheel with a pure-Python equivalent, which is not feasible for `psycopg2-binary`, `cryptography`, `pillow`, `numpy`, etc.

---

## D-22 — Skip separate clean-VM smoke test; Mac Mini is the first clean-target install

- **Date locked:** 2026-05-04
- **Decided by:** Operator (Rob)
- **Decision:** D-18's verification gate originally required a clean macOS 14 VM smoke test (UTM/Tart) BEFORE any Mac Mini install of the v1.0.3 .pkg. That step is skipped by operator decision. The Mac Mini becomes the first clean-target install for `MiningGuardian-1.0.3-a35728dcfc8c.pkg`. Every other safeguard from D-18 still applies — postinstall step ordering, Cocoa-dialog + exit-41 behavior on customer-info validation failure, `bin/uninstall.sh` rollback, and the post-install verification stages all remain in force.
- **Why:** Operator quote: no VM available; preferred to transfer the installer over the network rather than buy or use a USB-C adapter and burn a day on a UTM image. The package itself was built, signed, notarized, stapled, AirDropped to the Mini, checksum-verified (`MiningGuardian-1.0.3-a35728dcfc8c.pkg: OK`), Gatekeeper-accepted on the Mini (`accepted, source=Notarized Developer ID, origin=Developer ID Installer: Robert Fiesler (ARJZ5FYU94)`), and the Desktop conf passed all seven shape checks before the operator paused for a meeting. Skipping the VM step does not skip verification — it consolidates it onto the Mini.
- **Reconciles with D-18:** D-18 §"v1.0.3 verification gate" item 2 ("Smoke-test on a clean macOS 14 VM (UTM/Tart). Required pass criteria: …") is amended for the v1.0.3 install only. The same pass criteria still apply, but they are evaluated against the Mini after install rather than against a separate VM beforehand. Items 1 and 3 of that gate (build/sign/notarize/staple, then install on Mini AFTER VM passes) collapse into "build/sign/notarize/staple, then install on Mini and run the same pass criteria there."
- **Reconciles with D-16:** Unchanged. The Hostinger VPS continues running production. ROBS-PC catalog masters stay intact. VPS decommission and ROBS-PC container shutdown still happen only AFTER the Mini is verified green per D-16 + D-18 + this D-22.
- **Implication for future installs:** This is a one-off for the v1.0.3 install on Rob's first Mini. Customer-grade releases must restore a VM smoke gate or an equivalent isolated-target gate. A real customer install cannot be "first clean-target install + screenshots." See `docs/CUSTOMER_ONBOARDING_UX_GAPS_2026-05-04.md` and D-23 for the customer-grade direction.
- **Source of truth on the pause point:** `docs/handoffs/HANDOFF_2026-05-04_PAUSED_BEFORE_MINI_INSTALL.md`. Includes the package SHA, notary submission ID, transfer chain, validated-config shape checks, and the resume checklist.
- **Implementation status:**
  - Locked 2026-05-04.
  - **2026-05-04 — Captured in `docs/handoffs/HANDOFF_2026-05-04_PAUSED_BEFORE_MINI_INSTALL.md`** alongside the full pause-state record. Postinstall verification pulls the same pass criteria as D-18 §"v1.0.3 verification gate" item 2, evaluated post-install on the Mini.

---

## D-23 — Customer-onboarding UX gaps captured as forward-looking scope; not v1.0.3

- **Date locked:** 2026-05-04
- **Decided by:** Operator (Rob)
- **Decision:** The 2026-05-04 install staging surfaced a set of customer-onboarding UX gaps that are NOT in v1.0.3 scope and must NOT be pulled into the current pause-resume work. They are tracked in `docs/CUSTOMER_ONBOARDING_UX_GAPS_2026-05-04.md` and `docs/MG_UNIFIED_TODO_LIST.md` §18 for a future installer iteration that targets nontechnical customers rather than the operator. The v1.0.3 .pkg already on disk on the Mac Mini ships unchanged.
- **Gaps in scope of this decision (forward-looking only):**
  1. Customer-info collection should not be a hand-edited Desktop file. Replace `MiningGuardian.conf` `nano` editing with a native Installer.app form pane (InstallerPane plugin) or a first-run setup assistant with format hints, inline validation, and live credential testing.
  2. Tailscale guided onboarding: detect state, install if missing, walk the customer through `tailscale up`, show the Mini's tailnet name and the URLs they will use after, and add at least one of the customer's other devices to the same tailnet. Free-tier Tailscale is acceptable for Mining Guardian's typical deployment shape.
  3. Grafana dashboard auto-provisioning: vendor `Grafana.app`, drop datasource + dashboard provisioning yaml under `/usr/local/etc/grafana/provisioning/`, vendor every dashboard JSON under the install root, register an 11th LaunchDaemon if required, and open the customer to the AI & Learning dashboard on first boot. Tied to D-18 Gap 3 / `MG_UNIFIED_TODO_LIST.md` §1.2 row 4.
  4. Pre-install Slack / AMS connectivity validation: validate values actually work (Slack webhook ping, AMS `/api/v1/login` round-trip, workspace ID resolution) BEFORE any system state is touched. Plain-language error messages per failure mode; customer fixes typo in-place.
  5. Support bundle: a single `mg-support-bundle` command (also a button in the operator console) that captures last 24h of logs, `launchctl list`, last-run JSON stamps, service status, redacted `.env` shape (keys present, values redacted), package version + commit SHA + notarization status, into a single tar.gz on the Desktop. Zero credential values ever leave the Mini.
  6. `MG_DRY_RUN=true` as the safe default with a customer-facing explanation, a banner in the operator console when in dry-run, and a one-click "Switch to live mode" path gated on customer confirmation.
  7. Recovery / uninstall path surfaced in the operator console — "Reset Mining Guardian" button that runs `bin/uninstall.sh --dry-run` first, shows a preview, and asks for confirmation. Destructive `--purge-data` requires red affordance + double-confirm. "Re-run setup assistant" path for customers who want to rotate AMS or Slack credentials.
  8. Screenshot-ready customer runbook (PDF or web doc, SVG-first) walking every dialog the customer will see in order, with annotated screenshots; updated whenever a dialog string changes.
- **Why:** Operator quote 2026-05-04: "customers should be guided through Tailscale setup if they need private remote access; customers can use the free Tailscale option for a small/two-computer setup; the installer or first-run UX should help customers sign up for or connect Tailscale when needed; the UX should also help customers get Grafana running, including loading Mining Guardian dashboard JSON automatically rather than asking them to build charts by hand." Combined with the 2026-05-04 install-staging incident where a manually-edited `MiningGuardian.conf` typo'd `CUSTOMER_NAME` as `REPLACE_ME_SITE_NAME` and would have failed shape validation if not caught manually. Today's installer is "easy enough for the operator who built it." This decision locks the direction toward "easy enough for someone who barely knows a computer" without committing to a specific implementation.
- **Explicitly NOT v1.0.3 scope:** None of the above is implemented for the v1.0.3 .pkg sitting on the Mini. The current pause-resume work continues as-is. Any session that picks up this scope must open a separate work train against `main` after the Mini install is verified green.
- **Reconciles with:**
  - D-18 — Gap 3 (Grafana) and Cloudflare Tunnel auto-provisioning (D-19 step 5) are already deferred under D-18 / `MG_UNIFIED_TODO_LIST.md` §1.2 rows 4 and 9. D-23 captures the customer-grade expansion of Gap 3 (dashboard JSON auto-load, datasource provisioning, default-credential rotation) without changing the row-4 deferral.
  - D-19 — Operator console at `:8787` is the eventual home for the support-bundle button, the dry-run banner, the "Switch to live mode" toggle, and the "Reset Mining Guardian" button. The "Re-run setup assistant" path is also a console addition.
  - D-22 — Skipping the VM smoke gate is one-off for the v1.0.3 Mini install. Customer-grade releases per D-23 must restore an isolated-target gate equivalent to the original D-18 VM step.
- **Source of truth on the gaps:** `docs/CUSTOMER_ONBOARDING_UX_GAPS_2026-05-04.md`. New rows in `docs/MG_UNIFIED_TODO_LIST.md` §18.
- **Implementation status:**
  - Locked 2026-05-04.
  - **2026-05-04 — Forward-looking scope captured in `docs/CUSTOMER_ONBOARDING_UX_GAPS_2026-05-04.md` (8 gaps with acceptance criteria) + `docs/MG_UNIFIED_TODO_LIST.md` §18 (8 rows, all 🔴 OPEN).** No code touched. No installer logic changed. The v1.0.3 .pkg sitting in `~/Downloads` on the Mini is unchanged.

---

## D-24 — pkgbuild scripts must be staged with extensionless names (`preinstall`, `postinstall`)

- **Date locked:** 2026-05-04
- **Decided by:** Bobby (operator)
- **Decision:** `installer/macos-pkg/scripts/build_pkg.sh::step_4_assemble_payload` step 4d is the only place in the build pipeline allowed to write into `${BUILD_DIR}/stage/scripts/`. After it `rsync`'s the source `installer/macos-pkg/scripts/` directory into the staging dir, it MUST `mv -f` the two top-level scripts into extensionless names (`preinstall` and `postinstall`), `chmod 0755` them, and refuse to proceed if any `*.sh` file remains at the top level of the staging dir (`find -maxdepth 1 -type f -name '*.sh'` + `_die 43`). Source files keep the `.sh` extension on disk so editors render them as bash, shellcheck recognizes them, and `bash -n` works in CI. The rename happens at staging time only.
- **Why:** Apple's `pkgbuild --scripts` honors EXACTLY two top-level filenames in the Scripts archive: `preinstall` and `postinstall`, with NO extension (per `man pkgbuild`). PackageKit silently ignores any other filename — including `preinstall.sh` and `postinstall.sh`. v1.0.3 build `MiningGuardian-1.0.3-a35728dcfc8c.pkg` shipped with `preinstall.sh` / `postinstall.sh` in its Scripts archive: install reported success, payload + receipt landed at `/Library/Application Support/MiningGuardian/`, and the scripts NEVER fired. The Mac mini ended up with a payload-only install (no `.env`, no venv, no Postgres bootstrap, no LaunchDaemons, no `/etc/mining-guardian/install-receipt.json`, no `/var/log/mining-guardian/install-postinstall.log`). `/var/log/install.log` showed PackageKit extracted the payload + wrote the receipt + logged "Installed Mining Guardian (1.0.3)", but ZERO preinstall/postinstall script execution lines.
- **Reconciles with:**
  - D-18 — every D-18 audit gap that lands as a postinstall step (Gap 1 customer-info Cocoa dialog, Gap 2 catalog DB seed, Gap 4 scheduled-job launchd plists, Gap 5 venv + offline pip install) is silently bypassed if the scripts are named with `.sh`. D-24 is therefore a hard prerequisite on D-18 even though D-18 didn't call it out — the audit assumed Apple's tooling ran scripts named the way the source tree names them.
  - D-22 — the Mini install path (no separate VM smoke gate) means a script-naming bug surfaces directly on the customer Mac mini with no earlier detection. D-24 closes that detection gap with a build-time assertion; future installs cannot ship a payload-only .pkg.
- **Implementation status:**
  - Locked 2026-05-04.
  - **2026-05-04 — Fix landed in PR `mg/v103-p013-pkg-scripts-naming` (P-013):** `build_pkg.sh::step_4_assemble_payload` step 4d now `mv -f "${SCRIPTS_DIR}/preinstall.sh" "${SCRIPTS_DIR}/preinstall"` and `mv -f "${SCRIPTS_DIR}/postinstall.sh" "${SCRIPTS_DIR}/postinstall"`, `chmod 0755` both, asserts both are `-x`, and refuses to proceed if any `*.sh` remains at the top of the staging dir. Tests: new `tests/installer/test_pkg_scripts_naming.sh` (15 assertions, all green). All 9 prior installer test suites still green. `build_pkg.sh` shellcheck baseline unchanged. **Critical operator note:** the existing v1.0.3 `MiningGuardian-1.0.3-a35728dcfc8c.pkg` is NOT a shippable artifact — it has signed payload + valid receipt but no postinstall ever ran. The Mac mini currently has a payload-only install. Cleanup + rebuild + reinstall path lives in the PR description and `docs/RUNBOOK_PKG_REBUILD.md` Block-Cleanup.
- **Detection (durable):** `pkgutil --expand <pkg> /tmp/x && ls /tmp/x/core.pkg/Scripts/` MUST show two files named `preinstall` and `postinstall` (no extension), both `-x`. If they appear as `preinstall.sh` / `postinstall.sh`, the .pkg is broken, no matter what `installer -pkg` reports at install time.

---

## D-25 — Apple Silicon hardware gate uses `sysctl hw.optional.arm64`, never `uname -m`

- **Date locked:** 2026-05-04
- **Decided by:** Bobby (operator)
- **Decision:** Any installer-side or runtime-side check that gates on Apple Silicon hardware MUST read the kernel's `hw.optional.arm64` flag via `sysctl -n hw.optional.arm64` (returns `1` on Apple Silicon, `0` on Intel, missing on legacy/exotic kernels). It MUST NOT use `/usr/bin/uname -m` as the authoritative signal, because `uname -m` reports the architecture of the calling process, not the hardware. On Apple Silicon, a Rosetta-translated `/bin/bash` will return `x86_64` for `uname -m` even though the Mac is M-series. `sysctl.proc_translated` may be read for diagnostics (`=1` ⇒ this process is running under Rosetta 2; `=0` ⇒ native; missing ⇒ Intel) but MUST NOT be a gate — Rosetta-translated processes on Apple Silicon hardware are valid, the daemon and postinstall will run native arm64 once LaunchDaemons fire. `uname -m` is allowed only as a defensive fallback when `sysctl hw.optional.arm64` is unreadable, and only to ACCEPT (when `uname -m == arm64`); it must never be used to ACCEPT `x86_64` in the absence of authoritative arm64 evidence. Intel-only support remains explicitly out of scope per CLAUDE.md / D-18 / Vision Anchor 2.
- **Why:** v1.0.3 build `2b48f98` shipped P-013 + P-014 fixes that finally let PackageKit invoke the preinstall script on the Mac mini. The first install attempt hard-failed at `gate_apple_silicon`: `/var/log/mining-guardian/install-preinstall.log` showed `FATAL (12) this build supports Apple Silicon (arm64) only; detected 'x86_64'` on what is documented in CLAUDE.md as an M-series customer Mac mini. The signal misled — the hardware is arm64, but `uname -m` returned `x86_64` because the bash interpreter the installer spawned was running under Rosetta 2 translation (Terminal.app preference, or `arch -x86_64 sudo installer ...`). This is a documented Apple behavior, not a hardware question. Using `uname -m` as the authoritative signal made a non-blocking process attribute look like a hard hardware refusal. The kernel-set `hw.optional.arm64` flag is invariant under translation: on Apple Silicon it reads `1` from a Rosetta-translated process, a native arm64 process, and any future translation layer. It is the only correct primitive for "is this hardware Apple Silicon."
- **Reconciles with:**
  - D-18 — the v1.0.3 verification gate already required Apple-Silicon-only support; D-25 corrects how that gate is enforced in code without weakening the policy.
  - D-22 — the Mini IS the first clean-target install for v1.0.3, so a process-attribute false-negative surfaces directly on the customer Mac with no earlier detection. D-25 closes the false-negative path with a sysctl-first probe + a static drift test.
  - D-24 — without D-24, the preinstall never ran at all, so this gate had never been exercised in a real install. D-24 made the script run; D-25 made the script trust the right signal.
- **Implementation status:**
  - Locked 2026-05-04.
  - **2026-05-04 — Fix landed in PR `mg/v103-d18-p015-arch-gate-rosetta-safe` (P-015):** `installer/macos-pkg/scripts/preinstall.sh::gate_apple_silicon` rewritten as described above. Tests: new `tests/installer/test_preinstall_arch_gate.sh` (11 assertions, 6 static + 5 functional). All prior installer test suites still green. **No build_pkg.sh / payload / notarization-relevant code touched.** Source-tree change is preinstall-only.
- **Detection (durable):** Any future code in this repo that reads `uname -m` to make a HARDWARE decision (as opposed to a per-process decision such as picking an arm64 vs x86_64 binary to invoke) is a regression. `tests/installer/test_preinstall_arch_gate.sh` §2 + §4 fail if `gate_apple_silicon` drops the `hw.optional.arm64` branch.

---

## D-26 — Halt all Mac mini install attempts until full installer preflight audit completes

- **Date locked:** 2026-05-05
- **Decided by:** Bobby (operator)
- **Decision:** No further v1.0.3 `.pkg` install attempts will be run on the customer Mac mini until BOTH of the following are true: (1) P-024 — the catalog seed / `hardware.manufacturers` schema mismatch fix — is merged into `main` (✅ done as of `6a48a82` / PR #142, 2026-05-05); (2) the full installer preflight audit PR (P-025) is merged into `main`, AND every P0 gap that audit surfaces is also merged. The audit is an end-to-end review of every postinstall step downstream of `step_provision_catalog_db_and_seed` that has NOT been exercised live yet (uninstall script install, console plist registration, scheduled-job plists, log-collector plist, Ollama install, daily/weekly cron staging, anything else the installer does after the seed). The audit must produce a single audit doc enumerating every untested step and any prerequisite gaps it finds; gaps may be fixed in the audit PR itself or filed as new P-NNN rows in `docs/MG_UNIFIED_TODO_LIST.md` with explicit "must-fix-before-Mini" gating. After the audit + any P0 fixes merge, the operator builds a fresh `.pkg` off the merged `main`, runs Mac-mini cleanup per the existing canonical template (`docs/handoffs/HANDOFF_2026-05-04_NIGHT_PAUSE_POSTINSTALL_FAILURE.md`), and only then runs Round 9.
- **Why:** The v1.0.3 train ran eight live install rounds on the customer Mac mini between 2026-05-04 and 2026-05-05. Each round produced exactly one new postinstall failure (Round 1 P-014 arch gate / Round 2 P-015 payload path / Round 3 P-016 helper-lib operator-user / Round 4 P-018 PATH under sudo -u / Round 5 P-019 limactl + VZ / Round 6 P-020/P-021 env handoff / Round 7 P-022 migration 007 prereqs / Round 8 P-023 + P-024 catalog seed schema mismatch). Each round leaves the customer mini in a half-installed state — Colima profile created, postgres image loaded, operational DB partially or fully migrated, catalog DB partially seeded, no LaunchDaemons loaded, no `bin/uninstall.sh` installed (the uninstaller's installer step runs after the seed, so cleanup remains manual every time). Continuing the one-failure-at-a-time chain wastes build cycles, produces operator cleanup work between every round, and risks the next failure being downstream of seeds where state is harder to roll back. Operator quote 2026-05-05: "stop one failure at a time and inspect the rest of installer path before another mini install." D-26 makes that pause an explicit locked rule rather than a per-session preference.
- **Scope of the audit (non-exhaustive — the audit subagent owns the final list):**
  1. `step_install_uninstall_script` — verify it actually lays down `bin/uninstall.sh` mode 0755 with the documented arg surface (`--dry-run`, `--purge-data`).
  2. Console (10th LaunchDaemon, port 8787) — verify `com.miningguardian.console.plist` registers cleanly under `launchctl bootstrap system`, that the FastAPI app starts, and that the console serves at `http://127.0.0.1:8787/` with the documented routes.
  3. Scheduled-job plists (D-18 Gap 4) — verify every one of the scheduled-job plists loads and that their `LaunchOnlyOnce` / `StartCalendarInterval` configs match `docs/CRON_SCHEDULE.md`.
  4. Log-collector plist — verify it loads and that `/var/log/mining-guardian/*.log` rotation is wired.
  5. Ollama install — verify the install path, the model selection logic per D-13 (RAM-driven `llama3.2:3b` vs `qwen2.5:14b-instruct-q4_K_M`), and that `ollama list` post-install matches the choice.
  6. Daily / weekly cron staging — verify `train_cohort.py` weekly + `daily_deep_dive.py` daily + `refinement_chain.py` Sunday-after-train all have correct cron lines installed.
  7. Anything else the audit subagent identifies that postinstall does after `step_provision_catalog_db_and_seed`.
- **Reconciles with:**
  - D-18 — v1.0.3 installer scope is unchanged; D-26 is a process gate on WHEN the install is attempted, not WHAT the installer ships.
  - D-22 — Mac Mini remains the first clean-target install; D-26 narrows the "ship and watch" cadence to a single attempt after the audit, not a per-fix attempt. D-22's skip-VM decision is NOT widened by D-26 — the audit subagent may recommend an isolated-target validation step before Round 9, but D-26 does not unilaterally require one.
  - D-23 — customer-onboarding UX gaps remain forward-looking; D-26 does not pull any of them into v1.0.3.
  - D-24 / D-25 — script naming and arch gate are already merged and out of the install-failure chain.
- **Implementation status:**
  - Locked 2026-05-05.
  - **2026-05-05 — P-024 merged into `main` as `6a48a82` (PR #142).** Catalog seed schema mismatch is closed; row 10p in `MG_UNIFIED_TODO_LIST.md` is ✅. The remaining gate under D-26 is the preflight audit (P-025) plus any P0 fixes the audit surfaces.
  - **2026-05-05 — Captured in `docs/handoffs/HANDOFF_2026-05-05_INSTALLER_ROUNDS_AND_PREFLIGHT_AUDIT.md` (this PR)**, which lists the round-by-round timeline through Round 8, the merged P-024 fix, the in-flight preflight-audit subagent PR, and the resume path for the next session. New `MG_UNIFIED_TODO_LIST.md` row 10q (preflight audit / P-025) added in this PR as a 🔴 OPEN placeholder pointing at the subagent PR. No source / build / test code changed.
- **Detection (durable):** Any future session that builds a v1.0.3 `.pkg` from `main` and runs `sudo installer -pkg ... -target /` on the customer Mac mini before the preflight-audit PR (P-025) and any P0 fixes it surfaces are merged into `main` is violating D-26. The signal is `git log --oneline main` not containing the audit PR (and any P0 fix PRs the audit names) at the time of the install attempt.

---

## D-27 — Python 3.12 is installer-owned; no Homebrew prerequisite on customer Mac mini

- **Date locked:** 2026-05-05
- **Decided by:** Bobby (operator)
- **Decision:** The Mining Guardian `.pkg` MUST own its own Python 3.12 runtime. Customers MUST NOT be required to install Homebrew, run `brew install python@3.12`, edit `PATH`, or satisfy any other Python prerequisite ahead of running the `.pkg`. The .pkg vendors a relocatable Python 3.12 interpreter under `<payload>/runtime/python/` (recommended source: python-build-standalone `install_only_stripped` for `aarch64-apple-darwin`, version 3.12.x). `installer/macos-pkg/scripts/build_pkg.sh::step_4i_stage_python_runtime` stages the runtime from `${HOME}/MiningGuardian-vendor/python-runtime/` at build time, validates it (Mach-O, version 3.12.x, `import venv` succeeds, post-rsync sanity), and exits 43 if any check fails. `installer/macos-pkg/scripts/postinstall.sh::step_create_venv` resolves the packaged interpreter (flat `bin/python3.12` OR `Python.framework/Versions/3.12/bin/python3.12`) BEFORE any Homebrew or PATH fallback at install time; the fallback path remains for source-tree dev / smoke-test runs only and is logged as `WARN`. Operator-side: `docs/RUNBOOK_PKG_REBUILD.md` "Block Pre-B — populate the Python runtime" is a one-time-per-build-host step (re-run only when bumping Python 3.12 patch level). Customer-side: nothing changes — the customer runs the `.pkg` and never sees Python.
- **Why:** Round 9 of the Mac mini install (2026-05-05, package `MiningGuardian-1.0.3-00720ab71cc4.pkg`, built off main `00720ab` after P-024 + P-025 merged) progressed past every prior gate (env keys exported, Colima VZ started, postgres image loaded, all 8 operational migrations applied, catalog DB created and schema-deployed, **catalog seed verified at 320 rows**, all 9 launcher wrappers installed) and then exited 38 in `step_create_venv` with `FATAL (38) python3.12 not found on this Mac; install Homebrew + python@3.12 before running the .pkg`. Pre-D-27 the `.pkg` resolved Python 3.12 from `/opt/homebrew/opt/python@3.12/bin/python3.12` — the customer Mac mini did not have Homebrew installed (and was not expected to). That made Homebrew + `python@3.12` a hidden customer prerequisite, which violated CLAUDE.md "Working Principles" ("Future customer-ready installer should not require a nontechnical user to edit config files or manually satisfy hidden prerequisites") and the customer-onboarding bar already documented under D-23. Operator quote 2026-05-05: "yes include it in the installer and whatever else might pop up as the install keeps going". D-27 makes the no-prereq commitment a locked rule.
- **Reconciles with:**
  - **D-13** (RAM-detected Ollama model selection) — D-13 already established that the .pkg owns its own Ollama runtime + selected model. D-27 is the same shape applied to Python: the .pkg ships the runtime, install-time selection happens locally, no customer prerequisite. The Ollama model pull is the ONE network call at install time; D-27 does not add a second (the Python runtime is fully vendored, no download at install).
  - **D-18 Gap 5** — D-18 Gap 5 already vendored the Python wheels and built a venv at install time. D-27 closes the last hole by also vendoring the interpreter the venv is built from. The `postinstall.sh::step_create_venv` flow is otherwise unchanged: same `<payload>/python-wheels/`, same `--no-index --find-links --only-binary=:all:`, same `<payload>/requirements.txt`. The only change at install time is which interpreter `python -m venv` runs against (now packaged, was Homebrew).
  - **D-23** (customer-onboarding UX gaps) — D-23 captured the broader customer-readiness gap; D-27 closes the Python-prerequisite slice of it. Other D-23 rows (Tailscale onboarding, Slack/AMS pre-install validation, support-bundle export) remain forward-looking.
  - **D-26** (halt all Mac mini install attempts until full installer preflight audit completes) — D-26 paused the install-and-watch chain at Round 8 and required a preflight audit (P-025) plus any P0 fixes it surfaces to land before the next install. P-025 merged as `00720ab` and unblocked Round 9; Round 9 then surfaced the Python prerequisite as a new failure beyond what the audit covered (the audit reviewed every postinstall step downstream of `step_provision_catalog_db_and_seed`, and `step_create_venv` was in scope, but the Homebrew-dependency was not flagged as a customer-readiness gap because the failure was masked by the operator's build host having Homebrew). D-27 closes the gap and removes the Homebrew assumption from the install path.
  - **Vision Anchor 2** (Mac Mini IS the product) — appliance shape: customer plugs the Mini in, runs the `.pkg`, walks away. Anything that requires the customer to type `brew install` violates this anchor. D-27 makes the Python piece compliant.
  - **Vision Anchor 6** (local-only, no cloud-only deps) — the python-build-standalone tarball is downloaded ONCE on the build host, vendored offline, and shipped inside the .pkg. Customer install stays offline-equivalent (same one network call as before — Ollama model pull).
- **Implementation status:**
  - Locked 2026-05-05.
  - **2026-05-05 — Fix landed in PR `mg/p026-installer-owned-python-runtime` (P-026, this PR):**
    - `build_pkg.sh::step_4_assemble_payload` adds step 4i (`step_4i_stage_python_runtime` body inline; runs after the bulk runtime rsync, before the wheelhouse rsync).
    - The bulk runtime rsync at step 4c excludes `python-runtime/` so step 4i is the single owner of the python tree.
    - Build hard-fail (`_die 43`) on: missing vendor dir, no python3.12 in either accepted layout, non-Mach-O binary, non-3.12 version, missing `venv` module, post-rsync sanity failure.
    - `step_4b_codesign_inner_binaries` walks `<payload>/runtime/` recursively and signs every Mach-O — the Python tree is automatically covered without a new codesign branch.
    - `postinstall.sh::step_create_venv` resolves packaged-flat then packaged-framework BEFORE Homebrew/PATH fallback; rejects non-3.12 interpreter with a clear error.
    - `postinstall.sh` exit-code header docstring + step_create_venv "Hard rules" block updated for P-026.
    - `docs/RUNBOOK_PKG_REBUILD.md` "Block Pre-B — populate the Python runtime" added with python-build-standalone download + extraction + verification steps, plus the note that Block Pre-A's `pip download` should be re-run with the just-vendored interpreter so wheel ABI tags match exactly.
    - Tests: new `tests/installer/test_postinstall_python_runtime.sh` (29 assertions, all green). `tests/installer/test_postinstall_venv.sh` extended with §9 (P-026 postinstall) + §10 (P-026 build_pkg). All 22 installer suites green against the post-P-026 tree.
- **Tradeoff disclosure:** P-026 is a complete source fix + build guardrail. It does not ship a usable `.pkg` until the operator runs Block Pre-B once on the build host to populate `${HOME}/MiningGuardian-vendor/python-runtime/`. Until that is done, `make pkg` exits 43 at step 4i with a clear pointer to Block Pre-B. Deliberately favors a hard build failure over a notarization round-trip on a half-broken .pkg. The first time `make pkg` runs after P-026 merges, the build either succeeds with Python embedded or hard-fails at build with the runbook command in the error message — no chance of shipping a broken installer.
- **Detection (durable):** Any future code path that resolves Python 3.12 from a Homebrew Cellar, a system PATH, or `command -v python3.12` AS THE PRIMARY PATH (Tier 1) is a regression. Allowed: Homebrew/PATH as a Tier-2 fallback ONLY, gated behind the packaged-runtime probe, logged as `WARN`. `tests/installer/test_postinstall_python_runtime.sh` §3 enforces this ordering by line-number comparison; `test_postinstall_venv.sh` §9 mirrors it as a defensive duplicate. Any future PR that shifts the packaged resolver below the Homebrew fallback will fail both suites.

---
