#!/usr/bin/env python3
"""
Daily log collection script for cron.
Runs at 1pm daily to collect fresh logs from all miners.
The retry pass runs automatically for any miners that fail on first attempt.
"""
import sys
import logging
sys.path.insert(0, '/root/Mining-Gaurdian')

from core.mining_guardian import MiningGuardian, GuardianConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    logger.info('=== DAILY LOG COLLECTION START ===')
    
    config = GuardianConfig.from_file('/root/Mining-Gaurdian/config.json')
    mg = MiningGuardian(config)
    
    # First, we need to get the current list of miners from AMS
    logger.info('Fetching current miner list from AMS...')
    try:
        miners = mg.ams.get_miners()
        online_miners = [m for m in miners if m.get('status') == 'online']
        logger.info(f'Found {len(miners)} total miners, {len(online_miners)} online')
    except Exception as e:
        logger.error(f'Failed to fetch miners from AMS: {e}')
        return
    
    # Run the log collection (includes retry pass for failed miners)
    logger.info('Starting log collection with retry pass...')
    mg.collect_logs(miners=miners, issues=[])
    
    logger.info('=== DAILY LOG COLLECTION COMPLETE ===')

if __name__ == '__main__':
    main()
