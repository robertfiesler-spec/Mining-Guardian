#!/usr/bin/env python3
"""Complete AI Research Audit - Data Flow Analysis"""

import re
import json
import sqlite3
from pathlib import Path
from collections import defaultdict

def main():
    print('=' * 100)
    print('MINING GUARDIAN — COMPLETE AI RESEARCH AUDIT')
    print('=' * 100)
    
    # All AI files
    ai_files = list(Path('/root/Mining-Gaurdian/ai').glob('*.py')) + [
        Path('/root/Mining-Gaurdian/scripts/local_llm_analyzer.py'),
        Path('/root/Mining-Gaurdian/core/mining_guardian.py')
    ]

    # Data sources to track
    knowledge_keys = [
        'llm_scan_analyses', 'daily_deep_analyses', 'cross_miner_analysis',
        'refined_insights', 'operator_rules', 'miner_fingerprints', 'miner_profiles',
        'predictions', 'known_issues', 'patterns', 'hvac_correlation',
        'fleet_summary', 'baselines', 'weekly_refinement_chain', 'prediction_accuracy',
        'facility_events'
    ]

    db_tables = [
        'miner_readings', 'chain_readings', 'pool_readings', 'miner_logs',
        'log_metrics', 'miner_restarts', 'action_audit_log', 'hvac_readings',
        'weather_readings', 'miner_hardware', 'known_dead_boards', 'scans',
        'ams_notifications', 'pending_approvals', 'miner_baselines', 'chip_readings',
        'miner_state_readings', 'miner_ams_extended', 'llm_analysis'
    ]

    reads = defaultdict(set)
    writes = defaultdict(set)

    for fpath in ai_files:
        if '.bak' in str(fpath) or '__pycache__' in str(fpath):
            continue
        if not fpath.exists():
            continue
        
        try:
            content = fpath.read_text()
            fname = fpath.name
            
            # Knowledge reads/writes
            for key in knowledge_keys:
                # Writes
                if re.search(rf"[\"']{key}[\"']\]\s*=", content) or \
                   re.search(rf"[\"']{key}[\"']\]\.append", content) or \
                   re.search(rf"[\"']{key}[\"']\]\.insert", content) or \
                   re.search(rf"setdefault\([\"']{key}", content):
                    writes[f'k.{key}'].add(fname)
                # Reads
                if re.search(rf"\.get\([\"']{key}", content) or \
                   re.search(rf"knowledge\[[\"']{key}[\"']\](?!\s*=)", content):
                    reads[f'k.{key}'].add(fname)
            
            # Database reads/writes
            for table in db_tables:
                if re.search(rf"INSERT\s+INTO\s+{table}", content, re.IGNORECASE):
                    writes[f'db.{table}'].add(fname)
                if re.search(rf"UPDATE\s+{table}", content, re.IGNORECASE):
                    writes[f'db.{table}'].add(fname)
                if re.search(rf"FROM\s+{table}", content, re.IGNORECASE):
                    reads[f'db.{table}'].add(fname)
        except Exception as e:
            pass

    # Generate matrix
    all_sources = sorted(set(reads.keys()) | set(writes.keys()))

    print('\n### DATA FLOW MATRIX ###')
    print(f"{'DATA SOURCE':<40} | {'WRITERS':<35} | {'READERS'}")
    print('-' * 120)

    orphaned = []
    underused = []

    for src in all_sources:
        w = list(writes.get(src, []))
        r = list(reads.get(src, []))
        
        w_str = ', '.join(w[:2]) + ('...' if len(w) > 2 else '')
        r_str = ', '.join(r[:3]) + ('...' if len(r) > 3 else '')
        
        # Status
        if w and not r:
            status = '❌ ORPHAN'
            orphaned.append(src)
        elif w and len(r) == 1 and list(r)[0] in w:
            status = '⚠️ SELF'
            underused.append(src)
        elif len(r) < 2 and w:
            status = '⚠️ UNDER'
            underused.append(src)
        else:
            status = '✅'
        
        print(f'{status} {src:<35} | {w_str:<35} | {r_str}')

    print('\n### ORPHANED DATA (written but never read) ###')
    for o in orphaned:
        print(f'  ❌ {o}')

    print('\n### UNDERUSED DATA (read by very few) ###')
    for u in underused:
        print(f'  ⚠️ {u}')

if __name__ == '__main__':
    main()
