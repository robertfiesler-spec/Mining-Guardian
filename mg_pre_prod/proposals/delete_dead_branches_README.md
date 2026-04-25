# Dead-Branch Cleanup — `delete_dead_branches.ps1`

## What it does
Deletes 4 remote branches that are 0 commits ahead of `main` (verified
2026-04-25 17:48 CDT during pre-prod audit):

| Branch | Pinned SHA | Ahead | Behind |
|---|---|---|---|
| `feature/ai-learning-enhancements` | `f1b3cdc` | 0 | 394 |
| `realtime-and-observability` | `e5626c2` | 0 | 342 |
| `refactor/repo-structure` | `e46db9b` | 0 | 412 |
| `security/hardening-apr21` | `c2ca55c` | 0 | 103 |

## When to run
**AFTER** these are done:
1. Sunday 2026-04-26 typo rename (9 AM CDT)
2. CR-4 hotfix PR merged to main

Running it before then is fine technically (these branches don't block
anything), but the morning checklist groups it with post-merge cleanup.

## How to run
From PowerShell in the `Mining-Guardian` repo root on ROBS-PC:

```powershell
# 1. Dry-run first — shows what would be deleted, no changes made
.\mg_pre_prod\proposals\delete_dead_branches.ps1

# 2. If dry-run looks good, apply
.\mg_pre_prod\proposals\delete_dead_branches.ps1 -Apply
```

## Safety features
- **SHA pinning**: each branch's expected short SHA is hardcoded.
  If any branch has advanced since 2026-04-25, the script aborts
  with exit code 2 and refuses to delete anything.
- **Dry-run by default**: must pass `-Apply` to actually delete.
- **Auth check**: aborts immediately if `gh` CLI is not authenticated.
- **Per-branch error handling**: a failure on one branch doesn't stop
  the others; final exit code reflects partial failures (exit 3).

## Exit codes
- `0` — success (or dry-run completed cleanly)
- `1` — gh auth not configured
- `2` — SHA drift detected, aborted before any delete
- `3` — one or more deletes failed in apply mode

## What it does NOT do
- Does not touch local branches (only remote refs on GitHub).
- Does not touch any branch with commits ahead of main.
- Does not touch `feature/intelligence-catalog`, `installer-build`, or
  `feature/fast-cohort-analysis` — those need the consolidation plan
  (`branch_consolidation_plan_2026-04-25.md`), not deletion.

## Recovery
If you delete by mistake, GitHub keeps the commits reachable for ~90
days. To restore:
```
gh api -X POST repos/robertfiesler-spec/Mining-Guardian/git/refs \
  -f ref=refs/heads/<branch-name> -f sha=<full-sha-from-table-above>
```
Use the full 40-char SHA, not the short SHA shown in the table.
