"""Re-run AH3880 dual-model diagnosis with CORRECTED operator context.

Bobby physically verified Apr 8 2026 07:30 CDT that the AH3880 has exactly
2 hashboards. The 44,901 avg_volt 3:0.0000 events in the log are from a
phantom firmware rail, NOT a dead board. The previous analysis (commit
10664e8) incorrectly diagnosed Board 3 as failed.

Real findings to surface:
  - 11 PSU IOUT 0x02 overcurrent shutdowns
  - 726 DVFS power-over-limit alarms
  - 53 PowerState voltage clipping events
  - Hashrate ~358 TH/s avg vs ~591 TH/s tune target
  - Both real boards healthy in current API readings

This re-run injects the correct operator context (AH3880 is 2-board) into
the prompt and stores the new analysis under different miner_id keys so the
old analysis remains in knowledge.json as a historical "what we got wrong
the first time" example for the dual-model jump-start training data.
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
MODEL = 'Auradine AH3880 (2-board chassis, operator-confirmed)'
LOG_PATH = '/tmp/log1_full.txt'

print('=' * 70)
print('AH3880 DIAGNOSIS — RERUN WITH CORRECTED OPERATOR CONTEXT')
print('Operator confirmed: AH3880 has exactly 2 hashboards')
print('=' * 70)

with open(LOG_PATH) as f:
    log_content = f.read()
print(f'Loaded {len(log_content):,} bytes / {log_content.count(chr(10)):,} lines')

import re
total_lines = log_content.count(chr(10))
dvfs_alarms = log_content.count('DVFS ALARM')
power_state_alarms = log_content.count('PowerState ALARM')
board3_zero_lines = log_content.count('3:0.0000')

# Count PSU shutdowns
psu_shutdowns = log_content.count('PSU powered itself off')
psu_overcurrent = log_content.count('IOUT Status = 0x02')

first_ts_match = re.search(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?)', log_content[:5000])
last_ts_match = None
for m in re.finditer(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?)', log_content[-5000:]):
    last_ts_match = m
first_ts = first_ts_match.group(1) if first_ts_match else 'unknown'
last_ts = last_ts_match.group(1) if last_ts_match else 'unknown'

hashrate_samples = re.findall(r'HASHRATE\(total\)\s+([\d.]+)', log_content)
hr_floats = [float(x) for x in hashrate_samples] if hashrate_samples else [0]
hr_min, hr_max, hr_avg = min(hr_floats), max(hr_floats), sum(hr_floats) / len(hr_floats)

# Average board voltages from boards 1 and 2 only
board1_volts = re.findall(r'avg_volt 1:([\d.]+)', log_content)
board2_volts = re.findall(r'avg_volt 2:([\d.]+)', log_content)
b1_avg = sum(float(v) for v in board1_volts[:5000]) / max(1, len(board1_volts[:5000]))
b2_avg = sum(float(v) for v in board2_volts[:5000]) / max(1, len(board2_volts[:5000]))

print()
print('CORRECTED FACT SHEET (operator-verified):')
print(f'  Chassis:                 AH3880 with 2 hashboards (NOT 3)')
print(f'  Time range:              {first_ts}  →  {last_ts}')
print(f'  Total log lines:         {total_lines:,}')
print(f'  DVFS ALARMs:             {dvfs_alarms:,}')
print(f'  PowerState ALARMs:       {power_state_alarms:,}')
print(f'  PSU shutdown events:     {psu_shutdowns:,}')
print(f'  PSU IOUT 0x02 codes:     {psu_overcurrent:,}')
print(f'  Hashrate range:          {hr_min:.1f} – {hr_max:.1f} TH/s  (avg {hr_avg:.1f})')
print(f'  Board 1 avg voltage:     {b1_avg:.4f} V')
print(f'  Board 2 avg voltage:     {b2_avg:.4f} V')
print(f'  Phantom rail 3 events:   {board3_zero_lines:,}  (firmware artifact, NOT a real board)')

# Build sample
sample = (
    log_content[:30000]
    + '\n\n... [middle 11.6 MB elided] ...\n\n'
    + log_content[len(log_content)//2 - 10000 : len(log_content)//2 + 10000]
    + '\n\n... [more middle elided] ...\n\n'
    + log_content[-30000:]
)

# Build prompt with explicit operator correction
fact_sheet_str = f"""CRITICAL OPERATOR CONTEXT (operator physically verified):
  - This is an Auradine AH3880 chassis with EXACTLY 2 hashboards (Board 1 + Board 2).
  - There is NO Board 3. The chassis was manufactured as a 2-board variant.
  - The firmware (FluxOS / gcminer) is shared across multiple AH-series chassis variants
    including 3-board models. On a 2-board chassis the firmware still tracks a phantom
    third rail in DVFS reporting, which always reads 0V because no physical board exists.
  - Therefore, ANY log entry showing "3:0.0000" or "boardspeeds [N1 N2]" with only 2
    values is NORMAL and EXPECTED for this chassis. Do NOT diagnose Board 3 as failed.

PARSER FACT SHEET (trust these numbers):
  Time range:                  {first_ts} → {last_ts}
  Total log lines:             {total_lines:,}
  DVFS ALARM count:            {dvfs_alarms:,}
  PowerState ALARM count:      {power_state_alarms:,}
  PSU shutdown events:         {psu_shutdowns:,}
  PSU IOUT 0x02 (overcurrent): {psu_overcurrent:,}
  Hashrate: {hr_min:.1f} – {hr_max:.1f} TH/s (avg {hr_avg:.1f})
  Board 1 avg voltage:         {b1_avg:.4f} V (healthy)
  Board 2 avg voltage:         {b2_avg:.4f} V (healthy)
  Phantom rail 3 events:       {board3_zero_lines:,} (FIRMWARE ARTIFACT, ignore)
  AH3880 stock target:         591 TH/s @ ~10kW with 2 boards

YOUR JOB: Diagnose what's actually wrong with this miner given that BOTH real
boards are operational. Focus on the PSU instability, DVFS over-limit events,
and PowerState voltage clipping. Do not mention Board 3 except to acknowledge
the operator's correction that it does not exist.

"""

synthetic_pre = "(no prior log — single-snapshot diagnostic, see operator context and fact sheet above)"
synthetic_post = fact_sheet_str + "\n--- LOG SAMPLE (3 windows: start, middle, end) ---\n" + sample

miner_info = {
    'ip':           IP,
    'model':        MODEL,
    'action':       'diagnostic',
    'board_count':  2,
    'note':         'AH3880 is 2-board chassis; phantom rail 3 in logs is a firmware artifact',
}

# Run Qwen
print()
print('Running Qwen 2.5 32B with corrected context...')
from local_llm_analyzer import LocalLLMAnalyzer
analyzer = LocalLLMAnalyzer()
t0 = time.time()
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
print('Running Claude Sonnet 4.6 with corrected context...')
import claude_log_comparison
t0 = time.time()
claude_analysis = claude_log_comparison.compare_logs_via_claude(
    miner_id=MINER_ID,
    pre_log=synthetic_pre,
    post_log=synthetic_post,
    miner_info=miner_info,
)
claude_t = time.time() - t0
print(f'  Claude done in {claude_t:.1f}s ({len(claude_analysis or "")} chars)')

# Store under v2 keys to keep the old analysis as historical record
print()
print('Storing as v2 (corrected) — old analysis remains for training comparison...')
from knowledge_manager import KnowledgeManager
km = KnowledgeManager()
if qwen_analysis:
    km.add_llm_insight(qwen_analysis, miner_id=f'compare:diagnostic:qwen:{MINER_ID}:v2_corrected')
if claude_analysis:
    km.add_llm_insight(claude_analysis, miner_id=f'compare:diagnostic:claude:{MINER_ID}:v2_corrected')
print('  Stored')

# Print results
print()
print('=' * 70)
print('QWEN 2.5 32B v2 (CORRECTED CONTEXT)')
print('=' * 70)
print(qwen_analysis or '(no response)')
print()
print('=' * 70)
print('CLAUDE SONNET 4.6 v2 (CORRECTED CONTEXT)')
print('=' * 70)
print(claude_analysis or '(no response)')
print()
print('=' * 70)
print(f'DONE: Qwen={qwen_t:.0f}s  Claude={claude_t:.0f}s')
print('=' * 70)
