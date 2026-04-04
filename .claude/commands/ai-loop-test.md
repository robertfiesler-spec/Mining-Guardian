---
suggest_when:
  - signal: file_extension
    value: ".sh"
    min_edits: 2
    cooldown: 30
    message: "Modified loop scripts? `/ai-loop-test` validates shell plumbing without any AI calls or network access"
  - signal: session_start
    condition: uncommitted_changes
    cooldown: 60
    message: "Changes to loop infrastructure? `/ai-loop-test` sanity-checks it before merging"
---

# AI Loop Test (Infrastructure Sanity Check)

Validates loop infrastructure before merging changes. Runs shell-level tests with no AI calls, no network access, and no plan required.

## Cost Optimization

**Recommended Model**: `haiku`
This command just runs a shell script and reports output — no complex reasoning needed.

## What This Tests

| Test | What It Checks |
|------|----------------|
| jq available | jq is installed and parses JSON correctly |
| No flag leak | Sourcing ai-provider.sh does not tighten caller's shell options |
| Provider resolve | claude or codex binary is found on PATH |
| find_prd | Most-recent .json in docs/plans/ is located |
| next_story | Correct story is extracted from fixture plan |
| all_complete (false) | Incomplete plan is detected correctly |
| all_complete (true) | Completed plan is detected correctly |
| count_stories | Returns "N/M" format |
| Session init | init_plan_session creates correct file structure |

## Your Task

$ARGUMENTS

Run the loop infrastructure test suite:

```bash
bash .claude/scripts/loop-test.sh
```

Report the results:

- If all tests pass: confirm it is safe to proceed
- If any tests fail: show the failure output and suggest fixes

## Exit Codes

- `0` — All tests passed. Safe to proceed.
- `1` — One or more tests failed. Do NOT merge until fixed.

## When to Run

Run `/ai-loop-test` before merging any changes to:
- `scripts/loop.sh`
- `scripts/lib/ai-provider.sh`
- `scripts/lib/session-manager.sh`
- `scripts/lib/acs-client.sh`

## Related Commands

| Command | Purpose |
|---------|---------|
| `/ai-loop` | Run the actual autonomous loop |
| `/verify` | Code lint/typecheck/test verification |
| `/pre-commit-check` | Full pre-commit validation |

## Suggested Next

- `/ai-loop` — run the actual autonomous loop once infrastructure is verified
- `/verify` — lightweight code verification (lint, typecheck, tests)
- `/pre-commit-check` — full pre-commit validation before merging loop changes
