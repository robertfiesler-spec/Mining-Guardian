# Alias seeds — Tier 1 + Tier 2

Reference-data seeds for the two-tier importer alias resolver in
`mg_import_tool/resolver.py`. Applied during install by
`installer/macos-pkg/scripts/postinstall.sh::step_apply_alias_seeds`
(P-018D). Both files are idempotent (`ON CONFLICT … DO NOTHING`); a
re-install is a no-op against an already-seeded DB.

| File | Target DB | Target table | Rows | Conflict key |
|---|---|---|---|---|
| `001_hardware_model_aliases_tier1.sql` | `mining_guardian_catalog` | `hardware.model_aliases` | 12,840 | `(miner_model_id, alias)` |
| `002_mg_family_aliases_tier2.sql` | `mining_guardian` (operational) | `mg.model_family_aliases` | 1,494 | `alias_normalized` |

Tier 1 holds 1:1 unique aliases (one `alias_normalized` → one
`miner_model_id`) and lives in the catalog DB because it FK-refers to
`hardware.miner_models(id)` which is only populated there.

Tier 2 holds ambiguous aliases that map to a list of candidate model
ids. The candidate list is then narrowed by hashrate at lookup time
(see `mg_import_tool/resolver.py::_tier2_lookup`). This table lives in
the operational DB — the resolver runs in the importer process, the
operational DB is where `mg.import_runs` and `mg.unresolved_models`
already live, and a 1,494-row reference table is cheap.

## D-20 placement

Originally these files lived at `mg_import_tool/sql/seed/`, but D-20
(locked 2026-05-03) requires the customer payload to contain ZERO
`mg_import*` paths — `build_pkg.sh::step 4h` hard-fails the build
otherwise. P-018D (2026-05-06) moved them here so postinstall can
apply them without violating D-20. The originals were a single file
each, under git history; a `git log --follow` traces back to the v3
seed generator output.

## Regenerating

Operator-side. Use the original generator (NOT shipped to customers).
Whatever script regenerates `db_catalog.tsv` should also re-emit these
two files. The Tier-1 file's `ON CONFLICT` clause MUST match the
schema's actual UNIQUE constraint (`(miner_model_id, alias)` per
N6 / 2026-04-27). A previous generator emitted
`ON CONFLICT (alias_normalized)` which hard-fails at apply because no
such constraint exists; P-018D patched all 12,840 rows. If the
generator is rerun, fix the template there.
