---
suggest_when:
  - signal: total_tool_calls
    value: 40
    cooldown: 60
    message: "Long session with no TODO tracking — `/create-todo` to capture items for later"
  - signal: session_start
    condition: has_todos_or_issues
    message: "You have open TODOs — `/next` to prioritize or `/create-todo` to add more"
---

# /create-todo — Lightweight Todo Capture

Add, categorize, and track todo items in the project's `TODO.md`. Designed as a lightweight backlog that feeds `/next` for prioritization.

## Usage

```
/create-todo [description] [--priority high|med|low] [--category features|bugs|chores|research] [--from-issue #N]
```

$ARGUMENTS

## Your Task

Add a todo item to `TODO.md` at the project root. Auto-detect category and priority when not specified.

## Step 1: Parse Arguments

Extract from `$ARGUMENTS`:

- **Description**: The todo text (required — ask if missing)
- **`--priority`**: `high`, `med`, or `low` (default: `med`)
- **`--category`**: `features`, `bugs`, `chores`, or `research` (default: auto-detect)
- **`--from-issue #N`**: Pull title and labels from GitHub issue

If `--from-issue` is provided:

```bash
gh issue view <N> --json title,labels,body
```

Use the issue title as description, labels to infer category and priority.

## Step 2: Auto-Detect Category

If no `--category` given, infer from keywords in the description:

| Keywords | Category |
|----------|----------|
| bug, fix, broken, error, crash, regression | Bugs / Fix |
| feature, add, implement, create, build, support | Priority Features |
| chore, update, upgrade, migrate, cleanup, refactor | Chores |
| research, investigate, explore, evaluate, spike | Research |

Default to **Priority Features** if no keywords match.

## Step 3: Read TODO.md

Read `TODO.md` from the project root.

If it doesn't exist, create it with this template:

```markdown
# TODO

## Priority Features

## Bugs / Fix

## Chores

## Research
```

## Step 4: Check for Duplicates

Compare the new item against existing unchecked items (`- [ ]`) in TODO.md:

- If a very similar item exists (same topic/intent), inform the user and ask whether to skip, merge, or add anyway
- Use keyword overlap to detect similarity — not exact string matching

## Step 5: Add the Item

Append the item under the correct category heading with metadata tags:

```markdown
- [ ] [p:<priority>] [src:<source>] [<date>] <description>
```

Where:
- `<priority>`: `high`, `med`, or `low`
- `<source>`: `manual`, `session`, `issue#<N>`, or `wrap-up`
- `<date>`: Today's date in `YYYY-MM-DD` format

**Example:**

```markdown
- [ ] [p:high] [src:issue#42] [2026-03-28] Fix OAuth token refresh failing after 24 hours
```

## Step 6: Confirm

Display the added item and its category. Show a count of total open items.

```markdown
**Added to TODO.md** (Bugs / Fix):
- [ ] [p:high] [src:manual] [2026-03-28] Fix OAuth token refresh failing

**Open items:** 7 (2 high, 3 med, 2 low)
```

## Arguments

| Argument | Description |
|----------|-------------|
| `[description]` | Todo text (required) |
| `--priority high\|med\|low` | Priority level (default: med) |
| `--category features\|bugs\|chores\|research` | Category override |
| `--from-issue #N` | Import from GitHub issue |
| `--source <src>` | Override source tag (for hook/wrap-up integration) |

## Metadata Format

Items use inline metadata tags for machine parseability while staying human-readable:

```
- [ ] [p:high] [src:session] [2026-03-28] Description text here
```

**Backward compatibility**: Existing items without metadata tags are treated as `[p:med] [src:manual]` by `/next` and other consumers.

## Suggested Next

- `/next` — prioritize and group your TODOs with GitHub issues
- `/create-plan` — turn a TODO into a structured implementation plan
- `/status` — check git state and session progress
