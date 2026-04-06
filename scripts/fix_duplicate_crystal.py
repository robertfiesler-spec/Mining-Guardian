#!/usr/bin/env python3
"""Remove duplicate crystal ball Slack posting block."""
with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/core/mining_guardian.py") as f:
    c = f.read()

marker = "# Post to Slack so operator can approve/deny"
first = c.index(marker)
try:
    second = c.index(marker, first + 1)
    # Find the end of the second block
    end = c.index('except Exception as ex:', second)
    # Find the next line after the debug log
    end = c.index('\n', end + 80)
    c = c[:second] + c[end:]
    with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/core/mining_guardian.py", "w") as f:
        f.write(c)
    print("Duplicate removed from committed code")
except ValueError:
    print("Only one copy found — already clean")
