#!/usr/bin/env python3
"""
Watch for deep dive completion and send full report to Bobby's DM
"""
import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from slack_sdk import WebClient

load_dotenv('/root/Mining-Guardian/.env')
SLACK_TOKEN = os.getenv('SLACK_BOT_TOKEN')
BOBBY_USER_ID = 'U07AGTT8CLD'
WIP_DIR = Path('/root/Mining-Guardian/daily_deep_dive_wip/2026-04-16')
KNOWLEDGE_FILE = Path('/root/Mining-Guardian/knowledge.json')

def check_complete():
    """Check if fleet synthesis is done"""
    synth_file = WIP_DIR / 'fleet_synthesis.json'
    return synth_file.exists()

def build_report():
    """Build the full report from knowledge.json and synthesis"""
    synth_file = WIP_DIR / 'fleet_synthesis.json'
    
    # Load synthesis
    with open(synth_file) as f:
        synthesis = json.load(f)
    
    # Load knowledge
    with open(KNOWLEDGE_FILE) as f:
        knowledge = json.load(f)
    
    # Count real analyses (not skipped)
    miner_files = list(WIP_DIR.glob('miner_*.json'))
    real_count = sum(1 for f in miner_files if f.stat().st_size > 100)
    
    # Build report
    report = f":brain: *Daily Deep Dive Complete — {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n"
    report += f"*Miners Analyzed:* {real_count} (with full Qwen analysis)\n"
    report += f"*Total Fleet:* {len(miner_files)} miners\n\n"
    
    # Add synthesis content
    report += "*=== FLEET SYNTHESIS ===*\n"
    if isinstance(synthesis, dict):
        synth_text = synthesis.get('analysis', synthesis.get('content', str(synthesis)))
    else:
        synth_text = str(synthesis)
    
    # Truncate if too long for Slack (4000 char limit per message)
    if len(synth_text) > 3500:
        synth_text = synth_text[:3500] + "\n\n_(truncated - full report in knowledge.json)_"
    
    report += synth_text + "\n\n"
    
    # Add key learnings from knowledge
    report += "*=== KEY LEARNINGS ===*\n"
    
    insights = knowledge.get('refined_insights', [])
    if insights:
        report += f"*Insights:* {len(insights)} total\n"
        for i in insights[-3:]:  # Last 3
            report += f"• {i[:200]}...\n" if len(i) > 200 else f"• {i}\n"
    
    patterns = knowledge.get('patterns', [])
    if patterns:
        report += f"\n*Patterns:* {len(patterns)} identified\n"
    
    known_issues = knowledge.get('known_issues', [])
    if known_issues:
        report += f"*Known Issues:* {len(known_issues)} tracked\n"
    
    return report

def send_dm(message):
    """Send DM to Bobby"""
    client = WebClient(token=SLACK_TOKEN)
    
    # Open DM channel
    resp = client.conversations_open(users=[BOBBY_USER_ID])
    channel = resp['channel']['id']
    
    # Send message (split if too long)
    if len(message) > 4000:
        parts = [message[i:i+3900] for i in range(0, len(message), 3900)]
        for part in parts:
            client.chat_postMessage(channel=channel, text=part)
    else:
        client.chat_postMessage(channel=channel, text=message)
    
    return True

def main():
    print(f'Watching for deep dive completion...')
    
    while True:
        if check_complete():
            print('Fleet synthesis found! Building report...')
            try:
                report = build_report()
                print(f'Sending report ({len(report)} chars) to Bobby DM...')
                send_dm(report)
                print('Report sent!')
                
                # Also post to #mg-ai-reports
                client = WebClient(token=SLACK_TOKEN)
                client.chat_postMessage(
                    channel='#mg-ai-reports',
                    text=':white_check_mark: *Daily Deep Dive Complete!* Full report sent to Bobby via DM.'
                )
                break
            except Exception as e:
                print(f'Error: {e}')
                break
        else:
            print(f'[{datetime.now():%H:%M:%S}] Still waiting...')
            time.sleep(60)

if __name__ == '__main__':
    main()
