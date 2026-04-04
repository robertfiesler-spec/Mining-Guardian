# Vercel Web Interface Guidelines

Condensed from https://vercel.com/design/guidelines

## Interactions

| Guideline | Implementation |
|-----------|---------------|
| Keyboard works everywhere | All flows keyboard-operable, follow WAI-ARIA patterns |
| Clear focus | `:focus-visible` over `:focus`, use `:focus-within` for groups |
| Hit targets | ≥24px desktop, ≥44px mobile |
| Mobile input size | ≥16px font on inputs (prevents iOS zoom) |
| Never disable zoom | Respect user preferences |
| Hydration-safe inputs | Inputs keep focus/value after hydration |
| Don't block paste | Never disable paste on any input |
| Loading buttons | Spinner + keep original label |
| URL as state | Persist state in URL for share/refresh/navigation |
| Optimistic updates | Update UI immediately, reconcile on response |
| Confirm destructive actions | Confirmation dialog OR Undo with safe window |
| Tooltip timing | Delay first tooltip; peers show immediately |
| Autofocus for speed | Desktop only; avoid on mobile (keyboard shift) |
| Links are links | Use `<a>` for navigation (Cmd+Click, middle-click work) |

## Animations

| Guideline | Implementation |
|-----------|---------------|
| Honor reduced motion | `@media (prefers-reduced-motion: reduce)` |
| GPU-accelerated | Prefer `transform`, `opacity` over `width`, `height` |
| Never `transition: all` | Explicitly list properties |
| Interruptible | Animations cancelable by user input |
| Correct transform origin | Anchor to where motion starts |

## Layout

| Guideline | Implementation |
|-----------|---------------|
| Optical alignment | Adjust ±1px when perception beats geometry |
| Nested radii | Child radius ≤ parent radius, concentric curves |
| Safe areas | Use `env(safe-area-inset-*)` for notches |
| No excessive scrollbars | Fix overflow issues |
| Let browser size things | Prefer CSS flex/grid over JS measurement |

## Content

| Guideline | Implementation |
|-----------|---------------|
| Stable skeletons | Match final content dimensions exactly |
| Accurate page titles | `<title>` reflects current context |
| No dead ends | Every screen offers next step |
| All states designed | Empty, sparse, dense, error states |
| Typographic quotes | Use curly quotes `" "` not straight `" "` |
| Tabular numbers | `font-variant-numeric: tabular-nums` for data |
| Non-breaking spaces | `&nbsp;` between numbers and units |
| Accessible content | Set `aria-label`, hide decoration with `aria-hidden` |
| Headings & skip link | Hierarchical h1-h6, "Skip to content" link |

## Forms

| Guideline | Implementation |
|-----------|---------------|
| Enter submits | Single control: Enter submits |
| Textarea behavior | Cmd/Ctrl+Enter submits; Enter = newline |
| Labels everywhere | Every control has label |
| Submit enabled until submission | Show validation on submit, not before |
| Don't block typing | Allow any input, show validation feedback |
| Error placement | Errors next to fields; focus first error |
| Autocomplete & names | Set `autocomplete` and meaningful `name` |
| Placeholder format | End with ellipsis; use example values |
| Warn unsaved changes | `beforeunload` when data could be lost |

## Performance

| Guideline | Implementation |
|-----------|---------------|
| Track re-renders | Use React DevTools or React Scan |
| Throttle when profiling | Test with CPU/network throttling |
| Network latency | POST/PATCH/DELETE < 500ms |
| Large lists | Virtualize with virtua or `content-visibility: auto` |
| No image CLS | Set explicit dimensions |
| Preload fonts | Critical fonts to avoid FOUT |

## Design

| Guideline | Implementation |
|-----------|---------------|
| Layered shadows | Ambient + direct light (2+ layers) |
| Crisp borders | Combine borders + shadows |
| Nested radii | Inner = outer - padding |
| Minimum contrast | 4.5:1 text, prefer APCA |
| Interactions increase contrast | Hover/active/focus > rest |
| Browser theme color | `<meta name="theme-color">` |
| Set color-scheme | `color-scheme: dark` for dark themes |

## Copywriting (Vercel-specific)

- Active voice
- Title Case for headings/buttons
- Be clear & concise
- `&` over `and`
- Second person (avoid first person)
- Numerals for counts (`8 deployments` not `eight`)
- Space between numbers and units (`10 MB`)
- Default to positive language
- Error messages guide the exit
