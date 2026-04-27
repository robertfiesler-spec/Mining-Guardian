# Session Log — 2026-04-26 (Sunday)

**Operator:** Bobby Fiesler (BigBobby)
**Agent:** Perplexity Computer
**Session duration:** ~10:00 am CDT through ~5:30 pm CDT
**Commits shipped:** 1 PR merged to main (`#5` — CR-5 Phase 1B), plus this documentation PR
**Context:** Final pre-cutover Sunday. Hardened the operational data plane, consolidated every open audit thread into one canonical to-do list, locked Mac Mini hardware decisions, and rescheduled the customer-grade install from Tue/Wed to **Monday 2026-05-05**.

---

## TL;DR

PR #5 merged cleanly and the last `GroupingError` is gone — scan #1775 saved 62 miners with zero tracebacks. While the deploy was burning in, two structural realizations changed the plan:

1. **The installer is the unit under test, not a one-off Mac Mini playbook.** `scripts/setup.sh` is 177 lines, BiXBiT-branded, and missing Postgres, Ollama, 7 of 8 services, all 9 cron jobs, Grafana, Tailscale, and the 8 plist templates the customer flow depends on. It has to be rewritten as the real customer install path.
2. **The catalog database is starving the AI.** 165 tables, 1,712 columns, and only **5 tables actually have data**. The 313-row baseline seed (`seed-data/seed_miner_models.sql`) was never executed. Five background watchers write findings to JSON files in `cron_tracking/` and never reach Postgres. Every Qwen analysis right now is uninformed by the catalog. C1/C3/C4/C5 in the audit all stem from this.

The operator's response — verbatim — was:

> "I would like everything done before we install on the Mac Mini. I truly want this to be a 100% representative of what customer would receive and load. All patches all fixes done. Paper written. I want to be our first customer. So if we push loading on the mini out that is fine. We were planing on May 5 anyway. I did not realize how far out we were. Remember slow and steady. I would rather be late and perfect than early and wrong."

That moves the install to **2026-05-05** and reframes the next 9 days as a customer-grade hardening sprint, not a Tuesday rush.

---

## Opening state (2026-04-26 ~10am CDT)

- **VPS:** Hostinger srv1549463, 8 systemd services active on Postgres 16.13
- **Origin HEAD:** `bcfbd58` — Saturday's PR #4 (CR-5 Phase 1) was merged but two latent GROUP BY violations were still firing in production logs
- **Known issue going in:** `psycopg.errors.GroupingError` on the outcome-checker's miner-aggregation queries — first observed late Saturday after the strict Postgres fixes in PR #4
- **AMS state:** healthy — 62 miners in last scan
- **Deadline at start of day:** Mac Mini arrives Monday 04-27, install Tue/Wed 04-28/29
- **Deadline at end of day:** Mac Mini install moved to **Monday 2026-05-05** (operator decision, see TL;DR)

---

## Commits shipped this session (chronological)

### 1. `6556848` — cr-5 phase 1b: fix Postgres strict GROUP BY violations

**Problem identified:** Saturday's PR #4 swapped the outcome checker to psycopg, but three aggregation sites in `core/mining_guardian.py` had grown additional `SELECT` columns over time without matching them in the `GROUP BY`. Postgres rejects this in strict mode (SQLite tolerates it). Production logs showed the checker firing the error at line ~1070 on every loop.

**Investigation path:**
1. `journalctl -u mining-guardian --since "<restart>" | grep GroupingError` → 3 distinct sites
2. `grep -n "GROUP BY" core/mining_guardian.py` → 4 occurrences, lines 1070 / 1080 / 1102 / 1103
3. Cross-checked `SELECT` lists against `GROUP BY` lists → 4 columns missing across 3 sites; the 4th occurrence was a `HAVING COUNT(*)` and correct
4. Wrote the patch as a 4-line diff so PR review was trivial

**Fix:** Added the missing columns to each `GROUP BY` clause. No behavior change — every column added was already a deterministic per-row value.

**Verification on VPS:**
```
scan #1775 saved (62 miners)
0 GroupingError
0 AttributeError
0 unhandled tracebacks since service restart
```

**PR:** [#5 — `cr-5 phase 1b: fix Postgres strict GROUP BY violations`](https://github.com/robertfiesler-spec/Mining-Guardian/pull/5) — merged as `476ef30`.

---

### 2. `(this commit)` — Sunday documentation pass

**Why:** Operator request — "I believe in over-documentation so we know what each day brings. Have you been on GitHub updated all the proper docs in the proper formats. Would you please do that now."

Three new docs landing in this commit:

- `docs/SESSION_LOG_2026-04-26.md` — this file
- `docs/ROADMAP_TO_MAC_MINI_2026-05-05.md` — the new master plan with the May 5 target and the customer-grade exit criteria
- `docs/MG_UNIFIED_TODO_LIST.md` — canonical 13-section to-do list consolidating Sunday sprint outcomes, 14 security findings (S-1 through S-14), 5 critical + 8 high audit items (C1–C5, H1–H8), OpenClaw removal checklist, Slack audit, installer rebuild plan, orphan code, locked decisions, user backlog, execution order, and effort estimates

Plus an update to `docs/DECISIONS.md` (created if missing) capturing the May 5 install date as a locked decision.

---

## Conversations that changed the plan

### "Ollama moves to the Mac Mini"

Around midday the operator said:

> "Real quick ollama will now be on the Mac mini, no longer on the pc, it will all be contained on the new mac"

Hardware envelope on the Mac Mini is **Apple Silicon, 16 GB RAM**. That eliminates `qwen2.5:32b` (would page to swap and crawl). Locked model: **`qwen2.5:14b-instruct-q4_K_M`** — fits in roughly 8.5 GB resident with comfortable headroom for the rest of the stack.

Implications saved to `mg_pre_prod/DECISIONS.md`:
- `OLLAMA_URL=http://localhost:11434/api/generate`
- Catalog DB host moves from `robs-pc` → `localhost` on the Mac
- Tailscale stays installed but data plane is local-only — Tailscale is for remote ops access, not for inference traffic

### "We are using the installer"

Mid-afternoon the operator clarified that the Mac Mini install is **the customer install path**, not a hand-crafted migration. That recast the entire Sunday cutover playbook (`/home/user/workspace/cutover/MAC_MINI_CUTOVER_CHECKLIST.md`, 919 lines) from a runbook into an installer specification.

I inspected `scripts/setup.sh` against production reality and produced the gap list now in Section 7 of the unified to-do.

### The May 5 decision

After printing the unified to-do list and answering the database/AI question, operator said the line in the TL;DR. Install is now Monday **2026-05-05**. Everything must be done before then, customer-grade.

---

## What "customer-grade" means (operator's bar)

The operator wants to be customer #1 — the install must be 100% representative of what a paying customer would receive. From this we derived hard exit criteria for May 5:

1. **No leaked secrets in the repo** — S-2 PAT revoked, no live credentials in `docs/`
2. **No hardcoded passwords or default API keys** — CRIT-1, CRIT-3, CRIT-6 closed
3. **No dead code that ships to a customer** — OpenClaw fully removed (10 active source files), orphan tables dropped or wired (chip_readings, log_collection_failures, s19jpro_overheat_tracking, empty `guardian.db` stub)
4. **One canonical catalog schema** — N6 consolidated from the current 4 versions in the repo
5. **AI actually has data to think with** — C4 seed run, C1/C3 dual-write fix landed so the catalog DB is populated and the API can read it
6. **Installer creates a working system from a blank Mac in one pass** — Postgres + Ollama + 8 LaunchAgents + 9 cron jobs + Grafana + Tailscale + secrets generation, with masked credential prompts and idempotent re-runs
7. **Every deploy day captured in a `SESSION_LOG_YYYY-MM-DD.md`** — paper trail end to end
8. **Customer-facing docs written** — Setup Manual, Program Instructions, and the 8–10 page Product Brochure backlog items the operator flagged on Sunday

These eight criteria are now the cutover gate.

---

## Outstanding work after this session (canonical list)

See `docs/MG_UNIFIED_TODO_LIST.md` for the full breakdown. Headlines:

| Track | Status |
|---|---|
| Operational DB stability | ✅ Done — PR #5 merged |
| Security S-2 (revoke leaked PAT) | 🔴 Tonight, 2 minutes |
| OpenClaw surgical removal (12 sites) | 🔴 Build day |
| CRIT-1 password purge (29 hits) | 🔴 Build day |
| CRIT-3 mg_import auth | 🔴 Build day |
| CRIT-6 catalog API hardening | 🔴 Build day |
| C4 catalog seed | 🔴 30 seconds, build day |
| N6 schema consolidation (4 → 1) | 🔴 Build day, ~2 hrs |
| C1 catalog dual-write (unsticks AI) | 🔴 4–6 hrs, must land before May 5 |
| C3 watcher rewrite to Postgres | 🔴 3–4 hrs, must land before May 5 |
| C5 operational→catalog feedback loop | 🔴 2–3 hrs, must land before May 5 |
| Orphan table drops + dead-stub deletion | 🔴 ~1 hr |
| Installer v2 rewrite (Section 7) | 🔴 4–5 hrs |
| 8 plist templates in `deploy/launchd/` | 🔴 1 hr |
| `restore_from_snapshot.sh` | 🔴 1.5 hrs |
| Sandbox install test | 🔴 1 hr |
| `DEPLOYMENT_CHECKLIST.md` rewrite | 🔴 30 min |
| Customer Setup Manual + Program Instructions + Brochure | 🔴 Backlog, before May 5 |
| Final repo housekeeping pass (operator's last request) | 🔴 May 4 |

Total estimated work to ship-ready: **roughly 35–45 hours** spread across the next 9 days. See roadmap doc for the day-by-day plan.

---

## Open questions for next session

- C1 fix path: Path A (dual-write Postgres + JSON, recommended), Path B (rewrite API to read JSON), or Path C (sync job)? Operator preference: agent's call.
- N6: which of the 4 catalog schema versions becomes canonical? (Will surface a comparison before deciding.)
- Customer brochure: tone and length — operator wants 8–10 pages with images. Need to confirm visual style (technical spec sheet vs friendlier marketing).

---

## Closing state (2026-04-26 ~5:30pm CDT)

- **VPS:** Healthy. Scan #1775 clean. 0 errors since restart.
- **Origin HEAD:** `476ef30` (PR #5 merged) + this docs PR pending
- **Active branch (this PR):** `docs/sunday-2026-04-26-session-log-and-may5-roadmap`
- **Mac Mini install date:** **2026-05-05** (locked)
- **Next working day:** Monday 2026-04-27 — Build Day #1, see roadmap

---

*"Late and perfect over early and wrong."* — Operator, 2026-04-26
