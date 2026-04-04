---
suggest_when:
  - signal: session_start
    condition: staged_learnings
    cooldown: 60
    message: "Have staged learnings ready to promote? `/create-skill` scaffolds a new skill from toolkit patterns"
  - signal: total_tool_calls
    value: 35
    cooldown: 60
    message: "Discovering reusable patterns this session? `/create-skill` formalizes them into a loadable skill"
---

# /create-skill - Create New Skill Files

Scaffold a new skill that follows ai-toolkit patterns. Generates a `SKILL.md` with proper frontmatter, structured sections, code examples, and optional reference files.

## Usage

```
/create-skill <skill-name> [--with-refs] [--domain <domain>]
```

$ARGUMENTS

## Arguments

| Argument | Description |
|----------|-------------|
| `<skill-name>` | kebab-case name for the skill (e.g., `state-management`, `api-design`) |
| `--with-refs` | Also create a `references/` subdirectory with starter reference files |
| `--domain <domain>` | Pre-specify the domain (e.g., `react`, `backend`, `devops`, `design`) |

## Your Task

Create a well-structured skill file that provides actionable, example-driven guidance for Claude. Skills are on-demand reference material — they should be specific enough to inform real implementation decisions.

## Step 1: Gather Skill Details

If not provided as arguments, ask:

1. **Skill name** — kebab-case, descriptive (e.g., `error-handling`, `state-management`)
2. **Domain** — What area does this cover? (React, backend, DevOps, design, etc.)
3. **When to use** — What triggers loading this skill? (building forms, setting up auth, etc.)
4. **Key topics** — 3-5 major topics to cover (these become H2 sections)
5. **Reference files needed?** — Does it need extended patterns in `references/`?

## Step 2: Audit Existing Skills for Conflicts and Redundancy

Before writing anything, read **every** existing `SKILL.md` and scan relevant `rules/` files to identify overlaps. This is a hard gate — do not proceed to Step 3 until this audit is complete.

### 2a. Read all existing skills

Read each `skills/*/SKILL.md` file. For each one, extract:
- The skill's **name** and **description** (from frontmatter)
- Its **H2 topic headings** (the major knowledge areas it covers)
- Any **trigger keywords** in the description

### 2b. Check for topic overlap

Compare the proposed skill's topics against existing skills. Look for:

| Overlap Type | Example | Resolution |
|-------------|---------|------------|
| **Full redundancy** | New `forms` skill covers the same ground as `react-patterns` > Custom Hooks > Form Hook | Don't create — extend the existing skill instead |
| **Partial overlap** | New `state-management` skill covers Server Components, which `react-patterns` already covers | Scope the new skill to exclude the overlapping topic, and cross-reference the existing skill |
| **Complementary** | New `error-handling` skill covers error boundaries (also in `react-patterns`) but goes much deeper | OK to create — reference the existing skill's lighter treatment and note "for deeper error handling patterns, see `@skill/error-handling`" |
| **Contradictory** | New skill recommends `useEffect` for data fetching, but `data-fetching` skill says to avoid it | Resolve the contradiction before proceeding — one recommendation must win |

### 2c. Check rules for contradictions

Scan `rules/*.md` and `rules/design-system/*.md` for guidance that overlaps with the proposed skill's topics. Skills must **never contradict rules** — rules are invariants, skills are guidance that operates within those constraints.

If a contradiction is found:
1. The rule wins — it's a non-negotiable constraint
2. The skill must align with the rule and reference it explicitly
3. If the rule seems wrong, flag it to the user before proceeding

### 2d. Report findings

Before continuing, output an overlap report:

```
## Overlap Audit

**Proposed skill:** <name>
**Existing skills scanned:** <count>

### Overlaps Found
- [skill-name] > [section]: <description of overlap> → <resolution>
- [rule-file]: <description of overlap> → <resolution>

### No Conflicts
Proposed topics [list] have no overlap with existing skills or rules.

### Recommendations
- <any scope adjustments, cross-references to add, or topics to exclude>
```

If **full redundancy** is detected, recommend extending the existing skill instead of creating a new one and ask the user how to proceed.

### 2e. Choose a style model

After the audit, pick a style model from existing skills:

- **Code-focused** (patterns, hooks, utilities) → Follow `react-patterns` style with extensive code blocks
- **Compliance/checklist** (a11y, security, performance) → Follow `accessibility` style with severity levels and rules
- **Process/methodology** (workflows, generation, consumption) → Follow `pyramid-summary` style with steps and decision trees

Read the chosen model skill to match its conventions.

## Step 3: Write SKILL.md

Create `skills/<skill-name>/SKILL.md` with this structure:

### Required Structure

```markdown
---
name: <skill-name>
description: >
  <1-3 sentences>. Mention the domain, key use cases, and trigger keywords
  so the skill auto-triggers when relevant topics come up.
---

# <Skill Title>

<1-2 sentence intro explaining what this skill provides and when to use it.>

## <Topic 1>

<Explanation with context.>

### <Subtopic>

<Code examples showing both good and bad patterns.>

```typescript
// ✅ Good: [explain why]
<good pattern>

// ❌ Bad: [explain why]
<bad pattern>
```

## <Topic 2>

...

## <Topic N>

...

## Anti-Patterns

**Don't do this:**
- <Common mistake 1>
- <Common mistake 2>

**Do this instead:**
- <Correct approach 1>
- <Correct approach 2>

## File References

- `references/<file>.md` - <description> (if --with-refs)
- `@rules/<related-rule>.md` - <description>
- `@skill/<related-skill>` - <description>
```

### Writing Guidelines

Follow these rules when writing the SKILL.md content:

**Frontmatter:**
- `name` must match the directory name exactly (kebab-case)
- `description` should mention trigger keywords that cause auto-loading (e.g., "forms", "authentication", "caching")
- Use `>` for multi-line descriptions in YAML

**Sections:**
- Use H2 (`##`) for major topics — these are the skill's primary knowledge areas
- Use H3 (`###`) for subtopics and specific patterns within a topic
- Each H2 section should be independently useful (a reader may jump to just one)

**Code Examples:**
- Every pattern claim MUST have a code example
- Show both good (`✅`) and bad (`❌`) approaches when the distinction matters
- Use TypeScript with syntax highlighting (` ```typescript `)
- Include comments that explain "why", not "what"
- Keep examples practical — real-world patterns from actual projects, not toy demos
- Match the project's stack conventions (Next.js App Router, Tailwind, etc.)

**Tone:**
- Direct and imperative — "Use X", "Avoid Y", "Prefer Z over W"
- Explain trade-offs, not just rules — "X is better because..."
- Include gotchas and edge cases that trip people up
- Reference specific APIs, libraries, or patterns by name

**Length targets:**
- Short skills (single-concern): 80-150 lines
- Standard skills (multi-topic): 150-300 lines
- Comprehensive skills (deep domain): 300-500 lines
- Anything over 500 lines should split into SKILL.md + references/

## Step 4: Create Reference Files (if --with-refs)

If the skill needs extended patterns, create `skills/<skill-name>/references/`:

```
skills/<skill-name>/
├── SKILL.md
└── references/
    ├── <topic-1>.md     # Extended patterns for topic 1
    └── <topic-2>.md     # Extended patterns for topic 2
```

Reference files hold content too detailed for SKILL.md — comprehensive checklists, exhaustive pattern libraries, or deep-dive examples. Link them from the `## File References` section.

**Reference file format:**
```markdown
# <Topic Title>

Extended patterns for [context]. Referenced from `SKILL.md`.

## <Section>

<Detailed content with code examples>
```

## Step 5: Register the Skill

After creating the files, register the skill in the toolkit:

### 5a. Add to config.json

Add the skill name to the `skills.enabled` array in `config.json`:

```json
{
  "skills": {
    "enabled": [
      "react-patterns",
      "accessibility",
      ...,
      "<new-skill-name>"
    ]
  }
}
```

### 5b. Add to config.schema.json

Add the skill name to the enum list in `config.schema.json` under the skills enabled array schema.

### 5c. Update CLAUDE.md

Add a bullet to the `## Available Skills` section:

```markdown
- **<skill-name>**: <Short description of the skill's domain and when to use it>
```

### 5d. Update README.md

Add the skill to the `skills/` directory listing in the project structure section.

## Step 6: Validate

Before finishing, verify:

**Overlap & Consistency:**
- [ ] Overlap audit completed (Step 2) — no unresolved contradictions
- [ ] No topic fully duplicates an existing skill's coverage
- [ ] Recommendations from existing skills are consistent (no conflicting advice)
- [ ] Rules are not contradicted — skill aligns with all relevant `rules/*.md`
- [ ] Cross-references added for any partial overlaps with existing skills

**Structure & Content:**
- [ ] `SKILL.md` has valid YAML frontmatter with `name` and `description`
- [ ] `name` in frontmatter matches directory name exactly
- [ ] `description` includes trigger keywords for auto-loading
- [ ] Every major topic has at least one code example
- [ ] Code examples use TypeScript with syntax highlighting
- [ ] Good/bad pattern pairs where the distinction matters
- [ ] `## File References` section exists (even if empty — link related rules/skills)
- [ ] No `any` types in code examples
- [ ] Comments explain "why" not "what"

**Registration:**
- [ ] Skill registered in `config.json`
- [ ] Skill registered in `config.schema.json`
- [ ] Skill documented in `CLAUDE.md`
- [ ] Skill documented in `README.md`

## Step 7: Summarize

Output:

```
## Skill Created

**Name:** <skill-name>
**Location:** skills/<skill-name>/SKILL.md
**Topics:** <list of H2 sections>
**References:** <list of reference files, or "none">
**Overlaps resolved:** <list of overlap resolutions, or "none found">
**Cross-references:** <skills/rules linked in File References section>
**Registered:** config.json, config.schema.json, CLAUDE.md, README.md

Ready to use: the skill will auto-trigger when Claude encounters
tasks related to [trigger keywords].
```

## Examples

```bash
# Interactive — asks for details
/create-skill

# Named skill
/create-skill state-management

# With references directory
/create-skill error-handling --with-refs

# Fully specified
/create-skill api-design --domain backend --with-refs
```

## Quality Checklist

A great skill file:

| Quality | What It Means |
|---------|--------------|
| **Actionable** | Every section answers "what should I do?" not just "what is this?" |
| **Example-driven** | Patterns are shown in code, not just described in prose |
| **Opinionated** | Takes a position — "prefer X over Y" — with reasoning |
| **Scoped** | Covers one domain well rather than many domains shallowly |
| **Cross-referenced** | Links to related rules, skills, and reference files |
| **Stack-aware** | Examples use the project's actual stack (Next.js, TypeScript, Tailwind) |

## Related

- `skills/` — Existing skills to reference for patterns
- `config.json` — Skill registration
- `CLAUDE.md` — Global skill documentation
- `/learn` — Document mistakes as rules (complementary: rules are invariants, skills are guidance)

## Suggested Next

- `/docs-check` — verify CLAUDE.md and README reflect the new skill
- `/iterate` — continue with plan items after scaffolding
- `/learn` — alternative for patterns that fit rules rather than skills
