"""Analyze log 2 (192.168.188.55, the second AH3880) with CORRECTED operator
context: AH3880 has 2 hashboards, not 3. The avg_volt 3:0.0000 entries are
firmware phantom rail, NOT a fault.

This is also the test for whether the LLMs can catch the REAL story on
this miner: 566 pool stratum panics + DVFS power clipping.
"""
import os, sys, sqlite3, time, re
from datetime import datetime

os.chdir('/root/Mining-Gaurdian')
sys.path.insert(0, '/root/Mining-Gaurdian/core')
sys.path.insert(0, '/root/Mining-Gaurdian/ai')

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

MINER_ID = 'auradine_55'
IP = '192.168.188.55'
MODEL = 'Auradine AH3880 (2-board)'
LOG_PATH = '/tmp/log2_plain.txt'

print('=' * 70)
print('AH3880 #2 SINGLE-SNAPSHOT DIAGNOSIS — with CORRECTED operator context')
print(f'Miner: {MINER_ID} at {IP}')
print('Operator note: AH3880 has 2 boards. avg_volt 3:0.0000 = firmware noise.')
print('=' * 70)

with open(LOG_PATH) as f:
    log_content = f.read()
print(f'Loaded {len(log_content):,} bytes / {log_content.count(chr(10)):,} lines')

# Parser fact sheet
total_lines = log_content.count(chr(10))
dvfs_alarms = log_content.count('DVFS ALARM')
ps_alarms = log_content.count('PowerState ALARM')
panics = log_content.count('panic')
errors = log_content.count('ERROR')
board2_zero = log_content.count('2:0.0000')
board3_zero = log_content.count('3:0.0000')

ts_pattern = re.compile(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)')
all_ts = sorted(set(ts_pattern.findall(log_content)))
real_ts = [t for t in all_ts if not t.startswith('1970')]
first_real = real_ts[0] if real_ts else 'unknown'
last_real = real_ts[-1] if real_ts else 'unknown'

# Hashrate stats
mon_hr = re.findall(r'DVFS_MonitorHashRate avgHashRate\s+([\d.]+) target ([\d.]+)', log_content)
hr_avg = sum(float(x[0]) for x in mon_hr)/len(mon_hr) if mon_hr else 0
hr_target = float(mon_hr[0][1]) if mon_hr else 0
hr_pct = (hr_avg/hr_target*100) if hr_target else 0

# Power stats
power_samples = [float(x) for x in re.findall(r'power\s+([\d.]+),\s*inlet temp', log_content)]
pw_avg = sum(power_samples)/len(power_samples) if power_samples else 0
pw_max = max(power_samples) if power_samples else 0

# Temp stats
temp_samples = re.findall(r'avg_temp\s+([\d.]+),\s*max_temp\s+([\d.]+)', log_content)
chip_max = max(float(x[1]) for x in temp_samples) if temp_samples else 0

# Boardspeeds — verify 2 boards
boardspeeds = re.findall(r'boardspeeds\s+\[([0-9 ]+)\]', log_content)
board_counts = set(len(b.split()) for b in boardspeeds)

print()
print('FACT SHEET:')
print(f'  Time range:           {first_real} → {last_real}')
print(f'  (also has 1970 timestamps from a pre-NTP boot — at least 1 cold boot)')
print(f'  Total lines:          {total_lines:,}')
print(f'  Hashrate:             {hr_avg:.0f} of {hr_target:.0f} TH/s ({hr_pct:.1f}%)')
print(f'  Power:                avg {pw_avg:.0f} W, peak {pw_max:.0f} W')
print(f'  Max chip temp seen:   {chip_max:.1f}°C  (84°C operator threshold)')
print(f'  Boards reported:      {board_counts}  (each boardspeeds entry has this many slots)')
print(f'  DVFS ALARMs:          {dvfs_alarms:,}')
print(f'  PowerState ALARMs:    {ps_alarms:,}')
print(f'  ERRORs:               {errors:,}')
print(f'  panic events:         {panics:,}')
print(f'  avg_volt 2:0.0000:    {board2_zero:,}  (real momentary board-2 dropouts)')
print(f'  avg_volt 3:0.0000:    {board3_zero:,}  (firmware noise — phantom rail, AH3880 is 2-board)')

# Save to DB
print()
print('Saving to production DB...')
now = datetime.now().isoformat()
with sqlite3.connect('/root/Mining-Gaurdian/guardian.db', timeout=30) as conn:
    conn.execute("DELETE FROM miner_logs WHERE miner_id=? AND log_file=?",
                 (MINER_ID, 'log_2.rtf:gcminer/log'))
    conn.execute(
        "INSERT INTO miner_logs (collected_at, miner_id, model, health_status, log_file, content) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (now, MINER_ID, MODEL, 'diagnostic', 'log_2.rtf:gcminer/log', log_content)
    )
print('  Saved')

# Build operator-corrected fact sheet for LLM
fact_sheet = f"""FACT SHEET (pre-computed by parser, trust these numbers):
  Time range: {first_real} → {last_real}
  (log also contains 1970-01-01 timestamps from boot before NTP synced — indicates at least one cold reboot in the window)
  Total log lines: {total_lines:,}
  Hashrate achievement: {hr_avg:.0f} of {hr_target:.0f} TH/s = {hr_pct:.1f}% of tune target
  Power: avg {pw_avg:.0f} W, peak {pw_max:.0f} W  (vs ~10 kW stock budget)
  Max chip temperature observed: {chip_max:.1f}°C
  DVFS ALARM count: {dvfs_alarms:,}
  PowerState ALARM count: {ps_alarms:,}
  ERROR count: {errors:,}
  panic count: {panics:,}
  avg_volt 2:0.0000 events: {board2_zero}  (real momentary board 2 voltage dropouts)
  avg_volt 3:0.0000 events: {board3_zero}  (FIRMWARE NOISE — see operator note below)
  boardspeeds slot count per entry: {board_counts}

CRITICAL OPERATOR CONTEXT — DO NOT TREAT AS A FAULT:
  The Auradine AH3880 is a TWO-HASHBOARD chassis (Board 1 and Board 2 only).
  The FluxOS firmware was originally built for both AH3880 (2-board) and a
  sibling 3-board model from the same product line. On the 2-board AH3880,
  the firmware still logs DVFS readings for a phantom Board 3 rail that
  the hardware never populates. ALL `avg_volt 3:0.0000` and any "Board 3
  zero" patterns in the log are FIRMWARE NOISE, not a hardware fault.
  Verified by operator (Bobby, BiXBiT USA CTO) on 2026-04-08.

OPERATOR RULES:
  - Do NOT describe chip temps below 84°C as "overheating" or "high".
    The fleet runs 67-73°C normally. This miner is well below 84°C.
  - HVAC is correct — do NOT recommend HVAC investigation based on delta-T.
  - Do NOT report Board 3 / chain 3 issues — there is no Board 3 on AH3880.
"""

# Build sample (3 windows)
sample = (
    log_content[:30000]
    + '\n\n... [middle elided] ...\n\n'
    + log_content[len(log_content)//2 - 10000 : len(log_content)//2 + 10000]
    + '\n\n... [more middle elided] ...\n\n'
    + log_content[-30000:]
)
print(f'Built {len(sample):,} char prompt sample')

synthetic_pre = "(no prior log — single-snapshot diagnostic, see fact sheet)"
synthetic_post = fact_sheet + "\n--- LOG SAMPLE (3 windows from full log) ---\n" + sample

miner_info = {
    'ip': IP, 'model': MODEL, 'action': 'diagnostic',
    'note': 'AH3880 is a 2-board chassis. Board 3 entries are firmware noise.',
}

# Run Qwen
print()
print('Running Qwen 2.5 32B...')
from local_llm_analyzer import LocalLLMAnalyzer
import claude_log_comparison
analyzer = LocalLLMAnalyzer()
t0 = time.time()
qwen = analyzer.analyze_restart_logs(MINER_ID, synthetic_pre, synthetic_post, miner_info)
qt = time.time() - t0
print(f'  Qwen done in {qt:.1f}s ({len(qwen or "")} chars)')

# Run Claude
print()
print('Running Claude Sonnet 4.6...')
t0 = time.time()
claude = claude_log_comparison.compare_logs_via_claude(MINER_ID, synthetic_pre, synthetic_post, miner_info)
ct = time.time() - t0
print(f'  Claude done in {ct:.1f}s ({len(claude or "")} chars)')

# Store
print()
print('Storing in knowledge.json...')
from knowledge_manager import KnowledgeManager
km = KnowledgeManager()
if qwen:
    km.add_llm_insight(qwen, miner_id=f'compare:diagnostic:qwen:{MINER_ID}')
if claude:
    km.add_llm_insight(claude, miner_id=f'compare:diagnostic:claude:{MINER_ID}')
print('  Stored')

print()
print('=' * 70)
print('QWEN VERDICT')
print('=' * 70)
print(qwen or '(none)')
print()
print('=' * 70)
print('CLAUDE VERDICT')
print('=' * 70)
print(claude or '(none)')
print()
print('=' * 70)
print(f'DONE  Qwen={qt:.0f}s  Claude={ct:.0f}s')
print('=' * 70)
