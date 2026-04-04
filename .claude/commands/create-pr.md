---
suggest_when:
  - signal: edits_since_commit
    value: 0
    cooldown: 60
    message: "All changes committed — `/create-pr` generates a structured pull request"
---
# /create-pr Command

Generate a pull request with structured emoji sections.

## Usage

```
/create-pr [branch-name]
```

If no branch name provided, use current branch.

## Process

1. **Analyze** git diff between current branch and main/master
2. **Categorize** changes by type
3. **Generate** PR description with all sections
4. **Output** markdown ready to paste

## PR Template

```markdown
## 🎯 Overview

Brief description of what this PR accomplishes and why.

## ✨ What's New

- Feature/capability additions
- New components or utilities
- New API endpoints

## 🔧 Technical Changes

- Architecture changes
- Refactoring
- Dependency updates
- Configuration changes

## 🧪 Testing

- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] E2E tests added/updated
- [ ] Manual testing completed

**Test coverage:** X% → Y%

## 📝 Notes for Reviewers

- Areas that need careful review
- Known limitations
- Alternative approaches considered

## ⚠️ Breaking Changes

- [ ] No breaking changes
- [ ] Breaking changes (listed below)

If breaking changes:

- What breaks
- Migration path

## 🔄 Backward Compatibility

- [ ] Fully backward compatible
- [ ] Deprecation warnings added
- [ ] Migration guide included

## 👤 User Experience Impact

**Affected users:** (e.g., All users, Admin users only, API consumers)

**Changes visible to users:**

- UI changes
- Behavior changes
- Performance changes

**Rollout plan:**

- [ ] Feature flag
- [ ] Gradual rollout
- [ ] Immediate release
```

## Slack Notification (Optional)

If `--notify` flag provided or UX impact detected:

```
🚀 PR Ready for Review: [PR Title]

📍 Branch: feature/xyz → main
👤 Author: @james
📊 Changes: +X/-Y lines across N files

🎯 Summary: [1-2 sentence overview]

👤 UX Impact: [Brief description if any]

🔗 [Link to PR]
```

## Examples

```bash
# Generate PR for current branch
/create-pr

# Generate PR with Slack notification
/create-pr feature/auth-flow --notify

# Generate PR comparing specific branches
/create-pr feature/dashboard --base=develop
```

## Smart Detection

Automatically detect and highlight:

- **Security changes**: Auth, permissions, validation
- **Database changes**: Migrations, schema updates
- **Breaking changes**: API signature changes, removed exports
- **UX changes**: New UI components, changed behaviors

## Task Archival on PR Merge

When creating a PR for a plan-based feature, include task archival steps:

### Pre-PR: Gather Task Information

Before creating the PR, check for associated Tasks:

```typescript
// Get all tasks related to this feature's plan
const planPath = "docs/plans/[feature-name].json";
const tasks = await TaskList();

const planTasks = tasks.filter((t) => t.metadata?.planPath === planPath);
const completedTasks = planTasks.filter((t) => t.status === "completed");

// Include in PR description
console.log(`Tasks completed: ${completedTasks.length}/${planTasks.length}`);
```

### PR Description: Include Task Summary

Add a "Completed Tasks" section to the PR using task data:

```markdown
## Completed Tasks

- [x] US-1: Task description (commit: abc1234)
- [x] US-2: Task description (commit: def5678)
- [x] US-3: Task description (commit: ghi9012)

**Total**: N tasks completed
```

### Post-Merge: Archive Tasks

After PR is merged, archive tasks to plan metadata:

```typescript
// 1. Read the plan file
const planContent = await read(planPath);
const plan = JSON.parse(planContent);

// 2. Generate archival metadata
const archivalMetadata = {
  archival: {
    archived_at: new Date().toISOString(),
    pr_url: prUrl,
    merged_at: mergeTimestamp,
    task_count: completedTasks.length,
    tasks: completedTasks.map((t) => ({
      id: t.metadata.itemId,
      subject: t.subject,
      completed_at: t.completedAt,
      commit: t.metadata.commit,
    })),
  },
};

// 3. Update plan with archival metadata
plan.status = "complete";
plan.metadata = { ...plan.metadata, ...archivalMetadata };

// 4. Write updated plan
await write(planPath, JSON.stringify(plan, null, 2));

// 5. Move plan to archive folder (prevents future loops from picking it up)
const archiveDir = "docs/plans/archive";
await mkdir(archiveDir, { recursive: true });
const archivePath = path.join(archiveDir, path.basename(planPath));
await rename(planPath, archivePath);
console.log(`Plan archived: ${archivePath}`);
```

### Cleanup Arguments

| Argument       | Description                                          |
| -------------- | ---------------------------------------------------- |
| `--no-archive` | Skip task archival and plan file archival entirely   |

### Archival Flow

```
┌─────────────────────────────────────┐
│  PR Created                         │
│     ↓                               │
│  [Tasks listed in PR description]   │
│     ↓                               │
│  PR Merged                          │
│     ↓                               │
│  [Archive tasks to plan metadata]   │
│     ↓                               │
│  [Move plan to archive/ folder]     │
│     ↓                               │
│  [Clean up task list]               │
└─────────────────────────────────────┘
```

### Manual Archival

If automatic archival wasn't triggered, use `/tasks-cleanup`:

```bash
/tasks-cleanup --plan docs/plans/feature.json
```

This will:

1. Find all completed tasks for the plan
2. Archive them to plan metadata
3. Optionally delete the Tasks entries

## Suggested Next

| If... | Run |
|-------|-----|
| PR created, want to deploy preview | `/deploy` — deploy to Vercel with preview URL |
| Need to archive completed tasks | `/tasks-cleanup` — remove archived tasks from active list |
