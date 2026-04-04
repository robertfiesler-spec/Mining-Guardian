---
suggest_when:
  - signal: session_start
    condition: no_plan_many_edits
    message: "No active plan — `/create-plan` structures your work into trackable stories"
---
# Feature / Improve / Debug Plan

Create a structured implementation plan for new features, improvements, or bug fixes.

## Your Task

Guide the user through defining work and create a Plan with an actionable checklist. The flow adapts based on the type of work.

$ARGUMENTS

## Step 0: Enter Plan Mode

**REQUIRED**: Before doing anything else, enter plan mode to prevent accidental code changes during planning.

> Call the `EnterPlanMode` tool now and wait for user approval.

Plan mode ensures:

- You can explore the codebase (Glob, Grep, Read)
- You cannot accidentally edit files (Edit, Write disabled)
- User must approve the plan before implementation begins

Once in plan mode, proceed to Step 0.5.

## Step 0.5: Check for Active Plan Conflicts (Multi-Agent)

Before creating a new plan, check if it would conflict with active plans.

**If other plans are active**, check for potential file overlaps:

```bash
# Source overlap detection
source .claude/scripts/lib/overlap-detector.sh

# List active plans
get_active_plans

# If files are known, check for conflicts
check_plan_start "new-plan-name"
```

**If conflicts detected**:

```markdown
## Potential Conflict Warning

There are active plans that may conflict with this new plan:

**Active Plans:**
- `auth-feature` (running, 5/12 complete)
- `payment-ui` (paused, 3/8 complete)

**Potentially Shared Files:**
- `src/lib/api-client.ts` (claimed by auth-feature)

**Options:**
1. **Proceed anyway** - Create plan, but be aware of potential merge conflicts
2. **Complete active plan first** - Run `/iterate` on existing plan
3. **Use different files** - Design around the conflict

Would you like to proceed with creating this plan?
```

**If no conflicts or user proceeds**: Continue to Step 1.

**Note**: This check requires the plan's files to be identified. For new features where files aren't known yet, the check happens after the plan is created (before execution).

## Step 1: Determine Work Type

Check arguments or ask the user:

**If `--enrich [path]` argument**: Enrich existing plan with reuse annotations (skip to MODE: Enrich)
**If `--from-prd [path]` argument**: Load existing PRD mode (skip to MODE: From PRD)
**If `--improve` argument**: Improvement mode
**If `--debug` argument**: Debug mode
**Otherwise**: Ask:

"What type of work is this?

1. **New Feature** - Building something that doesn't exist yet
2. **Improvement** - Enhancing existing functionality
3. **Debug/Fix** - Fixing a bug or issue"

---

## Refinement Interview (All Modes)

After gathering initial answers (in any mode), DO NOT immediately generate the plan. First, run a refinement interview to surface gaps and sharpen the spec. This produces dramatically better plans.

### How the Refinement Works

1. **Review the answers** the user gave to the initial questions
2. **Identify gaps** — vague descriptions, missing edge cases, unstated assumptions, unclear scope boundaries, ambiguous acceptance criteria
3. **Ask 3-5 targeted follow-up questions** that probe the weakest areas. Examples:
   - "You mentioned [X] — how should it behave when [edge case]?"
   - "What happens if [failure scenario]? Should it retry, show an error, or fail silently?"
   - "You said 'users can do X' — which users? All authenticated users, or specific roles?"
   - "Is [Y] a hard requirement for v1, or could it be a fast-follow?"
   - "How does this interact with [existing feature Z]? Should they share state?"
   - "What's the expected data volume? This affects whether we need pagination/streaming."
   - "Are there existing components, hooks, or utilities in this codebase that should be reused or extended rather than rebuilt?"
   - "Should any part of this feature look or behave identically to an existing page or component? If so, which one?"
   - "Are there constraints on what must NOT be recreated from scratch?"

**Reuse gap check (mandatory)**: If the codebase analysis found reuse candidates, or if the feature involves UI, API routes, hooks, or utilities that resemble existing ones, you MUST ask about reuse intent. Do not skip this even if other questions seem sufficient.
4. **Incorporate the answers** into your mental model before generating the plan
5. **Repeat if needed** — if answers reveal further ambiguity, ask one more round (max 2 rounds total). Don't over-interview; 1-2 rounds is the sweet spot.

### When to Skip Refinement

Skip the refinement interview ONLY when:
- User passed `--minimal` flag (they explicitly want less ceremony)
- User passed `--from-prd` with a detailed PRD (the spec already exists)
- User explicitly says "just generate it" or "skip questions"

In all other cases, the refinement interview is mandatory.

---

## MODE: New Feature (default)

### Gather Information

Ask:

1. **Feature Name**: What should this feature be called?
2. **Problem Statement**: What problem does this solve?
3. **Proposed Solution**: How should it work?
4. **Acceptance Criteria**: How do we know it's done?
5. **Out of Scope**: What are we NOT doing?

### Refine (REQUIRED)

After the user answers the 5 questions above, run the **Refinement Interview** (see section above) before proceeding. Do not skip this step.

### Analyze Codebase

- Identify where new code will live
- Note patterns to follow
- Flag dependencies
- **Search for reusable code**: Before planning any new components, hooks, utilities, or patterns, search for existing similar code in the codebase. For each match found, record it as a reuse candidate:
  - `path`: file path of existing code
  - `what`: what's reusable (e.g., "Modal layout and form validation")
  - `how`: one of `import` (use directly), `extend` (wrap/inherit), `copy-and-adapt` (fork and modify), `follow-pattern` (use as structural reference)

Report findings: "Found [N] reuse candidates: [summary]. These will be included in the plan as mandatory references."

### Create and Save Plan

**IMPORTANT**: Create the plan using the template below, then **save it to `docs/plans/[feature-name].md`** using the Write tool. Do not just display it - it must be persisted to a file.

Use this template:

```markdown
# Plan: [Feature Name]

**Type**: New Feature
**Status**: In Progress
**Created**: [date]
**Branch**: [branch name]

## Problem Statement

[What problem this feature solves]

## Proposed Solution

[How the feature will work]

## Acceptance Criteria

- [ ] [Criterion 1]
- [ ] [Criterion 2]
- [ ] [Criterion 3]

## Out of Scope

- [What we're NOT doing]

## Technical Approach

[Where new code will live, patterns to follow, dependencies]

**Key Files:**

- `path/to/file.ts` - [purpose]
- `path/to/file.ts` - [purpose]

## Reuse Map

_Include this section when reuse candidates were identified during codebase analysis. Omit if none found._

| Source | What to Reuse | How |
|--------|---------------|-----|
| `path/to/existing-component.tsx` | [Component layout, state management] | copy-and-adapt |
| `hooks/use-existing.ts` | [Hook logic] | import |

## Constraints

_Include explicit directives about what must NOT be recreated. Each constraint is injected into `/ai-loop` iterations._

- DO NOT recreate [component/hook] from scratch — extend existing `path/to/file.ts`
- DO NOT build custom [pattern] — use existing `path/to/utility.ts`
- [Additional constraints from user interview]

---

## Implementation Checklist

### Phase 1: Setup

- [ ] **Setup** [Task description]
  - Files: `path/to/file.ts`
  - Test: [How to verify]

### Phase 2: Core Implementation

- [ ] **Core** [Task description]
  - Files: `path/to/file.ts`
  - Test: [How to verify]

### Phase 3: UI (if applicable)

- [ ] **UI** [Task description]
  - Files: `path/to/component.tsx`
  - Test: [How to verify]

### Phase 4: Testing

- [ ] **Test** Add unit tests
  - Files: `__tests__/...`
  - Test: Coverage maintained or improved

---

## Progress Log

| Date | Item | Commit | Notes |
| ---- | ---- | ------ | ----- |
|      |      |        |       |

---

_Generated by `/create-plan`. Execute with `/iterate`._
```

---

## MODE: Improvement (`--improve`)

### Gather Information

Ask:

1. **Area to Improve**: Which part of the codebase? (file, module, feature name)
2. **Current Behavior**: How does it work now?
3. **Desired Behavior**: How should it work after improvement?
4. **Why Improve**: Performance? Maintainability? UX? Security?
5. **Constraints**: What must NOT change? (APIs, behavior, etc.)

### Refine (REQUIRED)

After the user answers the 5 questions above, run the **Refinement Interview** (see section above) before proceeding. Do not skip this step.

### Analyze Existing Code

**CRITICAL**: Before creating the checklist, thoroughly read the existing code:

```bash
# Find relevant files
grep -r "keyword" --include="*.ts" --include="*.tsx" -l
```

- Read ALL files in the area being improved
- Understand current architecture
- Identify dependencies and side effects
- Note test coverage
- **Search for reusable code**: Look for existing components, hooks, utilities, or patterns that overlap with the improvement. Record reuse candidates with `{path, what, how}` for inclusion in plan stories.

Share: "I've reviewed [X files]. Current architecture is [summary]. Key dependencies are [list]. Found [N] reuse candidates."

### Create and Save Plan

**IMPORTANT**: Create the plan using the template below, then **save it to `docs/plans/improve-[area-name].md`** using the Write tool.

```markdown
# Plan: Improve [Area Name]

**Type**: Improvement
**Status**: In Progress
**Created**: [date]
**Branch**: [current branch name]

## Current State

[Description of how it currently works, with file references]

**Key Files:**

- `path/to/file.ts` - [purpose]
- `path/to/file.ts` - [purpose]

## Desired State

[Description of how it should work after improvement]

## Why This Improvement

- [Reason 1: e.g., "Performance: current implementation is O(n²)"]
- [Reason 2: e.g., "Maintainability: logic is spread across 5 files"]

## Reuse Map

_Existing code identified during analysis that must be reused or extended._

| Source | What to Reuse | How |
|--------|---------------|-----|
| `path/to/existing.ts` | [What's reusable] | extend |

## Constraints (Do Not Change)

- [ ] Public API must remain compatible
- [ ] Existing tests must pass
- [ ] DO NOT recreate [component/pattern] — extend existing implementation
- [ ] [Other constraints]

## Technical Approach

[How you'll make the improvement - refactor strategy, new patterns, etc.]

---

## Implementation Checklist

### Phase 1: Preparation

- [ ] **Test** Add tests for current behavior (safety net)
  - Files: `__tests__/...`
  - Test: Captures current behavior

### Phase 2: Refactor

- [ ] **Refactor** [Specific change]
  - Files: `path/to/file.ts`
  - Test: Existing tests still pass

### Phase 3: Enhance

- [ ] **Core** [The actual improvement]
  - Files: `path/to/file.ts`
  - Test: [How to verify improvement]

### Phase 4: Cleanup

- [ ] **Cleanup** Remove deprecated code
  - Files: [files]
  - Test: No dead code, tests pass

- [ ] **Test** Add tests for new behavior
  - Files: `__tests__/...`
  - Test: Coverage maintained or improved

---

## Progress Log

| Date | Item | Commit | Notes |
| ---- | ---- | ------ | ----- |
|      |      |        |       |

---

_Generated by `/create-plan --improve`. Execute with `/iterate` or `/ai-loop`._
```

---

## MODE: Debug (`--debug`)

### Gather Information

Ask:

1. **Issue Description**: What's the bug or problem?
2. **Reproduction Steps**: How do you trigger it?
3. **Expected Behavior**: What should happen?
4. **Actual Behavior**: What happens instead?
5. **Error Messages**: Any errors, stack traces, logs?
6. **When It Started**: Recent change? Always been broken?

### Refine (REQUIRED)

After the user answers the 6 questions above, run the **Refinement Interview** (see section above) before proceeding. Do not skip this step.

### Investigate

**CRITICAL**: Before creating the checklist, investigate the bug:

1. **Reproduce**: Try to reproduce the issue
2. **Trace**: Find where in the code the issue occurs
3. **Identify Root Cause**: Why is it happening?
4. **Consider Side Effects**: What else might be affected?

Share: "I've traced the issue to [location]. Root cause appears to be [explanation]."

### Create and Save Plan

**IMPORTANT**: Create the plan using the template below, then **save it to `docs/plans/fix-[issue-name].md`** using the Write tool.

```markdown
# Plan: Fix [Brief Issue Description]

**Type**: Bug Fix
**Status**: In Progress
**Created**: [date]
**Branch**: [current branch name]
**Related Issue**: [GitHub issue URL if any]

## Bug Description

**Reported Behavior**: [What's wrong]

**Reproduction Steps**:

1. [Step 1]
2. [Step 2]
3. [Observe: bug occurs]

**Expected Behavior**: [What should happen]

**Error Output**:
```

[Error message or stack trace if any]

```

## Investigation

### Root Cause

[Explanation of why the bug occurs]

**Location**: `path/to/file.ts:123`

### Contributing Factors

- [Factor 1]
- [Factor 2]

### Affected Areas

- `path/to/file.ts` - [how it's affected]
- `path/to/other.ts` - [how it's affected]

## Fix Approach

[How you'll fix it]

**Risk Assessment**: [Low/Medium/High] - [explanation]

---

## Implementation Checklist

### Phase 1: Reproduce & Test
- [ ] **Test** Add failing test that reproduces bug
  - Files: `__tests__/...`
  - Test: Test fails, proving bug exists

### Phase 2: Fix
- [ ] **Fix** [The actual fix]
  - Files: `path/to/file.ts`
  - Test: Failing test now passes

### Phase 3: Verify
- [ ] **Test** Verify no regression
  - Files: `__tests__/...`
  - Test: All existing tests pass

- [ ] **Test** Add edge case tests
  - Files: `__tests__/...`
  - Test: Similar bugs prevented

---

## Progress Log

| Date | Item | Commit | Notes |
|------|------|--------|-------|
| | | | |

---

_Generated by `/create-plan --debug`. Execute with `/iterate` or `/ai-loop`._
```

---

## MODE: From PRD (`--from-prd`)

Load and review an existing PRD file instead of creating a new one. Supports both JSON PRDs (machine-readable) and Markdown PRDs (human-readable).

### Usage

```bash
# JSON PRD (existing format)
/create-plan --from-prd docs/plans/my-app.json

# Markdown PRD (human-readable - will be converted)
/create-plan --from-prd examples/prd/prd.md
/create-plan --from-prd docs/requirements/feature-spec.md
```

### Step 1: Detect File Type and Load

1. Read the PRD file from the specified path
2. **Detect file type based on extension:**
   - `.json` → Continue with JSON validation flow (Step 1a)
   - `.md` → Convert to JSON first (Step 1b)

#### Step 1a: JSON PRD Flow

1. Validate against the schema (`schemas/prd.schema.json`)
2. If validation fails, report errors and ask user how to proceed
3. Continue to Step 2 (Display PRD Summary)

#### Step 1b: Markdown PRD Conversion Flow

For markdown files, analyze and convert to JSON PRD format:

**1. Read and Analyze Markdown Content**

Parse the markdown file to identify:

- **Feature name**: From title, first `#` heading, or "Overview" section
- **Components/modules**: Tables, sections describing system parts
- **Workflow steps**: Numbered lists, "Step X" sections, sequence descriptions
- **MVP scope**: "In Scope" sections, bullet lists of requirements
- **Technical requirements**: Architecture sections, code blocks, integration details
- **Success criteria**: Metrics, acceptance conditions, "How do we know it's done"

**2. Extract and Generate Stories**

Create stories from the markdown content with these mappings:

| Markdown Element                           | Story Field  |
| ------------------------------------------ | ------------ |
| Section heading / requirement bullet       | `title`      |
| Content type (UI, API, Data references)    | `type`       |
| Order in document / dependencies mentioned | `priority`   |
| File paths, component names mentioned      | `files`      |
| Success criteria, checkpoints, "must have" | `acceptance` |
| "depends on", "after", "requires" language | `depends`    |

**Story ID Generation:** Auto-generate as `US-1`, `US-2`, etc.

**Type Inference Rules:**

- "setup", "install", "scaffold", "create project" → `Setup`
- "endpoint", "route", "server", "backend" → `API`
- "component", "page", "form", "button", "UI" → `UI`
- "database", "schema", "model", "migration" → `Data`
- "test", "coverage", "spec" → `Test`
- "e2e", "playwright", "integration test" → `E2E`
- "refactor", "cleanup", "restructure" → `Refactor`
- "fix", "bug", "issue" → `Fix`
- "docs", "readme", "documentation" → `Docs`

**3. Show Conversion Preview**

Display the extracted stories for user review:

```markdown
## Markdown PRD Conversion Preview

**Source:** examples/prd/prd.md
**Detected Feature:** ai-content-factory
**Stories Extracted:** 12

| ID   | Title                       | Type  | Priority | Files (inferred)          |
| ---- | --------------------------- | ----- | -------- | ------------------------- |
| US-1 | Project setup with Next.js  | Setup | 1        | package.json, next.config |
| US-2 | Database schema design      | Data  | 2        | prisma/schema.prisma      |
| US-3 | Campaign brief API endpoint | API   | 3        | src/api/campaigns/        |
| ...  | ...                         | ...   | ...      | ...                       |

**Note:** Stories were inferred from your markdown. Review and adjust before proceeding.
```

**4. User Review and Edit**

Ask the user:

"I've converted your markdown PRD to 12 stories. What would you like to do?

1. **Accept and continue** - Proceed with these stories
2. **Review in detail** - Show full story breakdown with acceptance criteria
3. **Modify stories** - Add, remove, or edit before saving
4. **Regenerate** - Try again with different interpretation"

**5. Generate JSON PRD**

Once confirmed, generate the JSON file:

- Save to `docs/plans/{feature-name}.json`
- Include `source` field pointing to original markdown
- Set all stories to `passes: false`
- Set `status: "planning"`

```json
{
  "feature": "ai-content-factory",
  "branch": "feature/ai-content-factory",
  "status": "planning",
  "created": "2025-01-18T12:00:00Z",
  "source": "examples/prd/prd.md",
  "stories": [
    {
      "id": "US-1",
      "title": "Project setup with Next.js",
      "type": "Setup",
      "priority": 1,
      "passes": false,
      "files": ["package.json", "next.config.js", "tsconfig.json"],
      "acceptance": "Project builds and runs with npm run dev"
    }
    // ... more stories
  ]
}
```

**6. Create Tasks for Plan Items**

After saving the JSON file, create Tasks using the Tasks API for persistent tracking:

```typescript
// For each story in the generated plan where passes: false:
TaskCreate({
  subject: `${story.id}: ${story.title}`, // e.g., "US-1: Project setup with Next.js"
  description: story.acceptance, // Full acceptance criteria
  activeForm: `Implementing ${story.title}`, // Shown during execution
  metadata: {
    planPath: `docs/plans/${feature}.json`, // Link back to plan file
    itemId: story.id, // Story ID for tracking
    storyType: story.type, // Setup, Core, UI, etc.
  },
});
```

Use `TaskCreate` for each story where `passes: false`. Tasks created this way:

- Persist across sessions automatically
- Show up in `/tasks` command
- Can be tracked by `/iterate` and `/ai-loop`

**7. Continue to Standard Flow**

After JSON is generated and Tasks are created, continue to Step 2 (Display PRD Summary).

### Step 2: Display PRD Summary

Show the user:

```markdown
## PRD Loaded: [feature name]

**Status**: [status]
**Branch**: [branch]
**Created**: [date]

### Stories Overview

| ID   | Title   | Type   | Priority | Status      |
| ---- | ------- | ------ | -------- | ----------- |
| US-1 | [title] | [type] | 1        | ✅ Complete |
| US-2 | [title] | [type] | 2        | ⏳ Pending  |
| ...  | ...     | ...    | ...      | ...         |

**Progress**: X/Y stories complete (Z%)

### Pending Stories (by priority)

1. **US-2**: [title] - [type]
   - Files: [files]
   - Depends on: [dependencies]

2. **US-3**: [title] - [type]
   - Files: [files]
```

### Step 3: Review Options

Ask the user:

"PRD loaded successfully. What would you like to do?

1. **Start execution** - Begin with `/ai-loop` or `/iterate`
2. **Review stories** - Show detailed breakdown of each story
3. **Modify PRD** - Add, remove, or edit stories
4. **Validate dependencies** - Check story dependency graph
5. **Reset progress** - Mark all stories as incomplete"

### Step 4: Branch Setup

Check if the branch exists:

```bash
git branch --list [branch-name]
```

- If branch exists: Ask to switch to it
- If branch doesn't exist: Ask to create it
- If already on correct branch: Confirm and proceed

### Step 5: Ready for Execution

Once confirmed:

1. Copy PRD to `docs/plans/` if not already there
2. Ensure Tasks were created for all pending stories (via TaskCreate in Step 6)
3. Exit plan mode with `ExitPlanMode`
4. Remind user of next steps:

```markdown
PRD ready for execution.

**Tasks created:** [N] stories synced to Claude Code Tasks

**Next steps:**

- `/ai-loop --max 50` - Autonomous execution (recommended for large PRDs)
- `/iterate` - Human-in-the-loop execution

**Monitor progress:**

- Tasks persist across sessions automatically
- `tail -f .claude/state/progress.txt`
- `cat docs/plans/[feature].json | jq '.stories[] | select(.passes == false)'`
```

### Full Application PRDs

The loop can process PRDs of any size - from single features to entire applications. For large PRDs:

- Stories are processed by `priority` (1 = first)
- `depends` array ensures correct ordering
- Each story gets a fresh Claude instance (no context overflow)
- Progress persists in `prd.json` - safe to stop and resume

**Example: Full app PRD structure**

```json
{
  "feature": "my-saas-app",
  "stories": [
    {
      "id": "US-1",
      "title": "Project setup",
      "type": "Setup",
      "priority": 1,
      "passes": false
    },
    {
      "id": "US-2",
      "title": "Database schema",
      "type": "Data",
      "priority": 2,
      "depends": ["US-1"],
      "passes": false
    },
    {
      "id": "US-3",
      "title": "Auth API",
      "type": "API",
      "priority": 3,
      "depends": ["US-2"],
      "passes": false
    },
    {
      "id": "US-4",
      "title": "Login UI",
      "type": "UI",
      "priority": 4,
      "depends": ["US-3"],
      "passes": false
    }
    // ... 50+ more stories
  ]
}
```

Run `/ai-loop --max 100` and it processes the entire application.

### Writing Effective Markdown PRDs

For best conversion results, structure your markdown PRD with these elements:

**1. Clear Feature Title**

```markdown
# Feature Name — Product Requirements Document
```

The first `#` heading is used as the feature name (converted to kebab-case for the branch).

**2. Structured Sections**
Include clear sections that map to implementation areas:

- `## Overview` - What the feature does
- `## Core Components` - Tables or lists of system parts
- `## User Workflow` - Numbered steps (become stories)
- `## MVP Scope` - "In Scope" / "Out of Scope" lists
- `## Technical Architecture` - Files, integrations, patterns

**3. Actionable Requirements**
Write requirements as actionable items:

```markdown
### In Scope

- Single brand identity ← Becomes: "Setup single brand configuration"
- Manual campaign initiation ← Becomes: "UI: Campaign creation form"
- Full human approval at each stage ← Becomes: "UI: Review queue with approve/reject"
```

**4. Technical Details**
Include file paths and component names when possible:

```markdown
**Key Technical Considerations:**

1. **Manus as Browser Agent** - Stored credentials (secure vault)...
```

These help infer the `files` array for each story.

**5. Success Criteria**
Define what "done" looks like:

```markdown
## Success Metrics

- **Throughput:** 5 videos per day
- **Cycle Time:** < 4 hours brief to export
```

These become `acceptance` criteria for stories.

**6. Workflow Dependencies**
Use sequencing language to establish dependencies:

```markdown
### Step 1: Campaign Brief

...

### Step 2: Research Phase (after Step 1)

...

### Step 4: Asset Generation (requires approved concepts)
```

"after", "requires", "depends on" create the `depends` array.

**Example Structure (AI Content Factory)**

```markdown
# AI Content Factory — PRD

## Overview

[What it does, target output]

## Core Components

| Component | Role             | Integration      |
| --------- | ---------------- | ---------------- |
| Veo       | Video generation | Google Cloud API |

## User Workflow

### Step 1: Campaign Brief

### Step 2: Research Phase

### Step 3: Creative Strategy

...

## MVP Scope

### In Scope

- Feature 1
- Feature 2

### Out of Scope

- Future feature

## Technical Architecture

[Diagram, key considerations]

## Success Metrics

[Measurable criteria]
```

---

---

## MODE: Enrich (`--enrich`)

Retrofit an existing plan with reuse and constraint annotations. This does NOT change story titles, acceptance criteria, or completion status — it only adds `reuse` and `constraints` fields.

### Step 1: Load Existing Plan

```bash
/create-plan --enrich docs/plans/my-feature.json
```

1. Read the plan file (JSON or markdown) from the specified path
2. Identify all stories where `passes: false` (incomplete)
3. Display plan summary: feature name, total stories, incomplete count

### Step 2: Analyze Reuse Opportunities Per Story

For each incomplete story:

1. Read the story's `title`, `files` array, and `type`
2. Extract key nouns from the title (component names, patterns, entity types)
3. Search the codebase for similar code:
   - Grep for similar component/hook/utility names
   - Check for files with similar naming patterns in the same directories
   - For UI stories: look for existing modals, forms, tables, lists with similar structure
   - For API stories: look for existing route handlers, middleware, validators
   - For hooks/utilities: look for similar function signatures or behavior
4. For each match found, generate:
   - A `reuse` entry: `{ path, what, how }`
   - Suggested `constraints` (e.g., "DO NOT recreate X — extend existing Y")

### Step 3: Present Findings for Review

```markdown
## Reuse Analysis for [plan-name]

### US-3: Create events modal
**Found reusable code:**
- `app/outages/outage-modal.tsx` — Modal layout, asset picker flow (copy-and-adapt)
- `hooks/use-form-validation.ts` — Form validation hook (import)

**Suggested constraints:**
- DO NOT recreate the modal from scratch — extend the outage modal pattern
- DO NOT build custom form validation — import existing useFormValidation hook

### US-4: Add event API endpoints
**Found reusable code:**
- `app/api/outages/route.ts` — CRUD endpoint pattern (follow-pattern)

**Suggested constraints:**
- Follow the existing outage API structure for consistency

### US-5: Setup project scaffolding
**No reuse candidates found** — this is a Setup story.

---

Accept these annotations? Options:
1. **Accept all** — Save all annotations
2. **Review per story** — Accept/reject for each story individually
3. **Edit** — Modify annotations before saving
4. **Cancel** — Make no changes
```

### Step 4: Save Annotations

After user approval:

1. For JSON plans: Add `reuse` and `constraints` fields to each annotated story
2. For markdown plans: Add/update the "Reuse Map" and "Constraints" sections
3. Do NOT modify any other fields (title, acceptance, passes, priority, depends)
4. Report: "Enriched [N] stories with reuse annotations. [M] stories had no matches."

### Notes

- Stories with `passes: true` are skipped (already complete)
- Stories that already have `reuse`/`constraints` fields are shown for review but not overwritten unless the user explicitly approves
- Setup and Docs stories rarely have reuse candidates — the scan is lighter for these types
- This mode does NOT enter plan mode (no EnterPlanMode needed) — it only annotates existing plans

---

## General Guidelines (All Modes)

### ⚠️ CRITICAL: Tasks Must Be Created

**After saving any plan file, you MUST create Tasks using the Tasks API.** This is NOT optional. Plans without Tasks will not appear in `/tasks` and cannot be tracked properly.

The task creation step (Step B below) MUST be completed before finishing the `/create-plan` command.

### Checklist Items

Each item should:

- Be completable in one `/project:iterate` cycle
- Have clear files and test criteria
- Be atomic and independently verifiable

### Categories

- `Setup` - Config, dependencies, scaffolding
- `Core` - Main logic changes
- `UI` - Frontend components
- `API` - Backend endpoints
- `Data` - Database/models
- `Test` - Test coverage
- `Fix` - Bug fixes
- `Refactor` - Code restructuring
- `Cleanup` - Removing dead code
- `Docs` - Documentation

### After Creating Plan

**CRITICAL: The plan MUST be saved to files for `/iterate` and `/ai-loop` to find it.**

#### Step A: Save Plan to Plan-Mode File (DURING plan mode)

**⚠️ CONTEXT CLEAR SAFETY**: Plan mode only allows writing to the auto-generated plan file (shown in the plan mode system message, e.g., `.claude/plans/[name].md`). If the user clears context after ExitPlanMode, `docs/plans/` files won't exist yet. To prevent plan loss, **save the complete plan — including embedded JSON — to the plan-mode file BEFORE calling ExitPlanMode.**

Write the full markdown plan to the plan-mode file, then append the JSON at the bottom as a fenced code block:

```markdown
[... full markdown plan content ...]

---

_Generated by `/create-plan`. Execute with `/iterate`._

<!-- PLAN_JSON
```json
{
  "feature": "[feature-name]",
  "branch": "[branch-name]",
  ...full JSON plan...
}
```
PLAN_JSON -->

<!-- PLAN_META
feature: [feature-name]
branch: [branch-name]
PLAN_META -->
```

The `PLAN_JSON` block embeds the machine-readable plan inside the markdown file. The `PLAN_META` block provides quick metadata extraction. Both use HTML comments so they don't render visually.

**This file persists even if the user clears context after ExitPlanMode.** `/iterate` and `/ai-loop` will auto-recover from it (see Plan Recovery below).

**JSON Structure:**

Convert each checklist item to a story in this format:

```json
{
  "feature": "[feature-name]",
  "branch": "[branch-name]",
  "status": "planning",
  "created": "[ISO timestamp]",
  "stories": [
    {
      "id": "US-1",
      "title": "[First checklist item title]",
      "type": "Setup|Core|UI|API|Data|Test|Fix|Refactor|Cleanup|Docs",
      "priority": 1,
      "passes": false,
      "files": ["path/to/file.ts"],
      "acceptance": "[Test criteria from checklist item]"
    },
    {
      "id": "US-2",
      "title": "[Second checklist item title]",
      "type": "Core",
      "priority": 2,
      "passes": false,
      "depends": ["US-1"],
      "files": ["path/to/file.ts"],
      "acceptance": "[Test criteria]",
      "reuse": [
        {
          "path": "path/to/existing-component.tsx",
          "what": "Component layout and state management",
          "how": "copy-and-adapt"
        }
      ],
      "constraints": [
        "DO NOT recreate modal from scratch — extend existing pattern in path/to/existing.tsx"
      ]
    }
  ]
}
```

**Type mapping from checklist categories:**

- `Setup` → Setup
- `Core` → Core
- `UI` → UI
- `API` → API
- `Data` → Data
- `Test` → Test
- `Fix` → Fix
- `Refactor` → Refactor
- `Cleanup` → Cleanup
- `Docs` → Docs

#### Step B: Create Tasks for Plan Items (DURING plan mode)

**⚠️ CRITICAL - DO NOT SKIP**: After saving the plan-mode file, you MUST create Tasks using the Tasks API. TaskCreate is NOT blocked by plan mode (it's not a file write). Plans without Tasks will NOT appear in `/tasks` and session tracking will fail.

**Failure to complete this step is the #1 cause of empty `/tasks` lists.**

For each story in the JSON plan where `passes: false`, call `TaskCreate`:

```typescript
// For each story in the JSON plan:
TaskCreate({
  subject: `${story.id}: ${story.title}`, // e.g., "US-1: Project setup"
  description: story.acceptance, // Full acceptance criteria
  activeForm: `Implementing ${story.title}`, // Shown during execution
  metadata: {
    planPath: `docs/plans/${feature}.json`, // Link back to plan file
    itemId: story.id, // Story ID for tracking
    storyType: story.type, // Setup, Core, UI, etc.
  },
});
```

**Example: Creating tasks for a plan with 3 items:**

```typescript
// Task 1
TaskCreate({
  subject: "US-1: Create database schema",
  description: "Database builds and migrations run successfully",
  activeForm: "Creating database schema",
  metadata: {
    planPath: "docs/plans/my-feature.json",
    itemId: "US-1",
    storyType: "Data",
  },
});

// Task 2 (depends on US-1)
TaskCreate({
  subject: "US-2: Add API endpoints",
  description: "API returns correct responses for all endpoints",
  activeForm: "Adding API endpoints",
  metadata: {
    planPath: "docs/plans/my-feature.json",
    itemId: "US-2",
    storyType: "API",
  },
});
// Then use TaskUpdate to set: addBlockedBy: ["task-id-of-US-1"]

// Task 3 (depends on US-2)
TaskCreate({
  subject: "US-3: Build UI components",
  description: "Components render correctly and pass accessibility checks",
  activeForm: "Building UI components",
  metadata: {
    planPath: "docs/plans/my-feature.json",
    itemId: "US-3",
    storyType: "UI",
  },
});
```

**Rules for Task creation:**

1. Include story ID prefix in subject for traceability (e.g., "US-1: ...")
2. Use acceptance criteria from the plan as the description
3. Use present participle (-ing) for activeForm
4. Store planPath and itemId in metadata for cross-referencing
5. Only create tasks for stories where `passes: false`
6. If story has `depends` array, use `TaskUpdate` with `addBlockedBy` after creation

#### Step C: Verify Tasks and Confirm with User (DURING plan mode)

**Before showing confirmation, verify tasks were created:**

```typescript
// REQUIRED: Verify tasks exist
const tasks = await TaskList();
const planTasks = tasks.filter(t => t.metadata?.planPath?.includes(featureName));

if (planTasks.length === 0) {
  // Tasks were NOT created - go back to Step B and create them!
  console.error("ERROR: No tasks found for plan. Step B was skipped.");
  // Re-run Step B before continuing
}
```

Display this confirmation:

```markdown
## Plan Saved

**Plan-mode file:** `.claude/plans/[auto-name].md` (contains markdown + embedded JSON)
**Tasks created:** [N] items synced to Claude Code Tasks
**Items**: [N] checklist items / stories
**Branch**: [branch-name]

### Checklist Preview

- [ ] Item 1
- [ ] Item 2
- [ ] Item 3
      ...

---

**Please review the plan above.** When you're ready to proceed:

1. Approve the plan (respond "yes" or "approved")
2. Run `/iterate` for attended mode, or `/ai-loop` for autonomous

Or modify the plan by telling me what to change.
```

#### Step D: Wait for User Confirmation (DURING plan mode)

**Do NOT proceed until the user explicitly approves the plan content.**

- If user says "yes", "approved", "looks good", "proceed" → Continue to Step E
- If user requests changes → Make changes, save again, update Tasks, re-confirm
- If user has questions → Answer them, then re-confirm

#### Step E: Exit Plan Mode

Display guidance, then exit plan mode:

```markdown
---
## Ready to Exit Planning

Your plan is saved in `.claude/plans/` with embedded JSON. It is safe to clear context — `/iterate` and `/ai-loop` will auto-recover the plan from this file.

**Choose any option Claude Code presents:**

| Claude Code Option | Maps To | Safe? |
|-------------------|---------|-------|
| **"Yes, manually approve edits"** | Continue in this session | ✅ |
| **"Yes, auto-accept edits"** | Continue with auto-accept | ✅ |
| **"Yes, clear context..."** | Fresh start for implementation | ✅ Plan auto-recovers |

After selecting, run `/iterate` or `/ai-loop` to start implementation.
---
```

**Then call `ExitPlanMode`** with permissions based on the plan requirements:

```json
{
  "allowedPrompts": [
    { "tool": "Bash", "prompt": "run lint checks" },
    { "tool": "Bash", "prompt": "run type checks" },
    { "tool": "Bash", "prompt": "run tests" }
  ]
}
```

Add additional permissions if the plan requires them (e.g., "run database migrations", "build the project").

#### Step F: Copy Plan to `docs/plans/` (AFTER ExitPlanMode)

**⚠️ This step runs after ExitPlanMode. If the user cleared context, `/iterate` and `/ai-loop` will handle this automatically via Plan Recovery.**

If the session is still active (user did NOT clear context):

1. Create `docs/plans/` if needed: `mkdir -p docs/plans`
2. Copy the markdown plan (without the embedded JSON comments) to `docs/plans/[feature-name].md`
3. Extract the JSON from the `PLAN_JSON` block and save to `docs/plans/[feature-name].json`
4. Confirm:

```markdown
## Ready to Implement

**Plan files copied:**

- `docs/plans/[feature-name].md` - Human-readable
- `docs/plans/[feature-name].json` - Machine-readable

**When you're ready, choose your execution mode:**

### Option 1: Attended Mode

Run `/iterate` for human-in-the-loop execution.
Best for: Complex features, learning new codebases, when decisions are needed.

### Option 2: Autonomous Mode

Run `/ai-loop --max 30` for autonomous execution.
Best for: Well-defined tasks, routine work, grinding through stories.

**To check progress:** Run `/status`
```

If the user already cleared context, skip this step — Plan Recovery in `/iterate`/`/ai-loop` handles it.

## Arguments

| Argument             | Description                                        |
| -------------------- | -------------------------------------------------- |
| `--from-prd [path]`  | Load existing PRD file instead of creating new one |
| `--improve`          | Improvement mode (enhance existing code)           |
| `--debug`            | Debug mode (fix a bug)                             |
| `--enrich [path]`    | Retrofit existing plan with reuse/constraint annotations |
| `--name [name]`      | Pre-specify the feature name                       |
| `--from-issue [url]` | Pull context from GitHub issue                     |
| `--minimal`          | Shorter PRD with less ceremony                     |

## Related Commands

| Command         | Use                                 |
| --------------- | ----------------------------------- |
| `/ai-loop`      | Autonomous execution of PRD stories |
| `/iterate`      | Human-in-the-loop execution         |
| `/status`       | Check current progress              |
| `/pre-pr-check` | Validate before PR                  |

## Suggested Next

- `/iterate` — start executing the plan items with human review
- `/ai-loop` — autonomous execution of all plan stories
- `/worktree` — create isolated branch for the feature work
