#!/usr/bin/env python3
"""Fix the ai_dashboard_api.py junk lines."""
with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/api/ai_dashboard_api.py") as f:
    content = f.read()

# Find the junk: everything between '"""<tr>' and the next proper line
# The problem is a fragment starting with '"""<tr>' on line ~441
idx = content.find('"""<tr>')
if idx > 0:
    # Find the end of the junk (next proper HTML line)
    end_idx = content.find('</tr>\n', idx)
    if end_idx > 0:
        end_idx = content.find('\n', end_idx + 1)
        junk = content[idx:end_idx]
        content = content[:idx] + content[end_idx:]
        print(f"Removed {len(junk)} chars of junk")
    else:
        print("Could not find end of junk")
else:
    print("No junk found")

with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/api/ai_dashboard_api.py", "w") as f:
    f.write(content)
print("File cleaned")
