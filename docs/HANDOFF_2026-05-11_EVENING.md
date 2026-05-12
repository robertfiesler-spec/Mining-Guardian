# HANDOFF — 2026-05-11 (Monday evening)

> **For the next Claude session.** Drop this file (or paste its contents) into the first message of the new chat. Then attach the four strategic-planning `.docx` files referenced in §6. This single document should bring a fresh session fully up to speed in under five minutes.

---

## 0. The TL;DR for tomorrow

1. **Today was huge.** 7 PRs merged (P-038 cohort closed + P-039 scanner recurrence), full delivery to the Mac Mini, `.env` wired up with Anthropic key, Grafana 13.0.1 stood up via Homebrew with 3 dashboards loading.
2. **Four strategic-planning docs were dropped into context tonight.** They lay out 22 work items (W01–W22) across 6 phases, B+ → A+ over ~6 months. **Most of tomorrow's session is the reconciliation pass** — figure out what today's work already covered vs. what the plan thinks is still open — and then begin Phase 1.5.
3. **One decision already made:** W14 (two-Postgres-instance split) moves from Phase 4 (Weeks 5-6) to **Phase 1.5**, before any Phase 2 work. Rationale in §4.2.
4. **One open security item:** the May 11 Anthropic API key was pasted in the prior chat transcript. Bobby has agreed to rotate later. Do not paste the new value in chat once rotated.
5. **One open Grafana item:** 3 dashboards load, but panels show "No data" — query 400 from Postgres-side. Bobby's verdict: tabled, "we are going to add the others later."

---

## 1. Operator / project context (carry-over)

- **Operator:** Bobby Fiesler (BigBobby), CTO BiXBiT USA, Fort Worth TX. Slack `U07AGTT8CLD`.
- **Project:** Mining Guardian — AI-powered Bitcoin mining fleet monitor, 58 liquid-cooled miners, BiXBiT USA.
- **Repo:** `robertfiesler-spec/Mining-Guardian`. Local: `/Users/BigBobby/Documents/GitHub/Mining-Guardian/`.
- **Mac Mini:** `miningguardian@100.69.66.32` over Tailscale, M4 16GB, macOS 26.4.1, hostname `miningguardian.local`.
- **Install root on Mini:** `/Library/Application Support/MiningGuardian/` — NOT git-managed; manual sync from laptop.
- **Mini's repo checkout:** `/Users/miningguardian/code/Mining-Guardian/` — currently at commit `084dcba`, missing all 7 of today's PRs. Used only by `install_grafana_provisioning.sh`. Pull at convenience.
- **Test venv (on laptop):** `/Users/BigBobby/Documents/GitHub/Mining-Guardian/.venv-p018-tests/bin/python`.
- **Postgres on Mini:** Docker container `mining-guardian-db`, user `mg`, DB `mining_guardian` (52 MB, ~36 scan rows as of evening). Schema `mg.*`. Search_path `"$user", public` resolves bare `scans` → `mg.scans` automatically.

### Operating conventions in force
- **Failure Mode 9** — sibling sweeps OK in one PR (same bug class across N files); mixed bug classes never bundled.
- **Live-Mini evidence required before fix; live-Mini smoke required before commit.**
- **Cohort guard tests** catch unsurfaced siblings of a bug class.
- The Mini install tree is **not** git-managed. Delivery options today are: manual scp (used) OR future .pkg rebuild.

---

## 2. What got done today

### 2.1 Seven PRs merged to `main`

| PR | Title | Cohort | Verified live on Mini |
|---|---|---|---|
| **#175** | P-039 scanner recurrence (`--loop` + `StartInterval=3600`) | P-039 | ✅ scanner process running with `--loop`, internal interval=300s |
| **#177** | P-038 #7 — `ams_cleanup` hardcoded path (`_resolve_config_path()`) | P-038 | ✅ helper present, no legacy paths |
| **#178** | P-038 #2+#3+bonus — timestamptz vs text SQL (3 files, 18 substitutions) | P-038 | ✅ 0 buggy patterns across 3 files |
| **#179** | P-038 #1 — `catalog_import` heredoc | P-038 | ✅ exit 0; 13 unique events reported |
| **#180** | P-038 #5 datetime — new `core/dt_format.py` + `fmt_dt` helper across 5 files | P-038 | ✅ 0 buggy slices; helper imported |
| **#181** | P-038 #4+#5 env-gate — new `core/anthropic_gate.py` + `require_anthropic_or_exit(job, logger)` | P-038 | ✅ gate opens with the key set |
| **#182** | P-038 #6 — `db_maintenance` macOS-portable (Docker exec, drop `set -e`, drop `/var/log/`) | P-038 | ✅ exit 0 against live DB |

**P-038 cohort: 7 of 7 + 1 bonus → COMPLETE. Umbrella B-47 closes.**

### 2.2 Phase-1 delivery to Mini (14 source files scp'd, no sudo)

All byte-for-byte matched against laptop. Pre-sync backup at Mini `/tmp/mg-pre-sync-backup/` (11 modified files; 3 new files have no backup since they didn't previously exist).

Files synced:
- `core/anthropic_gate.py` (NEW, 7809 B)
- `core/dt_format.py` (NEW, 3458 B)
- `scripts/cleanup_ams_logs.py`
- `scripts/daily_log_failure_report.py`
- `scripts/db_maintenance.sh`
- `scripts/verify_training_data.py`
- `ai/daily_deep_dive.py`
- `ai/knowledge_manager.py`
- `ai/local_llm_analyzer.py`
- `ai/refinement_chain.py`
- `ai/train_comprehensive.py`
- `ai/train_llm.py`
- `ai/weekly_train.py`
- `intelligence-catalog/tools/run_daily_catalog_import.sh`

Smokes that passed live: `db_maintenance` exit 0 against live DB; `ams_cleanup _resolve_config_path` present; 3 timestamptz/text fixes verified zero buggy patterns; 5 datetime-slicing files import `fmt_dt` with zero buggy slices; env-gate skip-path emits expected INFO and exits 0; `catalog_import` succeeds reporting 13 unique events.

### 2.3 Phase-2: P-039 LaunchDaemon reload (Bobby did the sudo)

Bobby ran 4 commands successfully:
- Backed up old plist to `.pre-p039-backup`
- Installed new `/Library/LaunchDaemons/com.miningguardian.scanner.plist` (5518 B)
- Installed new `/Library/Application Support/MiningGuardian/bin/scanner_launcher.sh` (2721 B)
- `launchctl bootout` + `bootstrap` → scanner running with `--loop`, internal `interval=300s` (5 min), `state=running` confirmed via `launchctl print`.

### 2.4 Phase-3: `.env` updated for Anthropic flag-gating

Bobby created a new Anthropic API key named "mini" in the default workspace, then nano'd the `.env` on the Mini to add 3 lines at the bottom:

```
# P-038 #4+#5 env-gate (added 2026-05-11) — enables Anthropic-dependent jobs
MG_ANTHROPIC_LINKED=1
ANTHROPIC_API_KEY=sk-ant-api03-…  (108 chars total, key value redacted)
```

End-to-end gate smoke confirmed: `require_anthropic_or_exit("final_smoke", log)` returned the 108-char key cleanly. **Outcome: weekly_training and refinement_chain will fire Anthropic calls on their next scheduled runs.**

### 2.5 Grafana 13.0.1 stand-up via Homebrew (NEW today)

Goal: replace the retired tunnel-to-personal-domain access path. Tailscale + local-only. iPhone app in a few weeks will use the same URL.

What's working:
- ✅ Homebrew installed at `/opt/homebrew/` (Bobby ran the official installer interactively; ~30s download on Apple Silicon)
- ✅ `brew install grafana` → 13.0.1 (972 MB, 12,623 files)
- ✅ `brew services start grafana` — LaunchAgent set up, auto-starts on Mini reboot
- ✅ Reachable at `http://100.69.66.32:3000` over Tailscale (confirmed by Bobby's browser screenshot at 16:15 CDT)
- ✅ 2 Postgres datasources provisioned (`mg_operational_pg` + `mg_catalog_pg`) — both visible in Grafana's `/api/datasources`
- ✅ 3 dashboards loaded under "Mining Guardian" folder: Fleet Overview, Scans Health, Miner Models Catalog
- ✅ Bobby logged in via browser, set an admin password manually

What's NOT working (tabled by Bobby):
- 🟡 All dashboard panels show "No data" (green text, not red errors). Grafana log shows one `/api/ds/query → status=400 status_source=downstream` at 16:05:39 (Postgres-side error). Cause: likely SQL syntax mismatch between Postgres 16 and the May-era dashboard queries — not fully diagnosed. Direct Postgres query `SELECT online FROM scans ORDER BY scanned_at DESC LIMIT 1` returns `85` cleanly.
- Bobby's call: tabled. "You win some you lose some and we are going to add the others later." The 3 in the repo bundle aren't the dashboards he actually wants. He wants the 6 older April-era branded dashboards (Main, Fleet Overview, Per Miner, Board Health, AI & Learning, Pool Stats from `archive/tmp_scripts_apr08/grafana_brand_dashboards.py`) — those would need to be rebuilt or recovered from VPS backups.

### 2.6 Bugs surfaced during Grafana stand-up (NOT YET FIXED IN REPO)

Both got patched on-Mini-only with on-disk `sed` and `.bak` backups. Source repo bundle at `installer/macos-pkg/resources/grafana/` still has the bugs.

**Bug A — dashboard provider yaml has wrong path.**
- File: `installer/macos-pkg/resources/grafana/provisioning/dashboards/mining_guardian.yml`
- Has: `path: /usr/local/MiningGuardian/grafana/dashboards`
- Should be: `path: /Library/Application Support/MiningGuardian/grafana/dashboards`
- README in same directory correctly documents the right path; the yaml itself was never updated.

**Bug B — datasource yaml has wrong Postgres user.**
- File: `installer/macos-pkg/resources/grafana/provisioning/datasources/mining_guardian.yml`
- Has: `user: guardian_app`
- Should be: `user: mg` (the actual `.env` `GUARDIAN_PG_USER=mg`)

**Bug C (not really a bug, more a deployment concern) — `brew services` regenerates the LaunchAgent plist on every start, wiping `EnvironmentVariables`.**
- Means `${GUARDIAN_PG_PASSWORD}` env-substitution in the datasource yaml doesn't work without inlining the password in the yaml itself.
- Worked around tonight by replacing `${GUARDIAN_PG_PASSWORD}` with the literal 64-char password in the deployed yaml at `/opt/homebrew/var/lib/grafana/provisioning/datasources/mining_guardian.yml` (mode 0644, owned `miningguardian:admin`).
- For proper secret management before customer ship, needs a wrapper-script approach (env shim) or Grafana's own secret-management features.

**Bug D — `grafana.ini` default provisioning path was wrong.**
- File: `/opt/homebrew/etc/grafana/grafana.ini` on the Mini
- Was: commented-out `;provisioning = conf/provisioning` (resolves relative to `--homepath` = `/opt/homebrew/opt/grafana/share/grafana/conf/provisioning`)
- Patched to: `provisioning = /opt/homebrew/var/lib/grafana/provisioning`
- This edit persists (unlike plist edits which get clobbered). Backup at `grafana.ini.bak`. Source for `brew install grafana`'s shipped config — needs documenting in repo for future installs.

---

## 3. The four strategic-planning docs that arrived tonight

Bobby uploaded 4 `.docx` files to the chat — they were prepared May 9 by an outside reader (likely a previous Claude session) ahead of the May 10 cutover. They live on Claude's compute side at `/mnt/user-data/uploads/` and are **NOT in the repo** as of this handoff. (Recommendation in §5: commit copies to `docs/strategy/` tomorrow.)

| # | Title | Length | Role |
|---|---|---|---|
| 1 | Mining Guardian — Performance & Capability Audit | 218 lines | "What's wrong" — 3 tiers of findings |
| 2 | Mining Guardian — Two-Database Deep Dive | 307 lines | Deeper integration-gap analysis; 60% write-only catalog; Perplexity gap |
| 3 | Mining Guardian — Overall Assessment & Potential | 360 lines | Honest grade: B+ today, A+ ceiling in 6 months. Defends the plan |
| 4 | **Mining Guardian — Master Execution Plan** | **965 lines** | **The action document: W01–W22 in 6 phases, dependency-ordered** |

The Master Execution Plan is the operational artifact. The other three exist to make the plan defensible. **All four files need to be attached to the next chat for the new Claude to read them.**

### 3.1 The 22 W-items in original sequence

| Phase | Items | Original timeframe | Goal |
|---|---|---|---|
| 1 — Foundation | W01–W05 | Week 1 | Fast, observable, stable on Mac Mini |
| 2 — Closing the integration gap | W06–W09 | Weeks 2–3 | Closed learning loop fully wired |
| 3 — External intake & operator surfaces | W10–W13 | Week 4 | Perplexity flows through Slack `/intel` |
| 4 — Architectural correctness | W14–W17 | Weeks 5–6 | Two-Postgres-instance split; clean up shortcuts |
| 5 — Performance polish | W18–W22 | Weeks 7–8 | A-grade single-site |
| 6 — Federation | separate plan | Months 3–6 | A+ multi-site |

Specific items:
- **W01** — verify cutover (`pmset sleep`, 9 launchd services, backups)
- **W02** — `pg_stat_statements` for query observability
- **W03** — `psycopg2.pool.ThreadedConnectionPool` in `GuardianPGDB` (highest single-item win)
- **W04** — Postgres tuning for 16GB shared host
- **W05** — `ProcessType: Background` → `Standard` on always-on services
- **W06** — catalog read for `hardware.model_known_issues`
- **W07** — catalog read for `market.war_stories`
- **W08** — catalog read for `ops.environmental_correlations`
- **W09** — Pass 2 weekly training reads the catalog
- **W10** — extend `dual_writer` with `propose_firmware_release`, `propose_firmware_compatibility`, `propose_data_conflict`, `record_freshness_check`
- **W11** — Slack `/intel` command and intake API (Perplexity ingest)
- **W12** — morning briefing catalog visibility
- **W13** — watchdog-of-the-watchdog service
- **W14** — split Postgres into two separate instances
- **W15** — split `daily_deep_analyses` out of `knowledge.json`
- **W16** — stop casting timestamps through `TO_CHAR`
- **W17** — `datetime.now()` → `datetime.now(timezone.utc)` everywhere
- **W18** — pipeline DB I/O against LLM compute in daily deep dive
- **W19** — AMS WebSocket persistent connection
- **W20** — autovacuum tuning for high-churn tables
- **W21** — range-partition the timeseries tables
- **W22** — extend `raw_ingestion_log` partitions past 2027-Q1

---

## 4. Reconciliation: what today's work changes about the plan

This is the most important section for the next Claude. The plan was written May 9 — it does not know about today's 7 PRs.

### 4.1 W-items today already moved the needle on

| W-item | Plan status | Actual status as of 2026-05-11 evening | Evidence |
|---|---|---|---|
| **W01** (cutover verification) | Not done | **Substantially complete.** 9 launchd services confirmed loaded; PIDs all numeric; scanner running with new `--loop` recurrence; live DB reachable; `.env` wired. **Pending: `pmset sleep 0 disksleep 0`** (Bobby needs to run); **pending: confirm backup destination decision.** | Today's PR #175 delivery + smokes |
| **W05** (ProcessType) | Not done | **NOT done.** All 6 always-on plists still `<string>Background</string>` in repo (`installer/macos-pkg/resources/launchd/com.miningguardian.{scanner,alerts,approval-api,dashboard-api,slack-listener,slack-commands}.plist`). 1-line edit each, plus bootout/bootstrap cycle. | Verified via grep tonight |
| **W16** (TO_CHAR cleanup) | Not done | **COMPLETE in real source paths.** Zero `TO_CHAR(NOW(` in `ai/`, `core/`, `api/`, `scripts/`. Hits in `tests/test_p038_timestamptz_vs_text_sql_casts.py` are intentional regression-test pattern strings. Hits in `build/stage/payload/` are an old build artifact. | PR #178 closed it |
| **W17** (datetime.now() → tz-aware) | Not done | **NOT done.** 151 occurrences of `datetime.now()` (without timezone arg) across `core/ai/api/scripts/`. PR #180 was a different fix (`fmt_dt` datetime *slicing* / formatting), NOT the `datetime.now()` → `datetime.now(timezone.utc)` conversion. | Verified via grep tonight |

**Earlier in tonight's chat I said "W16 is 50–70% done and W17 is 20–30% done." That was wrong.** The reality is W16 is fully done in source paths, and W17 is essentially untouched. Future Claude should NOT trust the chat assertions there — trust the grep results above.

### 4.2 The W14 re-sequencing decision

**Bobby and I agreed tonight to move W14 (two-Postgres-instance split) from Phase 4 to a new Phase 1.5, before any Phase 2 work.**

Bobby's reasoning (his words paraphrased): "I agree with the moving of the split DBs — actually that is something I wanted to do first, so as we work on the rest, everything we do is tied into the way it was supposed to be. It was always supposed to be 2 but somehow did not do it."

Specific reasons doing W14 later costs more than doing it earlier:

1. **W11 (Slack `/intel`) writes to `staging.miner_model_proposals` and 3 other catalog tables.** Built before the split, it points at `127.0.0.1:5432`. After the split, every call needs reconfiguration to port 5433, and every operator review action that lands during the in-between window has to be reconciled.
2. **W06–W08 (catalog reads in `_fetch_miner_knowledge_pg`)** add catalog queries. These go through `core/db_targets.py::catalog_target()`. If the catalog is on the same instance today, those queries share the operational instance's connection pool (which will be W03 by then). After the split, they need their own pool against port 5433.
3. **The plan's W14 effort estimate (L, ~1 week) is likely light.** Realistic budget: 2 weeks with a maintenance window planned around minute one. `brew install postgresql@16` only creates ONE instance — running two means manual data-dir setup, separate launchd plist, separate `postgresql.conf`, two `pg_stat_statements`, two passwords, two ports, separate backup scripts, full re-test of all 9 scheduled jobs.

### 4.3 Revised plan structure

| Revised Phase | Items | Note |
|---|---|---|
| **Phase 1 — Foundation** | W01–W05 | Mostly small / one ProcessType item still pending |
| **Phase 1.5 — Architectural restoration** | **W14** | **MOVED HERE FROM PHASE 4** |
| **Phase 2 — Closing the integration gap** | W06–W09 | Now writes against correct two-instance topology |
| **Phase 3 — External intake & operator surfaces** | W10–W13 | `/intel` writes to the right place |
| **Phase 4 — Architectural correctness** | W15–W17 | W14 removed; W15/W16(done)/W17 still here |
| **Phase 5 — Performance polish** | W18–W22 | Unchanged |

W-numbering stays stable. W14 keeps its number even though its position moves.

### 4.4 New W-items the plan doesn't have (from tonight's Grafana work)

The plan treats Grafana as out of scope. But two real bugs and one operational concern emerged tonight that deserve W-numbers:

- **W23 (new)** — fix the 2 bundle bugs in `installer/macos-pkg/resources/grafana/`:
  - dashboard provider yaml path `/usr/local/MiningGuardian/...` → `/Library/Application Support/MiningGuardian/...`
  - datasource yaml `user: guardian_app` → `user: mg`
  - Small surgical PR. **XS effort, Low risk.**
- **W24 (new)** — Grafana password secret management. Currently password is inlined in deployed yaml. For ship-readiness, needs proper handling (env shim wrapper, or Grafana's own secret store, or runtime-write of the yaml at service start from `.env`).
  - **S effort, Medium risk.**
- **W25 (new)** — Grafana panel "No data" debug or rebuild. Either fix the 3 May-era dashboards' queries against live Postgres 16 schema, OR rebuild Bobby's preferred 6 April dashboards from `archive/tmp_scripts_apr08/grafana_brand_dashboards.py`.
  - **M effort, Low risk. Bobby's call which path.**

These should fit somewhere in Phase 5 or later. The plan currently has zero operator-facing-dashboard items, which is a defensible choice but explicit.

---

## 5. What to do tomorrow, concretely (in order)

1. **Read this handoff.** Then read the Master Execution Plan (attached `.docx`).
2. **Verify the reconciliation.** Re-grep `main` for `TO_CHAR(NOW(` in `ai/ core/ api/ scripts/` (should be 0), and for `datetime\.now()` (should be ~151). Confirm `installer/macos-pkg/resources/launchd/com.miningguardian.{scanner,alerts,approval-api,dashboard-api,slack-listener,slack-commands}.plist` all still show `<string>Background</string>`.
3. **Commit the 4 strategic docs to the repo.** Create `docs/strategy/` directory; copy the 4 `.docx` files in. This makes them permanently retrievable to future sessions without re-uploading. Suggested commit: `docs(strategy): add B+ → A+ planning suite (May 9 audit + plan)`.
4. **Create `docs/EXECUTION_PLAN_STATUS.md`.** Page 4 of the Master Execution Plan describes the format:
   ```
   W01  Verify cutover succeeded            [~]  2026-05-11  partial (pmset pending)
   W05  ProcessType for always-on services  [ ]  --          not started
   W14  Split Postgres into two instances   [ ]  --          MOVED TO PHASE 1.5 (per 2026-05-11 decision)
   W16  Stop casting timestamps via TO_CHAR [X]  2026-05-11  PR #178
   W17  Time zone discipline cleanup        [ ]  --          ~151 datetime.now() remain
   ```
   First line of the file should reference this handoff and the 4 strategic docs. **This becomes the single source of truth on plan progress from tomorrow forward.**
5. **Then decide Phase 1.5 entry.** W14 is the next real work item. Per §4.2, expect a 2-week effort with a maintenance window. **Don't start work on W06–W13 before W14 is done.** W05 (ProcessType, 1 hour) and the `pmset sleep 0` (5 minutes) parts of W01 are fine to knock out alongside W14 prep — they're independent and low-risk.

### 5.1 If you have only 30 minutes tomorrow

- Cut PR for W05 (ProcessType: Background → Standard on the 6 always-on plists). One file at a time, scp to Mini, `launchctl bootout`/`bootstrap` per plist. **This is the only XS work item left in Phase 1.**

### 5.2 If you have 2+ hours

- Steps 1–4 above (reconciliation + docs commit + status file). That sets you up for W14 next session with no ambiguity.

---

## 6. Open items, parked / to-do

### 6.1 Security
- **🔐 Rotate the Anthropic API key.** The May 11 "mini" key was pasted in the prior chat (`sk-ant-api03-CFvQ5RI_…`). Bobby agreed to rotate later. Steps:
  1. https://console.anthropic.com/settings/keys → delete the existing "mini" key
  2. Create a new key, also named "mini"
  3. SSH to Mini → `nano "/Library/Application Support/MiningGuardian/.env"` → replace value on the `ANTHROPIC_API_KEY=` line. Don't paste the new key into chat.

### 6.2 Grafana
- **W23/W24/W25 (see §4.4)** are the consolidated Grafana follow-ups.
- Grafana admin password: Bobby set it manually in the browser. Not known to Claude. A CLI password reset to `mining-debug-2026` was attempted but didn't take effect after `brew services restart`. If Claude needs API access tomorrow, ask Bobby to reset via the browser Profile → Change Password and share temporarily (or just operate via the browser).

### 6.3 Mini repo checkout
- `~miningguardian/code/Mining-Guardian/` is at `084dcba`, missing today's 7 PRs. If anyone re-runs `install_grafana_provisioning.sh` from there, they'd be running the stale bundle. `git pull` whenever convenient.

### 6.4 PyYAML on Mini
- During Grafana stand-up, the install script's yaml validation failed because system Python 3.9 didn't have PyYAML. Installed via `pip3 install --user pyyaml` (PyYAML 6.0.3). This worked but lives in the user site-packages — if the Mini ever needs to rebuild Python or if a different script needs yaml, it may surface again. Not blocking.

### 6.5 Customer-facing installer UI (P-040)
- Deferred work, ~half day, blocked on first-customer-ship timing (≥1 month out per the 2026-05-11 operator decisions).

### 6.6 Future .pkg rebuild
- Bundles today's 7 PRs + Grafana provisioning + Homebrew setup steps. Needs Apple notarization. Not urgent for Bobby's PoC Mini (manually synced). Critical before first customer ship.

---

## 7. What you'll see in production tomorrow

- 🕗 **8 AM CDT** — daily log pull (unaffected by today's work, continues normal)
- 🕔 **5 PM CDT** — `daily_deep_dive` runs (now fixed: won't crash on timestamptz, AND will hit Claude via the env-gate)
- 🌙 **3:30 AM CDT overnight** — `db_maintenance` exits 0 with full report (was exit 1 daily before today)
- 🌙 **Sunday 5 AM UTC** — `weekly_training` runs to completion firing Claude per cohort
- 🌐 **Anytime** — `http://100.69.66.32:3000` from your laptop on Tailscale → Grafana UI loads, dashboards render, panels say "No data" until W25

---

## 8. Memory notes added today (for the new chat)

Two memory edits have been added to Claude's persistent memory so a fresh chat doesn't have to re-establish them:

1. **Master Execution Plan exists with W01–W22 across 6 phases. W14 (two-Postgres split) was moved to Phase 1.5 per 2026-05-11 decision. Reference docs in `docs/strategy/` (after the next chat commits them).**
2. **Today's PR cohort (P-038 #175–#182) closed the W16 source-code work. W17 (datetime.now → timezone.utc) is essentially untouched.**

(See §9 for the full list.)

---

## 9. How to open the next chat

Suggested opening message for tomorrow:

> *Continuing from 2026-05-11 evening. The handoff is at `docs/HANDOFF_2026-05-11_EVENING.md`. The 4 strategic-planning docs are attached (or in `docs/strategy/` if committed). Goal of this session: do the reconciliation pass per §5 of the handoff — commit the strategic docs to the repo, create `docs/EXECUTION_PLAN_STATUS.md`, and decide whether to begin W14 (Phase 1.5, two-Postgres split) or knock out the small W05 / pmset items first.*

That single paragraph + this file + the 4 docs = fresh Claude up-to-speed in ~5 minutes.

---

## 10. Honest reactions to the strategic docs (carried over from tonight's discussion)

For Bobby's reference if questioned in the next session. These are MY reactions, not the plan's claims:

**Things the plan got right:**
- The W-numbering itself is the highest-value artifact. "Working on W11" is unambiguous; "working on the Slack thing" isn't.
- The W02 → W03 → W04 sequencing (pg_stat_statements before pool before tuning) is correct and non-obvious.
- "Additive, not corrective" framing in Report 3 is true. The plan's items are query additions and new modules, not refactors. That matters psychologically — you can finish W06 in an afternoon.

**Things I'd adjust:**
- The plan's W16/W17 status assumption is stale — today's work closed W16.
- W14's effort estimate (L, 1 week) is too light. 2 weeks more realistic.
- The plan has zero operator-facing-dashboard items. Defensible but explicit. W23/W24/W25 fill that gap.
- Bobby's instinct to move W14 forward is right. The plan put it in Phase 4 on stability grounds, but the cost of building W11 and W06–W08 against the wrong topology outweighs the disruption of doing W14 first.

---

*End of handoff. Prepared 2026-05-11 evening, Monday. Companion docs: 4 `.docx` strategy files (attach to next chat). Living document — amend tomorrow as work begins.*
