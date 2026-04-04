# Catchup (Redirect)

This command is an alias for `/status --history --tasks`.

$ARGUMENTS

## Behavior

Map arguments and delegate:

| Catchup Flag | Status Equivalent |
|---|---|
| (none) | `/status --history --tasks` |
| `--brief` | `/status --history --tasks --brief` |
| `--sessions N` | `/status --history --tasks --sessions N` |
| `--all` | `/dashboard` |

**Run the equivalent `/status` command now.** Follow the `/status` command instructions exactly — do not duplicate logic here.

## Suggested Next

| If... | Run |
|-------|-----|
| Resume the active plan | `/iterate` — execute plan items in batches |
| Start a new plan | `/create-plan` — break feature into stories |
| Commit uncommitted changes | `/create-commit` — generate a conventional commit |
| See all projects | `/dashboard` — cross-project status |
