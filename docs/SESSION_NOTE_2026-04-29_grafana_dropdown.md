# Grafana Intelligence Report — Miner Dropdown Auto-Expand Fix

**Date:** 2026-04-29 (afternoon, follow-up to morning over-doc PR #59)
**Bug:** § 15.6.1 in `docs/MG_UNIFIED_TODO_LIST.md`
**Dashboard:** [https://grafana.fieslerfamily.com/d/intelligence_report_001/](https://grafana.fieslerfamily.com/d/intelligence_report_001/) (UID `intelligence_report_001`, "Mining Guardian — Intelligence Report")
**Status:** fix script written, awaits one operator command on the VPS to apply

---

## What we discovered while investigating

The morning study note assumed the dashboard JSON lived in the repo at `installer/grafana/dashboards/intelligence.json`. **It does not.** The actual situation:

1. **No Grafana dashboard JSON is checked into this repo at all.** Every dashboard lives inside the running Grafana instance on the VPS.
2. The seven known dashboards are managed via the Grafana HTTP API by ad-hoc Python scripts in `scripts/` (e.g. `update_grafana_ai.py`, `update_grafana_pool.py`, `check_grafana_board2.py`).
3. The branding script (`scripts/branding/grafana_brand_dashboards.py`) lists six core dashboards by UID; the Intelligence Report (`intelligence_report_001`) is the **seventh** dashboard, added later, not in that list.
4. Authentication: the existing scripts hard-code `admin:002300rf` and call `http://localhost:3000`. That works only from the VPS itself.

So the right shape of the fix is **a Python script that runs on the VPS**, mirroring the existing pattern. The dashboard backup → diff → apply loop is the safe way to do this.

## The script

`scripts/fix_intelligence_dropdown.py`

Three modes, gated by CLI flags so you can never accidentally apply:

| Mode      | Flag         | Effect                                                  |
| --------- | ------------ | ------------------------------------------------------- |
| INSPECT   | (no flags)   | Fetch, print all template vars + datasources, backup, exit |
| DRY-RUN   | `--dry-run`  | Same + print unified diff, exit                         |
| APPLY     | `--apply`    | Same + POST the new dashboard with `overwrite=true`     |

It auto-detects whether the dashboard's panels query Postgres or Prometheus and writes the right kind of variable accordingly (Postgres `SELECT DISTINCT` over `miner_readings` for the last 7 days, or Prometheus `label_values(mining_guardian_fleet_online, miner)`). Idempotent: re-running `--apply` on an already-fixed dashboard is a no-op.

The corrected variable will have:

- `type: "query"` (was `"custom"`)
- `refresh: 2` ("On Time Range Change" — re-queries on every dashboard load)
- `multi: true`, `includeAll: true` (so you can pick one, several, or All)
- `sort: 1` (alphabetical)

## Operator instructions

Three commands on the VPS, run in order. Each is read-only until the last.

```bash
cd ~/Documents/GitHub/Mining-Guardian
git pull --ff-only

# 1. Inspect — read-only, writes a backup to /tmp/intelligence_report_001-BACKUP-<ts>.json
python3 scripts/fix_intelligence_dropdown.py

# 2. Preview the change — read-only, shows a unified diff
python3 scripts/fix_intelligence_dropdown.py --dry-run

# 3. Apply
python3 scripts/fix_intelligence_dropdown.py --apply
```

After step 3, hard-refresh the Intelligence Report in your browser (`Cmd+Shift+R`) and the miner dropdown will show every miner in the database, automatically expanding when daily search runs add new ones.

If any step prints something unexpected, stop and send the output. The backup written in step 1 lets us restore the previous dashboard state with one POST if anything goes sideways.

## Auth env override (if the embedded creds ever rotate)

```bash
GRAFANA_API_KEY="<your-service-account-token>" python3 scripts/fix_intelligence_dropdown.py --apply
# or
GRAFANA_USER=admin GRAFANA_PASS="<password>" python3 scripts/fix_intelligence_dropdown.py --apply
```

`GRAFANA_URL` defaults to `http://localhost:3000`; override only if Grafana moves.

## Why this isn't a full provisioning fix

The study note recommended provisioning the dashboard into `installer/grafana/dashboards/intelligence.json` so the Mac Mini install gets the corrected version on first boot. Doing that **properly** requires:

1. Setting up Grafana provisioning (`provisioning/dashboards/*.yaml`) inside the installer.
2. Exporting all seven dashboards as JSON.
3. Wiring the install scripts to drop them into Grafana's data dir on first boot.

That is the right long-term move, but it's a half-day job — bigger than fixing today's bug. Putting it in Bucket 2 as its own line item.

## Bucket 2 line items added today

- § 15.6.1 — Grafana Intelligence Report miner-dropdown auto-expand (**this fix — about to ship**)
- § 15.6.2 — Provision all seven Grafana dashboards as code under `installer/grafana/dashboards/` so customer installs reproduce them on first boot (NEW, not in morning todo)
