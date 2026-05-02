# Mining Guardian — State of the System (2026-05-02, 14:50 CDT)

**Author:** Computer (autonomous agent)
**Purpose:** Single page of ground truth, recovered from Session 59294da1 (368 turns) after a morning of wrong framings. Rob: read this, mark anything wrong, then we go.
**Mantras honored here:** "always over-document" · "leave no data behind" · "step by step" · "late and perfect over early and wrong"

---

## Hosts and what runs on each (TODAY, not the plan)

| Host | What's live | What it holds | Notes |
|---|---|---|---|
| **Hostinger VPS** (`187.124.247.182` / Tailscale `100.106.123.83`, path `/root/Mining-Guardian/`) | **Operational `mining_guardian` Postgres on :5432** + the actual Mining Guardian program (scans miners, polls AMS, writes readings, runs the 4 PM Qwen deep dive on ROBS-PC GPU) | Live fleet data — `miner_readings`, `miner_restarts`, `chain_readings`, `pool_readings`, `miner_hardware`, `action_audit_log`, `llm_analysis`, etc. **This is what feeds Grafana every morning.** | Path was `/root/Mining-Gaurdian/` (typo) — renamed to `/root/Mining-Guardian/` on Sunday. Path is load-bearing for cron jobs. |
| **ROBS-PC** (Windows 11, RTX 4090) | **Catalog `mining_guardian` Postgres in Docker container `mining-guardian-db`** (separate instance, port 5432 inside container) + `catalog-api` on :8420 + Qwen on the 4090 | Intelligence catalog reference — `hardware.*`, `firmware.*`, `ops.*`, `market.*`, `repair.*`, `pool.*`, `facility.*`, `regulatory.*`, `knowledge.*`, `staging.*`. Got the 355,626-row import on 2026-04-27. | Auth was broken this morning — D-1 password rotation never applied to the live volume. **Untouched as of right now per your stop call.** |
| **Mac Mini** (Fort Worth customer site) | **Empty.** Install was attempted 2026-05-01, aborted mid-Phase-2. | Nothing yet. | Cutover target. INSTALLER_UX_BACKLOG_2026-05-01.md has the 10 fixes needed before retry. |
| **Cloudflare** (Rob's `fieslerfamily.com`) | Fronts Grafana | — | Flagged as not customer-ready. |

**Two separate Postgres instances.** Not one. Not the same container. The catchup-doc line about "same Postgres 16 container" was wrong — that's what D-14 *plans* post-cutover, not what exists today.

---

## My 5 morning crons (Perplexity scheduled tasks I own)

Set up across 2026-04-24 → 2026-04-27. They run on **my agent host**, not on the VPS or ROBS-PC.

| Task | Cadence | What it writes | Where it writes |
|---|---|---|---|
| Aggregator Watcher | daily | Pricing/availability findings | `cron_tracking/aggregator_watcher/latest_findings.json` (file on disk) |
| Manufacturer Model Watcher | daily | New models found on manufacturer pages | `cron_tracking/manufacturer_watcher/latest_findings.json` (file on disk) |
| Firmware Tracker | daily | New firmware releases / changelogs | `cron_tracking/firmware_tracker/latest_findings.json` (file on disk) |
| Community Intel Scanner | daily | Forum/community signals | `cron_tracking/community_intel/latest_findings.json` (file on disk) |
| Deep Enrichment Sweep | every 2 days (tier-rotated) | Structured 39-field enrichment per model | `cron_tracking/enrichment_sweep/<DATE>_results.csv` + `unified_miner_index.json` updates |

**Critical correction to what I told you 5 minutes ago:** I said "that data went into the database." It did **not**. My own message at line 18837 of today's session: *"The watchers write findings to JSON files at cron_tracking/<watcher>/latest_findings.json — pure files on disk, no DB writes."* The Deep Enrichment Sweep is the only one that touches the catalog data shape (CSV + JSON), and even that one writes to files, not Postgres.

**What "the database" actually has:** the catalog Postgres on ROBS-PC has whatever was imported by the 2026-04-27 355k-row run + whatever `catalog_updater.py --add-from-csv` was run manually. It does **not** auto-receive my morning cron output.

---

## What "leave no data behind" actually means in code

The richest enrichment lives in **two files**: `intelligence-catalog/data/unified_miner_index.json` (288 slugs, 225 with rich `enrichment` dicts) and `intelligence-catalog/data/miner_enrichment_master.csv` (277 rows, 16 columns of Perplexity-research text).

The catalog API endpoint `GET /api/v1/knowledge/miner/{slug}` reads from **Postgres only**, not from those files. So when the Postgres rows for chips, PSUs, firmware, known issues are sparse (which they are), the API returns a thin shell — even though the rich answer is sitting in the JSON/CSV right next to it.

**That is the actual gap.** Not split-brain, not password rotation, not seeding. The data exists; the API just isn't surfacing it.

---

## What we agreed to do (Rob's directive in this session)

1. **Rebuild the installer** so the Mini install actually completes (10 bugs in `INSTALLER_UX_BACKLOG_2026-05-01.md`).
2. **Fix the database** — i.e., extend the catalog API to surface every dimension we have data on (chips, boards, firmware, known issues, voltage, release date, PSU compat, cooling, error codes), and on the Postgres side make the same data reachable to the operational AI for analysis.
3. **Put the program on the Mini** — second install attempt with Option γ scope (Mini replaces both VPS and ROBS-PC).

Order is fixed: installer fixes → DB surface fix → Mini install retry. We don't re-attempt the Mini install on a broken installer.

---

## Things I had wrong this morning, listed plainly

1. **"hardware.miner_models is empty"** — wrong. Catalog Postgres on ROBS-PC has 317 seeded rows + the 2026-04-27 import. The auth failure made me see zeros and I jumped to "empty" without questioning the auth.
2. **"Both DBs in same Postgres container"** — wrong. They are two separate Postgres instances on two different hosts.
3. **"Split-brain bug to fix"** — wrong. PR #15 + PR #22 closed split-brain on 2026-04-28. Today's gap is API surface, not DB write path.
4. **"Run docker volume rm"** — wrong and dangerous. You stopped me. The volume holds the 2026-04-27 import.
5. **"My morning crons write to the database"** — wrong. They write to JSON/CSV files in `cron_tracking/`. The DB only receives data when someone runs `catalog_updater.py --add-from-csv` manually.
6. **D-12 vs D-14 confusion** — D-12 is "Postgres-as-truth for spec/observation split" (locked 2026-04-27). D-14 is the future single-Postgres-on-Mini architecture, not today's reality.

---

## What I am NOT going to touch until you say go

- ROBS-PC Docker stack (containers stay down where you left them, volume intact)
- Any Postgres password
- Any catalog DB rows
- Any cron schedule

## What I'd like to do next, in order, with your approval at each step

1. **Read the installer backlog** (`INSTALLER_UX_BACKLOG_2026-05-01.md`) and propose a PR sequence for the 10 bugs. No code yet.
2. **Once installer plan is locked** — execute it bug by bug, one PR each, you approve each.
3. **After installer is green** — write the catalog API surface fix plan (extend `/knowledge/miner/{slug}` to merge JSON/CSV enrichment into responses; extend `dual_writer.py` with `propose_chip` / `propose_psu_model` / `propose_firmware_release` / `propose_known_issue` / `propose_error_code` so future cron output can land in Postgres correctly).
4. **Mini install retry** — only after 1 and 2 are merged, tagged, and you've signed off.

That's it. Tell me what's wrong on this page and we'll fix it before I touch anything else.

— Computer
