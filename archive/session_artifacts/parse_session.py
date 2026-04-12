#!/usr/bin/env python3
"""Parse an OpenClaw session jsonl file and print a human-readable transcript."""
import sys, json

for ln in sys.stdin:
    try:
        d = json.loads(ln)
    except Exception:
        continue
    t = d.get("type", "?")
    if t == "session":
        print("SESSION_START", d.get("timestamp"))
    elif t == "model_change":
        print("MODEL_CHANGE", d.get("provider"), d.get("modelId"))
    elif t == "message":
        m = d.get("message", {})
        role = m.get("role")
        content = m.get("content", [])
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        for c in content:
            ct = c.get("type", "text") if isinstance(c, dict) else "text"
            if ct == "text":
                txt = c.get("text", "") if isinstance(c, dict) else str(c)
                print("[" + str(role) + "][text] " + txt[:500])
            elif ct == "tool_use":
                name = c.get("name")
                inp = json.dumps(c.get("input", {}))[:300]
                print("[" + str(role) + "][TOOL_USE name=" + str(name) + "] input=" + inp)
            elif ct == "tool_result":
                tr = c.get("content", "")
                if isinstance(tr, list):
                    pieces = []
                    for x in tr:
                        if isinstance(x, dict):
                            pieces.append(str(x.get("text", x)))
                        else:
                            pieces.append(str(x))
                    tr = " ".join(pieces)
                print("[" + str(role) + "][TOOL_RESULT] " + str(tr)[:500])
            else:
                print("[" + str(role) + "][" + str(ct) + "]")
    elif t == "custom":
        ct = d.get("customType", "?")
        print("[CUSTOM] " + str(ct))
    else:
        print("[" + str(t) + "]")
