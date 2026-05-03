"""
console/ — Mining Guardian Customer Operator Console (D-19, P-006)

The 10th LaunchDaemon. Server-rendered FastAPI + Jinja2 + HTMX. Binds to
127.0.0.1 only; never exposed publicly. Cloudflare Tunnel + Access fronts
it for customer-facing access; Tailscale serves the operator/dev path.

Per D-19, the console is explicitly TEMPORARY scaffolding — once the
phone-app project ships, the console retires. Keep the surface small.

Port allocation note: D-19 originally requested 8686, but that port is
owned by api/approval_api.py (the Slack approval webhook + existing
/ui Web GUI). The console binds to 8787 to avoid collision. See
docs/CONSOLE_OPERATIONS_GUIDE.md for the full port table.

This module is intentionally read-mostly in v1; write paths flow through
existing api/system_settings.py and api/system_schedules.py helpers, plus
direct Postgres updates against pending_approvals for the approval queue.
INTERNAL_API_SECRET is never sent to the browser — all DB/API operations
are server-side, and the console reuses the env-loaded secret only for
its own outbound calls (none in v1, but reserved for future).
"""

__all__ = ["app"]

# Lazy import so `python -c 'import console'` doesn't pull FastAPI on a
# host that hasn't installed it yet (e.g., during installer payload
# validation).
def __getattr__(name: str):
    if name == "app":
        from console.main import app as _app
        return _app
    raise AttributeError(name)
