---
suggest_when:
  - signal: total_tool_calls
    value: 8
    cooldown: 60
    message: "Working without a plan? `/plan` breaks the feature into dependency-ordered tasks"
  - signal: session_start
    condition: no_plan_many_edits
    message: "Many edits with no plan — `/plan` to scope the work before continuing"
---

# /plan - Implementation Planning

Break a feature into dependency-ordered tasks with risk assessment and complexity estimates.

## Usage

```
/plan [options]
```

$ARGUMENTS

## Your Task

Create a structured implementation plan using the `planner` agent. The plan becomes the source of truth for `/iterate` and `/ai-loop`.

## Step 1: Gather Requirements

If not provided as arguments, ask:

1. **What are you building?** — Feature name and one-sentence description
2. **What problem does it solve?** — User pain point or business need
3. **What does "done" look like?** — 2-5 acceptance criteria
4. **What's out of scope?** — Boundaries to prevent scope creep

## Step 2: Analyze the Codebase

Load the `planner` agent. Before planning, understand the terrain:

1. **Grep** for related code — existing patterns, similar features
2. **Read** entry points and key files in the affected area
3. **Identify** conventions — naming, file structure, test patterns
4. **Flag** risks — external dependencies, shared state, migration needs

Report findings:

```markdown
## Codebase Analysis

**Existing patterns**: [what to follow]
**Key files**: [files that will be touched]
**Risks identified**: [potential blockers]
**Dependencies**: [external services, shared modules]
```

## Step 3: Break Into Tasks

Decompose the feature into atomic, implementable tasks:

**Task sizing rules:**
- Each task touches 1-3 files
- Each task completable in one `/iterate` cycle (~30 min)
- Each task independently verifiable
- High-risk tasks go early for faster feedback

**Task types:** Setup, API, UI, Data, Test, E2E, Refactor, Fix, Docs

For each task, define:
- **Title** — what gets done
- **Type** — category from above
- **Files** — which files are created or modified
- **Acceptance** — how to verify it works
- **Depends** — which tasks must complete first

## Step 4: Estimate Complexity

Rate overall complexity and per-task estimates:

| Complexity | Meaning | Iterations |
|------------|---------|------------|
| Low | 1-3 files, clear pattern | 1 cycle |
| Medium | 3-5 files, some decisions | 1-2 cycles |
| High | 5+ files, architectural impact | 2-3 cycles |

## Step 5: Write the Plan

Save to `docs/plans/[feature-name].md` (and `.json` for `/ai-loop`):

```markdown
# Plan: [Feature Name]

**Type**: New Feature | Improvement | Bug Fix
**Complexity**: Low | Medium | High
**Estimated iterations**: [N]
**Branch**: feature/[name]

## Problem
[One paragraph]

## Acceptance Criteria
- [ ] [Criterion 1]
- [ ] [Criterion 2]

## Risks
- [Risk 1] — mitigation: [approach]

## Tasks

### Phase 1: Foundation
- [ ] **[Type]** [Title]
  - Files: `path/to/file.ts`
  - Acceptance: [how to verify]
  - Depends: none

### Phase 2: Core
- [ ] **[Type]** [Title]
  - Files: `path/to/file.ts`
  - Acceptance: [how to verify]
  - Depends: Phase 1

### Phase 3: Polish
- [ ] **[Type]** [Title]
  - Files: `path/to/file.ts`
  - Acceptance: [how to verify]
  - Depends: Phase 2
```

## Step 6: Confirm and Create Tasks

1. Show the plan summary to the user
2. Wait for approval or revision requests
3. On approval, create Tasks via the Tasks API for each item
4. Remind user of next steps:

```markdown
## Plan Ready

**Tasks**: [N] items created
**Estimated iterations**: [N]

Next: `/iterate` (attended) or `/ai-loop` (autonomous)
```

## Arguments

| Argument | Description |
|----------|-------------|
| `--name <name>` | Feature name (skip prompt) |
| `--from-issue <url>` | Pull requirements from GitHub issue |
| `--from-prd <path>` | Convert a PRD file into a plan |
| `--improve` | Improvement mode (existing code) |
| `--debug` | Bug fix mode (root cause analysis) |
| `--minimal` | Shorter plan, fewer phases |

## Related

- **Agent**: `planner` — loaded for codebase analysis and task decomposition
- `/create-plan` — the full-featured planning command (this is the streamlined alias)
- `/iterate` — execute plan items with human review
- `/ai-loop` — autonomous plan execution

## Suggested Next

- `/iterate` — execute the plan items with human review
- `/ai-loop` — autonomous plan execution
- `/worktree` — create isolated branch for the feature work
