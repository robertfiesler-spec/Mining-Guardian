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
  - **Gap 1 — Customer-info collection:** Add a customer-info step to the installer. Approach: postinstall reads `/Users/${SUDO_USER}/Desktop/MiningGuardian.conf` if present (operator hands customer a USB or AirDrop with the pre-filled .conf; customer drops on Desktop, double-clicks .pkg). Postinstall validates per B-2 rules and aborts with a Cocoa dialog if missing or invalid. Avoids InstallerPane plugin complexity for v1.0.3; revisited if customer feedback demands GUI form.
  - **Gap 2 — Catalog DB + 320-row seed — SHIPPED (PR mg/v103-gap2-catalog-db-and-seed, 2026-05-04):** Postinstall creates `mining_guardian_catalog` DB in the Colima container, applies the canonical catalog schema bundle (`intelligence-catalog/seed-data/deploy_schema.sql`, which `\ir`-includes v1/v2/v3 + `staging_schema.sql`), and seeds the 320-row Bitcoin SHA-256 baseline (`seed_miner_models.sql`). Implementation: `installer/macos-pkg/scripts/postinstall.sh::step_provision_catalog_db_and_seed`, `installer/macos-pkg/scripts/build_pkg.sh` step 4g (post-assembly assertion that seed files are staged in payload), `tests/installer/test_postinstall_catalog_seed.sh` (24 assertions). Exit code 39 reserved for catalog-provisioning failures; exit code 44 reserved at build time for missing catalog seed in payload. D-20 importer-payload reconciliation (drop `mg_import_tool/***` from the .pkg payload + relocate importer migrations to canonical `migrations/`) shipped in P-004 (PR `mg/v103-d20-importer-payload-reconciliation`, 2026-05-04) — see D-20 implementation status below for details.
  - **Gap 3 — Grafana:** Vendor `grafana.app` and provisioning yaml into the .pkg payload. Postinstall installs to `/Applications/Grafana.app`, drops provisioning into `/usr/local/etc/grafana/provisioning/`, registers as 11th LaunchDaemon (`com.miningguardian.grafana.plist` if not auto-managed by .app), exposes :3000.
  - **Gap 4 — Scheduled tasks via launchd:** Convert the 11 cron entries in setup.sh phase_10 to launchd `StartCalendarInterval` plists. New plist set under `installer/macos-pkg/resources/launchd/scheduled/`. Bootstrap them in postinstall after the 9 service plists.
  - **Gap 5 — Python venv + pip install — SHIPPED (PR mg/v103-gap5-postinstall-venv, 2026-05-04):** Postinstall creates `${MG_INSTALL_ROOT}/venv` and runs `pip install -r requirements.txt` from the vendored payload (no network for pip — vendor wheels in the payload). Implementation: `installer/macos-pkg/scripts/postinstall.sh::step_create_venv`, `installer/macos-pkg/scripts/build_pkg.sh` step 4e+4f, `installer/macos-pkg/payload-requirements.txt`, `tests/installer/test_postinstall_venv.sh`. Exit code 38 reserved for venv failures.
  - **Copy bug 1:** welcome.html "four background services" → "ten background services" (9 + console).
  - **Copy bug 2:** welcome.html + conclusion.html dashboard URL :8080 → correct port (verify against actual dashboard-api binding; likely :8585 per setup.sh phase_07).
  - **Copy bug 3:** conclusion.html `uninstall.sh` reference — either (a) ship a real `bin/uninstall.sh` in payload that does `launchctl bootout` for all services, removes /Library/Application Support/MiningGuardian, removes /Library/LaunchDaemons/com.miningguardian.*.plist, removes /Applications/Mining Guardian, leaves Postgres data dir intact for safety, OR (b) remove the reference. v1.0.3: ship a real uninstall.sh.
  - **Copy bug 4:** conclusion.html "verify these 4 services" code block updated to enumerate all 10 services (9 + console).
  - **Integration bug 1:** `MG_DB_PASSWORD` flow — build_pkg.sh writes `/tmp/mg_install_env_secret` before postinstall runs, OR postinstall generates a random password and writes it to .env. v1.0.3: postinstall generates random password (no out-of-band staging step).
  - **Integration bug 2:** `GUARDIAN_PG_USER` vs `PGUSER` mismatch — postinstall .env writes both keys with the same value to satisfy both code paths until cleanup is complete (fix-forward, document as tech debt).
  - **Integration bug 3:** Tailscale handling — postinstall checks if Tailscale is already up; if yes, no-op; if no, surfaces a Cocoa dialog telling operator to run `tailscale up` separately. Tailscale auth is operator-side, not part of v1.0.2/v1.0.3 .pkg responsibility.
  - **Integration bug 4:** `AMS_*`, `SLACK_*`, `CATALOG_API_KEY`, `INTERNAL_API_SECRET`, `AUTHORIZED_SLACK_USER_IDS`, `AUTO_APPROVE_ENABLED` keys — written to .env by postinstall from the customer's Desktop conf file (Gap 1 closes this).
- **v1.0.3 verification gate (HARD, not skippable):**
  1. Build, sign, notarize, staple v1.0.3 .pkg on operator's laptop.
  2. Smoke-test on a clean macOS 14 VM (UTM/Tart). Required pass criteria:
     - Postgres container up, all 3 DBs created (`mining_guardian`, `mining_guardian_test`, `mining_guardian_catalog`).
     - `SELECT count(*) FROM hardware.miner_models;` against `mining_guardian_catalog` returns 320.
     - Grafana :3000 reachable, returns healthy JSON, AI & Learning dashboard renders.
     - All 10 LaunchDaemons (9 + console) loaded via `launchctl list | grep miningguardian`.
     - All scheduled-task launchd plists registered.
     - `~/Desktop/MiningGuardian.conf` validation passes for valid input, fails-with-Cocoa-dialog for invalid input.
     - Console reachable at `http://127.0.0.1:8686/`, displays task list + automation toggles + approval queue (D-19).
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
- **Implementation status:** Locked 2026-05-03. No code yet.

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
- **Implementation status:** Locked 2026-05-03. No code yet.

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
