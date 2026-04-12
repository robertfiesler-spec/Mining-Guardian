"""Re-run BOTH AH3880 diagnoses with the firmware regression operator note.

The previous runs gave both LLMs the 2-board correction but NOT the firmware
update context. Bobby has since told us the new firmware is the suspected
root cause. This run feeds both LLMs the full operator context so we can see
whether they reach a different conclusion (firmware regression instead of
PSU replacement).

Args: miner_id (28 or 55)
"""
import os, sys, sqlite3, time, re
from datetime import datetime

os.chdir('/root/Mining-Gaurdian')
sys.path.insert(0, '/root/Mining-Gaurdian/core')
sys.path.insert(0, '/root/Mining-Gaurdian/ai')

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

which = sys.argv[1] if len(sys.argv) > 1 else '28'

if which == '28':
    MINER_ID = 'auradine_28'
    IP = '192.168.188.28'
    LOG_PATH = '/tmp/log1_full.txt'
elif which == '55':
    MINER_ID = 'auradine_55'
    IP = '192.168.188.55'
    LOG_PATH = '/tmp/log2_plain.txt'
else:
    print('Usage: rerun_with_firmware_note.py [28|55]')
    sys.exit(1)

MODEL = 'Auradine AH3880 (2-board)'

print(f'Re-analyzing {MINER_ID} ({IP}) with firmware-regression operator context')
with open(LOG_PATH) as f:
    log_content = f.read()

# Quick parser stats
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

print(f'  {total_lines:,} lines, {panics:,} panics, {dvfs_alarms:,} DVFS, {ps_alarms:,} PowerState, {errors:,} ERR')
print(f'  hashrate {hr_avg:.0f}/{hr_target:.0f} ({hr_pct:.1f}%)  power avg {pw_avg:.0f}W peak {pw_max:.0f}W')

fact_sheet = f"""FACT SHEET (parser-computed):
  Miner: {MINER_ID} at {IP} ({MODEL})
  Time range: {first_real} → {last_real}
  Total lines: {total_lines:,}
  Hashrate achievement: {hr_avg:.0f} of {hr_target:.0f} TH/s ({hr_pct:.1f}%)
  Power: avg {pw_avg:.0f} W, peak {pw_max:.0f} W
  DVFS ALARMs: {dvfs_alarms:,}
  PowerState ALARMs: {ps_alarms:,}
  ERRORs: {errors:,}
  panic events: {panics:,}
  avg_volt 2:0.0000 events: {board2_zero}
  avg_volt 3:0.0000 events: {board3_zero} (FIRMWARE NOISE — phantom rail, see operator note)

CRITICAL OPERATOR CONTEXT — APRIL 8, 2026:
  1. The Auradine AH3880 is a TWO-HASHBOARD chassis (Board 1 + Board 2 only).
     ALL `avg_volt 3:0.0000` and "Board 3 zero" patterns are FIRMWARE NOISE,
     not a hardware fault. Verified physically by operator (Bobby).

  2. *** RECENT FIRMWARE UPDATE — SUSPECTED ROOT CAUSE ***
     Both AH3880 miners in the fleet (192.168.188.28 and 192.168.188.55)
     received an Auradine firmware update shortly before these logs were
     captured. After the update, BOTH miners began showing IDENTICAL fault
     patterns at the same time:
       - DVFS power overshoot alarms (power clipping at 11.5kW vs 10kW budget)
       - PowerState voltage clipping at both Vmin (31V) and Vmax (47V)
       - PSU IOUT 0x02 overcurrent shutdown trips
       - PSU AC input fault (Status 0x10) on some scans
       - PSU fan fault (Status 0x02) on some scans
       - Hundreds of pool stratum panics in gcminer
       - Hashrate stuck at ~79% of tune target
     The operator has emailed Auradine to request the previous firmware
     version for rollback. Both miners' PSUs were operating normally
     before the firmware update.

  3. WHEN YOU SEE THE SYMPTOMS LISTED ABOVE: prefer "firmware regression"
     as the root cause over "PSU hardware failure". The symptoms look
     unambiguously like PSU faults but firmware bugs in DVFS power
     management can produce identical signatures. The fact that two
     miners of the same model show identical fault patterns within
     hours of the same firmware update is the giveaway.

  4. Chip temperatures below 84°C are NORMAL for this liquid-cooled fleet.
     Do NOT describe any chip temp below 84°C as overheating.

  5. HVAC supply/return delta-T is intentionally low at this time of year.
     Do NOT recommend HVAC investigation based on delta-T.

YOUR JOB:
  Re-evaluate this log with the firmware update context in mind. Does the
  evidence support firmware regression, PSU failure, or both? Be specific
  about which evidence points which direction. Give a single recommended
  action (firmware rollback OR PSU replacement OR something else) and your
  confidence level. Acknowledge if the previous "Replace PSU" verdict
  needs to be revised.
"""

# Build sample
sample = (
    log_content[:30000]
    + '\n\n... [middle elided] ...\n\n'
    + log_content[len(log_content)//2 - 10000 : len(log_content)//2 + 10000]
    + '\n\n... [more middle elided] ...\n\n'
    + log_content[-30000:]
)

synthetic_pre = "(no prior log — single-snapshot diagnostic, see operator context)"
synthetic_post = fact_sheet + "\n--- LOG SAMPLE (3 windows from full log) ---\n" + sample

miner_info = {
    'ip': IP, 'model': MODEL, 'action': 'diagnostic_v3',
    'note': 'AH3880 2-board, recent firmware update suspected root cause, both miners affected identically',
}

from local_llm_analyzer import LocalLLMAnalyzer
import claude_log_comparison
analyzer = LocalLLMAnalyzer()

print(f'\nRunning Qwen on {MINER_ID}...')
t0 = time.time()
qwen = analyzer.analyze_restart_logs(MINER_ID, synthetic_pre, synthetic_post, miner_info)
qt = time.time() - t0
print(f'  Qwen done in {qt:.0f}s ({len(qwen or "")} chars)')

print(f'Running Claude on {MINER_ID}...')
t0 = time.time()
claude = claude_log_comparison.compare_logs_via_claude(MINER_ID, synthetic_pre, synthetic_post, miner_info)
ct = time.time() - t0
print(f'  Claude done in {ct:.0f}s ({len(claude or "")} chars)')

# Store both
from knowledge_manager import KnowledgeManager
km = KnowledgeManager()
if qwen:
    km.add_llm_insight(qwen, miner_id=f'compare:diagnostic:qwen:{MINER_ID}:v3_firmware_aware')
if claude:
    km.add_llm_insight(claude, miner_id=f'compare:diagnostic:claude:{MINER_ID}:v3_firmware_aware')
print('Stored as v3_firmware_aware')

print()
print('=' * 70)
print(f'QWEN VERDICT — {MINER_ID} v3 (firmware-aware)')
print('=' * 70)
print(qwen or '(none)')
print()
print('=' * 70)
print(f'CLAUDE VERDICT — {MINER_ID} v3 (firmware-aware)')
print('=' * 70)
print(claude or '(none)')
print()
print(f'DONE  Qwen={qt:.0f}s  Claude={ct:.0f}s')
