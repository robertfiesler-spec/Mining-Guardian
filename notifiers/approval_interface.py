"""
Approval Interface
Extracted from mining_guardian.py on April 21, 2026

Handles manual approval requests for remediation actions.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

class ApprovalInterface:
    def __init__(self, config):  # GuardianConfig
        self.config = config

    def request_approval(self, finding):  # MinerFinding -> bool:
        summary = (
            f"  Miner : {finding.miner_id} ({finding.ip})\n"
            f"  Key   : {finding.key}\n"
            f"  Actual: {finding.actual}  →  Fix: {finding.recommended_fix}\n"
            f"  Note  : {finding.note or '—'}"
        )
        logger.info("Approval required:\n%s", summary)
        if not os.isatty(0):
            logger.warning("Headless — auto-denying miner=%s key=%s", finding.miner_id, finding.key)
            return False
        try:
            answer = input(f"\nApprove patch for {finding.miner_id} [{finding.key}]? [y/N]: ")
            return answer.strip().lower() == "y"
        except (EOFError, KeyboardInterrupt):
            logger.warning("Approval interrupted — denying.")
            return False


# ------------------------------------------------------------
# ------------------------------------------------------------
# OpenClaw notifier
# ------------------------------------------------------------
# Sends a structured JSON payload to the local OpenClaw webhook
# after every scan. OpenClaw's local LLM interprets the findings
# and posts a plain-English summary to Slack for operator review.
#
# OpenClaw Gateway runs at http://127.0.0.1:18789 by default.
# Webhook URL format: http://127.0.0.1:18789/hooks
# Requires hooks.enabled: true and hooks.token set in ~/.openclaw/openclaw.json
# Full URL example: http://127.0.0.1:18789/hooks  (token sent as Authorization header)
#
# Set openclaw_webhook_url in config.json when OpenClaw is ready.
# Leave it null to disable silently — no errors will be thrown.
# ------------------------------------------------------------

