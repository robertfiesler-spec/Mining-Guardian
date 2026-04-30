# 06 — Information Architecture

The complete sitemap, navigation, and screen inventory for v1.

---

## Sitemap (every screen)

```
/login                              Login screen (only screen reachable while signed out)
│
├── /                              → redirects to /inbox if logged in
│
├── /inbox                          Alert inbox (default landing, badge count in nav)
│   └── /inbox/{alertId}            Alert detail (modal-style on desktop, full-screen on mobile)
│       ├── /inbox/{alertId}/customize  Customize action sheet (sub-sheet on alert detail)
│       └── /inbox/history          Resolved/dismissed alerts (last 30 days)
│
├── /fleet                          Fleet table view
│   └── /fleet/{minerId}            Single miner detail
│       └── /fleet/{minerId}/alerts Last 30 days of alerts for this miner
│
├── /reports                        Intelligence Report (latest)
│   ├── /reports/{date}             A specific report by date
│   └── /reports/archive            All historical reports (paginated)
│
├── /settings                       Settings (default tab: General)
│   ├── /settings/general           Operator profile, app version, time zone
│   ├── /settings/ams               AMS credentials, site location
│   ├── /settings/slack             Slack tokens, channels
│   ├── /settings/alerts            Threshold tuning (temp °C, hashrate %, etc.)
│   ├── /settings/mode              Full / Semi / Manual mode selector
│   ├── /settings/schedule          Schedule editor (24h timeline view)
│   ├── /settings/backups           Backup status, manual backup trigger
│   └── /settings/about             Version, dependencies, license, "Check for updates" button
│
└── /404                            Not found (silver-badge illustration)
```

**Total v1 screen count: 17** (counting tabs as separate screens).

---

## Top-level navigation

A persistent left sidebar on desktop, bottom tab bar on mobile.

| Order | Icon | Label | Route | Notes |
|---|---|---|---|---|
| 1 | inbox-icon | **Inbox** | `/inbox` | Badge count = unread alerts |
| 2 | grid-icon | **Fleet** | `/fleet` | |
| 3 | chart-icon | **Reports** | `/reports` | |
| 4 | gear-icon | **Settings** | `/settings` | |

**Header (always visible, top of viewport):**

```
┌─────────────────────────────────────────────────────────────┐
│ [MG WORDMARK]   ● Scanner: Alive · Last scan 2m ago    [👤] │
└─────────────────────────────────────────────────────────────┘
```

- Wordmark — links to `/inbox`
- Status pill — daemon health; click expands to "all 9 daemons" panel
- Avatar (silver circle with operator's initials) — click opens menu: Settings, Logout

**Mobile header (collapsed):**

```
┌────────────────────────────┐
│ ☰  MG  ● ALIVE         👤  │
└────────────────────────────┘
```

Hamburger opens a drawer with the same nav items.

---

## URL conventions

- All API routes under `/api/*` (separated from app routes)
- All app routes are SPA — handled by React Router
- IDs in URLs are short slugs where possible (`/fleet/s21-pro-014`) instead of UUIDs (avoids ugly URLs)
- Query params for filters: `/fleet?status=warn&rack=B`

---

## Component inventory (v1)

These are the components we'll build. Each has a Storybook entry — wait, scratch that, no Storybook (per Tech Decisions D13). Each has a unit test.

### Layout
- `<AppShell>` — header + sidebar + main + footer
- `<Sidebar>` — desktop nav
- `<MobileTabBar>` — bottom nav on mobile
- `<MobileDrawer>` — slide-in drawer for nav
- `<Header>` — top bar with logo + status + avatar
- `<PageHeader>` — title + breadcrumb + actions

### Primitives (mostly from shadcn/ui, Tailwind-themed)
- `<Button>` — primary/secondary/destructive/ghost variants
- `<Input>` — text, password, number
- `<Select>`, `<MultiSelect>` — dropdowns
- `<Toggle>`, `<Checkbox>`, `<Radio>` — state toggles
- `<Slider>` — for throttle %, duration, etc.
- `<Modal>`, `<Sheet>`, `<Drawer>` — overlays
- `<Toast>` — bottom-right notifications
- `<Banner>` — top-of-page persistent notices
- `<Tabs>` — settings tabs, etc.
- `<DropdownMenu>` — avatar menu, row actions
- `<Tooltip>` — explanatory hovers
- `<Skeleton>` — loading placeholders

### Domain components (Mining Guardian-specific)
- `<StatusPill status="alive|warn|offline|stale|learning|applying|resolved|dismissed">`
- `<MinerStatusCard>` — used on fleet table row
- `<AlertCard>` — used in inbox + on alert detail
- `<HashRateValue value="24.7" unit="PH/s">` — orange tabular nums
- `<TempValue value="87" threshold="85">` — color-coded
- `<TimeAgo timestamp={iso}>` — "2 min ago", auto-updates
- `<Sparkline data={[...]}>` — tiny chart for fleet rows
- `<ScheduleTimeline rules={[...]}>` — 24h horizontal bar
- `<ProfitabilityBar revenue={} cost={} net={}>`

### Charts (Recharts wrappers, Mining Guardian-themed)
- `<LineTrend>` — used on miner detail, report
- `<BarBreakdown>` — used on report
- `<AreaSpark>` — for fleet summary tiles

---

## Data fetching patterns

| Where | Pattern | Refresh |
|---|---|---|
| Inbox | `useQuery(['inbox'])` + SSE for new alerts | Real-time via SSE |
| Fleet table | `useQuery(['fleet', filters])` + SSE for status changes | Real-time via SSE; manual refetch on "Scan now" |
| Miner detail | `useQuery(['miner', id])` + SSE | Real-time |
| Reports | `useQuery(['reports', range])` | Refetch on time range change |
| Settings | `useQuery(['settings', namespace])` | On-demand, mutations refresh |
| Schedule | `useQuery(['schedule'])` | Refetch on save |

**SSE channels and what they publish:**

```
alert.new           { alertId, minerId, severity }
alert.updated       { alertId, status }       # approved/denied/applying/resolved
miner.status        { minerId, status }       # alive→warn→offline transitions
scan.started        { scanId }
scan.completed      { scanId, summary }
setting.changed     { namespace }              # any tab refetches
daemon.heartbeat    { name, status }           # for the header status pill
```

Frontend listens to SSE in a single `useSSE()` hook, dispatches React Query `queryClient.invalidateQueries()` based on event type. Clean and minimal.

---

## Loading, empty, and error states (every screen needs all three)

For each screen, we explicitly design:

| State | What's shown | Notes |
|---|---|---|
| **Loading** | `<Skeleton>` placeholders shaped like the real UI | Never spinners. Skeletons feel faster. |
| **Empty** | Silver-badge illustration + 1-line copy + 1 CTA | E.g. fleet empty: "No miners yet. Add credentials in Settings → AMS." |
| **Error** | Red-bordered card with short copy + "Retry" link | Never raw stack traces. |
| **Offline** | Top banner: "Offline — last data X min ago" | Stays until reconnect |

---

## Accessibility floor (non-negotiable)

- All interactive elements reachable by keyboard (Tab order matches visual order)
- Focus visible at 2px orange outline
- Color contrast: body 4.5:1, large text 3:1, status pills 4.5:1 against their background
- All images have alt text or `aria-hidden` if decorative
- All icons that are also buttons have `aria-label`
- Live regions (`aria-live="polite"`) for new alert toasts
- Honor `prefers-reduced-motion`
- Honor `prefers-color-scheme: dark` (we're dark anyway, just don't fight it)
- Form errors announced via `aria-invalid` + `aria-describedby`

---

## Deep-link patterns (for Slack → app handoff)

When Slack posts an alert, the message includes a button labeled "Open in Mining Guardian" linking to:

```
https://mg-mini.tail-scale.ts.net:8443/inbox/{alertId}
```

If the operator isn't logged in, they hit `/login?redirect=/inbox/{alertId}` and bounce back after auth.

This is the bridge between Slack-as-notification and app-as-action.

---

## Browser support

- **Chrome 110+, Safari 16+, Firefox 110+, Edge 110+** — all evergreen
- **iOS Safari 16+** — for phone use
- **Android Chrome 110+** — for phone use
- **No IE, no legacy Edge** (zero practical users on those)

---

*Next: `07_ROADMAP.md` — phases, milestones, what ships when.*
