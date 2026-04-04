---
suggest_when:
  - signal: session_start
    condition: first_session
    message: "New to the toolkit? Run `/guide` for a quick orientation."
  - signal: total_tool_calls
    value: 2
    cooldown: 86400
    message: "Need help finding commands? Try `/guide`."
---

# Guide

Interactive help and command discovery for the AI Dev Toolkit.

## Arguments

`$ARGUMENTS` — optional category or command name:

- _(empty)_ → Quick orientation + category menu
- `getting-started` → First 5 commands to learn
- `planning` → Plan creation and execution
- `development` → Building, testing, debugging
- `review` → Code quality and compliance
- `release` → Commit, PR, deploy
- `session` → Context management and recovery
- `advanced` → Multi-agent, pipelines, orchestration
- `workflows` → Common multi-command recipes
- `all` → Full command reference
- `<command-name>` → Deep dive on a specific command (e.g., `guide iterate`)

## Execution

### Step 1: Parse Arguments

Read `$ARGUMENTS`. Determine the mode:

1. **No arguments** → Show orientation overview
2. **Category name** (matches one of: `getting-started`, `planning`, `development`, `review`, `release`, `session`, `advanced`, `workflows`, `all`) → Show that category
3. **Command name** (e.g., `iterate`, `tdd`, `create-plan`) → Show deep dive on that command
4. **Unknown** → Show "did you mean?" with closest category/command match

### Step 2: Command Registry

Use this category mapping to organize commands. Each entry is `command-name: one-line summary`.

```yaml
getting-started:
  title: "Getting Started"
  description: "The 5 commands every developer should learn first."
  commands:
    verify: "Run lint, typecheck, and tests in one shot"
    create-plan: "Break a feature into atomic, executable stories"
    iterate: "Execute plan stories with automatic checkpointing"
    create-commit: "Generate a conventional commit with pre-checks"
    guide: "You're here — discover commands and workflows"

planning:
  title: "Planning & Execution"
  description: "Go from idea to structured implementation."
  commands:
    create-plan: "Create implementation plan with checklist (supports --from-prd)"
    plan: "Quick implementation planning: tasks, risks, acceptance criteria"
    iterate: "Execute plan items in batches with checkpointing"
    ai-loop: "Autonomous execution loop (supports --tui dashboard)"
    kickoff: "Initialize session, read project context"
    plan-status: "Show active plans, file claims, detect conflicts"
    summarize: "Generate pyramid summaries for progressive context loading"

development:
  title: "Development"
  description: "Build, test, and debug your code."
  commands:
    verify: "Quick lint, typecheck, tests (supports --visual)"
    tdd: "Test-driven development: RED → GREEN → IMPROVE"
    debug: "Hypothesis-driven debugging workflow"
    debug-browser: "Interactive browser debugging via Playwright MCP"
    verify-visual: "Browser-based visual verification with screenshots"
    scrap: "Discard current approach and restart elegantly"
    init: "Generate project CLAUDE.md from template"
    create-skill: "Scaffold new skill files following toolkit patterns"
    token-budget: "Check toolkit component token costs"
    ai-loop-test: "Sanity-check loop infrastructure without AI calls"

review:
  title: "Review & Quality"
  description: "Validate code quality, security, and compliance."
  commands:
    pre-pr-check: "Full pre-PR validation (git, complexity, security, a11y). Use --deep for thorough audits"
    review: "Code review with accessibility + design checks"
    design-check: "Design system compliance audit"
    rams: "Accessibility & visual design audit"
    security-scan: "OWASP Top 10 audit"
    security-check: "Security scan for secrets and vulnerabilities"
    compliance-check: "Skills/patterns + code complexity validation"
    techdebt: "Find duplicated code, redundant helpers, missed abstractions"
    deslop: "Remove AI-generated code artifacts from current branch"
    docs-check: "Audit CLAUDE.md and README.md for drift"
    check-agent-readiness: "Audit repo readiness for autonomous agents"
    dogfood: "Systematic exploratory QA for web apps"

release:
  title: "Release"
  description: "Ship your code with confidence."
  commands:
    create-commit: "Generate conventional commit (runs pre-checks first)"
    pre-commit-check: "Verify test coverage, techdebt, docs, token budgets"
    create-pr: "Generate PR with structured sections"
    deploy: "Deploy to Vercel with preview URL"
    version: "Show toolkit version, check for updates"
    update-toolkit: "Update toolkit from remote repository"

session:
  title: "Session Management"
  description: "Manage context, recover state, and track progress."
  commands:
    catchup: "Narrative session recovery after /clear or new session"
    remind: "Quick session recap: goal, completed, pending, next"
    status: "Show git state and progress"
    checkpoint: "Save session progress (decisions, files, pending items)"
    mode: "Switch context mode: dev, review, debug, deploy, research, orchestrate"
    dashboard: "Cross-project status dashboard"
    tasks-cleanup: "Archive completed tasks"
    monitor: "Launch TUI dashboard for agent monitoring"

advanced:
  title: "Advanced"
  description: "Multi-agent coordination and parallel execution."
  commands:
    multitask: "Parallel worktree instances for concurrent development"
    pipeline: "Graph-based pipeline runner for dependent task orchestration"
    orchestrate: "Launch multitask workflow from PRD or task list"
    worktree: "Create isolated git worktree with branch and deps"

learning:
  title: "Learning & Memory"
  description: "Capture patterns and build institutional knowledge."
  commands:
    learn: "Extract reusable patterns, stage for promotion"
    evolve: "Review staged learnings, propose permanent promotions"
    wrap-up: "End session: summarize work, extract learnings"
    memory-clean: "Archive old memory entries (default 30 days)"
    log-skill: "Emit skill_used event for ACS tracking"
```

### Step 3: Render Output

Based on the mode determined in Step 1, render the appropriate output.

#### Mode: Overview (no arguments)

Output this orientation:

```markdown
## AI Dev Toolkit — Quick Guide

**Core loop**: Plan → Build → Verify → Commit → PR

| Start here         | Command          | What it does                                   |
|---------------------|------------------|------------------------------------------------|
| 1. Plan your work   | `/create-plan`   | Break a feature into atomic stories            |
| 2. Execute stories  | `/iterate`       | Work through stories with auto-checkpointing   |
| 3. Check your work  | `/verify`        | Lint + typecheck + tests in one shot           |
| 4. Commit           | `/create-commit` | Conventional commit with pre-flight checks     |
| 5. Ship it          | `/create-pr`     | PR with structured summary                     |

**Browse by category:**

| Category       | Command               | Examples                                    |
|----------------|-----------------------|---------------------------------------------|
| Planning       | `/guide planning`     | create-plan, iterate, ai-loop               |
| Development    | `/guide development`  | verify, tdd, debug                          |
| Review         | `/guide review`       | pre-pr-check, security-scan, design-check   |
| Release        | `/guide release`      | create-commit, create-pr, deploy            |
| Session        | `/guide session`      | catchup, checkpoint, remind, mode           |
| Advanced       | `/guide advanced`     | multitask, pipeline, orchestrate            |
| Learning       | `/guide learning`     | learn, evolve, wrap-up                      |
| Workflows      | `/guide workflows`    | Common multi-command recipes                |
| All commands   | `/guide all`          | Full reference (53 commands)                |

**Deep dive**: `/guide <command>` — e.g., `/guide iterate` for details on any command.

**Context modes**: `/mode dev|review|debug|deploy|research|orchestrate` — switches Claude's behavior.

**Pro tip**: The toolkit auto-suggests commands as you work. Just start coding and it will nudge you when a command fits.
```

#### Mode: Category

For the requested category, render:

```markdown
## {category.title}

{category.description}

| Command | What it does |
|---------|-------------|
| `/{command}` | {summary} |
...for each command in the category...

**Deep dive**: `/guide <command>` for full details on any command above.
```

#### Mode: Workflows

Render these common workflow recipes:

```markdown
## Common Workflows

### New Feature (Structured)
~~~
/create-plan          ← Break feature into stories
/iterate              ← Execute stories in batches
/verify               ← Check lint/types/tests
/create-commit        ← Commit with conventional format
/create-pr            ← Ship with structured PR
~~~

### Quick Bug Fix
~~~
/debug                ← Hypothesis-driven debugging
/verify               ← Confirm the fix
/create-commit        ← Commit the fix
~~~

### Test-Driven Development
~~~
/tdd                  ← RED: write failing test
                        GREEN: minimal implementation
                        IMPROVE: refactor + coverage
/verify               ← Final check
/create-commit        ← Commit
~~~

### Code Review Prep
~~~
/pre-pr-check         ← Full validation (or --deep)
/deslop               ← Remove AI-generated artifacts
/design-check         ← Design system compliance (if UI)
/create-pr            ← Generate PR
~~~

### Autonomous Execution
~~~
/create-plan          ← Define the work
/ai-loop              ← Let it run autonomously
/ai-loop --tui        ← ...with visual dashboard
/monitor              ← Watch progress
~~~

### Parallel Development
~~~
/multitask --from plan.md    ← Spawn parallel worktrees
/dashboard                    ← Monitor all worktrees
/pipeline                     ← For dependent task graphs
~~~

### Session Recovery
~~~
/catchup              ← Full narrative recovery
/remind               ← Quick recap
/dashboard            ← Cross-project status
~~~

### End of Session
~~~
/learn                ← Extract reusable patterns
/wrap-up              ← Summarize and archive
/checkpoint           ← Save progress snapshot
~~~

### First Time in a Repo
~~~
/init                 ← Generate CLAUDE.md
/check-agent-readiness ← Audit repo for agent use
/guide                ← Learn available commands
~~~
```

#### Mode: Command Deep Dive

For a specific command:

1. Read the command file from `.claude/commands/{command-name}.md`
2. Extract:
   - **Title**: First `#` heading
   - **Summary**: First paragraph after heading
   - **Arguments/Flags**: Look for `## Arguments` or `$ARGUMENTS` section
   - **Suggest triggers**: From frontmatter `suggest_when`
3. Present as:

```markdown
## /{command-name}

{summary}

**Usage**: `/{command-name} {arguments if any}`

**Flags**: {extracted flags or "None"}

**Auto-suggested when**: {translated suggest_when triggers, or "Manual only"}

**Category**: {which category this command belongs to}

**Related commands**: {other commands in the same category}
```

If the command file references agents, skills, or other commands, mention those connections.

#### Mode: All

Render every category in sequence (compact table format), then a count:

```markdown
## All Commands ({count} total)

### {category.title}
| Command | Summary |
...

(repeat for each category)
```

#### Mode: Unknown Argument

If `$ARGUMENTS` doesn't match a category or command name:

```markdown
I don't recognize `{argument}`.

**Did you mean one of these?**
- `/guide {closest-category}` — {category description}
- `/{closest-command}` — {command summary}

Run `/guide` for the full category list.
```

### Step 4: Suggested Next

After rendering any mode, add a contextual "what's next" suggestion based on the current session state:

- If no plan exists: "Consider `/create-plan` to structure your next feature."
- If plan exists with pending items: "You have pending stories — run `/iterate` to continue."
- If many uncommitted edits: "You have uncommitted changes — run `/create-commit` to checkpoint."
- If no suggestion fits, omit this section.

## Suggested Next

After using `/guide`:
- `/kickoff` — Full session initialization with project context
- `/create-plan` — Start planning a feature
- `/mode` — Switch to a context mode that fits your task
