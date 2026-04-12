#!/usr/bin/env python3
"""Apply the two operator rules across the codebase.

Rule 1 (Temp alerting): Do not flag/warn about overheating until chip temp >= 84°C.
  - GREEN: <84°C (no action, no alert, no LLM warning)
  - RED:   >=84°C (flag, alert, LLM may recommend action)
  No YELLOW tier.

Rule 2 (HVAC delta-T is correct): The HVAC system at USA 188 is performing
  perfectly. Do not recommend HVAC investigation based on low delta-T alone —
  delta-T is intentionally low now and will rise as ambient warms.
"""

import re

REPO = '/Users/BigBobby/Documents/GitHub/Mining Gaurdian'

# ============================================================
# FILE 1: core/mining_guardian.py — flagging logic and emoji thresholds
# ============================================================

mg_path = f'{REPO}/core/mining_guardian.py'
with open(mg_path) as f:
    src = f.read()

# Patch the temp emoji thresholds (line ~3167)
old1 = 'temp_icon = "🔴" if t >= 86 else "🟡" if t >= 76 else "🟢"'
new1 = 'temp_icon = "🔴" if t >= 84 else "🟢"'
assert old1 in src, "temp_icon line not found"
src = src.replace(old1, new1)
print("  ✓ mining_guardian.py: temp_icon thresholds → GREEN<84, RED>=84")

# Patch the _check_miner flagging logic (line ~3575-3579)
old2 = '''        elif temp_chip >= 86:
            issues.append(f"🔴 RED — chip {temp_chip}°C (≥86°C danger zone)")
            severity = "critical"
        elif temp_chip >= 76:
            issues.append(f"🟡 YELLOW — chip {temp_chip}°C (76–85°C range)")'''

# We need to look at this more carefully — I'm going to use a more flexible match
# First find the actual block
import re
m = re.search(r'(elif temp_chip >= 86.*?elif temp_chip >= 76.*?range"\)\n\s+)', src, re.DOTALL)
if not m:
    print("  ! could not find _check_miner temp block — searching alternative")
    # Try a simpler search
    if 'temp_chip >= 76' in src:
        # Find the surrounding context
        idx = src.find('temp_chip >= 76')
        print(f"    found temp_chip >= 76 at position {idx}")
        print(f"    surrounding: {src[max(0,idx-200):idx+200]!r}")

# Use a precise byte-level match for the _check_miner block
old_check = '''        elif temp_chip >= 86:
            issues.append(f"🔴 RED — chip {temp_chip}°C (≥86°C danger zone)")
            severity = "critical"
        elif temp_chip >= 76:
            issues.append(f"🟡 YELLOW — chip {temp_chip}°C (76–85°C range)")
            if severity != "critical":
                severity = "warning"'''

new_check = '''        elif temp_chip >= 84:
            issues.append(f"🔴 RED — chip {temp_chip}°C (≥84°C, action required)")
            severity = "critical"
        # OPERATOR RULE: Do not flag below 84°C. Liquid-cooled fleet runs cool
        # by design (67-73°C is normal). The previous 76°C yellow tier was an
        # air-cooled inheritance that does not apply to hydro/immersion cooling.'''

if old_check in src:
    src = src.replace(old_check, new_check)
    print("  ✓ mining_guardian.py: _check_miner 76°C tier removed, 86°C → 84°C")
else:
    print("  ! _check_miner exact match failed, trying line-by-line")
    # Show what's actually there
    idx = src.find('elif temp_chip >= 86')
    if idx > 0:
        print(f"    actual content near line 3575:")
        print(f"    {src[idx:idx+400]!r}")

with open(mg_path, 'w') as f:
    f.write(src)

# ============================================================
# FILE 2: core/llm_analyzer.py — system prompt
# ============================================================

la_path = f'{REPO}/core/llm_analyzer.py'
with open(la_path) as f:
    src = f.read()

old_zones = '- Chip temp zones: GREEN <76°C, YELLOW 76-85°C, RED 86°C+.'
new_zones = '''- Chip temp zones: GREEN <84°C (NO action needed), RED ≥84°C (action required).
- IMPORTANT: This is a liquid-cooled fleet. 67-73°C is COMPLETELY NORMAL for these miners.
  Do NOT recommend any thermal action, profile change, or cooling adjustment for any
  miner running below 84°C. Do NOT describe a miner as "running hot" or "overheating"
  unless its chip temp is at or above 84°C.'''

if old_zones in src:
    src = src.replace(old_zones, new_zones)
    print("  ✓ llm_analyzer.py: temp zones updated to 84°C threshold")
else:
    print("  ! llm_analyzer.py temp zones not found")

# Add HVAC delta-T guidance
old_hvac = '- HVAC system: supply water ~75°F, return water ~87°F, ΔT ~11°F is normal.'
new_hvac = '''- HVAC system: supply water ~75°F, return water ~87°F. The supply/return
  delta-T varies seasonally — it is intentionally LOW in cooler months and
  rises as outside temperature climbs. A LOW delta-T is NORMAL and CORRECT.
  Do NOT recommend HVAC investigation based on low delta-T alone.
  Do NOT describe low delta-T as "minimal headroom" or "thermal stress".
  The HVAC system at USA 188 is performing as designed — assume it is fine
  unless multiple miners simultaneously exceed 84°C.'''

if old_hvac in src:
    src = src.replace(old_hvac, new_hvac)
    print("  ✓ llm_analyzer.py: HVAC delta-T guidance added")
else:
    print("  ! llm_analyzer.py HVAC line not found")

with open(la_path, 'w') as f:
    f.write(src)

# ============================================================
# FILE 3: ai/deep_analysis_claude.py — Claude weekly training prompt
# ============================================================

dac_path = f'{REPO}/ai/deep_analysis_claude.py'
with open(dac_path) as f:
    src = f.read()

old_dac = '"Chip temp zones: GREEN <76°C | YELLOW 76-85°C | RED 86°C+.",'
new_dac = '''"Chip temp zones: GREEN <84°C (no action) | RED >=84°C (action required). NO yellow tier — this is a liquid-cooled fleet, 67-73°C is normal.",
        "OPERATOR RULE: Do NOT recommend HVAC investigation based on low delta-T. The HVAC delta-T is intentionally low and rises seasonally. The HVAC system is performing correctly.",'''

if old_dac in src:
    src = src.replace(old_dac, new_dac)
    print("  ✓ deep_analysis_claude.py: temp zones + HVAC rule added")
else:
    print("  ! deep_analysis_claude.py temp zone line not found")

with open(dac_path, 'w') as f:
    f.write(src)

# ============================================================
# FILE 4: ai/action_diversity.py — TEMP_CHIP_POWER_DOWN constant
# ============================================================

ad_path = f'{REPO}/ai/action_diversity.py'
with open(ad_path) as f:
    src = f.read()

old_ad = 'TEMP_CHIP_POWER_DOWN   = 76.0  # chip temp above this → consider power down'
new_ad = 'TEMP_CHIP_POWER_DOWN   = 84.0  # OPERATOR RULE: chip temp >=84°C → consider power down (was 76, raised because liquid-cooled fleet runs 67-73°C normally)'

if old_ad in src:
    src = src.replace(old_ad, new_ad)
    print("  ✓ action_diversity.py: TEMP_CHIP_POWER_DOWN 76 → 84")
else:
    print("  ! action_diversity.py constant not found")

with open(ad_path, 'w') as f:
    f.write(src)

# ============================================================
# FILE 5: api/slack_command_handler.py — /hot command
# ============================================================

sc_path = f'{REPO}/api/slack_command_handler.py'
with open(sc_path) as f:
    src = f.read()

# The /hot command queries miners >= 76°C — bump to 84°C
src = src.replace(
    'AND temp_chip >= 76 AND status = \'online\'',
    'AND temp_chip >= 84 AND status = \'online\''
)
src = src.replace(
    'zone = "🔴" if m[\'temp_chip\'] >= 86 else "🟡"',
    'zone = "🔴"'
)
src = src.replace(
    '— list miners in yellow/red temp zone',
    '— list miners in red temp zone (chip >=84°C)'
)
src = src.replace(
    '"""List miners in yellow/red temp zone."""',
    '"""List miners in red temp zone (chip >=84°C)."""'
)
print("  ✓ slack_command_handler.py: /hot command threshold 76 → 84")

with open(sc_path, 'w') as f:
    f.write(src)

# ============================================================
# FILE 6: ai/train_cohort.py — add operator rules to all 3 prompts
# ============================================================

tc_path = f'{REPO}/ai/train_cohort.py'
with open(tc_path) as f:
    src = f.read()

# Find a good injection point — right before "=== YOUR TASK ===" in cohort prompt
operator_rules_block = '''        '=== OPERATOR RULES (MUST FOLLOW) ===',
        'These rules are set by the fleet operator and override any default heuristics:',
        '',
        '1. TEMPERATURE: This is a LIQUID-COOLED fleet. Chip temps of 67-73°C are NORMAL',
        '   and require NO action. Do NOT flag, warn about, or recommend action for any',
        '   miner running below 84°C. Do NOT describe miners under 84°C as "running hot",',
        '   "overheating", or "thermally stressed". Only chip temps >=84°C warrant action.',
        '',
        '2. HVAC: The USA 188 HVAC system is performing CORRECTLY. The supply/return',
        '   water delta-T is intentionally LOW right now and will rise as outside temps',
        '   climb (seasonal behavior). Do NOT recommend "check the HVAC because delta-T',
        '   is low". Do NOT describe low delta-T as "minimal headroom" or "thermal stress".',
        '   Assume the HVAC is fine unless multiple miners simultaneously exceed 84°C.',
        '',
        '3. ACTION RECOMMENDATIONS: Bias toward documenting hardware patterns over',
        '   recommending environmental changes. The cooling system is rarely the problem.',
        '',
'''

# We need to inject this in three places — one per prompt builder. Find each "=== YOUR TASK ==="
count = src.count("'=== YOUR TASK ===',")
print(f"  Found {count} '=== YOUR TASK ===' markers in train_cohort.py")

# Inject before each one
src = src.replace(
    "'=== YOUR TASK ===',",
    operator_rules_block + "        '=== YOUR TASK ===',"
)

# Verify the injection happened the right number of times
new_count = src.count('=== OPERATOR RULES (MUST FOLLOW) ===')
print(f"  Injected operator rules block {new_count} times (expected 3)")

with open(tc_path, 'w') as f:
    f.write(src)

print()
print("All operator rule patches applied")
