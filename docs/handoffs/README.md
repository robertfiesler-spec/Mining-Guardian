# Mining Guardian — Session Handoff Protocol

**Established:** 2026-05-02
**Author:** Computer (autonomous agent)
**Maintainer:** Rob Fiesler

---

## Why this protocol exists

On the morning of **2026-05-02**, a full session began without reading prior context. The agent proposed fixes for a split-brain bug that had already been closed (PR #15, PR #22), misidentified which Postgres instance lives on which host, believed `hardware.miner_models` was empty when it had 317+ rows, and nearly issued a `docker volume rm` against the live catalog volume that holds the 2026-04-27 355,626-row import. Rob had to stop the session manually. Roughly an hour was lost to wrong framings before a corrected ground-truth document (`STATE_OF_THE_SYSTEM_2026-05-02.md`) was written.

The root cause: the agent had no structured record of what it believed, what it had done, and what it was not allowed to touch. Nothing forced a verification step before acting.

This protocol is the failsafe.

---

## The hard rule

**Any new session that proposes or executes a fix without first reading the latest handoff file in this directory is a protocol violation.**

Rob can and should stop the session immediately if this rule is broken. "I forgot to read the handoff" is not a mitigating circumstance — it is the exact failure mode this protocol was designed to prevent.

---

## How it works

**At the end of every working session**, Computer creates:

```
docs/handoffs/HANDOFF_<YYYY-MM-DD>.md
```

If more than one session happens on the same calendar day, append a suffix: `HANDOFF_2026-05-02b.md`.

**At the start of every new session**, Computer reads the most recent `HANDOFF_<DATE>.md` before proposing or touching anything. Reading means:

1. Opening the file.
2. Working through the "Things I currently believe that need re-verification" section and re-verifying any belief older than 24 hours before acting on it.
3. Checking "Do not touch" and confirming no planned action conflicts with it.
4. Confirming with Rob if anything in the handoff feels stale or wrong.

---

## What the template covers

See [HANDOFF_TEMPLATE.md](HANDOFF_TEMPLATE.md) for the canonical copy-paste template. Every handoff must include, in order:

1. YAML-style header (date, session_id, last commit, agent, repo)
2. Open questions for Rob
3. Mantras and standing rules in effect
4. Host topology — what is live right now
5. Do not touch
6. Things I currently believe that need re-verification
7. Today's PRs / branches / commits
8. Open work in priority order
9. Decisions made today
10. Costs / credits burned today
11. Files created/modified this session
12. Failure modes spotted this session
13. Next session start checklist

---

## Where to find things

| File | Purpose |
|---|---|
| `docs/handoffs/HANDOFF_TEMPLATE.md` | Canonical blank template — copy this for every new handoff |
| `docs/handoffs/HANDOFF_<DATE>.md` | Completed handoffs — latest is the one to read at session start |
| `docs/STATE_OF_THE_SYSTEM_2026-05-02.md` | Ground-truth system state document written after the 2026-05-02 morning incident |
| `docs/INTEL_CATALOG_FULL_BRIEF_2026-05-02.md` | Intelligence catalog full brief as of 2026-05-02 |
| `docs/DECISIONS.md` | Canonical locked decisions log (D-1 through D-16+) |
| `docs/MG_UNIFIED_TODO_LIST.md` | Master to-do list with 🔴/✅ status per item |
| `docs/INSTALLER_UX_BACKLOG_2026-05-01.md` | 10 installer bugs to fix before Mac Mini retry |

---

## Related cross-references

- [STATE_OF_THE_SYSTEM_2026-05-02.md](../STATE_OF_THE_SYSTEM_2026-05-02.md) — the document that was written to recover ground truth after the 2026-05-02 morning failure
- [INTEL_CATALOG_FULL_BRIEF_2026-05-02.md](../INTEL_CATALOG_FULL_BRIEF_2026-05-02.md) — catalog state brief as of the same date

---

## Protocol version history

| Date | Change |
|---|---|
| 2026-05-02 | D-15: Protocol locked. Every session ends with a handoff. Every session starts by reading it. |
