#!/usr/bin/env python3
"""
Daily log collection script for cron.
Runs at 1pm daily to collect fresh logs from all miners.
"""
import sys
sys.path.insert(0, '/root/Mining-Gaurdian')

from core.mining_guardian import MiningGuardian, GuardianConfig

def main():
    config = GuardianConfig.from_file('/root/Mining-Gaurdian/config.json')
    mg = MiningGuardian(config)
    print('Starting daily log collection...')
    mg.collect_logs()
    print('Daily log collection complete.')

if __name__ == '__main__':
    main()
