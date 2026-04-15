#!/usr/bin/env python3
"""
Fix overnight_automation.py to store confidence in notes field.
"""

with open('/root/Mining-Gaurdian/core/overnight_automation.py', 'r') as f:
    content = f.read()

# Add confidence calculation import at top if not present
if 'from ai.confidence_scorer import get_confidence' not in content:
    # Add import after existing imports
    old_imports = 'from core.database import get_db'
    new_imports = '''from core.database import get_db

# Import confidence scorer for audit logging
try:
    from ai.confidence_scorer import get_confidence
    _has_confidence_scorer = True
except ImportError:
    _has_confidence_scorer = False'''
    
    if old_imports in content:
        content = content.replace(old_imports, new_imports)
        print('Added confidence_scorer import')

# Replace the notes field to include confidence
old_notes = '"Auto-executed during overnight window"'
new_notes = '''f"Auto-executed during overnight window | Conf:{_calc_conf(action)}%"'''

# Also need to add the helper function
helper_func = '''

def _calc_conf(action):
    """Calculate confidence for audit logging."""
    if not _has_confidence_scorer:
        return 75
    try:
        conf, _ = get_confidence(
            str(action.get("miner_id", "")),
            action.get("ip", ""),
            action.get("action_type", "RESTART")
        )
        return conf
    except:
        return 75

'''

# Add helper function before execute_action
if '_calc_conf' not in content:
    # Find a good spot - before execute_action function
    insert_point = 'def execute_action(action: dict) -> dict:'
    if insert_point in content:
        content = content.replace(insert_point, helper_func + insert_point)
        print('Added _calc_conf helper function')

# Now replace the notes
if old_notes in content:
    content = content.replace(old_notes, new_notes)
    print('Updated notes to include confidence')
else:
    print('Notes pattern not found')

with open('/root/Mining-Gaurdian/core/overnight_automation.py', 'w') as f:
    f.write(content)

print('Saved!')
