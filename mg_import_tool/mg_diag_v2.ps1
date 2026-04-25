# Mining Guardian — raw_json diagnostic v2 (drives Flask endpoint)
# This version goes through the real import pipeline: /api/import-files-stream
# which is what the web UI uses and what produced yesterday's 6/7 green tables.
#
# Prerequisites:
#   1. Flask server running:  .\launch_mg_import.bat  (serves on http://localhost:5050)
#   2. Postgres up:            docker ps | findstr mining-guardian-db
#
# Run with: powershell -ExecutionPolicy Bypass -File .\mg_diag_v2.ps1

$ErrorActionPreference = 'Continue'

# ---------------------------------------------------------------
# CRIT-1: refuse to run without MG_DB_PASSWORD env var
# ---------------------------------------------------------------
if (-not $env:MG_DB_PASSWORD) {
    Write-Host ""
    Write-Host "ERROR: MG_DB_PASSWORD environment variable is not set." -ForegroundColor Red
    Write-Host "This script requires the rotated guardian_admin password." -ForegroundColor Red
    Write-Host "Set it for the current session:" -ForegroundColor Yellow
    Write-Host '  $env:MG_DB_PASSWORD = [Environment]::GetEnvironmentVariable("MG_DB_PASSWORD","User")' -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

$Archive   = 'C:\Users\User\Downloads\Telegram Desktop\Antminer_S19_2024-06-27_2024-06-29.tar'
$ApiUrl    = 'http://localhost:5050/api/import-files-stream'
$FullLog   = Join-Path $env:TEMP 'mg_diag_v2_full.log'

$ConnParamsFile = Join-Path $env:TEMP 'mg_conn_params.json'
@{
    host     = 'localhost'
    port     = 5432
    database = 'mining_guardian'
    user     = 'guardian_admin'
} | ConvertTo-Json -Compress | Out-File -FilePath $ConnParamsFile -Encoding ASCII -NoNewline

# ---------------------------------------------------------------
# 0. Check Flask is actually listening
# ---------------------------------------------------------------
Write-Host ''
Write-Host '================================================================'
Write-Host '  Step 0/4 — Checking Flask server on port 5050'
Write-Host '================================================================'
try {
    $ping = Invoke-WebRequest -Uri 'http://localhost:5050/' -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    Write-Host "Flask is up (status $($ping.StatusCode))"
} catch {
    Write-Host ''
    Write-Host '   Flask server is NOT running on port 5050.'
    Write-Host '   Open a second PowerShell window, then run:'
    Write-Host '     cd C:\Users\User\Mining-Guardian\mg_import_tool'
    Write-Host '     .\launch_mg_import.bat'
    Write-Host '   Leave that window open and re-run this script.'
    Write-Host ''
    exit 1
}

# ---------------------------------------------------------------
# 1. Clean slate (preserves field_log_miner_identity)
# ---------------------------------------------------------------
$cleanSql = @'
DELETE FROM knowledge.field_log_imports;
DELETE FROM knowledge.field_log_pools;
DELETE FROM knowledge.field_log_antminer_boots;
DELETE FROM knowledge.field_log_antminer_autotune;
DELETE FROM knowledge.field_log_events;
DELETE FROM mg.import_runs;
DELETE FROM knowledge.field_log_raw_json;
'@

Write-Host ''
Write-Host '================================================================'
Write-Host '  Step 1/4 — Cleaning slate'
Write-Host '================================================================'
$cleanSql | docker exec -i -e "PGPASSWORD=$env:MG_DB_PASSWORD" mining-guardian-db psql -U guardian_admin -d mining_guardian

# ---------------------------------------------------------------
# 2. POST the archive to the Flask endpoint, capture SSE stream
# ---------------------------------------------------------------
Write-Host ''
Write-Host '================================================================'
Write-Host '  Step 2/4 — POSTing archive to Flask /api/import-files-stream'
Write-Host '           (this is the same path the UI uses)'
Write-Host '================================================================'

if (-not (Test-Path $Archive)) {
    Write-Host "Archive not found: $Archive"
    exit 1
}

# Use curl.exe (bundled with Windows 10+) for reliable multipart upload + SSE capture
# -s silent, -N no-buffer for SSE
# Use curl's @filename syntax so PowerShell doesn't mangle the JSON quotes
& curl.exe -s -N -X POST $ApiUrl `
    -F "files[]=@$Archive" `
    -F "conn_params=<$ConnParamsFile" `
    *>&1 | Tee-Object -FilePath $FullLog

Write-Host ''
Write-Host "Full SSE stream captured to: $FullLog"

# ---------------------------------------------------------------
# 3. Extract interesting events
# ---------------------------------------------------------------
Write-Host ''
Write-Host '================================================================'
Write-Host '  Step 3/4 — Key SSE events (errors, raw_json, totals)'
Write-Host '================================================================'
Select-String -Path $FullLog -Pattern 'error|raw_json|archive_done|batch_done|archive_error|statements_run|rows_affected'

# ---------------------------------------------------------------
# 4. Post-import DB counts
# ---------------------------------------------------------------
Write-Host ''
Write-Host '================================================================'
Write-Host '  Step 4/4 — Post-import row counts'
Write-Host '================================================================'
$countSql = @'
SELECT 'imports'      AS tbl, COUNT(*) FROM knowledge.field_log_imports
UNION ALL SELECT 'identity',    COUNT(*) FROM knowledge.field_log_miner_identity
UNION ALL SELECT 'raw_json',    COUNT(*) FROM knowledge.field_log_raw_json
UNION ALL SELECT 'pools',       COUNT(*) FROM knowledge.field_log_pools
UNION ALL SELECT 'boots',       COUNT(*) FROM knowledge.field_log_antminer_boots
UNION ALL SELECT 'autotune',    COUNT(*) FROM knowledge.field_log_antminer_autotune
UNION ALL SELECT 'events',      COUNT(*) FROM knowledge.field_log_events
UNION ALL SELECT 'import_runs', COUNT(*) FROM mg.import_runs;
'@
$countSql | docker exec -i -e "PGPASSWORD=$env:MG_DB_PASSWORD" mining-guardian-db psql -U guardian_admin -d mining_guardian

Write-Host ''
Write-Host '================================================================'
Write-Host '  DONE.'
Write-Host "  Full log: $FullLog"
Write-Host '================================================================'
