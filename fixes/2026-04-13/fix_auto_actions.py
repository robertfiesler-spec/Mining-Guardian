#!/usr/bin/env python3
"""
Fix Recent Autonomous Actions to show REAL confidence.

Since historical audit log entries don't have confidence stored,
we calculate it on-the-fly using the confidence_scorer module.
"""

with open('/root/Mining-Gaurdian/api/ai_dashboard_api.py', 'r') as f:
    content = f.read()

# Fix the auto-actions loop to calculate confidence using confidence_scorer
old_block = '''    # Auto-action rows
    ar = ""
    for a in autos:
        oc = a.get("outcome") or "—"
        bc = {
            "SUCCESS": G, "FAILURE": R, "PARTIAL": O
        }.get(oc, TD)
        badge = f'<span style="background:{bc};color:white;padding:2px 8px;border-radius:4px;font-size:11px">{_e(oc)}</span>'
        ts = str(a.get("timestamp", ""))[:16]
        # Get confidence from notes if available
        notes = str(a.get("notes", "") or "")
        auto_conf = 75
        if "Conf:" in notes:
            try:
                auto_conf = int(notes.split("Conf:")[1].split("%")[0].strip())
            except:
                pass
        elif "confidence" in notes.lower():
            try:
                # re already imported at top
                m = re.search(r'(\\d+)%', notes)
                if m:
                    auto_conf = int(m.group(1))
            except:
                pass
        auto_conf_color = G if auto_conf >= 80 else O if auto_conf >= 50 else R'''

new_block = '''    # Auto-action rows — calculate confidence dynamically
    # Import confidence scorer for on-the-fly calculation
    try:
        import sys
        _ai_path = str(Path(__file__).parent.parent / "ai")
        if _ai_path not in sys.path:
            sys.path.insert(0, _ai_path)
        from confidence_scorer import get_confidence
        _has_scorer = True
    except:
        _has_scorer = False
    
    ar = ""
    for a in autos:
        oc = a.get("outcome") or "—"
        bc = {
            "SUCCESS": G, "FAILURE": R, "PARTIAL": O
        }.get(oc, TD)
        badge = f'<span style="background:{bc};color:white;padding:2px 8px;border-radius:4px;font-size:11px">{_e(oc)}</span>'
        ts = str(a.get("timestamp", ""))[:16]
        
        # Calculate confidence dynamically using confidence_scorer
        auto_conf = 75  # fallback
        if _has_scorer:
            try:
                miner_id = str(a.get("miner_id", ""))
                ip = a.get("ip", "")
                action_type = a.get("action_taken", "RESTART")
                auto_conf, _ = get_confidence(miner_id, ip, action_type)
            except:
                pass
        
        auto_conf_color = G if auto_conf >= 80 else O if auto_conf >= 50 else R'''

if old_block in content:
    content = content.replace(old_block, new_block)
    print('Fixed auto-action rows to calculate confidence dynamically')
else:
    print('Old block not found - trying partial match...')
    if 'auto_conf = 75' in content and '# Get confidence from notes' in content:
        print('Found partial - manual fix needed')
    else:
        print('Pattern not found')

with open('/root/Mining-Gaurdian/api/ai_dashboard_api.py', 'w') as f:
    f.write(content)

print('Saved!')
