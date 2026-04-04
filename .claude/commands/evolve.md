---
suggest_when:
  - signal: session_start
    condition: staged_learnings
    message: "Staged learnings ready for review — `/evolve` proposes promotions to permanent rules"
---
# /evolve - Review Staged Learnings and Propose Promotions

Review accumulated learning entries that have passed the staging gate and propose their promotion into permanent rules or skills.

## Usage

```
/evolve
```

$ARGUMENTS

## Your Task

Read staged learnings from `.ai/memory/staging/`, evaluate each against the promotion criteria, and present qualifying entries as proposed rule/skill additions for human approval.

## Step 1: Load Staged Learnings

```bash
mkdir -p .ai/memory/staging
```

Read all JSON files in `.ai/memory/staging/`. Parse each as a learning entry (see `skills/continuous-learning/SKILL.md` for schema). Skip any with `"promoted": true`.

If no staged entries exist:

```markdown
## No Staged Learnings

No learnings are currently staged for review.

**To stage learnings:**
- `/learn --pattern` — extract a pattern from current work
- `/wrap-up` — scan session for unextracted patterns

Learnings accumulate in `.ai/memory/staging/` over time.
```

## Step 2: Apply Staging Gate

Filter entries by the promotion criteria:

| Criterion | Threshold | Field |
|-----------|-----------|-------|
| Usage count | >= 3 | `usage_count` |
| Time in staging | >= 14 days | `first_seen` to now |
| Failure count | 0 | `failures` |

Separate entries into three groups:

1. **Ready for promotion** — passes all criteria
2. **Maturing** — passes some criteria, needs more time or usage
3. **Blocked** — has failures, needs review or removal

## Step 3: Map Promotion Targets

For each entry ready for promotion, determine the target file:

| Category | Target File |
|----------|-------------|
| typescript | `rules/typescript.md` |
| security | `rules/security.md` |
| testing | `skills/testing/SKILL.md` |
| performance | `rules/code-style.md` (performance section) |
| react | `skills/react-patterns/SKILL.md` |
| accessibility | `skills/accessibility/SKILL.md` |
| page-layout | `rules/design-system/page-patterns.md` or project CLAUDE.md `### Page Patterns` |
| workflow | `CLAUDE.md` (Workflow section) |

Read the target file to find the appropriate insertion point.

## Step 4: Present Proposals

For each entry ready for promotion, show a diff-style proposal:

```markdown
## Promotion Proposals

### 1. [Entry ID] — [Category]

**Pattern**: [pattern description]
**Proposed rule**: [proposed_rule text]
**Evidence**: [usage_count] uses over [days] days, 0 failures
**Confidence**: [confidence]

**Target**: `[target file path]`

**Proposed addition:**

```diff
  ## [Existing Section Header]

  - [Existing rule above]
+ - [New rule from proposed_rule]
  - [Existing rule below]
```

**Action**: [Approve] [Skip] [Reject]

---
```

After all proposals, show the maturing and blocked entries as a summary:

```markdown
## Maturing (not yet ready)

| ID | Pattern | Uses | Days | Failures | Needs |
|----|---------|------|------|----------|-------|
| learn-abc | ... | 2 | 10 | 0 | 1 more use, 4 more days |
| learn-def | ... | 5 | 7 | 0 | 7 more days |

## Blocked (has failures)

| ID | Pattern | Failures | Last Failure |
|----|---------|----------|-------------|
| learn-ghi | ... | 2 | 2026-02-01 |

> Blocked entries can be removed with `/memory-clean` or manually edited in `.ai/memory/staging/`.
```

## Step 5: Apply Approved Promotions

For each approved entry:

1. **Read** the target file
2. **Insert** the new rule at the appropriate location
3. **Update** the staging entry: set `"promoted": true` and add `"promoted_at": "ISO-8601"` and `"promoted_to": "[file path]"`
4. **Confirm** the change

```markdown
## Promotions Applied

- [Entry ID] → `[target file]`: "[rule text]"
- [Entry ID] → `[target file]`: "[rule text]"

**[N] rules promoted. [M] entries still maturing.**
```

For rejected entries, set `"failures": failures + 1` to prevent re-proposal until reviewed.

For skipped entries, leave unchanged — they will appear again next time.

## Step 6: Summary

```markdown
## Evolve Summary

| Status | Count |
|--------|-------|
| Promoted | N |
| Skipped | N |
| Rejected | N |
| Maturing | N |
| Blocked | N |

Next review: Run `/evolve` again after more usage accumulates.
```

## Arguments

| Argument | Description |
|----------|-------------|
| `--dry-run` | Show proposals without applying any changes |
| `--all` | Show all staged entries, not just those passing the gate |
| `--category <name>` | Filter to a specific category |

## Examples

```bash
# Review staged learnings and propose promotions
/evolve

# Preview without making changes
/evolve --dry-run

# See all staged entries including immature ones
/evolve --all

# Review only security-related learnings
/evolve --category security
```

## Related

- `/learn --pattern` — stage new patterns
- `/wrap-up` — extract session learnings
- `/memory-clean` — archive old entries
- `skills/continuous-learning/SKILL.md` — schema and workflow details
- `.ai/memory/staging/` — staged learning entries

## Suggested Next

- `/learn` — stage new patterns before evolving
- `/wrap-up` — end session and extract learnings
- `/memory-clean` — archive old entries after promoting what matters
