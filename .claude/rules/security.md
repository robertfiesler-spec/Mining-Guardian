---
name: Security Rules
description: Non-negotiable security patterns for Next.js apps
---

# Security Rules

- Validate all inputs at API boundaries with Zod schemas -- never trust raw input
- Parameterized queries only -- no string interpolation for SQL/DB calls
- Never use `dangerouslySetInnerHTML` without DOMPurify sanitization
- Auth check in every Server Component/API route that requires it: `if (!session) redirect('/login')`
- Secrets in `process.env` only -- validate required env vars at startup, fail fast if missing
- Never log passwords, tokens, PII, or full user objects -- mask sensitive fields
- CSRF: Server Actions have built-in protection; custom API routes must verify `origin` header
- Rate limit auth endpoints and sensitive mutations (e.g., Upstash Ratelimit)
- Security headers in `next.config.js`: HSTS, X-Frame-Options, X-Content-Type-Options
- `.env.local` for secrets (not `.env` which is public in Next.js)
