---
suggest_when:
  - signal: total_tool_calls
    value: 40
    cooldown: 60
    message: "Lots of completed tasks? `/tasks-cleanup` archives them to keep the list tidy"
  - signal: session_start
    condition: incomplete_plan
    cooldown: 120
    message: "Task list getting long? `/tasks-cleanup` removes archived tasks so current work stays visible"
---

# Tasks Cleanup

Archive and clean up completed tasks from the Tasks list.

## Your Task

Archive completed tasks to plan metadata and optionally remove them from the active task list. This keeps the `/tasks` view clean while preserving history.

$ARGUMENTS

## When to Use

- After merging a PR (archive all tasks for that feature)
- When task list becomes cluttered with completed items
- Before starting a new feature (clean slate)
- Periodically to maintain task hygiene

## Step 1: Gather Current Tasks

Query the Tasks API to get all tasks:

```typescript
const allTasks = await TaskList();

// Group by status
const completed = allTasks.filter((t) => t.status === "completed");
const inProgress = allTasks.filter((t) => t.status === "in_progress");
const pending = allTasks.filter((t) => t.status === "pending");

console.log(`Total tasks: ${allTasks.length}`);
console.log(`  Completed: ${completed.length}`);
console.log(`  In Progress: ${inProgress.length}`);
console.log(`  Pending: ${pending.length}`);
```

## Step 2: Filter by Plan (if specified)

If `--plan` argument provided, filter to tasks for that plan:

```typescript
const planPath = args.plan; // e.g., "docs/plans/tasks-integration.json"
const planTasks = allTasks.filter((t) => t.metadata?.planPath === planPath);

console.log(`Tasks for plan: ${planTasks.length}`);
```

## Step 3: Apply Age Filter (if specified)

If `--older-than` argument provided, filter by completion date:

```typescript
const threshold = args.olderThan; // e.g., "7d", "24h", "1w"
const thresholdMs = parseThreshold(threshold);
const cutoffDate = Date.now() - thresholdMs;

const oldTasks = completed.filter((t) => {
  const completedAt = t.metadata?.completedAt || t.completedAt;
  return completedAt && new Date(completedAt).getTime() < cutoffDate;
});
```

## Step 4: Show Preview

Before taking action, show what will be archived:

```markdown
## Tasks Cleanup Preview

**Plan**: [plan path or "all"]
**Filter**: [age filter or "none"]

### Tasks to Archive (N)

| ID   | Subject                    | Completed  |
| ---- | -------------------------- | ---------- |
| US-1 | Create task sync utilities | 2026-01-25 |
| US-2 | Add Tasks to create-plan   | 2026-01-25 |
| US-3 | Update iterate command     | 2026-01-25 |

### Tasks to Keep (M)

- In Progress: N tasks
- Pending: M tasks

---

**Actions available:**

1. `--archive` - Archive to plan metadata only
2. `--archive --delete` - Archive and remove from task list
3. `--dry-run` - Show this preview only (default)
```

## Step 5: Archive Tasks (if --archive)

If `--archive` flag provided:

### 5a. Read Plan File

```typescript
const planContent = await read(planPath);
const plan = JSON.parse(planContent);
```

### 5b. Generate Archival Records

```typescript
const archivedTasks = tasksToArchive.map((task) => ({
  id: task.metadata?.itemId || task.id,
  subject: task.subject,
  status: "completed",
  completedAt: task.metadata?.completedAt || new Date().toISOString(),
  commit: task.metadata?.commit,
}));
```

### 5c. Update Plan with Archival Metadata

```typescript
const archivalMetadata = {
  archival: {
    archived_at: new Date().toISOString(),
    task_count: archivedTasks.length,
    tasks: archivedTasks,
  },
};

// Merge into existing plan metadata
plan.metadata = { ...plan.metadata, ...archivalMetadata };
plan.status = "complete"; // If all tasks archived
plan.updated = new Date().toISOString();

await write(planPath, JSON.stringify(plan, null, 2));
```

### 5d. Delete Tasks (if --delete)

If `--delete` flag also provided, remove archived tasks from active list:

```typescript
// Note: Tasks API doesn't have a delete operation
// Instead, mark as archived in metadata and filter from views
for (const task of tasksToArchive) {
  await TaskUpdate({
    taskId: task.id,
    metadata: { archived: true, archivedAt: new Date().toISOString() },
  });
}
```

## Step 6: Archive Plan File (if --archive-plan)

If `--archive-plan` flag provided, move the plan file to `docs/plans/archive/`:

```typescript
const archiveDir = "docs/plans/archive";
await mkdir(archiveDir, { recursive: true });

const planBasename = path.basename(planPath);
const archivePath = path.join(archiveDir, planBasename);

await rename(planPath, archivePath);
console.log(`Plan archived: ${archivePath}`);
```

This prevents future `/ai-loop` runs from picking up the completed plan, since `loop.sh` only scans `docs/plans/*.json` (not subdirectories).

**Auto-detect when to archive**: If `--archive-plan` is not explicitly provided but the plan's associated git branch has been merged to main, prompt the user:

```bash
git branch -a --merged main 2>/dev/null | grep -q "$PLAN_BRANCH" && echo "MERGED"
```

If merged, suggest: _"Branch `<branch>` is already merged. Archive the plan file too? Run `/tasks-cleanup --archive-plan --plan <path>`"_

## Step 7: Report Results

```markdown
## Tasks Cleanup Complete

**Archived**: N tasks
**Plan updated**: [plan path]
**Plan file**: [archived to docs/plans/archive/ | still in docs/plans/]

### Archived Tasks

- [x] US-1: Create task sync utilities
- [x] US-2: Add Tasks to create-plan
- [x] US-3: Update iterate command

### Next Steps

- Start new feature: `/create-plan`
```

## Arguments

| Argument             | Description                                  | Default       |
| -------------------- | -------------------------------------------- | ------------- |
| `--plan [path]`      | Archive tasks for specific plan only         | All tasks     |
| `--older-than [age]` | Only archive tasks older than threshold      | All completed |
| `--archive`          | Actually perform archival (not just preview) | Dry run       |
| `--archive-plan`     | Move plan JSON to `docs/plans/archive/`      | Skip          |
| `--delete`           | Also remove archived tasks from active list  | Keep tasks    |
| `--dry-run`          | Show preview without making changes          | Default       |
| `--force`            | Skip confirmation prompt                     | Prompt        |

### Age Format

- `1h`, `2h`, `24h` - Hours
- `1d`, `7d`, `30d` - Days
- `1w`, `2w` - Weeks

## Examples

```bash
# Preview what would be archived
/tasks-cleanup

# Archive all completed tasks for a specific plan
/tasks-cleanup --plan docs/plans/tasks-integration.json --archive

# Archive and delete tasks older than 7 days
/tasks-cleanup --older-than 7d --archive --delete

# Archive all completed tasks, skip confirmation
/tasks-cleanup --archive --force

# Only show tasks for a plan (dry run)
/tasks-cleanup --plan docs/plans/feature.json --dry-run
```

## Cleanup Strategies

### After PR Merge

```bash
# Archive all tasks and move plan file to archive
/tasks-cleanup --plan docs/plans/[feature].json --archive --archive-plan
```

### Weekly Maintenance

```bash
# Archive tasks completed more than a week ago
/tasks-cleanup --older-than 1w --archive --delete
```

### Before New Feature

```bash
# Clean up all completed tasks
/tasks-cleanup --archive --delete --force
```

## Related Commands

| Command      | Purpose                                    |
| ------------ | ------------------------------------------ |
| `/create-pr` | Includes task archival on merge            |
| `/status`    | Shows current task and plan state          |
| `/iterate`   | Creates and updates tasks during execution |
| `/catchup`   | Restores from Tasks or checkpoints         |

## Suggested Next

- `/create-pr` — open PR after archiving completed tasks
- `/status` — verify git state and remaining work
- `/catchup` — restore context if tasks were cleared unexpectedly
