---
name: Error Handling
description: Error patterns for TypeScript and React applications
globs: ["**/*.ts", "**/*.tsx"]
---

# Error Handling

- No empty catch blocks -- always log with context or rethrow
- Create typed error classes extending `Error` with a `code` field for programmatic handling
- React error boundaries at every route layout level -- never let errors crash the full app
- Structured error logging: include `userId`, `action`, `stack`, and relevant request context
- API error responses use consistent shape: `{ error: string, code: string, details?: unknown }`
- Use `Result<T>` discriminated unions for expected failures (validation, not-found) -- reserve `throw` for unexpected errors
- Server Actions: wrap in try/catch, return `{ success: boolean, error?: string }` -- never let raw errors reach the client
- Always handle Promise rejections -- no fire-and-forget `.then()` without `.catch()`
