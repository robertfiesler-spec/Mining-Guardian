"""
console/main.py — D-19 customer operator console (FastAPI + Jinja2 + HTMX)

Routes (all GET unless noted):
  GET   /                      → redirect to /tasks
  GET   /tasks                 → task registry view (the 11 + the 9 services)
  GET   /tasks/htmx            → HTMX partial: just the task table body
  POST  /tasks/{task_key}/pause     → bootout system/<label>; HTMX row swap
  POST  /tasks/{task_key}/resume    → bootstrap system <plist>; HTMX row swap
  POST  /tasks/{task_key}/schedule  → edit schedule via system_schedules
  GET   /automation            → automation switches (FULL_AUTO / SEMI_AUTO / MANUAL)
  POST  /automation/mode       → set automation_mode in system_settings
  GET   /approvals             → approval queue (pending_approvals)
  POST  /approvals/{id}/approve     → mark APPROVED
  POST  /approvals/{id}/deny        → mark DENIED
  POST  /approvals/{id}/snooze      → push wake time forward
  GET   /system                → read-only system state panel
  GET   /healthz               → liveness probe (always 200)

INTERNAL_API_SECRET note: the console performs every DB / launchctl /
api.system_settings call server-side. The browser only ever sees opaque
ids (e.g. an approval id, a task key). No secret material is rendered
into HTML or echoed in JSON responses.

Bind: 127.0.0.1:8787. (D-19 originally said 8686, but the existing
approval_api owns 8686. The plist binds to 8787 to avoid collision —
fully documented in docs/CONSOLE_OPERATIONS_GUIDE.md.)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from console.task_registry import TASK_REGISTRY, get_task, as_dicts as task_registry_dicts
from console import system_state, approvals, launchd_controls

logger = logging.getLogger("console")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")

_THIS_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = _THIS_DIR / "templates"
_STATIC_DIR = _THIS_DIR / "static"

# Customer Mini install root for plist resume path. Mirrors PLISTS_DEST in
# installer/macos-pkg/scripts/postinstall.sh.
PLISTS_DEST = os.environ.get("MG_PLISTS_DEST", "/Library/LaunchDaemons")

app = FastAPI(
    title="Mining Guardian Operator Console",
    version="1.0.3-d19-foundation",
    docs_url=None,           # OpenAPI docs intentionally disabled in v1
    redoc_url=None,
    openapi_url=None,
)

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


# ── small helpers ────────────────────────────────────────────────────────────

def _operator_id(request: Request) -> str:
    """Best-effort operator identity for audit. Cloudflare Access injects
    Cf-Access-Authenticated-User-Email; on the LAN/Tailscale path the
    header is absent and we fall back to 'console:local'."""
    email = request.headers.get("Cf-Access-Authenticated-User-Email")
    if email:
        return f"console:{email}"
    return "console:local"


def _task_row_context(task_key: str) -> Dict[str, Any]:
    """Build the per-row dict the table template expects. Keeps the row
    template DRY between the full-page render and the HTMX swap."""
    t = get_task(task_key)
    if t is None:
        raise HTTPException(status_code=404, detail=f"unknown task_key {task_key!r}")
    st = launchd_controls.status(t.plist_label)
    return {"task": t, "status": st}


# ── liveness ─────────────────────────────────────────────────────────────────

@app.get("/healthz")
def healthz() -> JSONResponse:
    return JSONResponse({"ok": True, "service": "mg-console"})


# ── root → tasks ─────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/tasks", status_code=302)


# ── tasks ────────────────────────────────────────────────────────────────────

@app.get("/tasks", response_class=HTMLResponse)
def tasks_index(request: Request) -> HTMLResponse:
    rows = []
    for t in TASK_REGISTRY:
        rows.append({"task": t, "status": launchd_controls.status(t.plist_label)})
    return templates.TemplateResponse(
        request, "tasks.html",
        {"rows": rows, "operator": _operator_id(request)},
    )


@app.get("/tasks/htmx", response_class=HTMLResponse)
def tasks_htmx(request: Request) -> HTMLResponse:
    rows = []
    for t in TASK_REGISTRY:
        rows.append({"task": t, "status": launchd_controls.status(t.plist_label)})
    return templates.TemplateResponse(
        request, "_task_rows.html", {"rows": rows},
    )


@app.post("/tasks/{task_key}/pause", response_class=HTMLResponse)
def tasks_pause(request: Request, task_key: str) -> HTMLResponse:
    ctx = _task_row_context(task_key)
    t = ctx["task"]
    if not t.pausable or t.plist_label is None:
        raise HTTPException(status_code=400, detail="task is not pausable")
    ok = launchd_controls.pause(t.plist_label)
    logger.info("pause %s by %s ok=%s", task_key, _operator_id(request), ok)
    ctx = _task_row_context(task_key)
    return templates.TemplateResponse(
        request, "_task_row.html",
        {**ctx, "flash": "paused" if ok else "pause failed"},
    )


@app.post("/tasks/{task_key}/resume", response_class=HTMLResponse)
def tasks_resume(request: Request, task_key: str) -> HTMLResponse:
    ctx = _task_row_context(task_key)
    t = ctx["task"]
    if t.plist_label is None:
        raise HTTPException(status_code=400, detail="task is not a launchd job")
    plist_path = os.path.join(PLISTS_DEST, f"{t.plist_label}.plist")
    ok = launchd_controls.resume(t.plist_label, plist_path)
    logger.info("resume %s by %s ok=%s", task_key, _operator_id(request), ok)
    ctx = _task_row_context(task_key)
    return templates.TemplateResponse(
        request, "_task_row.html",
        {**ctx, "flash": "resumed" if ok else "resume failed"},
    )


@app.post("/tasks/{task_key}/schedule", response_class=HTMLResponse)
async def tasks_schedule(request: Request, task_key: str) -> HTMLResponse:
    """Edit time-of-day or window schedule via the existing system_schedules
    table. Only supports the schedules that already exist there in v1.
    Future Gap 4 work will extend this to launchd plist rewrites for
    StartCalendarInterval-based scheduled jobs."""
    t = get_task(task_key)
    if t is None or not t.schedule_editable:
        raise HTTPException(status_code=400, detail="task schedule not editable")

    form = await request.form()
    payload = {
        "enabled": form.get("enabled", "1") == "1",
        "schedule_type": form.get("schedule_type"),
        "start_hour": _form_int(form.get("start_hour")),
        "start_minute": _form_int(form.get("start_minute")),
        "end_hour": _form_int(form.get("end_hour")),
        "end_minute": _form_int(form.get("end_minute")),
        "interval_seconds": _form_int(form.get("interval_seconds")),
        "days_of_week": form.get("days_of_week", "0,1,2,3,4,5,6"),
    }
    flash = "schedule saved"
    try:
        from api.system_schedules import update_schedule, DEFAULT_SCHEDULES
        if task_key in DEFAULT_SCHEDULES:
            update_schedule(task_key, payload, updated_by=_operator_id(request))
        else:
            # Gap 4 not landed yet — record the intent so it isn't lost.
            from api.system_settings import set_setting
            set_setting(
                f"console_pending_schedule:{task_key}",
                _to_json(payload),
                updated_by=_operator_id(request),
            )
            flash = "schedule queued (Gap 4 not yet wired)"
    except Exception as exc:  # noqa: BLE001 — surface to operator
        logger.warning("schedule edit %s failed: %s", task_key, exc)
        flash = f"error: {exc}"
    ctx = _task_row_context(task_key)
    return templates.TemplateResponse(
        request, "_task_row.html", {**ctx, "flash": flash},
    )


def _form_int(raw):
    if raw in (None, "", "None"):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _to_json(d: Dict[str, Any]) -> str:
    import json
    return json.dumps(d, default=str)


# ── automation ───────────────────────────────────────────────────────────────

@app.get("/automation", response_class=HTMLResponse)
def automation_index(request: Request) -> HTMLResponse:
    from api.system_settings import (
        get_setting, AUTOMATION_MODE_FULL_AUTO, ALLOWED_AUTOMATION_MODES,
    )
    mode = get_setting("automation_mode", default=AUTOMATION_MODE_FULL_AUTO) or AUTOMATION_MODE_FULL_AUTO
    if mode not in ALLOWED_AUTOMATION_MODES:
        mode = AUTOMATION_MODE_FULL_AUTO
    return templates.TemplateResponse(
        request, "automation.html",
        {"current_mode": mode,
         "allowed_modes": sorted(ALLOWED_AUTOMATION_MODES),
         "operator": _operator_id(request)},
    )


@app.post("/automation/mode", response_class=HTMLResponse)
async def automation_set_mode(request: Request) -> HTMLResponse:
    from api.system_settings import set_setting, ALLOWED_AUTOMATION_MODES
    form = await request.form()
    mode = form.get("mode")
    if mode not in ALLOWED_AUTOMATION_MODES:
        raise HTTPException(status_code=400, detail="invalid mode")
    ok = set_setting("automation_mode", mode, updated_by=_operator_id(request))
    if not ok:
        raise HTTPException(status_code=500, detail="failed to write setting")
    return templates.TemplateResponse(
        request, "_automation_pill.html",
        {"current_mode": mode},
    )


# ── approvals ────────────────────────────────────────────────────────────────

@app.get("/approvals", response_class=HTMLResponse)
def approvals_index(request: Request) -> HTMLResponse:
    rows = approvals.list_pending(limit=200)
    for r in rows:
        r["snoozed_until"] = approvals.snoozed_until(int(r["id"]))
    return templates.TemplateResponse(
        request, "approvals.html",
        {"rows": rows, "operator": _operator_id(request)},
    )


@app.post("/approvals/{approval_id}/approve")
def approvals_approve(request: Request, approval_id: int) -> JSONResponse:
    ok = approvals.approve(approval_id, operator=_operator_id(request))
    return JSONResponse({"ok": ok, "id": approval_id, "decision": "APPROVED"})


@app.post("/approvals/{approval_id}/deny")
def approvals_deny(request: Request, approval_id: int) -> JSONResponse:
    ok = approvals.deny(approval_id, operator=_operator_id(request))
    return JSONResponse({"ok": ok, "id": approval_id, "decision": "DENIED"})


@app.post("/approvals/{approval_id}/snooze")
async def approvals_snooze(request: Request, approval_id: int) -> JSONResponse:
    form = await request.form()
    minutes_raw = form.get("minutes", "30")
    try:
        minutes = int(minutes_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="minutes must be int")
    try:
        ok = approvals.snooze(approval_id, minutes=minutes, operator=_operator_id(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"ok": ok, "id": approval_id, "snoozed_minutes": minutes})


# ── system state ─────────────────────────────────────────────────────────────

@app.get("/system", response_class=HTMLResponse)
def system_index(request: Request) -> HTMLResponse:
    state = system_state.collect_system_state()
    return templates.TemplateResponse(
        request, "system.html",
        {"state": state, "operator": _operator_id(request)},
    )


# ── module entrypoint ────────────────────────────────────────────────────────

def main():
    """Console daemon entrypoint. Bind to 127.0.0.1:8787 only.

    The launchd launcher invokes this via `python -m console.main`, NOT
    via uvicorn directly, so we keep all bind config in code (no exposed
    --host flag that could accidentally bind 0.0.0.0)."""
    import uvicorn
    uvicorn.run(
        "console.main:app",
        host="127.0.0.1",
        port=int(os.environ.get("MG_CONSOLE_PORT", "8787")),
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
