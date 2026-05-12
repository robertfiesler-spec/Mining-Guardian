# Handoff — Tomorrow morning (2026-05-13): W14 execution day

> **Purpose.** Single page everything-you-need-to-know for tomorrow morning. Written 2026-05-12 evening at the end of a 10-PR working day. If you're future-Claude in a fresh session, read this **first** before any of the strategy docs. If you're Bobby starting the day, this is the briefing.
>
> **What's happening tomorrow:** W14 — split the single Postgres container holding two databases into two separate Postgres containers, one per database. Operational stays on port 5432. Catalog moves to port 5433.

---

## Where today left things (2026-05-12 final state)

**4 PRs merged this afternoon (in order #191 → #192 → #193 → #194):**

| PR | What |
|---|---|
| #191 | EXECUTION_PLAN_STATUS today's progress |
| #192 | W14_PREP D1-D7 locked + pre-W14 status section |
| #193 | W23 Grafana dashboards yml path fix |
| #194 | W26 audit results — no schema migration needed for federation |

**Main HEAD at end of day: `81b258e`** (PR #194 merge commit).

**Live Mini state:**
- All 10 launchd services running on W14a code with new Anthropic key
- `pmset -a sleep 0 disksleep 0` set (W01 closed)
- Step 0 backup files on disk at `/Library/Application Support/MiningGuardian/backups/`:
  - `pre-w14-operational-20260512-121154.dump` (24 MB)
  - `pre-w14-catalog-20260512-121154.dump` (596 KB)
  - **Both verified by restore-to-scratch.** Row counts matched baseline exactly.

**Baseline row counts (these must match after any rollback):**
- catalog: `miner_models`=324, `manufacturers`=17, `firmware_releases`=6, `war_stories`=22, `failure_patterns`=0
- operational: `miner_readings`=17856, `action_audit_log`=19, `miner_restarts`=8, `llm_analysis`=98

---

## Tomorrow's job: W14 — the 10-step Postgres split

**Authoritative runbook:** [`docs/strategy/W14_PREP.md`](strategy/W14_PREP.md) §"W14 — The topology change". Read steps 0–10 there. This handoff is a summary, not a replacement.

### D1–D7 decisions (all locked at defaults 2026-05-12)

| D | Locked value |
|---|---|
| D1 | **KEEP** container name `mining-guardian-db` (don't rename) |
| D2 | **SAME** password for both instances (one `MG_DB_PASSWORD`) |
| D3 | **ONE** parent dir for data: `/Library/Application Support/MiningGuardian/pgdata/` (existing) + `/Library/Application Support/MiningGuardian/pgdata-catalog/` (new) |
| D4 | Catalog **512MB** `shared_buffers`; operational stays at 1GB |
| D5 | Tuning **AFTER** the split (per A08 phase order) |
| D6 | **TWO** backup scripts + wrapper (`backup_operational.sh`, `backup_catalog.sh`, `daily_backup.sh`) |
| D7 | **INCLUDE** two-container provisioning in first customer .pkg (August ship) |

These are locked text in [`W14_PREP.md`](strategy/W14_PREP.md). No re-litigation needed during execution.

### Step-by-step (condensed from W14_PREP.md)

| Step | What | Reversible? |
|---|---|---|
| 0 | **Done** — backups taken, restore-verified | n/a |
| 1 | Unload 12 scheduled launchd jobs (leave 10 always-on running) | Yes — just reload |
| 2 | `docker run` new `mg-catalog-db` container on port 5433 with its own pgdata volume | Yes — stop+remove container |
| 3 | Drop empty bootstrap DB inside new container, restore from `pre-w14-catalog-*.dump` | Yes — stop+remove |
| 4 | Add `GUARDIAN_PG_CATALOG_HOST=127.0.0.1` and `GUARDIAN_PG_CATALOG_PORT=5433` to .env. **`core/db_targets.py` resolver functions are ALREADY pre-staged in `main` (PR #197, 2026-05-12 evening)** — just `scp` the file to Mini's install root. No code edit during the maintenance window. | Yes — remove env vars |
| 5 | Bootout/bootstrap **all 10** always-on services (W14_PREP says 9; **it's actually 10** — include `feedback-loop-daemon`) | Yes — just restart |
| 6 | Smoke test: `core.db_targets` reports catalog on `127.0.0.1:5433`; one deep-dive smoke run; one normal scan | n/a |
| 7 | **`DROP DATABASE mining_guardian_catalog`** on old container | 🚨 **IRREVERSIBLE** without restoring from backup |
| 8 | Reload 12 scheduled jobs | n/a |
| 9 | Update `scripts/daily_backup.sh` per D6 | (separate PR) |
| 10 | Update installer (`install_colima.sh`, `postinstall.sh`) per D7 | (separate PR) |

**The risk gate is Step 7.** Everything before it is fully reversible. Don't run Step 7 until Step 6 smoke tests are green. If you have any doubt, sleep on it and run Step 7 next day.

### Recommended maintenance window

W14_PREP suggests **02:00–04:00 CDT** — between the 01:00 refinement chain run and the 04:00 db_maintenance job. Quiet hour. If you'd rather do it during your awake hours, that's fine too; just make sure you're not running it across the top of the 13:00 Pass 2 / 16:00 daily deep dive boundary.

### Rollback (if anything breaks before Step 7)

```bash
docker stop mg-catalog-db && docker rm -f mg-catalog-db
sudo rm -rf "/Library/Application Support/MiningGuardian/pgdata-catalog"
# remove the two new GUARDIAN_PG_CATALOG_* env vars from .env
# bootout/bootstrap all 10 services
# reload 12 scheduled jobs
```

Time-to-rollback: ~10 minutes.

### Rollback (if anything breaks after Step 7)

The pre-W14 backup is the rollback artifact:

```bash
docker stop mg-catalog-db && docker rm -f mg-catalog-db
sudo rm -rf "/Library/Application Support/MiningGuardian/pgdata-catalog"
# Restore catalog back into the old operational container
/usr/local/bin/docker exec mining-guardian-db psql -U mg -d postgres \
  -c "CREATE DATABASE mining_guardian_catalog OWNER mg;"
/usr/local/bin/docker exec -i mining-guardian-db pg_restore -U mg \
  -d mining_guardian_catalog --no-owner --no-privileges \
  < "/Library/Application Support/MiningGuardian/backups/pre-w14-catalog-20260512-121154.dump"
# Remove the two new GUARDIAN_PG_CATALOG_* env vars
# Bootout/bootstrap all 10 services
# Reload 12 scheduled jobs
# Verify row counts match baseline (see top of this doc)
```

Time-to-rollback: ~15 minutes.

---

## Important corrections to W14_PREP.md to note during execution

W14_PREP was written 2026-05-09 before some things were locked. The doc text didn't get fully re-edited; here are the corrections to apply mentally tomorrow:

1. **"9 always-on services"** in W14_PREP Step 5 — should be **10**. The 10th is `feedback-loop-daemon` (added in PR #185 / AMENDMENT A07). When you bootout/bootstrap, include it.
2. **"W14a not yet done"** language in W14_PREP — W14a is done (PRs #186–#189 merged + deployed today).
3. **Docker CLI path** — `/usr/local/bin/docker` (Colima). The doc just says `docker`. If `docker` isn't on PATH (Claude's SSH sessions hit this), use the full path.
4. **`core/db_targets.py` code change in Step 4 is ALREADY DONE in `main` (PR #197).** W14_PREP §Step 4 shows code to edit live — don't. Instead just `scp` the file from your laptop to the Mini's install root. The new resolver functions are backward-compatible by design (fall back to operational host/port when catalog env vars are unset), so deploying the file is safe pre-W14. The behavior change is gated on the env vars from Step 4's `.env` edit.

---

## What's coming AFTER W14 (don't start tomorrow)

Per [`05_CATALOG_DESIGN_PLAN_2026-05-12.md`](strategy/05_CATALOG_DESIGN_PLAN_2026-05-12.md) §6 — locked phase order working backward from mid-August 2026 customer ship:

| Order | Item | Effort | When |
|---|---|---|---|
| 1 | **W14b** — lock two-target convention in CLAUDE.md + .env.example + postinstall.sh | XS | Day after W14, once stable |
| 2 | W10 — extend `dual_writer` with 5 propose_* functions | S | Next week |
| 3 | W11 — Slack `/intel paste` + intake API + structure extractor | M-L | Next week |
| 4 | W06, W07, W08 — AI reads `model_known_issues`, `war_stories`, `environmental_correlations` | S each | Week after |
| 5 | W09 — Daily Pass 2 reads catalog (**biggest unrealized AI value**) | M | Week after |
| 6 | W26 — cohort guard test (audit found near-zero scope; just the test) | XS | June |
| 7 | W27 — `ops.field_observed_specs` + mg_import_tool Layer 2.5 | M | June |
| 8 | W30 — enrichment CSV → chips/PSUs structured rows | M | June |
| 9 | W23/W24/W25 + W12 — Grafana intelligence dashboard rebuild | M | Late June |
| 10 | W28, W29 — Federation v1 + Pass 2 cadence config flag | L | July |
| 11 | Customer .pkg + notarization + August bake | (multi-day) | Late July / early August |

Federation v1 (W28) is the big one for customer ship — that's the **bidirectional monthly sync** locked from the operator dialogue. Don't get distracted by polishing W18-W22 performance work; those are post-August per A08.

---

## Sanity-check questions for tomorrow morning

Before running Step 1, confirm:

- [ ] `git log --oneline -1` shows `81b258e` (PR #194 merge) on main — your local repo matches what's verified
- [ ] `ssh miningguardian@100.69.66.32 'ls -lh "/Library/Application Support/MiningGuardian/backups/"'` returns both dump files
- [ ] `ssh miningguardian@100.69.66.32 '/usr/local/bin/docker ps'` shows `mining-guardian-db` healthy
- [ ] `sudo launchctl list | grep com.miningguardian` on Mini returns 22 entries (10 always-on + 12 scheduled)
- [ ] You have at least 2 hours uninterrupted (rollback takes 15 min; execution + smoke takes 60-90 min; buffer matters)
- [ ] Your sudo SSH session to the Mini is live and authenticated

If all 6 boxes check, run W14_PREP Step 1.

---

## Open items not blocking W14 (for context, not for tomorrow)

- **W23 sub-items** still open: datasource user standardization deferred to W14b; password inlining deferred to W24
- **W25 Grafana panels** still showing "No data" — Bobby's preference is Path B (rebuild the 6 April-era branded dashboards). Doesn't block W14.
- **W22 raw_ingestion_log partition** extension deadline is 2027-Q2 — months away
- **AMS BiXBiT API key** in mg_import_tool was redacted to first 8 chars of sha256 in some old branch — investigate before customer ship

---

## Quick reference — Mini paths and commands

```bash
# SSH
ssh miningguardian@100.69.66.32

# Docker (NOT on PATH in non-interactive SSH — use full path)
/usr/local/bin/docker ps
/usr/local/bin/docker exec mining-guardian-db psql -U mg -d mining_guardian -c "SELECT 1;"

# Install root (post-v1.0.1 B-13 fix)
"/Library/Application Support/MiningGuardian/"

# .env location
"/Library/Application Support/MiningGuardian/.env"

# Backup files
"/Library/Application Support/MiningGuardian/backups/pre-w14-operational-20260512-121154.dump"
"/Library/Application Support/MiningGuardian/backups/pre-w14-catalog-20260512-121154.dump"

# Launchd plists
/Library/LaunchDaemons/com.miningguardian.*.plist

# Service control (needs sudo)
sudo launchctl list | grep com.miningguardian
sudo launchctl bootout system "/Library/LaunchDaemons/com.miningguardian.SERVICE.plist"
sudo launchctl bootstrap system "/Library/LaunchDaemons/com.miningguardian.SERVICE.plist"
```

---

*End of handoff. Now you have everything you need for tomorrow in one place.*
