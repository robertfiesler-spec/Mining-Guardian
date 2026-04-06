#!/usr/bin/env python3
"""Fix outcome_checker.py atomic write indentation."""
import os

path = "/Users/BigBobby/Documents/GitHub/Mining Gaurdian/ai/outcome_checker.py"
with open(path) as f:
    c = f.read()

old = '''        profile["last_updated"] = datetime.now().isoformat()

        # Atomic write — crash-safe
    _tmp = str(KNOWLEDGE_PATH) + ".tmp"
    with open(_tmp, "w") as f:
            json.dump(knowledge, f, indent=2)
    os.replace(_tmp, str(KNOWLEDGE_PATH))
    except Exception as e:'''

new = '''        profile["last_updated"] = datetime.now().isoformat()

            # Atomic write — crash-safe
            _tmp = str(KNOWLEDGE_PATH) + ".tmp"
            with open(_tmp, "w") as f:
                json.dump(knowledge, f, indent=2)
            os.replace(_tmp, str(KNOWLEDGE_PATH))
    except Exception as e:'''

if old in c:
    c = c.replace(old, new)
    with open(path, "w") as f:
        f.write(c)
    print("FIXED")
else:
    print("Pattern not found — checking manually")
    # Show context
    idx = c.find("_tmp = str(KNOWLEDGE_PATH)")
    if idx > 0:
        print(c[idx-100:idx+200])
