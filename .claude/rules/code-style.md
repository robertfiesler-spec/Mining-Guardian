---
name: Code Style
description: Naming, structure, and formatting conventions
globs: ["**/*.ts", "**/*.tsx"]
---

# Code Style

- Naming: Components `PascalCase.tsx` | Hooks `use*.ts` | Utils `camelCase.ts` | Constants `SCREAMING_SNAKE`
- Props interfaces: `{ComponentName}Props` | Non-component files: `kebab-case.ts`
- Component order: imports, types, constants, named export, hooks, handlers, early returns, render
- Named exports only (except Next.js pages/layouts)
- Early returns over nested conditionals; no magic numbers
- Comments explain "why" not "what"
- Colocate by feature: `features/auth/components/` not `components/Auth/`
