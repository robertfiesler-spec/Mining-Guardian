#!/usr/bin/env python3
"""Component-by-component AI audit"""
from pathlib import Path
import re

print('=' * 100)
print('SECTION 6: COMPONENT-BY-COMPONENT AUDIT')
print('=' * 100)

files = {
    'predictor.py': 'Pre-failure signal detection',
    'outcome_checker.py': 'Validates restart outcomes',
    'confidence_scorer.py': 'Sets action confidence levels',
    'action_diversity.py': 'Recommends varied actions',
    'fingerprint_builder.py': 'Builds miner behavioral profiles',
    'hvac_correlator.py': 'Correlates HVAC with failures',
    'insight_manager.py': 'Manages refined insights',
    'daily_deep_dive.py': 'Daily per-miner deep analysis',
    'train_cohort.py': 'Weekly Claude training',
    'refinement_chain.py': '4-pass knowledge refinement',
    'knowledge_manager.py': 'Pattern/issue extraction',
}

for fname, desc in files.items():
    fpath = Path(f'/root/Mining-Gaurdian/ai/{fname}')
    
    if not fpath.exists():
        print(f'\n### {fname} — FILE NOT FOUND ###')
        continue
    
    content = fpath.read_text()
    
    # Find what it reads
    reads_k = set(re.findall(r"\.get\(['\"](\w+)['\"]", content))
    writes_k = set()
    # Find writes (more patterns)
    writes_k.update(re.findall(r"\['\"](\w+)['\"]\]\s*=", content))
    writes_k.update(re.findall(r"\['\"](\w+)['\"]\]\.append", content))
    writes_k.update(re.findall(r"\['\"](\w+)['\"]\]\.insert", content))
    
    reads_db = set(re.findall(r"FROM\s+(\w+)", content, re.IGNORECASE))
    writes_db = set(re.findall(r"INSERT\s+INTO\s+(\w+)", content, re.IGNORECASE))
    writes_db.update(re.findall(r"UPDATE\s+(\w+)\s+SET", content, re.IGNORECASE))
    
    # Filter to relevant knowledge keys
    k_keys = {'llm_scan_analyses', 'predictions', 'miner_fingerprints', 'operator_rules',
              'patterns', 'known_issues', 'refined_insights', 'cross_miner_analysis',
              'daily_deep_analyses', 'hvac_correlation', 'prediction_accuracy',
              'facility_events', 'miner_profiles', 'fleet_summary', 'weekly_refinement_chain'}
    
    reads_k = reads_k & k_keys
    writes_k = writes_k & k_keys
    
    print(f'\n### {fname} ###')
    print(f'Purpose: {desc}')
    print(f'Reads knowledge: {sorted(reads_k) if reads_k else "NONE"}')
    print(f'Writes knowledge: {sorted(writes_k) if writes_k else "NONE"}')
    print(f'Reads DB: {sorted(reads_db)[:5] if reads_db else "NONE"}')
    print(f'Writes DB: {sorted(writes_db)[:4] if writes_db else "NONE"}')

# Also check local_llm_analyzer
fpath = Path('/root/Mining-Gaurdian/scripts/local_llm_analyzer.py')
if fpath.exists():
    content = fpath.read_text()
    reads_k = set(re.findall(r"\.get\(['\"](\w+)['\"]", content)) & k_keys
    writes_k = set()
    writes_k.update(re.findall(r"\['\"](\w+)['\"]\]\s*=", content))
    writes_k.update(re.findall(r"\['\"](\w+)['\"]\]\.append", content))
    writes_k = writes_k & k_keys
    
    print(f'\n### local_llm_analyzer.py ###')
    print(f'Purpose: Hourly Qwen analysis')
    print(f'Reads knowledge: {sorted(reads_k) if reads_k else "NONE"}')
    print(f'Writes knowledge: {sorted(writes_k) if writes_k else "NONE"}')
