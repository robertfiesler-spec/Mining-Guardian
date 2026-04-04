# Page Patterns: Cross-Page Consistency

Pages of the same archetype MUST share identical structure, element placement, and functionality. Inconsistency across sibling pages is a UX bug.

## Enforcement Process

Before building or modifying any page:

1. **Identify the archetype** — list, detail, form, dashboard, settings
2. **Find an existing page of the same type** in the codebase
3. **Match its structure exactly** — same elements, same order, same placement
4. **Deviate only with explicit justification** using `ds-exception:` marker

If no sibling page exists, follow the archetype defaults below. If the project CLAUDE.md defines `### Page Patterns`, that takes precedence.

---

## Archetype Defaults

### List Pages

| Element | Placement | Required |
|---------|-----------|----------|
| Page title | Top-left | Yes |
| Primary action button | Top-right (header row) | Yes |
| Search bar | Toolbar, left | Yes |
| Filters | Toolbar, after search | Yes |
| Column manager / sort | Toolbar, right | When table has 5+ columns |
| Data table | Below toolbar | Yes |
| Pagination | Below table | When rows exceed page size |
| Empty state with CTA | Replaces table when no data | Yes |

### Detail Pages

| Element | Placement | Required |
|---------|-----------|----------|
| Entity name / title | Top-left | Yes |
| Status badges | Top-right of header | When entity has status |
| Action buttons | Right-aligned in header | Yes |
| Tab navigation | Below header | Yes (minimum: Overview + History) |
| Content area | Below tabs, card-based | Yes |
| Summary / metric cards | Top of content (neutral text, no colored numbers) | When entity has key metrics |

### Form Pages

| Element | Placement | Required |
|---------|-----------|----------|
| Breadcrumb | Above title | Yes |
| Page title | Top-left | Yes |
| Form layout | Single column | Yes |
| Section headings | Group related fields | When form has 6+ fields |
| Action bar (Save / Cancel) | Bottom or top-right (consistent across project) | Yes |

### Dashboard Pages

| Element | Placement | Required |
|---------|-----------|----------|
| Page title | Top-left | Yes |
| Date range / global filters | Top-right | When data is time-bound |
| Metric cards | First row, equal sizing | Yes |
| Charts / tables | Below metrics | Yes |

---

## Consistency Rules

- Summary/metric cards use **neutral text** — colored numbers only for semantic meaning (error, warning, success states)
- Action buttons are **always right-aligned** in headers across all page types
- Tab names use **sentence case**, consistent verbs across sibling pages
- Empty states include **icon + message + CTA** — never a blank area
- If one list page has search + filters + column manager, ALL list pages must have them
- If one detail page has tabs, ALL detail pages must have tabs

## Anti-Patterns

| Anti-Pattern | Fix |
|--------------|-----|
| Detail page missing tabs that sibling detail pages have | Copy tab structure from existing detail page |
| Colored numbers on summary cards inconsistently | Neutral text everywhere; semantic color only for status badges |
| Action buttons left on some pages, right on others | Always right-align in page header |
| List page missing search/filter that sibling pages have | Copy toolbar pattern from nearest sibling list page |
| Inconsistent header layout between pages of same type | Extract shared `PageHeader` component |

## Project Customization

These archetypes are defaults. Projects SHOULD document their specific patterns in their project CLAUDE.md under a `### Page Patterns` section, overriding these defaults with project-specific element lists and placement rules.

When `/learn` captures a page-consistency correction, it maps to the `page-layout` category and promotes to this rule file or to the project's `### Page Patterns` section.
