---
name: pyramid-summary
description: >
  Generate and consume multi-resolution project summaries at three zoom levels
  (overview, modules, files). Agents load only the depth they need per task,
  reducing token waste on large codebases. Use when starting sessions, planning
  features, or onboarding to unfamiliar projects.
---

# Pyramid Summary

Reversible summarization at multiple zoom levels. Compress project context without losing the ability to expand back to full detail.

The pyramid has three levels. Each is a progressively more detailed view of the same codebase. Agents use a decision tree to load only what they need — a typo fix doesn't require the same context as an architectural refactor.

## Pyramid Levels

### L1: Project Overview (~50-100 lines)

The 30-second orientation. Enough to understand what this project is and how it's structured.

**Contains:**
- Project purpose and domain (1-2 sentences)
- Architecture style (monorepo, monolith, microservices)
- Tech stack with versions
- Top-level directory structure (annotated)
- Major subsystems (1 paragraph each)
- External integrations (databases, APIs, third-party services)
- Deployment model

**Use for:** commit messages, doc updates, config changes, PR descriptions, "what does this project do?"

**Example L1 entry:**

```markdown
# L1: Project Overview

## Purpose
E-commerce platform for handmade goods. Sellers list products, buyers browse/purchase, platform handles payments and shipping coordination.

## Architecture
Next.js 14 monolith with App Router. PostgreSQL via Prisma. Stripe for payments. S3 for media. Deployed on Vercel.

## Stack
- Next.js 14.1 (App Router) / TypeScript 5.3
- Tailwind CSS + Radix UI primitives
- Prisma 5.8 + PostgreSQL 16
- Stripe SDK, AWS S3 SDK
- Vitest + Playwright

## Directory Structure
src/
  app/           # Next.js routes (pages, layouts, API routes)
  features/      # Domain modules (auth, products, orders, payments)
  components/    # Shared UI (buttons, forms, modals)
  lib/           # Utilities (db client, auth helpers, validation)

## Subsystems
- **Auth**: Email/password + OAuth (Google). JWT sessions via next-auth.
- **Products**: CRUD with image upload (S3), search via Prisma full-text.
- **Orders**: Cart → checkout → payment → fulfillment state machine.
- **Payments**: Stripe Checkout Sessions with webhook confirmation.
- **Notifications**: Email via Resend. No real-time yet.
```

### L2: Module Map (~200-400 lines)

What each module does, how they connect, and how to work within them.

**Contains per module:**
- Purpose (one sentence)
- Key files (3-5 most important)
- Public API surface (exported functions, types, components)
- Patterns used (e.g., "repository pattern", "Server Components by default")
- Dependencies on other modules

**Also includes:**
- Data flow between modules (what calls what)
- Shared utilities and where they live
- Testing strategy per module

**Use for:** single-module features, code review, finding where to add functionality, understanding data flow.

**Example L2 module entry:**

```markdown
## Module: orders

**Purpose**: Manages cart, checkout, and order fulfillment lifecycle.

**Key Files:**
- `src/features/orders/actions/checkout.ts` - Server Action for checkout flow
- `src/features/orders/components/Cart.tsx` - Cart UI with optimistic updates
- `src/features/orders/lib/order-machine.ts` - State machine (pending→paid→shipped→delivered)
- `src/features/orders/types.ts` - Order, CartItem, CheckoutSession types

**Public API:**
- `createCheckoutSession(cartId: string): Promise<CheckoutSession>`
- `updateOrderStatus(orderId: string, status: OrderStatus): Promise<Order>`
- `<Cart />`, `<OrderHistory />`, `<CheckoutForm />` components

**Patterns:**
- State machine for order lifecycle (no ad-hoc status updates)
- Optimistic UI updates on cart mutations
- Stripe webhook handler validates signatures before processing

**Dependencies:**
- `payments` (creates Stripe sessions during checkout)
- `products` (reads product data for cart display)
- `auth` (validates user session on all mutations)
```

### L3: File Detail (~500-1000 lines)

Key functions, types, and non-obvious implementation details for significant files.

**Contains per significant file:**
- Key functions/classes with signatures
- Important types and interfaces
- Non-obvious implementation details ("uses optimistic updates", "caches for 5 minutes")
- Known edge cases or gotchas
- Test coverage notes

**Significance threshold** (include files that match any):
- More than 100 lines of code
- Imported by 3+ other files
- Matches `**/types.ts`, `**/index.ts`, `**/utils.ts`
- Contains business logic, not just UI rendering

**Skip:** test files, generated files, vendor/node_modules, config-only files, simple re-exports.

**Use for:** deep debugging, cross-module refactoring, security reviews, understanding complex interactions.

**Example L3 file entry:**

```markdown
### src/features/orders/lib/order-machine.ts (87 lines)

**Functions:**
- `transition(order: Order, event: OrderEvent): Order` - Pure state machine. Throws on invalid transitions. Events: `pay`, `ship`, `deliver`, `cancel`, `refund`.
- `canTransition(status: OrderStatus, event: OrderEvent): boolean` - Check without mutating.

**Types:**
- `OrderStatus = 'pending' | 'paid' | 'shipped' | 'delivered' | 'cancelled' | 'refunded'`
- `OrderEvent = 'pay' | 'ship' | 'deliver' | 'cancel' | 'refund'`

**Gotchas:**
- `cancel` is only valid from `pending` or `paid` (not after shipping).
- `refund` triggers a Stripe refund via side effect in the action layer, NOT in this pure module.
- No partial refunds yet — always full amount.
```

## Generating Summaries

Generation is command-triggered via `/summarize`. Not automatic — generating requires reading significant code and costs tokens.

### When to Generate

- After `/kickoff` on a new or unfamiliar project
- Before `/create-plan` when you need architectural understanding
- After completing a major feature or refactor (manual refresh)
- When summaries are 50+ commits stale (you'll be warned)

### Generation Process

1. **Scan**: Glob the file tree. Identify module boundaries by directory structure (`src/features/*`, `app/*`, `lib/*`, or project-specific patterns).

2. **Build L1** (top-down, no source code needed):
   - Read `package.json`, `CLAUDE.md`, `README.md`, top-level config files
   - Read directory structure at depth 2
   - Synthesize the overview

3. **Build L2** (module scan, 3-5 files per module):
   - Per module: read index/barrel file, type definitions, primary entry points
   - Extract public API surface, patterns, inter-module dependencies
   - Note shared utilities

4. **Build L3** (selective deep read):
   - Filter to significant files (>100 lines, 3+ importers, types/index/utils)
   - Per file: extract key functions with signatures, important types, gotchas
   - Skip tests, generated, vendor

5. **Write metadata**: Save `.pyramid-meta.json` with git SHA and timestamps.

### Partial Regeneration

Don't regenerate everything when only one area changed:

```bash
/summarize --level L2          # Refresh only the module map
/summarize --module auth       # Refresh only the auth module in L2 and L3
/summarize --level L1          # Refresh only the project overview
```

### File Locations

Summaries are stored per-project (not in the skill directory):

```
.claude/pyramid/
  L1-overview.md          # Project overview
  L2-modules.md           # Module-level map
  L3-files.md             # File-level detail
  .pyramid-meta.json      # Generation metadata
```

**Metadata schema:**

```json
{
  "generated_at": "2026-02-08T15:30:00Z",
  "git_sha": "abc1234",
  "branch": "main",
  "levels": {
    "L1": { "generated_at": "...", "line_count": 87, "git_sha": "..." },
    "L2": { "generated_at": "...", "line_count": 312, "git_sha": "..." },
    "L3": { "generated_at": "...", "line_count": 748, "git_sha": "..." }
  },
  "file_count": 142,
  "module_count": 8
}
```

## Consuming Summaries

### Decision Tree

At the start of any task, determine what depth to load:

```
What is the task scope?
│
├── Project-wide (architecture decisions, planning, onboarding)
│   → Read L1 + L2
│
├── Single module (feature, bug fix, tests within one area)
│   → Read L1 + relevant L2 section only
│
├── Cross-module deep work (refactor, debug, security review)
│   → Read L1 + L2 + relevant L3 sections
│
├── Simple known-location change (typo, config, doc update)
│   → Read L1 only (or nothing if already oriented)
│
└── Unfamiliar codebase (first session, new contributor)
    → Read L1 + L2, then L3 sections as needed during work
```

### Reading Specific Sections

L2 and L3 use markdown headers per module (`## Module: auth`, `## Module: payments`). To load only what you need:

1. Read L1 (always cheap, ~50-100 lines)
2. Identify the target module from the task description or story's `files` field
3. Read only the relevant `## Module: <name>` section from L2 using line offsets
4. If deeper detail needed, read the matching section from L3

### Integration with Commands

| Command | Pyramid Behavior |
|---------|-----------------|
| `/kickoff` | Read L1 if pyramid exists. Suggest `/summarize` if missing. |
| `/create-plan` | Read L1 + L2 to inform story decomposition and file identification. |
| `/iterate` | Read L1 + relevant L2 section for current story's module. |
| `/ai-loop` | Each iteration reads L1 + L2 module section. Keeps per-iteration context lean. |
| `/review` | Read L1 to verify changes align with architecture. |

## Staleness and Maintenance

### Detecting Stale Summaries

Compare the git SHA in `.pyramid-meta.json` to current HEAD:

| Commit Distance | Action |
|-----------------|--------|
| 0-50 | Summaries are fresh. Use as-is. |
| 50-200 | Warn: "Pyramid summaries are N commits stale. Consider `/summarize` to refresh." |
| 200+ | Strongly recommend refresh. Mark as "potentially inaccurate" in output. |

### When Summaries Are Wrong

Summaries are point-in-time snapshots. If you discover a summary claim that contradicts actual code:

1. Trust the actual code, not the summary
2. Note the discrepancy for the user
3. Suggest running `/summarize --module <affected>` to fix

### Maintenance Rules

- Summaries do NOT auto-update — this is deliberate (cost control)
- Partial refresh (`--module`, `--level`) is cheaper than full regeneration
- After major refactors touching 20+ files, recommend full refresh
- Summaries are gitignored (`.claude/pyramid/` in `.gitignore`)

## Anti-Patterns

**Don't do this:**

- Loading all three levels for a simple config change (L1 is enough)
- Regenerating on every commit (expensive, use staleness detection instead)
- Including test files in L3 (tests describe behavior but aren't architectural context)
- Treating summaries as authoritative when they're stale (always verify critical claims against actual code)
- Putting summaries in git (they're per-developer context, not shared artifacts)

**Do this instead:**

- Start with L1 and expand only if the task demands it
- Regenerate when you feel lost or after major structural changes
- Use `--module` for targeted refresh after focused work
- Cross-reference L3 claims with actual code before making critical decisions
