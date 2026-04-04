---
name: continuous-learning
description: >
  Extract generalizable patterns from recurring corrections, stage them as
  structured learning entries, and gate promotion into rules/skills. The
  local-first precursor to ACS cross-project memory. Invoked by /learn
  (pattern mode) and /wrap-up; reviewed via /evolve.
---

# Continuous Learning

Turn repeated mistakes and discovered patterns into permanent toolkit knowledge. Philosophy: **thin skills, fat memory** — accumulate raw observations locally, promote only what survives the staging gate.

## Memory Directory Structure

```
.ai/memory/
├── session-state.json      # Current session state
├── learnings/              # Extracted learning entries ({date}-{id}.json)
├── staging/                # Learnings pending promotion ({id}.json)
├── checkpoints/            # Session checkpoints ({timestamp}.json)
└── archive/                # Archived old entries ({date}-{id}.json)
```

Directories are created on first write. Entries are **append-only** — never delete, only archive.

## Learning Entry Schema

```json
{
  "id": "learn-{uuid}",
  "timestamp": "ISO-8601",
  "source_session": "session-id or branch name",
  "pattern": "Description of what was learned",
  "category": "typescript|security|testing|performance|react|accessibility|workflow",
  "proposed_rule": "Concise rule statement that could be added to rules/",
  "confidence": 0.0,
  "usage_count": 0,
  "first_seen": "ISO-8601",
  "last_seen": "ISO-8601",
  "failures": 0,
  "promoted": false
}
```

## Pattern Extraction Workflow

**1. Identify** — Scan for recurring corrections, novel solutions, integration patterns, or debugging strategies that resolved issues.

**2. Extract** — Create a learning entry in `.ai/memory/learnings/{date}-{id}.json`. Set confidence: `0.8` (user corrected twice), `0.5` (used successfully once), `0.3` (observed, untested).

**3. Stage** — Copy generalizable entries to `.ai/memory/staging/{id}.json`. Staging is a holding area for promotion candidates.

**4. Track** — On each subsequent use, increment `usage_count` and update `last_seen`. On each failure, increment `failures`.

**5. Promote** — Via `/evolve`. The staging gate prevents premature promotion:

| Criterion | Threshold |
|-----------|-----------|
| Usage count | >= 3 |
| Time in staging | >= 14 days |
| Failure count | 0 |

Entries passing all three are flagged by `/evolve`. Promotion requires human approval.

## Integration Points

| Command | Behavior |
|---------|----------|
| `/learn --pattern` | Extracts a pattern, creates learning entry, stages it |
| `/wrap-up` | Scans session for unextracted patterns, creates entries |
| `/evolve` | Reviews staged entries against the gate, proposes promotions |
| `/memory-clean` | Archives old entries, keeps memory lean |
| `/iterate` | Increments `usage_count` when a staged pattern is applied |

## Anti-Patterns

- Promoting after a single use — wait for the gate
- Storing vague observations ("code was messy") — be specific and actionable
- Deleting entries instead of archiving — breaks audit trail
- Skipping the human approval step in `/evolve`

## Related

- **`napkin`** — The real-time capture layer. Napkin logs raw corrections, mistakes, and patterns as they happen during a session. Continuous-learning draws from these (and other sources) to extract structured, generalizable patterns worth promoting.
- **Escalation path**: napkin captures raw observations → `/learn` extracts recurring patterns into `.ai/memory/staging/` → `/evolve` promotes to permanent `rules/` or `skills/`
- **Key difference**: napkin is per-repo, committed, shared (`.claude/napkin.md`). Continuous-learning is personal, gitignored (`.ai/memory/`). Napkin is always-on; continuous-learning is invoked explicitly via `/learn` and `/evolve`.