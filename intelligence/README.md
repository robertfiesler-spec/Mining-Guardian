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

## What this catalog will hold (planned tables)

To be finalized through Q2-Q10 design questions. Initial sketch:

- **`model_specs`** — vendor-published spec sheets (TH/s, watts, voltage, board count, chip type, PSU, control board, etc.). One row per miner model. Source-tagged with confidence score.
- **`community_knowledge`** — Reddit posts, forum threads, blog reviews, teardown writeups, war stories. Full-text indexed. Tagged by miner family.
- **`log_archive`** — pointer to raw log files on disk + extracted metadata (brand, model, firmware, serial, MAC, ingestion timestamp, source).
- **`log_metrics`** — structured data parsed out of logs (per-chip hashrate, voltages, error counts, panic traces).
- **`diagnostic_test_results`** — what tests fired against what logs and what the verdict was.
- **`dual_model_verdicts`** — Qwen and Claude analyses side by side, for jump-start training.
- **`known_patterns`** — cross-miner patterns once they emerge (e.g., "AH3880 Board 3 failures cluster around chassis serials 080010xxx batch").
- **`ingestion_log`** — provenance of every file ever fed in (source, timestamp, who/what fed it).
- **`web_research_cache`** — every URL ever fetched, content cached, expiry date — so we don't rehit vendor sites.
- **`miner_hardware_components`** — hashboard variants, PSU revisions, control board flavors, chip generations, BOM details, cross-referenced with `model_specs`.

## Files in this directory

| File | Purpose |
|---|---|
| `docker-compose.yml` | Defines the Postgres container — image, port binding, bind mounts, healthcheck, resource limits |
| `postgres-tuning.conf` | Postgres performance config tuned for Ryzen 7800X3D + 32 GB RAM. Re-tune notes inside the file. |
| `.env.example` | Template for the secrets file. Copy to `.env` and fill in. NEVER commit `.env` to git. |
| `schema/` | (TBD) SQL files defining tables, indexes, extensions |
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
