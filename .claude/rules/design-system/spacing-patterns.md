# Spacing Patterns

Application patterns for the spacing scale. See `foundations.md` for token values.

---

## Vertical Rhythm & Form Spacing

| Relationship | Spacing | Token |
|--------------|---------|-------|
| Label to input | 4-8px | `xs` |
| Field to field (same group) | 16px | `sm` |
| Field to field (different concern) | 24px | `md` |
| Group to group (with heading) | 32-48px | `lg`/`xl` |

### Visual Hierarchy Through Spacing

**Principle:** Tighter spacing = related. Looser spacing = separate. Whitespace creates implicit grouping without borders.

```
[Section Heading]
    32px (lg) ↓
[Label]
    4px (xs) ↓
[Input]
    16px (sm) ↓         ← same logical group
[Label]
    4px (xs) ↓
[Input]
    24px (md) ↓         ← different concern
[Label]
    4px (xs) ↓
[Input]
    48px (xl) ↓         ← new section
[Section Heading]
```

### Form Spacing Rules

- ✅ Use `sm` between related fields (City + State + Zip)
- ✅ Use `md` to separate distinct concerns (Personal Info → Payment)
- ✅ Add section headings when gaps exceed `lg`
- ❌ Don't use uniform spacing for all fields - flattens hierarchy
- ❌ Don't let fields touch or nearly touch

---

## Card & Container Spacing

| Density | Padding | Use Case |
|---------|---------|----------|
| Compact | `sm` (16px) | Data tables, dense lists, dashboards |
| Comfortable | `md` (24px) | Standard cards, form sections |
| Spacious | `lg` (32px) | Hero cards, marketing, empty states |

### Container Rules

- ✅ Match internal padding to content density
- ✅ Use consistent padding across similar components
- ✅ Increase padding as container importance increases
- ❌ Don't mix density levels within the same view

---

## Section & Page-Level Spacing

| Context | Spacing | Token |
|---------|---------|-------|
| Between major sections | 48-80px | `xl`/`2xl` |
| Above h1 | 48px | `xl` |
| Above h2/h3 | 32px | `lg` |
| Below headings | 16-24px | `sm`/`md` |
| Page horizontal margins | 16-48px | Responsive |
| Content max-width | 1200px | - |

### Page Layout Rules

- ✅ Use larger gaps (`xl`/`2xl`) between unrelated sections
- ✅ Keep heading spacing asymmetric: more above, less below
- ✅ Constrain line length (45-75 characters for readability)
- ❌ Don't let content span full viewport width

---

## Common Anti-Patterns

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| Uniform 16px everywhere | Flattens visual hierarchy | Vary spacing by relationship |
| Fields nearly touching | Hard to parse, feels cramped | Minimum `sm` between fields |
| Inconsistent card padding | Looks unpolished | Standardize on density tier |
| Borders instead of whitespace | Visual noise, cluttered | Let spacing create grouping |
| Massive gaps in compact UI | Wastes space, breaks flow | Match density to context |

### Spacing Decision Tree

```
Are these elements part of the same logical group?
├── Yes: Use tighter spacing (xs/sm)
└── No: Are they in the same section?
    ├── Yes: Use medium spacing (md)
    └── No: Use loose spacing (lg/xl/2xl)
```
