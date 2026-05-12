# Mining Guardian — Strategic Planning Documents

> **For future Claude sessions and humans alike.** This directory holds the planning documents that describe where Mining Guardian is going, how, and why. The Master Execution Plan is the operational document; the three audits exist to make the plan defensible.
>
> **The single source of truth for what's been done is [`../EXECUTION_PLAN_STATUS.md`](../EXECUTION_PLAN_STATUS.md), NOT this directory.** These planning docs are stable references; the status file is the living layer.

---

## Quick navigation

**If you're asking…**

| Question | Start here |
|---|---|
| "What's the next thing to work on?" | [`../EXECUTION_PLAN_STATUS.md`](../EXECUTION_PLAN_STATUS.md) → find first `[ ]` in dependency order |
| "What's been done already?" | [`../EXECUTION_PLAN_STATUS.md`](../EXECUTION_PLAN_STATUS.md) → look for `[X]` and `[~]` rows |
| "Why are we doing W##?" | [`04_MASTER_EXECUTION_PLAN.md`](04_MASTER_EXECUTION_PLAN.md) → find the W## section |
| "What did the audit find specifically?" | [`01_PERFORMANCE_AUDIT.md`](01_PERFORMANCE_AUDIT.md) — performance findings in 3 tiers |
| "How do the two databases interact?" | [`02_TWO_DATABASE_DEEP_DIVE.md`](02_TWO_DATABASE_DEEP_DIVE.md) — operational↔catalog flow, write-only catalog tables, Perplexity gap |
| "Why does the audit believe A+ is reachable?" | [`03_OVERALL_ASSESSMENT.md`](03_OVERALL_ASSESSMENT.md) — three-layer ceiling, risk factors |
| "What's changed since the Plan was written?" | [`AMENDMENTS_2026-05-12.md`](AMENDMENTS_2026-05-12.md) — every W-item adjustment with rationale |
| "Are the W##-done claims actually true?" | [`RECONCILIATION_2026-05-12.md`](RECONCILIATION_2026-05-12.md) — grep receipts against `main` |
| "How do we do the two-Postgres split (W14)?" | [`W14_PREP.md`](W14_PREP.md) — operational plan with rollbacks |

---

## Document descriptions

### [`01_PERFORMANCE_AUDIT.md`](01_PERFORMANCE_AUDIT.md) — Performance & Capability Audit

Source: Outside read on 2026-05-09, ahead of May 10 cutover.

Three tiers of findings:
- **Tier 1** — Pre-cutover verification (4 items: LLM model override, sleep settings, service health, backup destination)
- **Tier 2** — High-impact performance work for Week 1 post-cutover (7 items: connection pool, TO_CHAR cleanup, Postgres tuning, ProcessType, knowledge.json split, pipelining, AMS WebSocket)
- **Tier 3** — Things you may not have considered (8 items: autovacuum, partitioning, watchdog, time zones, Perplexity health, backups, repo hygiene, OpenClaw)

Most of these became numbered W-items in the Master Plan. Read this when you want the *original rationale* for a fix; read the Plan when you want the *operational steps*.

### [`02_TWO_DATABASE_DEEP_DIVE.md`](02_TWO_DATABASE_DEEP_DIVE.md) — Two-Database Deep Dive

Architectural view of the operational ↔ catalog interaction. Key claims:
- ~60% of catalog data is currently write-only (the AI writes failure patterns, war stories, model_known_issues to catalog, but doesn't read them back)
- The Perplexity research feed has no integration path into Mining Guardian (zero references in the repo)
- Pass 2 weekly training doesn't query the catalog at all
- Several catalog read paths would be hours-to-days to add, not weeks

These map to W06-W12 in the Master Plan.

### [`03_OVERALL_ASSESSMENT.md`](03_OVERALL_ASSESSMENT.md) — Overall Assessment & Potential

The "B+ today, A+ ceiling in 6 months" assessment. Argues the gap is **additive** (finish what's started), not **corrective** (rewrite what's built). Three-layer ceiling:
- **Layer 1** — single-site Mining Guardian fully realized (~6-10 weeks)
- **Layer 2** — multi-site federation at BiXBiT scale (~6-12 months)
- **Layer 3** — productizable platform (business decision)

Read this when you need to remember *why the discipline matters* — it explains the operating principles that earned the B+ and makes the case that they're the same ones that close the gap to A+.

### [`04_MASTER_EXECUTION_PLAN.md`](04_MASTER_EXECUTION_PLAN.md) — Master Execution Plan

22 work items (W01-W22) in dependency order across 6 phases. Each item has files, effort estimate, risk level, blocked-by relations, "what to do," "how to verify," "definition of done."

**This is the operational document.** When you're picking up work, this tells you the structure.

**But trust the status file over the Plan for current state.** The Plan was written 2026-05-09; everything since has been amendments. Always cross-reference with `EXECUTION_PLAN_STATUS.md`.

### [`AMENDMENTS_2026-05-12.md`](AMENDMENTS_2026-05-12.md) — Plan Amendments (living)

Every meaningful delta between the Plan as written and reality. New W-items (W23-W25), scope adjustments (W05 from 6 to 9 plists), sub-items (W14a, W14b), status corrections (W16 done, W17 untouched, W03 half-done). Cite amendments by ID (A01, A02, ...) in commit messages.

This is where the *rationale* for changes lives. The status file shows *what changed*; this file explains *why*.

### [`RECONCILIATION_2026-05-12.md`](RECONCILIATION_2026-05-12.md) — Reconciliation Receipts (snapshot)

Grep output for W16/W17/W05/W03/W02 status, run against `main` HEAD `9d2e117` on 2026-05-12. **Trust these numbers over chat memory.** If a future Claude session disagrees with these, re-run the commands — they're deterministic.

The companion script `../../scripts/run_reconciliation_greps.sh` regenerates this data on demand against the current `main`. Run it when you want fresh receipts.

### [`W14_PREP.md`](W14_PREP.md) — Two-Postgres-Instance Split Prep

The operational plan for W14a → W14 → W14b. Includes:
- State A vs State B mental model with diagrams
- Decision matrix (D1-D7) for choices the operator hasn't made yet
- Step-by-step plan with rollbacks for each step
- The cohort guard test contents
- The CLAUDE.md and .env.example edits

Read this **before starting any Phase 1.5 work**.

---

## File conventions

| Filename pattern | Lifecycle |
|---|---|
| `01_*.md` through `04_*.md` | **Frozen snapshots** of the 2026-05-09 audit reports + Plan. Do not edit. If something is wrong, file an amendment in `AMENDMENTS_<date>.md`. |
| `AMENDMENTS_<date>.md` | **Living amendment files.** When the count of amendments in one file grows past ~10 or the file passes a quarter boundary, start a new dated file. Each amendment has a stable ID. |
| `RECONCILIATION_<date>.md` | **Point-in-time snapshots.** Each dated reconciliation captures `main`-state on that date. They're not edited after the fact. |
| `W##_PREP.md` | **Living prep docs** for L-effort items. Updated as decisions are made; archived once the W-item completes. |

---

## How to open a fresh session

> *Continuing the Mining Guardian project. The execution plan status is at `docs/EXECUTION_PLAN_STATUS.md`. The strategic docs are in `docs/strategy/`. Currently working on W##. The relevant amendment is A## in `docs/strategy/AMENDMENTS_2026-05-12.md`.*

That single paragraph gives a fresh Claude session the entry points to everything else. Trust the files; if any chat memory conflicts with a file, the file wins.

---

*Maintained as a living index. Add new strategic docs here when they land.*
