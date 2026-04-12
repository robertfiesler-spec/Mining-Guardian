"""Ingest the AH3880 log 1.pdf extraction and run dual-model diagnosis.

This is a SINGLE-SNAPSHOT diagnostic — there's no pre/post pair, just one
big 16-hour log window from a sick miner. Used to demo the dual-model
analysis on a real Auradine miner with a real fault.

Saves the extracted text into miner_logs under label='diagnostic' for
miner_id='auradine_28' (192.168.188.28), then calls Qwen + Claude with
the same prompt structure used for restart comparisons.
"""
import os, sys, sqlite3, time
from datetime import datetime

os.chdir('/root/Mining-Gaurdian')
sys.path.insert(0, '/root/Mining-Gaurdian/core')
sys.path.insert(0, '/root/Mining-Gaurdian/ai')

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

MINER_ID = 'auradine_28'
IP = '192.168.188.28'
MODEL = 'Auradine AH3880'
LOG_PATH = '/tmp/log1_full.txt'

print('=' * 70)
print('AH3880 SINGLE-SNAPSHOT DIAGNOSIS')
print(f'Miner: {MINER_ID} at {IP} ({MODEL})')
print(f'Log:   {LOG_PATH}')
print('=' * 70)

# Read full log
with open(LOG_PATH) as f:
    log_content = f.read()
print(f'Loaded {len(log_content):,} bytes / {log_content.count(chr(10)):,} lines')

# Quick fact sheet for the LLM (since 12 MB is way over Claude's 200K context)
import re
total_lines = log_content.count(chr(10))
dvfs_alarms = log_content.count('DVFS ALARM')
power_state_alarms = log_content.count('PowerState ALARM')
board3_zero_lines = log_content.count('3:0.0000')

# Extract first and last timestamps
first_ts_match = re.search(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?)', log_content[:5000])
last_ts_match = None
for m in re.finditer(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?)', log_content[-5000:]):
    last_ts_match = m

first_ts = first_ts_match.group(1) if first_ts_match else 'unknown'
last_ts = last_ts_match.group(1) if last_ts_match else 'unknown'

# Sample hashrates from across the log
hashrate_samples = re.findall(r'HASHRATE\(total\)\s+([\d.]+)', log_content)
if hashrate_samples:
    hr_floats = [float(x) for x in hashrate_samples]
    hr_min = min(hr_floats)
    hr_max = max(hr_floats)
    hr_avg = sum(hr_floats) / len(hr_floats)
else:
    hr_min = hr_max = hr_avg = 0

# Power samples
power_samples = re.findall(r'power\s+([\d.]+)', log_content)
if power_samples:
    pw_floats = [float(x) for x in power_samples[:1000]]  # cap at 1000 to be safe
    pw_avg = sum(pw_floats) / len(pw_floats)
else:
    pw_avg = 0

# Sample DVFS chip alarms
chip_voltage_alarms = re.findall(r'chip (\d+/\d+).*?(\d+\.\d+)V', log_content[:200000])
unique_chips_alarmed = set(c[0] for c in chip_voltage_alarms[:5000])

print()
print('FACT SHEET FROM LOG:')
print(f'  Time range:           {first_ts}  →  {last_ts}')
print(f'  Total lines:          {total_lines:,}')
print(f'  DVFS ALARMs:          {dvfs_alarms:,}')
print(f'  PowerState ALARMs:    {power_state_alarms:,}')
print(f'  Board 3 zero events:  {board3_zero_lines:,}')
print(f'  Hashrate range:       {hr_min:.1f} – {hr_max:.1f} TH/s  (avg {hr_avg:.1f})')
print(f'  Avg power draw:       {pw_avg:.0f} W')
print(f'  Unique chips alarmed: {len(unique_chips_alarmed)}')

# Save into miner_logs under 'diagnostic' label
print()
print('Saving log to production DB...')
now = datetime.now().isoformat()
with sqlite3.connect('/root/Mining-Gaurdian/guardian.db', timeout=30) as conn:
    existing = conn.execute(
        "SELECT id FROM miner_logs WHERE miner_id=? AND health_status='diagnostic' AND log_file=?",
        (MINER_ID, 'log_1.pdf:gcminer/log')
    ).fetchone()
    if existing:
        print('  Already in DB, updating timestamp')
        conn.execute("UPDATE miner_logs SET collected_at=?, content=? WHERE id=?",
                     (now, log_content, existing[0]))
    else:
        conn.execute(
            "INSERT INTO miner_logs (collected_at, miner_id, model, health_status, log_file, content) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (now, MINER_ID, MODEL, 'diagnostic', 'log_1.pdf:gcminer/log', log_content)
        )
        print('  Inserted')

# Build a focused prompt — use a sampled excerpt + the fact sheet, NOT all 12 MB
# Take first 30K chars (early state), middle 20K (steady state), last 30K (end state)
sample = (
    log_content[:30000]
    + '\n\n... [middle 11.6 MB elided] ...\n\n'
    + log_content[len(log_content)//2 - 10000 : len(log_content)//2 + 10000]
    + '\n\n... [more middle elided] ...\n\n'
    + log_content[-30000:]
)
print(f'Built {len(sample):,} char prompt sample (3 windows from a 12 MB log)')

# Direct call: bypass the comparison helper since we have only one log.
# Use analyze_restart_logs with a synthetic "no prior log" pre-side.
from local_llm_analyzer import LocalLLMAnalyzer
import claude_log_comparison

miner_info = {
    'ip':           IP,
    'model':        MODEL,
    'action':       'diagnostic',
    'fact_sheet': {
        'time_range':         f'{first_ts} → {last_ts}',
        'total_lines':        total_lines,
        'dvfs_alarms':        dvfs_alarms,
        'powerstate_alarms':  power_state_alarms,
        'board3_zero_events': board3_zero_lines,
        'hashrate_th_s':      f'{hr_min:.1f} – {hr_max:.1f} (avg {hr_avg:.1f})',
        'avg_power_w':        f'{pw_avg:.0f}',
        'unique_chips_alarmed': len(unique_chips_alarmed),
    },
}

# Decorate sample with the fact sheet so models don't have to re-derive it
fact_sheet_str = (
    f"FACT SHEET (pre-computed by parser, trust these numbers):\n"
    f"  Time range: {first_ts} → {last_ts}\n"
    f"  Total log lines: {total_lines:,}\n"
    f"  DVFS ALARM count: {dvfs_alarms:,}\n"
    f"  PowerState ALARM count: {power_state_alarms:,}\n"
    f"  Board 3 zero-voltage events: {board3_zero_lines:,}\n"
    f"  Hashrate: {hr_min:.1f} – {hr_max:.1f} TH/s (avg {hr_avg:.1f})\n"
    f"  Avg power draw: {pw_avg:.0f} W\n"
    f"  Unique chips appearing in voltage alarms: {len(unique_chips_alarmed)}\n"
    f"  Auradine AH3880 stock target: 591 TH/s @ ~10kW\n\n"
)
synthetic_pre = "(no prior log — single-snapshot diagnostic, see fact sheet)"
synthetic_post = fact_sheet_str + "\n--- LOG SAMPLE (3 windows) ---\n" + sample

# Run Qwen
print()
print('Running Qwen 2.5 32B...')
t0 = time.time()
analyzer = LocalLLMAnalyzer()
qwen_analysis = analyzer.analyze_restart_logs(
    miner_id=MINER_ID,
    pre_log=synthetic_pre,
    post_log=synthetic_post,
    miner_info=miner_info,
)
qwen_t = time.time() - t0
print(f'  Qwen done in {qwen_t:.1f}s ({len(qwen_analysis or "")} chars)')

# Run Claude
print()
print('Running Claude Sonnet 4.6...')
t0 = time.time()
claude_analysis = claude_log_comparison.compare_logs_via_claude(
    miner_id=MINER_ID,
    pre_log=synthetic_pre,
    post_log=synthetic_post,
    miner_info=miner_info,
)
claude_t = time.time() - t0
print(f'  Claude done in {claude_t:.1f}s ({len(claude_analysis or "")} chars)')

# Store both
print()
print('Storing both analyses in knowledge.json...')
from knowledge_manager import KnowledgeManager
km = KnowledgeManager()
if qwen_analysis:
    km.add_llm_insight(qwen_analysis, miner_id=f'compare:diagnostic:qwen:{MINER_ID}')
if claude_analysis:
    km.add_llm_insight(claude_analysis, miner_id=f'compare:diagnostic:claude:{MINER_ID}')
print('  Stored')

# Print results
print()
print('=' * 70)
print('QWEN 2.5 32B VERDICT')
print('=' * 70)
print(qwen_analysis or '(no response)')
print()
print('=' * 70)
print('CLAUDE SONNET 4.6 VERDICT')
print('=' * 70)
print(claude_analysis or '(no response)')
print()
print('=' * 70)
print(f'DONE: Qwen={qwen_t:.0f}s  Claude={claude_t:.0f}s')
print('=' * 70)
