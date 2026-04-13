# =============================================================================
# Mining Intelligence Catalog - One-Shot Deployment Script
# Run from: Mining-Guardian/intelligence-catalog/
# =============================================================================

Write-Host "=== Mining Intelligence Catalog - Deployment ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Start PostgreSQL
Write-Host "[1/6] Starting PostgreSQL 16 in Docker..." -ForegroundColor Yellow
docker-compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: docker-compose failed. Is Docker Desktop running?" -ForegroundColor Red
    exit 1
}

# Step 2: Wait for PostgreSQL to be ready
Write-Host "[2/6] Waiting for PostgreSQL to be ready..." -ForegroundColor Yellow
$attempts = 0
$maxAttempts = 30
do {
    Start-Sleep -Seconds 2
    $attempts++
    $result = docker exec mining-guardian-db pg_isready -U guardian_admin -d mining_guardian 2>$null
    if ($LASTEXITCODE -eq 0) { break }
    Write-Host "  Waiting... attempt $attempts of $maxAttempts"
} while ($attempts -lt $maxAttempts)

if ($attempts -ge $maxAttempts) {
    Write-Host "ERROR: PostgreSQL did not start in time." -ForegroundColor Red
    docker-compose logs db
    exit 1
}
Write-Host "  PostgreSQL is ready." -ForegroundColor Green

# Step 3: Copy SQL files into container
Write-Host "[3/6] Copying SQL files into container..." -ForegroundColor Yellow
docker cp seed-data/intelligence_catalog_schema.sql mining-guardian-db:/docker-entrypoint-initdb.d/
docker cp seed-data/intelligence_catalog_schema_v2_additions.sql mining-guardian-db:/docker-entrypoint-initdb.d/
docker cp seed-data/intelligence_catalog_schema_v3_additions.sql mining-guardian-db:/docker-entrypoint-initdb.d/
docker cp seed-data/fix_and_seed.sql mining-guardian-db:/docker-entrypoint-initdb.d/
docker cp seed-data/seed_miner_models.sql mining-guardian-db:/docker-entrypoint-initdb.d/
Write-Host "  SQL files copied." -ForegroundColor Green

# Step 4: Deploy base schema
Write-Host "[4/6] Deploying base schema..." -ForegroundColor Yellow
docker exec mining-guardian-db psql -U guardian_admin -d mining_guardian -f /docker-entrypoint-initdb.d/intelligence_catalog_schema.sql
Write-Host "  Base schema done." -ForegroundColor Green

# Step 4b: Deploy V2 additions
Write-Host "  Deploying V2 additions..." -ForegroundColor Yellow
docker exec mining-guardian-db psql -U guardian_admin -d mining_guardian -f /docker-entrypoint-initdb.d/intelligence_catalog_schema_v2_additions.sql
Write-Host "  V2 done." -ForegroundColor Green

# Step 4c: Deploy V3 additions
Write-Host "  Deploying V3 additions..." -ForegroundColor Yellow
docker exec mining-guardian-db psql -U guardian_admin -d mining_guardian -f /docker-entrypoint-initdb.d/intelligence_catalog_schema_v3_additions.sql
Write-Host "  V3 done." -ForegroundColor Green

# Step 5: Fix constraints, add enums, seed manufacturers and sources
Write-Host "[5/6] Fixing constraints and seeding manufacturers..." -ForegroundColor Yellow
docker exec mining-guardian-db psql -U guardian_admin -d mining_guardian -f /docker-entrypoint-initdb.d/fix_and_seed.sql
Write-Host "  Manufacturers and sources seeded." -ForegroundColor Green

# Step 6: Seed miner data
Write-Host "[6/6] Seeding 313 Bitcoin SHA-256 ASIC miners..." -ForegroundColor Yellow
docker exec mining-guardian-db psql -U guardian_admin -d mining_guardian -f /docker-entrypoint-initdb.d/seed_miner_models.sql
Write-Host "  Miners seeded." -ForegroundColor Green

# Verification
Write-Host ""
Write-Host "=== Verification ===" -ForegroundColor Cyan
$query = @"
SELECT 'Tables' AS check_name, COUNT(*)::text AS result FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
UNION ALL
SELECT 'Schemas', COUNT(*)::text FROM information_schema.schemata WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'public')
UNION ALL
SELECT 'Manufacturers', COUNT(*)::text FROM hardware.manufacturers
UNION ALL
SELECT 'Miner Models', COUNT(*)::text FROM hardware.miner_models
UNION ALL
SELECT 'Sources', COUNT(*)::text FROM knowledge.sources
ORDER BY 1;
"@
docker exec mining-guardian-db psql -U guardian_admin -d mining_guardian -c $query

Write-Host ""
Write-Host "=== Deployment Complete ===" -ForegroundColor Green
Write-Host "Local:     localhost:5432  db=mining_guardian  user=guardian_admin" -ForegroundColor White
Write-Host "Tailscale: 100.110.87.1:5432" -ForegroundColor White
