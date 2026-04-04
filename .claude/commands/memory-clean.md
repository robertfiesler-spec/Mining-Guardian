---
suggest_when:
  - signal: session_start
    condition: staged_learnings
    cooldown: 120
    message: "Memory entries piling up? `/memory-clean` archives old entries (default 30 days) to keep context lean"
  - signal: total_tool_calls
    value: 50
    cooldown: 120
    message: "Long-running project? `/memory-clean` prunes stale memory so future sessions load faster"
---

# /memory-clean - Archive Old Memory Entries

Manual cleanup of `.ai/memory/` — move old entries to the archive. Append-only: never deletes, only relocates.

## Usage

```
/memory-clean [--archive-days N] [--dry-run]
```

$ARGUMENTS

## Your Task

Scan `.ai/memory/learnings/` and `.ai/memory/staging/` for entries older than the threshold, then move them to `.ai/memory/archive/`.

## Step 1: Scan Memory Directories

```bash
mkdir -p .ai/memory/learnings .ai/memory/staging .ai/memory/archive
```

Read all JSON files from:

1. `.ai/memory/learnings/*.json`
2. `.ai/memory/staging/*.json` (only entries with `"promoted": true`)

Parse each file and extract `timestamp` (or `last_seen` as fallback).

**Never archive unpromoted staging entries** — they are still candidates for `/evolve` regardless of age.

## Step 2: Apply Age Filter

Default threshold: **30 days**. Override with `--archive-days N`.

```
cutoff = now - (archive_days * 24 * 60 * 60 * 1000)
```

An entry qualifies for archival if:

- **Learnings**: `last_seen` (or `timestamp`) is before the cutoff
- **Staging**: `promoted: true` AND `promoted_at` is before the cutoff

## Step 3: Preview

Show what would be archived:

```markdown
## Memory Cleanup Preview

**Threshold**: [N] days (entries before [cutoff date])
**Mode**: [dry-run | archive]

### Learnings to Archive ([count])

| File | Category | Last Seen | Age (days) |
|------|----------|-----------|------------|
| 20260101-learn-abc.json | typescript | 2026-01-01 | 43 |
| 20260105-learn-def.json | security | 2026-01-05 | 39 |

### Promoted Staging to Archive ([count])

| File | Category | Promoted At | Promoted To |
|------|----------|-------------|-------------|
| learn-ghi.json | react | 2026-01-02 | skills/react-patterns/SKILL.md |

### Skipped (kept in place)

- **[N] unpromoted staging entries** — still candidates for /evolve
- **[N] recent entries** — within the [archive_days]-day window

---

**Total**: [N] entries to archive, [M] entries kept
```

If `--dry-run`, stop here.

## Step 4: Archive

For each entry to archive:

1. **Copy** the file to `.ai/memory/archive/{original-filename}`
2. **Remove** the original from `learnings/` or `staging/`
3. **Log** the move

This is the only operation that removes files from `learnings/` or `staging/`, and only after copying to `archive/`. The archive itself is never pruned.

## Step 5: Report

```markdown
## Memory Cleanup Complete

**Archived**: [N] entries
**Kept**: [M] entries
**Archive location**: `.ai/memory/archive/`

### Summary

| Source | Archived | Kept |
|--------|----------|------|
| learnings/ | [n] | [m] |
| staging/ (promoted) | [n] | [m] |
| staging/ (unpromoted) | 0 | [m] |

Archive is append-only. Entries can be reviewed at any time in `.ai/memory/archive/`.
```

## Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--archive-days N` | Archive entries older than N days | 30 |
| `--dry-run` | Show what would be archived without making changes | false |
| `--include-staging` | Also archive unpromoted staging entries (use with caution) | false |

## Examples

```bash
# Preview what would be archived (default 30 days)
/memory-clean --dry-run

# Archive entries older than 30 days
/memory-clean

# Archive entries older than 14 days
/memory-clean --archive-days 14

# Preview with a 60-day threshold
/memory-clean --archive-days 60 --dry-run

# Include unpromoted staging entries (rare, use with caution)
/memory-clean --include-staging --dry-run
```

## Safety Guarantees

1. **Append-only archive** — archived entries are never deleted
2. **Unpromoted staging entries are protected** — they stay in `staging/` unless `--include-staging` is explicitly passed
3. **Dry-run by default when piped** — always preview before archiving
4. **Copy-then-remove** — the archive copy is written before the original is removed

## Related

- `/evolve` — review and promote staged learnings
- `/learn --pattern` — create new learning entries
- `/wrap-up` — extract session learnings
- `skills/continuous-learning/SKILL.md` — schema and directory structure
- `.ai/memory/archive/` — archived entries

## Suggested Next

- `/evolve` — review and promote staged learnings before archiving
- `/wrap-up` — extract session learnings
- `/learn` — stage new patterns to keep memory fresh
