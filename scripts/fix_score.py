#!/usr/bin/env python3
"""Fix: divide total score by 10 for better milestone psychology."""
with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/ai/ai_score.py") as f:
    c = f.read()

# Change the total calculation to divide by 10
c = c.replace(
    'total = data_score + knowledge_score + actions_score + outcomes_score + autonomy_score',
    'total = (data_score + knowledge_score + actions_score + outcomes_score + autonomy_score) // 10'
)

with open("/Users/BigBobby/Documents/GitHub/Mining Gaurdian/ai/ai_score.py", "w") as f:
    f.write(c)
print("Score divided by 10")
