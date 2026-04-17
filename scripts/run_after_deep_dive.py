#!/usr/bin/env python3
"""
Watch for deep dive completion, then run midnight cron jobs:
1. weekly_train.py (Claude cohort training)
2. refinement_chain.py (Qwen reflection + Claude merge)
"""
import os
import sys
import time
import subprocess
from pathlib import Path
from datetime import datetime

sys.path.insert(0, '/root/Mining-Gaurdian')

WIP_DIR = Path('/root/Mining-Gaurdian/daily_deep_dive_wip/2026-04-16')
SYNTHESIS_FILE = WIP_DIR / 'fleet_synthesis.json'

def log(msg):
    print(f'[{datetime.now():%H:%M:%S}] {msg}', flush=True)

def send_slack(msg):
    try:
        from slack_sdk import WebClient
        token = None
        with open('/root/Mining-Gaurdian/.env') as f:
            for line in f:
                if line.startswith('SLACK_BOT_TOKEN='):
                    token = line.strip().split('=', 1)[1]
                    break
        if token:
            client = WebClient(token=token)
            client.chat_postMessage(channel='#mg-ai-reports', text=msg)
    except Exception as e:
        log(f'Slack error: {e}')

def run_job(name, script_path):
    log(f'Starting {name}...')
    send_slack(f'🚀 *Starting {name}*')
    
    start = time.time()
    result = subprocess.run(
        ['python3', script_path],
        cwd='/root/Mining-Gaurdian',
        capture_output=True,
        text=True,
        timeout=7200  # 2 hour timeout
    )
    duration = time.time() - start
    
    if result.returncode == 0:
        log(f'{name} completed in {duration:.0f}s')
        send_slack(f'✅ *{name} completed* in {duration/60:.1f} min')
        return True
    else:
        log(f'{name} failed: {result.stderr[-500:]}')
        send_slack(f'❌ *{name} failed*: {result.stderr[-200:]}')
        return False

def main():
    log('Waiting for deep dive to complete (watching for fleet_synthesis.json)...')
    
    while True:
        if SYNTHESIS_FILE.exists():
            log('Fleet synthesis found! Deep dive complete.')
            send_slack('🎉 *Deep Dive Complete!* Starting midnight training jobs...')
            break
        time.sleep(60)
    
    # Run midnight jobs in order
    os.chdir('/root/Mining-Gaurdian')
    os.environ['PATH'] = '/root/Mining-Gaurdian/venv/bin:' + os.environ.get('PATH', '')
    
    # 1. Weekly training
    run_job('Weekly Training (Claude)', '/root/Mining-Gaurdian/ai/weekly_train.py')
    
    # 2. Refinement chain
    run_job('Refinement Chain', '/root/Mining-Gaurdian/ai/refinement_chain.py')
    
    send_slack('✅ *All midnight jobs complete!* Knowledge base updated.')
    log('All done!')

if __name__ == '__main__':
    main()
