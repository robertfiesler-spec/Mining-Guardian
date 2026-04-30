# 03 — Technical Decisions

These are the technical choices I'm recommending. Each one has reasoning. You sign off on them or push back. None of these are religion — they're tradeoffs, and the numbers change if your constraints change.

**Read alongside `02_QUESTIONNAIRE.md`** — answers there sometimes change recommendations here.

---

## D1. Frontend framework

**Recommendation: React (with Vite + TypeScript)**

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **React** | Largest ecosystem; you can hire help on Fiverr/Upwork easily; great docs; component libraries everywhere | Slightly heavier than Svelte/Solid | ✅ winner — boring is good |
| Vue | Smaller, friendlier API | Smaller hiring pool; you'll find more React tutorials when stuck | second |
| Svelte/SvelteKit | Tiny bundle, great DX | Smaller ecosystem; harder to hire for; less mature for complex state | not for v1 |
| Vanilla JS / HTMX | Zero build step, maximum simplicity | The Intelligence Report and fleet view will get complex enough that you'll regret this in week 3 | no |

**Why React specifically:** You're new to this. When you Google "how do I show a toast in [framework]", React has 100x more answers. Your time is better spent on Mining Guardian's domain logic than fighting the tooling.

**Build tool:** **Vite.** Fast cold start, fast HMR, no Webpack config nightmares.

**TypeScript: yes.** Catches half the bugs before runtime, the brand will be glad we did, and it's the same syntax as plain JS plus type annotations. Cost is small, value is huge for a long-lived app.

---

## D2. UI component library

**Recommendation: Tailwind CSS + shadcn/ui (copy-paste components, not a dependency)**

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Tailwind + shadcn/ui** | Direct CSS control; matches a custom brand cleanly; components copy into your repo so you own them | More to wire up than a kit | ✅ winner — gives us the dark space-black brand |
| Material-UI (MUI) | Full kit, fast | Looks like Material, fights against the dark/industrial brand | no — wrong vibe |
| Chakra UI | Friendly, themeable | Heavier; default style still has to be overridden hard | no |
| Ant Design | Enterprise-y kit | Looks like an Excel-era enterprise app | no — wrong vibe |
| Radix UI (without Tailwind) | Excellent accessibility primitives | More CSS work | runner-up — shadcn already builds on Radix |

**Why this combo:** shadcn/ui is built on Radix (excellent accessibility) and Tailwind (utility CSS). Components live IN your repo, you tweak them freely, and the dark-mode, industrial brand fits naturally. No "Material design" fight.

---

## D3. Charts / data viz

**Recommendation: Recharts for the v1 charts; consider Visx or D3 directly only if Recharts hits a wall**

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Recharts** | React-native, easy theming, covers line/area/bar/pie | Slightly limited customization for exotic charts | ✅ for v1 — Intelligence Report's charts are standard |
| ECharts (via echarts-for-react) | Most powerful, gorgeous defaults | Heavier bundle; theming is JSON-config-heavy | overkill |
| Chart.js | Simple | Imperative, awkward in React | no |
| D3 directly | Anything is possible | You'll spend 3 weekends building one chart | not yet |

**Note:** We are NOT replacing Grafana with the app's charts. The app shows summary tiles and a couple of trend lines. Power users still open Grafana for deep dives.

---

## D4. Backend — for the app's web server

**The Mac Mini already runs Postgres + 9 launchd daemons in Python.** We need a tiny web server to serve the React app and proxy a few new endpoints.

**Recommendation: Fastify (Node.js, TypeScript)**

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Fastify (Node)** | Tiny, fast, TypeScript-first; same language as frontend | Adds Node to the Mac Mini stack | ✅ winner |
| Extend the existing Python API (FastAPI) | No new runtime | You'd be returning HTML/serving static assets from the same process that does scanning — separation hurts | no |
| Express | Most familiar | Slower, less TS-native than Fastify | no |
| Just use the existing `dashboard-api` | Zero new infra | Python serving a React SPA is fine but feels off, and you'd be coupling app updates to dashboard-api updates | runner-up |

**Why Fastify specifically:** Native TypeScript, excellent perf, plug-in ecosystem, Vite-friendly. ~300 lines of server code total for v1.

**Caveat:** If the questionnaire reveals you'd rather not add Node to the stack, we can fall back to the existing Python API. That's a real, valid choice. I'd just have to do more proxy work.

---

## D5. Database

**Recommendation: Reuse the existing Postgres `mining_guardian` DB. Add a few new tables under a new schema `app.*`.**

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Reuse existing Postgres + new `app` schema** | Zero new infra; transactions across miner data and app data | Tighter coupling | ✅ winner |
| Separate Postgres database | Hard isolation | Two DBs to back up, no cross-DB joins | no |
| SQLite for app | Simpler | You explicitly retired SQLite. Don't go backwards. | hard no |
| Redis for sessions | Fast | One more daemon for no real benefit at single-operator scale | no |

**New tables under `app.*`:**
- `app.users` (one row, the operator)
- `app.sessions` (auth tokens, expiry)
- `app.audit_log` (every approve/deny/settings change)
- `app.notifications_seen` (read/unread state per device)

All written via a new migration file `006_app_schema.sql` (next available slot — 002 is reserved for B-7 VPS migration).

---

## D6. Authentication — implementation

**Recommendation: bcrypt password + httpOnly cookie session, no JWT**

- **Password storage:** bcrypt with cost 12
- **Session:** random 256-bit token in `app.sessions`, set as `Secure; HttpOnly; SameSite=Lax` cookie
- **CSRF:** double-submit cookie pattern (cookie value mirrored in a custom header)
- **Rate limiting:** existing `flask-limiter` style, on `/api/auth/login` only — 5 attempts per IP per 15 min

**Why not JWT:** JWTs are overkill for one operator and one Mac Mini. Server-side sessions let us revoke instantly (logout = delete row). JWTs need a refresh-token dance for the same effect.

---

## D7. State management (frontend)

**Recommendation: TanStack Query (React Query) for server state, Zustand for client state. No Redux.**

- **Server state** (miners, alerts, settings from API) → **TanStack Query**. Caches, refetches, polling — exactly what we need.
- **Client state** (modal open, current selection, theme) → **Zustand**. ~1KB, no boilerplate.
- **Forms** → **React Hook Form + Zod**. Schema validation, no useState soup.

**Why not Redux:** Both old and new Redux are way too much ceremony for an app this size. State libraries should disappear into the background.

---

## D8. Real-time updates (alerts, miner status)

**Recommendation: Server-Sent Events (SSE). Polling fallback if SSE fails.**

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **SSE (one-way: server → client)** | Built into browsers; no library; simple | One-way only | ✅ winner — we don't need duplex |
| WebSockets | Full duplex | Overkill for "tell me when something changes"; trickier through Tailscale | no |
| Polling every 30s | Dead simple | Wasteful, slight delay | fallback only |

We push 4 event types: `alert.new`, `miner.status_changed`, `scan.completed`, `setting.changed`. Client renders or refetches the affected query.

---

## D9. Deployment / build

**Recommendation: A single shell script `scripts/app_build.sh` that runs `npm run build`, copies output to `/usr/local/var/mining-guardian/app-static/`, and reloads the launchd daemon `com.miningguardian.app`.**

- New launchd plist: `com.miningguardian.app.plist` (10th daemon)
- Listens on `:8443` (HTTPS, self-signed for v1)
- Static files served by Fastify directly
- App update flow (Q17 = B): button POSTs `/api/admin/update` → runs the script → reloads daemon

---

## D10. Testing

**Recommendation: Vitest + Playwright. No Jest.**

- **Vitest** for unit / component tests (Vite-native, fast)
- **Playwright** for end-to-end (login flow, approve/deny flow)
- **Same coverage standard as the Python backend:** every PR adds or updates tests for the change. No PR ships with red tests.

---

## D11. Logging / observability

**Recommendation: pino on the server, console-only on the client (with optional Sentry-equivalent later)**

- **Server logs** → pino → `/usr/local/var/log/mining-guardian/app.log` (rotated weekly)
- **Client errors** → fetch to `/api/log/error` → pino → same file, tagged
- **Sentry / Bugsnag** is rejected for v1 (cloud-only, telemetry leaves premises)
- Self-hosted error tracking (Glitchtip) is **post-v1** if you want it

---

## D12. Versioning & release

**Recommendation: Semver, tagged releases, one-line changelog per release.**

- App version separate from the backend version
- Tag format: `app-v0.1.0`, `app-v0.2.0`, etc.
- `docs/app/CHANGELOG.md` with one paragraph per release
- v1.0 ships when all questionnaire items are green and Phase 1 of the roadmap is complete

---

## D13. What we're NOT building (justified)

- **Server-side rendering / Next.js.** This is a single-operator internal tool. SEO doesn't matter. Initial load can be 200ms slower than Next would deliver — fine. Plain Vite SPA.
- **GraphQL.** REST is fine. We have ~12 endpoints in v1.
- **Microservices.** One Fastify server, one DB, one launchd plist. Stop adding moving parts.
- **Docker for the app.** The Mac Mini is the deploy target; running Docker for one Node process adds operational complexity for zero benefit. (Grafana already runs in Docker via Colima — that's fine, that's its native shape.)
- **Storybook.** Tempting, but you'll never look at it after week 3. Build the screen, ship the screen.

---

## Summary of the proposed stack

```
Frontend:    React 18 + Vite + TypeScript + Tailwind + shadcn/ui + Recharts
State:       TanStack Query + Zustand + React Hook Form + Zod
Backend:     Fastify + TypeScript (new) + Postgres (existing)
Auth:        bcrypt + httpOnly session cookie
Realtime:    Server-Sent Events
Test:        Vitest + Playwright
Build/run:   npm + a launchd plist on :8443
Domain:      mg-mini.tail-scale.ts.net (free, via Tailscale MagicDNS)
```

**Lines of new code estimate for v1:** ~3500 lines (frontend) + ~800 lines (server). Manageable.

---

## What I need from you on this file

Each numbered decision (D1–D13) — agree, disagree, or "I want to discuss." Easiest format:

```
D1: yes
D2: yes
D3: yes
D4: discuss — I don't want Node on the Mac Mini
D5: yes
... etc.
```

Or just "all yes" if everything looks good.

---

*Next: `04_BRAND_REFERENCE_CARD.md` — the one-pager I'll keep open while building.*
