#!/usr/bin/env python3
import json
import sys
import re
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

KNOWLEDGE_PATH = Path(__file__).parent.parent / "knowledge.json"
PENDING_PATH = Path(__file__).parent.parent / "pending_operator_reviews.json"

def load_knowledge():
    with open(KNOWLEDGE_PATH) as f:
        return json.load(f)

def save_knowledge(data):
    with open(KNOWLEDGE_PATH, "w") as f:
        json.dump(data, f, indent=2)

def load_pending():
    if PENDING_PATH.exists():
        with open(PENDING_PATH) as f:
            return json.load(f)
    return {"pending": [], "history": []}

def save_pending(data):
    with open(PENDING_PATH, "w") as f:
        json.dump(data, f, indent=2)

def process_response(text, user_id):
    pending = load_pending()
    knowledge = load_knowledge()
    
    match = re.match(r"(APPROVE|ADJUST|DENY)\s+(\d+)(?:\s+(.*))?$", text.strip(), re.IGNORECASE)
    if not match:
        return "Invalid format. Use: APPROVE/ADJUST/DENY <number> [reason]"
    
    action = match.group(1).upper()
    num = int(match.group(2))
    reason = match.group(3) or ""
    
    if not pending.get("pending"):
        return "No pending reviews found"
    
    if num < 1 or num > len(pending["pending"]):
        return "Invalid number"
    
    item = pending["pending"][num - 1]
    
    record = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "item_type": item["type"],
        "item_id": item["id"],
        "operator_id": user_id,
        "reason": reason
    }
    
    if item["type"] == "REFINED_INSIGHT":
        if action == "APPROVE":
            if item["id"] in knowledge.get("refined_insights", {}):
                knowledge["refined_insights"][item["id"]]["operator_approved"] = True
        elif action == "DENY":
            if item["id"] in knowledge.get("refined_insights", {}):
                del knowledge["refined_insights"][item["id"]]
            if "denied_insights" not in knowledge:
                knowledge["denied_insights"] = []
            knowledge["denied_insights"].append({"id": item["id"], "reason": reason})
        elif action == "ADJUST":
            if item["id"] in knowledge.get("refined_insights", {}):
                knowledge["refined_insights"][item["id"]]["operator_adjustment"] = reason
                knowledge["refined_insights"][item["id"]]["operator_approved"] = True
    
    elif item["type"] == "PATTERN":
        for p in knowledge.get("patterns", []):
            if p.get("id") == item["id"]:
                if action == "APPROVE":
                    p["operator_approved"] = True
                elif action == "DENY":
                    knowledge["patterns"] = [x for x in knowledge["patterns"] if x.get("id") != item["id"]]
    
    pending["pending"].pop(num - 1)
    if "history" not in pending:
        pending["history"] = []
    pending["history"].append(record)
    
    save_pending(pending)
    save_knowledge(knowledge)
    
    return action + " processed for " + item["type"] + " " + item["id"]

if __name__ == "__main__":
    if len(sys.argv) > 1:
        result = process_response(" ".join(sys.argv[1:]), "U07AGTT8CLD")
        print(result)
