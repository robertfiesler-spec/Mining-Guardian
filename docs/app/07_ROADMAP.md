# 07 — Roadmap

The phased build plan from "Saturday morning" to v1.0 ship. **Estimates assume the questionnaire and tech decisions are signed off and the Mac Mini install is stable.**

---

## Cadence assumption

You said this weekend, then "tackling this starting this weekend." Translating that to honest hours:
- ~6 hours Saturday
- ~6 hours Sunday
- ~3-5 weeknight evenings × 1-2 hours each
- Repeat for ~4 weekends

**Total budget: ~30–40 hours over 4 weekends** to v1.0.

If pace slips, we slip — never ship rough. "Rather late and perfect" applies to the app the same way it applied to the install cascade.

---

## Phase 0 — Foundations (weekend 1)

**Goal:** Boring scaffolding that sets us up for fast feature work in Phase 1.

| # | Item | Time | Owner |
|---|---|---|---|
| 0.1 | Lock decisions: questionnaire + tech sign-off | 1h | You |
| 0.2 | Scaffold the project: `app/` directory, Vite + React + TS + Tailwind, prettier/eslint/tsconfig | 1h | Me |
| 0.3 | Install shadcn/ui, configure to space-black + bitcoin-orange theme | 1h | Me |
| 0.4 | Wire fonts (Chakra Petch, Space Grotesk, Inter, JetBrains Mono) | 30m | Me |
| 0.5 | Build `<AppShell>` + `<Header>` + `<Sidebar>` + mobile drawer; static (no data) | 2h | Me |
| 0.6 | Set up Fastify server skeleton on `:8443` (HTTPS self-signed), serve static, add `/api/health` | 1h | Me |
| 0.7 | New launchd plist `com.miningguardian.app` (10th daemon) — installed by `setup.sh` Phase 10 update | 30m | Me |
| 0.8 | Migration `006_app_schema.sql`: `app.users`, `app.sessions`, `app.audit_log`, `app.notifications_seen` | 30m | Me |
| 0.9 | Auth flow: bcrypt + httpOnly cookie + login page + middleware | 2h | Me |
| 0.10 | First end-to-end test: log in, see empty inbox, log out | 30m | Me |
| 0.11 | Tag `app-v0.1.0-foundations` | — | Me |

**Phase 0 done when:** You can navigate to `https://mg-mini.tail-scale.ts.net:8443`, log in with the password you chose, see the empty Inbox screen with the brand-correct layout, and log out cleanly. No real data yet — that's Phase 1.

---

## Phase 1 — Approve / deny end-to-end (weekend 2)

**Goal:** The highest-value flow, working in production.

| # | Item | Time | Owner |
|---|---|---|---|
| 1.1 | `<Inbox>` screen — list pending + recent alerts, real data from `/api/inbox` | 2h | Me |
| 1.2 | `<AlertDetail>` — full alert info + AI reasoning + 3 action buttons | 2h | Me |
| 1.3 | Approve / deny / customize flows wired to existing `approval_api:8686` | 2h | Me |
| 1.4 | SSE channel for alert status updates (alert.new, alert.updated) | 1.5h | Me |
| 1.5 | Status pill component with all 8 states + pulse animation (motion-aware) | 1h | Me |
| 1.6 | Deep link from Slack to `/inbox/{alertId}` (Slack post template change) | 1h | Me |
| 1.7 | Mobile pass: every alert flow tested on iPhone Safari + Android Chrome | 1h | You + me |
| 1.8 | Audit log entries on every approve/deny | 30m | Me |
| 1.9 | Vitest unit tests for AlertCard, status mappings; Playwright E2E for the approve flow | 2h | Me |
| 1.10 | Tag `app-v0.2.0-approvals` | — | Me |

**Phase 1 done when:** A real alert lands in Slack, you tap the link, log in (cookie was already set), approve from your phone in <10 seconds, and the miner status flips. End-to-end.

---

## Phase 2 — Fleet & schedule (weekend 3)

**Goal:** Replace SSH and Grafana for the day-to-day "what's running and when does it scan."

| # | Item | Time | Owner |
|---|---|---|---|
| 2.1 | `<Fleet>` table view with summary tiles, filters, sortable columns | 3h | Me |
| 2.2 | `<MinerDetail>` page with sparkline, temp triplet, alert history, action buttons | 3h | Me |
| 2.3 | `<Schedule>` editor — 24h timeline view, rule editor modal, dry-run preview | 3h | Me |
| 2.4 | Operator Mode tab (Full / Semi / Manual) wired to `system_settings` | 1h | Me |
| 2.5 | "Scan now" button → triggers immediate scan, status pill animates | 1h | Me |
| 2.6 | `react-window` virtualization on fleet table (for fleets ≥ 100) | 1h | Me |
| 2.7 | Tests: fleet sort/filter, schedule rule overlap detection, mode change | 2h | Me |
| 2.8 | Tag `app-v0.3.0-fleet-schedule` | — | Me |

**Phase 2 done when:** You haven't SSH'd into the Mac Mini for a week.

---

## Phase 3 — Reports & settings (weekend 4)

**Goal:** The flagship "are we making money" screen + the rest of settings.

| # | Item | Time | Owner |
|---|---|---|---|
| 3.1 | `<IntelligenceReport>` screen — hero number, AI summary, profitability breakdown | 3h | Me |
| 3.2 | Time range selector (today/yesterday/7d/30d) + report archive | 1.5h | Me |
| 3.3 | PDF download via `/api/reports/{id}/pdf` (brand-styled) | 2h | Me |
| 3.4 | Settings tabs: General, AMS, Slack, Alerts (threshold tuning), Backups, About | 3h | Me |
| 3.5 | "Test connection" buttons for AMS and Slack | 1h | Me |
| 3.6 | "Check for updates" button → `git pull && rebuild && reload daemon` | 1h | Me |
| 3.7 | Polish pass: loading/empty/error states on every screen, accessibility audit | 2h | Me |
| 3.8 | Final cross-browser pass: Safari, Firefox, Chrome, iPhone, iPad, Android | 2h | You + me |
| 3.9 | Documentation: user guide for the app, screenshot tour | 1h | Me |
| 3.10 | Tag `app-v1.0.0` 🎯 | — | Me |

**Phase 3 done when:** You can demo the full app to a friend in 5 minutes and they get it.

---

## Post-v1 backlog (in priority order, no commitments)

1. **PWA upgrade** — install to home screen, basic offline support (1 weekend)
2. **TOTP 2FA** — optional, off by default (1 evening)
3. **Custom alert rule builder** — beyond preset thresholds (2 weekends)
4. **Multi-operator support** — invitations, roles, audit log per user (2 weekends)
5. **Multi-site management** — one app, multiple Mac Minis (4 weekends; needs design rethink)
6. **Native mobile apps** — iOS first via Capacitor over the existing PWA (2 weekends if PWA done)
7. **Public marketing site** — separate project, separate domain (1 weekend)
8. **Self-hosted error tracking (Glitchtip)** — when client-side bugs become a thing
9. **Real-time graphs in-app** (replacing Grafana) — only if Grafana proves to be a friction point

---

## Risk register

| Risk | Mitigation |
|---|---|
| Mac Mini install fails / unstable → app build delayed | Phase 0 doesn't start until Mac Mini is stable for 24h |
| Tailscale doesn't suit the customer's network | Phase 0 includes a fallback test: app works on LAN via `https://mg-mac-mini.local:8443` |
| AMS API doesn't expose all the fleet data we need | Discovered before Phase 2; we ship what's available, add a "missing data" placeholder |
| AI summary in Intelligence Report is bad/wrong | Template-based fallback already specified in flows doc |
| SSE through Tailscale is flaky | Polling fallback (every 30s) is the documented backup |
| Scope creep ("can we add X to v1?") | All adds go to "Post-v1 backlog" by default; bumping to v1 requires explicit go-back-and-redo-the-roadmap |

---

## What "v1.0 ship" means

- All 5 user flows from doc 05 work end-to-end on phone, tablet, desktop
- All 17 screens from doc 06 are built, with all four states (loading/empty/error/offline)
- ≥ 80% test coverage on the new TS code; 100% pass; Playwright E2E for login + approve covers happy path
- Daemon `com.miningguardian.app` runs cleanly on the Mac Mini, restarts on crash, survives reboot
- Brand-system audit clean (no white backgrounds, ≤ 3 accents, voice rules followed)
- Audit log entries for every state-changing action
- "Check for updates" works
- Documentation: this folder + `docs/app/USER_GUIDE.md` (Phase 3.9)
- One tagged release: `app-v1.0.0`

---

## Definition of "weekend slipped"

If at the end of a weekend a phase isn't done, we don't compress the next phase to compensate. We push v1.0 by a weekend. **Rather late and perfect.**

If you find yourself building at 2am to "just finish the phase," stop. The Mining Guardian backend doesn't care if the app ships next Saturday or the one after.

---

*That's the plan. Read 02 (questionnaire) and 03 (tech decisions), reply, and we're off.*
