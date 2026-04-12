"""Test which Anthropic model names are currently valid for this API key.
Run on the VPS where the .env lives.
"""
import os, sys, requests
from pathlib import Path

# Load .env manually
env_path = Path("/root/Mining-Gaurdian/.env")
for line in env_path.read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

key = os.environ.get("ANTHROPIC_API_KEY", "")
if not key:
    print("NO API KEY")
    sys.exit(1)

candidates = [
    "claude-sonnet-4-6",
    "claude-sonnet-4-5",
    "claude-sonnet-4-5-20250929",
    "claude-sonnet-4-20250514",
    "claude-opus-4-6",
    "claude-opus-4-5",
    "claude-opus-4-1",
    "claude-haiku-4-5",
]

for model in candidates:
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            json={
                "model": model,
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            timeout=15,
        )
        body = r.json()
        if "content" in body:
            text = body["content"][0]["text"][:30]
            print(f"OK     {model:35s} -> {text!r}")
        elif "error" in body:
            etype = body.get("error", {}).get("type", "?")
            emsg = body.get("error", {}).get("message", "?")[:80]
            print(f"FAIL   {model:35s} -> {etype}: {emsg}")
        else:
            print(f"WEIRD  {model:35s} -> {str(body)[:80]}")
    except Exception as e:
        print(f"ERR    {model:35s} -> {e}")
