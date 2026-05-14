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
│   │   └── mining_guardian.yml                        (4 datasources)
│   └── dashboards/
│       └── mining_guardian.yml                        (file-based dashboard provider)
└── dashboards/
    ├── fleet_overview.json                            (uid: mg-fleet-overview)
    ├── scans_health.json                              (uid: mg-scans-health)
    ├── miner_models_catalog.json                      (uid: mg-miner-models-catalog)
    ├── intelligence_catalog_live_queries.json         (uid: cfj6drj3pbk74b) — W26a
    └── reference-mini/                                (Mini-specific reference snapshots — NOT customer-deployable; see below)
        ├── mining_guardian_ai_learning.json
        ├── mining_guardian_board_health.json
        ├── mining_guardian_fleet_overview.json
        ├── mining_guardian_intelligence_report.json
        ├── mining_guardian_main.json
        ├── mining_guardian_mobile.json
        ├── mining_guardian_per_miner.json
        └── mining_guardian_pool_stats.json
```

### Datasources (`provisioning/datasources/mining_guardian.yml`)

| UID | Name | Type | URL | DB |
|---|---|---|---|---|
| `mg_operational_pg` | Mining Guardian (operational) | postgres | `127.0.0.1:5432` | `mining_guardian` |
| `mg_catalog_pg` | Mining Guardian Catalog (legacy uid) | postgres | `127.0.0.1:5433` | `mining_guardian_catalog` |
| `efi3m84mbf668b` | Prometheus (Mining Guardian) | prometheus | `127.0.0.1:9090` | — |
| `ffj6dpxcsts74d` | Mining Guardian Catalog (vps uid) | postgres | `127.0.0.1:5433` | `mining_guardian_catalog` |

The two catalog datasources (`mg_catalog_pg`, `ffj6dpxcsts74d`) point at the
**same** catalog DB on port 5433 — both UIDs are kept so dashboards carrying
either reference still resolve (the `ffj6dpxcsts74d` UID came in with the
VPS-restored dashboards). Operational Postgres is on 5432, catalog Postgres
on 5433 (W14 two-instance split, 2026-05-13). All Postgres datasources bind
to `127.0.0.1` only (S-13 — never exposed off-host). Password is
read from the env var `GUARDIAN_PG_PASSWORD` which `setup.sh` Phase 11
exports from `.env` (`MG_DB_PASSWORD`). **Never hardcode the password
into this yaml.**

`editable: false` blocks GUI edits — the yaml is canonical. To rotate the
password: change `MG_DB_PASSWORD` in `.env`, then `brew services restart grafana`.

### Dashboard provider (`provisioning/dashboards/mining_guardian.yml`)

Watches `/Library/Application Support/MiningGuardian/grafana/dashboards/*.json` every 30 s.
`allowUiUpdates: false` — operators may experiment in the browser, but the
JSON files are truth and overwrite UI changes on each tick. Permanent
changes must go through PR.

### Dashboards

| UID | Title | Datasource | Panels |
|---|---|---|---|
| `mg-fleet-overview` | Mining Guardian — Fleet Overview | operational | header + 4 KPI stats + 1 timeseries + 1 table (7) |
| `mg-scans-health` | Mining Guardian — Scans & Collection Health | operational | header + 4 KPI stats + 2 timeseries + 1 table (8) |
| `mg-miner-models-catalog` | Mining Guardian — Miner Models Catalog | catalog | header + 4 KPI stats + 2 barcharts + 1 table (8) |
| `cfj6drj3pbk74b` | 🧠 Intelligence Catalog — Live Queries | catalog | 5 — added W26a (PR #211) |

All four dashboards open inside the **`Mining Guardian`** folder (uid `mg`),
created automatically by the provider.

The eight `mining_guardian_*.json` dashboards under `dashboards/reference-mini/`
are **not** in this table — they are Mini-specific reference snapshots, not
customer-deployable, and the provider does not autoload them. See the
**Reference dashboards (`dashboards/reference-mini/`)** section below.

### Reference dashboards (`dashboards/reference-mini/`)

`dashboards/reference-mini/` holds reference snapshots of the eight
dashboards that run on the developer Mac Mini at `100.69.66.32`. They were
restored from the old VPS tarball during the W25/W26a Grafana work and,
until W26b, lived **only** on the Mini's filesystem. They are mirrored into
the repo for two reasons:

1. **Durability.** The repo is the disaster-recovery source of truth; the
   Mini is a deployment target. A Mini disk failure must not lose them.
2. **Installer parity / future templating.** Keeping them in-repo makes the
   eventual IP-templating work (see below) tractable and reviewable.

**These eight dashboards are NOT customer-deployable as-shipped.** Five of
the eight contain hardcoded references to `100.69.66.32` — the developer
Mini's specific Tailscale IP — in iframe-panel URLs and other panel content:

| File | `100.69.66.32` sites |
|---|---|
| `mining_guardian_ai_learning.json` | 2 |
| `mining_guardian_board_health.json` | 1 |
| `mining_guardian_fleet_overview.json` | 1 |
| `mining_guardian_intelligence_report.json` | 1 |
| `mining_guardian_per_miner.json` | 1 |
| `mining_guardian_main.json` | 0 |
| `mining_guardian_mobile.json` | 0 |
| `mining_guardian_pool_stats.json` | 0 |

A customer running the `.pkg` and getting one of the five IP-bearing
dashboards would see broken iframes pointing at a host that does not exist
on their network. So `reference-mini/` is a clearly-labeled holding area,
**not** part of the customer-deployable set.

**The provider does not autoload `reference-mini/`.** The customer install
path is `scripts/install_grafana_provisioning.sh`, whose dashboard copy step
globs `"$BUNDLE/dashboards"/*.json` — the **top level only**, non-recursive.
`reference-mini/` is a subdirectory, so its JSONs are never copied into the
runtime dashboards path (`/Library/Application Support/MiningGuardian/grafana/dashboards/`)
that the provider watches. The provider only ever sees the four
customer-deployable dashboards at the top of `dashboards/`. No provider-yaml
exclude rule is needed — the top-level-only glob already enforces the
boundary. (If that glob is ever changed to recurse, `reference-mini/` would
need an explicit exclude — a `tests/test_w26b_installer_dashboard_set.py`
cohort guard asserts the customer-deployable set stays IP-free.)

**Why ship them as-is instead of templating the IPs now?** Templating
`100.69.66.32` → a per-install configurable host is real work — it needs a
substitution mechanism and runtime config injection — and was deliberately
deferred to a future W-item rather than rushed into W26b. Until then the
honest move is to preserve the dashboards verbatim in a folder whose name
documents exactly what they are.

**Do not edit the files in `reference-mini/`.** They are byte-for-byte
snapshots of what the Mini runs; the cohort guard test verifies they parse
and are schema-current, but their content is intentionally a faithful
mirror, not a maintained customer artifact.

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
   --runtime-dashboards=/Library/Application Support/MiningGuardian/grafana/dashboards`
4. `brew services restart grafana`

The helper script copies datasource yaml + provider yaml into the Grafana
provisioning tree and copies the top-level dashboard JSONs (the four
customer-deployable dashboards — its glob is `dashboards/*.json`,
non-recursive, so `dashboards/reference-mini/` is **not** copied) into the
runtime dashboards directory referenced by the provider. **Idempotent** —
re-running overwrites with the latest committed version.

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
   under `/Library/Application Support/MiningGuardian/grafana/dashboards/`.

---

## Removing a dashboard

Delete the file from `dashboards/` AND from
`/Library/Application Support/MiningGuardian/grafana/dashboards/` on the Mac. Provider has
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
