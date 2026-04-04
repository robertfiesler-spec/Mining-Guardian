---
suggest_when:
  - signal: edits_since_commit
    value: 15
    cooldown: 45
    message: "Long session — `/learn` to extract reusable patterns before context clears"
  - signal: session_start
    condition: staged_learnings
    message: "Staged learnings from last session — run `/learn` or `/evolve` to promote them"
---

# /learn - Extract and Document Learnings

Capture mistakes, patterns, and reusable insights from the current session. Feeds the "thin skills, fat memory" approach.

## Usage

```
/learn [options]
```

$ARGUMENTS

## Your Task

Extract learnings mid-session and persist them. Two modes: **mistake** (correction becomes a rule) and **pattern** (reusable insight staged for review).

## Mode 1: Mistake Correction (Default)

When a human corrects your work, that correction becomes a permanent rule.

### Step 1: Gather Information

If not provided as arguments, ask:

1. **What happened?** — Brief description of the mistake
2. **What should have happened?** — The correct behavior
3. **Why did it happen?** — Root cause (if known)

### Step 2: Categorize

| Category | Location in CLAUDE.md |
|----------|----------------------|
| TypeScript | `### TypeScript` |
| React/Next.js | `### React/Next.js` |
| Code Style | `### Code Style` |
| Security | `### Security (Always Apply)` |
| Git/Commits | `### Git Commits` |
| Documentation | `### Documentation (Always Update)` |
| Testing | `rules/testing.md` |
| Page Layout | `### Page Patterns` (project CLAUDE.md) or `rules/design-system/page-patterns.md` (global) |
| Workflow | `## Workflow` |

### Step 3: Formulate the Rule

Convert to an actionable imperative:

```markdown
# Good (specific, actionable)
- ALWAYS update CLAUDE.md and README.md when adding new commands
- NEVER use outline-none without providing focus-visible replacement

# Bad (vague)
- Remember to update docs
```

### Step 4: Add to CLAUDE.md

Read CLAUDE.md, add the rule to the appropriate section. Confirm:

```
Added to CLAUDE.md (### [Section]):
- [The new rule]
```

### Step 5: Store in ACS (if available)

If `ACS_URL` is configured, also persist to cross-project memory:

```bash
if [[ -n "${ACS_URL:-}" ]]; then
  source ~/.claude/scripts/lib/acs-client.sh
  if acs_is_available; then
    acs_store "[RULE TEXT]" "insight" "/learn" "$(basename $(pwd))"
  fi
fi
```

## Mode 2: Pattern Extraction (`--pattern`)

Identify reusable patterns from current work and stage for review.

### Step 1: Identify the Pattern

Analyze the current session for:

- **Repeated approaches** — same technique used 2+ times
- **Novel solutions** — creative approaches worth remembering
- **Integration patterns** — how services/modules were connected
- **Error recovery** — debugging strategies that worked

### Step 2: Stage for Review

Write the pattern to `.ai/memory/staging/`:

```bash
mkdir -p .ai/memory/staging
```

**Path**: `.ai/memory/staging/[YYYYMMDD]-[pattern-name].json`

```json
{
  "id": "learn-[unique-id]",
  "pattern": "[Pattern name]",
  "category": "[component | data-flow | error-handling | testing | integration]",
  "source": "[file or feature where discovered]",
  "problem": "[What situation this pattern addresses]",
  "solution": "[The pattern — brief description]",
  "code_example": "[Optional code snippet]",
  "when_to_use": ["Situation 1", "Situation 2"],
  "when_not_to_use": ["Anti-pattern situation"],
  "proposed_rule": "[Concise rule text if promoting to rule]",
  "proposed_target": "[skill-name | rules/file.md | memory-only]",
  "first_seen": "[ISO-8601 timestamp]",
  "last_seen": "[ISO-8601 timestamp]",
  "usage_count": 1,
  "failures": 0,
  "confidence": 0.7,
  "promoted": false
}
```

### Step 3: Propose Skill/Rule Addition

If the pattern is significant enough:

```markdown
## Pattern Staged

**File**: `.ai/memory/staging/[filename]`
**Category**: [category]

**Recommendation**: [one of]
- Add to skill `[name]` — detailed guidance with examples
- Add to rule `rules/[name].md` — concise always-apply constraint
- Keep as memory — useful but not universal enough for a rule

Would you like me to add this to a skill or rule now?
```

## Step 6: Confirm and Summarize (Both Modes)

```markdown
## Learning Captured

**Type**: [Mistake Rule | Pattern]
**Summary**: [Brief description]
**Stored**: [CLAUDE.md / .ai/memory/staging/ / rules/]

This [will prevent future mistakes | is staged for review].
```

## Arguments

| Argument | Description |
|----------|-------------|
| `--mistake "[text]"` | Pre-specify the mistake description |
| `--rule "[text]"` | Pre-specify the rule to add |
| `--category [name]` | Pre-specify the category |
| `--pattern` | Pattern extraction mode (not mistake) |
| `--quick` | Skip confirmation, add directly |

## Integration

| Trigger | Behavior |
|---------|----------|
| `/iterate` human correction | Prompts: "Run `/learn` to document this?" |
| `/wrap-up` | Reviews session for learnings to extract |
| `/ai-loop` failure | Logs suggestion in progress.txt |
| `/pre-pr-check` fixed issues | Suggests documenting as rule |

## Examples

```bash
# Mistake correction (default)
/learn --mistake "Forgot README update when adding /rams command"

# Quick rule add
/learn --quick --rule "Always sync commands to both directories"

# Pattern extraction
/learn --pattern

# Fully specified mistake
/learn --mistake "Used outline-none without focus" --category "Code Style" \
  --rule "NEVER use outline-none without focus-visible:ring replacement"
```

## Related

- `CLAUDE.md` — where rules are stored
- `rules/` — detailed guidance files
- `.ai/memory/staging/` — staged patterns for review
- `.ai/memory/learnings/` — session learnings from `/wrap-up`
- `/wrap-up` — end-of-session learning extraction

## Suggested Next

| If... | Run |
|-------|-----|
| Enough learnings accumulated for promotion | `/evolve` — review staged patterns and promote to permanent rules |
| Back to implementation work | `/iterate` — continue executing plan items |
