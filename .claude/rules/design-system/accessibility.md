# Accessibility

Meet WCAG 2.1 Level AA as a minimum standard.

## Contrast Requirements

| Element | Minimum Ratio |
|---------|---------------|
| Small text (≤18px) | 4.5:1 |
| Large text (≥24px regular, ≥18px bold) | 3:1 |
| UI elements (borders, icons, focus rings) | 3:1 |

## Visual Design

- ✅ Ensure sufficient color contrast (see ratios above)
- ✅ Don't rely on color alone - add icons, text, or patterns
- ✅ Ensure form field borders are clearly visible
- ✅ Provide text labels for all icons
- ✅ Make focus states highly visible
- ✅ Underline text links for discoverability

## Interactive Elements

- ✅ Minimum touch/click target: 44×44px (WCAG 2.5.5 AAA)
- ✅ Keep related actions close to their associated elements
- ✅ Ensure all interactions work with keyboard alone
- ✅ Provide visible focus indicators
- ✅ Support escape key to close modals/dialogs

## Screen Readers

- ✅ Use semantic HTML (`<button>`, `<nav>`, `<main>`, `<article>`)
- ✅ Add descriptive `aria-label` to icon-only buttons
- ✅ Use proper heading hierarchy (h1 → h2 → h3)
- ✅ Add alt text to meaningful images
- ✅ Use `aria-live` regions for dynamic content updates
- ✅ Ensure link text makes sense out of context

## Screen Magnifiers

Users see only a small portion of the screen at once:

- ✅ Left-align important actions (don't hide in right corners)
- ✅ Keep related elements in close proximity
- ✅ Avoid layouts that spread related content across the viewport

## Motion & Animation

- ✅ Respect `prefers-reduced-motion` media query
- ✅ Avoid auto-playing animations
- ✅ Keep animations subtle and purposeful
- ❌ Never use flashing content (seizure risk)

## Quick Checklist

```
□ Text contrast ≥ 4.5:1 (small) or 3:1 (large)
□ UI element contrast ≥ 3:1
□ Touch targets ≥ 44×44px
□ Color not sole indicator of meaning
□ All functionality keyboard accessible
□ Focus states visible
□ Semantic HTML structure
□ Alt text on images
□ Link text is descriptive
□ prefers-reduced-motion respected
```

## Why This Matters

Good accessibility benefits everyone:

- **Permanent disabilities** - Vision, hearing, motor, cognitive impairments
- **Temporary disabilities** - Broken arm, eye infection, concussion
- **Situational limitations** - Bright sunlight, noisy environment, one hand occupied