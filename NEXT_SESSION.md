# Next Session Notes — Mining Guardian

**Last Updated:** 2026-04-22 18:30 CDT

---

## Tomorrow's Plan (in order)

### 1. Deploy v3.3 Import Tool
Follow `TOMORROW_DEPLOY_STEPS.md` (shipped with the v3.3 zip; also copied into repo at
`mg_import_tool/`).

- Stop any running v3.1 instance
- Drop in v3.3 tree
- Verify Flask starts on `:5050`
- Hit `GET /api/resolver-summary` — expect Tier-1=12,852, Tier-2=1,494, unresolved=0

### 2. 83-Archive Mass Import
Use the **SSE streaming endpoint** `POST /api/import-files-stream` — gives live per-archive
progress, per-archive error isolation, and sha256 dedup.

Watchpoints during the run:
- `archive_skipped` events → sha256 dedup hits (expected for the earlier Antminer_S19
  test archive)
- `archive_failed` events → per-archive errors land in `mg.import_runs` but batch continues
- `resolver_stats_updated` events → watch Tier-1 / Tier-2 / unresolved counts evolve

After the batch: `GET /api/resolver-summary` should show **≥95% coverage**. Any misses
live in `mg.unresolved_models` — peek with `GET /api/unresolved-sample?limit=50`.

### 3. SQLite → Postgres Phase 2 Migration
Phase 1 (today) split the monolith into `operational.db`, `timeseries.db`,
`ai_knowledge.db`, `audit.db`. Phase 2 moves them all into Postgres.

Open decisions to make together:
- One Postgres DB with schemas (`operational.*`, `timeseries.*`, etc.) or separate DBs?
- TimescaleDB hypertables for `miner_readings` / `chip_readings` / `log_metrics`?
  (5.4 GB and growing — hypertables would pay off)
- Retention policies: how long does `audit.db` data live? `log_metrics`?
- Connection-pool wiring — `core/database_router.py` gets rewritten to psycopg pool pattern

Keep the router pattern. Just swap drivers + update `TABLE_ROUTING` to point at Postgres
schemas/DBs.

### 4. Layer 2 Coverage Audit
After 83-archive batch:
- `mg.unresolved_models` manual triage — add to Tier 1 or Tier 2 as appropriate
- Any new raw strings that should feed back into the seed SQL
- Refresh seed SQL so a clean re-seed stays idempotent

---

## What Shipped Today (2026-04-22)

### Field Intelligence Pipeline — Layer 2 LIVE
- Two-tier resolver (Tier-1 exact + Tier-2 hashrate-disambiguated families)
- **12,852** Tier-1 aliases in `hardware.model_aliases`
- **1,494** Tier-2 family aliases in `mg.model_family_aliases`
- 317 SHA-256 models in `hardware.miner_models`
- First real archive: 14,178 rows persisted in 0.45s (Antminer_S19_2024-06-27_2024-06-29)

### Import Tool v3.3
- SSE streaming endpoint with per-archive error isolation
- sha256 dedup, cancel-batch, resolver-summary, unresolved-sample endpoints
- 277 tests passing
- In repo at `mg_import_tool/` + zip at workspace root

### Database Split Phase 1 (transitional)
- 4 SQLite files routed by `core/database_router.py`
- All 6 systemd services still running
- See `core/database_router.py::TABLE_ROUTING` for the full map

### Documentation
- `intelligence-catalog/FIELD_INTELLIGENCE_PIPELINE.md` — updated to match shipped reality
- `docs/SESSION_LOG_2026-04-22.md` — this session
- `AI_ROADMAP.md` — Layer 2 added to build queue

---

## System Status

### Services Running
All 8 systemd services operational:
- mining-guardian
- dashboard-api (:8585)
- approval-api (:8686)
- slack-listener
- slack-commands
- overnight-automation
- prometheus (:9090)
- grafana-server (:3000)

### Postgres (Docker: `mining-guardian-db`)
- `mining_guardian` DB, user `guardian_admin`
- 11 schemas, catalog + field intelligence live here
- Access: `docker exec -e PGPASSWORD='...' mining-guardian-db psql -U guardian_admin -d mining_guardian`

### SQLite (split, Phase 1)
- `/databases/operational.db` (1.5 MB)
- `/databases/timeseries.db` (5.4 GB)
- `/databases/ai_knowledge.db` (5.2 MB)
- `/databases/audit.db` (1006 MB)

---

## Pending Items from Previous Sessions (still open)

### From 2026-04-21 session log
1. Power cycle miner 53476 (.31) at facility
2. Complete signal 6 (PSU voltage degradation) implementation
3. Thursday Apr 24: Re-enable S21/Auradine after HVAC work
4. May 5-9: Mac Mini arrives, migrate Cloudflare tunnels
5. Continue Phase 4: Add more tests, increase coverage

### From 2026-04-17 session (physical)
1. **Miner 53521** — CRITICAL, all 3 hashboards failing (0/126 ASICs each), IP .12,
   Antminer S19JPro, likely needs board replacement
2. **Miner 53482** (.46) — BiXBiT S19JPro running 83.5% of target, error codes 412+101,
   firmware `BiXBiT 0.9.9.3-stage29.2799`, needs operator eyeballs
3. **S21 Immersion Benchmark** — BiXBiT vs stock firmware comparison, miners .22/.23,
   customer CSV in progress
4. **S19J Pro Container HVAC** — `clients/av2_plant_client.py` in progress; BACnet points
   already mapped (see 2026-04-21 log)

---

## Quick Reference

### Postgres (Docker)
```bash
docker exec -e PGPASSWORD='MiningGuardian2026!' mining-guardian-db \
  psql -U guardian_admin -d mining_guardian -c "\dn"

# Resolver summary via API
curl http://localhost:5050/api/resolver-summary

# Unresolved peek
curl "http://localhost:5050/api/unresolved-sample?limit=50"
```

### SQLite Router
```bash
python core/database_router.py  # prints full routing table + connection test
```

### Log Files to Check
```
/tmp/daily_deep_dive.log        # 4pm deep dive
/tmp/direct_log_collection.log  # 1pm log collection
/tmp/daily_claude_training.log  # midnight training
/tmp/daily_refinement_chain.log # 1am refinement
/var/log/db_maintenance.log     # 3:30am DB vacuum
```
