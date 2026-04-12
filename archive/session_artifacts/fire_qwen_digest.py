#!/usr/bin/env python3
import json, urllib.request, time
hdr = open("/tmp/qwen_prompt_header.txt").read()
k = json.load(open("/root/Mining-Gaurdian/knowledge.json"))
raw = k["cross_miner_analysis"][0]["analysis"]
full_prompt = hdr + raw
print("PROMPT CHARS:", len(full_prompt))
payload = {"model": "qwen2.5:32b", "prompt": full_prompt, "stream": False, "options": {"temperature": 0.3, "num_ctx": 32768}}
req = urllib.request.Request("http://100.110.87.1:11434/api/generate",
    data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
print("FIRING QWEN...")
t0 = time.time()
with urllib.request.urlopen(req, timeout=900) as r:
    resp = json.loads(r.read().decode())
elapsed = time.time() - t0
digest = resp.get("response", "")
print(f"DONE in {elapsed:.1f}s, response len={len(digest)}")
open("/root/Mining-Gaurdian/qwen_digest_20260410.txt", "w").write(digest)
open("/root/Mining-Gaurdian/qwen_digest_20260410.meta.json", "w").write(json.dumps({
    "elapsed_s": elapsed, "prompt_chars": len(full_prompt),
    "response_chars": len(digest), "model": resp.get("model"),
    "eval_count": resp.get("eval_count"),
    "prompt_eval_count": resp.get("prompt_eval_count"),
}, indent=2))
print("SAVED to qwen_digest_20260410.txt")
print("===PREVIEW (first 800 chars)===")
print(digest[:800])
