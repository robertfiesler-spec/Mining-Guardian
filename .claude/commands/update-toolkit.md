---
suggest_when:
  - signal: session_start
    condition: no_agent_context
    message: "Starting a new project session — `/update-toolkit` to pull the latest toolkit improvements"
---

# /update-toolkit Command

Update the AI Toolkit to the latest version from the remote repository.

## Trigger

User runs `/update-toolkit` or asks to "update the toolkit" / "update ai toolkit"

## Purpose

Fetch and apply the latest toolkit version from GitHub without requiring manual git operations.

## Options

| Option             | Description                                      |
| ------------------ | ------------------------------------------------ |
| `--dry-run`        | Preview changes without applying them            |
| `--force`          | Skip prompts, overwrite conflicts (with backups) |
| `--skip-conflicts` | Preserve all user customizations                 |
| `--branch <name>`  | Update from specific branch (default: main)      |

## Process

### Step 1: Verify Installation

Check that a toolkit installation exists:

```bash
# Look for .claude/.toolkit-manifest.json
if [ ! -f ".claude/.toolkit-manifest.json" ]; then
    echo "No toolkit installation found in this project."
    exit 1
fi
```

### Step 2: Run Self-Update Script

Execute the self-update script with appropriate options:

```bash
# Default update (interactive)
.claude/scripts/self-update.sh

# Or with options
.claude/scripts/self-update.sh --dry-run        # Preview changes
.claude/scripts/self-update.sh --force          # Non-interactive
.claude/scripts/self-update.sh --skip-conflicts # Preserve customizations
```

If the script doesn't exist locally (older installation), download and run it:

```bash
# Fallback: run directly from the source script location
# Read repository URL from manifest
REPO_URL=$(grep '"repository"' .claude/.toolkit-manifest.json | sed 's/.*: *"\([^"]*\)".*/\1/' | head -1)

# Create temp dir, clone, run update
TEMP_DIR=$(mktemp -d)
git clone --depth 1 --branch main "$REPO_URL" "$TEMP_DIR/ai-toolkit"
"$TEMP_DIR/ai-toolkit/scripts/update.sh" .
rm -rf "$TEMP_DIR"
```

### Step 3: Report Results

Display the update summary:

- Version change (e.g., "1.0.0 → 1.1.0")
- Files added/updated/unchanged
- User customizations preserved
- Any conflicts that need attention

## Example Output

```
══════════════════════════════════════════════════════════════
AI Toolkit Self-Update
══════════════════════════════════════════════════════════════

Installation found: .claude
Current version: 1.0.0
Repository: https://github.com/jamesscaggs/ai-toolkit.git
Branch: main

Fetching latest from remote...
Fetched version: 1.1.0

Running update...

  + commands/new-command.md
  ↻ commands/feature.md
  ✓ commands/iterate.md (user customization preserved)
  ○ agents/planner.md (unchanged)

══════════════════════════════════════════════════════════════
Update complete!
══════════════════════════════════════════════════════════════

  Summary:
    + New files:         1
    ↻ Updated:           5
    ○ Unchanged:         42
    ✓ Customized:        2
```

## Error Handling

| Error                 | Resolution                                           |
| --------------------- | ---------------------------------------------------- |
| No installation found | Run install.sh first                                 |
| No repository URL     | Reinstall toolkit (older version)                    |
| Git not available     | Install git                                          |
| Clone failed          | Check internet/repository access                     |
| Conflicts detected    | Use --force or --skip-conflicts, or resolve manually |

## Related Commands

- `/version` - Check current version and available updates
- `/status` - Show project and toolkit status

## Implementation Notes

The update process:

1. Reads `repository` URL from `.claude/.toolkit-manifest.json`
2. Clones fresh from remote (shallow clone of main branch)
3. Runs `update.sh` from the fresh clone against the project
4. Cleans up temp directory
5. Preserves user customizations via checksum comparison

User modifications are detected by comparing file checksums:

- If file matches manifest checksum → safe to update
- If file differs from manifest → user customized, preserve unless forced

## Suggested Next

- `/version` — verify the installed version after update
- `/kickoff` — initialize session with the updated toolkit
- `/docs-check` — verify docs match new toolkit state
