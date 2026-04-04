---
name: Performance
description: Model selection and context efficiency
---

# Performance

- Models: Haiku for simple edits, Sonnet for standard dev (default), Opus for architecture/planning
- Prompt caching hygiene: keep prompt prefixes stable — static instructions/tools first, dynamic/session-specific content later
- Prefer model stability inside a single long-running session; avoid mid-session model switching unless intentional
- Keep tool definitions stable within an active session; avoid adding/removing tools mid-session when cache efficiency matters
- Prefer sending updated context as new messages (or reminders) instead of rewriting core prompt anchors
- Grep first, then Read specific line ranges -- never read entire files speculatively
- Batch independent tool calls in parallel; use Glob/Grep/Read/Edit directly, Bash only for git/npm
- mgrep for natural-language exploration when Grep pattern is unclear
