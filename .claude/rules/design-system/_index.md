# Design System Rules

Practical guidelines for building intuitive, accessible, and beautiful interfaces.

## Applies When

- Building UI components (React, Vue, Svelte, etc.)
- Writing CSS, Tailwind, or styled-components
- Creating new pages, layouts, or templates
- Reviewing frontend code
- Implementing forms or interactive elements

## Does Not Apply When

- Backend-only work (APIs, databases, CLI tools)
- Documentation or markdown files
- Build configuration or DevOps

## Core Principles

1. **Minimize Usability Risks** - Base decisions on risk assessment. Consider users with poor eyesight, low computer literacy, reduced dexterity, and cognitive impairments.

2. **Have a Logical Reason for Every Detail** - Design with objective logic rather than subjective opinion.

3. **Minimize Interaction Cost** - Reduce physical and mental effort: looking, scrolling, clicking, waiting, typing, thinking, remembering.

4. **Minimize Cognitive Load** - Remove unnecessary styles, break up information, use conventional patterns, maintain consistency.

5. **Use Common Patterns** - Stick with conventional designs people already know (Jakob's Law).

6. **Be Consistent** - Similar elements should look and work similarly.

7. **80/20 Rule** - Prioritize the 20% of work that delivers 80% of impact.

## Exception Policy

Design system rules are enforced deterministically. When a rule must be broken:

1. Add a `ds-exception:` marker on the line before the violation
2. Include a short reason explaining why the exception is necessary
3. Exceptions are reported by `design-lint.sh` and tracked as tech debt
4. Periodically audit and remove stale exceptions

```tsx
{/* ds-exception: marketing hero uses brand gradient per campaign brief */}
<div className="bg-gradient-to-r from-[#6366f1] to-[#8b5cf6]">
```

**Scope**: Enforcement applies to the logged-in application by default. Admin surfaces and legacy marketing pages can be excluded via `--scope` until they receive a dedicated redesign pass.

## Related Rules

- `@rules/design-system/foundations.md` - Color, typography, spacing scales
- `@rules/design-system/spacing-patterns.md` - Vertical rhythm, form spacing, layout gaps
- `@rules/design-system/components.md` - Buttons, forms, inputs
- `@rules/design-system/accessibility.md` - WCAG requirements, screen readers
- `@rules/design-system/page-patterns.md` - Cross-page consistency for list, detail, form, dashboard archetypes

## Related Skills

For detailed implementation patterns and code examples, see:

- `ui-design` skill - Vercel Web Interface Guidelines, animations, layout
- `accessibility` skill - ARIA patterns, focus management, testing

## Commands

- `/design-check` - Validate code against these design system rules
- `/rams` - Broader accessibility & visual design audit