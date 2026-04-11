#!/usr/bin/env python3
"""Complete AI System Audit for Mining Guardian"""

import json
import os
import re
import sqlite3
from pathlib import Path
from collections import defaultdict

def main():
    print('=' * 80)
    print('MINING GUARDIAN — COMPLETE AI SYSTEM AUDIT')
    print('=' * 80)

    # Load knowledge to see all data structures
    k = json.load(open('/root/Mining-Gaurdian/knowledge.json'))

    print('\n' + '=' * 80)
    print('SECTION 1: ALL DATA STRUCTURES IN KNOWLEDGE.JSON')
    print('=' * 80)

    for key in sorted(k.keys()):
        val = k[key]
        if isinstance(val, dict):
            print(f'  {key}: dict with {len(val)} entries')
        elif isinstance(val, list):
            print(f'  {key}: list with {len(val)} items')
        else:
            print(f'  {key}: {type(val).__name__}')

    print('\n' + '=' * 80)
    print('SECTION 2: WHO WRITES AND READS EACH STRUCTURE')
    print('=' * 80)

    # Key data structures to track
    structures = [
        'llm_scan_analyses', 'daily_deep_analyses', 'cross_miner_analysis',
        'refined_insights', 'operator_rules', 'miner_fingerprints',
        'predictions', 'known_issues', 'patterns', 'hvac_correlation',
        'miner_profiles', 'fleet_summary', 'baselines', 'weekly_refinement_chain'
    ]

    ai_files = list(Path('/root/Mining-Gaurdian/ai').glob('*.py'))
    ai_files += list(Path('/root/Mining-Gaurdian/scripts').glob('*.py'))
    ai_files += [Path('/root/Mining-Gaurdian/core/mining_guardian.py')]

    writers = defaultdict(list)
    readers = defaultdict(list)

    for f in ai_files:
        if '.bak' in str(f) or '__pycache__' in str(f):
            continue
        try:
            content = f.read_text()
            fname = f.name
            for struct in structures:
                # Check for writes (assignment, append, insert, setdefault)
                write_patterns = [
                    rf"\['{struct}'\]\s*=",
                    rf'\["{struct}"\]\s*=',
                    rf"'{struct}'\]\.append",
                    rf'"{struct}"\]\.append',
                    rf"'{struct}'\]\.insert",
                    rf'"{struct}"\]\.insert',
                    rf"setdefault\('{struct}'",
                    rf'setdefault\("{struct}"',
                ]
                for pat in write_patterns:
                    if re.search(pat, content):
                        if fname not in writers[struct]:
                            writers[struct].append(fname)
                        break
                
                # Check for reads (get, direct access without assignment)
                read_patterns = [
                    rf"\.get\('{struct}'",
                    rf'\.get\("{struct}"',
                    rf"knowledge\['{struct}'\](?!\s*=)",
                    rf'knowledge\["{struct}"\](?!\s*=)',
                ]
                for pat in read_patterns:
                    if re.search(pat, content):
                        if fname not in readers[struct]:
                            readers[struct].append(fname)
                        break
        except Exception as e:
            pass

    for struct in structures:
        w = writers.get(struct, [])
        r = readers.get(struct, [])
        status = "✅" if (w and r) else "❌" if (w and not r) else "⚠️"
        print(f'\n{status} {struct}:')
        print(f'   WRITES: {w if w else ["NOBODY"]}')
        print(f'   READS:  {r if r else ["NOBODY"]}')

    print('\n' + '=' * 80)
    print('SECTION 3: DATABASE TABLES')
    print('=' * 80)

    conn = sqlite3.connect('/root/Mining-Gaurdian/guardian.db')
    tables = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

    for t in sorted(tables):
        count = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
        print(f'  {t}: {count:,} rows')

    print('\n' + '=' * 80)
    print('SECTION 4: AI COMPONENT INVENTORY')
    print('=' * 80)
    
    components = {
        'outcome_checker.py': 'Evaluates restart success/failure, updates miner_restarts table',
        'confidence_scorer.py': 'Calculates confidence score for each action recommendation',
        'fingerprint_builder.py': 'Builds per-miner behavioral profiles',
        'hvac_correlator.py': 'Correlates fleet issues with HVAC/facility conditions',
        'predictor.py': 'Runs 12 pre-failure signals, generates predictions',
        'action_diversity.py': 'Generates non-restart actions (profile changes, eco mode)',
        'local_llm_analyzer.py': 'Hourly Qwen analysis of each scan',
        'daily_deep_dive.py': 'Daily Qwen deep analysis of every miner',
        'train_cohort.py': 'Weekly Claude training (cohort-based)',
        'refinement_chain.py': 'Post-training Qwen review of Claude output',
        'insight_manager.py': 'Manages refined insights from training',
        'combine_knowledge.py': 'Merges knowledge from multiple sites',
        'claude_log_comparison.py': 'Pre/post restart log analysis via Claude',
    }
    
    for comp, desc in components.items():
        print(f'  {comp}')
        print(f'    {desc}')

    conn.close()
    print('\n' + '=' * 80)
    print('AUDIT COMPLETE')
    print('=' * 80)

if __name__ == '__main__':
    main()
