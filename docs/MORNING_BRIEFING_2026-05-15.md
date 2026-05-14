# Morning Briefing — 2026-05-15 (Friday)

> **You are reading this at the START of a new Claude session.** This is the single document that brings the new session up to speed without needing to ask the operator questions. Read this file top-to-bottom in order. Linked references are listed inline so you can pull them as needed.
>
> **The operator (Bobby) has explicitly stated:** "I would rather not spend 30-60 minutes answering questions about what the day is about and what we have done and what is the right way to do things." Honor that. Read the docs, read the linked files, then state what you're going to do.
>
> **Today is operator's-choice day.** Yesterday closed cleanly (W10 + W34 shipped) and surfaced one major new item (W33 — the VPS data migration). There are two well-scoped candidates for today; Bobby picks. See §1 and §9.

---

## 0 · Required reading order (do this BEFORE the first action)

Read these files in this exact order. Each is canonical for its domain. Don't ask the operator about anything in these files — read them.

| # | File | Why |
|---|---|---|
| 1 | This file (`docs/MORNING_BRIEFING_2026-05-15.md`) | Single-page orientation + reading order |
| 2 | `docs/HANDOFF_2026-05-14_EVENING.md` | **What actually happened yesterday.** W10 shipped (PR #221), then the Grafana diagnosis that became the W33 discovery. Read E0 through E10 — especially **E4 (the W33 finding)** and **E8/E9 (today's options + notes)**. |
| 3 | `docs/EXECUTION_PLAN_STATUS.md` | Source of truth for what's done. **The W33 table row is the authoritative migration runbook** until a `strategy/W33_PREP.md` exists. Also check the History tail. |
| 4 | `CLAUDE.md` in repo root | Working conventions (Failure Mode 9, sibling sweeps, evidence-before-fix, live-Mini smoke, W14b two-target rule, `.env` quote-stripping). Skim if you have it. |
| 5 | (if today is W33) `ai/ai_score.py` | The cumulative row-count metric at the heart of the W33 finding. Read `calculate_score()` so you understand what the migration restores. |
| 6 | (if today is W10b) `intelligence-catalog/db/dual_writer.py` + `strategy/AMENDMENTS_2026-05-12.md` §A11 | The W10 four functions are the template for W10b's fifth. A11 explains why `propose_community_intel` was split out. |

**After reading those, you have hour-4 context.** Don't ask the operator to re-explain any of it.

---

## 1 · Today's job — operator picks one

Yesterday's work is **done and merged**. There is no carry-over execution task. Two clean candidates for today, and Bobby decides:

### Option 1 — W33: migrate the VPS historical data to the Mini (the big one)

The AI Intelligence Score reads ~43.8K on the Mini vs 100K+ on the old VPS. **This is not a bug** — `ai_score.py` is a cumulative row-count metric and the Mini's operational Postgres is a 2026-05-07 fresh start (`log_metrics` = 0 rows). The VPS's ~12.5M-row historical dataset — the original "jumpstart" — **was never carried across at cutover.** It is **not lost**: it's intact on the VPS, SQLite, and all 5 relevant DB files were preserved + byte-verified yesterday to `/root/db-preserve-20260514/`.

W33 is a real SQLite→Postgres migration. **L–XL effort. It needs a fresh, unhurried block of time.** Full 6-step scope is in the W33 row of `EXECUTION_PLAN_STATUS.md`. **Do not start W33 unless there's a genuine work block for it** — a half-done schema migration is worse than an un-started one.

### Option 2 — W10b: the catalog critical-path item (smaller, contained)

Design `knowledge.community_intel`, add it via `v5_additions.sql` + `deploy_schema.sql` `\ir`, write the 5th `propose_*` function mirroring the W10 four (shipped yesterday), test + live-Mini-smoke. Unblocks W11. **M effort, well-defined, finishes cleanly.** Good if today is a lighter session.

### Recommendation

Full work session → **W33** (highest value, been un-migrated since cutover, wants care). Short session → **W10b** (contained, clean finish). Either way: **propose the plan to Bobby before executing** — but the choice between the two is his to make first.

---

## 2 · Trivial first task regardless of which option (≤2 min)

PR #222 merged yesterday but the **W34 row in `EXECUTION_PLAN_STATUS.md` is still `[~]`** — it was deliberately left partial last night because the merge hadn't been confirmed in a fresh `git log`. Confirm `b89e033` is on `origin/main` (it is), then flip W34 `[~]` → `[X]`, cite merge commit `b89e033`, and add a one-line History entry. This is the "document as you go" loose end from yesterday — close it first, in its own tiny commit or folded into today's first PR's doc changes.

---

## 3 · Locked context (do NOT re-litigate or re-diagnose these)

- **The dashboards are FINE.** AI & Learning and Intelligence Report render correctly. They were (a) defaulting to too-wide a time window — **fixed yesterday, W34/PR #222** — and (b) the real data panels sit *below* oversized iframe panels, so you have to scroll. If anyone says "the dashboards are still broken," scroll down before re-diagnosing. The pipeline (`dashboard_api /metrics` → Prometheus → Grafana) was traced end-to-end yesterday and is healthy.
- **The AI score being "low" is correct behavior.** `ai_score.py` is a cumulative row-count metric doing exactly what it should. **Do NOT "fix" `ai_score.py` to inflate the number.** The fix is to restore the data it counts (W33). Whether a raw-row-count score is the right *design* long-term is a real question — but it is NOT W33 and NOT urgent; don't fold it in.
- **The VPS data is safe.** Preserved + byte-verified to `/root/db-preserve-20260514/` on `srv1549463`. W33 is a *migration*, not a *recovery*. The real risk in W33 is **schema drift** (VPS SQLite schema predates W14/P-020/P-038), not data loss.
- **Two VPS source candidates exist** — the Apr 8 snapshot (`/root/snapshots/2026-04-08-1410/.../guardian.db`, 4.1G, definitely has 12.5M `log_metrics`) AND the Apr 22-23 split DBs (`/root/Mining-Guardian/databases/{timeseries,audit,operational,ai_knowledge}.db`). The split DBs are newer but were the VPS's own mid-migration artifacts. **Deciding canonical source is W33 step 1** — don't assume.

---

## 4 · Production state as of end of 2026-05-14

### Repo
- **`main` HEAD: `b89e033`** (PR #222 merge) — verify with `git log --oneline -1`
- Working tree clean except `.claude/settings.json` (always-present plugin-marketplace drift; out of scope; never stage it)
- 15 stale local branches (13 `mg/p0*` + 2 others) — cleanup deferred, no urgency

### Mini at `miningguardian@100.69.66.32` (Tailscale)
- macOS 26.4.1, M4, 16GB RAM. Install root `/Library/Application Support/MiningGuardian/` (NOT git-managed; manual scp delivery). Colima Docker, CLI at `/usr/local/bin/docker`.

### Postgres topology (W14, unchanged)
- `mining-guardian-db` (port 5432:5432) — operational only, DB `mining_guardian`. **2026-05-07 fresh start; `log_metrics` = 0 — this is what W33 fixes.**
- `mg-catalog-db` (port 5433:5432) — catalog only, DB `mining_guardian_catalog`

### Mini operational DB row counts (the W33 baseline — 2026-05-14)
| Table | Rows |
|---|---|
| `log_metrics` | 0 |
| `scans` | 558 (oldest 2026-05-07) |
| `miner_readings` | 53,568 |
| `chain_readings` | 116,494 |
| `pool_readings` | 40,328 |
| `ams_notifications` | 23,160 |
| `action_audit_log` | 36 |
| `miner_restarts` | 13 |

### Prometheus (Mini)
- Homebrew 3.11.3, launchd plist present, `:9090` healthy
- Config `/opt/homebrew/etc/prometheus.yml` — scrape job `mining_guardian` → `127.0.0.1:8585`, 30s
- TSDB started 2026-05-13 14:23 (~32h+ of history by now), ~2490 series

### Grafana 13.0.1
- `http://100.69.66.32:3000` over Tailscale. 4 datasources (1 operational PG + 2 catalog PG + 1 Prometheus `efi3m84mbf668b`).
- AI & Learning + Intelligence Report default to `now-6h` (W34). Admin `admin / W25test` (rotation deferred).

### VPS at `srv1549463` (root SSH)
- Still up + reachable + being paid for. SQLite-based, no Postgres. Scanner `inactive`.
- 5 DB files preserved + byte-verified to `/root/db-preserve-20260514/` (~12GB total).
- `*** System restart required ***` + 36 apt updates pending — a reboot is owed; do it deliberately, NOT mid-migration.

### launchd (Mini)
- 10 always-on services (`ProcessType=Standard`), 22 jobs total (12 cron + 10 always-on)

---

## 5 · Working conventions cheat-sheet

Pulled from `CLAUDE.md`. **These are binding** — do not silently violate.

- **Failure Mode 9** — sibling sweeps in one PR OK if same bug class; mixed bug classes never bundled.
- **Evidence before fix** — live-Mini evidence required before fix; live-Mini smoke required before commit.
- **Cohort guard tests** — every fix lands with a guard test that catches unsurfaced siblings.
- **Document as you go** — code change + doc update in the SAME commit.
- **Postgres access** (W14b rule 1) — through `core.db_targets` only. Enforced by `tests/test_w14a_no_direct_pg_env_reads.py`.
- **`.env` quote-stripping** (W14b rule 2) — through `xargs`. Enforced by `tests/test_w14_password_quote_consistency.py`.
- **Branch naming** — `mg/prNN-<name>` for features, `docs/<name>` for doc-only. New W-items get W35+. Sub-items use suffix letters.
- **Bobby's SSH session has sudo; Claude's does not.** Hand sudo commands to Bobby.
- **Bobby's terminal mangles multi-line pasted commands** — use the `cat > /tmp/x.sh << 'SCRIPT' ... SCRIPT` then `bash /tmp/x.sh` pattern for any diagnostic that isn't a single clean line. This bit the session repeatedly yesterday until the pattern was adopted.
- **`ask_user_input_v0` was not capturing selections yesterday** — if it happens again, ask in plain prose, don't fight the tool.
- **Bobby's standing preference** — always the most correct / highest-quality path, never the fastest. Present the rigorous option as the recommendation. Don't weight speed or effort.
- **Bobby likes to learn** — explain reasoning, don't just give answers.
- **No emojis unless Bobby uses them first** — minimal exception: ✅ ❌ for status, 🔐 for security flags.

---

## 6 · If today is W33 — the shape of it (full detail in EXECUTION_PLAN_STATUS.md W33 row)

Do NOT write migration code before steps 1–2 are done. The 6-step scope:

1. **Decide canonical source** — inspect the Apr 8 snapshot vs the Apr 22-23 split DBs; determine which holds the authoritative `log_metrics` / `miner_readings` history.
2. **Per-table schema diff** — VPS-SQLite schema → Mini-Postgres operational schema, column by column. This is where schema drift gets caught. **Gate: do not proceed to step 3 until this is complete.**
3. **Write the migration script** — explicit column mapping + type coercion (SQLite TEXT timestamps → Postgres timestamptz), chunked for the ~12M-row tables.
4. **Decide merge strategy** — the Mini already has 7+ days of *newer* data (May 7 onward) that must NOT be clobbered. VPS data is *older* (through Apr 8 / Apr 22-23) so it prepends — but watch for `scan_id` / PK collisions.
5. **Dry-run into a scratch DB** — row-count + spot-check before touching the live operational DB.
6. **Load, then verify** — re-run `ai_score` and confirm the score reflects the restored history.

Consider writing a `strategy/W33_PREP.md` runbook as the first deliverable (the way W14 and W26b got prep docs) — W33 is big enough to deserve one, and the EXECUTION_PLAN_STATUS row can be promoted into it.

---

## 7 · If today is W10b — the shape of it

1. Design the `knowledge.community_intel` table (schema, columns, indexes — what does "community intel" actually need to store; check A09/A11 and the catalog design plan for intent).
2. Add it via a new `intelligence-catalog/seed-data/intelligence_catalog_schema_v5_additions.sql` + `\ir` line in `deploy_schema.sql` (mirror how W10's v4 additions were structured).
3. Add `propose_community_intel` to `dual_writer.py` — mirror the four W10 functions (direct catalog write, arg validation, the same shape).
4. Test (`test_w10b_*` mirroring `test_w10_catalog_intake.py`) + live-Mini smoke against `mg-catalog-db`.
5. Apply the v5 index/table to the live `mg-catalog-db` as part of smoke.
6. PR. Unblocks W11.

---

## 8 · Open items NOT in scope for today (don't pull them in)

- **Iframe-panel layout fix** — the oversized iframe panels burying the real data panels (AI & Learning `id=1` `h:26`, Intelligence Report `id=10` `h:28`). Real, small, but **has no W-number yet** — if it's going to be worked, give it one (W35+); otherwise leave it captured in yesterday's handoff E6.
- **W31** — Grafana inline-`<script>` HTML panel rendering defect. Still `[ ]`.
- **W32** — IP-templating for `reference-mini/` dashboards. Still `[ ]`.
- **W17** — 151 naked `datetime.now()` → UTC-aware. Sweep.
- **W14a cohort-guard gap** — `tests/test_w14a_no_direct_pg_env_reads.py` documents a `tests/` exclusion `_scan_for_pattern_2()` never implements. Own one-commit fix.
- 🔐 **Postgres password rotation** — Mini's deployed yaml has a literal hex password. ~30-60 min careful work, dedicated session.
- 🔐 **Grafana admin password** — `W25test`. Before customer ship.
- **W24** — Grafana password secret management. Real, separate scope.
- **catalog_import permissions**, **`daily_deep_dive` stale last-run-date**, **feedback-loop-daemon catalog writes** — pre-existing bugs, tracked, not today.
- **Pre-existing scanner-log errors** — `no such table: hvac_readings`; SQLite-ism `datetime('now',...)` in a post-scan LLM query; `dashboard_api.py` `/metrics` + `environment_history` SQLite-isms. Fragile but not currently crashing. Their own items.

If any become urgent mid-session, surface them — don't fold them in. Failure Mode 9: same bug class only.

---

## 9 · Sanity-check commands (run after reading, before proposing the plan)

```bash
# Repo state
cd /Users/BigBobby/Documents/GitHub/Mining-Guardian
git status                                              # clean modulo .claude/settings.json
git log --oneline -1                                    # b89e033 or later
.venv-p018-tests/bin/python -m pytest tests/ 2>&1 | tail -5
# Expected: all pass

# Mini reachable + services healthy
ssh miningguardian@100.69.66.32 'echo ok && date'       # <2s
ssh miningguardian@100.69.66.32 'sudo launchctl list | grep com.miningguardian | wc -l'
# Expected: 22

# Both Postgres instances up
ssh miningguardian@100.69.66.32 'docker ps --format "{{.Names}} {{.Status}}"' | grep -E "mining-guardian-db|mg-catalog-db"

# The W33 reality check (run this even if today isn't W33 — it's the baseline)
ssh miningguardian@100.69.66.32 'docker exec mining-guardian-db psql -U mg -d mining_guardian -t -c "SELECT (SELECT COUNT(*) FROM log_metrics), (SELECT COUNT(*) FROM scans), (SELECT MIN(scanned_at) FROM scans)"'
# Expected: log_metrics 0 | scans ~558+ | oldest 2026-05-07

# VPS reachable + preserved data intact (only if today is W33)
ssh root@srv1549463 'ls -lh /root/db-preserve-20260514/ && df -h /root | tail -1'
# Expected: 5 files ~12GB total; /dev/sda1 ~328G free

# Grafana healthy
curl -s http://100.69.66.32:3000/api/health
# Expected: {"database":"ok","version":"13.0.1-0",...}
```

After verification, propose the plan to Bobby in your own words. Confirm which option (W33 / W10b / something else) before executing.

---

## 10 · Yesterday's PR list (for reference)

| # | PR | Summary |
|---|---|---|
| 1 | #221 | W10 — four catalog-intake `propose_*` functions in `dual_writer.py` (A11) |
| 2 | #222 | W34 — narrow `reference-mini/` dashboard time-range defaults + W33/W34 plan entries |

---

*End of morning briefing. Start with §0 (read the linked files), do §2 (the W34 status flip), do §9 (sanity checks), then propose your execution plan. Don't ask questions answered in these docs.*
