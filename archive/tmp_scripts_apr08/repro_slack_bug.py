"""Reproduce the exact API call slack_command_handler.py makes for Bobby's
'what are my best miners top 5' question, see what fails.
"""
import os, sys, json, requests
from pathlib import Path

env_path = Path("/root/Mining-Gaurdian/.env")
for line in env_path.read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

key = os.environ["ANTHROPIC_API_KEY"]

system = (
    "You are Mining Guardian AI, the fleet intelligence system for BiXBiT USA "
    "in Fort Worth, TX. You have full access to real-time fleet data, miner history, "
    "audit logs, and learned patterns. All cooling is liquid — hydro racks and "
    "immersion tank. No air cooling. Answer the operator's question directly and "
    "specifically using the data provided. Be concise but complete. "
    "If recommending an action, say exactly which miner IPs and what to do."
)

# Simulate a minimal fleet context (the real one is huge, this proves the API works
# regardless of context size)
prompt = (
    "FLEET CONTEXT: 49 miners, 42 online, 7 offline.\n"
    "\n\nOPERATOR QUESTION: what are my best miners top 5\n"
    "\n\nProvide a direct, specific answer using the fleet data above."
)

print("REQUEST:")
print(f"  model: claude-sonnet-4-6")
print(f"  max_tokens: 800")
print(f"  system: {len(system)} chars")
print(f"  prompt: {len(prompt)} chars")
print()

try:
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 800,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        },
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    print(f"HTTP {resp.status_code}")
    body = resp.json()
    print("Top-level keys:", list(body.keys()))
    print()
    print("FULL RESPONSE:")
    print(json.dumps(body, indent=2)[:2000])
    print()
    if "content" in body:
        answer = body["content"][0]["text"]
        print(f"\nEXTRACTED ANSWER ({len(answer)} chars):")
        print(answer[:500])
    else:
        print("\n*** NO 'content' KEY IN RESPONSE — this is the bug ***")
except Exception as e:
    print(f"EXCEPTION: {type(e).__name__}: {e}")
