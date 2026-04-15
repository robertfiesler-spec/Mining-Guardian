#!/usr/bin/env python3
"""Add S19J Pro HVAC section to Slack scan reports - Part 2"""

with open('/root/Mining-Gaurdian/core/mining_guardian.py', 'r') as f:
    content = f.read()

# Find where warehouse HVAC section ends and add S19J Pro section
old_block = '''            lines.extend(hvac_lines)

        lines.append(status_line)'''

new_block = '''            lines.extend(hvac_lines)

        # S19J Pro Container HVAC (separate system for S19J Pros)
        if hvac_s19jpro is not None:
            s19_lines = [f"\\n*🏭 S19J Pro Container*"]
            
            sup = f"{hvac_s19jpro.supply_temp_f:.1f}°F" if hvac_s19jpro.supply_temp_f is not None else "N/A"
            ret = f"{hvac_s19jpro.return_temp_f:.1f}°F" if hvac_s19jpro.return_temp_f is not None else "N/A"
            dlt = f"{hvac_s19jpro.delta_t_f:+.1f}°F" if hvac_s19jpro.delta_t_f is not None else "N/A"
            
            s19_lines.append(f"  Supply: *{sup}* | Return: *{ret}* | ΔT: *{dlt}*")
            
            # S19J Pro container has simpler controls - no CT fans shown (manually at 100%)
            pump = "🟢 ON" if getattr(hvac_s19jpro, 'spray_pump_on', False) else "🔴 OFF"
            cwp1 = f"{hvac_s19jpro.cwp1_vfd_pct:.0f}%" if getattr(hvac_s19jpro, 'cwp1_vfd_pct', None) is not None else "?"
            cwp2 = f"{hvac_s19jpro.cwp2_vfd_pct:.0f}%" if getattr(hvac_s19jpro, 'cwp2_vfd_pct', None) is not None else "?"
            
            s19_lines.append(f"  Spray Pump: {pump} | CW Pump 1: {cwp1} | CW Pump 2: {cwp2}")
            
            # Check alarms
            alarms = []
            if getattr(hvac_s19jpro, 'leak_alarm', False):
                alarms.append("🔴 LEAK DETECTED")
            if getattr(hvac_s19jpro, 'pump_fault', False):
                alarms.append("🔴 Pump FAULT")
            
            if alarms:
                s19_lines.append(f"  ⚠️ *ALARMS:* {' | '.join(alarms)}")
            else:
                s19_lines.append("  ✅ All alarms clear")
            
            lines.extend(s19_lines)

        lines.append(status_line)'''

if old_block in content:
    content = content.replace(old_block, new_block)
    print('Added S19J Pro Container section to Slack reports')
else:
    print('Pattern not found - check manually')

with open('/root/Mining-Gaurdian/core/mining_guardian.py', 'w') as f:
    f.write(content)

print('Saved - Part 2 complete!')
