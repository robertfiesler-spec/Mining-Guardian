#!/usr/bin/env python3
"""
Direct Miner Log Collection — bypasses AMS entirely.
"""
import sys, os, json, sqlite3, tarfile, io, logging, time, requests
from requests.auth import HTTPDigestAuth
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, List, Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler('/tmp/direct_log_collection.log')]
)
logger = logging.getLogger(__name__)

DB_PATH = '/root/Mining-Gaurdian/guardian.db'
TIMEOUT = 60
MAX_WORKERS = 5

def get_online_miners() -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('SELECT id FROM scans ORDER BY id DESC LIMIT 1')
    row = cur.fetchone()
    if not row:
        return []
    scan_id = row['id']
    
    cur.execute('''
        SELECT DISTINCT miner_id, ip
        FROM miner_state_readings
        WHERE scan_id = ? AND ip IS NOT NULL AND hashrate_medium > 0
    ''', (scan_id,))
    miners = [dict(row) for row in cur.fetchall()]
    conn.close()
    logger.info(f'Found {len(miners)} online miners in scan {scan_id}')
    return miners

def download_miner_log(miner: Dict, target_date: date) -> Tuple[str, bool, str, Optional[bytes]]:
    miner_id = miner['miner_id']
    ip = miner['ip']
    auth = HTTPDigestAuth('root', 'root')
    date_path = f'/{target_date.strftime("%Y-%m")}/{target_date.strftime("%d")}'
    
    try:
        resp = requests.post(f'http://{ip}/cgi-bin/create_log_backup.cgi',
                             json=[date_path], auth=auth, timeout=TIMEOUT,
                             headers={'Content-Type': 'application/json'})
        if resp.status_code != 200:
            return (miner_id, False, f'create:{resp.status_code}', None)
        
        data = resp.json()
        if data.get('stats') != 'success':
            return (miner_id, False, f'create failed', None)
        
        filename = data.get('msg')
        if not filename:
            return (miner_id, False, 'no filename', None)
        
        resp = requests.get(f'http://{ip}/log/{filename}', auth=auth, timeout=TIMEOUT)
        if resp.status_code != 200:
            return (miner_id, False, f'download:{resp.status_code}', None)
        if len(resp.content) < 100:
            return (miner_id, False, f'{len(resp.content)}b', None)
        
        return (miner_id, True, f'{len(resp.content):,}b', resp.content)
    except requests.exceptions.Timeout:
        return (miner_id, False, 'timeout', None)
    except requests.exceptions.ConnectionError:
        return (miner_id, False, 'conn err', None)
    except Exception as e:
        return (miner_id, False, str(e)[:30], None)

def extract_and_store_log(miner_id: str, ip: str, log_bytes: bytes, target_date: date) -> bool:
    try:
        with tarfile.open(fileobj=io.BytesIO(log_bytes), mode='r:bz2') as tar:
            miner_log = None
            log_file = None
            for member in tar.getmembers():
                if member.name.endswith('miner.log'):
                    f = tar.extractfile(member)
                    if f:
                        miner_log = f.read().decode('utf-8', errors='replace')
                        log_file = member.name
                        break
            if not miner_log:
                return False
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # Check if we have this log already today
        cur.execute('SELECT id FROM miner_logs WHERE miner_id = ? AND DATE(collected_at) = ?',
                    (miner_id, target_date.isoformat()))
        existing = cur.fetchone()
        
        if existing:
            cur.execute('UPDATE miner_logs SET content = ?, collected_at = ? WHERE id = ?',
                        (miner_log, datetime.now().isoformat(), existing[0]))
        else:
            cur.execute('''INSERT INTO miner_logs (collected_at, miner_id, model, health_status, log_file, content)
                           VALUES (?, ?, ?, ?, ?, ?)''',
                        (datetime.now().isoformat(), miner_id, 'direct', 'collected', log_file or 'miner.log', miner_log))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f'Miner {miner_id}: {e}')
        return False

def send_slack_report(collected: int, failed: int, total: int, failures: List[str], duration: float):
    try:
        from slack_sdk import WebClient
        token = None
        with open('/root/Mining-Gaurdian/.env') as f:
            for line in f:
                if line.startswith('SLACK_BOT_TOKEN='):
                    token = line.strip().split('=', 1)[1]
                    break
        if not token:
            return
        client = WebClient(token=token)
        emoji = ':white_check_mark:' if failed == 0 else ':warning:'
        msg = f'{emoji} *Direct Log Collection Complete*\n• Collected: {collected}/{total}\n• Failed: {failed}\n• Duration: {duration:.1f}s'
        if failures and len(failures) <= 10:
            msg += '\n\nFailures:\n' + '\n'.join(f'• {f}' for f in failures)
        elif failures:
            msg += f'\n\n_{len(failures)} failures - see log_'
        client.chat_postMessage(channel='#mg-logs', text=msg)
    except Exception as e:
        logger.warning(f'Slack: {e}')

def main():
    start = time.time()
    target_date = date.today()
    logger.info(f'=== DIRECT LOG COLLECTION START — {target_date} ===')
    
    miners = get_online_miners()
    if not miners:
        logger.error('No online miners')
        return
    
    collected, failed, failures = 0, 0, []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(download_miner_log, m, target_date): m for m in miners}
        for future in as_completed(futures):
            miner = futures[future]
            miner_id, success, msg, log_bytes = future.result()
            if success and log_bytes:
                if extract_and_store_log(miner_id, miner['ip'], log_bytes, target_date):
                    collected += 1
                    logger.info(f'✓ {miner_id} ({miner["ip"]}): {msg}')
                else:
                    failed += 1
                    failures.append(f'{miner_id}: extract fail')
            else:
                failed += 1
                failures.append(f'{miner_id} ({miner["ip"]}): {msg}')
                logger.warning(f'✗ {miner_id} ({miner["ip"]}): {msg}')
    
    duration = time.time() - start
    logger.info(f'=== COMPLETE: {collected}/{len(miners)} in {duration:.1f}s ===')
    send_slack_report(collected, failed, len(miners), failures, duration)

if __name__ == '__main__':
    main()
