# Miner Intelligence Catalog

**Standalone backend research and intelligence database for Mining Guardian.**

This is NOT part of the production fleet operations system. It's a parallel research environment that ingests miner spec sheets, community knowledge, repair shop dumps, and historical logs to build a comprehensive knowledge base about every miner family Bobby's fleet operates or might operate in the future.

## Why this exists separately from `guardian.db`

| | guardian.db (production) | miner_intelligence (research) |
|---|---|---|
| Engine | SQLite | PostgreSQL 16 |
| Host | VPS (`100.106.123.83`) | ROBS-PC (`192.168.188.47`) |
| Size | ~1 GB max | 50-100 GB target, 1 TB ceiling |
| Workload | Real-time fleet ops, scans, audit log | Batch ingestion, web research, LLM analysis |
| Volatility | Production-stable, never rebuilt | Schema may evolve, rebuilds OK |
| Audience | Mining Guardian daemon + operator | Bobby + LLMs only |
| Backup | Daily dump to GitHub | Daily dump local + weekly cloud |

The two databases are separated so the research side can iterate freely without risking production stability. Guardian eventually queries the catalog read-only over Tailscale for spec lookups and pattern matches, but it does not depend on the catalog being available — if the PC is offline, Guardian keeps running on its existing knowledge.

## Hardware

**Phase 1 (now → July 2026): ROBS-PC**
- Windows 11
- AMD Ryzen 7 7800X3D — 8 cores / 16 threads, 96 MB L3 V-Cache (excellent for database workloads)
- 32 GB RAM (upgrading to 64 GB or 128 GB in ~1 month)
- 2 TB SSD attached via Thunderbolt 4 enclosure (pending enclosure delivery)
- Static IP `192.168.188.47` on facility subnet (DHCP reservation in router)
- Gateway `192.168.188.1`, subnet `255.255.255.0`
- Tailscale `100.110.87.1` (subnet gateway for `192.168.188.0/24`)
- Already running Qwen 2.5 32B Q4 on the RTX 4090 at `localhost:11434`
- Antivirus: Windows Defender only
- WSL2: installed
- Hostname: `ROBS-PC`

**Phase 2 (July 2026 onward): UGREEN NASync iDX6011 Pro**
- Intel Core Ultra 7 255H, 16c/16t, 96 TOPS AI inference
- 64 GB LPDDR5x RAM (8533 MHz)
- 6 × 3.5" SATA bays (180 TB raw HDD configured, ~120 TB usable in RAID 5/6)
- 2 × M.2 NVMe (PCIe Gen 4) for cache layer
- Dual 10 GbE
- Native Docker support, UGOS Pro Linux-based OS
- Designed for 24/7 AI workloads

Migration from Phase 1 to Phase 2 is one `pg_dump` + file copy + `pg_restore` over the LAN. ~20 minutes for 50 GB. Same `docker-compose.yml`, no code changes.

## Drive letter pinning (Thunderbolt enclosure)

Because the 2 TB SSD lives in a Thunderbolt 4 enclosure rather than internal SATA, **Windows may assign different drive letters across reboots** if other USB/Thunderbolt devices are plugged in. To prevent this:

1. After plugging in the enclosure for the first time, open **Disk Management** (`diskmgmt.msc`)
2. Right-click the SSD partition → **Change Drive Letter and Paths**
3. Assign letter **`D:`** explicitly
4. Windows will remember this assignment for that specific drive even across reboots

Postgres bind mounts are absolute paths (`D:\miner-intelligence\...`), so a wrong drive letter would prevent the container from starting. Better to fail fast with a clear error than to silently lose data.

## Schema — Completed

**90 tables | 2,363 columns | 10 schemas | 10-year design horizon**

The schema is implemented across three SQL files, designed to run in sequence:

| File | Lines | Content |
|---|---|---|
| `database/intelligence_catalog_schema.sql` | 4,431 | Base schema: 63 tables, 10 schemas, 16 enums, extensions, triggers |
| `database/intelligence_catalog_schema_v2_additions.sql` | 887 | V2: 9 new tables, 113 new columns — PSU serials, chip bins, board serials, fan specs, pinouts, known issues, reviews |
| `database/intelligence_catalog_schema_v3_additions.sql` | 1,256 | V3: 14+ new tables, 170+ columns — auto-discovery, container reference, immersion fluids, electricity, curtailment, depreciation, diagnostics, weather |

### Schemas

| Schema | Tables | Columns | Purpose |
|---|---|---|---|
| knowledge | 10 | 173 | Source tracking, citations, data conflicts, auto-discovery mechanism, LLM pattern accuracy |
| hardware | 19 | 637 | Miner hardware — manufacturers, chips, PSUs, control boards, hashboards, serial batches, chip bins, fan specs, pinouts, signal chains |
| firmware | 7 | 169 | Firmware releases, compatibility, API capabilities, telemetry fields, known bugs, changelogs, autotuning profiles |
| ops | 9 | 240 | Failure patterns, symptoms, probabilistic diagnosis, thresholds, environmental correlations, baselines |
| market | 10 | 239 | User reviews, pricing, manufacturer reputation, forum posts, teardowns, war stories, depreciation, resale values |
| repair | 10 | 257 | Parts catalog, suppliers, repair procedures, step-by-step guides, shop directory, repair records, diagnostic tools |
| pool | 7 | 152 | Pool directory, endpoints, stratum configs, reliability history, incidents, Bitcoin network snapshots |
| facility | 13 | 395 | Cooling solutions, HVAC patterns, container hydraulics/cooling/environment, immersion fluids, electricity rates, demand response, curtailment, weather |
| regulatory | 5 | 101 | Legal frameworks, environmental regs, import/export rules, insurance, tax treatment |

### Auto-Discovery Mechanism

Four interconnected tables ensure no data point is ever skipped:
1. **`knowledge.field_registry`** — master dictionary of all known fields (75 pre-seeded entries)
2. **`knowledge.unknown_fields`** — captures any field not in the registry, with LLM auto-classification
3. **`knowledge.raw_ingestion_log`** — complete raw payload of every API response (partitioned by quarter)
4. **`knowledge.field_discovery_log`** — lifecycle audit trail for every discovered field

## Files in this directory

| File | Purpose |
|---|---|
| `docker-compose.yml` | Defines the Postgres container — image, port binding, bind mounts, healthcheck, resource limits |
| `postgres-tuning.conf` | Postgres performance config tuned for Ryzen 7800X3D + 32 GB RAM. Re-tune notes inside the file. |
| `.env.example` | Template for the secrets file. Copy to `.env` and fill in. NEVER commit `.env` to git. |
| `database/intelligence_catalog_schema.sql` | Base schema — 63 tables, 10 schemas, 16 enums, extensions, triggers (4,431 lines) |
| `database/intelligence_catalog_schema_v2_additions.sql` | V2 additions — 9 new tables, 113 new columns (887 lines) |
| `database/intelligence_catalog_schema_v3_additions.sql` | V3 additions — 14+ new tables, 170+ columns, auto-discovery mechanism (1,256 lines) |
| `docs/intelligence_catalog_design_notes.md` | Design philosophy, decisions, and evolution notes |
| `docs/intelligence_catalog_gap_analysis.md` | Gap analysis — what was missing, what V3 added |
| `docs/mining_intelligence_catalog_paper.pdf` | 34-page comprehensive paper documenting everything about the catalog |
| `docs/schema_inventory.json` | Machine-readable inventory of all 90 tables and 2,363 columns |
| `scripts/` | (TBD) Ingestion, web research, backup, and migration scripts |
| `README.md` | This file |

## Install procedure (Phase 1 — ROBS-PC)

**Prerequisites verified before install:**
- ✅ Static IP `192.168.188.47` set on router (DHCP reservation)
- ✅ Gateway `192.168.188.1`, subnet `255.255.255.0`
- ✅ WSL2 installed
- ⏳ Docker Desktop installed
- ⏳ Thunderbolt 4 enclosure arrived, 2 TB SSD installed
- ⏳ SSD assigned to drive letter `D:` via Disk Management
- ⏳ Directory created: `D:\miner-intelligence\` (with subdirs: `postgres-data\`, `backups\`, `logs\`)
- ⏳ `.env` file created from `.env.example` with strong random password
- ⏳ Cloud backup account created (Backblaze B2 recommended)

**Install commands** (will be added to this README once we walk through them step by step):

```powershell
# 1. Verify Docker is alive
docker run hello-world

# 2. Clone the intelligence directory to D:\
# (or copy from the Mac repo manually)

# 3. Start Postgres
cd D:\miner-intelligence
docker compose up -d

# 4. Verify it's healthy
docker compose ps
docker compose logs miner-intel-db | findstr "ready to accept connections"

# 5. Connect from the host
docker exec -it miner-intel-db psql -U miner_intel -d miner_intelligence
```

**Connection from Mining Guardian VPS** (over Tailscale):
```bash
psql -h 192.168.188.47 -U miner_intel -d miner_intelligence
```

## Backup strategy

**Three copies, two media, one off-site (3-2-1 rule):**

1. **Primary** — live database on ROBS-PC's 2 TB SSD (Phase 1) → NAS RAID 5/6 (Phase 2)
2. **Secondary local** — daily `pg_dump` to `D:\miner-intelligence\backups\` (Phase 1) → NAS share (Phase 2). Keeps 14 days locally.
3. **Off-site** — encrypted nightly upload to Backblaze B2 of the day's `pg_dump`. Keeps 30 days remote.

Backups are scheduled via Windows Task Scheduler in Phase 1 and via NAS-native scheduling in Phase 2.

## Security model

- Postgres password is randomly generated (32 chars) and stored only in `D:\miner-intelligence\.env` on ROBS-PC. Never in git.
- Postgres listens on `192.168.188.47:5432` only — bound to the LAN interface, NOT the public internet.
- Access is gated by:
  1. Strong Postgres password
  2. The facility LAN being private (only your devices and the miners on `192.168.188.0/24`)
  3. Tailscale ACLs for remote access from the VPS
- No Cloudflare tunnel, no public ingress, no exposed ports beyond Tailscale + LAN.
- Backup files are encrypted with a separate passphrase before being uploaded to cloud.

## What this catalog is NOT

- ❌ NOT a replacement for `guardian.db`
- ❌ NOT consumer-facing, no UI in Phase 1
- ❌ NOT cloud-hosted, all data lives on hardware Bobby owns
- ❌ NOT a real-time fleet operations tool
- ❌ NOT shared with anyone outside Bobby and Mining Guardian itself

## Migration to NAS (July 2026)

Planned procedure once the UGREEN NASync iDX6011 Pro arrives:

1. Install Docker on the NAS (UGOS Pro has native Docker support)
2. Copy this `intelligence/` directory to the NAS
3. Update `docker-compose.yml` bind-mount paths to point at NAS storage volume
4. On ROBS-PC: `docker compose stop`, then `docker exec ... pg_dump > full_backup.sql`
5. Copy `full_backup.sql` to the NAS over LAN (~10 minutes for 60 GB at 1 GbE, faster if NAS gets a 10 GbE switch)
6. On NAS: `docker compose up -d`, then `psql ... < full_backup.sql`
7. Update VPS `.env` to point at NAS IP instead of `192.168.188.47`
8. Keep ROBS-PC as a hot standby for 30 days, then decommission the catalog there
9. Free the 2 TB SSD on ROBS-PC for other use

ROBS-PC stays in service after migration as the LLM host (Qwen 2.5 32B on the 4090) and as Mining Guardian's facility subnet gateway. The catalog just moves to its permanent home.
