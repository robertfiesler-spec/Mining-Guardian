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

*Append new decisions below this line. Do not edit history.*
