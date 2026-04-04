# Agents

Specialized agent personas that bring focused expertise to specific tasks. Agents define HOW Claude thinks, while commands define WHAT Claude does.

## Mental Model

```
┌─────────────┬─────────────────────────────────────────────────────┐
│  LAYER      │  PURPOSE                                            │
├─────────────┼─────────────────────────────────────────────────────┤
│  Agents     │  Personas - HOW to think (priorities, patterns)    │
│  Commands   │  Actions - WHAT to do (steps, outputs)             │
│  Skills     │  Knowledge - Domain expertise loaded on-demand     │
│  Rules      │  Invariants - Constraints that always apply        │
└─────────────┴─────────────────────────────────────────────────────┘
```

## Available Agents

| Agent                  | Purpose                             | Auto-Activates                     |
| ---------------------- | ----------------------------------- | ---------------------------------- |
| `planner`              | Break features into atomic stories  | `/create-plan`                     |
| `architect`            | System design, trade-offs, diagrams | `@architect` explicit              |
| `tdd-guide`            | Test-first implementation           | `Test` items in Plan               |
| `code-reviewer`        | Quality, patterns, maintainability  | `/pre-pr-check`, `/review`         |
| `security-reviewer`    | OWASP, vulnerabilities, secrets     | `/pre-pr-check`, `/security-check` |
| `build-error-resolver` | Fix lint/type/test failures         | Verification failures              |
| `e2e-runner`           | Playwright test execution           | `E2E` items in Plan                |
| `refactor-cleaner`     | Dead code removal, simplification   | `Refactor` items                   |
| `doc-updater`          | Keep docs in sync with code         | `Docs` items                       |
| `visual-verifier`      | Browser-based visual QA             | `UI` items in Plan, `/verify-visual` |
| `orchestrator`         | Multi-step task coordination        | `/orchestrate`, multi-file changes |
| `deployer`             | Migration-aware deploy orchestration| `Deploy` items in Plan, `/deploy`  |

## Invocation

### Automatic (Context-Based)

Agents auto-load based on Plan item type or command context:

```
/iterate on "Test: Add login tests"
    → tdd-guide.md auto-loads

/pre-pr-check
    → code-reviewer.md + security-reviewer.md auto-load

Verification fails during /iterate
    → build-error-resolver.md auto-loads
```

### Explicit

Invoke an agent directly for focused work:

```
@architect      # Enter architect mode
@code-reviewer  # Review current changes
@tdd-guide      # Get TDD guidance
```

## Agent Composition

Agents can invoke other agents when needed:

```
@architect designing auth system
    → May invoke @security-reviewer for threat modeling
    → May invoke @planner to break down implementation
```

## Writing Custom Agents

Create `.ai/agents/[name].md` with this structure:

```markdown
# [Agent Name]

[One-line description of the agent's purpose]

## Activation

- **Auto**: [When this agent auto-loads]
- **Explicit**: `@agent-name`

## Persona

[How this agent thinks, what it prioritizes]

## Responsibilities

1. [Primary responsibility]
2. [Secondary responsibility]

## Workflow

[Step-by-step process this agent follows]

## Output Format

[Expected output structure]

## Do NOT

- [Anti-pattern 1]
- [Anti-pattern 2]
```

## Integration with Autonomous Loop

In `/ai-loop` (autonomous) mode, agents are loaded per-iteration based on story type:

```
loop.sh iteration N
    ↓
Read prd.json → story.type = "Test"
    ↓
Load tdd-guide.md
    ↓
Execute story with TDD approach
    ↓
Commit, update progress.txt
    ↓
Exit iteration
```

This ensures each story gets the right expertise without context bloat.
