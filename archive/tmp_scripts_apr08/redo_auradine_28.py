"""Re-run auradine_28 (192.168.188.28) analysis with corrected operator context.

The first run incorrectly diagnosed "Board 3 dead" because neither model knew
the AH3880 is a 2-board chassis. With the corrected operator note, both models
should focus on the REAL faults: PSU IOUT 0x02 overcurrent shutdowns and the
power/voltage clipping pattern.
"""
import os, sys, sqlite3, time, re
from datetime import datetime

os.chdir('/root/Mining-Gaurdian')
sys.path.insert(0, '/root/Mining-Gaurdian/core')
sys.path.insert(0, '/root/Mining-Gaurdian/ai')

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

MINER_ID = 'auradine_28'
IP = '192.168.188.28'
MODEL = 'Auradine AH3880 (2-board)'
LOG_PATH = '/tmp/log1_full.txt'

print('Re-analyzing auradine_28 with corrected 2-board operator context')

with open(LOG_PATH) as f:
    log_content = f.read()

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

mon_hr = re.findall(r'DVFS_MonitorHashRate avgHashRate\s+([\d.]+) target ([\d.]+)', log_content)
hr_avg = sum(float(x[0]) for x in mon_hr)/len(mon_hr) if mon_hr else 0
hr_target = float(mon_hr[0][1]) if mon_hr else 0
hr_pct = (hr_avg/hr_target*100) if hr_target else 0

power_samples = [float(x) for x in re.findall(r'power\s+([\d.]+),\s*inlet temp', log_content)]
pw_avg = sum(power_samples)/len(power_samples) if power_samples else 0
pw_max = max(power_samples) if power_samples else 0

print(f'Time: {first_real} → {last_real}')
print(f'Lines: {total_lines:,}  panics: {panics:,}  DVFS: {dvfs_alarms:,}  PowerState: {ps_alarms:,}  ERR: {errors:,}')
print(f'Hashrate: {hr_avg:.0f}/{hr_target:.0f} TH/s ({hr_pct:.1f}%)  Power: avg {pw_avg:.0f}W peak {pw_max:.0f}W')
print(f'avg_volt 2:0.0000: {board2_zero}  avg_volt 3:0.0000: {board3_zero} (firmware noise)')

fact_sheet = f"""FACT SHEET (parser-computed):
  Time range: {first_real} → {last_real}
  Total lines: {total_lines:,}
  Hashrate: {hr_avg:.0f} of {hr_target:.0f} TH/s ({hr_pct:.1f}%)
  Power: avg {pw_avg:.0f} W, peak {pw_max:.0f} W
  DVFS ALARMs: {dvfs_alarms:,}
  PowerState ALARMs: {ps_alarms:,}
  ERRORs: {errors:,}
  panic events: {panics:,}
  avg_volt 2:0.0000 events: {board2_zero}
  avg_volt 3:0.0000 events: {board3_zero} (FIRMWARE NOISE — phantom rail, see operator note)

CRITICAL OPERATOR CONTEXT:
  The Auradine AH3880 is a TWO-HASHBOARD chassis (Board 1 + Board 2 only).
  FluxOS firmware was originally built for both AH3880 (2-board) and a sibling
  3-board model. On the 2-board AH3880 the firmware still logs DVFS readings
  for a phantom Board 3 rail. ALL `avg_volt 3:0.0000` and "Board 3 zero"
  patterns are FIRMWARE NOISE, not a hardware fault. Verified physically by
  operator (Bobby, BiXBiT USA CTO) on 2026-04-08. Do NOT report Board 3
  failures. Focus on Board 1, Board 2, PSU, and DVFS findings only.

OPERATOR RULES:
  - Chip temps below 84°C are NORMAL. Do not flag as overheating.
  - HVAC is correct. Do not recommend HVAC investigation.
"""

sample = (
    log_content[:30000]
    + '\n\n... [middle elided] ...\n\n'
    + log_content[len(log_content)//2 - 10000 : len(log_content)//2 + 10000]
    + '\n\n... [more middle elided] ...\n\n'
    + log_content[-30000:]
)

synthetic_pre = "(no prior log — single-snapshot diagnostic)"
synthetic_post = fact_sheet + "\n--- LOG SAMPLE (3 windows) ---\n" + sample

miner_info = {'ip': IP, 'model': MODEL, 'action': 'diagnostic',
              'note': 'AH3880 2-board chassis, Board 3 entries are firmware noise'}

from local_llm_analyzer import LocalLLMAnalyzer
import claude_log_comparison

print('\nQwen running...')
t0 = time.time()
analyzer = LocalLLMAnalyzer()
qwen = analyzer.analyze_restart_logs(MINER_ID, synthetic_pre, synthetic_post, miner_info)
print(f'  done in {time.time()-t0:.0f}s')

print('Claude running...')
t0 = time.time()
claude = claude_log_comparison.compare_logs_via_claude(MINER_ID, synthetic_pre, synthetic_post, miner_info)
print(f'  done in {time.time()-t0:.0f}s')

# Update knowledge.json — replace the wrong entries
from knowledge_manager import KnowledgeManager
km = KnowledgeManager()
if qwen:
    km.add_llm_insight(qwen, miner_id=f'compare:diagnostic:qwen:{MINER_ID}_v2')
if claude:
    km.add_llm_insight(claude, miner_id=f'compare:diagnostic:claude:{MINER_ID}_v2')

print('\n=== QWEN ===')
print(qwen or '(none)')
print('\n=== CLAUDE ===')
print(claude or '(none)')
