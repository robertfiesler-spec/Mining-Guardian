"""
llm_scan_hook.py
Mining Guardian — Post-Scan LLM Analysis Hook

Called after every scan in the main daemon loop.
Sends fleet data to local LLM, posts analysis to Slack,
and processes any new denial reasons or restart logs.

This runs EVERY scan — the LLM sees everything, learns from everything.
"""

import logging
import sqlite3
import json
from pathlib import Path
from typing import Optional, Dict

_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = str(_ROOT / "guardian.db")

logger = logging.getLogger("mining_guardian")


def run_post_scan_llm(scan_id: int, slack_client=None) -> Optional[str]:
    """
    Run local LLM analysis after a scan.

    Args:
        scan_id: The scan ID to analyze
        slack_client: SlackNotifier instance for posting results

    Returns:
        Analysis text if successful, None if LLM unavailable
    """
    try:
        from local_llm_analyzer import LocalLLMAnalyzer

        # Load LLM URL from config
        llm_url = None
        model = None
        config_path = _ROOT / "config.json"
        if config_path.exists():
            try:
                cfg = json.loads(config_path.read_text())
                llm_url = cfg.get("local_llm_url")
                model = cfg.get("local_llm_model")
            except Exception:
                pass

        analyzer = LocalLLMAnalyzer(llm_url=llm_url, model=model)

        # Check if LLM is available before spending time building context
        if not analyzer.is_available():
            logger.debug("Local LLM not available — skipping scan analysis")
            return None

        # Run scan analysis
        analysis = analyzer.analyze_scan(scan_id)

        if analysis and slack_client:
            # Post to Slack as the AI's interpretation -> #mg-ai-reports
            try:
                msg = f":brain: *Mining Guardian AI Analysis — Scan #{scan_id}*\n{analysis}"
                # Truncate if too long for Slack
                if len(msg) > 3000:
                    msg = msg[:2950] + "\n_...truncated_"
                slack_client.post_to_ai_reports(msg)
            except Exception as e:
                logger.debug("Failed to post LLM analysis to Slack: %s", e)

        return analysis

    except ImportError:
        logger.debug("local_llm_analyzer not available — skipping")
        return None
    except Exception as e:
        logger.warning("Post-scan LLM analysis failed (non-fatal): %s", e)
        return None


def run_log_comparison_llm(miner_id: str, pre_log: str, post_log: str,
                            miner_info: Dict, slack_client=None) -> Optional[str]:
    """
    Run LLM comparison of pre/post restart logs.

    Called after a restart when both pre and post logs are collected.
    The LLM reads both logs and reports what changed.
    """
    try:
        from local_llm_analyzer import LocalLLMAnalyzer

        analyzer = LocalLLMAnalyzer()
        if not analyzer.is_available():
            return None

        analysis = analyzer.analyze_restart_logs(miner_id, pre_log, post_log, miner_info)

        if analysis and slack_client:
            ip = miner_info.get("ip", miner_id)
            model = miner_info.get("model", "?")
            try:
                msg = (
                    f":mag: *Restart Log Analysis — {ip} ({model})*\n"
                    f"{analysis}"
                )
                if len(msg) > 3000:
                    msg = msg[:2950] + "\n_...truncated_"
                slack_client.post_to_logs(msg)
            except Exception as e:
                logger.debug("Failed to post log analysis to Slack: %s", e)

        return analysis

    except Exception as e:
        logger.warning("Log comparison LLM failed (non-fatal): %s", e)
        return None


def run_denial_processing_llm(ip: str, action: str, reason: str,
                               slack_client=None) -> Optional[str]:
    """
    Process a denial reason through the LLM immediately.

    When the operator denies an action and gives a reason, the LLM
    interprets it and suggests an operational rule. This is real-time
    learning — not waiting for the weekly Claude training.
    """
    try:
        from local_llm_analyzer import LocalLLMAnalyzer

        analyzer = LocalLLMAnalyzer()
        if not analyzer.is_available():
            return None

        rule = analyzer.process_denial(ip, action, reason)

        if rule and slack_client:
            try:
                msg = (
                    f":bulb: *AI Learning from Denial*\n"
                    f"Operator denied {action} on {ip}\n"
                    f"Reason: _{reason}_\n\n"
                    f"*Suggested rule:* {rule}"
                )
                slack_client.post_to_ai_reports(msg)
            except Exception as e:
                logger.debug("Failed to post denial learning to Slack: %s", e)

        return rule

    except Exception as e:
        logger.warning("Denial processing LLM failed (non-fatal): %s", e)
        return None
