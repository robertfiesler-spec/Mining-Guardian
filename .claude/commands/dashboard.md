---
suggest_when:
  - signal: session_start
    condition: no_plan_many_edits
    message: "Multiple projects may have pending work -- `/dashboard` for a cross-project view"
---

# Dashboard

Cross-project status dashboard. Scan multiple project directories and worktrees to show a unified view of activity, branches, pending work, and suggested actions. Designed for developers managing 3-5+ concurrent projects.

**When to use**: Starting your day. Deciding which project to work on next. Checking if any project needs attention.

**Not this command**: For a single project use `/catchup`. For current session state use `/remind`.

$ARGUMENTS

## Arguments

- `--paths <dir1,dir2,...>` — Explicit project paths to scan (comma-separated)
- `--json` — Output as JSON for tooling integration
- `--verbose` — Show full per-project summaries (like running `/catchup` for each)

## Step 1: Discover Projects

Find projects to scan using this priority:

### 1a. Explicit Paths

If `$ARGUMENTS` contains `--paths`, parse the comma-separated list and use those directories.

### 1b. Config-Based Discovery

Read `config.json` from the current toolkit installation. Check for:
```json
{
  "dashboard": {
    "projectPaths": ["~/projects/app-a", "~/projects/app-b"],
    "scanPaths": ["~/projects"],
    "includeWorktrees": true,
    "maxProjects": 10
  }
}
```

- `projectPaths`: explicit project directories (always included)
- `scanPaths`: directories to scan for projects (look for subdirectories with `.git/` or `package.json`)
- `includeWorktrees`: also discover git worktrees

### 1c. Worktree Discovery

From the current project, run:
```bash
git worktree list --porcelain 2>/dev/null
```

Parse output for worktree paths. Each worktree is a separate "project" for dashboard purposes.

### 1d. Fallback: Scan ~/projects/

If no config and no explicit paths, scan `~/projects/` for directories containing `.git/`:
```bash
find ~/projects -maxdepth 2 -name ".git" -type d 2>/dev/null | head -10
```

Use the parent directory of each `.git/` as a project path.

## Step 2: Gather Per-Project State

For each discovered project directory, gather state using shell commands (these run outside Claude's context, so use Bash):

### For Each Project:

```bash
# Project name (directory basename)
basename "$PROJECT_PATH"

# Current branch
git -C "$PROJECT_PATH" branch --show-current 2>/dev/null

# Uncommitted file count
git -C "$PROJECT_PATH" status --short 2>/dev/null | wc -l

# Last commit date (proxy for "last active")
git -C "$PROJECT_PATH" log -1 --format="%ci" 2>/dev/null

# Recent commits (last 3)
git -C "$PROJECT_PATH" log --oneline -3 2>/dev/null
```

Also read each project's `.ai/memory/session-state.json` if it exists:
```bash
cat "$PROJECT_PATH/.ai/memory/session-state.json" 2>/dev/null
```

And check for active plans:
```bash
ls "$PROJECT_PATH/docs/plans/" 2>/dev/null
```

## Step 3: Build Dashboard

Sort projects by last activity (most recent first). Classify each:

| Status | Criteria |
|--------|----------|
| **Active** | Uncommitted changes OR in-progress tasks |
| **Planned** | Has active plan with pending stories, but no uncommitted work |
| **Idle** | No uncommitted changes, no pending tasks |
| **Stale** | Last activity > 7 days ago |

### Output Format

```markdown
## Project Dashboard
_[N] projects scanned | [date/time]_

| Project | Branch | Last Active | Plan | Uncommitted | Status |
|---------|--------|-------------|------|-------------|--------|
| my-app | `feat/auth` | 2h ago | auth (4/8) | 2 files | Active |
| api-svc | `main` | 3d ago | -- | 0 files | Idle |
| toolkit | `main` | 1d ago | -- | 5 files | Active |
| docs-site| `feat/nav` | 8d ago | nav (2/3) | 0 files | Stale |

### Needs Attention
- **my-app**: 2 uncommitted files on `feat/auth`, plan 50% complete
- **toolkit**: 5 uncommitted files — consider committing or stashing

### Suggested Actions
-> `cd ~/projects/my-app` — resume auth plan (most active, plan in progress)
-> `cd ~/projects/toolkit` — commit or stash 5 dirty files
-> `cd ~/projects/docs-site` — stale plan, consider wrapping up or archiving
```

### Verbose Mode (--verbose)

If `--verbose` is specified, after the table, show a mini-catchup for each Active/Planned project:

```markdown
---

### my-app (Active)
**Branch**: `feat/auth` | **Last active**: 2 hours ago
**Last session**: Implemented OAuth callback handler, added session refresh
**Plan**: auth-overhaul — 4/8 stories, next: "Add CSRF token rotation"
**Uncommitted**: `src/auth/callback.ts`, `src/middleware.ts`
-> `/iterate` to continue

### toolkit (Active)
**Branch**: `main` | **Last active**: 1 day ago
**Last session**: Added session archival to hooks
**Uncommitted**: 5 files (hooks, commands)
-> `/create-commit` to checkpoint
```

### JSON Mode (--json)

If `--json` is specified, output structured JSON:

```json
{
  "scanned_at": "2026-03-12T15:30:00Z",
  "projects": [
    {
      "name": "my-app",
      "path": "/Users/user/projects/my-app",
      "branch": "feat/auth",
      "last_active": "2026-03-12T13:30:00Z",
      "uncommitted_count": 2,
      "plan": { "name": "auth", "completed": 4, "total": 8 },
      "status": "active"
    }
  ]
}
```

## Step 4: Suggest Focus

Based on the dashboard, recommend which project to focus on:

1. **Active projects with plans** — highest priority (momentum exists)
2. **Active projects without plans** — dirty state needs resolution
3. **Stale projects with plans** — may need attention or archival
4. **Idle projects** — no action needed

End with:

> Switch to a project with `cd <path>` then `/catchup` for full context.

## Suggested Next

After `/dashboard`, users typically:
- `cd <project-path>` then `/catchup` — dive into a specific project
- `/catchup` — single-project deep dive (current project)
- `/create-plan` — start a plan for a project without one
