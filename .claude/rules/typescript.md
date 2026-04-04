---
name: TypeScript Patterns
description: Project-specific TypeScript constraints beyond standard strict mode
globs: ["**/*.ts", "**/*.tsx"]
---

# TypeScript Patterns

- `interface` for object shapes, `type` for unions/intersections
- `satisfies` over `as` for type checking without widening
- `as const` for literal types; const objects over enums
- Explicit return types on all exported functions
- Discriminated unions with exhaustive `never` check in switch default
- Constrained generics (`K extends keyof T`) over unconstrained
- No `any`, no `!` non-null assertions, no `@ts-ignore`
- No `as` type assertions -- use type guards or `satisfies`
- Prefer built-in utility types (`Pick`, `Omit`, `Partial`, `ReturnType`)
