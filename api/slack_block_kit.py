"""
slack_block_kit.py
Mining Guardian — Slack Block Kit Message Builder

Builds rich Slack messages with buttons, checkboxes, and dropdowns.
Mining Guardian posts these directly via Slack API.
Interactive payloads (button clicks) are handled by approval_api.py.

This replaces the plain-text scan messages with rich interactive UI.
"""

import json
import logging
from typing import List, Dict, Optional

logger = logging.getLogger("mining_guardian")


def build_scan_blocks(scan_summary: Dict, issues: List[Dict],
                      weather: Dict = None, hvac: Dict = None,
                      llm_analysis: str = None) -> List[Dict]:
    """Build Block Kit blocks for a scan summary message."""
    blocks = []

    # Header
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"🤖 Mining Guardian Scan — {scan_summary.get('time', 'now')}",
        }
    })

    # Fleet status
    online = scan_summary.get("online", 0)
    offline = scan_summary.get("offline", 0)
    total = scan_summary.get("total", online + offline)
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*Fleet:* {total} miners | 🟢 {online} online | 🔴 {offline} offline"
        }
    })

    # Weather + HVAC
    env_parts = []
    if weather:
        env_parts.append(f"🌡️ Outside: *{weather.get('temp_f', '?')}°F* | Humidity: {weather.get('humidity_pct', '?')}%")
    if hvac:
        env_parts.append(
            f"🏭 Supply: *{hvac.get('supply_temp_f', '?')}°F* | "
            f"Return: *{hvac.get('return_temp_f', '?')}°F* | "
            f"ΔT: *{hvac.get('delta_t_f', '?')}°F*"
        )
    if env_parts:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(env_parts)}
        })

    # LLM Analysis (if available)
    if llm_analysis:
        # Truncate to fit Slack's 3000 char limit per text block
        truncated = llm_analysis[:2500]
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🧠 *AI Analysis:*\n{truncated}"
            }
        })

    # Actionable issues with buttons
    actionable = [i for i in issues
                  if i.get("action") in ("RESTART", "PDU_CYCLE", "RESTART_CHECK_BOARDS")]

    if actionable:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"⚠️ *{len(actionable)} action(s) need your decision:*"
            }
        })

        for issue in actionable[:10]:
            ip = issue.get("ip", "?")
            model = issue.get("model", "?")
            action = issue.get("action", "?")
            hr = issue.get("hashrate_pct", "?")
            temp = issue.get("temp_chip", "?")
            miner_id = issue.get("id", "?")

            # Action label
            action_label = {
                "RESTART": "🔄 Restart",
                "PDU_CYCLE": "🔌 PDU Cycle",
                "RESTART_CHECK_BOARDS": "🔧 Board Check",
            }.get(action, action)

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{ip}* ({model})\n"
                        f"HR: {hr}% | Temp: {temp}°C | Action: {action_label}"
                    )
                },
                "accessory": {
                    "type": "overflow",
                    "action_id": f"miner_action_{miner_id}",
                    "options": [
                        {
                            "text": {"type": "plain_text", "text": "✅ Approve"},
                            "value": f"approve_{miner_id}"
                        },
                        {
                            "text": {"type": "plain_text", "text": "❌ Deny"},
                            "value": f"deny_{miner_id}"
                        },
                    ]
                }
            })

    # Batch actions (if multiple actionable)
    if len(actionable) > 1:
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Approve All"},
                    "action_id": "approve_all",
                    "style": "primary",
                    "value": json.dumps({"action": "approve_all"}),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ Deny All"},
                    "action_id": "deny_all",
                    "style": "danger",
                    "value": json.dumps({"action": "deny_all"}),
                },
            ]
        })

    return blocks


def build_recommendation_blocks(recommendations: List[Dict]) -> List[Dict]:
    """Build Block Kit for AI recommendations (crystal ball messages)."""
    blocks = []

    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": f"🔮 AI Recommendations — {len(recommendations)} pending"}
    })

    # Checkboxes for batch selection
    if recommendations:
        options = []
        for rec in recommendations[:10]:
            ip = rec.get("ip", "?")
            action = rec.get("action", "?")
            conf = rec.get("confidence", "?")
            reason = rec.get("reasons", [""])[0] if rec.get("reasons") else ""
            options.append({
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{ip}* — {action} ({conf}% conf) _{reason[:60]}_"
                },
                "value": f"{rec.get('miner_id', '')}:{action}"
            })

        blocks.append({
            "type": "actions",
            "elements": [{
                "type": "checkboxes",
                "action_id": "recommendation_select",
                "options": options,
            }]
        })

        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Approve Selected"},
                    "action_id": "approve_selected_recs",
                    "style": "primary",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Approve All"},
                    "action_id": "approve_all_recs",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ Deny All"},
                    "action_id": "deny_all_recs",
                    "style": "danger",
                },
            ]
        })

    return blocks


def build_denial_reason_blocks(miner_ip: str, action: str,
                                miner_id: str) -> List[Dict]:
    """Build Block Kit for denial reason collection."""
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"❌ *Denied* — {action} on `{miner_ip}`\n💬 *Why did you deny?*"
            }
        },
        {
            "type": "actions",
            "elements": [{
                "type": "static_select",
                "action_id": f"denial_reason_{miner_id}",
                "placeholder": {"type": "plain_text", "text": "Select a reason..."},
                "options": [
                    {
                        "text": {"type": "plain_text", "text": "⏱️ Just restarted — wait 20 min"},
                        "value": "recent_restart:Miner just restarted, need to wait 20 minutes for stability"
                    },
                    {
                        "text": {"type": "plain_text", "text": "🌡️ Outside temp rising — save headroom"},
                        "value": "thermal_headroom:Outside temperature is rising, saving thermal headroom"
                    },
                    {
                        "text": {"type": "plain_text", "text": "🔧 Known hardware issue — needs repair"},
                        "value": "hardware_issue:Known hardware issue, restart won't help, needs physical repair"
                    },
                    {
                        "text": {"type": "plain_text", "text": "📊 Not enough data yet — monitoring"},
                        "value": "insufficient_data:Not enough data to make this decision yet, continue monitoring"
                    },
                    {
                        "text": {"type": "plain_text", "text": "🔄 Already handled manually"},
                        "value": "manual_handled:Already handled this manually through AMS"
                    },
                ]
            }]
        },
        {
            "type": "input",
            "dispatch_action": True,
            "element": {
                "type": "plain_text_input",
                "action_id": f"denial_custom_{miner_id}",
                "placeholder": {"type": "plain_text", "text": "Or type a custom reason..."},
            },
            "label": {"type": "plain_text", "text": "Custom reason"},
            "optional": True,
        },
    ]
    return blocks
