# =============================================================================
# Mining Intelligence Catalog — One-Shot Deployment Script (Docker dev box)
# Run from: Mining-Guardian/intelligence-catalog/
# =============================================================================
# This script:
#   1. Starts PostgreSQL 16 in Docker
#   2. Waits for it to be ready
#   3. Copies SQL files into the container's /docker-entrypoint-initdb.d/
#   4. Runs the canonical seed-data/deploy_schema.sql (uses \ir relative includes)
#   5. Seeds 313 Bitcoin SHA-256 miners
#
# N6 consolidation (2026-04-27): the canonical schema entry point lives in
# seed-data/deploy_schema.sql and uses psql's \ir directive so the same file
# works in this Docker context AND in the customer Mac Mini install. The old
# duplicate intelligence-catalog/deploy_schema.sql with hardcoded
# /docker-entrypoint-initdb.d/ paths has been removed.
# =============================================================================

Write-Host "=== Mining Intelligence Catalog — Deployment ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Start PostgreSQL
Write-Host "[1/5] Starting PostgreSQL 16 in Docker..." -ForegroundColor Yellow
docker-compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: docker-compose failed. Is Docker Desktop running?" -ForegroundColor Red
    exit 1
}

# Step 2: Wait for PostgreSQL to be ready
Write-Host "[2/5] Waiting for PostgreSQL to be ready..." -ForegroundColor Yellow
$attempts = 0
$maxAttempts = 30
do {
    Start-Sleep -Seconds 2
    $attempts++
    $result = docker exec mining-guardian-db pg_isready -U guardian_admin -d mining_guardian 2>$null
    if ($LASTEXITCODE -eq 0) { break }
    Write-Host "  Waiting... ($attempts/$maxAttempts)"
} while ($attempts -lt $maxAttempts)

if ($attempts -ge $maxAttempts) {
    Write-Host "ERROR: PostgreSQL did not start in time." -ForegroundColor Red
    docker-compose logs db
    exit 1
}
Write-Host "  PostgreSQL is ready!" -ForegroundColor Green

# Step 3: Copy SQL files into container
Write-Host "[3/5] Copying SQL files into container..." -ForegroundColor Yellow
docker cp seed-data/intelligence_catalog_schema.sql mining-guardian-db:/docker-entrypoint-initdb.d/
docker cp seed-data/intelligence_catalog_schema_v2_additions.sql mining-guardian-db:/docker-entrypoint-initdb.d/
docker cp seed-data/intelligence_catalog_schema_v3_additions.sql mining-guardian-db:/docker-entrypoint-initdb.d/
docker cp seed-data/deploy_schema.sql mining-guardian-db:/docker-entrypoint-initdb.d/
docker cp seed-data/seed_miner_models.sql mining-guardian-db:/docker-entrypoint-initdb.d/
Write-Host "  SQL files copied." -ForegroundColor Green

# Step 4: Deploy schema
Write-Host "[4/5] Deploying schema (86+ tables across 10 schemas)..." -ForegroundColor Yellow
docker exec -i mining-guardian-db psql -U guardian_admin -d mining_guardian -f /docker-entrypoint-initdb.d/deploy_schema.sql
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Schema deployment failed. Check output above." -ForegroundColor Red
    exit 1
}
Write-Host "  Schema deployed!" -ForegroundColor Green

# Step 5: Seed miner data
Write-Host "[5/5] Seeding 313 Bitcoin SHA-256 ASIC miners..." -ForegroundColor Yellow
docker exec -i mining-guardian-db psql -U guardian_admin -d mining_guardian -f /docker-entrypoint-initdb.d/seed_miner_models.sql
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Seed data failed. Check output above." -ForegroundColor Red
    exit 1
}
Write-Host "  313 miners seeded!" -ForegroundColor Green

# Verification
Write-Host ""
Write-Host "=== Verification ===" -ForegroundColor Cyan
docker exec mining-guardian-db psql -U guardian_admin -d mining_guardian -c "
SELECT 'Tables' AS check, COUNT(*)::text AS result FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
UNION ALL
SELECT 'Schemas', COUNT(*)::text FROM information_schema.schemata WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'public')
UNION ALL
SELECT 'Manufacturers', COUNT(*)::text FROM hardware.manufacturers
UNION ALL
SELECT 'Miner Models', COUNT(*)::text FROM hardware.miner_models
UNION ALL
SELECT 'Sources', COUNT(*)::text FROM knowledge.sources
ORDER BY 1;
"

Write-Host ""
Write-Host "=== Deployment Complete ===" -ForegroundColor Green
Write-Host "Connection: postgresql://guardian_admin:<MG_DB_PASSWORD>@localhost:5432/mining_guardian" -ForegroundColor White
Write-Host "Tailscale:  postgresql://guardian_admin:<MG_DB_PASSWORD>@<tailscale-ip>:5432/mining_guardian" -ForegroundColor White
Write-Host "            (substitute the value of `$Env:MG_DB_PASSWORD or read from your .env)" -ForegroundColor DarkGray
