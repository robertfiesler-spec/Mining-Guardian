---
suggest_when:
  - signal: session_start
    condition: incomplete_plan
    message: "Incomplete plan found — run `/iterate` to continue"
---
# Iterate

Execute Plan items with a document-and-clear workflow. Completes items, checkpoints, then stops for context clearing.

## Cost Optimization

**Cost scales with batch size and item complexity.** This command delegates to specialized agents based on item type - each agent has its own model recommendation. See `agents/*.md` for model hints.

- **Simple items** (config, docs): Batched 2-3 at a time, lower cost
- **Complex items** (features, refactors): Single item per batch, higher cost
- **Use `/ai-loop`** for autonomous execution - it manages iterations efficiently

## Your Task

Work through Plan checklist items, then checkpoint and stop for context clearing. This optimizes for clean context over continuous execution.

**Automatic Session Management**: This command automatically handles checkpointing and restoration - no manual `/checkpoint` or `/catchup` needed.

**Tasks Integration**: This command uses Claude Code's native Tasks API for persistent state tracking. Tasks provide:

- Cross-session persistence without file I/O
- Visual progress tracking via `/tasks` command
- Automatic sync with plan files
- Dependency tracking with `blockedBy`

**Tasks API Tools**:

- `TaskCreate` - Create new tasks with metadata
- `TaskUpdate` - Update status (pending/in_progress/completed)
- `TaskList` - Query all tasks
- `TaskGet` - Retrieve task details by ID

$ARGUMENTS

## Execution Modes

| Mode           | Trigger             | Behavior                                                  |
| -------------- | ------------------- | --------------------------------------------------------- |
| **Attended**   | `/iterate`          | Adaptive batching (1-3 items), checkpoint, STOP for human |
| **Autonomous** | Called by `loop.sh` | Single item, update prd.json, completion signal           |

## Document & Clear Loop (Attended Mode)

**DEFAULT BEHAVIOR**: Complete item(s) → checkpoint → STOP for clear.

```
┌─────────────────────────────────────────────┐
│  /iterate                                   │
│     ↓                                       │
│  [Load agent based on item type]            │
│     ↓                                       │
│  [Implement item]                           │
│     ↓                                       │
│  [Verify: lint, typecheck, test]            │
│     ↓                                       │
│  [/create-commit --plan context]            │
│     ↓                                       │
│  [Update Plan: mark complete, log progress] │
│     ↓                                       │
│  [Checkpoint: save full state]              │
│     ↓                                       │
│  [Batch complete?] ──no──→ [Next item]      │
│     ↓ yes                                   │
│  STOP → "Clear context, run /iterate (auto-restores)"
└─────────────────────────────────────────────┘
```

## Autonomous Mode (for /ai-loop)

When running via `loop.sh`, behavior changes:

```
┌─────────────────────────────────────────────┐
│  [Fresh Claude instance]                    │
│     ↓                                       │
│  Read prd.json → find next story            │
│     ↓                                       │
│  [Load agent based on story type]           │
│     ↓                                       │
│  [Implement ONE story]                      │
│     ↓                                       │
│  [Verify: lint, typecheck, test]            │
│     ↓                                       │
│  [/create-commit --plan context]            │
│     ↓                                       │
│  [Update prd.json: passes: true]            │
│     ↓                                       │
│  [Append to progress.txt]                   │
│     ↓                                       │
│  [All stories done?]                        │
│     ↓ yes                                   │
│  Output: <promise>COMPLETE</promise>        │
│     ↓ no                                    │
│  Exit (loop.sh spawns next instance)        │
└─────────────────────────────────────────────┘
```

## Adaptive Batching

Decide batch size based on item complexity:

| Item Complexity | Batch Size | Examples                                              |
| --------------- | ---------- | ----------------------------------------------------- |
| **Simple**      | 2-3 items  | Config changes, imports, small edits, renaming        |
| **Medium**      | 1-2 items  | New function, component update, API endpoint          |
| **Complex**     | 1 item     | New feature, significant refactor, multi-file changes |

**Assess complexity by:**

- Number of files touched
- Lines of code changed
- Cognitive load of the change
- Whether tests need to be written

**When in doubt, batch smaller.** Clean context > fewer interruptions.

## Agent Loading

Based on the story/item type, load the appropriate agent:

| Item Type  | Agent Loaded          |
| ---------- | --------------------- |
| `Test`     | `tdd-guide.md`        |
| `E2E`      | `e2e-runner.md`       |
| `Refactor` | `refactor-cleaner.md` |
| `Docs`     | `doc-updater.md`      |
| `UI`       | `visual-verifier.md`  |
| `Deploy`   | `deployer.md`         |
| Other      | No special agent      |

If verification fails, automatically load `build-error-resolver.md`.

**UI Story Verification**: When processing `UI` type stories, after standard verification (lint, typecheck, test) passes, visual verification runs automatically via the visual-verifier agent. This captures screenshots and accessibility snapshots to catch rendering issues that code analysis misses.

## Step 0: Check for Interrupted Session (Auto-Restore)

Before starting, check if there's an interrupted session to resume. This now supports **plan-scoped sessions** for multi-agent coordination.

```bash
# Determine session file location (plan-scoped if CLAUDE_PLAN is set)
PLAN_NAME="${CLAUDE_PLAN:-}"
if [[ -n "$PLAN_NAME" ]]; then
  # Plan-scoped session (multi-agent mode)
  SESSION_FILE=".claude/state/plans/$PLAN_NAME/session.json"
else
  # Legacy global session (single-agent mode)
  SESSION_FILE=".claude/state/session.json"
fi

# Check for existing session state
if [[ -f "$SESSION_FILE" ]]; then
  STATUS=$(jq -r '.status // "unknown"' "$SESSION_FILE" 2>/dev/null)
  echo "Found session with status: $STATUS"
fi

# Also check for recent checkpoints
ls -t .claude/checkpoints/*.md 2>/dev/null | head -1
```

**If interrupted session found** (status is "paused", "crashed", or checkpoint exists):

1. Read the session state and/or latest checkpoint
2. Present summary to user:

   ```markdown
   ## Previous Session Detected

   **Plan**: [plan name]
   **Session**: [plan-scoped | legacy]
   **Status**: [interrupted/paused/crashed]
   **Progress**: [X]/[Y] items complete
   **Last Activity**: [timestamp] - [activity]

   Would you like to:

   1. **Resume** - Continue from where you left off
   2. **Start Fresh** - Clear session and start from next incomplete item
   ```

3. If user chooses Resume:
   - Restore context from checkpoint (read modified files, understand state)
   - Update session status to "running"
   - Continue to Step 0.5 to detect/confirm plan
4. If user chooses Start Fresh:
   - Archive current session to plan-specific archive:
     ```bash
     if [[ -n "$PLAN_NAME" ]]; then
       ARCHIVE_DIR=".claude/state/plans/$PLAN_NAME/archive"
       mkdir -p "$ARCHIVE_DIR"
       mv "$SESSION_FILE" "$ARCHIVE_DIR/session-$(date +%Y%m%d-%H%M%S).json"
     else
       mv "$SESSION_FILE" ".claude/state/sessions/"
     fi
     ```
   - Continue to Step 0.5 normally

**If no interrupted session**: Continue to Step 0.5.

## Step 0.5: Detect Active Plan (Multi-Agent Support)

Before loading a plan, determine which plan this session should work on. This enables multiple agents to work on different plans simultaneously without interference.

**Detection Priority** (first match wins):

1. **Environment variable**: `$CLAUDE_PLAN` (explicit override)
2. **Git branch**: Extract plan name from branch (e.g., `feature/auth-flow` → `auth-flow`)
3. **Argument**: `--plan <name>` passed to iterate
4. **Most recent**: Most recently modified plan file in `docs/plans/`

**Detection Logic**:

```bash
# 1. Check environment variable (explicit override from /ai-loop or user)
if [[ -n "${CLAUDE_PLAN:-}" ]]; then
  PLAN_NAME="$CLAUDE_PLAN"
  echo "Using plan from CLAUDE_PLAN: $PLAN_NAME"
fi

# 2. Try to match git branch to a plan file
if [[ -z "$PLAN_NAME" ]]; then
  BRANCH=$(git branch --show-current 2>/dev/null)
  if [[ -n "$BRANCH" ]]; then
    # Extract plan name from branch (feature/my-plan -> my-plan)
    PLAN_NAME="${BRANCH#feature/}"
    PLAN_NAME="${PLAN_NAME#fix/}"
    PLAN_NAME="${PLAN_NAME#refactor/}"

    # Verify plan file exists
    if [[ ! -f "docs/plans/${PLAN_NAME}.json" && ! -f "docs/plans/${PLAN_NAME}.md" ]]; then
      PLAN_NAME=""  # Reset if no matching plan
    fi
  fi
fi

# 3. Fall back to most recent plan
if [[ -z "$PLAN_NAME" ]]; then
  RECENT=$(ls -t docs/plans/*.json 2>/dev/null | head -1)
  [[ -z "$RECENT" ]] && RECENT=$(ls -t docs/plans/*.md 2>/dev/null | head -1)
  PLAN_NAME=$(basename "$RECENT" | sed 's/\.\(json\|md\)$//')
fi

# Export for session and child processes
export CLAUDE_PLAN="$PLAN_NAME"
echo "Plan context: $PLAN_NAME (CLAUDE_PLAN exported)"
```

**Why This Matters**:

- Each plan gets its own session state in `.claude/state/plans/{plan-name}/session.json`
- Multiple agents can work on different plans without stepping on each other
- Session restoration (Step 0) uses the correct plan-scoped session
- File claims registry tracks which plan owns which files

**If Multiple Plans Active**:

When `$CLAUDE_PLAN` is not set and multiple plans exist:

1. List active plans (those with running/paused sessions)
2. If one matches current git branch, use it
3. Otherwise, prompt user to select:

```markdown
## Multiple Active Plans Detected

Found active sessions for multiple plans:
1. `auth-flow` (3/8 complete, paused)
2. `payment-ui` (5/10 complete, running in another terminal?)

Which plan should this session work on?
- Enter plan name, or
- Use `--plan <name>` argument, or
- Set `export CLAUDE_PLAN=<name>` before running
```

**Continue to Step 1** with the detected plan.

## Step 0.6: Query ACS for Cross-Project Context (if available)

Before implementing, check for relevant cross-project learnings from ACS:

```bash
if [[ -n "${ACS_URL:-}" ]]; then
  source ~/.claude/scripts/lib/acs-client.sh
  if acs_is_available; then
    PROJECT_NAME=$(basename "$(pwd)")
    ACS_RESULT=$(acs_get_project_context "$PROJECT_NAME")
    ACS_CONTEXT=$(echo "$ACS_RESULT" | acs_extract_context)
    if [[ -n "$ACS_CONTEXT" ]]; then
      echo "ACS: Found relevant cross-project context"
    fi
  fi
fi
```

If ACS returns context, keep it in mind during implementation — it may contain
patterns, corrections, or architectural decisions from past work.

**This step is non-blocking**: if ACS is slow or unavailable, skip and continue.

## Step 0.7: Register File Claims

After detecting the plan (Step 0.5), register file claims so other loops/worktrees know which files this session owns. This prevents concurrent loops from editing the same files on different branches.

```bash
# Source file claims library
CLAIMS_LIB=""
if [[ -f ".claude/hooks/lib/file-claims.sh" ]]; then
  CLAIMS_LIB=".claude/hooks/lib/file-claims.sh"
elif [[ -f "$HOME/.claude/hooks/lib/file-claims.sh" ]]; then
  CLAIMS_LIB="$HOME/.claude/hooks/lib/file-claims.sh"
fi

if [[ -n "$CLAIMS_LIB" && -n "$PLAN_NAME" ]]; then
  source "$CLAIMS_LIB"

  # Get files from the plan
  PLAN_FILE="docs/plans/${PLAN_NAME}.json"
  if [[ -f "$PLAN_FILE" ]] && command -v jq &>/dev/null; then
    # Extract file paths from plan stories
    PLAN_FILES=$(jq -r '.stories[]? | .files[]? // empty' "$PLAN_FILE" 2>/dev/null)

    CLAIMED=0
    while IFS= read -r file; do
      [[ -z "$file" ]] && continue

      # Check for conflicts before claiming
      if ! check_claim "$file" "$PLAN_NAME" 2>/dev/null; then
        OWNER=$(get_claim "$file" | jq -r '.plan // "unknown"' 2>/dev/null)
        echo "WARNING: $file is claimed by plan '$OWNER'"
        echo "  Use CLAUDE_ALLOW_CONFLICT=1 to override"
      else
        claim_file "$file" "$PLAN_NAME" "${CLAUDE_AGENT_ID:-iterate}" "write"
        CLAIMED=$((CLAIMED + 1))
      fi
    done <<< "$PLAN_FILES"

    if [[ $CLAIMED -gt 0 ]]; then
      echo "File claims registered: $CLAIMED files for plan '$PLAN_NAME'"
    fi
  fi
fi
```

**If conflicts are found and `CLAUDE_ALLOW_CONFLICT` is not set:**

```markdown
## File Conflict Warning

The following files are claimed by another plan:

| File | Owned By |
|------|----------|
| `src/lib/api.ts` | `auth-feature` |

**Options:**
1. **Switch plans** — work on the other plan first
2. **Override** — set `CLAUDE_ALLOW_CONFLICT=1` (risk merge conflicts)
3. **Redesign** — modify your plan to avoid these files
```

**If no conflicts or user overrides**: Continue to Step 1.

**Claims are released** when the plan completes (via `complete_plan_session()` in session-manager.sh).

## Step 0.8: Reuse Discovery (Before Implementation)

Before implementing any story, check for reuse opportunities. This step runs once per batch, after loading the plan but before implementation begins.

### If story has `reuse` field:

These are **mandatory references** — read each file before implementing.

- For `import`: Verify the export exists, plan your import statement
- For `extend`: Read the source file, understand the interface to extend
- For `copy-and-adapt`: Read the source file, identify the relevant section, plan your adaptation
- For `follow-pattern`: Read the source to understand the structural pattern to replicate

```
Reuse check for US-3: "Create events modal"
  ✓ Reading app/outages/outage-modal.tsx — Modal layout (copy-and-adapt)
  ✓ Reading hooks/use-form-validation.ts — Form validation (import)
  2 reuse references loaded
```

### If story has `constraints` field:

Treat each constraint as a hard requirement. Your implementation plan MUST NOT violate any constraint. If a constraint conflicts with the story requirements, flag it to the user before proceeding.

### If story has neither:

Run a lightweight discovery scan based on story type:

| Story Type | Scan Depth | What to Search |
|------------|-----------|----------------|
| Setup, Docs | Skip | No scan needed |
| Test, E2E | Light (~200 tokens) | Existing test utilities, fixtures |
| API, Data | Medium (~500 tokens) | Existing route handlers, models, validators |
| UI, Core, Refactor | Thorough (~2k tokens) | Similar components, hooks, utilities, patterns |

**Scan process:**
1. Extract key nouns from the story title (e.g., "modal", "form", "table", "picker")
2. Search for existing files matching those keywords: `grep -rl "keyword" src/ app/ lib/ hooks/ components/`
3. If matches found, briefly review for reuse potential
4. Log findings: "Found existing [X] at [path] — will extend/reuse" or "No reuse matches found"

**This step is informational** — it does not block implementation. Proceed to Step 1 after discovery.

## Step 1: Find Active Plan and Sync Tasks

Check for both formats (JSON for autonomous, markdown for attended):

```bash
# JSON format (for autonomous mode)
ls -t docs/plans/*.json 2>/dev/null | head -1

# Markdown format (for attended mode)
ls -t docs/plans/*.md 2>/dev/null | head -1
```

### Plan Recovery (if no plan found in `docs/plans/`)

If no plan exists in `docs/plans/`, check `.claude/plans/` for plan files created by `/create-plan` that weren't copied (e.g., user cleared context after ExitPlanMode):

```bash
# Check for plan-mode files with embedded JSON
ls -t .claude/plans/*.md ~/.claude/plans/*.md 2>/dev/null | head -5
```

For each candidate file, check if it contains a `PLAN_JSON` block:

```bash
grep -l "PLAN_JSON" .claude/plans/*.md ~/.claude/plans/*.md 2>/dev/null
```

If a plan file with embedded JSON is found:

1. **Extract the JSON** from between `<!-- PLAN_JSON` and `PLAN_JSON -->` markers
2. **Extract metadata** from between `<!-- PLAN_META` and `PLAN_META -->` markers (feature name, branch)
3. **Create `docs/plans/`**: `mkdir -p docs/plans`
4. **Save the markdown** (stripping the JSON/META comment blocks) to `docs/plans/[feature-name].md`
5. **Save the JSON** to `docs/plans/[feature-name].json`
6. **Create Tasks** if they don't already exist (they may have been created during plan mode)
7. **Report recovery**:

```
Plan Recovery:
  Found plan in .claude/plans/[file].md
  Extracted: [feature-name] ([N] stories)
  Saved: docs/plans/[feature-name].md + .json
  Tasks: [N] tasks verified ✓
  Continuing with recovered plan...
```

If no plan found anywhere: "No active Plan. Run `/create-plan` first."

Read the Plan and extract:

- Feature name and branch
- All checklist items/stories with status
- Next incomplete item(s) `- [ ]` or `passes: false`
- Progress so far

### Sync with Tasks API (MANDATORY)

**⚠️ CRITICAL**: After loading the plan, you MUST sync state with Claude Code Tasks. This ensures `/tasks` shows progress and enables cross-session persistence.

**If Tasks don't exist, CREATE THEM NOW before proceeding:**

**Always inform the user what's happening:**

```
Syncing plan to Tasks API...
- Found [N] stories in plan
- Checking existing tasks...
- [Creating N new tasks / Tasks already exist]
Tasks synced ✓
```

1. **Check existing Tasks**: Use `TaskList` to see if tasks already exist for this plan
2. **Create missing tasks**: If no tasks exist (or fewer than expected), create them immediately:

```typescript
// For each incomplete story/item in the plan:
for (const item of planItems) {
  TaskCreate({
    subject: `${item.id}: ${item.title}`,
    description: `${item.description}\n\nFiles: ${item.files?.join(", ")}\nAcceptance: ${item.acceptance}`,
    activeForm: `Implementing ${item.title}`,
    metadata: {
      planPath: planFile,
      itemId: item.id,
      type: item.type,
    },
  });
}

// REQUIRED: Verify tasks were created
const verifyTasks = await TaskList();
if (verifyTasks.length === 0) {
  throw new Error("Failed to create tasks - /tasks will be empty!");
}
console.log(`Created ${verifyTasks.length} tasks for plan`);
```

**⚠️ DO NOT proceed to Step 2 until tasks exist.** If `TaskList()` returns empty, re-run the creation loop above.

3. **Reconcile state**: If Tasks exist but don't match plan file:
   - Plan file is source of truth for `passes` status
   - Use `TaskUpdate` to sync task status with plan file
   - Log any discrepancies found

4. **Handle dependencies**: Use `blockedBy` for items with dependencies:
   - If story has `depends: ["US-1", "US-2"]`, set `addBlockedBy` on TaskUpdate
   - Blocked tasks cannot start until dependencies complete

5. **Include subtasks**: If subtasks exist (created by orchestrator), include them in sync:
   - Subtasks have IDs like `US-5.1`, `US-5.2` (parent.index format)
   - Subtasks have `owner` metadata indicating which agent owns them
   - Subtask status is tracked independently from parent task

**Note**: Tasks persist across context clears and are visible via `/tasks` command.

### Fallback When Tasks Unavailable

If the Tasks API is not available (e.g., older Claude Code version, offline mode), iterate gracefully falls back to file-based tracking:

**Detection**:

```typescript
// Try to use Tasks API
try {
  const tasks = await TaskList();
  // Tasks available - use Tasks API for tracking
  useTasksApi = true;
} catch (error) {
  // Tasks unavailable - fall back to file-based tracking
  console.log("Tasks API unavailable, using file-based tracking");
  useTasksApi = false;
}
```

**Fallback Behavior**:

| Operation        | Tasks API (Primary)   | File-Based (Fallback)               |
| ---------------- | --------------------- | ----------------------------------- |
| List items       | `TaskList()`          | Read plan file (JSON/MD)            |
| Mark in_progress | `TaskUpdate(status)`  | Update session.json `current_story` |
| Mark completed   | `TaskUpdate(status)`  | Update plan file `passes: true`     |
| Track subtasks   | Tasks with `parentId` | Not supported in fallback           |
| Cross-session    | Automatic via Tasks   | Via session.json + checkpoint files |

**Session State Fallback**:

When Tasks are unavailable, session.json becomes the primary state store:

```json
{
  "status": "running",
  "progress": {
    "current_story": "US-6",
    "completed": ["US-1", "US-2", "US-3", "US-4", "US-5"],
    "in_progress": ["US-6"]
  }
}
```

**Hybrid Mode**:

If Tasks become available mid-session, iterate can sync from file-based state:

1. Read session.json and plan file state
2. Create Tasks for incomplete items
3. Mark completed items in Tasks
4. Continue with Tasks API

**Important**: The plan file (JSON/MD) is ALWAYS the source of truth for `passes` status. Tasks API provides additional features (cross-session persistence, visual tracking) but is not required for iterate to function.

### Subtask Tracking (Orchestrator Integration)

When the orchestrator creates subtasks for a parent story, they require special handling:

**Subtask Identification**:

```typescript
// Subtasks follow the pattern: parentId.index
const isSubtask = (taskId: string) => /^US-\d+\.\d+$/.test(taskId);
const getParentId = (subtaskId: string) => subtaskId.split(".")[0]; // "US-5.1" -> "US-5"
```

**Subtask Metadata Schema**:

```typescript
interface SubtaskMetadata {
  planPath: string; // Path to the plan file
  itemId: string; // e.g., "US-5.1"
  parentId: string; // e.g., "US-5"
  type: string; // Task type (e.g., "Core", "Test")
  owner: string; // Agent name that owns this subtask
  delegatedBy: string; // "orchestrator"
  delegatedAt: string; // ISO timestamp
}
```

**Subtask Status Rules**:

1. **Independent Updates**: Subtasks update their own status without affecting siblings
2. **Parent Completion**: Parent task only completes when ALL subtasks are complete
3. **Ownership Tracking**: Each subtask has an `owner` field indicating the responsible agent
4. **Blocked Dependencies**: Subtasks can have `blockedBy` pointing to other subtasks

**Checking Subtask Completion**:

```typescript
// Before marking parent as complete, verify all subtasks are done
async function canCompleteParent(parentId: string): Promise<boolean> {
  const tasks = await TaskList();
  const subtasks = tasks.filter((t) => t.metadata?.parentId === parentId);

  // Parent can only complete if ALL subtasks are completed
  return subtasks.every((t) => t.status === "completed");
}
```

**Example Flow**:

```
1. User starts story US-5
2. Orchestrator delegates work, creates:
   - US-5.1 (owner: "tdd-guide")
   - US-5.2 (owner: "architect")
   - US-5.3 (owner: "security-reviewer")
3. Each subtask updates independently:
   - US-5.1: pending -> in_progress -> completed
   - US-5.2: pending -> in_progress -> completed
   - US-5.3: pending -> in_progress -> completed
4. Only when US-5.1, US-5.2, US-5.3 are ALL complete:
   - US-5 can be marked complete
   - Plan file updated with passes: true
```

**Subtask Display in TaskList**:

When listing tasks, subtasks are shown indented under their parent:

```
[ ] US-5: Add dynamic task creation (in_progress)
    [x] US-5.1: Implement core logic (owner: tdd-guide)
    [x] US-5.2: Add API endpoint (owner: architect)
    [ ] US-5.3: Security review (owner: security-reviewer, in_progress)
```

## Step 1.5: Initialize Session State (Attended Mode)

If no session state exists, create one for attended mode tracking:

```bash
SESSION_FILE=".claude/state/session.json"
if [[ ! -f "$SESSION_FILE" ]]; then
  mkdir -p .claude/state
  TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
  PLAN_NAME=$(basename "$PLAN_PATH" .md | sed 's/.json$//')

  cat > "$SESSION_FILE" << EOF
{
  "version": "1.0",
  "created_at": "$TIMESTAMP",
  "updated_at": "$TIMESTAMP",
  "status": "running",
  "plan": {
    "path": "$PLAN_PATH",
    "name": "$PLAN_NAME",
    "branch": "$BRANCH"
  },
  "progress": {
    "total_stories": 0,
    "completed": 0,
    "current_story": null,
    "current_iteration": 0
  },
  "execution": {
    "mode": "attended",
    "start_time": "$TIMESTAMP"
  },
  "activity_log": []
}
EOF
fi
```

This enables session state tracking for attended mode, allowing auto-restore and TUI dashboard support.

### Load Pyramid Context (if available)

If `.claude/pyramid/` exists, load context proportional to the current story's scope:

1. **Always read** `L1-overview.md` (~50-100 lines) for project orientation
2. **Read the relevant module section** from `L2-modules.md` — match the story's files to the appropriate `## Module:` header
3. **Only read L3** if the story involves deep debugging or cross-module refactoring

This keeps per-iteration context lean while ensuring agents understand the project architecture.

## Step 2: Plan This Batch

Before implementing, assess:

1. **Next item complexity** - Simple, medium, or complex?
2. **Batch size decision** - How many items this session?
3. **Announce plan**: "This session: implementing [N] item(s) - [brief descriptions]"

### Mark Current Item as In Progress

When starting work on an item, update its Task status:

```typescript
// Mark the item we're about to work on as in_progress
TaskUpdate({
  taskId: currentTaskId,
  status: "in_progress",
});
```

This provides real-time visibility into what's being worked on via `/tasks` command.

## Step 3: Execute Each Item

For each item in the batch:

### 3a. Implement

- Read item description, files, and test criteria
- Make focused code changes for THIS item only
- Follow existing patterns in the codebase

### 3b. Verify

Run verification (errors block, warnings OK):

```bash
# Lint
pnpm lint

# Typecheck
pnpm typecheck

# Tests
pnpm test
```

**If ANY check fails with errors:**

1. STOP immediately
2. Report exact error with file/line
3. Do NOT proceed to commit
4. Wait for user guidance

### 3c. Commit

Delegate to `/create-commit` with Plan context:

```bash
/create-commit --all --plan "[feature-name]" --item "[checklist item text]" --progress "[X]/[Y]"
```

This ensures consistent commit format and leverages create-commit's change analysis.

The commit message will include:

- Conventional commit format (feat/fix/refactor etc.)
- Bullet points explaining changes
- Plan context (item implemented, progress)
- Co-author attribution

### 3d. Update Plan and Tasks

Edit the Plan file:

1. Change `- [ ]` to `- [x]` for completed item
2. Add row to Progress Log:

```markdown
| [date] | [item summary] | [commit hash] | Completed |
```

**Update Tasks via TaskUpdate**:

After updating the plan file, sync the task status:

```typescript
// Mark the completed item as done in Tasks
TaskUpdate({
  taskId: completedTaskId,
  status: "completed",
});
```

This ensures:

- Tasks reflect current progress (visible via `/tasks`)
- State persists across context clears
- `/catchup` can restore from Tasks if needed

**Handling Subtask Completion**:

When the completed item is a subtask (e.g., `US-5.1`):

```typescript
// 1. Mark the subtask as complete
TaskUpdate({
  taskId: subtaskId,
  status: "completed",
});

// 2. Check if parent can be completed
const parentId = getParentId(subtaskId); // "US-5.1" -> "US-5"
const allSubtasksDone = await canCompleteParent(parentId);

if (allSubtasksDone) {
  // 3. Mark parent task as complete
  TaskUpdate({
    taskId: parentTaskId,
    status: "completed",
  });

  // 4. Update plan file with passes: true for parent story
  // (only when ALL subtasks are done)
}
```

**IMPORTANT**: Do NOT mark the parent story as `passes: true` in the plan file until ALL subtasks are complete. This prevents `/ai-loop` from skipping incomplete work.

### 3e. Item Complete

Log: "Item [N] complete. Commit: [hash]"

## Step 4: Checkpoint (Automatic - Replaces Manual /checkpoint)

After completing batch, **automatically** create a detailed checkpoint. This replaces the need for manual `/checkpoint` commands.

### 4a. Update Session State

If session state exists (`.claude/state/session.json`), update it:

```bash
# Update session status and progress
SESSION_FILE=".claude/state/session.json"
if [[ -f "$SESSION_FILE" ]]; then
  # Update for attended mode
  TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  jq --arg ts "$TIMESTAMP" \
     --arg status "paused" \
     '.status = $status | .updated_at = $ts' \
     "$SESSION_FILE" > "$SESSION_FILE.tmp" && mv "$SESSION_FILE.tmp" "$SESSION_FILE"
fi
```

### 4b. Create Checkpoint File

**Filename**: `.claude/checkpoints/[YYYYMMDD-HHMMSS]-[feature]-batch.md`

**Contents**:

```markdown
# Checkpoint: [Feature Name]

**Created**: [timestamp]
**Status**: in progress
**Branch**: [branch name]

## Session Summary

Completed [N] items this session.

## Items Completed This Session

- [x] Item description (commit: abc1234)
- [x] Item description (commit: def5678)

## Files Modified

- `path/to/file.ts` - [what changed]

## Plan Progress

- Total items: [Y]
- Completed: [X]
- Remaining: [Y-X]

## Next Items

The next items to implement are:

1. [Next incomplete item]
2. [Following item]

## Notes

[Any context that would help next session - edge cases found, decisions made, etc.]

---

**To continue**: `/clear` → `/iterate` (auto-restores context)
```

Note: The "To continue" instructions no longer require `/catchup` - the `/iterate` command now handles restoration automatically via Step 0.

## Step 5: Send Notification and Report

**ALWAYS stop after checkpoint.** Before reporting, send a notification:

```bash
# Batch complete notification
.claude/scripts/notify.sh "iterate_batch_complete" "Batch Complete" "[N] items completed" \
  --progress "[X]/[Y]" --plan "[feature-name]"
```

Report:

```markdown
## Batch Complete

**Plan**: [feature-name]
**This Session**: [N] items completed
**Total Progress**: [X]/[Y] ([percentage]%)

### Completed

- [x] Item 1 (commit: abc1234)
- [x] Item 2 (commit: def5678)

### Next Up

- [ ] Item 3
- [ ] Item 4

### Checkpoint Saved

`.claude/checkpoints/[filename]`

---

**Next Steps**:

1. Clear context: `/clear` or `/compact`
2. Continue: `/iterate` (auto-restores from checkpoint)

_Note: Manual `/catchup` is no longer needed - `/iterate` automatically detects and offers to resume interrupted sessions._

[If all items complete]:
**Feature complete!** Run `/pre-pr-check` then create PR.
```

## Stopping Conditions

| Condition          | Action                                                |
| ------------------ | ----------------------------------------------------- |
| Batch complete     | Checkpoint → Notify → Stop → Prompt to clear          |
| All items done     | Checkpoint → Notify → Stop → Suggest pre-pr-check     |
| Verification error | Notify error → Stop immediately → Report error        |
| Blocker/ambiguity  | Notify error → Stop → Explain what decision is needed |
| Human correction   | Prompt → Suggest /learn                               |

### Error Notifications

When hitting an error or blocker, send a notification before stopping:

```bash
.claude/scripts/notify.sh "iterate_error" "Iteration Error" "[Brief error description]" \
  --plan "[feature-name]"
```

## Learning from Corrections

**When human intervention corrects your work**, always ask:

> I notice you corrected [X]. Would you like me to run `/learn` to document this as a rule so I don't make this mistake again?

**Triggers for learning prompt:**

- User manually fixes code you wrote
- User points out a missed step or forgotten file
- User corrects a pattern or approach
- Verification passes after user intervention

**Do not prompt for:**

- Typos or minor wording preferences
- User changing their requirements (not a mistake)
- Exploratory changes during development

## Completion Signal (Autonomous Mode)

When ALL stories in prd.json have `passes: true`, output:

```
<promise>COMPLETE</promise>
```

This signals `loop.sh` to stop iterating and report success.

## Updating prd.json and Tasks (Autonomous Mode)

After completing a story, update both the JSON file and Tasks:

### Update JSON File

```bash
# Mark story as complete
jq '.stories |= map(if .id == "US-X" then .passes = true | .commit = "abc1234" | .completed_at = "2024-01-15T14:30:00Z" else . end)' docs/plans/feature.json > tmp.json && mv tmp.json docs/plans/feature.json
```

### Update Tasks via TaskUpdate

After updating the JSON, also update Tasks for cross-session persistence:

```typescript
// Mark the completed story in Tasks
TaskUpdate({
  taskId: storyTaskId, // Task ID for "US-X"
  status: "completed",
});
```

**Why both?**

- JSON file: Source of truth, read by loop.sh, contains full metadata
- Tasks API: Visual feedback, persists in Claude Code, enables `/catchup` sync

## Appending to progress.txt (Autonomous Mode)

After each iteration, append learnings:

```markdown
### Iteration N (YYYY-MM-DD HH:MM:SS)

**Story**: US-X: Story title [Type]
**Status**: Complete

**Files Changed**:

- `path/to/file.ts` - description

**Learnings**:

- Key insight discovered
- Pattern to remember

**Commit**: abc1234
```

## Arguments

| Argument        | Description                                           |
| --------------- | ----------------------------------------------------- |
| `--single`      | Force single item only (ignore adaptive batching)     |
| `--batch [N]`   | Force specific batch size (1-5)                       |
| `--autonomous`  | Autonomous mode (single item, prd.json, progress.txt) |
| `--dry-run`     | Show plan without executing                           |
| `--skip-verify` | Skip verification (use with caution)                  |

## Related Commands

| Command          | Use                                  |
| ---------------- | ------------------------------------ |
| `/create-plan`   | Create Plan before iterating         |
| `/ai-loop`       | Start autonomous execution           |
| `/catchup`       | Restore context after clear          |
| `/create-commit` | Called automatically for commits     |
| `/learn`         | Document mistakes as permanent rules |

## Suggested Next

- `/create-commit` — commit in-progress work before clearing context
- `/create-pr` — open PR after feature is complete
- `/catchup` — restore context in a fresh session after `/clear`
