---
suggest_when:
  - signal: session_start
    condition: has_todos_or_issues
    message: "Have TODOs or open issues — `/next` to see what to work on"
  - signal: total_tool_calls
    value: 5
    cooldown: 120
    message: "Not sure what to tackle? `/next` suggests your top priorities"
---

# /next — What to Work On Next

Analyze your backlog (TODO.md + GitHub issues + active plans) and suggest what to `/create-plan` next. Groups related items, ranks by priority, and offers to start planning immediately.

## Usage

```
/next [--limit N] [--category features|bugs|chores|research] [--no-issues]
```

$ARGUMENTS

## Your Task

Help the user decide what to work on next by synthesizing their backlog into ranked, actionable suggestions.

## Step 1: Read TODO.md

Read `TODO.md` from the project root. Parse all unchecked items (`- [ ]`):

**New format** (with metadata tags):
```
- [ ] [p:high] [src:issue#42] [2026-03-28] Fix OAuth token refresh
```

Extract: priority, source, date, description, category (from section heading).

**Legacy format** (no metadata):
```
- [ ] Fix OAuth token refresh
```

Treat as: `p:med`, `src:manual`, date unknown.

**If TODO.md doesn't exist**: Note it and continue with GitHub issues only.

## Step 2: Fetch GitHub Issues

Fetch open issues from the current repository:

```bash
gh issue list --limit 30 --state open --json number,title,labels,createdAt,url,body 2>/dev/null
```

**If `gh` is not installed or no remote exists**: Skip this step gracefully with a note:

```markdown
> **Note**: GitHub issues skipped (`gh` CLI not available or no remote configured)
```

Extract: issue number, title, labels (for priority/category), creation date, URL.

**Label-to-priority mapping**:

| Labels | Priority |
|--------|----------|
| `priority:critical`, `urgent`, `P0` | high |
| `bug`, `priority:high`, `P1` | high |
| `enhancement`, `feature`, `P2` | med |
| `chore`, `documentation`, `P3` | low |

Default to `med` if no recognized labels.

## Step 3: Read Active Plans

Scan `docs/plans/` for active plans:

```bash
ls docs/plans/*.json 2>/dev/null
```

For each JSON plan file, read it and extract:
- Feature name
- Story count and completion percentage
- File paths claimed by the plan
- Status (in-progress stories)

**Purpose**: Identify what's already being worked on to avoid suggesting redundant work and to flag potential conflicts.

## Step 4: Group Related Items

Cross-reference TODO items with GitHub issues to find related work:

1. **Keyword matching**: Group items that share significant keywords (e.g., "auth", "login", "OAuth" → auth group)
2. **Issue references**: Link TODO items that reference issue numbers (`[src:issue#42]`)
3. **Label clustering**: Group issues with shared labels
4. **Category alignment**: TODO items in same category that address related functionality

Create groups of 1-5 related items. Standalone items form their own group.

## Step 5: Rank Suggestions

Score each group using these factors:

| Factor | Weight | Logic |
|--------|--------|-------|
| Priority | High | Groups containing `p:high` items rank higher |
| Group size | Medium | More related items = higher impact (signal of importance) |
| Age | Medium | Older items get urgency boost (stale backlog = neglect) |
| No plan conflict | High | Groups that don't overlap with active plans rank higher |
| Bug vs feature | Low | Bugs get slight priority boost (stability first) |

**Conflict detection**: If a group's likely files overlap with an active plan's claimed files, flag it as a conflict but don't exclude it.

Select the top 3-5 groups (or fewer if the backlog is small). Respect `--limit N` if provided, and `--category` to filter.

## Step 6: Present Ranked Suggestions

Output the ranked list:

```markdown
## What to Work On Next

### 1. [Group Title] ⬆ High Priority | Effort: Medium
**Items:**
- TODO: [item text] (Priority Features, p:high, added 2026-03-20)
- Issue #42: [issue title] — [labels]
- Issue #47: [related issue title] — [labels]

**Why this is #1:** [Rationale — e.g., "Two open issues and a TODO all point to auth being broken. High-priority bug cluster with 3 related items, oldest from 8 days ago."]

**Potential conflicts:** None
**Estimated scope:** [Small/Medium/Large] — [brief justification]

---

### 2. [Group Title] ⬆ Medium Priority | Effort: Small
**Items:**
- TODO: [item text] (Chores, p:med, added 2026-03-25)

**Why this is #2:** [Rationale]

**Potential conflicts:** Overlaps with active plan `improve-auth` (both touch `src/lib/auth.ts`)
**Estimated scope:** Small — single file change

---

### 3. [Group Title] ...

---

### Backlog Summary
- **TODO.md**: X open items (Y high, Z med, W low)
- **GitHub Issues**: X open
- **Active Plans**: X in progress (Y% average completion)
- **Items not shown**: X (lower priority or already covered by active plans)
```

## Step 7: Interactive Selection

After presenting the list, prompt the user:

```markdown
**Pick a number (1-5) to create a plan, or:**
- `all` — show full backlog details
- `skip` — just reviewing, no action needed
- Describe custom work to plan instead
```

**If user picks a number:**

1. Compose a feature description from the grouped items
2. Include issue URLs for reference
3. Offer to run `/create-plan`:

```markdown
Ready to plan: **[Group Title]**

This will include:
- [Item 1]
- [Item 2]
- Issue #42, Issue #47

Run `/create-plan --feature [composed description]`? (yes/no)
```

If yes, invoke `/create-plan` with the composed description.

**If user describes custom work:** Offer to run `/create-plan` with their description.

## Arguments

| Argument | Description |
|----------|-------------|
| `--limit N` | Show top N suggestions (default: 5) |
| `--category features\|bugs\|chores\|research` | Filter to one category |
| `--no-issues` | Skip GitHub issues, use TODO.md only |
| `--verbose` | Show all backlog items, not just top suggestions |

## Suggested Next

- `/create-plan` — turn a suggestion into a structured implementation plan
- `/iterate` — start executing an existing plan
- `/status` — check git state and session progress
