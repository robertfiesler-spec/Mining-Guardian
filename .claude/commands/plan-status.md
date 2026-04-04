---
suggest_when:
  - signal: edits_since_commit
    value: 8
    cooldown: 30
    message: "Editing shared files? `/plan-status` shows file claims and detects conflicts across active plans"
  - signal: session_start
    condition: incomplete_plan
    cooldown: 90
    message: "Multiple plans active? `/plan-status` checks for file ownership conflicts before you start"
---

# Plan Status

Show status of all active plans, file claims, and detect conflicts.

## Usage

```bash
/plan-status                    # Show all active plans
/plan-status --overlaps         # Check for file overlaps between plans
/plan-status --claims           # Show all file claims
/plan-status --check <plan>     # Check if starting a plan would conflict
```

## What This Does

Provides visibility into multi-agent coordination state:

1. **Active Plans**: Lists all plans with running/paused sessions
2. **File Claims**: Shows which files are claimed by which plans
3. **Overlap Detection**: Identifies when multiple plans touch the same files
4. **Conflict Warnings**: Alerts when starting a new plan would conflict

## Arguments

| Argument | Description |
|----------|-------------|
| (none) | Show summary of all active plans |
| `--overlaps` | Check for file overlaps between active plans |
| `--claims` | Show all file claims grouped by plan |
| `--check <plan>` | Check if starting `<plan>` would cause conflicts |

## Output Examples

### Default (Active Plans)

```
=== Active Plans Summary ===

1. auth-feature (running)
   Progress: 5/12 stories
   Files: 8 claimed/modified
   Branch: feature/auth-feature

2. payment-ui (paused)
   Progress: 3/8 stories
   Files: 5 claimed/modified
   Branch: feature/payment-ui

Current context: CLAUDE_PLAN=auth-feature
```

### With --overlaps

```
=== File Overlap Report ===

WARNING: The following files are claimed by multiple plans:

  src/lib/api-client.ts
    - auth-feature
    - payment-ui

  src/components/Button.tsx
    - auth-feature
    - design-system

Recommendation: Coordinate with the other plan or use
CLAUDE_ALLOW_CONFLICT=1 to proceed with caution.
```

### With --claims

```
=== File Claims ===

Total claims: 13

Plan: auth-feature
  - src/auth/login.ts
  - src/auth/session.ts
  - src/lib/api-client.ts

Plan: payment-ui
  - src/payment/checkout.tsx
  - src/payment/cart.tsx
  - src/lib/api-client.ts
```

### With --check

```bash
/plan-status --check new-feature
```

```
=== Potential Conflicts ===

Starting plan 'new-feature' may conflict with active plans:

  - src/lib/api-client.ts (claimed by auth-feature)
  - src/components/Form.tsx (claimed by payment-ui)

Options:
  1. Complete or pause the conflicting plan first
  2. Use a different branch/worktree for isolation
  3. Proceed with CLAUDE_ALLOW_CONFLICT=1 (may cause merge conflicts)
```

## Your Task

$ARGUMENTS

### Step 1: Parse Arguments

Determine which mode to run:
- No args: Show active plans summary
- `--overlaps`: Run overlap detection
- `--claims`: Show file claims
- `--check <plan>`: Check specific plan for conflicts

### Step 2: Source Helper Libraries

```bash
source .claude/scripts/lib/session-manager.sh
source .claude/scripts/lib/overlap-detector.sh
```

### Step 3: Execute Requested Report

**For default (no args)**:
1. Call `get_plans_summary`
2. Show current `CLAUDE_PLAN` context if set
3. List recent conflicts if any

**For --overlaps**:
1. Call `report_overlaps`
2. If overlaps found, suggest resolution options

**For --claims**:
1. Call `show_file_claims`
2. Show claim counts by plan

**For --check <plan>**:
1. Call `check_plan_start <plan>`
2. Report conflicts or confirm safe to proceed

### Step 4: Provide Recommendations

Based on findings:

| Situation | Recommendation |
|-----------|----------------|
| No active plans | "Run /create-plan to start a new plan" |
| One active plan | "Working on: [plan]. Run /iterate to continue" |
| Multiple plans, no conflicts | "Multiple plans active. Use CLAUDE_PLAN=<name> to switch" |
| Overlapping files | "Conflicts detected. Complete one plan before modifying shared files" |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `CLAUDE_PLAN` | Current plan context (auto-set by /loop, /iterate) |
| `CLAUDE_ALLOW_CONFLICT` | Set to "1" to allow editing conflicting files |

## Related Commands

| Command | Use |
|---------|-----|
| `/iterate` | Continue working on current plan |
| `/loop` | Start autonomous execution |
| `/create-plan` | Create a new plan |
| `/status` | Show git status and progress |

## Suggested Next

- `/iterate` — continue working on the current plan
- `/status` — git state and overall progress
- `/orchestrate` — launch multi-agent workflow across plans
