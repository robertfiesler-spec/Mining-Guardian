---
suggest_when:
  - signal: edits_since_commit
    value: 20
    cooldown: 60
    message: "Large AI-assisted session — `/deslop` to remove unnecessary comments and defensive code"
  - signal: file_extension
    value: ".tsx"
    min_edits: 8
    cooldown: 45
    message: "Many component edits — `/deslop` to clean up AI-generated patterns before committing"
---

# Deslop

Remove AI-generated code patterns ("slop") introduced in the current branch.

## Your Task

Compare the current branch against its parent branch (auto-detected) and remove AI-generated artifacts that are inconsistent with the codebase's existing style and practices.

$ARGUMENTS

## What to Remove

### Unnecessary Comments

- Explanatory comments for self-evident code
- Comments that describe "what" instead of "why"
- JSDoc/docstrings added to unchanged code
- Comments inconsistent with the rest of the file's commenting style

### Defensive Overkill

- Try/catch blocks around code that can't throw or is already in a trusted path
- Null checks for values that are guaranteed by the type system
- Validation on internal function calls (not at trust boundaries)
- Redundant error handling that duplicates framework behavior

### Type Workarounds

- Casts to `any` to bypass type errors
- `as unknown as T` chains
- `@ts-ignore` or `@ts-expect-error` without justification
- Overly loose types where stricter ones exist

### Style Inconsistencies

- Naming conventions that don't match the file
- Import organization that differs from existing patterns
- Formatting choices inconsistent with the codebase
- Abstractions or helpers for one-time operations

## Process

1. **Detect base branch** - Find the branch this branch was forked from:
   ```bash
   # Find fork point against common base branches
   for branch in main master staging develop; do
     git merge-base HEAD "origin/$branch" 2>/dev/null
   done
   # Use the branch with the most recent common ancestor
   ```
2. **Get the diff** against the detected base branch
3. **Scan** each changed file for slop patterns
4. **Compare** against unchanged code in the same file to understand local style
5. **Remove** artifacts that don't match the codebase conventions
6. **Report** a brief summary of changes

## Output Format

After completing all changes, output only:

```
## Deslop Complete

[1-3 sentence summary of what was changed]
```

Do not list individual files or changes unless `--verbose` is passed.

## Arguments

- `--verbose` - List each file and what was changed
- `--dry-run` - Report what would be changed without modifying files
- `--base <branch>` - Override auto-detection and compare against a specific branch

## Suggested Next

- `/create-commit` — commit the cleaned-up code
- `/pre-pr-check` — full pre-PR validation after deslop pass
- `/compliance-check` — verify code quality metrics after cleanup
