PATH = '/Users/BigBobby/Documents/GitHub/Mining Gaurdian/core/mining_guardian.py'
with open(PATH) as f:
    src = f.read()

old = '''                km.add_llm_insight(
                    miner_id=f"compare:{miner_id}",
                    insight=analysis,
                    source=f"log_comparison_{action_label}",
                    confidence=None,
                )'''

new = '''                # add_llm_insight signature: (insight, miner_id="fleet")
                # Use a special miner_id format so the dashboard can render
                # these as a distinct "log comparison" category.
                km.add_llm_insight(
                    analysis,
                    miner_id=f"compare:{action_label}:{miner_id}",
                )'''

if old not in src:
    print("ERROR: add_llm_insight call site not found")
    exit(1)
src = src.replace(old, new)
with open(PATH, 'w') as f:
    f.write(src)
print("Fixed add_llm_insight call signature")
