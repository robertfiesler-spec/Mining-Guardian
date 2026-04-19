#!/bin/bash
# Full Learning Chain - Run Pass 1,2,3,4 in sequence
# Created 2026-04-19 for Claude fallback mode

set -e
cd /root/Mining-Gaurdian
source venv/bin/activate
export PYTHONPATH=/root/Mining-Gaurdian
export USE_CLAUDE_FALLBACK=1

LOG=/tmp/full_chain.log
echo "========================================" >> $LOG
echo "FULL LEARNING CHAIN STARTED: $(date)" >> $LOG
echo "========================================" >> $LOG

# Wait for Pass 1 (deep dive) to complete
echo "[$(date)] Waiting for deep dive to complete..." >> $LOG
while pgrep -f "daily_deep_dive.py" > /dev/null; do
    sleep 30
done
echo "[$(date)] Pass 1 (Deep Dive) COMPLETE" >> $LOG

# Run Pass 2 - Claude cohort training
echo "[$(date)] Starting Pass 2 (Claude cohort training)..." >> $LOG
python3 ai/weekly_train.py >> $LOG 2>&1
echo "[$(date)] Pass 2 COMPLETE" >> $LOG

# Run Pass 3+4 - Refinement chain (with Claude fallback for Pass 3)
echo "[$(date)] Starting Pass 3+4 (Refinement chain)..." >> $LOG
python3 ai/refinement_chain.py >> $LOG 2>&1
echo "[$(date)] Pass 3+4 COMPLETE" >> $LOG

echo "========================================" >> $LOG
echo "FULL LEARNING CHAIN FINISHED: $(date)" >> $LOG
echo "========================================" >> $LOG
