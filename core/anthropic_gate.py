"""
core/anthropic_gate.py — Install-time Anthropic provisioning gate.
===================================================================

Provides `require_anthropic_or_exit(job_name, logger)` — used as the
first call inside Anthropic-dependent scheduled jobs (`weekly_train.py`
`run_weekly()`, `refinement_chain.py` `__main__`) so they exit cleanly
when Anthropic was not provisioned at install time, and fail loudly
when the install promised a key but the key is missing.

Why this exists (P-038 items #4 + #5 env-gate, 2026-05-11):
    Pre-fix behavior on a Mac Mini without ANTHROPIC_API_KEY set:
      `weekly_training` runs for ~18 minutes per Sunday, calling
      `LLMAnalyzer._query_claude` 18 times (6 cohorts × 3 retries),
      each call logging:
        WARNING:llm_analyzer:Claude API key not set —
            returning empty, no Ollama fallback
      then sleeping 30/60/90 seconds between retries. The Sunday
      scheduled run on the customer Mini wastes ~20 minutes producing
      nothing, then exits. P-038 #5 datetime-slicing fix means the job
      no longer crashes, but it still wastes the cycle.
    Pre-fix behavior of `refinement_chain.py`: pre-flight checks
      include "ANTHROPIC_API_KEY present" but raise RuntimeError on
      absence, which the __main__ block catches → `sys.exit(1)`. So
      customer Minis that don't link Anthropic see a daily refinement
      failure in `logs/scheduled/refinement_chain.last-run.json`.

Design (per operator decision 2026-05-11):
    Strict-require behavior is gated by a `.env` flag
    `MG_ANTHROPIC_LINKED=1` — the marker the future installer UI will
    write when the customer clicks "yes, link Anthropic at install
    time." Pre-installer-UI, the operator's PoC Mini sets this flag
    manually.

    - MG_ANTHROPIC_LINKED=1 AND ANTHROPIC_API_KEY present
        → return cleanly, job runs normally.
    - MG_ANTHROPIC_LINKED=1 AND ANTHROPIC_API_KEY missing or empty
        → log ERROR + sys.exit(1). The install promised a key, so
        absence is a real misconfiguration the operator must see.
    - MG_ANTHROPIC_LINKED absent OR set to anything other than "1"
        → log INFO "Anthropic API key not linked at install time —
        skipping {job_name}" + sys.exit(0). Customer-Mini default.
        Operator can grep `logs/scheduled/{job}.out.log` for the
        skip message to confirm why the job did nothing.

The check honors `.env` file content (parsed the same way as
`refinement_chain.py::get_api_key`) AND environment variables, with
environment variables winning on conflict — matching the existing
convention in the codebase.

Test isolation: an internal env override `MG_ANTHROPIC_GATE_ROOT_OVERRIDE`
lets the test suite point _ROOT at a tmp directory so the helper
doesn't accidentally read the repo's own `.env`. This is internal-only
and not part of the public contract.

Never imports the `anthropic` SDK — the whole point is to decide
whether to use Anthropic without requiring it to be installed.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

__all__ = ["require_anthropic_or_exit"]


def _resolve_root() -> Path:
    """Resolve the install root. Test isolation override wins."""
    override = os.environ.get("MG_ANTHROPIC_GATE_ROOT_OVERRIDE")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent


def _read_dotenv_value(root: Path, key: str) -> Optional[str]:
    """Parse a single `KEY=value` line out of `.env`. Returns None if
    the file doesn't exist or the key isn't present.

    Strips surrounding double or single quotes (matching the existing
    `refinement_chain.py::get_api_key` convention).
    """
    env_path = root / ".env"
    if not env_path.exists():
        return None
    try:
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith(f"{key}="):
                value = line.split("=", 1)[1].strip()
                # Strip matching surrounding quotes.
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                return value
    except Exception:
        # Defensive — never crash on a malformed .env line.
        return None
    return None


def _resolve_value(key: str, root: Path) -> Optional[str]:
    """Environment variable wins, then `.env` file. Returns None if
    neither source has the key."""
    env_value = os.environ.get(key)
    if env_value is not None:
        # Empty string from env still wins — caller decides whether
        # empty is OK. This matches operator expectation: if you
        # export ANTHROPIC_API_KEY='' in your shell, you mean it.
        return env_value
    return _read_dotenv_value(root, key)


_TRUTHY = {"1", "true", "yes", "on"}


def _is_linked(flag_value: Optional[str]) -> bool:
    """Per the operator decision, only "1" is the canonical truthy
    value (that's what the future installer UI will write). Other
    truthy spellings ("true", "yes", "on") are accepted for operator
    convenience when setting the flag manually. Anything else is
    falsy, including None, "0", "false", "no", "", and unknown
    strings."""
    if flag_value is None:
        return False
    return flag_value.strip().lower() in _TRUTHY


def require_anthropic_or_exit(job_name: str, logger: logging.Logger) -> Optional[str]:
    """Gate an Anthropic-dependent job on install-time provisioning.

    Behavior:
      - Not linked → log INFO, sys.exit(0). The job is intentionally
        skipped on this install. This is the customer-Mini default
        for any install that opts out of Anthropic.
      - Linked but key missing/empty → log ERROR, sys.exit(1). The
        install promised a key. Absence is a real misconfiguration.
      - Linked and key present → return the key. Caller may use it
        or call its own `get_api_key()` helper; the contract is
        "if you reach the next line, Anthropic is provisioned."

    Args:
        job_name: A short identifier the operator can grep for in
            scheduled-job logs. Examples: "weekly_training",
            "refinement_chain".
        logger: The caller's logger. The skip / fail message is
            emitted through this logger so it appears in the job's
            normal log stream (visible in
            `logs/scheduled/{job}.out.log` or `.err.log`).

    Returns:
        The Anthropic API key as a string when linked + present.
        Never returns when the gate decides to exit — the function
        calls `sys.exit` directly.

    This function never raises. Callers can treat it as either
    "returns the key" or "exits the process before the next line
    runs" — both outcomes are normal control flow.
    """
    root = _resolve_root()

    linked_raw = _resolve_value("MG_ANTHROPIC_LINKED", root)
    if not _is_linked(linked_raw):
        logger.info(
            "Anthropic API key not linked at install time — "
            "skipping %s (set MG_ANTHROPIC_LINKED=1 in .env to enable)",
            job_name,
        )
        sys.exit(0)

    api_key = _resolve_value("ANTHROPIC_API_KEY", root)
    if not api_key:
        logger.error(
            "MG_ANTHROPIC_LINKED=1 but ANTHROPIC_API_KEY is missing or empty. "
            "The install was configured to use Anthropic but no key is provisioned. "
            "Add ANTHROPIC_API_KEY=sk-ant-... to .env or unset MG_ANTHROPIC_LINKED "
            "to disable Anthropic for %s.",
            job_name,
        )
        sys.exit(1)

    return api_key
