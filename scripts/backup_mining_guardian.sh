#!/bin/zsh
# backup_mining_guardian.sh
# Pulls critical Mining Guardian files from VPS to Big-Bobby-T9
# Runs every 5 minutes via cron on Mac
# Keeps 12 rolling copies (1 hour window) + 1 daily snapshot per day

VPS="root@187.124.247.182"
REMOTE="/root/Mining-Guardian"
BACKUP_BASE="/Volumes/Big-Bobby-T9/Bixbit USA/Mining Guardian Backups"
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
DATE=$(date +%Y-%m-%d)
LOG="/tmp/mining_guardian_backup.log"

# Check drive is mounted
if [ ! -d "$BACKUP_BASE" ]; then
    echo "$(date): ERROR — Big-Bobby-T9 not mounted, skipping backup" >> "$LOG"
    exit 1
fi

# ── guardian.db — rolling 12 copies ───────────────────────────────────────
scp -q -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
    "$VPS:$REMOTE/guardian.db" \
    "$BACKUP_BASE/db/guardian_$TIMESTAMP.db" 2>/dev/null

if [ $? -eq 0 ]; then
    # Keep only the 12 most recent
    ls -t "$BACKUP_BASE/db/"guardian_*.db 2>/dev/null | tail -n +13 | xargs rm -f 2>/dev/null

    # Daily snapshot — one per day, keep 30 days
    if [ ! -f "$BACKUP_BASE/daily/guardian_$DATE.db" ]; then
        cp "$BACKUP_BASE/db/guardian_$TIMESTAMP.db" \
           "$BACKUP_BASE/daily/guardian_$DATE.db"
        ls -t "$BACKUP_BASE/daily/"*.db 2>/dev/null | tail -n +31 | xargs rm -f 2>/dev/null
    fi
    echo "$(date): guardian.db OK" >> "$LOG"
else
    echo "$(date): ERROR — guardian.db copy failed" >> "$LOG"
fi

# ── knowledge.json — rolling 12 copies ────────────────────────────────────
scp -q -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
    "$VPS:$REMOTE/knowledge.json" \
    "$BACKUP_BASE/db/knowledge_$TIMESTAMP.json" 2>/dev/null

if [ $? -eq 0 ]; then
    ls -t "$BACKUP_BASE/db/"knowledge_*.json 2>/dev/null | tail -n +13 | xargs rm -f 2>/dev/null
    echo "$(date): knowledge.json OK" >> "$LOG"
fi

# ── config.json — latest only (has profile map + AMS settings) ────────────
scp -q -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
    "$VPS:$REMOTE/config.json" \
    "$BACKUP_BASE/config/config.json" 2>/dev/null
echo "$(date): config.json OK" >> "$LOG"

# ── .env — latest only (credentials) ──────────────────────────────────────
scp -q -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
    "$VPS:$REMOTE/.env" \
    "$BACKUP_BASE/config/.env" 2>/dev/null
echo "$(date): .env OK" >> "$LOG"

# Trim log to last 200 lines
tail -200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
