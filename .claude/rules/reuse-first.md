---
description: DRY enforcement — prefer extending existing code over creating new
globs: ["**/*.ts", "**/*.tsx", "**/*.svelte", "**/*.jsx"]
---

# Reuse First

- Before creating a component, hook, utility, or API route, search for existing similar code
- Extend or adapt existing implementations rather than building from scratch
- Extract shared logic into reusable modules when patterns repeat across 2+ files
- One-time wrappers around well-known APIs are clutter, not reuse (complements deslop)
- When a plan story has `reuse` or `constraints` fields, those are mandatory — read referenced files before implementing
- When generalizing an existing feature, start by extracting the existing code into a shared module
