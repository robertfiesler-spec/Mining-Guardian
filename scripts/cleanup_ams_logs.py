#!/usr/bin/env python3
"""
Cleanup ALL AMS log files daily.

Since logs are stored in guardian.db after download, we don't need to keep
them in AMS. This prevents "too many log files" errors and keeps AMS clean.

CRON SCHEDULE:
0 10 * * *  # 10am daily - clean before 1pm log collection

OPERATOR REQUIREMENT (April 12 2026):
"Delete all files not just failed attempts. For clean up and house cleaning 
overall don't let it clutter. We store the logs in the db anyway."
"""
import sys
import time
import logging

sys.path.insert(0, '/root/Mining-Guardian')

from core.mining_guardian import AMSClient, GuardianConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def cleanup_all_logs():
    """Delete ALL log files from AMS for all miners."""
    
    logger.info('=== AMS LOG CLEANUP START ===')
    
    config = GuardianConfig.from_file('/root/Mining-Guardian/config.json')
    ams = AMSClient(config)
    token = ams._ensure_token()
    
    # Get all miners
    try:
        miners = ams.get_miners()
        logger.info(f'Found {len(miners)} miners')
    except Exception as e:
        logger.error(f'Failed to get miners: {e}')
        return
    
    total_deleted = 0
    miners_cleaned = 0
    errors = 0
    
    for miner in miners:
        miner_id = miner.get('id')
        if not miner_id:
            continue
        
        try:
            logs = ams.get_log_list(miner_id)
        except Exception as e:
            logger.warning(f'Failed to get logs for miner {miner_id}: {e}')
            errors += 1
            continue
        
        if not logs:
            continue
        
        deleted = 0
        for log_entry in logs:
            log_id = log_entry.get('id')
            if not log_id:
                continue
            
            try:
                resp = ams.session.delete(
                    f'{ams.base_url}/log/delete',
                    json={'deviceID': miner_id, 'id': log_id},
                    headers={'Authorization': f'Bearer {token}'},
                    timeout=10
                )
                if resp.status_code == 200:
                    deleted += 1
                else:
                    errors += 1
            except Exception:
                errors += 1
            
            # Small delay to avoid hammering API
            time.sleep(0.05)
        
        if deleted > 0:
            logger.info(f'Miner {miner_id}: deleted {deleted} logs')
            total_deleted += deleted
            miners_cleaned += 1
    
    logger.info(f'CLEANUP COMPLETE: {total_deleted} logs deleted from {miners_cleaned} miners, {errors} errors')
    logger.info('=== AMS LOG CLEANUP END ===')


if __name__ == '__main__':
    cleanup_all_logs()
