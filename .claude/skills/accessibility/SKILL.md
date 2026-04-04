---
name: accessibility
description: WCAG 2.1 compliance, semantic HTML, ARIA patterns, and accessibility testing. Use when building forms, interactive components, navigation, or reviewing existing UI for accessibility issues. Also use when the user mentions a11y, screen readers, keyboard navigation, or focus management.
---

# Accessibility Skill

Patterns for building accessible React/Next.js interfaces following WCAG 2.1 AA.

## Critical Issues (Must Fix)

### Images Without Alt Text

```typescript
// ❌ Missing alt
<img src="/hero.jpg" />

// ✅ Descriptive alt
<img src="/hero.jpg" alt="Team collaborating around a whiteboard" />

// ✅ Decorative images
<img src="/decoration.svg" alt="" aria-hidden="true" />
```

### Icon-Only Buttons

```typescript
// ❌ No accessible name
<button><CloseIcon /></button>

// ✅ With aria-label
<button aria-label="Close dialog"><CloseIcon aria-hidden="true" /></button>

// ✅ With visually hidden text
<button>
  <CloseIcon aria-hidden="true" />
  <span className="sr-only">Close dialog</span>
</button>
```

### Form Inputs Without Labels

```typescript
// ❌ No label association
<input type="email" placeholder="Email" />

// ✅ Explicit label
<label htmlFor="email">Email address</label>
<input id="email" type="email" />

// ✅ Implicit label (wrapping)
<label>
  Email address
  <input type="email" />
</label>

// ✅ aria-label for icon inputs
<input type="search" aria-label="Search products" />
```

### Non-Semantic Click Handlers

```typescript
// ❌ Div with onClick (not keyboard accessible)
<div onClick={handleClick}>Click me</div>

// ✅ Use button for actions
<button onClick={handleClick}>Click me</button>

// ✅ Use anchor for navigation
<Link href="/dashboard">Go to dashboard</Link>
```

### Links Without href

```typescript
// ❌ Missing href
<a onClick={handleClick}>Learn more</a>

// ✅ Real link
<a href="/about">Learn more</a>

// ✅ If it's an action, use button
<button onClick={handleClick}>Learn more</button>
```

## Serious Issues

### Focus Outline Removed

```typescript
// ❌ Removes focus indicator
<button className="outline-none">Submit</button>

// ✅ Custom focus ring
<button className="focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2">
  Submit
</button>

// ✅ Tailwind preset (add to tailwind.config.js)
// focusVisible: 'focus-visible:ring-2 focus-visible:ring-offset-2'
```

### Missing Keyboard Handlers

```typescript
// ❌ Mouse-only interaction
<div 
  onClick={handleSelect}
  className="cursor-pointer"
>
  Option 1
</div>

// ✅ Keyboard accessible
<div
  role="option"
  tabIndex={0}
  onClick={handleSelect}
  onKeyDown={(e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleSelect();
    }
  }}
>
  Option 1
</div>

// ✅ Better: Use a real button
<button onClick={handleSelect}>Option 1</button>
```

### Touch Targets Too Small

Minimum size: 44×44px on mobile, 24×24px on desktop.

```typescript
// ❌ Too small
<button className="p-1 text-sm">×</button>

// ✅ Adequate touch target
<button className="p-3 min-w-[44px] min-h-[44px]">
  <span className="text-sm">×</span>
</button>
```

### Color-Only Information

```typescript
// ❌ Status indicated only by color
<span className={status === 'error' ? 'text-red-500' : 'text-green-500'}>
  {status}
</span>

// ✅ Color + icon + text
<span className={status === 'error' ? 'text-red-500' : 'text-green-500'}>
  {status === 'error' ? '⚠️ Error: ' : '✓ Success: '}
  {message}
</span>
```

## Moderate Issues

### Skipped Heading Levels

```typescript
// ❌ Skips h2
<h1>Page Title</h1>
<h3>Section</h3>

// ✅ Proper hierarchy
<h1>Page Title</h1>
<h2>Section</h2>
<h3>Subsection</h3>
```

### Positive tabIndex

```typescript
// ❌ Disrupts natural tab order
<button tabIndex={5}>First</button>
<button tabIndex={1}>Second</button>

// ✅ Use 0 or -1 only
<button tabIndex={0}>Focusable in DOM order</button>
<button tabIndex={-1}>Programmatically focusable only</button>
```

## Focus Management

### Modal/Dialog Focus Trap

```typescript
'use client';
import { useEffect, useRef } from 'react';

export function Modal({ isOpen, onClose, children }) {
  const modalRef = useRef<HTMLDivElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      previousFocus.current = document.activeElement as HTMLElement;
      modalRef.current?.focus();
    } else {
      previousFocus.current?.focus();
    }
  }, [isOpen]);

  return (
    <div
      ref={modalRef}
      role="dialog"
      aria-modal="true"
      tabIndex={-1}
      onKeyDown={(e) => {
        if (e.key === 'Escape') onClose();
      }}
    >
      {children}
    </div>
  );
}
```

### Skip Link

```typescript
// In layout.tsx
<a 
  href="#main-content" 
  className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-white"
>
  Skip to main content
</a>

// Main content
<main id="main-content" tabIndex={-1}>
  {children}
</main>
```

## ARIA Patterns

For complex widget patterns (tabs, menus, comboboxes), see `references/aria-patterns.md`.

## Testing

```bash
# Automated testing
npm install -D @axe-core/react

# In development
import React from 'react';
import ReactDOM from 'react-dom';
import axe from '@axe-core/react';

if (process.env.NODE_ENV === 'development') {
  axe(React, ReactDOM, 1000);
}
```

Manual checklist:
1. Tab through entire page - is order logical?
2. Can you operate everything with keyboard only?
3. Test with screen reader (VoiceOver on Mac: Cmd+F5)
4. Check color contrast (APCA > WCAG 2 for accuracy)

## File References

- `references/aria-patterns.md` - Complex widget patterns (tabs, menus, etc.)
- `references/wcag-checklist.md` - Full WCAG 2.1 AA checklist

## Related Rules

Always apply these rules when building UI:

- `@rules/design-system/accessibility.md` - Concise WCAG requirements checklist
- `@rules/design-system/foundations.md` - Color contrast, typography scales
- `@rules/design-system/components.md` - Accessible form patterns
