# Catalog schema & seed data — canonical install order

This folder is the **single source of truth** for the Mining Intelligence Catalog
PostgreSQL schema. Per N6 (consolidated 2026-04-27), there is exactly one
deploy script and one canonical install order.

## Files in this folder

| File | Purpose | Lines | Run order |
|---|---|---|---|
| `intelligence_catalog_schema.sql` | Base schema — extensions, 10 schemas, 63 tables, enums, functions | 4,430 | 1 |
| `intelligence_catalog_schema_v2_additions.sql` | Bobby's gap audit — PSU serials, repair shop tracking, 9 more tables | 886 | 2 |
| `intelligence_catalog_schema_v3_additions.sql` | Exhaustive gap audit — auto-discovery field registry, 14+ more tables | 1,256 | 3 |
| `deploy_schema.sql` | **Canonical entry point.** Runs files 1–3, then enum extensions, then seeds sources/contributors/manufacturers | 108 | run this |
| `seed_miner_models.sql` | 313 Bitcoin SHA-256 ASIC miner models (factory specs only) | 4,097 | run after |
| `all_bitcoin_sha256_miners.csv` | Source CSV the seed file was generated from (audit trail) | — | reference only |
| `compile_all_miners.py` | Generator that produced `seed_miner_models.sql` from the CSV | — | reference only |

## How to install (canonical order)

```bash
# Prereq: Postgres 16, database `mining_guardian` exists, role `guardian_admin` owns it
# Prereq: $MG_DB_PASSWORD set in env (D-1)

cd intelligence-catalog/seed-data

# Step 1 — schema + enum extensions + base reference rows
psql -U guardian_admin -d mining_guardian -f deploy_schema.sql

# Step 2 — 313 miner models
psql -U guardian_admin -d mining_guardian -f seed_miner_models.sql
```

Both steps are idempotent:

- `deploy_schema.sql` uses `CREATE ... IF NOT EXISTS`, `ON CONFLICT DO NOTHING`, and `ADD VALUE IF NOT EXISTS`.
- `seed_miner_models.sql` is wrapped in a `BEGIN; ... COMMIT;` transaction. Re-running while data is present needs the idempotency wrapper added in PR #13 (C4 seed runner).

## Why path-agnostic

`deploy_schema.sql` uses psql's `\ir` (include relative) directive to pull in
the three schema files. `\ir` resolves paths relative to the calling script's
own directory, so the same file works in three contexts without modification:

1. **Repo / Mac Mini install** — run from `intelligence-catalog/seed-data/`
   via the installer's `psql -f` invocation.
2. **Docker on dev box** — `deploy.ps1` copies all five files into the
   container's `/docker-entrypoint-initdb.d/` and runs `deploy_schema.sql`
   from there. `\ir` resolves to that same directory.
3. **Sandbox / one-off testing** — `cd intelligence-catalog/seed-data && psql -f deploy_schema.sql`.

Before N6, there were two `deploy_schema.sql` files in the repo — one with
`\i /sql/...` paths and one with `\i /docker-entrypoint-initdb.d/...` paths.
They had identical bodies otherwise. The duplicate is gone; `\ir` covers
both deploy contexts.

## Customer Mac Mini install (May 5)

The installer's catalog-deployment phase runs:

```
psql -U guardian_admin -d mining_guardian -f \
     intelligence-catalog/seed-data/deploy_schema.sql

scripts/seed_catalog.sh   # added in PR #13 (C4) — idempotent wrapper around seed_miner_models.sql
```

That's it. No path patching, no Docker-specific branches.

## When to edit which file

| Change | Edit | Why |
|---|---|---|
| New table in an existing schema | `intelligence_catalog_schema_v3_additions.sql` (or later v4 if v3 ships) | Keep the base file frozen for reproducibility |
| New manufacturer brand enum | `deploy_schema.sql` `ALTER TYPE ... ADD VALUE` block | One canonical location for enum extensions |
| New manufacturer reference row | `deploy_schema.sql` manufacturer INSERT block | Same place as the enum that names it |
| New seed miner model | Edit `all_bitcoin_sha256_miners.csv`, regenerate via `compile_all_miners.py` | Audit trail stays intact |
| Field-observed data (real-world hashrate, failure stories) | **Not here.** Operational tables (`market.war_stories`, `ops.failure_patterns`) are populated by the watchers and the C5 feedback loop, not by seed files. | Factory specs and field observations stay separate by design. |

## Schema layering at a glance

```
intelligence_catalog_schema.sql           ← base, 4,430 lines
        │
        ▼
intelligence_catalog_schema_v2_additions  ← Bobby's gap audit, 886 lines
        │
        ▼
intelligence_catalog_schema_v3_additions  ← exhaustive gap audit + auto-discovery, 1,256 lines
        │
        ▼
deploy_schema.sql                         ← runs the three above, adds enum extensions, seeds reference rows
        │
        ▼
seed_miner_models.sql                     ← 313 factory-spec miner rows
```

Total surface: ~10,777 lines of SQL, 86+ tables across 10 schemas.

---

*N6 consolidation done 2026-04-27. See `docs/SESSION_LOG_2026-04-27.md`.*
