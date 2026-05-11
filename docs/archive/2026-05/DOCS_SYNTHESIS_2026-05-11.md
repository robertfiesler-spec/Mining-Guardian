# Documentation Synthesis — 2026-05-11

**Purpose:** Inventory and synthesis of existing Mining Guardian documentation discovered during the 2026-05-11 cutover work. This file answers (or surfaces specific doc references for) the planning questions in FINDINGS_REPORT_2026-05-11.md sections J + K so future sessions don't re-litigate ground that's already been covered.

**Reading order recommended by `docs/VISION.md §9` (the Morning Kickoff Ritual):**
1. `CLAUDE.md` (binding rules) — VPS only at `/root/Mining-Guardian/CLAUDE.md`, also on Mac Mini at `/Library/Application Support/MiningGuardian/CLAUDE.md`
2. `docs/VISION.md` — product vision + Vision Anchors
3. `docs/DECISIONS.md` — locked decisions (D-1 through D-29 as of 2026-05-08)
4. `README.md` — current architecture
5. `AI_ROADMAP.md` — feature status
6. `REPAIR_LOG.md` — live regression log
7. `docs/LATENT_BUGS.md` — known unfixed B-### defects
8. `docs/MG_UNIFIED_TODO_LIST.md` — unified backlog
9. Latest `docs/handoffs/HANDOFF_<YYYY-MM-DD>.md` (D-15 protocol)

The May 10 handoff Bobby gave me at the start of this session is a session-handoff that *summarized* the situation but is **not** in the formal handoffs/ directory and is informed-source, not ground truth (already established earlier today).

---

## A. Full doc inventory (paths)

### Mac Mini install at `/Library/Application Support/MiningGuardian/`

~150 markdown documents across:

- **Top-level operational refs:** `CLAUDE.md`, `README.md`, `AI_ROADMAP.md`, `DEPLOYMENT_CHECKLIST.md`, `NEXT_SESSION.md` (note: a few of these are present on VPS at the repo root but absent from Mac Mini — see VPS list below)
- **`docs/` (live):** `DECISIONS.md` (568 lines, 29 decisions through D-29), `VISION.md`, `MAC_MINI_DEPLOYMENT_RUNBOOK.md`, `ROADMAP_TO_MAC_MINI_2026-05-05.md` (SUPERSEDED), `STATE_OF_THE_SYSTEM_2026-05-02.md`, `PROGRAM_STATE.md`, `MG_UNIFIED_TODO_LIST.md`, `LATENT_BUGS.md`, `CAPABILITIES.md`, `REFINED_INSIGHTS_DESIGN.md`, `FINGERPRINTS_VS_PROFILES.md`, `CONFIDENCE_SCORING.md`, `RELEASE_NOTES_v1.0.0..v1.0.3.md`, `RUNBOOK_PKG_REBUILD.md`, `RUNBOOK_2026-04-28_pkg_build.md`, `RUNBOOK_2026-05-08_pkg_build.md`, `OPERATOR_GUIDE.md`, `OPERATOR_RULES.md`, `CONSOLE_OPERATIONS_GUIDE.md`, `SCANNER_DISCOVERY_SINK.md`, `CRON_SCHEDULE.md`, `CRON_RECONCILIATION.md`, `INSTALL_PATHS_2026-05-02.md` / `_05-03.md`, `INSTALLER_UX_BACKLOG_2026-05-01.md`, `PRE_BUILD_READINESS_v1.0.3_2026-05-04.md`, `PKG_AUDIT_v1.0.2_FINDINGS_2026-05-03.md` (under `docs/audits/`), `CUSTOMER_ONBOARDING_UX_GAPS_2026-05-04.md`, `INTEL_CATALOG_*.md` (several), `INTELLIGENCE_CATALOG_STATUS.md`, `INTELLIGENCE_REPORT_API.md`, `OPEN_LOG_UPLOADER_VISION.md`, `HOW_TO_UPLOAD_LOGS_TO_CLAUDE.md`, `DAILY_LOG_CAPTURE_VISION.md`, `WAREHOUSE_MECHANICAL.md`, `HVAC_SYSTEMS.md`, `HVAC_ARCHITECTURE.md`, `OPERATOR_SCHEDULES.md`, `AMS_INTEGRATION.md`, `AMS_API.md`, `AURADINE_API.md`, `BIXBIT_DIRECT_API.md`, `WHATSMINER_API.md`, `CONTAINER_MONITORING.md`, `CONTAINER_SENSOR_REFERENCE.md`, `LOG_COLLECTION_ARCHITECTURE.md`, `DIRECT_LOG_COLLECTION.md`, `WEB_GUI_OPERATOR_CONSOLE.md`, `FEEDBACK_LOOP_FIXES.md`, `DAILY_DEEP_DIVE_DESIGN.md`, `SECURITY.md`, `TESTING.md`, `TROUBLESHOOTING.md`, `REPAIR.md`, `RUNBOOK_DISTRIBUTION_v1.0.0.md`, `RUNBOOK_HEADLESS_ADDENDUM_2026-04-30.md`, `RUNBOOK_TAILSCALE_REMOTE_ACCESS.md`, plus `BUCKET_*` runbooks for the 2026-04-29 doc sweep
- **`docs/app/`** (the customer-facing app project, post-cutover): `00_README.md` through `07_ROADMAP.md`
- **`docs/handoffs/`:** `HANDOFF_TEMPLATE.md`, README, `HANDOFF_2026-05-02.md`, `_03`, `_04`, `_04_NEW_CHAT.md`, `_04_NIGHT_PAUSE_POSTINSTALL_FAILURE.md`, `_04_PAUSED_BEFORE_MINI_INSTALL.md`, `_04_REBUILDING_AFTER_P015.md`, `_05_INSTALLER_ROUNDS_AND_PREFLIGHT_AUDIT.md`, `_06_DAY_END.md`, `_07.md`, `_07_P022_P023_P024_DAY_LOG.md`, `_08.md` (1289 lines — the most recent canonical handoff), `_08_P030_P032_P029_P031_DAY_LOG.md`
- **`docs/archive/2026-04/`:** session logs `_04-09` through `_04-29`, plus AUDIT_SUMMARY, CORE_DATABASE_AUDIT, DB_STATE snapshots, POSTGRES_MIGRATION_*, REPAIR_LOG, OPENCLAW_AUDIT (also at `docs/archive/`)
- **`intelligence-catalog/`:** `FIELD_INTELLIGENCE_PIPELINE.md` (615 lines — Layer 1-6 pipeline, two-tier resolver, RMA + dormant + pool tables), `LIVING_CATALOG.md`, plus `research/*.md` (catalog research notes)
- **`docs/customer/`:** `README.md` — references three customer-facing PDFs built from `customer_docs/` (Setup Manual, Program Instructions, Brochure)

### VPS repo at `/root/Mining-Guardian/`

Same docs PLUS:

- **`mg_import_tool/README.md` (908 lines)** — THE catalog importer + log archive ingestion tool, operator-only per D-20. Flask app, port 5050, v3.3 with two-tier resolver, RMA, dormant, raw JSON capture. **Not bundled into Mac Mini .pkg per D-20 reconciliation in P-004.**
- **`installer/macos-pkg/README.md`** (156 lines) + `KEYS_AND_SECRETS.md` (101 lines) — installer source for the .pkg
- **`installer/macos-pkg/scripts/`** — preinstall.sh / postinstall.sh + lib/*.sh
- **`installer/macos-pkg/resources/`** — Distribution.xml, plist templates, launchd resources
- **`.claude/`** — Claude Code agent definitions, hooks, rules, skills (this is the operator's Claude Code workspace tooling — `.claude/agents/{architect,code-reviewer,doc-updater,...}.md`, `.claude/commands/*.md`, `.claude/rules/{security,testing,git-workflow,...}.md`, `.claude/skills/{accessibility,security,testing,...}/SKILL.md`)
- **`intelligence/`** — older catalog dir with `DEPRECATED.md` and design notes (intelligence-catalog/ is the live successor)
- **`deploy/openclaw-skills/guardian-db/SKILL.md`** — DB skill reference
- **`logs/warehouse_miners/2026-04-14/README.txt`** — historical warehouse log capture

### Bobby's Mac (NOT on either system I can access)

Per `docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md` and the May 8 build runbook:
- **Build host** at `BigBobby` user / Tailscale `100.103.185.53` — `/Users/BigBobby/Documents/GitHub/Mining-Guardian/build/` is where the .pkg builds land
- **`/Users/BigBobby/Documents/Apple Cert/CREDENTIALS_NOTES.txt`** — Apple Developer notarization secrets (off-repo, off-Mini, local-only per `installer/macos-pkg/KEYS_AND_SECRETS.md`)
- **`customer_docs/`** workspace — source files for the three customer PDFs (NOT in the repo)

---

## B. What each high-signal doc covers (summary)

### `docs/VISION.md` — the canonical product vision
- 7 Vision Anchors (immutable): (1) catalog is sacred, (2) the LLM IS the product, (3) the Mac Mini IS the product, (4) scale-first, (5) federated learning across sites, (6) Bitcoin SHA-256 only, (7) local-first.
- One-paragraph one-Mac-Mini-per-customer-site architecture.
- The 4-phase learning loop (per-scan, per-action, weekly training, monthly federation).
- §4d **Monthly federation across customer sites**: each Mini exports catalog deltas → Bobby merges (optionally Claude+local-LLM refinement) → master pushed back to every site. **USB or manual transfer; no internet required.**

### `docs/DECISIONS.md` — 29 locked decisions
The single most important doc. Most relevant entries for cutover:

- **D-7 (Ollama hosting):** "Ollama runs on the Mac Mini exclusively. Removed from robs-pc."
- **D-8 → D-13 (Ollama model selection):** RAM-tier auto-detect. 16 GB → `llama3.2:3b`, 24 GB+ → `qwen2.5:14b-instruct-q4_K_M`. **D-13 is the live policy; D-8's hard-code is superseded.**
- **D-9 (Mac Mini network):** miner LAN `192.168.188.0/24`, Tailscale for remote ops only, data plane local.
- **D-14 (Operational ↔ Catalog live reference):** Two DBs on Mini in same Postgres 16 container. Live cross-reference, NO scheduled refresh, NOTIFY/LISTEN feedback loop. Catalog read failure is loud, not silent.
- **D-15 (Handoff protocol):** every session ends with `docs/handoffs/HANDOFF_<DATE>.md`; every session starts by reading the latest one. Mantra: "fix proposals without reading the handoff = D-15 violation, halt session."
- **D-16 (Post-cutover masters on ROBS-PC):** ROBS-PC retains catalog masters as backup archive only. Mac Mini does NOT pull anything from ROBS-PC at runtime. After Mini verified green, ROBS-PC's `mining-guardian-db` Docker container shuts down, VPS decommissioned.
- **D-17 (Monthly catalog sync deferred):** Mini ships with the 320-row baseline; monthly sync is a post-cutover work item, not a cutover gate.
- **D-20 (Importer stays with operator forever):** `mg_import_tool/` is operator-only. Customers are read-only catalog consumers. Master → Tailscale push (or USB) → customer Minis. "Single source of truth — one master catalog, one operator, N read-only customer copies."
- **D-22 (Skip clean-VM smoke test for v1.0.3 install):** Mini IS the first clean-target install for v1.0.3 (one-off for Bobby's own customer-#1 install; future customer-grade releases must restore an isolated-target gate per D-23).
- **D-23 (Customer-onboarding UX gaps):** 8 forward-looking gaps captured. NOT v1.0.3 scope. Most relevant: Slack/AMS pre-install validation, support-bundle command, `MG_DRY_RUN=true` default, recovery UI.
- **D-26 (Halt installs until preflight audit):** P-024 + P-025 must merge before next Mini install attempt. Both have merged.
- **D-27 (Python 3.12 is installer-owned):** No Homebrew prerequisite on customer Mac. `.pkg` vendors a relocatable Python 3.12 under `<payload>/runtime/python/`.
- **D-28 (Install paths with spaces are first-class):** every shell-level use of a path-bearing variable must be quoted.
- **D-29 (Installer payload includes baseline `knowledge.json`):** **This is the doc that answers most of the cutover questions.** See section C below.

### `docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md`
- Historical-status header (top of file) explicitly says: "DB approach: The Mac Mini stands up its own operational Postgres DB from migrations 001–005 + the 320-row catalog seed. **There is no live data copy from the VPS** — the VPS is decommissioned for Mining Guardian (Bobby still uses it for his own facility). The optional `restore_from_snapshot.sh` path remains available for any operator who explicitly wants to import a historical operational-DB snapshot from the pre-Mac-Mini era."
- This is locked: **the canonical install does not migrate Postgres data from VPS to Mac Mini.** It builds a clean DB on the Mini. The historical Postgres dump path is preserved for explicit-opt-in only.
- Phase-by-phase install plan (Phases 1-8) + emergency rollback.

### `docs/handoffs/HANDOFF_2026-05-08.md` (most recent canonical handoff)
- Records the full P-029/P-030/P-031/P-032/P-034/P-035/P-036 fix train.
- Records the live install of `MiningGuardian-1.0.3-2b41764a121b.pkg` on the customer Mini, followed by the live discovery of B-45 (the canonical-vs-symlink knowledge.json bug) and the same-day P-036 fix.
- **Notes that the installed Mini tree is NOT git-managed** (`git rev-parse --is-inside-work-tree` returns `not_git`). So fixes are delivered by rebuilding the .pkg, not by `git pull`.
- The "Resume plan — pick up tomorrow morning (one-at-a-time)" section describes the install steps R-1 through R-8 for the post-P-036 `e3461260af2a` package (built 2026-05-08 PM, was waiting to be installed on the Mini the next morning).
- **The May 9 build SHA `53eac9397f00` that we observed on Mac Mini is *post* the `e3461260af2a` build** described in this handoff — so a further build happened on May 9 that we don't have a handoff for (gap).

### `docs/REFINED_INSIGHTS_DESIGN.md` (April 10)
- Original design for `refined_insights` storage in `knowledge.json`.
- **Claude only generates insights** (not Qwen) — daily at R&D Home, monthly at customer sites via master push.
- Storage format with 18 fields per insight (matches Mac Mini exactly; the `_audit` field VPS has is a later addition).
- Update logic: small change (<5%) updates in place; significant change adds new insight noting the change.

### `intelligence-catalog/FIELD_INTELLIGENCE_PIPELINE.md`
- 6-layer pipeline for ingesting miner log archives into Postgres.
- Layer 2 two-tier resolver (12,852 Tier-1 + 1,494 Tier-2 aliases).
- All schemas, RMA tracking, dormant miner detection, learning loops A-D.
- This is the **operator-side** pipeline run by `mg_import_tool/`, NOT the customer-Mini runtime.

### `mg_import_tool/README.md` (VPS only, 908 lines)
- The catalog importer + log archive ingestion tool.
- Flask app, port 5050, loopback-only with login per CRIT-3.
- v3.3 with mass-import hardening (SSE streaming, per-archive error isolation, sha256 dedup).
- This is THE tool Bobby runs on his workstation to maintain the master catalog.
- **NOT bundled into the customer .pkg** (confirmed by D-20 / P-004 — `build_pkg.sh` step 4h asserts no `mg_import*` matches in payload).

### `docs/STATE_OF_THE_SYSTEM_2026-05-02.md`
- One-page snapshot of which host runs what (as of May 2 — pre-Mac-Mini install era).
- Confirms: "Two separate Postgres instances. Not one." (VPS + ROBS-PC, with Mac Mini still empty at that point.)
- Documents which docs to trust as authoritative on the morning of May 2.

### `installer/macos-pkg/README.md` (VPS only)
- Build inputs/scripts/resources for the macOS hybrid .pkg.
- Locked decisions: Q1 (hybrid .pkg, NOT terminal wizard), D-13 (RAM-driven model), cutover scope γ (Mini replaces both VPS and ROBS-PC).
- Apple Developer cert refs (public IDs only); secrets live in `/Users/BigBobby/Documents/Apple Cert/CREDENTIALS_NOTES.txt`.

### `docs/HOW_TO_UPLOAD_LOGS_TO_CLAUDE.md`
- The interactive workflow for getting any miner log file analyzed by Claude. PDF/zip/tar.gz/text/json/csv all supported. Dual-model (Qwen + Claude) analysis.

---

## C. Answers to the FINDINGS_REPORT planning questions

Mapping the Q1–Q12 in `FINDINGS_REPORT_2026-05-11.md` section K to the docs that answer them.

### Q1 — Do we restart VPS Postgres briefly to pg_dump?
**Answered by `docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md` (the historical-status header) and `docs/DECISIONS.md` D-16, D-17.**

The canonical answer is **no** — by design. The Mac Mini stands up its own operational Postgres DB from migrations 001–005 + the 320-row catalog seed. **There is no live data copy from the VPS** in the customer install path. The VPS Postgres history is intentionally not migrated to Mac Mini; the optional `restore_from_snapshot.sh` is preserved only for explicit-opt-in.

This was a locked decision before May 5 and remains locked. The architecture treats the customer Mini as a fresh install with a fresh DB — telemetry accumulates from scan #1 forward on each site. The VPS data is "Bobby's own facility R&D data" and stays on the VPS if he wants to keep using it for his personal facility.

**Implication for the current state:** the Mac Mini's standalone-test telemetry (96 miners, 26 scans, 2,496 rows since May 7) IS the canonical operational data for that site going forward. There is no merge problem because there's no merge.

### Q2 — Treat VPS knowledge.json as canonical and migrate, or merge?
**Answered by D-29.**

The locked behavior:
- **Fresh install:** seed from the .pkg-bundled baseline (`installer/macos-pkg/resources/knowledge/knowledge.json`, SHA-256 prefix `2edea974d711`, 96 profiles / 133 fingerprints / 61 insights).
- **Upgrade:** postinstall **does NOT overwrite** site-specific learned data. The packaged seed is staged alongside under `${MG_INSTALL_ROOT}/knowledge/incoming/knowledge-seed-<version>-<git_sha>.json` for audit only. Site `operator_decisions`, `refined_insights`, `baselines`, `llm_scan_analyses` survive intact.
- **Monthly updates** are operator-staged (Tailscale or USB), merged by `ai/apply_master_update.py` (NOT YET IMPLEMENTED — deferred from v1.0.3).
- **Section-level merge rules are locked in D-29** (already cited above): `operator_decisions`, `baselines`, `operator_rules` are **site-only — master must not include these and the merge must not import them if present.**

**So the answer:** there is no "wholesale migrate VPS knowledge.json to Mac Mini" path. VPS's 56 operator_decisions are Bobby's personal R&D decisions. The Mac Mini will accumulate its own operator_decisions over time. If Bobby wants to copy specific VPS decisions over manually, that's a one-off operator action, not a system-level migration.

**Open question that D-29 does NOT answer:** Bobby's own customer-#1 install — is the VPS data Bobby's pre-cutover R&D operator state that *should* carry over (because Bobby is also customer #1), or is the standalone-test reset deliberate? This is the one place where the operator-as-customer-1 boundary matters.

### Q3 — Mac Mini standalone LLM (qwen3:8b + Anthropic key) or "intelligence elsewhere"?
**Answered by D-7, D-13, Vision Anchor 2, Vision Anchor 7.**

The locked answer: **Mac Mini standalone is the target.** Vision Anchor 3 ("the Mac Mini IS the product") makes this non-negotiable. D-7 explicitly says "Ollama runs on the Mac Mini exclusively. Removed from robs-pc." D-13 chose the 16 GB-tier model (`llama3.2:3b`) intentionally — Claude API is for opt-in weekly training only, not the hot path.

The standalone-test we're observing has Llama 3.2 3B as the canonical D-13-tier choice for the Mac Mini's 16 GB envelope. The qwen3:8b option from Planning Decision 1 isn't in the locked docs — that was a session-level proposal in PLANNING_DECISIONS.md that supersedes the original handoff's qwen2.5:32b but is **not yet reconciled with D-13's `llama3.2:3b` choice**. Bobby should reconcile these two before pulling any model: stay with D-13's `llama3.2:3b`, or formally supersede D-13 with a new locked decision for `qwen3:8b`.

`ANTHROPIC_API_KEY` is expected on customer Minis per Vision Anchor 7 caveat ("opt-in weekly only"). It's missing on Mac Mini because the standalone test deliberately removed it.

### Q4 — What did the 25-hour test prove vs what Bobby wanted to learn?
**No doc — that's a session-context question, not a documented one.**

This is for Bobby to answer when he's back.

### Q5 — knowledge.json structural differences (array vs object, _audit field)
**Partially answered by D-29.**

D-29 explicitly says `miner_profiles, miner_fingerprints: dict keyed`. For `refined_insights` it says "list of dicts with `id`" — which contradicts what we found on Mac Mini (object keyed by string id). For `operator_decisions` D-29 says "site-only" with no explicit type contract.

**On VPS:** `operator_decisions` is an array, `refined_insights` is an object, insights have `_audit`.
**On Mac Mini:** `operator_decisions` is an object keyed by integer strings, `refined_insights` is an object keyed by string IDs, insights don't have `_audit`.

D-29's locked merge rules treat `refined_insights` as "list of dicts with id" with "append-unique by id" semantics. The Mac Mini's object form is a divergence from the locked contract — likely because the scanner (or whatever wrote knowledge.json on Mac Mini since May 7) is using a different schema version. Worth confirming with Bobby — this may be a separate bug (B-46 candidate) or it may be a normalization the Mac Mini's runtime applies that gets denormalized at merge time.

### Q6 — Hardware control creds on VPS (AURADINE/ECLYPSE/PDU/AV2)
**Partially answered by `docs/VISION.md` §6d (Clients).**

`auradine_client.py` is documented as Teraflux AH3880 direct API. `hvac_client.py` is Distech Eclypse BAS, documented as "facility-specific, NOT in deployment templates." `pdu_client.py` is BiXBiT 2U+PDU.

The VPS `.env` having these keys but Mac Mini not having them is consistent with **VPS = Bobby's R&D facility (USA 188)** and **Mac Mini = customer-#1 install for the same facility**. Whether customer Minis at *other* sites need these depends on what hardware those sites have. The HVAC client doc explicitly says it's facility-specific.

So: not a bug. Mac Mini gets hardware creds added at install time per site, or via the customer-info conf file. The current Mac Mini might just not have them populated yet because the standalone test isn't exercising hardware control.

### Q7 — Hardcoded `qwen2.5:32b` fallback at `core/llm_analyzer.py:29` on Mac Mini
**Answered by `docs/handoffs/HANDOFF_2026-05-08.md` and D-29 reconciliation.**

P-031 (PR #165, merged 2026-05-08 as commit `0d8f73d`) drops the qwen2.5:32b fallback. The Mac Mini's build SHA is `53eac9397f00` (May 9), which is *later* than the `2b41764a121b`, `e3461260af2a` builds documented in HANDOFF_2026-05-08. So the May 9 build SHOULD include P-031.

If `core/llm_analyzer.py:29` on Mac Mini still has the hardcoded fallback, one of two things:
- P-031 didn't reach that specific code site (P-031 may have only fixed `ai/local_llm_analyzer.py`, not `core/llm_analyzer.py`).
- The May 9 build SHA `53eac9397f00` predates `e346126` (where PR #165 lives).

We need to check the git ancestry between `53eac9` and `0d8f73d`. Likely answer: P-031 fixed the analyzer surface paths but `core/llm_analyzer.py:29`'s comment line about "never-pulled qwen2.5:32b" was preserved as a doc comment, and the literal string in the line we grep'd is in the comment, not in an `os.getenv` fallback. **Worth verifying tomorrow.**

### Q8 — Mac Mini scanner running as root
**Indirectly answered by P-022 and the SCANNER_DISCOVERY_SINK design.**

The scanner is part of `core/mining_guardian.py`, which the May 8 runbook describes as a LaunchDaemon (`com.miningguardian.scanner.plist`). LaunchDaemons in `/Library/LaunchDaemons/` run as root by default unless the plist specifies `UserName`.

P-032 (PR #163, merged 2026-05-08) specifically locked the discovery sink mode at 0664 and added an atomic-write invariant. The post-install verification command in HANDOFF_2026-05-08 step R-7c expects `stat -f '%Lp %N' .../latest_findings.json` → `664`.

If the scanner is running as root and writing events-YYYY-MM-DD.jsonl as root-owned 0644 (which is what we observed), that's drift from the P-032 invariant. **Not necessarily a B-46 — possibly the plist was set to run as root deliberately for AMS-LAN port access — but worth confirming the plist's `UserName` field.**

### Q9 — `catalog_import` exit 126
**Indirectly answered by what we already found.**

The cron_tracking ownership drift (root-owned `events-2026-05-10.jsonl`, `events-2026-05-11.jsonl`) is consistent with Q8 — scanner-as-root creates files as root. `catalog_import` shell script line 86 probably does a redirect or write that fails because the script runs as a different user (or its parent dir was created with restrictive perms by the root-owned scanner). The plist's `UserName` field is the diagnostic.

### Q10 — VPS-path hardcodes (`/root/Mining-Guardian/...`)
**No specific doc — but `docs/MG_UNIFIED_TODO_LIST.md` likely tracks the broader "is this customer-ready" effort.**

I didn't read MG_UNIFIED_TODO_LIST.md in this pass. The scope of VPS-path hardcodes can be enumerated with:
```bash
ssh root@vps "grep -rn '/root/Mining-Guardian' /root/Mining-Guardian/ --include='*.py' --include='*.sh' | grep -v 'docs/'"
```
**This is a code-grep task, not a doc-read task.** Doc-side it's likely covered as a UTODO row.

### Q11 — Crontab credential leak (Mac Mini equivalent?)
**Answered by `installer/macos-pkg/KEYS_AND_SECRETS.md`.**

The Mac Mini installer is explicit: secrets go in `.env` mode 0600, never in launchd plist `EnvironmentVariables` (the runbook says "Write it to a launchd `EnvironmentVariables` plist that has `0600` permissions" — but that's for the `MG_DB_PASSWORD` specifically, and the broader rule is to keep secrets out of plain-text inspection surfaces). The crontab leak we found is **VPS-only legacy** — Mac Mini's launchd plists shouldn't have credentials inline. **Worth verifying by reading one of the actual plists on Mac Mini.**

### Q12 — ROBS-PC Qwen unreachability
**Answered by D-7 + D-16.**

ROBS-PC's Qwen role is retired post-cutover (D-7). ROBS-PC stays as catalog master archive (D-16) but is NOT in the data plane. The fact that the VPS's `refinement_chain` cron still tries `http://100.110.87.1:11434` is **VPS legacy** — not a Mac Mini concern. The Mac Mini runs Ollama locally per D-7/D-9/D-13.

---

## D. Gaps — what the docs do NOT cover

These are places where the docs we've read don't have the answer, or where the doc is silent on a current state.

### D1. The May 9 build SHA `53eac9397f00`
HANDOFF_2026-05-08 documents `e3461260af2a` as the last package built that day (PM pause). Mac Mini's `BUILD_STAMP.json` shows git_sha `53eac9397f00` stamped 2026-05-09T14:32:02Z — which is AFTER the `e346126` merge timestamp. **There is no handoff or runbook in `docs/handoffs/` for the May 9 build.** Either:
- A handoff exists in the working tree that wasn't merged.
- The May 9 build was an emergency / quick rebuild without a formal handoff.
- The build SHA in the stamp file came from a different branch.

Worth surfacing with Bobby. The "Resume plan" in HANDOFF_2026-05-08 was for installing `e3461260af2a` on May 9 morning, so the install must have happened — but we don't have a runbook for the install itself.

### D2. `ai/apply_master_update.py` is unimplemented
D-29 locks the merge contract but explicitly defers the implementation. **There is no script on either Mac Mini or VPS that performs the monthly merge.** This means the federated update path is not yet operational, only specified.

### D3. The "knowledge.json structural divergence" between VPS array form and Mac Mini object form
D-29 specifies `refined_insights` as "list of dicts with id" but Mac Mini stores it as an object. No doc explains the divergence. Either:
- A schema version mismatch (Mac Mini may be writing schema v2 while D-29 contract is v1).
- A runtime denormalization that's invisible to D-29.
- An actual bug (B-46 candidate).

### D4. Whether the standalone test is intentional or accidental
We learned from session context that it's intentional. Not documented in `docs/handoffs/` — likely too recent. Tomorrow's handoff is the canonical place for it.

### D5. Confirmation on which build the Mac Mini is actually running vs. should be running
`BUILD_STAMP.json` says `53eac9397f00`. The newest documented .pkg in HANDOFF_2026-05-08 is `e3461260af2a`. We need git log between them to see if there's a P-### we haven't accounted for.

### D6. What `OPEN_QUESTIONS.md` was supposed to be (Bobby's earlier mention)
Bobby's earlier message referenced an `OPEN_QUESTIONS.md` that doesn't exist. The docs above suggest the operator's actual workflow is to land questions as "Open work" / "Things I currently believe that need re-verification" sections in the daily handoff template (per D-15 mandatory sections). So the absence of `OPEN_QUESTIONS.md` isn't a doc gap — it's that questions live in handoffs.

### D7. Customer-grade vs operator-grade
D-22 + D-23 acknowledge that the v1.0.3 install on Bobby's own Mac Mini is one-off "first clean-target install" treatment, and that customer-grade UX work is forward-looking. **The Mac Mini we're working on IS Bobby's customer-#1 install, NOT a generic customer install.** That affects expectations: the standalone-test behavior, manual MiningGuardian.conf editing, hardware-control creds at the operator's discretion — all consistent with operator-grade.

---

## E. Implications for the current cutover work

1. **Stop calling it a "VPS-to-Mac-Mini migration."** Per the locked docs it's a fresh install on the Mini with operator-time-boxed cleanup of the historical VPS data Bobby wants to keep for his R&D facility.

2. **Don't try to migrate Postgres data.** Per MAC_MINI_DEPLOYMENT_RUNBOOK, the canonical install builds a fresh DB. The optional snapshot-restore is the explicit-opt-in path, and Bobby hasn't asked for it.

3. **Don't try to migrate `operator_decisions` from VPS to Mac Mini.** D-29 explicitly forbids that for the merge path. If Bobby wants specific decisions copied, that's an operator-side manual action.

4. **The qwen3:8b vs llama3.2:3b decision needs explicit reconciliation.** PLANNING_DECISIONS.md proposes qwen3:8b; D-13 specifies llama3.2:3b for 16 GB. Bobby should either (a) supersede D-13 with a new locked decision and update the runbook, or (b) keep llama3.2:3b and rip qwen3:8b out of the planning decisions.

5. **The denial-overwrite bug fix is still real and still pre-Anthropic-key-add.** That part of the plan stays.

6. **The .env diff and the qwen2.5:32b code reference are still real findings** but reframed: the .env diff shows hardware-creds-not-yet-installed (operator action, not migration); the qwen2.5:32b reference needs to be looked at as code, not as a setting (Q7 above).

7. **The May 9 build SHA gap (D1 in Gaps) is the most actionable thing for tomorrow** — find or write the missing handoff.

---

*This synthesis lives at `~/mining-guardian-cutover/DOCS_SYNTHESIS_2026-05-11.md` and complements FINDINGS_REPORT_2026-05-11.md. Read both at session start.*
