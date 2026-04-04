---
suggest_when:
  - signal: session_start
    condition: no_pyramid_large_project
    cooldown: 120
    message: "Large project with no pyramid summaries — `/summarize` generates multi-level context for leaner sessions"
  - signal: total_tool_calls
    value: 30
    cooldown: 60
    message: "Deep into a codebase? `/summarize` captures multi-resolution snapshots to keep future sessions lean"
---

# Summarize (Pyramid Summary Generator)

Generate multi-resolution project summaries at three zoom levels for progressive context loading.

## Your Task

Generate or refresh pyramid summaries for the current project. Summaries are stored in `.claude/pyramid/` and consumed by agents to load only the context depth they need.

$ARGUMENTS

## Step 0: Check Existing Summaries

Check if pyramid summaries already exist:

```bash
ls -la .claude/pyramid/ 2>/dev/null
```

**If summaries exist**, check staleness:

```bash
# Read metadata
cat .claude/pyramid/.pyramid-meta.json 2>/dev/null

# Compare git SHA to current HEAD
PYRAMID_SHA=$(cat .claude/pyramid/.pyramid-meta.json 2>/dev/null | grep -o '"git_sha":"[^"]*"' | cut -d'"' -f4)
CURRENT_SHA=$(git rev-parse --short HEAD)
COMMIT_DISTANCE=$(git rev-list --count "$PYRAMID_SHA..$CURRENT_SHA" 2>/dev/null || echo "unknown")
```

Report staleness:

```markdown
## Existing Pyramid Summaries

| Level | Lines | Generated | Staleness |
|-------|-------|-----------|-----------|
| L1: Overview | [N] | [date] | [N commits behind] |
| L2: Modules | [N] | [date] | [N commits behind] |
| L3: Files | [N] | [date] | [N commits behind] |
```

- If `--force` flag: proceed to regeneration
- If fresh (< 50 commits): "Summaries are current. Use `--force` to regenerate."
- If stale (50-200 commits): "Summaries are [N] commits stale. Regenerating..."
- If very stale (200+): "Summaries are significantly outdated. Full regeneration recommended."

**If no summaries exist**: proceed directly to generation.

## Step 1: Parse Arguments

| Flag | Behavior |
|------|----------|
| (none) | Generate all three levels |
| `--level L1` | Regenerate only L1: Project Overview |
| `--level L2` | Regenerate only L2: Module Map |
| `--level L3` | Regenerate only L3: File Detail |
| `--module <name>` | Regenerate only the named module's sections in L2 and L3 |
| `--force` | Regenerate even if summaries are fresh |
| `--dry-run` | Show what would be generated without writing files |

If `--level` or `--module` specified, only regenerate that portion. Preserve the rest.

## Step 2: Scan Project Structure

Build a map of the project:

1. **Read project identity files**: `package.json`, `CLAUDE.md`, `README.md`, top-level config files
2. **Map directory structure** at depth 2 using Glob:
   ```
   Glob: **/*/
   ```
3. **Identify module boundaries**: Look for these patterns:
   - `src/features/*` or `src/modules/*` (feature folders)
   - `app/*` (Next.js route groups)
   - `lib/*` or `src/lib/*` (utility modules)
   - `packages/*` (monorepo packages)
   - Any directory with its own `types.ts`, `index.ts`, or barrel export

4. **Count files per module** to estimate scope:
   ```
   Glob: src/features/**/*.{ts,tsx}
   ```

Report the scan results:

```markdown
## Project Scan

**Modules detected:** [N]
- `auth` (12 files)
- `products` (18 files)
- `orders` (15 files)
- ...

**Total source files:** [N]
**Estimated generation cost:** L1 (~5 reads) + L2 (~[N×4] reads) + L3 (~[N] reads)
```

## Step 3: Generate L1 — Project Overview

**Target**: ~50-100 lines. No source code reading needed.

Read these files only:
- `package.json` (stack, dependencies)
- `CLAUDE.md` (project rules, architecture notes)
- `README.md` (project description, setup)
- Top-level config files (`next.config.*`, `tsconfig.json`, `tailwind.config.*`, etc.)
- Directory listing at depth 2

Synthesize into this structure:

```markdown
# L1: Project Overview

**Generated**: [ISO date]
**Git SHA**: [short SHA]
**Branch**: [branch name]

## Purpose
[1-2 sentences: what this project does]

## Architecture
[1-2 sentences: architectural style and key decisions]

## Stack
- [Framework] [version] / [Language] [version]
- [Styling solution]
- [Database / ORM]
- [Key integrations]
- [Testing tools]

## Directory Structure
[Annotated tree at depth 2, with 1-line descriptions per directory]

## Subsystems
[1 paragraph per major subsystem/module, covering purpose and key integration points]

## External Integrations
[List of external services, APIs, databases with brief role description]
```

Write to `.claude/pyramid/L1-overview.md`.

## Step 4: Generate L2 — Module Map

**Target**: ~200-400 lines. Read 3-5 files per module.

For each detected module:

1. Read the module's `index.ts` or barrel export (if exists)
2. Read `types.ts` or type definition files
3. Read 2-3 primary entry points (largest files, most-imported files)
4. Extract:
   - Module purpose
   - Key files (3-5)
   - Public API surface (exported functions, components, types)
   - Patterns used
   - Dependencies on other modules (from import statements)

Synthesize into this structure:

```markdown
# L2: Module Map

**Generated**: [ISO date]
**Git SHA**: [short SHA]

## Data Flow
[Brief description of how data moves between modules — what calls what]

## Shared Utilities
[Where shared code lives: lib/, utils/, helpers/]

## Module: [name]

**Purpose**: [one sentence]

**Key Files:**
- `path/to/file.ts` - [role]
- `path/to/file.ts` - [role]

**Public API:**
- `functionName(params): ReturnType` - [brief description]
- `<ComponentName />` - [brief description]

**Patterns:**
- [Pattern 1]
- [Pattern 2]

**Dependencies:**
- `other-module` ([why: e.g., "reads user data for permissions"])

---

[Repeat for each module]
```

Write to `.claude/pyramid/L2-modules.md`.

## Step 5: Generate L3 — File Detail

**Target**: ~500-1000 lines. Read all significant files.

**Significance filter** (include files matching ANY):
- More than 100 lines
- Imported by 3+ other files (check with Grep for import references)
- Matches `**/types.ts`, `**/index.ts`, `**/utils.ts`, `**/constants.ts`
- Contains business logic (not pure UI rendering)

**Skip**: test files (`*.test.*`, `*.spec.*`), generated files, vendor code, config-only files, simple re-exports under 20 lines.

For each significant file:

1. Read the file
2. Extract:
   - Key functions/classes with signatures
   - Important types and interfaces
   - Non-obvious implementation details
   - Known edge cases or gotchas

Synthesize into this structure:

```markdown
# L3: File Detail

**Generated**: [ISO date]
**Git SHA**: [short SHA]
**Files documented**: [N]

## Module: [name]

### path/to/file.ts ([N] lines)

**Functions:**
- `functionName(param: Type): ReturnType` - [brief description]

**Types:**
- `TypeName = ...` - [what it represents]

**Details:**
- [Non-obvious implementation note]

**Gotchas:**
- [Edge case or surprising behavior]

---

[Repeat for each significant file, grouped by module]
```

Write to `.claude/pyramid/L3-files.md`.

## Step 6: Write Metadata

After generating all requested levels, write `.claude/pyramid/.pyramid-meta.json`:

```json
{
  "generated_at": "[ISO timestamp]",
  "git_sha": "[current short SHA]",
  "branch": "[current branch]",
  "levels": {
    "L1": { "generated_at": "[timestamp]", "line_count": [N], "git_sha": "[SHA]" },
    "L2": { "generated_at": "[timestamp]", "line_count": [N], "git_sha": "[SHA]" },
    "L3": { "generated_at": "[timestamp]", "line_count": [N], "git_sha": "[SHA]" }
  },
  "file_count": [total source files],
  "module_count": [detected modules]
}
```

If only a partial regeneration was done (`--level` or `--module`), preserve existing metadata for unchanged levels.

## Step 7: Report Results

```markdown
## Pyramid Summary Generated

| Level | Lines | Files Read | Status |
|-------|-------|------------|--------|
| L1: Overview | [N] | [N] | ✅ Generated |
| L2: Modules | [N] | [N] | ✅ Generated |
| L3: Files | [N] | [N] | ✅ Generated |

**Location**: `.claude/pyramid/`
**Git SHA**: [short SHA]
**Modules**: [list]

Summaries will be used automatically by `/kickoff`, `/iterate`, and `/loop`.
To refresh later: `/summarize` (or `/summarize --module <name>` for targeted refresh).
```

## Arguments

| Flag | Description |
|------|-------------|
| `--level L1\|L2\|L3` | Regenerate only a specific level |
| `--module <name>` | Regenerate only a specific module in L2/L3 |
| `--force` | Regenerate even if summaries are fresh |
| `--dry-run` | Show scan results and estimated cost without writing |

## Related Commands

| Command | Relationship |
|---------|-------------|
| `/kickoff` | Reads L1 if pyramid exists, suggests `/summarize` if not |
| `/iterate` | Reads L1 + relevant L2 section per story |
| `/create-plan` | Reads L1 + L2 for story decomposition |
| `/loop` | Each iteration loads L1 + module context |

## Suggested Next

- `/kickoff` — initialize session with pyramid context loaded
- `/iterate` — execute plan items with pyramid context available
- `/create-plan` — plan features with architecture overview in context
