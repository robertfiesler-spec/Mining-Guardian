#!/bin/bash
# Database Maintenance Script — Postgres version
# Runs daily to keep the Postgres mining_guardian database healthy.
# Rewritten 2026-04-23 during migration from SQLite to Postgres.
#
# Expected to run as root via cron at 3:30am daily.

set -e

LOG_FILE="/var/log/db_maintenance.log"
PGDB="mining_guardian"

echo "$(date +%Y-%m-%d\ %H:%M:%S) Starting database maintenance (Postgres)…" >> $LOG_FILE

# 1. VACUUM ANALYZE — reclaims space from deleted rows AND updates query stats.
#    Safe to run while services are active; uses MVCC, no locks on active tables.
echo "  Running VACUUM ANALYZE…" >> $LOG_FILE
sudo -u postgres psql -d $PGDB -c "VACUUM ANALYZE;" >> $LOG_FILE 2>&1

# 2. Refresh planner stats specifically (redundant after VACUUM ANALYZE but cheap).
echo "  Running ANALYZE…" >> $LOG_FILE
sudo -u postgres psql -d $PGDB -c "ANALYZE;" >> $LOG_FILE 2>&1

# 3. Database size reporting.
DB_SIZE=$(sudo -u postgres psql -d $PGDB -tAc "SELECT pg_size_pretty(pg_database_size('$PGDB'))" 2>/dev/null)
echo "  Database size: $DB_SIZE" >> $LOG_FILE

# 4. Table size reporting (top 10 largest tables)
echo "  Top 10 largest tables:" >> $LOG_FILE
sudo -u postgres psql -d $PGDB -c "
SELECT
    schemaname || '.' || relname AS table_name,
    pg_size_pretty(pg_total_relation_size(schemaname || '.' || relname)) AS total_size,
    n_live_tup AS live_rows
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(schemaname || '.' || relname) DESC
LIMIT 10;
" >> $LOG_FILE 2>&1

# 5. Quick integrity check — confirm we can read from key tables.
ROWS=$(sudo -u postgres psql -d $PGDB -tAc "SELECT COUNT(*) FROM scans" 2>/dev/null || echo 'ERROR')
if [ "$ROWS" = "ERROR" ]; then
    echo "  WARNING: Integrity check failed — could not read scans table" >> $LOG_FILE
else
    echo "  Integrity: OK (scans=$ROWS)" >> $LOG_FILE
fi

echo "$(date +%Y-%m-%d\ %H:%M:%S) Database maintenance complete" >> $LOG_FILE
echo "---" >> $LOG_FILE
