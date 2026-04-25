# Audit Branch ↔ Main Divergence Triage — 2026-04-25

**Question:** After Sunday's typo rename + CR-4 merge, do any of the 36 commits
unique to `pre-prod-audit-2026-04-25` need to land on `main`?

**TL;DR:** Most don't. Three categories below — copy this list into your "next
session" backlog.

## Branch state

- `origin/main` @ `b28c8a7` — production line, 212 commits ahead of audit branch's fork point
- `pre-prod-audit-2026-04-25` @ `0ff5140` — 36 commits ahead of main, 212 commits behind
- These are NOT a linear lineage. They diverged. Many audit-branch additions were
  later **superseded** by parallel work on main (this is why `intelligence-catalog/`
  shows 46 diffs with deletions in both directions).

## Category A — KEEP on audit branch only (don't merge to main)

These are pre-prod planning artifacts. They never belong on the production line.

| Commits | What |
|---|---|
| 0ff5140, 865a017, f682ac1, d979804, 2b19f26, fe08923, cc6dbd0, 8c5440f, cd85d37, 94070a6 | All `mg_pre_prod/proposals/*` — runbooks, finding docs, hotfix patcher script, morning checklist |

**Action:** Leave on audit branch indefinitely as the historical record of the
pre-prod hardening session.

## Category B — ALREADY ON MAIN via different commits (don't re-merge)

These were ported to main (or done independently on main) by parallel work.

| Audit commit | Topic | Main equivalent (verify before discarding) |
|---|---|---|
| 0089ed6, e0b5b1a, e49f45b, 530466e, 5823921 | mg_import_tool initial + features | Main has `mg_import_tool/` (19 files) — likely a divergent newer version. Diff before assuming. |
| 0a37f94, bdca6e5 | Intelligence Catalog importer | Main has `intelligence-catalog/importer/` already (Cat-A diff shows main version is fuller). |
| 2d3a7a3 | OpenClaw catalog bridge | Main `deploy/openclaw-skills/` matches audit (0 file diff). Already merged or redundant. |
| 8059d1b, 36d0656, 1ba973e, 58a7e3e | DB password purge (crit-1a/b/c) | **VERIFY ON MAIN** — if main still has hardcoded passwords, this MUST be ported. |
| db47293, 57ccbfb, 8b6e66c | Deep research CSVs + enrichment SQL | Main has `intelligence-catalog/research/` and `seed-data/` — diff to verify. |
| 7189a44, 2433bfe, b61ea49, 0d77ede, 1e88f40 | Schema fixes + deploy.ps1 fixes | Likely on main; verify. |
| cc829e2, 9afff68, 58be898, 71675a5 | Doc updates (README, AI_ROADMAP, SESSION_LOG) | Main has progressed further on these. Audit version is stale. Discard. |
| f18ad86 | gitignore | Trivial; main may already have equivalent. |

**Action item for next session:**
> **CONFIRMED:** main STILL has hardcoded password fallbacks. The audit branch's
> crit-1a/b/c commits (8059d1b, 36d0656, 1ba973e, 58a7e3e) **never landed on main**.
>
> Specifically on main:
> - `intelligence-catalog/catalog-api/catalog_api.py:45` — `DB_PASSWORD = os.getenv("DB_PASSWORD", "MiningGuardian2026!")`
> - `mg_import_tool/mg_import.py` — 5+ sites with `password=conn_params.get('password', 'MiningGuardian2026!')`
>
> **CRITICAL:** the GitHub repo is PUBLIC. The string `MiningGuardian2026!`
> is fully exposed at `https://github.com/robertfiesler-spec/Mining-Guardian/blob/main/intelligence-catalog/catalog-api/catalog_api.py#L45`
> (and 5+ places in `mg_import_tool/mg_import.py`).
>
> **Required actions (in order, NOT today — too risky to bundle with rename + CR-4):**
> 1. Rotate the actual production DB password on the VPS Postgres instance
>    (whatever `MiningGuardian2026!` was used for is compromised regardless of patch).
> 2. Update VPS service env files / systemd Environment= directives with the new password.
> 3. Restart all 8 services with new env.
> 4. Then port the password-purge code changes from audit branch to main as CR-7.
> 5. Optionally make the repo private until rotation is complete.

## Category C — UNIQUE TO AUDIT BRANCH, may need port to main

Real code that exists only on the audit branch and isn't on main.

### C1. CR-2 hashrate fix (commit 9e705f7)
- **What:** `_parse_hashrate_pct` helper + 3 site replacements at audit-branch
  lines 4108/4413/4475 in `core/mining_guardian.py`.
- **Status on main:** Audit branch's `mining_guardian.py` is 5500+ lines; main is
  2473 lines. The line numbers don't translate. The bug (ValueError on `'N/A'`
  and `'80.5%'` strings) likely exists on main but at different sites.
- **Recommendation:** Already on Rob's deferred list (locked decision: corner-case,
  low priority). Translate line numbers in a future CR-6 hotfix.

### C2. catalog-bridge integration_example.py / prompt_builder.py
- These were committed in 2d3a7a3 but the diff with main shows 0 file delta
  for `deploy/openclaw-skills/`. Means main HAS the same files. **Already merged.** Discard.

### C3. mg_import_tool tests (commit e49f45b)
- Audit branch added `mg_import_tool/tests/test_*.py` — 9 test files.
- **Status on main:** Likely missing on main (main has only 19 files in
  `mg_import_tool/` and audit's tests/ alone is 9 files).
- **Recommendation:** If Rob still uses mg_import_tool, port the tests. If the
  catalog-api on main has its own tests, skip.

## Category D — DELETIONS on audit branch (do NOT propagate)

Audit branch deleted files that main still has. Keep main's versions.

| Deleted on audit | Why kept on main |
|---|---|
| `intelligence-catalog/FIELD_INTELLIGENCE_PIPELINE.md` | Doc — main may still reference it |
| `intelligence-catalog/LIVING_CATALOG.md` | Doc |
| `intelligence-catalog/data/*.json` and `*.csv` (6 files) | Reference data still in use by importer on main |
| `mg_import_tool/sql/migrations/000_bootstrap_field_log_tables.sql` | Bootstrap migration |

**Action:** Do nothing. These would be re-deletions if merged; main is correct as-is.

## Category E — `core/mining_guardian.py` itself

3,726 insertions / 307 deletions between branches. **This is by far the biggest
divergence.** Audit branch's mining_guardian.py is essentially a different file
from main's.

- Main is what's running in production.
- Audit branch's version was a parallel evolution that never landed.
- CR-4 hotfix targets MAIN's version — that's the canonical line going forward.
- **Recommendation:** Treat audit branch's `core/mining_guardian.py` as archival
  research. Do NOT attempt to merge it. Future fixes go to main.

## Decision summary

| Action | When |
|---|---|
| Audit branch stays alive as historical record | Indefinite |
| Verify password-purge commits made it to main (security) | This week |
| Port mg_import_tool tests if used | When Rob next touches mg_import |
| Translate CR-2 line numbers for main hotfix | Already on backlog (low priority) |
| Treat audit's `mining_guardian.py` as archive | Permanent — main is the line |
| Don't merge audit branch into main | Period |

## Open question for Rob

> Is `mg_import_tool/` something you still actively use? If yes, the tests in
> commit `e49f45b` are worth porting. If you've moved on to using
> `intelligence-catalog/importer/` instead, skip it.
