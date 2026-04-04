---
suggest_when:
  - signal: total_tool_calls
    value: 40
    cooldown: 60
    message: "Context growing large — `/token-budget` to check which toolkit components are heaviest"
  - signal: edits_since_commit
    value: 20
    cooldown: 60
    message: "Long session — `/token-budget` to verify context costs before continuing"
---

# Token Budget

Check toolkit component token costs against configured budgets. Prevents context bloat by measuring every command, agent, skill, and rule file.

## Your Task

Run the token budget check and display results.

$ARGUMENTS

## Step 1: Locate Script

```bash
# Detect script location
if [ -f ".claude/scripts/token-budget.sh" ]; then
  BUDGET_SCRIPT=".claude/scripts/token-budget.sh"
elif [ -f "$HOME/.claude/scripts/token-budget.sh" ]; then
  BUDGET_SCRIPT="$HOME/.claude/scripts/token-budget.sh"
elif [ -f "./scripts/token-budget.sh" ]; then
  BUDGET_SCRIPT="./scripts/token-budget.sh"
fi
```

If script not found, inform the user to run `./scripts/install.sh` or `./scripts/update.sh --global`.

## Step 2: Execute Based on Arguments

| Argument | Action |
|----------|--------|
| (none) | Run `--report` for full human-readable output |
| `--json` | Run `--json` for machine-readable output |
| `--save-baseline` | Save current measurements as baseline snapshot |
| `--compare` | Compare current state against saved baseline |
| `--verbose` | Show per-file token counts (all files, not just warnings) |
| `--component <type>` | Only check one type: `commands`, `agents`, `skills`, `rules` |

## Step 3: Interpret Results

After running, summarize the results:

- **FAIL**: Component exceeds its token budget. Should be fixed before commit.
- **WARN**: Component is approaching its budget (80%+ by default). Worth noting.
- **OK**: Within budget.

If there are failures or warnings, suggest specific actions:
- For oversized commands: "Consider splitting this command or removing verbose examples"
- For oversized rules: "Consider moving detailed examples to the corresponding skill file"
- For aggregate overages: "The total across all files in this category is growing; audit for redundancy"

## Arguments

| Argument | Description |
|----------|-------------|
| `--json` | Machine-readable JSON output |
| `--save-baseline` | Save current snapshot as baseline |
| `--compare` | Compare against saved baseline |
| `--verbose` | Show all files, not just warnings/failures |
| `--component <type>` | Only check: `commands`, `agents`, `skills`, `rules` |

## Thresholds

Configured in `config.json` under `tokenBudget.thresholds`:

| Component | Default Budget | Rationale |
|-----------|---------------|-----------|
| CLAUDE.md | 8,000 tk | Always loaded; keep lean |
| Command | 8,000 tk | Loaded per invocation |
| Agent | 4,000 tk | Persona + checklist |
| Skill | 4,000 tk | On-demand reference |
| Rule | 3,000 tk | Always loaded; must be concise |
| Hook config | 2,000 tk | Always loaded |

## Related Commands

| Command | Use |
|---------|-----|
| `/pre-commit-check` | Includes token budget as Step 7 |
| `/compliance-check` | Broader code quality checks |

## Suggested Next

- `/pre-commit-check` — full pre-commit validation (includes token budget)
- `/compliance-check` — broader code quality checks
- `/create-commit` — commit after optimizing for budget
