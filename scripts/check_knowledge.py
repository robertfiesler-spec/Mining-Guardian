#!/usr/bin/env python3
import json
d = json.load(open("knowledge.json"))
print(f"Issues: {len(d.get('known_issues',[]))}")
print(f"Patterns: {len(d.get('patterns',[]))}")
print(f"Profiles: {len(d.get('miner_profiles',{}))}")
print(f"Cross-miner: {'cross_miner_analysis' in d}")
print(f"Last updated: {d.get('last_updated','?')[:19]}")
