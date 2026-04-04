---
name: Testing Rules
description: TDD workflow and testing conventions
globs: ["**/*.test.ts", "**/*.test.tsx", "**/*.spec.ts", "**/*.spec.tsx"]
---

# Testing Rules

- Red-Green-Refactor: failing test first, minimal code to pass, then clean up
- Write a reproducing test before fixing any bug
- Test behavior not implementation; AAA pattern (Arrange, Act, Assert)
- Coverage: 100% for auth/payments/mutations, 80% line for business logic, best-effort for UI
- Name: `it("[action] [result] [condition]")` (e.g., `it("returns null when user not found")`)
- Mock at boundaries only (APIs, DB, third-party) -- prefer MSW for HTTP mocks
- Colocate unit tests; integration in `__tests__/`; E2E in `e2e/`
- No snapshot tests for logic; no flaky tests -- fix or delete
