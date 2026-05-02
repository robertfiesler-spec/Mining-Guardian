# Step 0 · Pre-flight Baseline Capture — ROBS-PC

**Run on:** ROBS-PC (Windows, the box hosting `mining-guardian-db`)
**Run by:** Rob, ~5 minutes total
**Purpose:** Capture the **before** state so the audit trail proves the fix actually changed something. Nothing here modifies any data.
**Output:** Two files Rob will paste back to me — `baseline_counts.txt` and `baseline_api.txt`.

---

## Why we do this first

Per "always over-document": every claim in the PR ("288 rows imported," "API now returns real data") needs a paired before/after artifact. If we skip Step 0, the audit doc has only an "after" half — useless if anything goes sideways and we need to retreat.

---

## Commands — copy/paste into PowerShell on ROBS-PC

> All commands assume you're in the repo root: `cd C:\path\to\Mining-Guardian` first.

### 0.1 · Container health (5 seconds)

```powershell
docker ps --filter "name=mining-guardian-db" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

**Expected:** one row showing `mining-guardian-db   Up X hours   0.0.0.0:5432->5432/tcp`. If empty, run `docker-compose -f intelligence-catalog\docker-compose.yml up -d` first and wait 15 seconds.

### 0.2 · Catalog API health (5 seconds)

```powershell
curl http://localhost:8420/health
```

**Expected:** `{"status":"ok"}` or similar. If connection refused, the catalog-api container isn't running — start it the same way as 0.1.

### 0.3 · Baseline row counts in all 22 tables — save to file

```powershell
docker exec -i mining-guardian-db psql -U guardian_admin -d mining_guardian -c @"
SELECT
  'hardware.manufacturers' AS table_name, COUNT(*) AS row_count FROM hardware.manufacturers
UNION ALL SELECT 'hardware.miner_models', COUNT(*) FROM hardware.miner_models
UNION ALL SELECT 'hardware.chips', COUNT(*) FROM hardware.chips
UNION ALL SELECT 'hardware.psu_models', COUNT(*) FROM hardware.psu_models
UNION ALL SELECT 'hardware.model_known_issues', COUNT(*) FROM hardware.model_known_issues
UNION ALL SELECT 'firmware.firmware_releases', COUNT(*) FROM firmware.firmware_releases
UNION ALL SELECT 'firmware.firmware_compatibility', COUNT(*) FROM firmware.firmware_compatibility
UNION ALL SELECT 'firmware.firmware_bugs', COUNT(*) FROM firmware.firmware_bugs
UNION ALL SELECT 'ops.failure_patterns', COUNT(*) FROM ops.failure_patterns
UNION ALL SELECT 'ops.failure_symptoms', COUNT(*) FROM ops.failure_symptoms
UNION ALL SELECT 'ops.miner_error_codes', COUNT(*) FROM ops.miner_error_codes
UNION ALL SELECT 'ops.operational_thresholds', COUNT(*) FROM ops.operational_thresholds
UNION ALL SELECT 'ops.miner_baseline_reference', COUNT(*) FROM ops.miner_baseline_reference
UNION ALL SELECT 'ops.operational_profiles', COUNT(*) FROM ops.operational_profiles
UNION ALL SELECT 'ops.environmental_correlations', COUNT(*) FROM ops.environmental_correlations
UNION ALL SELECT 'repair.repair_procedures', COUNT(*) FROM repair.repair_procedures
UNION ALL SELECT 'repair.diagnostic_tools', COUNT(*) FROM repair.diagnostic_tools
UNION ALL SELECT 'repair.parts', COUNT(*) FROM repair.parts
UNION ALL SELECT 'facility.cooling_solutions', COUNT(*) FROM facility.cooling_solutions
UNION ALL SELECT 'facility.container_environment_reference', COUNT(*) FROM facility.container_environment_reference
UNION ALL SELECT 'staging.miner_model_proposals', COUNT(*) FROM staging.miner_model_proposals
ORDER BY table_name;
"@ > docs\INTEL_CATALOG_BASELINE_COUNTS_2026-05-02.txt
```

**Expected:** every row shows `0` except possibly `staging.miner_model_proposals` (might be 0 too). If any table errors with "relation does not exist," **stop and tell me which one** — that means the schema files weren't fully applied, which is a different bug.

### 0.4 · Baseline API responses for 3 sample slugs — save to file

```powershell
$slugs = @("antminer-s19xp", "whatsminer-m50s", "antminer-s21-hydro")
"=== BASELINE API RESPONSES ($(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')) ===" | Out-File docs\INTEL_CATALOG_BASELINE_API_2026-05-02.txt
foreach ($s in $slugs) {
  "`n--- /knowledge/$s ---" | Out-File docs\INTEL_CATALOG_BASELINE_API_2026-05-02.txt -Append
  curl "http://localhost:8420/knowledge/$s" | Out-File docs\INTEL_CATALOG_BASELINE_API_2026-05-02.txt -Append
}
Get-Content docs\INTEL_CATALOG_BASELINE_API_2026-05-02.txt | Select-Object -First 60
```

**Expected:** each response should show empty arrays / empty objects for `models`, `failure_patterns`, `firmware`, etc. — the smoking gun for the split-brain.

### 0.5 · Confirm the JSON enrichment file is present and readable

```powershell
$json = Get-Content intelligence-catalog\data\unified_miner_index.json -Raw | ConvertFrom-Json
"unified_miner_index.json: $($json.PSObject.Properties.Name.Count) miner slugs"
```

**Expected:** `unified_miner_index.json: 288 miner slugs` (matches what I counted in the sandbox).

---

## What you send back

Paste these two file contents into our chat:

1. **`docs\INTEL_CATALOG_BASELINE_COUNTS_2026-05-02.txt`** — the row-count snapshot
2. **`docs\INTEL_CATALOG_BASELINE_API_2026-05-02.txt`** — the API empty-response snapshot

Plus a one-line confirmation of the slug count from 0.5.

That gives me everything I need to lock in Step 1 (branch + audit doc skeleton) and move on to Step 2 (running the seed).

---

## Troubleshooting cheat sheet

| Symptom | Likely cause | Fix |
|---|---|---|
| `docker ps` shows nothing | Containers stopped | `docker-compose -f intelligence-catalog\docker-compose.yml up -d` |
| `curl :8420/health` connection refused | catalog-api container down or unhealthy | `docker logs catalog-api --tail 50` |
| psql says "role guardian_admin does not exist" | Wrong env or container reset | check `intelligence-catalog\.env` for `MG_DB_PASSWORD` |
| psql says "relation hardware.miner_models does not exist" | Schema files weren't applied | tell me — separate fix needed before Step 2 |
| `ConvertFrom-Json` fails | JSON file corrupted | `git status` to see if it's modified locally; revert if so |

---

*Step 0 deliverable. After you run this and paste results back, I move to Step 1.*
