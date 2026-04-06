#!/usr/bin/env bash
# daily_backup.sh — Mining Guardian daily backup
# Runs at 2pm CDT via cron
# Backs up: guardian.db, config.json, .env, knowledge.json, miner_specs.json
# Keeps 7 days of backups, auto-deletes older ones

BACKUP_ROOT="/root/Mining-Gaurdian/backups"
TODAY=$(date +%Y-%m-%d)
BACKUP_DIR="$BACKUP_ROOT/$TODAY"
SRC="/root/Mining-Gaurdian"

mkdir -p "$BACKUP_DIR"

echo "$(date) — Starting daily backup to $BACKUP_DIR"

# Copy critical files
cp "$SRC/config.json" "$BACKUP_DIR/config.json" 2>/dev/null
cp "$SRC/.env" "$BACKUP_DIR/dot-env" 2>/dev/null
cp "$SRC/knowledge.json" "$BACKUP_DIR/knowledge.json" 2>/dev/null
cp "$SRC/knowledge_backup.json" "$BACKUP_DIR/knowledge_backup.json" 2>/dev/null
cp "$SRC/miner_specs.json" "$BACKUP_DIR/miner_specs.json" 2>/dev/null

# SQLite safe backup (copy while WAL is active)
cp "$SRC/guardian.db" "$BACKUP_DIR/guardian.db" 2>/dev/null
cp "$SRC/guardian.db-wal" "$BACKUP_DIR/guardian.db-wal" 2>/dev/null
cp "$SRC/guardian.db-shm" "$BACKUP_DIR/guardian.db-shm" 2>/dev/null

# Compress the DB to save space
gzip -1 -f "$BACKUP_DIR/guardian.db" 2>/dev/null

# Delete backups older than 7 days
find "$BACKUP_ROOT" -maxdepth 1 -type d -mtime +7 -exec rm -rf {} \; 2>/dev/null

# Summary
TOTAL=$(du -sh "$BACKUP_DIR" 2>/dev/null | awk '{print $1}')
echo "$(date) — Backup complete: $BACKUP_DIR ($TOTAL)"
echo "$(date) — Files:"
ls -lh "$BACKUP_DIR/"
