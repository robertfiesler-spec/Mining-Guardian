"""
tests/test_p038_anthropic_env_gate.py

P-038 items #4 + #5 (env-gate portion, 2026-05-11) — `weekly_train.py`
and `refinement_chain.py` need to gracefully skip when Anthropic is not
provisioned at install time, and fail loudly when the install promised
a key but the key is missing.

Live evidence on the Mini before writing the fix (`/Library/Application
Support/MiningGuardian/logs/scheduled/weekly_training.err.log`):

    WARNING:llm_analyzer:Claude API key not set — returning empty,
        no Ollama fallback
    WARNING:train_cohort:  Attempt 1 failed or empty — waiting 30s
    (... x 6 cohorts x 3 retries = 18 occurrences of the same warning ...)
    WARNING:train_cohort:  Attempt 3 failed or empty — waiting 90s
    ERROR:train_cohort:  All attempts failed for this cohort

The current behavior is "soft-fail inside the loop, three retries per
cohort, ~3 minutes wasted per cohort, every Sunday morning, forever."
The post-P-038 #5-datetime fix means the job no longer crashes, but it
still burns ~20 minutes producing empty Claude output before exiting.

Design (per operator decision 2026-05-11):
    - Strict-require behavior gated by `.env` flag MG_ANTHROPIC_LINKED=1
      (the marker the future installer UI will write when the customer
       says "yes, link Anthropic at install time")
    - If MG_ANTHROPIC_LINKED=1 and ANTHROPIC_API_KEY present → run normally
    - If MG_ANTHROPIC_LINKED=1 but ANTHROPIC_API_KEY missing → fail loudly
      (sys.exit(1)) — the install promised a key, missing key is a real
      misconfiguration that the operator needs to see
    - If MG_ANTHROPIC_LINKED absent or set to anything other than "1" →
      log INFO "Anthropic key not linked at install time — skipping
      {job_name}" and sys.exit(0). This is the customer-Mini default
      and is the right behavior for any install that opts out of
      Anthropic at install time.

The check lives in a new shared helper `core/anthropic_gate.py` so both
entry points (`weekly_train.py::run_weekly`, `refinement_chain.py::
__main__`) call the same code with the same semantics.

Asserted by this test module:

  S1. Helper exists. `require_anthropic_or_exit(job_name, logger)` is
      importable from `core.anthropic_gate`.
  S2. Skips cleanly when MG_ANTHROPIC_LINKED is absent (sys.exit(0)).
  S3. Skips cleanly when MG_ANTHROPIC_LINKED="0" (sys.exit(0)).
  S4. Skips cleanly when MG_ANTHROPIC_LINKED="false" (sys.exit(0)).
  S5. Fails loudly when MG_ANTHROPIC_LINKED="1" but ANTHROPIC_API_KEY
      absent (sys.exit(1)).
  S6. Fails loudly when MG_ANTHROPIC_LINKED="1" but ANTHROPIC_API_KEY
      empty string (sys.exit(1)).
  S7. Returns cleanly (no exit) when MG_ANTHROPIC_LINKED="1" and
      ANTHROPIC_API_KEY is present.
  S8. Honors .env file when env vars are unset (reads MG_ANTHROPIC_LINKED
      and ANTHROPIC_API_KEY from `_ROOT/.env`).
  S9. Environment variable takes precedence over .env file value.
  S10. weekly_train.py invokes the gate at the top of run_weekly().
  S11. refinement_chain.py invokes the gate in __main__ before any other
       work.
  S12. The gate logs a clear INFO message naming the job when it skips,
       so the operator can grep `logs/scheduled/<job>.out.log` and see
       why nothing happened.
"""

import importlib
import io
import logging
import os
import re
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def gate_module():
    """Import the helper. The helper has no DB / SDK dependency, so this
    must succeed without psycopg2 or anthropic installed."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    # Force a fresh import in case a previous test polluted state.
    if "core.anthropic_gate" in sys.modules:
        del sys.modules["core.anthropic_gate"]
    return importlib.import_module("core.anthropic_gate")


@pytest.fixture
def isolated_env(monkeypatch, tmp_path):
    """Strip MG_ / ANTHROPIC_ env vars and point _ROOT at a temp dir
    with no .env file. Each test seeds whatever it needs."""
    for k in list(os.environ):
        if k.startswith("MG_") or k.startswith("ANTHROPIC_"):
            monkeypatch.delenv(k, raising=False)
    # Point the helper's _ROOT at a fresh tmpdir so we don't accidentally
    # read the repo's own .env (if any developer has one).
    monkeypatch.setenv("MG_ANTHROPIC_GATE_ROOT_OVERRIDE", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# S1. Helper exists and is importable.
# ---------------------------------------------------------------------------


def test_helper_importable_without_anthropic_sdk(gate_module):
    """The gate must not import the anthropic SDK at module load time —
    the whole point is to decide whether to use Anthropic without
    requiring it to be installed."""
    assert hasattr(gate_module, "require_anthropic_or_exit")
    assert callable(gate_module.require_anthropic_or_exit)


# ---------------------------------------------------------------------------
# S2 - S4. Skip cleanly when flag is absent / falsy.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("flag_value", [None, "0", "false", "False", "no", ""])
def test_skips_cleanly_when_flag_falsy(gate_module, isolated_env, caplog, flag_value, monkeypatch):
    """When MG_ANTHROPIC_LINKED is absent or set to a falsy value, the
    gate logs INFO and exits 0 — the job is intentionally skipped."""
    if flag_value is not None:
        monkeypatch.setenv("MG_ANTHROPIC_LINKED", flag_value)
    logger = logging.getLogger("test_gate")
    with caplog.at_level(logging.INFO, logger="test_gate"):
        with pytest.raises(SystemExit) as exc_info:
            gate_module.require_anthropic_or_exit("test_job", logger)
    assert exc_info.value.code == 0
    # Operator must see the job name and a clear "not linked" message
    # in the log so they can grep for it.
    assert any(
        "test_job" in r.message and "not linked" in r.message.lower()
        for r in caplog.records
    ), f"Expected 'test_job ... not linked' in INFO log, got: {[r.message for r in caplog.records]}"


# ---------------------------------------------------------------------------
# S5 - S6. Fail loudly when flag is set but key is missing.
# ---------------------------------------------------------------------------


def test_fails_loudly_when_linked_but_key_missing(gate_module, isolated_env, monkeypatch, caplog):
    monkeypatch.setenv("MG_ANTHROPIC_LINKED", "1")
    logger = logging.getLogger("test_gate")
    with caplog.at_level(logging.ERROR, logger="test_gate"):
        with pytest.raises(SystemExit) as exc_info:
            gate_module.require_anthropic_or_exit("test_job", logger)
    assert exc_info.value.code == 1
    assert any(
        "ANTHROPIC_API_KEY" in r.message and ("missing" in r.message.lower() or "not found" in r.message.lower())
        for r in caplog.records
    ), f"Expected ANTHROPIC_API_KEY missing error, got: {[r.message for r in caplog.records]}"


def test_fails_loudly_when_linked_but_key_empty_string(gate_module, isolated_env, monkeypatch):
    monkeypatch.setenv("MG_ANTHROPIC_LINKED", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    logger = logging.getLogger("test_gate")
    with pytest.raises(SystemExit) as exc_info:
        gate_module.require_anthropic_or_exit("test_job", logger)
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# S7. Returns cleanly when properly configured.
# ---------------------------------------------------------------------------


def test_returns_cleanly_when_linked_and_key_present(gate_module, isolated_env, monkeypatch):
    monkeypatch.setenv("MG_ANTHROPIC_LINKED", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-1234567890")
    logger = logging.getLogger("test_gate")
    # Must not raise SystemExit. Return value is implementation-defined
    # (None or the key), the contract is "if you reach the next line,
    # Anthropic is provisioned."
    result = gate_module.require_anthropic_or_exit("test_job", logger)
    # If the helper returns the key (convenient for the caller), great.
    # If it returns None, also fine — the caller can use the existing
    # get_api_key() shape. Don't constrain.
    assert result is None or result == "sk-ant-test-1234567890"


# ---------------------------------------------------------------------------
# S8 - S9. .env file reading + env-var precedence.
# ---------------------------------------------------------------------------


def test_reads_flag_and_key_from_dotenv(gate_module, isolated_env, monkeypatch):
    """If neither env var is set but `.env` contains both lines, the
    helper should still see them."""
    env_path = isolated_env / ".env"
    env_path.write_text(
        "MG_ANTHROPIC_LINKED=1\n"
        "ANTHROPIC_API_KEY=sk-ant-from-dotenv\n"
        "# unrelated comment\n"
        "GUARDIAN_PG_HOST=127.0.0.1\n"
    )
    logger = logging.getLogger("test_gate")
    # Must not raise.
    gate_module.require_anthropic_or_exit("test_job", logger)


def test_env_var_takes_precedence_over_dotenv(gate_module, isolated_env, monkeypatch):
    """If both env var and .env are set, env var wins (matches the
    existing get_api_key() convention in refinement_chain.py)."""
    env_path = isolated_env / ".env"
    env_path.write_text(
        "MG_ANTHROPIC_LINKED=1\n"
        "ANTHROPIC_API_KEY=sk-ant-from-dotenv\n"
    )
    monkeypatch.setenv("MG_ANTHROPIC_LINKED", "0")  # env var says "not linked"
    logger = logging.getLogger("test_gate")
    # Env var wins → falsy → skip with exit 0.
    with pytest.raises(SystemExit) as exc_info:
        gate_module.require_anthropic_or_exit("test_job", logger)
    assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# S10 - S11. Both entry points invoke the gate.
# ---------------------------------------------------------------------------


def test_weekly_train_invokes_gate_before_work():
    """weekly_train.py::run_weekly must call the gate as one of its
    first steps — BEFORE run_cohort_training, BEFORE knowledge_manager
    instantiation, BEFORE any LLM call. Static-source check."""
    src = (REPO_ROOT / "ai" / "weekly_train.py").read_text(encoding="utf-8")
    assert "require_anthropic_or_exit" in src, (
        "ai/weekly_train.py does not invoke require_anthropic_or_exit. "
        "The env-gate fix requires the gate to fire at the top of "
        "run_weekly() so the scheduled job skips cleanly when Anthropic "
        "is not provisioned at install time."
    )
    # The gate must appear in the body of `def run_weekly` BEFORE the
    # first `try:` / `run_cohort_training()` call.
    m = re.search(r"def run_weekly\(\):(.*?)(?:\nif __name__|\Z)", src, re.DOTALL)
    assert m, "Could not locate run_weekly() body"
    body = m.group(1)
    gate_pos = body.find("require_anthropic_or_exit")
    cohort_pos = body.find("run_cohort_training")
    assert gate_pos != -1, "Gate not invoked inside run_weekly()"
    assert cohort_pos != -1, "run_cohort_training call disappeared"
    assert gate_pos < cohort_pos, (
        "Gate must be called BEFORE run_cohort_training in run_weekly(). "
        "Currently the gate is invoked after — that means cohort training "
        "fires before we check whether Anthropic is provisioned."
    )


def test_refinement_chain_invokes_gate_in_main():
    """refinement_chain.py's __main__ block must call the gate before
    invoking run_chain(). Static-source check."""
    src = (REPO_ROOT / "ai" / "refinement_chain.py").read_text(encoding="utf-8")
    assert "require_anthropic_or_exit" in src, (
        "ai/refinement_chain.py does not invoke require_anthropic_or_exit"
    )
    main_block_start = src.find('if __name__ == "__main__"')
    assert main_block_start != -1, "__main__ block not found"
    main_block = src[main_block_start:]
    gate_pos = main_block.find("require_anthropic_or_exit(")
    # Find the actual run_chain CALL site (with arguments), not a
    # comment mention. The real call passes `dry_run=` as the first
    # keyword argument, which is unique to the call site.
    run_chain_call_pos = main_block.find("run_chain(dry_run=")
    assert gate_pos != -1, "Gate not invoked in __main__"
    assert run_chain_call_pos != -1, "run_chain(dry_run=...) call disappeared"
    assert gate_pos < run_chain_call_pos, (
        "Gate must be called BEFORE run_chain(dry_run=...) in __main__. "
        f"Found gate at offset {gate_pos}, run_chain call at offset "
        f"{run_chain_call_pos}."
    )


# ---------------------------------------------------------------------------
# S12. Clear log message naming the job.
# ---------------------------------------------------------------------------


def test_skip_log_message_contains_job_name(gate_module, isolated_env, caplog):
    """Operator greps logs/scheduled/<job>.out.log for the skip line
    when wondering why a job didn't fire. The line must contain the
    job name passed in."""
    logger = logging.getLogger("test_gate")
    with caplog.at_level(logging.INFO, logger="test_gate"):
        with pytest.raises(SystemExit):
            gate_module.require_anthropic_or_exit("weekly_training", logger)
    messages = "\n".join(r.message for r in caplog.records)
    assert "weekly_training" in messages, (
        f"Expected job name 'weekly_training' in log message, got:\n{messages}"
    )
