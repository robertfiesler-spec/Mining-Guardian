---
suggest_when:
  - signal: session_start
    condition: no_agent_context
    message: "New session — `/version` to confirm which toolkit version is active"
---

# Version

Display the installed AI Toolkit version and check for updates.

## Your Task

Show the current toolkit version and compare against the source to check for updates.

$ARGUMENTS

## Step 1: Determine Context

Check if this is the source toolkit or an installed copy:

```bash
# Check if .toolkit-version exists (indicates installed copy)
if [ -f ".claude/.toolkit-version" ]; then
  echo "INSTALLED"
else
  # Check if this is the source toolkit (has config.json at root .claude/)
  if [ -f ".claude/config.json" ]; then
    echo "SOURCE"
  else
    echo "NOT_FOUND"
  fi
fi
```

## Step 2: Get Version Info

### If SOURCE toolkit:

Read the version from `.claude/config.json`:

```bash
grep '"version"' .claude/config.json | head -1
```

Display:

```markdown
## AI Toolkit Version

**This is the source toolkit**

Version: `1.0.0`

To install this toolkit to a project:

\`\`\`bash
./scripts/install.sh /path/to/your/project
\`\`\`
```

### If INSTALLED:

1. Read installed version:

```bash
cat .claude/.toolkit-version
```

2. Read manifest to get source path:

```bash
cat .claude/.toolkit-manifest.json | grep '"source"'
```

3. If source is accessible, read source version:

```bash
# Extract source path from manifest and read its config.json
SOURCE_PATH=$(grep '"source"' .claude/.toolkit-manifest.json | sed 's/.*"source": "\([^"]*\)".*/\1/')
cat "$SOURCE_PATH/.claude/config.json" | grep '"version"'
```

## Step 3: Compare Versions

If both versions are available, compare them:

- **Same version**: "Up to date"
- **Different versions**: "Update available"
- **Source inaccessible**: "Cannot check for updates (source not accessible)"

## Output Format

### Up to Date

```markdown
## AI Toolkit Version

**Installed**: `1.0.0`
**Source**: `1.0.0`

Status: Up to date
```

### Update Available

```markdown
## AI Toolkit Version

**Installed**: `1.0.0`
**Source**: `1.1.0`

Status: Update available

To update:

\`\`\`bash
/path/to/ai-toolkit/scripts/update.sh .
\`\`\`

Or preview changes first:

\`\`\`bash
/path/to/ai-toolkit/scripts/update.sh --dry-run .
\`\`\`
```

### Source Inaccessible

```markdown
## AI Toolkit Version

**Installed**: `1.0.0`
**Source**: (not accessible at `/original/path`)

To check for updates, ensure the source toolkit is available or update manually.
```

### Not Installed

```markdown
## AI Toolkit Version

No toolkit installation detected.

To install:

\`\`\`bash
git clone git@github.com:jamesscaggs/ai-toolkit.git ~/.ai-toolkit
~/.ai-toolkit/scripts/install.sh .
\`\`\`
```

## Arguments

- `--json` - Output version info as JSON
- `--check` - Only check if update is available (exit code 0 if up to date, 1 if update available)

## Suggested Next

| If... | Run |
|-------|-----|
| Update available | `/update-toolkit` — update toolkit from remote repository |
| Check toolkit token costs | `/token-budget` — check component token costs against budgets |
