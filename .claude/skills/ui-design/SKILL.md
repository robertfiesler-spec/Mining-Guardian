---
name: ui-design
description: Visual design review, UI polish, and interface quality guidelines based on Vercel's Web Interface Guidelines. Use when reviewing UI for visual inconsistencies, polish issues, or when building new interfaces that need professional-grade quality. Also use for animation, layout, typography, and interaction design decisions.
---

# UI Design Skill

Production-grade interface patterns from Vercel's Web Interface Guidelines.

## Interactions

### Keyboard

- All flows keyboard-operable
- Visible focus ring on every focusable element
- Use `:focus-visible` over `:focus` to avoid distracting pointer users

```css
/* ✅ Good: Focus visible only on keyboard */
button:focus-visible {
  outline: 2px solid var(--focus-color);
  outline-offset: 2px;
}
```

### Hit Targets

- Minimum 24×24px on desktop
- Minimum 44×44px on mobile
- If visual target is smaller, expand hit area:

```css
.icon-button {
  position: relative;
  /* Visual size */
  width: 16px;
  height: 16px;
}

.icon-button::before {
  content: '';
  position: absolute;
  /* Hit target expansion */
  inset: -12px;
}
```

### Loading States

- Show loading indicator + keep original label
- Add short show-delay (~150-300ms) to avoid flicker on fast responses
- Minimum visible time (~300-500ms) once shown

```typescript
const [isPending, startTransition] = useTransition();

<button disabled={isPending}>
  {isPending && <Spinner className="mr-2" />}
  {isPending ? 'Saving…' : 'Save'}
</button>
```

### Optimistic Updates

Update UI immediately when success is likely:

```typescript
const [optimisticLikes, addOptimisticLike] = useOptimistic(
  likes,
  (state, newLike) => [...state, newLike]
);

async function handleLike() {
  addOptimisticLike({ id: tempId, userId: currentUser.id });
  await likePost(postId); // Reconcile on response
}
```

### Destructive Actions

Always require confirmation OR provide Undo:

```typescript
// Option 1: Confirmation
<AlertDialog>
  <AlertDialogTrigger asChild>
    <Button variant="destructive">Delete</Button>
  </AlertDialogTrigger>
  <AlertDialogContent>
    <AlertDialogTitle>Delete item?</AlertDialogTitle>
    <AlertDialogDescription>
      This action cannot be undone.
    </AlertDialogDescription>
    <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>
    <AlertDialogCancel>Cancel</AlertDialogCancel>
  </AlertDialogContent>
</AlertDialog>

// Option 2: Undo toast
toast({
  title: 'Item deleted',
  action: <Button onClick={handleUndo}>Undo</Button>,
});
```

## Animations

### Honor `prefers-reduced-motion`

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

### GPU-Accelerated Properties

Prioritize `transform` and `opacity`. Avoid animating `width`, `height`, `top`, `left`.

```css
/* ✅ Good: Compositor-friendly */
.card {
  transition: transform 200ms ease-out, opacity 200ms ease-out;
}
.card:hover {
  transform: translateY(-4px);
}

/* ❌ Bad: Triggers reflow */
.card {
  transition: margin-top 200ms;
}
.card:hover {
  margin-top: -4px;
}
```

### Never `transition: all`

```css
/* ❌ Bad */
button { transition: all 200ms; }

/* ✅ Good */
button { transition: background-color 200ms, transform 200ms; }
```

### Interruptible Animations

Animations should be cancelable by user input:

```typescript
const controls = useAnimationControls();

// Can be interrupted
<motion.div
  animate={controls}
  onHoverStart={() => controls.start({ scale: 1.05 })}
  onHoverEnd={() => controls.start({ scale: 1 })}
/>
```

## Layout

### Optical Alignment

Adjust ±1px when perception beats geometry. Icons often need slight offsets.

### Nested Radii

Child radius ≤ parent radius. Use concentric curves:

```css
.card {
  border-radius: 16px;
  padding: 8px;
}
.card-inner {
  /* Inner radius = outer radius - padding */
  border-radius: 8px;
}
```

### Safe Areas

Account for device notches:

```css
.bottom-nav {
  padding-bottom: env(safe-area-inset-bottom, 0);
}
```

## Typography

### Tabular Numbers

Use `tabular-nums` for numbers in tables, prices, counts:

```css
.price { font-variant-numeric: tabular-nums; }
```

### Non-Breaking Spaces

Keep units and shortcuts together:

```html
<!-- Prevents awkward line breaks -->
10&nbsp;MB
⌘&nbsp;+&nbsp;K
Vercel&nbsp;SDK
```

### Typographic Quotes

Use curly quotes:
- `"quoted"` not `"quoted"`
- `'apostrophe'` not `'apostrophe'`

## Design Tokens

### Layered Shadows

```css
--shadow-sm: 
  0 1px 2px rgba(0, 0, 0, 0.05),
  0 1px 1px rgba(0, 0, 0, 0.03);

--shadow-md:
  0 4px 6px rgba(0, 0, 0, 0.07),
  0 2px 4px rgba(0, 0, 0, 0.05);

--shadow-lg:
  0 10px 15px rgba(0, 0, 0, 0.1),
  0 4px 6px rgba(0, 0, 0, 0.05);
```

### Crisp Borders

Combine borders with shadows for clarity:

```css
.card {
  border: 1px solid rgba(0, 0, 0, 0.08);
  box-shadow: var(--shadow-sm);
}
```

### Contrast Ratios

See `@rules/design-system/accessibility.md` for WCAG contrast requirements and full a11y checklist. Use APCA for more accurate perceptual contrast.

## Forms

### Enter Submits

When text input is focused, Enter submits (if single control) or Cmd/Ctrl+Enter for textareas.

### Error Placement

Show errors next to fields. On submit, focus first error:

```typescript
const firstError = Object.keys(errors)[0];
if (firstError) {
  document.getElementById(firstError)?.focus();
}
```

### Placeholder Format

End with ellipsis to signal emptiness. Use example values:

```html
<input placeholder="sk-012345679…" />
<input placeholder="+1 (123) 456-7890" />
```

## File References

- `references/vercel-guidelines.md` - Complete Vercel Web Interface Guidelines
- `references/design-tokens.md` - Standard token definitions

## Related Rules

Always apply these rules when building UI:

- `@rules/design-system/_index.md` - Core design principles
- `@rules/design-system/foundations.md` - Color, typography, spacing scales
- `@rules/design-system/components.md` - Button, form, copywriting guidelines
- `@rules/design-system/accessibility.md` - WCAG requirements
