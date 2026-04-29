# Stale Branches Retained for Post-Install Review (2026-04-29)

During the install-day prep stale-branch triage, 19 branches whose PRs had been
merged into `main` were deleted. Three branches were **retained** because they
had unique commits that were never opened as a PR — deleting them would risk
losing in-flight work.

## Retained branches

### 1. `feature/fast-cohort-analysis`
- **Last commit:** 2026-04-19 16:23 UTC
- **Ahead of main:** 2 commits
- **Behind main:** 241 commits
- **Last commit message:** "docs: Complete session log Apr 19 + operator review"
- **Likely contents:** Apr 19 session log + operator review notes (3 approved
  patterns: HEALTHY_BASELINE_S19JPRO, PSU Signal 6, HIGH_OFFLINE_FREQUENCY_PATTERN).
- **Recommended action:** Cherry-pick the session log + operator-review notes
  into `docs/` if not already captured elsewhere, then delete.

### 2. `feature/intelligence-catalog`
- **Last commit:** 2026-04-25 19:02 UTC
- **Ahead of main:** 21 commits
- **Behind main:** 333 commits
- **Last commit message:** "chore: gitignore in-flight backups + sql patch staging"
- **Likely contents:** Early intelligence-catalog work prior to the canonical
  `intelligence-catalog/` directory landing on main. The `intelligence/` directory
  removed in PR Bucket 7.1 was the *deprecated duplicate* of this. Worth
  diffing the 21 unique commits against current `intelligence-catalog/` to
  confirm nothing valuable is stranded.
- **Recommended action:** Audit the 21 unique commits post-install, salvage
  anything novel (likely none — superseded), then delete.

### 3. `pre-prod-audit-2026-04-25`
- **Last commit:** 2026-04-26 18:41 UTC
- **Ahead of main:** 47 commits
- **Behind main:** 333 commits
- **Last commit message:** "cr-6 patch: re-pin SHA to main @ 2e8a1e0 (post-CR-4)"
- **Likely contents:** Pre-prod audit work — CR (code-review) patch series
  CR-2 through CR-6. CR-2 through CR-5 already landed via merged PRs #1-#5
  (the hotfix branches we deleted). CR-6 may not have shipped — worth
  confirming before deletion.
- **Recommended action:** Verify CR-6 status (search commits for "cr-6"
  in main). If CR-6 landed, safe to delete. If not, cherry-pick the CR-6
  patch then delete.

## Why retained

Per the user's standing rule "I would rather be late and perfect than early
and wrong," these were not deleted in the automated triage. The user can
review post-install when there is time to audit each branch's unique commits
without install-day pressure.

## Triage tally

- **Total remote branches before triage:** 21 (excluding `main`)
- **Deleted (PR merged):** 18
- **Deleted (no-PR but fully merged):** 1 (`openclaw-integration`, 0 ahead)
- **Retained for review:** 3 (this file)
- **Final stale-branch count:** 3 + `main` = 4

## Generated

- 2026-04-29 21:18 UTC, by Computer (install-day prep cascade)
