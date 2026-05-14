# HANDOFF — 2026-05-14 (Thursday evening)

> **For the next session.** This is the durable record of what happened today. The state of the world is in this file plus the artifacts it points at. Read this AFTER `docs/MORNING_BRIEFING_2026-05-15.md` — the morning briefing is the orientation; this file is the deep history.

---

## E0. The actual TL;DR

A focused day with **one shipped PR** but **one major discovery** that reframes a chunk of the project's near-term work.

**Chapter 1 — W10 shipped (started in the morning, before this session's compaction).** PR #221: four catalog-intake `propose_*` functions added to `intelligence-catalog/db/dual_writer.py`. Merged. (Detail in E2 — it landed early and is already reflected in `EXECUTION_PLAN_STATUS.md`.)

**Chapter 2 — Grafana dashboard diagnosis → a much bigger finding.** What started as "the AI & Learning and Intelligence Report dashboards look empty on the Mini" turned into a multi-layer investigation. The dashboards themselves are **fine** — the Prometheus pipeline is healthy end-to-end, and the panels were just (a) defaulting to time windows wider than the young Mini Prometheus has data for, and (b) visually buried under oversized iframe panels. **That part is fixed and shipped — PR #222 (W34).**

But the same investigation surfaced the real thing: **the AI Intelligence Score reads ~43.8K on the Mini vs 100K+ on the old VPS.** Root cause traced cleanly — `ai_score.py` is a cumulative row-count metric, and the Mini's operational Postgres is a **2026-05-07 fresh start**. The VPS's historical operational data — including ~12.5M `log_metrics` rows — **was never migrated to the Mini at cutover.** It is **NOT lost**: it's intact on the VPS, and all five relevant DB files were preserved and byte-verified today. This is now tracked as **W33** — a real SQLite→Postgres migration, explicitly scoped as its own future session (operator decision: tomorrow or this weekend, not rushed).

**End-of-day state:** `main` at `b89e033` (PR #222 merge). Mini dashboards fixed + verified. VPS data preserved. W33 + W34 added to the execution plan. One shipped PR, one major find documented.

**Main HEAD at end of day:** `b89e033` (PR #222 merge).

---

## E1. PR ledger for today

| # | PR | Branch | Summary |
|---|---|---|---|
| 1 | #221 | `w10-catalog-propose-functions` | W10 — four catalog-intake `propose_*` functions in `dual_writer.py` (A11) |
| 2 | #222 | `mg/pr-grafana-time-window` | W34 — narrow `reference-mini/` dashboard time-range defaults + W33/W34 plan entries |

Two merges. The day's *value* is not in PR count — it's in the W33 discovery (see E4), which is worth more than several small PRs because it prevents the team from building on a wrong assumption about what data the Mini has.

---

## E2. Chapter 1 — W10 shipped (PR #221)

W10 = "Extend `dual_writer.py` with catalog-intake `propose_*` functions." This landed early in the calendar day (the session was compacted afterward; full detail is in the transcript referenced by the compaction summary).

**What shipped:** four functions in `intelligence-catalog/db/dual_writer.py` — `propose_firmware_release`, `propose_firmware_compatibility`, `propose_data_conflict`, `record_freshness_check`. Unlike the existing `propose_*` functions (which stage into `staging.*`), these write **direct** to their catalog tables — confirmed against the schema that `staging_schema.sql` has exactly 3 proposal tables, none for firmware/conflict/freshness, and the W11 Slack-Approve flow is their validation gate.

- `propose_data_conflict` dedups on the unresolved `(conflict_table, conflict_row_id, conflict_field)` triple both in-function and via a new partial-unique-index backstop (`intelligence_catalog_schema_v4_additions.sql` + `\ir` line in `deploy_schema.sql`; index applied to live `mg-catalog-db`, 0 pre-existing dup triples).
- Tests: `intelligence-catalog/db/tests/test_w10_catalog_intake.py` (5 unit + 9 integration).
- **Live-Mini smoke: 9/9 against `mg-catalog-db`, teardown clean.**
- Per **A11** in `strategy/AMENDMENTS_2026-05-12.md`: `propose_community_intel` (A09's 5th function) was split out to **W10b** because no `community_intel` table exists yet — designing it deserves deliberate treatment, not a guess.

W10 status is `[X]` in `EXECUTION_PLAN_STATUS.md`. W10b is `[ ]`, blocked-on-nothing, and is the next item on the catalog critical path (before W11).

**One mid-flight bug worth remembering** (full detail in transcript): a rogue `/tmp/inspect.py` left on the Mini from May 13 Grafana debugging was shadowing the stdlib `inspect` module for *any* Python run from `/tmp/`, breaking `import dataclasses` in `core/db_targets.py`. Cost three wrong guesses before a step-by-step diagnostic pinned it. Lesson: throwaway scripts in `/tmp/` on the Mini can shadow stdlib modules — name them defensively or clean them up. (This is part of why `.w10-smoke-tmp/` on the laptop was cleaned up at end of day — see E5.)

---

## E3. Chapter 2 — Grafana dashboard diagnosis (PR #222 / W34)

### E3.1. The presenting problem

Two dashboards Bobby cares about most — **"Mining Guardian — AI & Learning"** (proves the program works) and **"Mining Guardian — Intelligence Report"** (catalog data access) — looked nearly-empty on the Mini. AI & Learning showed one "43.7K" tile and black space; Intelligence Report showed logo + static text only.

### E3.2. The full pipeline trace — everything proven healthy

This was the disciplined part. Rather than guessing, every link in the chain was verified against the live Mini:

1. **`dashboard_api /metrics` endpoint EXISTS and WORKS** — `api/dashboard_api.py` already has a comprehensive Prometheus `/metrics` endpoint emitting ~43 `mining_guardian_*` metrics. Live `curl localhost:8585/metrics` = 2589 lines, 43 metrics, real values (`mining_guardian_knowledge_score{site="usa_188"} 43806`). No crashes.
2. **Prometheus is installed + running** — Homebrew prometheus 3.11.3, `:9090` HTTP 200, launchd plist present.
3. **Prometheus IS scraping and HAS the data** — `prometheus.yml` at `/opt/homebrew/etc/prometheus.yml` has the correct scrape job `mining_guardian` → `127.0.0.1:8585`, 30s interval. Target health `up`, `lastError` empty. TSDB has the series (`mining_guardian_knowledge_score = 43868`, 2490 series).
4. **Datasource UIDs all match** — every panel references `efi3m84mbf668b` (the provisioned Prometheus datasource UID). 25/25 refs in AI & Learning, 4/4 in Intelligence Report. Confirmed by parsing the JSON.
5. **Grafana loaded all 14 panels** — `/api/dashboards/uid/llm_learning_001` confirms Grafana sees every panel. `provisioned: true`.
6. **Prometheus query works THROUGH Grafana's own datasource proxy** — `/api/datasources/proxy/uid/efi3m84mbf668b/api/v1/query?query=mining_guardian_knowledge_score` returns `{"status":"success", ... "value":[...,"43868"]}`. The exact path a panel uses — works.
7. **All panel PromQL queries are correct** — full per-panel audit done: every metric name in every `expr` exists in the live 43-metric set. AI & Learning's 8 data panels all valid. Intelligence Report's 2 timeseries panels valid.

**Conclusion: the pipeline is not broken.** Not the endpoint, not Prometheus, not the scrape, not the datasource, not the UIDs, not the queries.

### E3.3. The two actual issues

**Issue A — time-range defaults too wide for a young Prometheus.** Prometheus on the Mini started `Wed May 13 14:23:37` — it has **~23 hours** of history. The dashboards defaulted to VPS-era windows: AI & Learning `now-24h`, Intelligence Report `now-7d` with `refresh: ""`. A 7-day window against 23h of data renders ~85% empty — the timeseries panels *looked* broken when the data simply wasn't in the queried window. The stat panel ("43.7K") rendered because a stat panel only needs the latest value; timeseries panels need history across the window.

**Issue B — oversized iframe panels burying the real panels.** AI & Learning panel `id=1` is an iframe at `gridPos {h:26}` ≈ 780px tall. The 8 real data panels live at `y:42` and below — two screens down, hidden behind the iframe. Intelligence Report panel `id=10` is an `h:28` iframe with panels 20/21 below it. **The panels were rendering the whole time** — Bobby confirmed this live by scrolling: the timeseries panels are there and populated, just below the fold.

### E3.4. What W34 fixed and shipped (PR #222)

**Issue A is fixed.** Surgical 3-line edit to the two `reference-mini/` JSONs:
- `mining_guardian_ai_learning.json`: `time.from` `now-24h` → `now-6h`
- `mining_guardian_intelligence_report.json`: `time.from` `now-7d` → `now-6h`, `refresh` `""` → `"1m"`

Diff is exactly `3 insertions(+), 3 deletions(-)` on the JSON — byte-for-byte formatting otherwise preserved (W26b mirror discipline held; an initial `json.dump` attempt that reformatted all the emoji escapes was caught and reverted via `git checkout`). Both files re-parse as valid JSON. Deployed to the Mini via `scp` and **operator-verified live**.

PR #222 also carries the W33 + W34 entries in `EXECUTION_PLAN_STATUS.md` (doc + code in the same commit, per the "document as you go" convention).

**Issue B is NOT fixed — it's a known follow-on, noted under W34 but not yet its own tracked item.** It's a layout fix (shrink or relocate the oversized iframe panels). Different bug class from the time-window fix → Failure Mode 9 says it doesn't ride along. See E6.

### E3.5. Process notes from this chapter (worth keeping)

- **Two wrong hypotheses before the right one.** First guess: datasource UID mismatch (the W26a-style bug). Wrong — audit showed all UIDs match. Second guess: the panels aren't rendering at all. Wrong — Grafana's API showed all 14 loaded and the proxy query worked. The right answer (below-the-fold + time window) only emerged from disciplined elimination. **Lesson reinforced: verify each link, don't pattern-match to the last similar bug.**
- **The `ask_user_input_v0` tool was not capturing selections in this session** — it returned the question structure with no answers attached. Worked around by asking in plain text. If a future session sees the same, don't fight it — just ask in prose.
- **Bobby's terminal mangles multi-line pasted commands** — multi-line inline-Python (`python3 -c "..."` spanning lines, or heredocs pasted interactively) collides with shell scrollback and hangs on `>` continuation prompts. **The reliable pattern: write a `cat > /tmp/script.sh << 'SCRIPT' ... SCRIPT` file, then `bash /tmp/script.sh`.** Used this for every Mini/VPS diagnostic in the back half of the session and it worked every time.

---

## E4. THE BIG FINDING — W33: VPS historical data was never migrated

This is the most important thing in this handoff. Read it carefully.

### E4.1. How it surfaced

While confirming the dashboards work, Bobby noted: the AI Intelligence Score used to read **100K+** on the VPS; on the Mini it reads **~43.8K**. That's not a rounding difference — it's more than half the score gone.

### E4.2. Root cause — NOT a bug, a true measurement

`ai/ai_score.py::calculate_score()` is a **cumulative, row-count-driven metric.** Its single largest contributor, by the code's own comment:

```python
"log_metrics": 0.01,   # 9.7M rows × 0.01 = ~97k pts
```

`log_metrics` at VPS-scale (~12.5M rows) was contributing ~97K of the old ~100K score. The score is essentially a function of *how many rows are in the operational database.*

The Mini's operational Postgres (`mining-guardian-db`, DB `mining_guardian`) is a **fresh start** — its oldest scan is **2026-05-07**, and it has been collecting for ~7 days. Confirmed row counts (2026-05-14 13:55):

| Table | Mini rows |
|---|---|
| `log_metrics` | **0** |
| `scans` | 558 (oldest 2026-05-07) |
| `miner_readings` | 53,568 |
| `chain_readings` | 116,494 |
| `pool_readings` | 40,328 |
| `ams_notifications` | 23,160 |
| `action_audit_log` | 36 |
| `miner_restarts` | 13 |

So the score isn't lying and `ai_score` isn't broken — the score honestly reflects that the Mini's DB is days old, not months old. **The VPS jumpstart data was never carried across when the Mini cutover happened.**

### E4.3. The data is NOT lost — it's intact on the VPS

The whole point of running the VPS beforehand was to accumulate a jumpstart dataset. That dataset still exists. The VPS (`srv1549463`, root SSH, still reachable, still being paid for) stores its data as **SQLite, not Postgres** — the Postgres/two-DB split is Mini-era only.

Three `guardian.db` files on the VPS are **0-byte empty stubs** — red herrings (`/root/guardian.db`, `/root/Mining-Guardian/guardian.db`, both empty; the scanner is `inactive`). The **real data** is in:

| File | Size | Contents |
|---|---|---|
| `/root/snapshots/2026-04-08-1410/Mining-Gaurdian/guardian.db` | 4.1 G | 22 tables, 1,351 scans, **`log_metrics` = 12,549,605**, scan range 2026-03-27 .. 2026-04-08 |
| `/root/Mining-Guardian/databases/timeseries.db` | 5.4 G | newer VPS split DB, mtime Apr 22 |
| `/root/Mining-Guardian/databases/audit.db` | 1006 M | newer VPS split DB, mtime Apr 22 |
| `/root/Mining-Guardian/databases/operational.db` | 1.6 M | newer VPS split DB, mtime Apr 23 |
| `/root/Mining-Guardian/databases/ai_knowledge.db` | 5.2 M | newer VPS split DB, mtime Apr 22 |

Note there are **two candidate sources**: the April 8 snapshot (older, single SQLite file, definitely has the 12.5M `log_metrics`) AND the April 22-23 split DBs (newer, but they were the VPS's *own* mid-migration artifacts — the VPS went through its own SQLite→split-DB migration in April). Part of W33's scope is deciding which is canonical.

### E4.4. Data preserved today — byte-verified

Before any migration work, all five files were copied to `/root/db-preserve-20260514/` on the VPS. **Copy completed and byte-verified:**

| File | Bytes |
|---|---|
| guardian.db | 4,301,082,624 |
| timeseries.db | 5,771,853,824 |
| audit.db | 1,054,085,120 |
| operational.db | 1,585,152 |
| ai_knowledge.db | 5,390,336 |

VPS `/dev/sda1`: 328G free of 387G — ample headroom for the migration's scratch DB.

### E4.5. Why this is a migration, not a recovery — and why it's NOT today's work

The data is safe. That safety is *exactly* what makes it correct to NOT rush this. **The real risk in W33 is schema drift:** the VPS SQLite schema predates the W14 two-DB split, the P-020/W14a column conventions, and the P-038 timestamptz work. It likely has column renames and type differences vs the Mini's Postgres schema. A naive `INSERT` will silently truncate or mis-map data — which would be a real loss, manufactured by haste, when the original is fine.

**Operator decision (2026-05-14): W33 is its own session — tomorrow or this weekend, not the tail end of a long day.** It is fully scoped in `EXECUTION_PLAN_STATUS.md` (the W33 row has the complete 6-step plan). See E7 for the next-session pointer.

---

## E5. End-of-day state

### Repo
- **`main` HEAD: `b89e033`** (PR #222 merge)
- Working tree: clean except `.claude/settings.json` (the always-present plugin-marketplace drift — out of scope, never staged, per existing convention)
- `mg/pr-grafana-time-window` branch deleted (local + remote) after merge
- `.w10-smoke-tmp/` throwaway dir removed from laptop (W10 merged; contained `w10_diag.py`, `w10_mini_smoke.py`, `.ready` — all dead)
- Stale local branches still present (13 `mg/p0*` + `feat/w26-cohort-guard-test` + `docs/w25-correct-grafana-preference`) — cleanup deferred, same as prior handoffs noted

### Mini at `miningguardian@100.69.66.32` (Tailscale)
- macOS 26.4.1, M4, 16GB RAM
- Install root: `/Library/Application Support/MiningGuardian/` (NOT git-managed; manual scp delivery)
- Colima Docker, CLI at `/usr/local/bin/docker`
- **Two dashboards updated today** (`mining_guardian_ai_learning.json`, `mining_guardian_intelligence_report.json`) at `/Library/Application Support/MiningGuardian/grafana/dashboards/` — match the repo's `reference-mini/` versions as of PR #222
- W10 code already on the Mini (`dual_writer.py` scp'd during W10 smoke; backup `dual_writer.py.pre-w10-20260514-124451` retained)

### Postgres topology (unchanged from W14)
- `mining-guardian-db` (port 5432:5432) — operational only, DB `mining_guardian`
- `mg-catalog-db` (port 5433:5432) — catalog only, DB `mining_guardian_catalog`
- **Operational DB is a 2026-05-07 fresh start — see E4. `log_metrics` = 0 rows.**

### Prometheus (newly characterized today)
- Homebrew prometheus 3.11.3, launchd plist present, `:9090` healthy
- Config `/opt/homebrew/etc/prometheus.yml` — scrape job `mining_guardian` → `127.0.0.1:8585`, 30s interval
- TSDB started `2026-05-13 14:23` — ~23h of history at end of day, ~2490 series
- Scraping `dashboard_api /metrics` (43 metrics), target healthy

### Grafana 13.0.1
- `http://100.69.66.32:3000` over Tailscale
- 4 datasources (1 operational PG + 2 catalog PG + 1 Prometheus `efi3m84mbf668b`)
- AI & Learning + Intelligence Report dashboards now default to `now-6h` (W34) — panels render + verified
- Admin: `admin / W25test` (rotation still deferred)

### VPS at `srv1549463` (root SSH)
- **Still up, still reachable, still being paid for**
- SQLite-based (no Postgres). Scanner `inactive`.
- Historical data intact; 5 DB files preserved + byte-verified to `/root/db-preserve-20260514/` (see E4.4)
- `*** System restart required ***` pending + 36 apt updates — note for whoever does W33: a reboot is owed, do it deliberately, not mid-migration

---

## E6. Open items at end of day

### Resolved today (moved off the open list)
- ~~W10 — four `propose_*` functions~~ ✅ Done (PR #221)
- ~~W34 — dashboard time-range defaults~~ ✅ Done (PR #222)
- ~~"Why are the dashboards empty"~~ ✅ Diagnosed — pipeline healthy, was time-window + below-the-fold
- ~~"Why is the AI score down"~~ ✅ Diagnosed — W33 (VPS data not migrated); data preserved

### Newly opened today
- **W33 — Migrate VPS historical operational data → Mini Postgres.** The big one. SQLite→Postgres, ~12.5M-row scale, schema-drift risk. Fully scoped in `EXECUTION_PLAN_STATUS.md`. **Operator decision: own session, tomorrow/weekend.** Data preserved + safe.
- **W34 — dashboard time-range defaults.** Shipped today (PR #222), status `[~]` → should be flipped to `[X]` next session now that PR #222 is merged (minor doc-status follow-up).

### Still open — known, tracked, not urgent
- **Iframe-panel layout fix** (Issue B from E3.3) — the oversized iframe panels (AI & Learning `id=1` `h:26`, Intelligence Report `id=10` `h:28`) bury the real data panels below the fold. **Not yet its own W-item** — noted under W34's follow-ons. Should get a number next session if it's going to be worked. Small, cosmetic-ish, but real.
- **W31** — Grafana HTML-panel inline-`<script>` rendering defect. Re-confirmed today: visible in the AI & Learning screenshots dumping raw JS as text. Still `[ ]`.
- **W32** — IP-templating for `reference-mini/` dashboards. The hardcoded `100.69.66.32` in iframe panels. Still `[ ]`.
- **W10b** — `community_intel` table + `propose_community_intel` (5th function, split from W10 per A11). Next on the catalog critical path, before W11. Still `[ ]`.
- **W17** — 151 naked `datetime.now()` calls to convert to UTC-aware. Sweep, not deep work.
- **W14a cohort-guard gap** — noted in earlier sessions: `tests/test_w14a_no_direct_pg_env_reads.py` documents a `tests/` exclusion that `_scan_for_pattern_2()` never implements. A guard with a hole. Own one-commit fix when picked up.

### Open security (unchanged — still needs a dedicated pass)
- 🔐 **Postgres password rotation** — Mini's deployed Grafana yaml still has the password as a literal 64-char hex string. Same value was visible in chat on prior days. Rotation: `ALTER USER mg WITH PASSWORD '<new>'` on **both** containers (5432 + 5433), update `.env` on Mini, update Grafana's deployed yaml, restart services that read `GUARDIAN_PG_PASSWORD`. ~30-60 min careful work.
- 🔐 **Grafana admin password rotation** — currently `W25test`. Before customer ship.
- 🔐 **Anthropic API key** — was rotated May 12; new key briefly visible in chat that day. Watch rotation cadence.

### Deferred technical debt (carried from prior handoffs, unchanged)
- **W24** — Grafana password secret management (proper). Currently inlined in deployed yaml.
- **catalog_import permissions** — pre-existing bug surfaced during W14 verification.
- **`daily_deep_dive` stale last-run-date tracking** — pre-existing bug surfaced during W14 verification.
- **feedback-loop-daemon** — not writing to catalog since 2026-05-09.
- **`.claude/settings.json`** plugin marketplace migration — clean drift in working tree, not committed.
- **Pre-existing scanner-log errors** (noted at W03 close, still unaddressed): `no such table: hvac_readings`; a SQLite-ism `datetime('now', ...)` in a post-scan LLM query (flagged non-fatal by the code). `dashboard_api.py`'s `/metrics` and `environment_history` endpoints also still contain SQLite-isms (`strftime`) and reference possibly-missing tables — they don't currently crash, but they're fragile. Their own items.
- **13 stale local `mg/p0*` branches** + 2 others — local-only cleanup, no urgency.

---

## E7. Where the plan stands after today

| Phase | Items | Status after 2026-05-14 |
|---|---|---|
| Phase 1 — Foundation | W01–W05 | W01 `[~]`, W03 `[X]`, W05 `[X]`. W02/W04 in line. |
| Phase 1.5 — Architectural restoration | W14a, W14, W14b | All `[X]` (closed 05-12/05-13). |
| Phase 2 — Closing the integration gap | W06–W09 | Unblocked by W03 + W14. Not started. |
| Phase 3 — External intake & operator surfaces | W10, W10b, W11, W12, W13 | **W10 `[X]` (today).** W10b next on critical path. W11 blocked on W10b. |
| Phase 4 — Architectural correctness | W15, W16, W17 | W16 `[X]`. W15/W17 open. |
| Phase 5 — Performance polish | W18–W22 | Post-August. |
| New W-items | W23–W34 | W23/W25/W25b/W26/W26a/W26b `[X]`. **W34 `[X]` (today, pending status flip).** W24/W27/W28/W29/W30/W31/W32 open. **W33 NEW (today) — the migration.** W10b also open. |

**Critical path to mid-August customer ship is unchanged:** W10b → W11 → W06–W09 → W27/W30 → W12/W24/W31/W32 → W28/W29. **W33 is NOT on the customer-ship critical path** — it restores *master-instance* historical depth (the AI score, the jumpstart). It matters, but it's a parallel track, not a blocker for shipping.

---

## E8. Tomorrow's job — operator's call

Two clear candidates, and Bobby decides which (or neither — it's a weekend):

**Option 1 — W33, the migration.** The big one. It has a full 6-step scope already written in `EXECUTION_PLAN_STATUS.md`. It's L–XL effort and wants a fresh, unhurried session. If tomorrow is a real work day, this is the highest-value thing on the board. **First moves if chosen:** (1) inspect both VPS source candidates (Apr 8 snapshot vs Apr 22-23 split DBs) to decide canonical source; (2) per-table schema diff VPS-SQLite → Mini-Postgres operational schema; do NOT write migration code until the schema diff is done.

**Option 2 — W10b, the catalog critical-path item.** Smaller, well-defined: design the `knowledge.community_intel` table, add it via `v5_additions.sql` + `deploy_schema.sql` `\ir`, add the 5th `propose_*` function mirroring the W10 four, test + live-Mini-smoke. This unblocks W11. Good choice if tomorrow is a lighter session.

**My recommendation:** if it's a full work session, **W33** — it's the thing most worth doing carefully, and it's been sitting un-migrated since the cutover. If it's a short session, **W10b** — it's the kind of contained, well-scoped work that finishes cleanly. Do NOT start W33 if there isn't a real block of time for it; a half-done schema migration is worse than an un-started one.

---

## E9. Notes to tomorrow's Claude

- **Read `MORNING_BRIEFING_2026-05-15.md` first.** It has the ordered reading list and the sanity-check commands.
- **W33 is the headline. Do not treat it as a quick task.** The data is safe on the VPS (preserved + byte-verified) — that safety is the whole reason to do the migration *carefully*. If you find yourself writing migration `INSERT`s before you've done a column-by-column schema diff, stop.
- **There are TWO VPS source candidates** (Apr 8 snapshot + Apr 22-23 split DBs). Don't assume the snapshot is canonical just because it's the one we counted first. The split DBs are newer. Part of W33 step 1 is deciding.
- **The score being "low" is correct behavior, not a bug.** `ai_score.py` is doing exactly what it should. Don't "fix" `ai_score.py` to inflate the number — the fix is to restore the data it counts (W33), or, separately and later, to decide whether a raw-row-count score is the right *design* (that's a real question, but it's not W33 and it's not urgent).
- **The dashboards are FINE.** If Bobby or a future session says "the dashboards are still broken" — they're not. The panels render. They were (a) defaulting to too-wide a time window (fixed, W34) and (b) sitting below oversized iframe panels (known, not yet a numbered item). Scroll down before re-diagnosing.
- **`ask_user_input_v0` was not capturing selections this session.** If it happens again, just ask in plain prose. Don't burn turns fighting the tool.
- **Multi-line pasted commands break Bobby's terminal.** Use the `cat > /tmp/x.sh << 'SCRIPT' ... SCRIPT` then `bash /tmp/x.sh` pattern for anything that isn't a single clean line.
- **W34 status flip:** PR #222 is merged; the W34 row in `EXECUTION_PLAN_STATUS.md` is still `[~]` "until the PR merges." First trivial task next session: flip it to `[X]` with the merge commit `b89e033`, plus a History line. (Left as `[~]` tonight deliberately — didn't want to claim `[X]` before confirming the merge in a fresh `git log`.)
- **The iframe-panel layout issue (E3.3 Issue B / E6) has no W-number yet.** If it's going to be worked, give it one. If not, at least it's captured here.

---

## E10. Quick verification commands for tomorrow

```bash
# Repo where we think it is?
cd /Users/BigBobby/Documents/GitHub/Mining-Guardian
git status                                              # main clean (modulo .claude/settings.json)
git log --oneline -1                                    # b89e033 or later
.venv-p018-tests/bin/python -m pytest tests/ 2>&1 | tail -3
# Expected: all pass (474+ / some skipped)

# Mini reachable + services healthy?
ssh miningguardian@100.69.66.32 'echo ok && date'
ssh miningguardian@100.69.66.32 'sudo launchctl list | grep com.miningguardian | wc -l'
# Expected: 22 (12 cron + 10 always-on)

# Both Postgres instances responding?
ssh miningguardian@100.69.66.32 'docker ps --format "{{.Names}} {{.Status}}"' | grep -E "mining-guardian-db|mg-catalog-db"

# The W33 reality check — Mini operational DB row counts
ssh miningguardian@100.69.66.32 'docker exec mining-guardian-db psql -U mg -d mining_guardian -t -c "SELECT (SELECT COUNT(*) FROM log_metrics) AS log_metrics, (SELECT COUNT(*) FROM scans) AS scans, (SELECT MIN(scanned_at) FROM scans) AS oldest"'
# Expected: log_metrics 0, scans ~558+, oldest 2026-05-07 — this is the gap W33 closes

# Grafana healthy + dashboards default to 6h?
curl -s http://100.69.66.32:3000/api/health
# Expected: {"database":"ok","version":"13.0.1-0",...}

# VPS still reachable + preserved data intact?
ssh root@srv1549463 'ls -lh /root/db-preserve-20260514/'
# Expected: 5 files, ~12GB total — guardian.db 4.3GB, timeseries.db 5.8GB, audit.db 1.05GB, operational.db 1.6MB, ai_knowledge.db 5.4MB
```

---

*End of evening handoff. See [`MORNING_BRIEFING_2026-05-15.md`](MORNING_BRIEFING_2026-05-15.md) for tomorrow's orientation. The W33 scope lives in [`EXECUTION_PLAN_STATUS.md`](EXECUTION_PLAN_STATUS.md) — the W33 table row is the authoritative runbook until a dedicated `strategy/W33_PREP.md` is written.*
