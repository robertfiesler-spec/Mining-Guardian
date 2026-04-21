"""
OpenClaw Notifier
Extracted from mining_guardian.py on April 21, 2026

Sends notifications via OpenClaw webhook for Slack integration.
"""

import os
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

class OpenClawNotifier:
    def __init__(self, webhook_url: Optional[str]):
        self.webhook_url = webhook_url

    def send_scan(self, miners: List[Dict], issues: List[Dict]) -> None:
        """POST scan results to OpenClaw webhook.

        OpenClaw receives this payload, passes it to the local LLM,
        and the LLM posts a plain-English summary + recommendations
        to Slack for operator review and approval.
        """
        if not self.webhook_url:
            logger.debug("OpenClaw webhook not configured — skipping notification")
            return

        now    = datetime.now().strftime("%Y-%m-%d %H:%M")
        online = sum(1 for m in miners if m.get("status") == "online")

        # Build a plain-English summary line for the LLM to work with
        pdu_cycles  = [i for i in issues if i["action"] == "PDU_CYCLE"]
        fw_restarts = [i for i in issues if i["action"] == "RESTART"]
        monitors    = [i for i in issues if i["action"] == "MONITOR"]
        temp_action = [i for i in issues if i["action"] == "TEMP_ACTION_REQUIRED"]

        pdu_cycles_oc  = [i for i in issues if i["action"] == "PDU_CYCLE"]
        fw_restarts_oc = [i for i in issues if i["action"] == "RESTART"]
        board_restarts_oc = [i for i in issues if i["action"] == "RESTART_CHECK_BOARDS"]
        phys_oc        = [i for i in issues if i["action"] == "PHYSICAL_CYCLE"]
        monitors_oc    = [i for i in issues if i["action"] == "MONITOR"]
        temp_oc        = [i for i in issues if i["action"] == "TEMP_ACTION_REQUIRED"]

        parts = []
        if pdu_cycles_oc:
            parts.append(f"{len(pdu_cycles_oc)} offline miner(s) need PDU power cycle")
        if fw_restarts_oc:
            parts.append(f"{len(fw_restarts_oc)} miner(s) need firmware restart")
        if board_restarts_oc:
            dead_details = ", ".join(
                f"{i['ip']} boards {i.get('chain_info', {}).get('dead_indices', [])}"
                for i in board_restarts_oc
            )
            parts.append(
                f"{len(board_restarts_oc)} miner(s) have dead hashboard(s) — "
                f"restart + log comparison required ({dead_details})"
            )
        if phys_oc:
            parts.append(f"{len(phys_oc)} offline miner(s) need physical power cycle at facility")
        if temp_oc:
            parts.append(f"{len(temp_oc)} miner(s) have critical chip temps (86°C+)")
        # Yellow zone miners omitted from summary — stored in DB for learning only
        summary = ". ".join(parts) + "." if parts else "All miners operating normally."
        payload = {
            "source":     "mining_guardian",
            "scanned_at": now,
            "fleet": {
                "total":   len(miners),
                "online":  online,
                "offline": len(miners) - online,
                "issues":  len(issues),
            },
            "summary": summary,
            "issues": [
                {
                    "miner_id":    i["id"],
                    "ip":          i["ip"],
                    "model":       i["model"],
                    "status":      i["status"],
                    "hashrate":    i["hashrate_pct"],
                    "temp_chip":   i["temp_chip"],
                    "action":      i["action"],
                    "pdu_action":  i.get("pdu_action"),
                    "detail":      " | ".join(i["issues"]),
                    "map_location": i.get("map_location", "N/A"),
                    "active_profile": i.get("active_profile", "N/A"),
                    "pdu_power_kw":   i.get("pdu_power_kw", None),
                }
                for i in issues
            ],
            # Instruction for the LLM — tells it what to do with this data
            "instructions": (
                "You are Mining Guardian's AI analyst for BiXBiT USA in Fort Worth, TX. "
                "Review the fleet scan below and post a concise Slack message to #mining-guardian. "
                "For each miner needing action, include: IP, model, map location, active profile, "
                "PDU power draw, and recommended fix. "
                "Ask the operator to reply APPROVE or DENY in the thread to confirm actions. "
                "Keep it professional and brief."
            ),
        }

        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info("OpenClaw notified — scan summary sent")
            else:
                logger.warning("OpenClaw webhook returned %s", resp.status_code)
        except Exception as exc:
            logger.warning("OpenClaw notification failed: %s", exc)



# ------------------------------------------------------------
# Remediation cooldown — unchanged
# ------------------------------------------------------------

