#!/usr/bin/env python3
"""Fix deny handler — pass inline reason, store it, skip follow-up if provided."""

with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/api/slack_approval_listener.py") as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    
    # Find the "else:  # DENY" line and replace the block
    if "else:  # DENY" in line and "resp" not in line:
        # Write the new deny block
        indent = line[:line.index("else")]
        new_lines.append(line)  # keep the else: # DENY line
        
        # Skip old deny block lines until we hit the chat_postMessage
        i += 1
        while i < len(lines) and "chat_postMessage" not in lines[i]:
            i += 1
        
        # Write new deny logic before chat_postMessage
        new_lines.append(f"{indent}    deny_payload = {{\n")
        new_lines.append(f'{indent}        "thread_ts": thread_ts, "user": user_name, "user_id": user_id\n')
        new_lines.append(f"{indent}    }}\n")
        new_lines.append(f"{indent}    if selector:  # inline reason from 'DENY reason here'\n")
        new_lines.append(f'{indent}        deny_payload["reason"] = selector\n')
        new_lines.append(f"{indent}    resp = requests.post(f\"{{APPROVAL_API}}/deny\", json=deny_payload, timeout=15)\n")
        new_lines.append(f"{indent}    count = resp.json().get(\"count\", 0)\n")
        new_lines.append(f"{indent}    if selector:\n")
        new_lines.append(f'{indent}        msg = f"❌ *DENIED* by {{user_name}} — {{count}} action(s) cancelled.\\n💬 Reason: _{{selector}}_"\n')
        new_lines.append(f"{indent}    else:\n")
        new_lines.append(f'{indent}        msg = f"❌ *DENIED* by {{user_name}} — {{count}} action(s) cancelled."\n')
        # Now continue with chat_postMessage line
        continue
    
    # Find the denial reason capture and add inline reason handling
    if "if action == \"DENY\":" in line and "_capture_denial_reason" in (lines[i+1] if i+1 < len(lines) else ""):
        indent = line[:line.index("if")]
        new_lines.append(f"{indent}if action == \"DENY\" and not selector:\n")
        i += 1
        continue
    
    new_lines.append(line)
    i += 1

with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/api/slack_approval_listener.py", "w") as f:
    f.writelines(new_lines)

print("FIXED: Deny handler updated with inline reason support")
