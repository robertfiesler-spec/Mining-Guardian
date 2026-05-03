# v1.0.3 Discovery — 2026-05-04

```yaml
date:           2026-05-04
written_by:     Computer (autonomous agent), per HANDOFF_2026-05-04_NEW_CHAT.md Step 3
scope:          repo-source discovery only — no code changes, no host access
input_decisions: D-18 (v1.0.3 scope), D-19 (operator console), D-20 (importer is operator-only)
input_handoff:   docs/handoffs/HANDOFF_2026-05-04_NEW_CHAT.md
input_audit:     docs/audits/PKG_AUDIT_v1.0.2_FINDINGS_2026-05-03.md
last_main_sha:   9449fab
```

> Per D-18 implementation plan step 2 / PROGRAM_STATE.md Section 12 step 2, the
> first work in this v1.0.3 chat is discovery, NO code. This file is the
> output. It answers three questions and lists the reconciliation work the
> v1.0.3 PR train must do BEFORE the D-19 console implementation begins.

---

## 1. Where do pending approvals live today? Postgres, JSON, or Slack-only?

**Answer: Postgres. The canonical store is the `pending_approvals` table in the operational `mining_guardian` database. Slack is the surface, not the source of truth.**

### 1.1 Schema

`migrations/001_initial_schema.sql:126-144` defines the table:

```sql
CREATE TABLE IF NOT EXISTS pending_approvals (
    id               SERIAL PRIMARY KEY,
    created_at       TIMESTAMP WITH TIME ZONE NOT NULL,
    scan_id          INTEGER,
    thread_ts        TEXT NOT NULL,
    miner_id         TEXT NOT NULL,
    ip               TEXT NOT NULL,
    model            TEXT,
    action_type      TEXT NOT NULL,
    problem          TEXT,
    pdu_id           INTEGER,
    outlet           INTEGER,
    status           TEXT DEFAULT 'PENDING',
    responded_at     TEXT,
    confidence_score INTEGER,
    confidence_gate  TEXT
);

CREATE INDEX IF NOT EXISTS idx_pending_thread ON pending_approvals(thread_ts, status);
```

Status lifecycle observed in code: `PENDING` → `APPROVED` / `DENIED` / `EXPIRED`.

### 1.2 Producers (who INSERTs into `pending_approvals`)

| Path | Site | What it writes |
|---|---|---|
| `core/mining_guardian.py:2274` | `self.db.save_pending_approvals(thread_ts, scan_id, issues)` — per-scan main daemon | Inserts one row per flagged miner action when the scan loop posts the Slack approval thread. |
| `api/approval_api.py:429` | `INSERT INTO pending_approvals … VALUES (…, 'PENDING')` inside `/internal/urgent_action` (line 384) | Inserts an urgent action queued by the AMS alert listener (out-of-cycle, picked up either by the main loop or overnight automation). |

### 1.3 Consumers (who READs / UPDATEs)

| Path | Operation |
|---|---|
| `api/approval_api.py:174` (`/approve`) | `UPDATE … SET status='APPROVED'` plus `INSERT` into `action_audit_log`. |
| `api/approval_api.py:259` (`/deny`) | `UPDATE … SET status='DENIED'` plus `INSERT` into `action_audit_log`. |
| `api/approval_api.py:316,327,343` (`/approve_selected`) | Per-miner `APPROVED` / `DENIED` UPDATE for selective Block Kit approval. |
| `api/approval_api.py:509,619,624,657,725` | `/queue`, `/by-miner`, `/by-thread` read endpoints; `UPDATE` for retry / explicit action selection paths. |
| `api/slack_approval_listener.py:153` | Sweeps `status='PENDING'` rows older than the TTL and marks them `EXPIRED`. |
| `api/slack_approval_listener.py:178,195,247,412` | Reads thread state to honor Slack thread replies (APPROVE/DENY) and to look up miner identity. |
| `api/ai_dashboard_api.py:107` (`get_action_queue()`) | Reads the live list, joined to the latest `miner_readings` row, for the "Live Action Queue" panel. |
| `core/overnight_automation.py:163,328` | Reads `status='PENDING'` to apply overnight auto-approval (D-2 gated) and updates rows it actions to `APPROVED`. |
| `core/mining_guardian.py:1230,2225,2240` | Read for action-tracking; `expire_old_pending_approvals(60)` every loop; `UPDATE … responded_at` after Slack response. |

### 1.4 What this means for D-19

Approvals are **already** persistent state in Postgres. The D-19 console
does NOT need a new persistence layer. It can — and should — read and
mutate the same `pending_approvals` table the rest of the system already
uses. No new schema work is required for the queue itself.

> Cross-reference: `archive/tmp_scripts_apr08/mining_guardian_backup_$(date +%H%M).py`
> contains the historical SQLite-era equivalents (`save_pending_approvals`,
> `expire_old_pending_approvals`); these are archive-only and do not run.
> The live data plane is Postgres per the 2026-04-23 migration recorded
> in CLAUDE.md.

---

## 2. Grafana "Live Action Queue" panel — display-only or interactive?

**Answer: It is rendered as buttons, but the buttons are not functional from a customer browser today. The panel is an HTML iframe pointing at a server-rendered page; the Approve/Deny POSTs hit endpoints that are gated `verify_internal` (X-Internal-Secret) and reject browser-origin requests with HTTP 403.**

### 2.1 How the panel is wired

The panel at `grafana.fieslerfamily.com/d/llm_learning_001` is **not** a
native Grafana panel reading a Postgres datasource. It is a Grafana `text`
panel of `mode: html` containing an iframe:

`scripts/update_grafana_ai.py:20-31`:

```python
new_panels = [
    {
        "id": 20,
        "type": "text",
        "title": "",
        "gridPos": {"h": 28, "w": 24, "x": 0, "y": 0},
        "options": {
            "mode": "html",
            "content": '<iframe src="https://dashboard.fieslerfamily.com/ai/dashboard" '
                       'style="width:100%;height:100%;border:none;background:#0f172a" '
                       'frameborder="0"></iframe>',
        },
        "transparent": True,
    },
    …
]
```

`https://dashboard.fieslerfamily.com/ai/dashboard` is served by
`api/ai_dashboard_api.py`. That module:

- `api/ai_dashboard_api.py:101-114` — `get_action_queue()` SELECTs
  `pending_approvals` rows `WHERE status='PENDING'`.
- `api/ai_dashboard_api.py:267,288-289` — renders one HTML row per
  pending approval, each row containing two buttons:
  ```html
  <button onclick="approveAction('{qid}')" …>✓ Approve</button>
  <button onclick="denyAction('{qid}')"     …>✗ Deny</button>
  ```
- `api/ai_dashboard_api.py:477-480` — the JS handlers POST JSON to
  `https://slack.fieslerfamily.com/approve` and `/deny` (the public
  hostname for `api/approval_api.py`).
- `api/ai_dashboard_api.py:500-501` — section header and `<table>`
  rendering for the panel.
- `api/ai_dashboard_api.py:292` — empty-state message
  `"✓ No pending actions — system is running autonomously"` (the
  message the operator screenshotted recently — confirms queue empty,
  not that the panel is non-interactive).

### 2.2 Why the buttons are non-functional today

`api/approval_api.py:156,231,295,384` — every action endpoint applies
the same gate:

```python
@app.post("/approve")
async def approve_actions(request: Request):
    if not verify_internal(request):
        return Response(status_code=403, content="Forbidden")
    …
```

`api/approval_api.py:143-153`:

```python
def verify_internal(request: Request) -> bool:
    if not INTERNAL_API_SECRET:
        logger.warning("INTERNAL_API_SECRET not set — rejecting (fail closed)")
        return False
    provided = request.headers.get("X-Internal-Secret", "")
    return hmac.compare_digest(provided, INTERNAL_API_SECRET)
```

The dashboard's browser-side `fetch(...)` does not (and cannot, by
design — the secret would leak into the page) send the
`X-Internal-Secret` header. The endpoints exist because the
**Slack approval listener** (`api/slack_approval_listener.py`) is the
intended caller and has the secret server-side. Today the only
functional approve/deny path for an operator is replying to the Slack
approval thread itself; the dashboard buttons render but POST a 403.

Browser-confirmed live behavior was not part of this discovery (no host
access). The repo-source reading above is sufficient to ground D-19;
a separate live browser inspection on the running VPS may be performed
later if desired but does not change the conclusion.

### 2.3 What this means for D-19

D-19 locks the operator console as the customer-facing surface and
explicitly notes "the Grafana 'Live Action Queue' panel … displays the
same queue but its interactive Approve/Deny is unverified — discovery
task at start of v1.0.3 work confirms whether to extend the existing
flow or build new." The discovery answer:

- The existing dashboard panel is browser-rendered and the buttons exist
  but are non-functional from the browser due to the `verify_internal`
  fail-closed gate. **Extending the existing browser-side handlers is not
  the right move** — it would require either bypassing the
  `INTERNAL_API_SECRET` gate (security regression — the gate is the only
  thing keeping a stray HTTP caller from approving actions) or punching a
  separate browser-trusted auth layer in front of `approval_api.py`.
- **The right move for D-19 is the locked design:** build the console
  under `console/` as a FastAPI + Jinja2 + HTMX server-rendered app
  bound to `127.0.0.1:8686`, fronted by Cloudflare Tunnel + Cloudflare
  Access (email-based auth). The console SERVER calls into the
  `pending_approvals` table directly via psycopg, signs its own internal
  requests to `approval_api.py` with `INTERNAL_API_SECRET` (it lives on
  the same Mini and can read the `.env`), and renders an authenticated
  HTML page to the operator. No browser ever holds the secret.
- The Grafana panel's Approve/Deny buttons should either (a) be removed
  in v1.0.3 to avoid customer confusion (clicking does nothing
  user-visible), or (b) be re-pointed at the new console URL. **(a) is
  recommended for v1.0.3** to keep the console as the single
  customer-facing approval surface; (b) is a post-cutover follow-up
  if the operator wants Grafana to remain a viable second surface.

This finding does not change D-19 scope. It confirms the locked design
and rules out the cheaper "extend the browser handlers" path.

---

## 3. What does `mg_import_tool/` actually do, and is it bundled in the customer .pkg?

**Answer: `mg_import_tool/` is a 6,604-line Flask single-file web application for ingesting research data into the catalog Postgres. Per D-20 it is operator-only forever. Today, `installer/macos-pkg/scripts/build_pkg.sh` BUNDLES it into the customer .pkg payload (line 207) AND copies its migrations into `<payload>/migrations/` for postinstall to apply (lines 218–220). This is a D-20 violation that v1.0.3 must reconcile before build.**

### 3.1 What `mg_import_tool/` does

`mg_import_tool/README.md:1-13` — v3.3 importer:

> A single-file Python web application for importing research data into
> PostgreSQL. Drag-and-drop CSVs, SQL scripts, ZIP bundles, JSON arrays,
> Excel files, TSVs, and miner log archives (.tar/.tgz/.tar.gz/.rar)
> into the `knowledge` schema with auto-generated, dollar-quoted INSERT
> statements.

Files: `mg_import.py` (6,604 lines, Flask web app), `resolver.py`
(444 lines, two-tier model alias resolver), `patch_html.py`,
`launch_mg_import.bat`, `create_shortcut.ps1`, `tools/`,
`sql/migrations/`, `sql/seed/` (the 12,852-row Tier-1 alias seed +
1,494-row Tier-2 family seed, plus bootstrap migrations).

The README also documents post-import verification SQL
(`tools/verify_post_import.sql`) and pre-import rolling-state SQL
(`tools/verify_pre_import.sql`). It is operator tooling — there is no
customer-facing scenario where a customer Mini ingests research CSVs.

### 3.2 D-20 says: NOT bundled

`docs/DECISIONS.md:303-305`:

> **D-20 — Importer stays with operator forever (single-source-of-truth catalog model)**
>
> The hardware-catalog importer (`mg_import_tool/`) stays on the operator's
> workstation forever. It is NOT shipped to customers. The customer .pkg
> will not include `mg_import_tool/` in its payload (or if it does for
> code-coupling reasons, no LaunchDaemon or console UI surfaces it).

Implementation step 1: "v1.0.3 .pkg payload audit: confirm
`mg_import_tool/` is NOT bundled into the customer .pkg, OR if it is
(for shared-code reasons), no UI surfaces it."

### 3.3 What the build script does today

`installer/macos-pkg/scripts/build_pkg.sh:194-213` (step_4 payload assembly):

```bash
/usr/bin/rsync -a --delete \
    --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
    --exclude 'build' --exclude 'venv' --exclude '.venv' \
    --include 'pyproject.toml' \
    --include 'predictor.py' \
    --include 'requirements.txt' \
    --include 'core/***' \
    --include 'clients/***' \
    --include 'notifiers/***' \
    --include 'monitoring/***' \
    --include 'api/***' \
    --include 'ai/***' \
    --include 'intelligence-catalog/***' \
    --include 'mg_import_tool/***' \         # ← line 207: BUNDLED
    --include 'docs/***' \
    --include 'branding/***' \
    --include 'deploy/***' \
    --include 'migrations/***' \
    --exclude '*' \
    "${REPO_ROOT}/" "${app_root}/"
```

`build_pkg.sh:217-220`:

```bash
install -d -m 0755 "${PAYLOAD_DIR}/migrations"
/usr/bin/rsync -a \
    "${REPO_ROOT}/mg_import_tool/sql/migrations/" \
    "${PAYLOAD_DIR}/migrations/"
```

So `<payload>/mg_import_tool/**` ships AND `<payload>/migrations/`
contains a copy of `mg_import_tool/sql/migrations/*.sql` that
postinstall.sh applies on first boot.

### 3.4 Is any LaunchDaemon surfacing it?

No. `installer/macos-pkg/resources/launchd/` contains 8 plists (the 9th,
`com.miningguardian.feedback-loop-daemon`, ships from `deploy/` per
PROGRAM_STATE.md Section 5):

```
com.miningguardian.alerts.plist
com.miningguardian.approval-api.plist
com.miningguardian.dashboard-api.plist
com.miningguardian.intelligence-report.plist
com.miningguardian.overnight-automation.plist
com.miningguardian.scanner.plist
com.miningguardian.slack-commands.plist
com.miningguardian.slack-listener.plist
```

None of them references `mg_import_tool` (verified by
`grep -rn 'mg_import' installer/`). The audit
(`docs/audits/PKG_AUDIT_v1.0.2_FINDINGS_2026-05-03.md:332`) made the
same observation: payload bundles the code, but no service exposes it.

### 3.5 The migrations question — is the `<payload>/migrations/` copy required?

`mg_import_tool/sql/migrations/` contains the `field_log_*` /
`mg.import_runs` / Layer-2 resolver schema (per
`mg_import_tool/README.md:42-60`). These migrations create catalog
schema tables (`hardware.model_aliases`, `mg.model_family_aliases`,
`mg.unresolved_models`, partitioned `raw_json`, …) that the
**runtime** consumes via `intelligence-catalog/` even when the
importer is never run. The Layer-2 resolver tables are read by the
operational loop's catalog lookup path.

So: the **schema** these migrations create is needed at runtime, but
the **importer code** that writes those tables is not. v1.0.3 needs to
separate the two.

### 3.6 Reconciliation required for v1.0.3 (before build)

The cleanest reconciliation, in PR-train order:

| # | Change | Why |
|---|---|---|
| 1 | Drop `--include 'mg_import_tool/***'` from `build_pkg.sh` step 4a `rsync`. | Per D-20: importer code does not ship to customer Mini. |
| 2 | Move the resolver-and-field-log migrations the runtime needs out of `mg_import_tool/sql/migrations/` and into the canonical `migrations/` directory under their next free numeric prefix (e.g., `migrations/004_layer2_resolver.sql`, `migrations/005_field_log.sql`), retaining the original importer copies as the source of truth for the operator-side install of `mg_import_tool/`. | Make the runtime self-contained for migrations; don't rely on a path that won't ship. |
| 3 | Change `build_pkg.sh:217-223` so postinstall picks up migrations from `<payload>/migrations/` (the canonical repo path) only — drop the `mg_import_tool/sql/migrations/` rsync. | Removes the cross-directory dependency that ties the importer to the customer payload. |
| 4 | Add a `build_pkg.sh` post-assembly assertion: `find "$PAYLOAD_DIR" -name 'mg_import*' -print` returns empty, OR the build aborts with exit 43. | Belt-and-suspenders prevention of D-20 regression in future builds. |
| 5 | Add a smoke-test gate to D-18 verification: on the clean Mac VM, `find /Library/Application\ Support/MiningGuardian -name 'mg_import*'` returns empty. | Closes the loop end-to-end. |

Steps 1, 3, 4, 5 are pure delete / assertion work. Step 2 is the only
substantive change and is small (rename + numeric prefix; the SQL
content is unchanged because both copies must continue to be
idempotent under `IF NOT EXISTS`).

---

## 4. Reconciliation needed BEFORE D-19 console implementation

D-19 explicitly defers its discovery question 1 ("read existing
approval-queue code paths, determine where pending actions live") to
this document. This section enumerates the reconciliation work the
console PR depends on. None of these are blocking the console DESIGN
(D-19 is locked); they are all execution-detail dependencies that the
PR train must close in dependency order.

| # | Item | Status | Dependency |
|---|---|---|---|
| 1 | Console reads `pending_approvals` directly via psycopg, not via the public `approval_api.py` HTTP. | Confirmed feasible per §1.3 above. | None — table already exists. |
| 2 | Console writes `APPROVED` / `DENIED` by calling `approval_api.py` with `INTERNAL_API_SECRET` server-side, OR by issuing the same `UPDATE pending_approvals SET status=…` + `INSERT INTO action_audit_log` SQL the API does. | Recommendation: route through `approval_api.py` with the secret. Reuses the side-effect logic (executing the action, logging the audit row, refreshing the Slack thread). | Console code in `console/` must source `INTERNAL_API_SECRET` from the same `.env` the `approval-api` LaunchDaemon launcher wrapper sources. |
| 3 | Cloudflare Tunnel routes `mg.fieslerfamily.com` → `127.0.0.1:8686` (the console). | 🔴 Not yet implemented — D-19 step 5. | Cloudflare API token in operator's Desktop conf (per D-19 plan). |
| 4 | The Grafana "Live Action Queue" iframe Approve/Deny buttons should be removed in v1.0.3 (recommendation §2.3 above) so the console becomes the single customer-facing approval surface. | 🔴 Not yet decided — needs operator confirmation. | Edit `api/ai_dashboard_api.py:288-289` to render row state only (no buttons), and update the iframe page's empty-state to point operators at the console URL. |
| 5 | `mg_import_tool/` payload exclusion + migration relocation per §3.6. | 🔴 Not yet implemented. | Step 1 of the v1.0.3 PR train (no order dependency on the console PR — they can land in parallel). |
| 6 | `pending_approvals` is created by `migrations/001_initial_schema.sql`. The audit found postinstall.sh applies bootstrap + layer2 + c5_triggers but does NOT apply 001 (or 002, etc.). Confirm the `pending_approvals` table actually exists post-install before the console assumes it. | 🟡 v1.0.3 postinstall already needs venv + catalog seed work (Gap 5 + Gap 2 per D-18). Add: postinstall must apply ALL `migrations/NNN_*.sql` files in lexical order, not a hand-picked subset. | This is part of the existing v1.0.3 venv / catalog seed PR scope. |

Items 1, 2, 6 are inputs that determine console PR shape. Items 3, 5
are independent. Item 4 is the only one that needs an explicit
operator decision before the console PR lands; if deferred, the
console still works — the Grafana buttons just continue to silently
403, which is the status quo.

### Open question for operator (one, not three)

**Should v1.0.3 remove the Approve/Deny buttons from the
`api/ai_dashboard_api.py` Live Action Queue panel, leaving it as
display-only and pointing operators at the new console URL for
Approve/Deny?** Recommendation: yes. The buttons are non-functional
today, the console exists to be the single customer-facing approval
surface, and a non-functional button is worse than no button.

---

## 5. Questions answered by Rob in current chat

The new-chat operator (Rob) confirmed the following scope clarifications
at session start. Captured here so the v1.0.3 PR train and follow-up
sessions reason from the same scope:

- **Phone app is a separate project.** It is post-cutover work
  (PROGRAM_STATE.md Section 12 step 13) and is NOT part of v1.0.3.
  The console (D-19) is the bridge until the phone app ships; the
  console retires when the phone app ships.
- **Installer completion in this chat includes:** the customer-facing
  operator console (D-19), clean-VM validation per D-18 verification
  gate, the actual Mac Mini install, screenshots at every install
  boundary, the customer Setup Manual / Program Instructions PDFs and
  brochure (the customer-facing artifacts referenced in
  PROGRAM_STATE.md Section 4.6).
- **Decommission sequencing is unchanged from D-16 + D-18:** the
  Hostinger VPS decommission and the ROBS-PC `mining-guardian-db`
  Docker container shutdown happen ONLY AFTER the Mini is verified
  green per D-16 + D-18. Both hosts remain healthy and untouched
  until the Mini is green.
- **Doctrine carry-overs:** "stay local," "Bitcoin SHA-256 only,"
  "leave no data behind," "step by step," "late and perfect over
  early and wrong" — all still in force. No shortcuts.

---

## 6. Affected docs and decisions

| Touched | Why |
|---|---|
| **D-18** (v1.0.3 installer scope) | Confirms Gap 2 (catalog seed), Gap 5 (venv) and adds an audit-time assertion against `mg_import_tool/` in the payload (§3.6 step 4). Confirms postinstall must apply ALL `migrations/NNN_*.sql` not a subset (§4 item 6). |
| **D-19** (operator console) | Resolves D-19 step-1 discovery: pending approvals already live in Postgres (§1); the Grafana buttons are non-functional and should not be extended (§2). The locked design (FastAPI + Jinja2 + HTMX, 127.0.0.1:8686, Cloudflare-fronted) is correct. |
| **D-20** (importer is operator-only) | Identifies the live D-20 violation in `build_pkg.sh:207,218-220` and prescribes the exclusion + migration-relocation reconciliation (§3.6). |
| `docs/PROGRAM_STATE.md` Section 11 (in-flight) | This discovery moves from "🔴 QUEUED" to "🟢 done" in the next PROGRAM_STATE update (will be done in the same PR as the next session-end handoff, per Section 14 of PROGRAM_STATE.md). |
| `docs/audits/PKG_AUDIT_v1.0.2_FINDINGS_2026-05-03.md` line 332 | This discovery confirms the audit's flag and prescribes the fix path. |
| `docs/handoffs/HANDOFF_2026-05-04_NEW_CHAT.md` Step 3 | This file IS the deliverable named in Step 3. |

### Lint / doc-check result

This is a documentation-only PR. No code paths are touched. The
project's design-lint (`design-lint.sh`) applies to UI source files
(`.tsx`, `.jsx`, …) and is not relevant here. `grep -in "mg_import"
docs/DECISIONS.md` returns 7 hits — 2 in D-4, 2 in D-5, 1 in D-18, 2 in
D-20 — all consistent with this discovery's findings (no
contradictions).

---

End of `DISCOVERY_2026-05-04.md`.
