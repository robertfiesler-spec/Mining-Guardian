#!/usr/bin/env python3
"""Fix outcome_checker.py indentation."""
path = "/Users/BigBobby/Documents/GitHub/Mining Gaurdian/ai/outcome_checker.py"
with open(path) as f:
    lines = f.readlines()

fixes = {
    247: '            # Atomic write \u2014 crash-safe\n',
    248: '            _tmp = str(KNOWLEDGE_PATH) + ".tmp"\n',
    249: '            with open(_tmp, "w") as f:\n',
    250: '                json.dump(knowledge, f, indent=2)\n',
    251: '            os.replace(_tmp, str(KNOWLEDGE_PATH))\n',
}

for idx, replacement in fixes.items():
    lines[idx-1] = replacement

with open(path, "w") as f:
    f.writelines(lines)
print("FIXED")
