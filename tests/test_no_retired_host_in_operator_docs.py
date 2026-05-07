"""
P-019A regression guard — operator-facing docs do not recommend the
retired ROBS-PC host as a setting.

The P-018E test (`tests/test_no_retired_host_defaults.py`) intentionally
excludes `docs/` because historical handoffs, decisions logs, and bug
entries legitimately reference `100.110.87.1` (the retired tailscale
host) in past-tense contexts. P-019A narrows the scope to a curated
list of OPERATOR-FACING docs that the customer / installer reads as
current guidance — the kind of doc where `OLLAMA_URL=http://100.110.87.1`
or `curl http://100.110.87.1:11434/api/tags` would mislead someone
following the steps today.

In those docs, the retired IP must not appear in either of the two
"recommendation shapes":

  1. A KEY=value line (`OLLAMA_URL=http://100.110.87.1...`).
  2. A bare `curl http://100.110.87.1...` line.

Past-tense / historical-context references inside the same file are
allowed — the bar is just that the recommendation shapes are gone.

Test runs as a static check; no extra dependencies.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent

# Files the operator follows as CURRENT GUIDANCE during install / cutover.
# Anything here will fail the test if it shows the retired host in a
# recommendation shape. Files NOT on this list (handoffs, decisions log,
# session bug entries, archived bucket runbooks) are exempt — those
# legitimately reference the retired host in past tense.
OPERATOR_FACING_DOCS = (
    "DEPLOYMENT_CHECKLIST.md",
    "docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md",
    "docs/CRON_SCHEDULE.md",
    "docs/DAILY_DEEP_DIVE_DESIGN.md",
    "docs/PERPLEXITY_PROMPT_MINING_INTELLIGENCE_CATALOG.md",
)

RETIRED_IP = "100.110.87.1"

# Recommendation shapes — strings that, if they appear in an operator-facing
# doc, copy/paste the retired host into the operator's environment or
# terminal. Both are forbidden in the curated doc list above.
#
# Shape 1: a `KEY=http://…100.110.87.1…` line. The KEY anchor at start
# of line (with optional leading whitespace) is what distinguishes a
# config-recipe line from prose that mentions the IP.
SHAPE_KEY_VALUE = re.compile(
    r"^\s*[A-Z_][A-Z0-9_]*\s*=\s*[^#\n]*100\.110\.87\.1",
    flags=re.MULTILINE,
)
# Shape 2: a `curl http://100.110.87.1…` URL — the `curl` literal is the
# operator's signal to run the command, and the IP must sit IN the URL
# argument (not in trailing prose). The character class `[^\s)]*` keeps
# the match inside one URL token: it stops at whitespace and at a
# closing backtick/paren, so a paragraph that mentions the IP later in
# prose does not trip this guard.
SHAPE_CURL = re.compile(
    r"\bcurl\b[^\n]*?\bhttps?://[^\s)`]*100\.110\.87\.1",
)


@pytest.mark.parametrize("rel_path", OPERATOR_FACING_DOCS)
def test_operator_doc_has_no_recommendation_of_retired_host(rel_path: str):
    path = REPO_ROOT / rel_path
    assert path.is_file(), f"operator-facing doc missing: {rel_path}"
    text = path.read_text(encoding="utf-8")

    bad_kv = SHAPE_KEY_VALUE.findall(text)
    bad_curl = SHAPE_CURL.findall(text)

    if bad_kv or bad_curl:
        msg_lines = [f"\noperator-facing doc {rel_path!r} still recommends the retired ROBS-PC host:"]
        for hit in bad_kv:
            msg_lines.append(f"  KEY=VALUE shape:  {hit.strip()}")
        for hit in bad_curl:
            msg_lines.append(f"  curl shape:       {hit.strip()}")
        msg_lines.append(
            "Operator-facing docs MUST recommend the local Mac Mini Ollama "
            "(`http://127.0.0.1:11434`) by default. The retired ROBS-PC tailscale "
            "host is decommissioned for MG (D-7 / D-9 / S-13)."
        )
        pytest.fail("\n".join(msg_lines))


def test_no_recommendation_of_retired_host_in_curated_set_total():
    """Aggregate guard: combined hit count across the curated doc set
    must be zero. Catches future docs added to the set that introduce
    a fresh recommendation."""
    total = 0
    for rel in OPERATOR_FACING_DOCS:
        path = REPO_ROOT / rel
        text = path.read_text(encoding="utf-8")
        total += len(SHAPE_KEY_VALUE.findall(text))
        total += len(SHAPE_CURL.findall(text))
    assert total == 0, (
        f"{total} retired-host recommendation(s) still in operator-facing docs"
    )
