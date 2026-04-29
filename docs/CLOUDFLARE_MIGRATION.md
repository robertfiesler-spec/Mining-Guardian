# Cloudflare Migration — Hard Deadline

## ⚠️ SUPERSEDED — Cloudflare path NOT taken

> The locked decision is Mac Mini local-first, loopback-only services. This document is preserved as a historical record of an evaluated-and-rejected alternative architecture. Do not implement; do not reference as canonical. See `MG_UNIFIED_TODO_LIST.md` and `ROADMAP_TO_MAC_MINI_2026-05-05.md`.

---

**Original deadline:** May 5-9, 2026 (Mac Mini arrival window) — superseded by 2026-04-30 install date

## Why this matters

`fieslerfamily.com` is Bobby's **personal family domain**, used right now ONLY
for R&D against the VPS while the local Mac Mini is in transit. It is not a
production asset and it is not part of any customer deployment.

When the Mac Mini arrives, every service that currently uses a Cloudflare
tunnel **must come off** and run from the local Mac Mini instead. There is no
public ingress in the production architecture — all inbound paths become
`localhost` on the Mac Mini, and only outbound internet (for AMS, the OpenClaw
Slack socket connection, and Slack outbound API calls) is required.

## What is on Cloudflare today

All three are systemd-managed Cloudflare tunnels on the VPS:

| Subdomain | Currently routes to | Production replacement |
|---|---|---|
| `dashboard.fieslerfamily.com` | VPS:8585 (Retool / dashboard_api) | `localhost:8585` on Mac Mini |
| `slack.fieslerfamily.com` | VPS:8686 (approval_api / Slack actions) | OpenClaw socket → `localhost:8686` on Mac Mini |
| `grafana.fieslerfamily.com` | VPS:3000 (Grafana) | `localhost:3000` on Mac Mini (operator-only access) |

## What this means for code that exists today

### Block Kit interactive buttons — architecture is wrong for production

`api/slack_actions_handler.py` was written to receive Slack interactive
payloads via a publicly-reachable URL. That works on the VPS via the
`slack.fieslerfamily.com` Cloudflare tunnel. **It does not work on a Mac Mini
behind a customer firewall** because Slack cannot POST inbound to a private IP.

**The correct production path:**

1. Block Kit messages are posted via `slack_sdk.WebClient.chat_postMessage`
   with `blocks=` (outbound only — works fine on Mac Mini).
2. When an operator clicks an Approve / Deny button, Slack tries to deliver
   the `block_actions` payload.
3. Because OpenClaw is connected to Slack via Socket Mode (an outbound
   websocket), Slack delivers the payload to OpenClaw's socket connection
   instead of trying to POST inbound.
4. **OpenClaw must catch the `block_actions` event and forward it to Mining
   Guardian's approval API at `http://localhost:8686/approve` or `/deny`.**
5. Mining Guardian processes the action exactly as it does today for plain
   text approvals — the only difference is the trigger source.

So the work that's needed before May 5 is:

- [ ] Add an OpenClaw handler for `block_actions` events that POSTs to the
      local approval API
- [ ] Update `api/slack_block_kit.py` action_id values to use a `mg_` prefix
      so OpenClaw can recognize Mining Guardian buttons and route them
- [ ] Delete or formally deprecate `api/slack_actions_handler.py` — its
      design assumes public ingress and won't work on a Mac Mini
- [ ] Update `deploy/` systemd units to remove the slack.fieslerfamily.com
      tunnel dependency

### Dashboard access on the Mac Mini

Retool currently iframes `dashboard.fieslerfamily.com/charts/*`. After
migration, the operator will access the dashboard directly from the Mac Mini's
local interface (or via Tailscale if remote access is needed for support).
No public URL.

### Grafana access on the Mac Mini

Grafana stays as an operator tool. After migration:
- Bound to localhost on the Mac Mini
- Reached via `http://localhost:3000` from the operator's screen
- Or via Tailscale if Bobby needs to view it remotely
- No public DNS, no Cloudflare

## Audit before May 5

Grep the entire repo for references to `fieslerfamily.com` and confirm every
hit is either:
1. Migrated to `localhost`, or
2. Migrated to a Tailscale IP for support-only access, or
3. Removed entirely

```bash
grep -rn 'fieslerfamily' . --include='*.py' --include='*.md' --include='*.json' --include='*.service'
```

No customer-facing code or documentation should reference
`fieslerfamily.com`. It is Bobby's personal R&D crutch and disappears at
production.

## Outbound-only internet requirements (these stay)

Production Mac Minis still need outbound internet for:
- **AMS API** (`api-staging.dev.bixbit.io` and the eventual production AMS host)
- **OpenClaw Slack Socket Mode** (outbound websocket to Slack)
- **Slack outbound API** (`slack.com` for `chat_postMessage` etc.)
- **NTP** (system clock)
- **Tailscale** (if used for support access)

Nothing else. No public DNS for the customer's mining network.
