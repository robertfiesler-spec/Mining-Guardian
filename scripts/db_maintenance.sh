#!/bin/bash
# Database Maintenance Script
# Runs daily to keep SQLite healthy
# Added: April 21, 2026

set -e

DB_PATH="/root/Mining-Gaurdian/guardian.db"
LOG_FILE="/var/log/db_maintenance.log"

echo "$(date +%Y-%m-%d\ %H:%M:%S) Starting database maintenance..." >> $LOG_FILE

# 1. Force WAL checkpoint - flushes write-ahead log to main database
echo "  Checkpointing WAL..." >> $LOG_FILE
sqlite3 $DB_PATH "PRAGMA wal_checkpoint(TRUNCATE);" >> $LOG_FILE 2>&1

# 2. Incremental vacuum - reclaims free space without full rebuild
echo "  Running incremental vacuum..." >> $LOG_FILE
sqlite3 $DB_PATH "PRAGMA incremental_vacuum(1000);" >> $LOG_FILE 2>&1

# 3. Analyze tables - updates query planner statistics
echo "  Analyzing tables..." >> $LOG_FILE
sqlite3 $DB_PATH "ANALYZE;" >> $LOG_FILE 2>&1

# 4. Integrity check (quick version)
echo "  Quick integrity check..." >> $LOG_FILE
INTEGRITY=$(sqlite3 $DB_PATH "PRAGMA quick_check;")
if [ "$INTEGRITY" != "ok" ]; then
    echo "  WARNING: Integrity check failed: $INTEGRITY" >> $LOG_FILE
else
    echo "  Integrity: OK" >> $LOG_FILE
fi

# 5. Report WAL size
WAL_SIZE=$(ls -lh ${DB_PATH}-wal 2>/dev/null | awk "{print \$5}" || echo "0")
echo "  WAL file size after checkpoint: $WAL_SIZE" >> $LOG_FILE

# 6. Report DB size
DB_SIZE=$(ls -lh $DB_PATH | awk "{print \$5}")
echo "  Database size: $DB_SIZE" >> $LOG_FILE

echo "$(date +%Y-%m-%d\ %H:%M:%S) Database maintenance complete" >> $LOG_FILE
echo "---" >> $LOG_FILE
