# DEPRECATED — Do Not Use

**Status:** This entire directory is dead code as of 2026-04-27.
**Audit:** See [`docs/CATALOG_ORPHAN_TABLES_2026-04-28.md`](../docs/CATALOG_ORPHAN_TABLES_2026-04-28.md).
**Final removal:** Scheduled for the Mon 2026-05-04 housekeeping PR (with confirmation).

## What this directory was

`intelligence/` was the original location of the Mining Intelligence Catalog when the architecture was:
- Catalog Postgres on **ROBS-PC** with Thunderbolt 4 SSD enclosure
- Container orchestrated by `docker-compose.yml` here
- OpenClaw subsystem (now removed in PR #7)
- Tuning sized for ROBS-PC's 32 GB RAM

## What replaced it

| Old path (deprecated) | New canonical path |
|---|---|
| `intelligence/README.md` | (architecture is now in `docs/VISION.md` + `intelligence-catalog/seed-data/README.md`) |
| `intelligence/database/intelligence_catalog_schema.sql` | `intelligence-catalog/seed-data/intelligence_catalog_schema.sql` |
| `intelligence/database/intelligence_catalog_schema_v2_additions.sql` | `intelligence-catalog/seed-data/intelligence_catalog_schema_v2_additions.sql` |
| `intelligence/database/intelligence_catalog_schema_v3_additions.sql` | `intelligence-catalog/seed-data/intelligence_catalog_schema_v3_additions.sql` |
| `intelligence/docker-compose.yml` | (Mac Mini uses native Postgres, not Docker) |
| `intelligence/postgres-tuning.conf` | (Mac Mini tuning lives in `installer/postgres.conf.template` — Thursday rewrite) |
| `intelligence/.env.example` | `installer/secrets.env.example` (Thursday rewrite) |

## Why this directory is dangerous

The `database/*.sql` files in this directory are the **unpatched originals** — they still contain the 7 latent bugs that PR #12 fixed in the canonical copies:

1. `knowledge.freshness_log.staleness_days` — STORED GENERATED column with `NOW()` (volatile) — would fail to create
2. `firmware.firmware_releases` — tsvector trigger with enum cast — would fail at INSERT time
3. `facility.cooling_solutions` — same enum-in-tsvector bug
4. `hardware.hashboards.chips_per_board` — NOT NULL but seed inserts NULL for Auradine AH3880
5. `hardware.model_aliases UNIQUE (alias_normalized)` — rejects legit aliases that normalize to the same string
6. `knowledge.raw_ingestion_log` — partition key not in PK
7. `hardware.manufacturers.brand` — missing UNIQUE that seed's `ON CONFLICT (brand)` requires

**If the Mac Mini installer (Thursday rewrite) accidentally points at `intelligence/database/` it will deploy a broken schema.** The path forward must be exactly one canonical answer to "where is the catalog schema": `intelligence-catalog/seed-data/`.

## What to do if you arrive here from a doc link

The doc you came from is stale. Open `docs/CATALOG_ORPHAN_TABLES_2026-04-28.md` for the current architecture and pointers.
