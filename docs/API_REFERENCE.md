# Mining Guardian API Reference

**Status:** PLACEHOLDER — full reference doc to be expanded post-install (post 2026-04-30).
**Last touched:** 2026-04-29

This guide will document the live HTTP surfaces shipped on the Mac Mini install. Both APIs are loopback-only by default (`127.0.0.1`); remote operator access is via Tailscale to the Mini.

## Dashboard API (port 8585)
- `GET /status` — process / scan health
- `GET /metrics` — Prometheus exposition
- `GET /query/*` — read-only catalog query endpoints
- `POST /api/hvac/ingest` — HVAC sensor ingest
- `GET /api/hvac/latest` — latest HVAC readings

## Approval API (port 8686)
- `POST /approve` — approve a pending action
- `POST /deny` — deny a pending action
- `POST /approve_selected` — bulk approve
- `GET /pending` — list pending approvals
- `POST /slack/actions` — Slack interaction webhook

For the installer / packaging side, see `installer/macos-pkg/README.md`.
