# Mining Guardian — Session Handoff

<!--
INSTRUCTIONS FOR USE:
1. Copy this file to docs/handoffs/HANDOFF_<YYYY-MM-DD>.md
2. Fill in every section. No <placeholder> text in the committed version.
3. If a section has nothing to report, write "Nothing to report this session." — do not delete the section heading.
4. Append-only for Decisions. Never edit a prior D-N entry.
5. Do not use markdown italic asterisks (single * around text).
-->

---

```yaml
date: YYYY-MM-DD
session_id: <pplx session hash or "manual">
last_commit_on_main: <short SHA> — <one-line commit message>
agent: Computer (autonomous agent)
repo: mg-repo (Mining Guardian)
```

---

## Open questions for Rob

_These are the first things Rob should read. List every unresolved question or ambiguity from this session that Rob needs to answer before the next session proceeds._

1. 

---

## Mantras and standing rules in effect

The following rules are always in force. Do not skip, abbreviate, or reinterpret them:

- Leave no data behind. Every piece of enrichment, every belief, every intermediate file is documented or committed before the session closes.
- Step by step. One action at a time. No "while I'm at it" changes.
- Late and perfect over early and wrong. Do not push a fix under time pressure. Stop, confirm, then act.
- Stay local — Bitcoin SHA-256 only. No cloud AI inference for mining operational data. Qwen on ROBS-PC 4090 or local Ollama on Mini only.
- Never call SQLite live. The program is on Postgres. Any SQLite reference is a bug.
- No destructive operations without confirming with Rob first. This includes: `docker volume rm`, `DROP TABLE`, `DELETE FROM`, any `rm -rf` on repo or data directories, and any password change on a live service.
- Use `gh` CLI for all GitHub operations, not browser_task. No PR creation, merge, or review through the browser tool.
- Every fix PR flips the corresponding MG_UNIFIED_TODO_LIST row from 🔴 to ✅ in the same commit.
- Every session ends with a HANDOFF_<DATE>.md. Every session starts by reading the latest handoff. Failure to read the prior handoff before proposing a fix is a protocol violation Rob can use to stop the session immediately.

---

## Host topology — what is LIVE right now

_Do not copy the plan here. Copy what actually exists today._

| Host | What is running | What data it holds | Key notes |
|---|---|---|---|
| Hostinger VPS (`187.124.247.182` / Tailscale `100.106.123.83`) | | | |
| ROBS-PC (Windows 11, RTX 4090) | | | |
| Mac Mini (Fort Worth customer site) | | | |
| Cloudflare (`fieslerfamily.com`) | | | |

---

## Do not touch

_List every component, file, operation, or service that must not be modified until Rob explicitly says go. Be specific._

- 

---

## Things I currently believe that need re-verification

_This is the section that would have caught the 2026-05-02 morning failure. List every belief older than 24 hours that this session is acting on. For each belief, note when it was last verified and what the verification step would be. Mark beliefs that must be re-verified BEFORE acting with [VERIFY FIRST]._

**How to use this section:** Before acting on any belief listed here, stop and verify it is still true. Do not skip this. The morning of 2026-05-02 is the example of what happens when beliefs go unverified.

**Worked example (do not delete — leave as a reference):**

> I believe Postgres on ROBS-PC (`mining-guardian-db` container) is NOT empty — it has 317 seeded rows plus the 2026-04-27 355,626-row import. [VERIFY FIRST]
> Last verified: 2026-04-27 (via `catalog_updater.py` run output).
> Verify step: `docker exec mining-guardian-db psql -U mg_catalog -d mining_guardian -c "SELECT COUNT(*) FROM hardware.miner_models;"` — must return > 0.
> Risk if wrong: Any "seed from scratch" action would destroy the existing import.

---

_Beliefs for this session:_

1. 

---

## Today's PRs / branches / commits

| PR / branch / commit | Description | Status | Notes |
|---|---|---|---|
| | | draft / open / merged / blocked | |

---

## Open work in priority order

_Numbered list. Copy current state from MG_UNIFIED_TODO_LIST.md as of this session. Mark items touched this session._

1. 

---

## Decisions made today

_Append-only. D-N format. Include date, what was decided, and why it is locked._

<!-- If no new decisions were made, write: "No new decisions locked this session." -->

---

## Costs / credits burned today

_Order-of-magnitude estimate so Rob can see the spend trend across sessions._

- Subagents spawned: ~X
- Memory writes: ~Y
- PR reads / fetches: ~Z
- Web fetches / searches: ~W
- Notable expensive operations: 

---

## Files created/modified this session

| Path | Purpose |
|---|---|
| | |

---

## Failure modes spotted this session

_Over-document here. Future sessions learn from this one's near-misses. List every moment where a wrong action was almost taken, every assumption that turned out to be false, every place where the protocol caught something._

- 

---

## Next session start checklist

Complete in order. Do not skip steps.

1. Read this handoff file (docs/handoffs/HANDOFF_<DATE>.md) in full.
2. Read the "Things I currently believe that need re-verification" section and re-verify every [VERIFY FIRST] belief before taking any action.
3. Check "Do not touch" — confirm no planned work conflicts with any item on that list.
4. Review "Open questions for Rob" — if Rob has not answered them, ask before proceeding.
5. Check docs/DECISIONS.md for any new entries since the last session.
6. Check docs/MG_UNIFIED_TODO_LIST.md for the current 🔴 open items.
7. Confirm the current last commit on main matches what this handoff records.
8. If anything in this handoff feels wrong or stale, STOP and confirm with Rob before acting.
