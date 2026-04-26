#!/usr/bin/env python3
"""
Deep Dive Progress Monitor - Posts to Slack every 15 min while deep dive runs
"""
import os, sys, time, glob, subprocess
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from slack_sdk import WebClient

# Force unbuffered output
sys.stdout = sys.stderr = open('/tmp/progress_monitor.log', 'w', buffering=1)

load_dotenv('/root/Mining-Guardian/.env')
SLACK_TOKEN = os.getenv('SLACK_BOT_TOKEN')
CHANNEL = '#mg-ai-reports'
INTERVAL = 900
WIP_BASE = Path('/root/Mining-Guardian/daily_deep_dive_wip')

def get_status():
    result = subprocess.run(['pgrep', '-f', 'daily_deep_dive.py'], capture_output=True, text=True)
    is_running = result.returncode == 0
    today = datetime.now().strftime('%Y-%m-%d')
    wip_dir = WIP_BASE / today
    completed = len(list(wip_dir.glob('miner_*.json'))) if wip_dir.exists() else 0
    has_synth = (wip_dir / 'fleet_synthesis.json').exists() if wip_dir.exists() else False
    total = 39
    logs = glob.glob('/tmp/manual_deep_dive_*.log') + ['/tmp/daily_deep_dive.log']
    for lf in logs:
        try:
            with open(lf) as f:
                for line in f:
                    if 'Online miners in latest scan:' in line:
                        total = int(line.split(':')[-1].strip())
        except: pass
    return is_running, completed, total, has_synth

def make_bar(pct):
    filled = int(pct / 5)
    return '\u2588' * filled + '\u2591' * (20 - filled)

def post_slack(msg):
    client = WebClient(token=SLACK_TOKEN)
    resp = client.chat_postMessage(channel=CHANNEL, text=msg)
    return resp.get('ok', False)

def main():
    print(f'Progress monitor started at {datetime.now()}')
    print(f'Token loaded: {bool(SLACK_TOKEN)}')
    
    # Post first update immediately
    running, done, total, synth = get_status()
    print(f'Initial status: running={running}, done={done}, total={total}, synth={synth}')
    
    if not running:
        print('Deep dive not running - exiting immediately')
        return
    
    pct = (done / total * 100) if total else 0
    remaining_mins = (total - done) * 9
    hrs, mins = divmod(remaining_mins, 60)
    bar = make_bar(pct)
    msg = f':brain: *Deep Dive Progress*\n`[{bar}]` {pct:.0f}%\nMiners: {done}/{total} analyzed | ETA: ~{hrs}h {mins}m'
    print(f'Posting first update: {done}/{total}')
    
    try:
        ok = post_slack(msg)
        print(f'Slack post result: {ok}')
    except Exception as e:
        print(f'Slack error: {e}')
    
    # Now loop
    while True:
        print(f'Sleeping {INTERVAL}s until next update...')
        time.sleep(INTERVAL)
        
        try:
            running, done, total, synth = get_status()
            print(f'Status check: running={running}, done={done}/{total}')
            
            if not running:
                if synth:
                    post_slack(':white_check_mark: *Daily Deep Dive Complete* - all miners analyzed + fleet synthesis done.')
                print('Deep dive finished - exiting')
                break
            
            pct = (done / total * 100) if total else 0
            remaining_mins = (total - done) * 9
            hrs, mins = divmod(remaining_mins, 60)
            bar = make_bar(pct)
            msg = f':brain: *Deep Dive Progress*\n`[{bar}]` {pct:.0f}%\nMiners: {done}/{total} analyzed | ETA: ~{hrs}h {mins}m'
            
            ok = post_slack(msg)
            print(f'Posted update: {done}/{total}, ok={ok}')
            
        except Exception as e:
            print(f'Error in loop: {e}')

if __name__ == '__main__':
    main()
