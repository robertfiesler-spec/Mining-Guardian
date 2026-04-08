"""claude_log_comparison.py — Pre/post log comparison via Claude API

Mirror of ai/llm_scan_hook.run_log_comparison_llm but routed to Claude API
(claude-sonnet-4-6) instead of local Qwen.

Used during the dual-model jump-start phase: until we have 10+ comparison
runs from each model, we run BOTH local Qwen AND Claude on every pre/post
pair so the operator can see differences between the two analyses and the
local model can learn from Claude's diagnostic style.

After 10 runs of each, the cohort training script will use the accumulated
side-by-side data to fine-tune the local model's prompts and we can decide
whether to keep dual-mode permanently or fall back to local-only for
day-to-day with Claude reserved for weekly training.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Optional

import requests
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

logger = logging.getLogger("claude_log_comparison")

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL   = "claude-sonnet-4-6"
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"


def _build_comparison_prompt(miner_id: str, pre_log: str, post_log: str,
                             miner_info: Dict) -> str:
    """Build the same prompt structure used for the local Qwen comparison.

    Aligned with ai/local_llm_analyzer.LocalLLMAnalyzer._build_log_analysis_prompt
    so the two model outputs are directly comparable. Same operator rules
    apply: 84°C temp threshold, HVAC delta-T is correct.
    """
    ip       = miner_info.get("ip", "?")
    model    = miner_info.get("model", "?")
    action   = miner_info.get("action", "restart")

    # Truncate logs if absurdly long to stay within Claude API limits.
    # Claude Sonnet 4.6 takes 200K context but we keep prompts focused.
    MAX_LOG_CHARS = 80_000
    pre_truncated  = pre_log[:MAX_LOG_CHARS]
    post_truncated = post_log[:MAX_LOG_CHARS]
    pre_note  = f" (truncated from {len(pre_log)} bytes)" if len(pre_log) > MAX_LOG_CHARS else ""
    post_note = f" (truncated from {len(post_log)} bytes)" if len(post_log) > MAX_LOG_CHARS else ""

    return f"""You are a Bitcoin miner diagnostic expert. Compare these pre-{action} and post-{action} miner.log files from a single miner and report what changed.

OPERATOR RULES (always apply, never violate):
1. TEMPERATURE: do NOT describe chip temperatures below 84°C as "overheating", "high", or "concerning". This is a liquid-cooled fleet that runs 67-73°C normally. Only flag temps at or above 84°C as a problem.
2. HVAC: the HVAC system at this site is performing perfectly. The supply/return water delta-T is intentionally low and will rise as outside temperatures climb seasonally. NEVER recommend "check HVAC" or "investigate cooling" based on a low delta-T.

MINER:
  ID:    {miner_id}
  IP:    {ip}
  Model: {model}

PRE-{action.upper()} LOG ({len(pre_log)} bytes{pre_note}):
```
{pre_truncated}
```

POST-{action.upper()} LOG ({len(post_log)} bytes{post_note}):
```
{post_truncated}
```

Your analysis must follow this exact structure. Be concise — max 600 words total:

1. **Errors before {action}**: list specific WARN/ERROR/FAULT lines from the pre log
2. **Errors cleared after {action}**: which pre-log errors are gone in the post log
3. **New errors after {action}**: which post-log errors are NEW (not in the pre log)
4. **Board health comparison**: voltage, frequency, chip counts, ASIC status — same/different on each chain
5. **Verdict**: did the {action} fix the root cause? If not, what physical action is needed (PSU replacement / control board / specific chain repair / coolant / etc.)?
6. **Confidence**: HIGH / MEDIUM / LOW that your verdict is correct, and one sentence why

Do NOT speculate about anything not visible in the logs."""


def query_claude(prompt: str, timeout: int = 120) -> Optional[str]:
    """Send prompt to Claude API and return the text response, or None on error."""
    if not CLAUDE_API_KEY:
        logger.warning("CLAUDE_API_KEY not set in environment — cannot run Claude comparison")
        return None
    try:
        logger.info("Sending to Claude API (%d chars)...", len(prompt))
        resp = requests.post(
            CLAUDE_API_URL,
            json={
                "model":      CLAUDE_MODEL,
                "max_tokens": 4096,
                "messages":   [{"role": "user", "content": prompt}],
            },
            headers={
                "x-api-key":         CLAUDE_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type":      "application/json",
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        for block in data.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                logger.info("Claude responded (%d chars)", len(text))
                return text
        logger.warning("Claude response had no text blocks: %s", data)
        return None
    except requests.exceptions.HTTPError as e:
        logger.warning("Claude HTTP error %s: %s", e.response.status_code if e.response else "?", e)
        return None
    except requests.exceptions.Timeout:
        logger.warning("Claude API timed out after %ss", timeout)
        return None
    except Exception as e:
        logger.warning("Claude API call failed: %s", e)
        return None


def compare_logs_via_claude(miner_id: str, pre_log: str, post_log: str,
                             miner_info: Dict) -> Optional[str]:
    """Run pre/post log comparison via Claude API. Returns analysis text or None.

    Mirror of ai.local_llm_analyzer.LocalLLMAnalyzer.analyze_restart_logs
    but uses Claude Sonnet 4.6 instead of local Qwen.
    """
    if not pre_log or not post_log:
        logger.info("[%s] Skipping Claude comparison — empty pre or post log", miner_id)
        return None

    prompt = _build_comparison_prompt(miner_id, pre_log, post_log, miner_info)
    return query_claude(prompt)


def is_available() -> bool:
    """Return True if the Claude API key is configured."""
    return bool(CLAUDE_API_KEY)
