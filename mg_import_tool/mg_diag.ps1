# Mining Guardian — raw_json diagnostic script
# Runs one archive through process_archive() with full debug logging,
# then shows the interesting log lines and post-import DB counts.
#
# Save to:  C:\Users\User\Mining-Guardian\mg_import_tool\mg_diag.ps1
# Run with: powershell -ExecutionPolicy Bypass -File .\mg_diag.ps1
#
# Full output is written to: $env:TEMP\mg_diag_full.log
# Just the interesting lines go to: $env:TEMP\mg_diag_summary.log

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

$MGTool   = 'C:\Users\User\Mining-Guardian\mg_import_tool'
$Archive  = 'C:\Users\User\Downloads\Telegram Desktop\Antminer_S19_2024-06-27_2024-06-29.tar'
$PyFile   = Join-Path $env:TEMP 'mg_debug.py'
$FullLog  = Join-Path $env:TEMP 'mg_diag_full.log'
$SumLog   = Join-Path $env:TEMP 'mg_diag_summary.log'

# ---------------------------------------------------------------
# 1. Write the Python debug runner
# ---------------------------------------------------------------
$py = @'
import sys, logging
sys.path.insert(0, r"__MGTOOL__")
logging.basicConfig(
    level=logging.DEBUG,
    stream=sys.stdout,
    format='%(levelname)s %(name)s: %(message)s',
)
import mg_import as m
cp = {
    'host':     'localhost',
    'port':     5432,
    'database': 'mining_guardian',
    'user':     'guardian_admin',
}
try:
    m.process_archive(r"__ARCHIVE__", cp)
    print("=== process_archive RETURNED NORMALLY ===")
except Exception as exc:
    import traceback
    print("=== process_archive RAISED ===")
    traceback.print_exc()
'@ -replace '__MGTOOL__', $MGTool -replace '__ARCHIVE__', $Archive

Set-Content -Path $PyFile -Value $py -Encoding UTF8

# ---------------------------------------------------------------
# 2. Clean slate in the DB (preserves identity, same as handoff)
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
Write-Host '  Step 1/4 — Cleaning slate (preserves field_log_miner_identity)'
Write-Host '================================================================'
$cleanSql | docker exec -i -e "PGPASSWORD=$env:MG_DB_PASSWORD" mining-guardian-db psql -U guardian_admin -d mining_guardian

# ---------------------------------------------------------------
# 3. Run the import with DEBUG logging
# ---------------------------------------------------------------
Write-Host ''
Write-Host '================================================================'
Write-Host '  Step 2/4 — Running process_archive with DEBUG logging'
Write-Host '           (this may take 30-60 seconds, output is captured)'
Write-Host '================================================================'
Push-Location $MGTool
python $PyFile *>&1 | Out-File -FilePath $FullLog -Encoding UTF8
Pop-Location
$lineCount = (Get-Content $FullLog).Count
Write-Host "Captured $lineCount lines to $FullLog"

# ---------------------------------------------------------------
# 4. Extract interesting lines
# ---------------------------------------------------------------
Write-Host ''
Write-Host '================================================================'
Write-Host '  Step 3/4 — Interesting log lines (raw_json / Layer2 / errors)'
Write-Host '================================================================'
$patterns = 'raw_json|Layer2|insert_raw|ERROR|Traceback|RAISED|RETURNED NORMALLY|process_archive|identity|_insert_archive'
$hits = Select-String -Path $FullLog -Pattern $patterns
$hits | ForEach-Object { "{0,5}: {1}" -f $_.LineNumber, $_.Line } | Tee-Object -FilePath $SumLog
Write-Host ''
Write-Host "(Summary also saved to $SumLog)"

# ---------------------------------------------------------------
# 5. Post-import DB counts
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
Write-Host '  DONE. If the summary looks empty, the full log is at:'
Write-Host "  $FullLog"
Write-Host '================================================================'
