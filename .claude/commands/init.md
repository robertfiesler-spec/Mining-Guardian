---
suggest_when:
  - signal: session_start
    condition: no_agent_context
    message: "No CLAUDE.md found — `/init` generates one from a template for this project type"
---

# /init - Generate Project CLAUDE.md

Generate a project-specific CLAUDE.md from a template, auto-detecting project type and filling in values.

## Usage

```
/init [template-name]
```

$ARGUMENTS

## Arguments

| Argument | Description |
|----------|-------------|
| `[template-name]` | Optional: `nextjs-fullstack`, `api-service`, or `minimal`. Auto-detected if omitted. |
| `--force` | Overwrite existing CLAUDE.md without prompting |
| `--dry-run` | Show what would be generated without writing |

## Your Task

Generate a CLAUDE.md tailored to this project by detecting its type, selecting a template, and filling in project-specific values.

## Step 1: Check for Existing CLAUDE.md

```bash
ls -la CLAUDE.md 2>/dev/null
```

If CLAUDE.md exists and `--force` was not passed:
- Show the first 5 lines of the existing file
- Ask: "CLAUDE.md already exists. Overwrite? (Use `--force` to skip this prompt)"
- Wait for confirmation before proceeding

## Step 2: Detect Project Type

If no template name was provided, auto-detect from project files:

### 2a. Read package.json

```bash
cat package.json 2>/dev/null
```

Extract:
- **Project name**: from `name` field
- **Dependencies**: from `dependencies` and `devDependencies`

### 2b. Detection Rules

Apply these rules in order (first match wins):

| Check | Template |
|-------|----------|
| `next` in dependencies | `nextjs-fullstack` |
| `express` in dependencies | `api-service` |
| `fastify` in dependencies | `api-service` |
| `hono` in dependencies | `api-service` |
| `koa` in dependencies | `api-service` |
| Default (no match) | `minimal` |

### 2c. Detect Commands

Scan `package.json` scripts for common commands:

```bash
node -e "
  const pkg = require('./package.json');
  const scripts = pkg.scripts || {};
  console.log(JSON.stringify({
    name: pkg.name || 'my-project',
    dev: scripts.dev ? 'npm run dev' : '',
    build: scripts.build ? 'npm run build' : '',
    test: scripts.test ? 'npm run test' : '',
    lint: scripts.lint ? 'npm run lint' : '',
    typecheck: scripts.typecheck || scripts['type-check'] ? 'npm run typecheck' : 'npx tsc --noEmit',
    e2e: scripts.e2e || scripts['test:e2e'] ? 'npm run e2e' : '',
    migrate: scripts.migrate || scripts['db:migrate'] ? 'npm run migrate' : ''
  }, null, 2));
"
```

### 2d. Detect Additional Stack Details (api-service only)

If template is `api-service`, also detect:

| Check | Value |
|-------|-------|
| `prisma` in devDependencies | ORM: Prisma |
| `drizzle-orm` in dependencies | ORM: Drizzle |
| `pg` or `postgres` in dependencies | Database: PostgreSQL |
| `mysql2` in dependencies | Database: MySQL |
| `better-sqlite3` in dependencies | Database: SQLite |

### 2e. Report Detection

```
## Project Detected

**Name:** {{name}}
**Template:** {{template}} (auto-detected / specified)
**Reason:** {{detection reason}}

**Commands found:**
- dev: {{dev}}
- build: {{build}}
- test: {{test}}
- lint: {{lint}}
```

## Step 3: Read Template

Read the selected template file:

```bash
cat ~/.claude/templates/{{template}}.md 2>/dev/null || cat templates/{{template}}.md
```

If the template file is not found, report an error:
```
Error: Template "{{template}}" not found.
Available templates: nextjs-fullstack, api-service, minimal
```

## Step 4: Fill Placeholders

Replace all `{{PLACEHOLDER}}` values in the template:

| Placeholder | Source | Fallback |
|-------------|--------|----------|
| `{{PROJECT_NAME}}` | `package.json` name | Directory name |
| `{{PROJECT_DESCRIPTION}}` | `package.json` description | "A TypeScript project" |
| `{{DEV_COMMAND}}` | Detected from scripts | `npm run dev` |
| `{{BUILD_COMMAND}}` | Detected from scripts | `npm run build` |
| `{{TEST_COMMAND}}` | Detected from scripts | `npm run test` |
| `{{LINT_COMMAND}}` | Detected from scripts | `npm run lint` |
| `{{TYPECHECK_COMMAND}}` | Detected from scripts | `npx tsc --noEmit` |
| `{{E2E_COMMAND}}` | Detected from scripts | `npx playwright test` |
| `{{MIGRATE_COMMAND}}` | Detected from scripts | `npx prisma migrate dev` |
| `{{FRAMEWORK}}` | Detected dependency | `Express` |
| `{{DATABASE}}` | Detected dependency | `PostgreSQL` |
| `{{ORM}}` | Detected dependency | `Prisma` |
| `{{AUTH}}` | Detected dependency | `JWT` |
| `{{RUNTIME}}` | Always | `Node.js` |

Also remove the `:-default` fallback syntax from placeholders, so `{{BUILD_COMMAND:-npm run build}}` becomes the resolved value.

## Step 5: Write CLAUDE.md

If `--dry-run` was passed:
- Show the full generated content
- Do NOT write to disk
- Exit

Otherwise, write the filled template to `CLAUDE.md` in the project root:

```bash
# Write will be done via the Edit/Write tool, not bash
```

## Step 6: Report Results

```
## CLAUDE.md Generated

**Template:** {{template}}
**Project:** {{name}}
**Location:** ./CLAUDE.md
**Context Budget:** ~{{N}} instructions

### What's Included
- Stack definition with detected commands
- {{rule_count}} rule references (loaded from rules/)
- {{agent_count}} agent delegation guidelines
- {{skill_count}} on-demand skills
- Workflow with standard /commands

### Next Steps
1. Review the generated CLAUDE.md and customize as needed
2. Add project-specific notes to the `## Notes` section
3. Run `/kickoff` to start a session with this context
```

## Examples

```bash
# Auto-detect project type
/init

# Specify template explicitly
/init nextjs-fullstack

# Preview without writing
/init --dry-run

# Overwrite existing
/init --force

# Specify template with preview
/init api-service --dry-run
```

## Related

- `templates/` -- Template files for each project type
- `CLAUDE.md` -- The generated output
- `/kickoff` -- Initialize a session using the generated CLAUDE.md
- `/learn` -- Add project-specific rules after generation

## Suggested Next

| If... | Run |
|-------|-----|
| CLAUDE.md created, ready to start | `/kickoff` — initialize session with project context |
| Need to plan implementation work | `/create-plan` — break feature into atomic stories |
