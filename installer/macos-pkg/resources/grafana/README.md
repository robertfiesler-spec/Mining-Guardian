# Mining Guardian — Grafana provisioning bundle

**BiXBiT USA · Bucket 6d · §7.3 row 7g of `docs/MG_UNIFIED_TODO_LIST.md`**

This directory is the **source of truth** for the Mining Guardian Grafana
configuration on every customer Mac Mini. Anything not described here is
not provisioned. To add a dashboard or change a datasource, edit the files
in this directory, commit, and re-run `scripts/install_grafana_provisioning.sh`
(or rerun `scripts/setup.sh` Phase 11).

---

## Inventory

```
grafana/
├── README.md                                          (this file)
├── provisioning/
│   ├── datasources/
│   │   └── mining_guardian.yml                        (2 Postgres datasources)
│   └── dashboards/
│       └── mining_guardian.yml                        (file-based dashboard provider)
└── dashboards/
    ├── fleet_overview.json                            (uid: mg-fleet-overview)
    ├── scans_health.json                              (uid: mg-scans-health)
    └── miner_models_catalog.json                      (uid: mg-miner-models-catalog)
```

### Datasources (`provisioning/datasources/mining_guardian.yml`)

| UID | Name | DB |
|---|---|---|
| `mg_operational_pg` | Mining Guardian (operational) | `mining_guardian` |
| `mg_catalog_pg` | Mining Guardian Catalog | `mining_guardian_catalog` |

Both bind to `127.0.0.1:5432` (S-13 — never exposed off-host). Password is
read from the env var `GUARDIAN_PG_PASSWORD` which `setup.sh` Phase 11
exports from `.env` (`MG_DB_PASSWORD`). **Never hardcode the password
into this yaml.**

`editable: false` blocks GUI edits — the yaml is canonical. To rotate the
password: change `MG_DB_PASSWORD` in `.env`, then `brew services restart grafana`.

### Dashboard provider (`provisioning/dashboards/mining_guardian.yml`)

Watches `/usr/local/MiningGuardian/grafana/dashboards/*.json` every 30 s.
`allowUiUpdates: false` — operators may experiment in the browser, but the
JSON files are truth and overwrite UI changes on each tick. Permanent
changes must go through PR.

### Dashboards

| UID | Title | Datasource | Panels |
|---|---|---|---|
| `mg-fleet-overview` | Mining Guardian — Fleet Overview | operational | header + 4 KPI stats + 1 timeseries + 1 table (7) |
| `mg-scans-health` | Mining Guardian — Scans & Collection Health | operational | header + 4 KPI stats + 2 timeseries + 1 table (8) |
| `mg-miner-models-catalog` | Mining Guardian — Miner Models Catalog | catalog | header + 4 KPI stats + 2 barcharts + 1 table (8) |

All dashboards open inside the **`Mining Guardian`** folder (uid `mg`),
created automatically by the provider.

---

## Brand colors (consistent with installer welcome.html / conclusion.html)

| Role | Hex | Use |
|---|---|---|
| Navy panel header bg | `#0A1428` | text panel header strip |
| BTC orange accent | `#F7931A` | wordmark, alert thresholds |
| Electric blue accent | `#3DA9FC` | sub-headers, online series |
| Muted text | `#94a3b8` | subtitles |

Colors are inlined in the dashboard JSON `text.options.content` HTML and in
panel `fieldConfig.defaults.color.fixedColor`. No external CDN — fully
offline.

---

## How `setup.sh` consumes this bundle

`scripts/setup.sh` Phase 11 (`phase_11_grafana()`) does:

1. `brew services start grafana`
2. Determine `$GRAFANA_VAR` (`/opt/homebrew/var/lib/grafana` on Apple
   Silicon, `/usr/local/var/lib/grafana` on Intel).
3. Call `scripts/install_grafana_provisioning.sh
   --target=$GRAFANA_VAR
   --bundle=installer/macos-pkg/resources/grafana
   --runtime-dashboards=/usr/local/MiningGuardian/grafana/dashboards`
4. `brew services restart grafana`

The helper script copies datasource yaml + provider yaml into the Grafana
provisioning tree and copies the three dashboard JSONs into the runtime
dashboards directory referenced by the provider. **Idempotent** — re-running
overwrites with the latest committed version.

(Setup.sh PR #75 still has a placeholder Phase 11 noting "Bucket 6d will
overwrite". A follow-up PR will wire Phase 11 to call this helper script
once both PRs land.)

---

## How `restore_from_snapshot.sh` interacts with this bundle

`scripts/restore_from_snapshot.sh` (PR #76) restores **`grafana.db`** —
the operational SQLite DB that holds users, API keys, alert state, and
in-flight UI session data. It does **not** touch this provisioning bundle.

That separation is intentional:

- The bundle (this directory) is **declarative** — versioned in git,
  identical on every Mac.
- `grafana.db` is **operational** — per-host state, restored from VPS
  snapshot for migration scenarios.

When restore is followed by a `brew services restart grafana`, the
provider re-loads the JSON dashboards from this bundle on top of the
restored DB.

---

## Local development / testing

```bash
# Sandbox test — render dashboards locally without a running Mining Guardian
docker run -d --name mg-grafana-test -p 3000:3000 \
  -v "$(pwd)/installer/macos-pkg/resources/grafana/provisioning:/etc/grafana/provisioning:ro" \
  -v "$(pwd)/installer/macos-pkg/resources/grafana/dashboards:/var/lib/grafana/dashboards:ro" \
  -e GF_SECURITY_ADMIN_PASSWORD=test \
  -e GUARDIAN_PG_PASSWORD=ignored_for_render_only \
  grafana/grafana:11.0.0
open http://localhost:3000   # admin / test
```

Datasource queries will fail (no Postgres in the container), but dashboard
**layout, panel positioning, and HTML rendering** can be inspected. For a
full functional test, point a Grafana at a real `mining_guardian` Postgres
on `127.0.0.1:5432`.

---

## Adding a new dashboard

1. Create `dashboards/<slug>.json` in this directory.
2. Required top-level fields: `uid` (kebab-case, prefix `mg-`), `title`
   (prefix `Mining Guardian — `), `tags` includes `mining-guardian`,
   `schemaVersion: 39`, `version: 1`, `editable: false`.
3. Use `datasource: {type: postgres, uid: mg_operational_pg}` (or
   `mg_catalog_pg`).
4. Match the brand-color text panel header pattern (see `fleet_overview.json`).
5. Run `python3 -c "import json; json.load(open('dashboards/<slug>.json'))"`
   to validate.
6. Commit. Phase 11 (or `install_grafana_provisioning.sh`) picks it up
   on next run; live Grafana picks it up within 30 s of the file appearing
   under `/usr/local/MiningGuardian/grafana/dashboards/`.

---

## Removing a dashboard

Delete the file from `dashboards/` AND from
`/usr/local/MiningGuardian/grafana/dashboards/` on the Mac. Provider has
`disableDeletion: false` so it will purge on next tick. Commit the removal.

---

## Why not Prometheus?

`docs/GRAFANA_PROMETHEUS_PLAN.md` describes a future multi-site
Prometheus + Grafana architecture. Today (single Mac Mini, single site)
the simplest correct architecture is **Grafana → Postgres directly**,
which is what this bundle implements. When the multi-site Prometheus
foundation is built, datasource yaml gains a third entry and dashboards
that benefit from time-series math get rewritten — the bundle structure
does not change.

---

## Related PRs / runbooks

- PR #74 — Bucket 6a: macOS LaunchDaemon plists + launcher wrappers
- PR #75 — Bucket 6b: `scripts/setup.sh` v2 (15 phases)
- PR #76 — Bucket 6c: `scripts/restore_from_snapshot.sh`
- **THIS PR** — Bucket 6d: Grafana provisioning bundle
- PR #68 — Bucket 3.2: `hardware.*` catalog schema deploy runbook (powers
  `mg_catalog_pg` datasource)

`docs/MG_UNIFIED_TODO_LIST.md` §7.3 row 7g is flipped to ✅ DONE in the
same commit that ships this bundle.
