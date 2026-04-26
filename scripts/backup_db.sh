#!/bin/bash
# backup_db.sh
# Backs up guardian.db, knowledge.json, config.json, .env to Mac over Tailscale SSH
# Runs every 5 minutes via cron
# Keeps 12 rolling copies (1 hour) + daily snapshots

REMOTE_DIR="/root/Mining-Guardian"
BACKUP_BASE="/Volumes/Big-Bobby-T9/Bixbit USA/Mining Guardian Backups"
MAC_USER="BigBobby"
MAC_HOST="100.103.185.53"
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
DATE=$(date +%Y-%m-%d)

# Pull files from VPS to Mac using scp
# guardian.db — rolling backup (keep last 12)
scp -q -o StrictHostKeyChecking=no \
    root@187.124.247.182:$REMOTE_DIR/guardian.db \
    "$BACKUP_BASE/db/guardian_$TIMESTAMP.db"

# Keep only the 12 most recent db backups
ls -t "$BACKUP_BASE/db/"*.db 2>/dev/null | tail -n +13 | xargs rm -f 2>/dev/null

# knowledge.json — rolling backup (keep last 12)
scp -q -o StrictHostKeyChecking=no \
    root@187.124.247.182:$REMOTE_DIR/knowledge.json \
    "$BACKUP_BASE/db/knowledge_$TIMESTAMP.json" 2>/dev/null

ls -t "$BACKUP_BASE/db/"knowledge_*.json 2>/dev/null | tail -n +13 | xargs rm -f 2>/dev/null

# config.json and .env — keep latest copy only (no rotation needed, small files)
scp -q -o StrictHostKeyChecking=no \
    root@187.124.247.182:$REMOTE_DIR/config.json \
    "$BACKUP_BASE/config/config.json" 2>/dev/null

scp -q -o StrictHostKeyChecking=no \
    root@187.124.247.182:$REMOTE_DIR/.env \
    "$BACKUP_BASE/config/.env" 2>/dev/null

# Daily snapshot — one full copy per day
if [ ! -f "$BACKUP_BASE/daily/guardian_$DATE.db" ]; then
    cp "$BACKUP_BASE/db/guardian_$TIMESTAMP.db" \
       "$BACKUP_BASE/daily/guardian_$DATE.db" 2>/dev/null
fi

# Keep only the last 30 daily snapshots
ls -t "$BACKUP_BASE/daily/"*.db 2>/dev/null | tail -n +31 | xargs rm -f 2>/dev/null

echo "$(date): Backup complete" >> /tmp/backup_db.log
