---
suggest_when:
  - signal: edits_since_commit
    value: 10
    cooldown: 30
    message: "Added or changed features? `/docs-check` audits CLAUDE.md and README.md for drift vs actual files"
  - signal: session_start
    condition: incomplete_plan
    cooldown: 90
    message: "Working on features? `/docs-check` catches phantom entries and undocumented items before they ship"
---

# Docs Check

Audit documentation (CLAUDE.md, README.md, and related docs) for accuracy, consistency, and drift from the actual codebase. Works in both the ai-toolkit source repo and any project repo.

## Usage

```
/docs-check [options]
```

Options:
- `--fix` — Auto-fix issues found (add missing entries, remove phantom entries)
- `--section <name>` — Check only a specific section (see mode-specific sections below)
- `--verbose` — Show passing checks too, not just failures

$ARGUMENTS

## Step 0: Detect Mode

Determine whether you're in the **ai-toolkit source repo** or a **project repo**:

```bash
# Check if this is the ai-toolkit source repo
if [ -d "commands" ] && [ -d "skills" ] && [ -d "agents" ] && [ -f "config.json" ] && grep -q '"repository".*ai-toolkit' config.json 2>/dev/null; then
  echo "MODE: toolkit"
else
  echo "MODE: project"
fi
```

- **Toolkit mode**: Audit toolkit-specific directories (commands/, agents/, skills/, hooks/, rules/, contexts/) against CLAUDE.md and README.md. This is the original behavior.
- **Project mode**: Audit project documentation against the actual codebase. Checks that README.md, CLAUDE.md, and any agents/rules files accurately describe the project.

**Route to the appropriate section below based on mode.**

---

# TOOLKIT MODE

> Only runs when inside the ai-toolkit source repo.

## Toolkit Step 1: Inventory Actual Files

Scan the filesystem to build ground-truth inventories:

**Commands** — list all `.md` files in `commands/`:
```bash
ls commands/*.md | sed 's|commands/||; s|\.md||' | sort
```

**Agents** — list all `.md` files in `agents/` (exclude README):
```bash
ls agents/*.md | grep -v README | sed 's|agents/||; s|\.md||' | sort
```

**Skills** — list all skill directories in `skills/`:
```bash
ls -d skills/*/ | sed 's|skills/||; s|/||' | sort
```

**Hooks** — list all hook scripts:
```bash
# Bash hooks
ls hooks/pre-tool-use/ hooks/post-tool-use/ hooks/stop/ 2>/dev/null | grep -v README | sort
# Node.js hooks
ls hooks/scripts/*.js 2>/dev/null | sed 's|hooks/scripts/||' | sort
```

**Rules** — list all rule files:
```bash
find rules/ -name '*.md' | sed 's|rules/||' | sort
```

**Contexts** — list all context files:
```bash
ls contexts/*.md 2>/dev/null | sed 's|contexts/||; s|\.md||' | sort
```

## Toolkit Step 2: Parse CLAUDE.md Tables

Read `CLAUDE.md` and extract every item listed in these sections:

| Section | What to Extract |
|---------|----------------|
| **Available Commands** | All command names from the table and descriptions |
| **Available Agents** | All agent names from the table |
| **Available Skills** | All skill names from the bullet list |
| **Lifecycle Hooks** | All hook names from the table |
| **Context Modes** | All mode names from the table |
| **File References** | All rule files referenced |

Build a structured list for each category.

## Toolkit Step 3: Parse README.md Tables

Read `README.md` and extract every item listed in these sections:

| Section | What to Extract |
|---------|----------------|
| **Commands Reference** (all subsections) | All command names and descriptions |
| **Hooks** | All hook names |
| **File Structure** | All files/directories shown in the tree |
| **Core Concepts** table | Items listed |

Build a structured list for each category.

## Toolkit Step 4: Cross-Reference — Files vs CLAUDE.md

For each category, compare the filesystem inventory (Step 1) against CLAUDE.md entries (Step 2):

### 4.1 Commands
- **Undocumented**: Files in `commands/` not listed in CLAUDE.md's Available Commands table
- **Phantom**: Commands listed in CLAUDE.md but no corresponding file in `commands/`
- **Deprecated markers**: Commands marked with ~~strikethrough~~ — verify the deprecation note is accurate

### 4.2 Agents
- **Undocumented**: Files in `agents/` not listed in CLAUDE.md's Available Agents table
- **Phantom**: Agents listed in CLAUDE.md but no corresponding file in `agents/`

### 4.3 Skills
- **Undocumented**: Directories in `skills/` not listed in CLAUDE.md's Available Skills list
- **Phantom**: Skills listed in CLAUDE.md but no corresponding directory in `skills/`

### 4.4 Hooks
- **Undocumented**: Hook scripts not listed in CLAUDE.md's Lifecycle Hooks table
- **Phantom**: Hooks listed in CLAUDE.md but no corresponding script file

### 4.5 Rules
- **Undocumented**: Rule files not referenced in CLAUDE.md's File References section
- **Phantom**: Rules referenced in CLAUDE.md but no corresponding file in `rules/`

### 4.7 Command Suggestion Coverage
Check that commands include suggestion system integration:

```bash
# Commands missing suggest_when frontmatter
for f in commands/*.md; do
  name=$(basename "$f" .md)
  # Skip CLAUDE.md, deprecated commands, and meta-commands
  [[ "$name" == "CLAUDE" || "$name" == "catchup" || "$name" == "create-todo" ]] && continue
  if ! head -1 "$f" | grep -q '^---'; then
    echo "MISSING frontmatter: $name"
  elif ! grep -q 'suggest_when' "$f"; then
    echo "MISSING suggest_when: $name"
  fi
done

# Commands missing Suggested Next section
for f in commands/*.md; do
  name=$(basename "$f" .md)
  [[ "$name" == "CLAUDE" || "$name" == "catchup" || "$name" == "create-todo" ]] && continue
  if ! grep -q '## Suggested Next' "$f"; then
    echo "MISSING Suggested Next: $name"
  fi
done
```

- **Missing `suggest_when`**: Commands without frontmatter triggers won't be suggested by the hook system
- **Missing `## Suggested Next`**: Commands without next-step guidance break the suggestion chain

### 4.6 Contexts
- **Undocumented**: Context files not listed in CLAUDE.md's Context Modes table
- **Phantom**: Contexts listed in CLAUDE.md but no corresponding file in `contexts/`

## Toolkit Step 5: Cross-Reference — Files vs README.md

Repeat the same comparison against README.md entries (Step 3):

### 5.1 Commands
- **Undocumented**: Commands in `commands/` not in any README Commands Reference table
- **Phantom**: Commands in README but no file exists

### 5.2 Hooks
- **Undocumented**: Hook scripts not in README's Hooks tables
- **Phantom**: Hooks in README but no script exists

### 5.3 File Structure Tree
- **Missing from tree**: Important files/directories that exist but aren't shown in the File Structure section
- **Phantom in tree**: Files shown in the tree that don't actually exist

## Toolkit Step 6: Cross-Reference — CLAUDE.md vs README.md

Compare the two documentation files against each other:

### 6.1 Command Consistency
For every command listed in CLAUDE.md's Available Commands:
- Is it also in README.md's Commands Reference?
- Do the descriptions roughly match (not contradictory)?

For every command in README.md's Commands Reference:
- Is it also in CLAUDE.md's Available Commands?

### 6.2 Agent Consistency
- Agents listed in CLAUDE.md should be mentioned in README.md (at minimum in the File Structure or Core Concepts)

### 6.3 Skill Consistency
- Skills listed in CLAUDE.md should appear in README.md

### 6.4 Hook Consistency
- Hooks listed in CLAUDE.md should match README.md's Hooks section

## Toolkit Step 7: Description Accuracy Spot-Check

For up to 5 commands (prioritize recently modified files), read the actual command file and compare:
- Does the CLAUDE.md description accurately reflect what the command does?
- Does the README.md description accurately reflect what the command does?
- Are any flags/options mentioned in docs that don't exist in the command, or vice versa?

```bash
# Find 5 most recently modified commands
ls -t commands/*.md | head -5
```

**Skip to Step 8 (Report).**

---

# PROJECT MODE

> Runs in any project repo that is NOT the ai-toolkit source.

## Project Step 1: Discover Documentation Files

Find all documentation files in the project:

```bash
# Primary docs
ls -la CLAUDE.md README.md .claude/CLAUDE.md 2>/dev/null

# Agent definitions
ls .claude/agents/*.md 2>/dev/null
ls agents/*.md 2>/dev/null

# Rule files
ls .claude/rules/*.md 2>/dev/null
find . -name 'AGENTS.md' -not -path '*/node_modules/*' 2>/dev/null
```

Build a list of which doc files exist. Adapt remaining checks to only cover files that exist.

## Project Step 2: Audit README.md

If `README.md` exists, check the following:

### 2.1 Scripts & Commands
Extract any `npm run`, `yarn`, `pnpm`, `bun` commands mentioned in README. Cross-reference against `package.json` scripts:

```bash
# Get actual scripts from package.json
cat package.json | grep -A 100 '"scripts"' | grep -B 100 '^\s*}'
```

- **Phantom scripts**: Commands documented in README that don't exist in package.json
- **Undocumented scripts**: Important scripts in package.json not mentioned in README (focus on: dev, build, test, lint, start, deploy — skip pre/post hooks and internal scripts)

### 2.2 File Structure / Architecture
If README contains a file/directory tree or architecture section:
- Verify that referenced directories exist
- Verify that referenced key files exist
- Flag phantom paths that don't exist

```bash
# Quick check: extract paths from code blocks and verify
# Look for tree-style blocks or file path references
```

### 2.3 API Routes
If the project uses Next.js App Router or similar, check documented API routes against actual route files:

```bash
# Next.js App Router
find app -name 'route.ts' -o -name 'route.js' 2>/dev/null | sort
# Pages API
find pages/api -name '*.ts' -o -name '*.js' 2>/dev/null | sort
```

- **Phantom routes**: API routes documented but files don't exist
- **Undocumented routes**: Route files that exist but aren't mentioned anywhere in docs

### 2.4 Environment Variables
If README documents environment variables (often in a "Setup" or "Configuration" section):
- Cross-reference against `.env.example` or `.env.local.example` if they exist
- Check for env vars used in code (grep for `process.env.`) that aren't documented

```bash
# Env vars in example files
cat .env.example .env.local.example 2>/dev/null | grep -v '^#' | grep '=' | cut -d= -f1 | sort
# Env vars used in code
grep -r 'process\.env\.' --include='*.ts' --include='*.tsx' --include='*.js' -h | grep -oP 'process\.env\.(\w+)' | sort -u
```

### 2.5 Tech Stack Claims
If README lists technologies/dependencies:
- Verify major dependencies are actually in package.json
- Flag any mentioned libraries that aren't installed

## Project Step 3: Audit CLAUDE.md

If a project-level CLAUDE.md exists (at root or `.claude/CLAUDE.md`), check:

### 3.1 File References
Extract all file paths mentioned in CLAUDE.md. Verify each exists:
- Rule files (e.g., `rules/security.md`)
- Configuration files
- Key source files referenced as examples

### 3.2 Stack Context
If CLAUDE.md declares a stack (framework, language, styling, testing):
- Verify against package.json dependencies
- Flag contradictions (e.g., says "Tailwind" but tailwind isn't installed)

### 3.3 Commands & Scripts
If CLAUDE.md references shell commands or scripts:
- Verify referenced scripts exist
- Verify referenced npm scripts exist in package.json

### 3.4 Directory Conventions
If CLAUDE.md describes directory conventions (e.g., "components go in `features/*/components/`"):
- Spot-check that the convention is actually followed (check 2-3 examples)
- Flag if the documented convention contradicts reality

## Project Step 4: Audit Agent & Rule Files

### 4.1 Agent Files
If `.claude/agents/` or `agents/` exists:
- Read each agent file
- Verify any file paths or tools they reference exist
- Check that agent names in CLAUDE.md match actual agent files

### 4.2 Rule Files
If `.claude/rules/` or `rules/` exists:
- Verify files referenced in CLAUDE.md's File References exist
- Flag phantom references

## Project Step 5: Cross-Reference CLAUDE.md vs README.md

If both files exist:
- **Stack consistency**: Do they agree on the tech stack?
- **Script consistency**: Do they reference the same key commands?
- **Architecture consistency**: Do they describe the same directory structure?
- Flag any contradictions between the two files

## Project Step 6: Freshness Check

Check if docs might be stale:

```bash
# When were docs last modified vs code?
git log -1 --format="%ai" -- README.md 2>/dev/null
git log -1 --format="%ai" -- CLAUDE.md .claude/CLAUDE.md 2>/dev/null
git log -1 --format="%ai" -- 'src/' 'app/' 'lib/' 2>/dev/null
```

- If code was modified significantly more recently than docs (>30 commits apart), flag as **potentially stale**
- Check git log for files added/renamed/deleted since docs were last updated — these are likely undocumented

---

# REPORT (Both Modes)

## Step 8: Generate Report

Output a structured report:

```
# Documentation Audit Report

## Mode: [toolkit | project]

## Summary
- Total issues found: N
- Critical (phantom entries): N
- Warning (undocumented items): N
- Info (inconsistencies / staleness): N

## Critical Issues (Phantom Entries)
Items documented but don't exist — misleading to users/agents.

| Type | Item | Documented In | Issue |
|------|------|---------------|-------|
| ...  | ...  | ...           | ...   |

## Warnings (Undocumented Items)
Items that exist but aren't documented — won't be discovered.

| Type | Item | File Location | Missing From |
|------|------|---------------|-------------|
| ...  | ...  | ...           | ...          |

## Info (Inconsistencies)
Description mismatches, staleness, or drift.

| Item | Source A Says | Source B Says | Suggestion |
|------|-------------- |---------------|------------|
| ...  | ...           | ...           | ...        |

## File Structure Drift
Files/paths referenced in docs that don't exist, or missing from docs.

| Issue | Path | Details |
|-------|------|---------|
| ...   | ...  | ...     |
```

## Step 9: Auto-Fix (if `--fix` flag)

If `--fix` was passed:

### Toolkit Mode Fixes
1. **Add undocumented commands** to CLAUDE.md Available Commands table — read the command file's first line/description to generate the entry
2. **Add undocumented commands** to README.md Commands Reference — place in the most appropriate subsection
3. **Remove phantom entries** — delete table rows for items that don't exist (with confirmation)
4. **Add missing agents/skills/hooks/rules/contexts** — update both files where applicable
5. **Update File Structure tree** in README.md to reflect actual filesystem
6. **Add missing `suggest_when` frontmatter** — read the command to determine the best signal/threshold, add YAML frontmatter block
7. **Add missing `## Suggested Next`** — read the command to determine 2-3 logical next commands, append the section

### Project Mode Fixes
1. **Remove phantom paths** from README.md and CLAUDE.md (file paths, scripts, routes that don't exist)
2. **Add undocumented scripts** to README.md — insert into the appropriate section
3. **Update stack context** in CLAUDE.md to match actual package.json dependencies
4. **Add undocumented env vars** to `.env.example` if it exists
5. **Update file references** in CLAUDE.md to point to files that actually exist

After fixes, re-run the audit steps to verify all issues are resolved.

If `--fix` was NOT passed, end with:

```
Run `/docs-check --fix` to auto-fix these issues.
```

## Suggested Next

- `/create-commit` — commit documentation fixes
- `/pre-pr-check` — full pre-PR validation including docs consistency
- `/compliance-check` — validate code complexity and pattern compliance
