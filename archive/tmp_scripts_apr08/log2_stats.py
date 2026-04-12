"""Quick stats on log2_plain.txt — figure out what kind of miner state this is."""
import re
from collections import Counter

with open('/tmp/log2_plain.txt') as f:
    log = f.read()

print(f'Total chars: {len(log):,}')
print(f'Total lines: {log.count(chr(10)):,}')

# Time range
ts_pattern = re.compile(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)')
all_ts = ts_pattern.findall(log)
if all_ts:
    print(f'Time range: {min(all_ts)} → {max(all_ts)}')
    span_start = min(all_ts)
    span_end = max(all_ts)

# IPs
ips = set(re.findall(r'\b192\.168\.\d+\.\d+\b', log))
print(f'IPs in log: {ips}')

# Counts
print()
print('--- ALARMS ---')
print(f'DVFS ALARM:        {log.count("DVFS ALARM"):,}')
print(f'PowerState ALARM:  {log.count("PowerState ALARM"):,}')
print(f'WARN:              {log.count("WARN"):,}')
print(f'ERROR:             {log.count("ERROR"):,} (case sensitive)')
print(f'FATAL:             {log.count("FATAL"):,}')
print(f'panic:             {log.count("panic"):,}')

print()
print('--- BOARD STATE ---')
print(f'avg_volt 1:0.0000: {log.count("1:0.0000"):,}')
print(f'avg_volt 2:0.0000: {log.count("2:0.0000"):,}')
print(f'avg_volt 3:0.0000: {log.count("3:0.0000"):,}')

# Hashrate samples
print()
print('--- HASHRATE ---')
hr_total = re.findall(r'HASHRATE\(total\)\s+([\d.]+)', log)
if hr_total:
    vals = [float(x) for x in hr_total]
    print(f'HASHRATE(total) samples: {len(vals):,}')
    print(f'  range: {min(vals):.1f} - {max(vals):.1f} TH/s')
    print(f'  avg:   {sum(vals)/len(vals):.1f} TH/s')

# DVFS_MonitorHashRate is more reliable
mon_hr = re.findall(r'DVFS_MonitorHashRate avgHashRate\s+([\d.]+) target ([\d.]+)', log)
if mon_hr:
    avgs = [float(x[0]) for x in mon_hr]
    targets = [float(x[1]) for x in mon_hr]
    print(f'DVFS_MonitorHashRate samples: {len(avgs):,}')
    print(f'  avg current: {sum(avgs)/len(avgs):.1f} TH/s')
    print(f'  target:      {targets[0]:.0f} TH/s')
    print(f'  achievement: {(sum(avgs)/len(avgs))/targets[0]*100:.1f}%')

# Power samples
power_samples = re.findall(r'power\s+([\d.]+),\s*inlet temp', log)
if power_samples:
    pw = [float(x) for x in power_samples]
    print(f'Power samples: {len(pw):,}')
    print(f'  range: {min(pw):.0f} - {max(pw):.0f} W')
    print(f'  avg:   {sum(pw)/len(pw):.0f} W')

# Temps
temp_samples = re.findall(r'avg_temp\s+([\d.]+),\s*max_temp\s+([\d.]+)', log)
if temp_samples:
    avgs = [float(x[0]) for x in temp_samples]
    maxs = [float(x[1]) for x in temp_samples]
    print(f'Temp samples: {len(avgs):,}')
    print(f'  avg_temp: {sum(avgs)/len(avgs):.1f}°C  (max seen: {max(avgs):.1f}°C)')
    print(f'  max_temp: {sum(maxs)/len(maxs):.1f}°C  (max seen: {max(maxs):.1f}°C)')

# Boardspeeds
board_speeds = re.findall(r'boardspeeds\s+\[([0-9 ]+)\]', log)
if board_speeds:
    parsed = [list(map(int, b.split())) for b in board_speeds]
    if parsed:
        n_boards = len(parsed[0])
        print(f'boardspeeds samples: {len(parsed):,}, {n_boards} boards reported')
        for i in range(n_boards):
            vals = [b[i] for b in parsed if len(b) > i]
            if vals:
                print(f'  board {i+1}: avg {sum(vals)/len(vals):.0f}, range {min(vals)}-{max(vals)}')

# Pool state
print()
print('--- POOL ---')
pool_lines = [l for l in log.split('\n') if 'pool' in l.lower()][:5]
for l in pool_lines:
    print(f'  {l[:160]}')

# WARN and notable events
print()
print('--- NOTABLE EVENTS ---')
notable = []
for line in log.split('\n'):
    lower = line.lower()
    if any(w in lower for w in ['warn', 'error', 'fatal', 'panic', 'fail', 'disconnect', 'reset', 'reboot', 'crash']):
        notable.append(line.strip())
print(f'Total notable lines: {len(notable):,}')
# Show distinct types
type_count = Counter()
for l in notable:
    # Extract a "type" — last colon-separated chunk usually
    tag = re.search(r'(WARN|ERROR|FATAL|panic|disconnect|reset|reboot|crash|fail)', l, re.IGNORECASE)
    if tag:
        type_count[tag.group(1).lower()] += 1
for k, v in type_count.most_common(10):
    print(f'  {k}: {v}')

# Sample 5 notable lines
print()
print('Sample notable lines:')
for l in notable[:5]:
    print(f'  {l[:180]}')
