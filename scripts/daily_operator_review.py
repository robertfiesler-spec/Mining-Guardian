#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import os
from notifiers.slack_notifier import SlackNotifier
from dotenv import load_dotenv
load_dotenv()

KNOWLEDGE_PATH = Path(__file__).parent.parent / "knowledge.json"
PENDING_PATH = Path(__file__).parent.parent / "pending_operator_reviews.json"

def load_knowledge():
    with open(KNOWLEDGE_PATH) as f:
        return json.load(f)

def load_pending():
    if PENDING_PATH.exists():
        with open(PENDING_PATH) as f:
            return json.load(f)
    return {"pending": [], "history": []}

def save_pending(data):
    with open(PENDING_PATH, "w") as f:
        json.dump(data, f, indent=2)

def get_proposals(knowledge):
    proposals = []

    # Proposed rules
    for rule in knowledge.get("proposed_rules", []):
        if not rule.get("locked"):
            proposals.append({
                "type": "PROPOSED_RULE",
                "id": rule.get("id", "rule"),
                "content": rule.get("text", rule.get("description", "")),
                "confidence": rule.get("confidence", "MEDIUM"),
                "source": rule.get("source", "AI")
            })

    # Refined insights from last 24h
    for key, insight in knowledge.get("refined_insights", {}).items():
        last_updated = insight.get("last_updated", "")
        if last_updated and not insight.get("operator_approved"):
            try:
                dt = datetime.fromisoformat(last_updated.replace("Z", ""))
                if (datetime.now(timezone.utc) - dt).total_seconds() / 3600 <= 24:
                    proposals.append({
                        "type": "REFINED_INSIGHT",
                        "id": key,
                        "content": insight.get("summary", key),
                        "confidence": insight.get("confidence", "MEDIUM"),
                        "source": "refinement_chain"
                    })
            except: pass

    # Patterns not approved.
    # Note: knowledge['patterns'] is a list of strings (descriptions only) in the
    # current schema. We tolerate dicts too in case the schema evolves later.
    for idx, p in enumerate(knowledge.get("patterns", [])):
        if isinstance(p, str):
            proposals.append({
                "type": "PATTERN",
                "id": f"pattern_{idx}",
                "content": p,
                "confidence": "MEDIUM",
                "source": "pattern_detection",
            })
        elif isinstance(p, dict):
            if not p.get("operator_approved"):
                proposals.append({
                    "type": "PATTERN",
                    "id": p.get("id", f"pattern_{idx}"),
                    "content": p.get("description", ""),
                    "confidence": p.get("confidence", "MEDIUM"),
                    "source": "pattern_detection",
                })

    return proposals

def format_message(proposals):
    if not proposals:
        return None

    lines = ["*:clipboard: Daily Operator Review Required*", ""]
    lines.append("*" + str(len(proposals)) + " items need your review:*")
    lines.append("")

    for i, p in enumerate(proposals, 1):
        emoji = {"PROPOSED_RULE": ":gear:", "REFINED_INSIGHT": ":bulb:", "PATTERN": ":chart_with_upwards_trend:"}.get(p["type"], ":question:")
        conf = {"HIGH": ":large_green_circle:", "MEDIUM": ":large_yellow_circle:", "LOW": ":red_circle:"}.get(p["confidence"], ":white_circle:")

        content = p["content"][:400] + "..." if len(p["content"]) > 400 else p["content"]

        lines.append("*" + str(i) + ". " + emoji + " " + p["type"] + "* " + p["id"])
        lines.append("   " + conf + " Confidence: " + p["confidence"])
        lines.append("   Source: " + p["source"])
        if content:
            lines.append("")
        lines.append("")

    lines.append("---")
    lines.append("*Reply with:*")
    lines.append("APPROVE <num> - Lock in")
    lines.append("ADJUST <num> <changes> - Modify")
    lines.append("DENY <num> <reason> - Reject")
    lines.append("")
    lines.append("_Be specific about WHY - helps AI learn!_")

    return chr(10).join(lines)

def main():
    print("Starting daily operator review...")
    knowledge = load_knowledge()
    pending = load_pending()

    proposals = get_proposals(knowledge)
    print("Found " + str(len(proposals)) + " items")

    if not proposals:
        print("No new items")
        return

    pending["pending"] = proposals
    pending["last_generated"] = datetime.now(timezone.utc).isoformat()
    save_pending(pending)

    msg = format_message(proposals)
    if msg:
        slack = SlackNotifier(
            webhook_url=os.environ.get("SLACK_WEBHOOK_URL"),
            bot_token=os.environ.get("SLACK_BOT_TOKEN"),
        )
        slack.post_to_channel(msg, channel_id="U07AGTT8CLD")
        print("Sent to Slack")

if __name__ == "__main__":
    main()