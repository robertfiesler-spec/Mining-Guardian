#!/usr/bin/env python3
"""Fix action diversity: post to Slack and save pending approvals so they appear in queue."""
import re

with open("/root/Mining-Gaurdian/core/mining_guardian.py") as f:
    c = f.read()

# Find the action diversity block and add Slack posting + pending save
old = '''                            # Log to audit trail for tracking
                            try:
                                self.db.log_action(
                                    act["miner_id"], act["ip"],
                                    act["model"],
                                    problem="; ".join(act.get("reasons", [])),
                                    action_taken=act["action"],
                                    decision="PENDING_APPROVAL",
                                    notes=f"confidence={act['confidence']}% data={act.get('data_used',[])}",
                                )
                            except Exception:
                                pass'''

new = '''                            # Log to audit trail for tracking
                            try:
                                self.db.log_action(
                                    act["miner_id"], act["ip"],
                                    act["model"],
                                    problem="; ".join(act.get("reasons", [])),
                                    action_taken=act["action"],
                                    decision="PENDING_APPROVAL",
                                    notes=f"confidence={act['confidence']}% data={act.get('data_used',[])}",
                                )
                            except Exception:
                                pass
                            # Post to Slack so operator can approve/deny
                            try:
                                reasons_str = ", ".join(act.get("reasons", []))[:100]
                                msg = (
                                    f":crystal_ball: *AI Recommendation — {act['action']}*\\n"
                                    f"Miner: `{act['ip']}` ({act['model']})\\n"
                                    f"Confidence: *{act['confidence']}%*\\n"
                                    f"Reason: {reasons_str}\\n\\n"
                                    f"_Reply `APPROVE` to execute or `DENY <reason>` to skip._"
                                )
                                thread = self.slack.post_to_channel(msg)
                                if thread and isinstance(thread, str):
                                    issue_entry = [{
                                        "id": act["miner_id"],
                                        "ip": act["ip"],
                                        "model": act["model"],
                                        "action": act["action"],
                                        "issues": act.get("reasons", []),
                                    }]
                                    self.db.save_pending_approvals(
                                        thread, latest_scan["id"], issue_entry
                                    )
                            except Exception as ex:
                                logger.debug("Action diversity Slack post failed: %s", ex)'''

if old in c:
    c = c.replace(old, new)
    with open("/root/Mining-Gaurdian/core/mining_guardian.py", "w") as f:
        f.write(c)
    print("FIXED: Action diversity now posts to Slack + saves pending approvals")
else:
    print("ERROR: Could not find the target code block")
