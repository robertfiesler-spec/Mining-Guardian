#!/usr/bin/env python3
"""Fix the prediction row builder to use confidence field directly"""

with open('/root/Mining-Gaurdian/api/ai_dashboard_api.py', 'r') as f:
    content = f.read()

# Find and replace the prediction loop that extracts confidence from text
old_block = '''    # Prediction rows
    pr = ""
    for p in predictions:
        ts = str(p.get("timestamp", ""))[:16]
        # Extract confidence from problem/notes field
        prob = str(p.get("problem", "") or "")
        pred_conf = 75
        if "%" in prob:
            try:
                # re already imported at top
                m = re.search(r'(\\d+)%', prob)
                if m:
                    pred_conf = int(m.group(1))
            except:
                pass
        pred_conf_color = G if pred_conf >= 80 else O if pred_conf >= 50 else R'''

new_block = '''    # Prediction rows — uses REAL confidence from knowledge.json
    pr = ""
    for p in predictions:
        ts = str(p.get("timestamp", ""))[:16]
        # Use actual confidence field directly (not parsed from text!)
        pred_conf = p.get("confidence", 75)
        if not isinstance(pred_conf, (int, float)):
            try:
                pred_conf = int(pred_conf)
            except:
                pred_conf = 75
        pred_conf = int(pred_conf)
        pred_conf_color = G if pred_conf >= 80 else O if pred_conf >= 50 else R'''

if old_block in content:
    content = content.replace(old_block, new_block)
    print('Fixed prediction loop to use confidence field directly')
else:
    print('Old block not found - checking for variations...')
    # Try a simpler replacement
    if 'pred_conf = 75' in content and '# Extract confidence from problem' in content:
        print('Found partial match - applying targeted fix')
        content = content.replace(
            '# Extract confidence from problem/notes field',
            '# Use actual confidence field directly (not parsed from text!)'
        )
        content = content.replace(
            'pred_conf = 75\n        if "%" in prob:',
            'pred_conf = p.get("confidence", 75)\n        if False:  # Disabled old text parsing'
        )
    else:
        print('Could not find pattern to fix')

with open('/root/Mining-Gaurdian/api/ai_dashboard_api.py', 'w') as f:
    f.write(content)

print('Saved!')
