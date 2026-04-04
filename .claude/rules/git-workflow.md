---
name: Git Workflow
description: Commit format, branching, and PR conventions
---

# Git Workflow

- Commits: `<type>(<scope>): <description>` -- imperative, lowercase, no period, max 72 chars
- Types: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `chore`
- Branches: `<type>/<ticket-id>-<description>` from `develop`; squash merge back; delete after
- PRs: title matches commit format; under 500 lines; self-review before requesting review
