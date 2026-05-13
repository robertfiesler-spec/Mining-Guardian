"""
tests/test_w25_dashboard_api_bind_config.py

W25 (2026-05-13) — dashboard_api bind host/port must be configurable
via env so the Mini's production install can flip to 0.0.0.0 for
Tailscale-side iframe reachability without code changes.

Live evidence that motivated the fix (Safari Web Inspector console on
http://100.69.66.32:3000/d/llm_learning_001/...):

    Failed to load resource: Could not connect to the server
        http://100.69.66.32:8585/ai/dashboard

The same URL returned HTTP 200 with valid HTML when curled from the
Mini itself via `curl http://127.0.0.1:8585/ai/dashboard`. The mismatch:
dashboard_api was hardcoded to `host="127.0.0.1"`, so connections
arriving on the Tailscale interface (100.69.66.32) were refused before
the HTTP handshake even started. Grafana's iframe panels in the
restored VPS dashboards (AI & Learning, Intelligence Report, Board
Health, Fleet Overview, Per Miner — 5 dashboards, 6 iframe references)
all rendered as white boxes.

Design (matches the catalog_api.py CRIT-6 pattern):
    - Default to loopback: `MG_DASHBOARD_HOST=127.0.0.1`,
      `MG_DASHBOARD_PORT=8585`. Safe for developer-laptop runs.
    - Production override lives in the install's .env. The Mini sets
      `MG_DASHBOARD_HOST=0.0.0.0` so the iframes work.
    - Module docstring + .env.example both document the trust-boundary
      caveat: only flip to 0.0.0.0 on a host that has no public NIC
      (the Mini's only routable interfaces are loopback + Tailscale).

Asserted by this test module:

  S1. The hardcoded bind line `host="127.0.0.1", port=8585` is gone
      from the `__main__` block of api/dashboard_api.py. (Regression
      guard — the whole point of this work item is that it stays gone.)
  S2. The `__main__` block reads `MG_DASHBOARD_HOST` from os.environ
      with a `127.0.0.1` default.
  S3. The `__main__` block reads `MG_DASHBOARD_PORT` from os.environ
      with an `8585` default, and casts to int.
  S4. The `__main__` block invokes `uvicorn.run(..., host=_bind_host,
      port=_bind_port)` — the env vars are actually plumbed through,
      not just read and ignored.
  S5. The module docstring at the top of the file documents the
      W25 change (string match on "W25" + "MG_DASHBOARD_HOST").
  S6. .env.example documents both vars with the safe defaults and
      explains the trust-boundary rule.
  S7. No other file in api/ scripts/ ai/ core/ hardcodes
      `host="127.0.0.1"` paired with `port=8585` in a uvicorn.run
      call. (Sibling-sweep guard — Failure Mode 9.)

These tests run against the repo on the laptop, not against the
running service on the Mini. The live smoke (curl from a remote host
to http://<mini-tailscale-ip>:8585/ai/dashboard) is captured in the
PR description and the day-end handoff doc.
"""
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_API = REPO_ROOT / "api" / "dashboard_api.py"
ENV_EXAMPLE = REPO_ROOT / ".env.example"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# S1. Old hardcoded bind line is gone.
# ---------------------------------------------------------------------------

def test_S1_old_hardcoded_bind_line_is_gone():
    """The pre-W25 line `host="127.0.0.1", port=8585` must not appear
    anywhere in dashboard_api.py. This is the regression guard."""
    src = _read(DASHBOARD_API)
    # Normalize whitespace so we catch reformat-only attempts at
    # restoring the old form.
    normalized = re.sub(r"\s+", "", src)
    forbidden = re.sub(r"\s+", "", 'host="127.0.0.1", port=8585')
    assert forbidden not in normalized, (
        "api/dashboard_api.py still contains a hardcoded "
        '`host="127.0.0.1", port=8585` — the W25 env-var indirection '
        "was reverted or sidestepped. See module docstring for context."
    )


# ---------------------------------------------------------------------------
# S2 + S3. Env-var reads are present with safe defaults.
# ---------------------------------------------------------------------------

def test_S2_reads_MG_DASHBOARD_HOST_with_loopback_default():
    """The __main__ block must read MG_DASHBOARD_HOST from os.environ
    with a 127.0.0.1 default."""
    src = _read(DASHBOARD_API)
    # Match either single or double quotes around the var name and the
    # default. Tolerate `os.environ.get` and `os.getenv`.
    pattern = re.compile(
        r"""(?xs)
        (?:os\.environ\.get|os\.getenv)\s*\(
        \s*['"]MG_DASHBOARD_HOST['"]\s*,
        \s*['"]127\.0\.0\.1['"]\s*\)
        """
    )
    assert pattern.search(src) is not None, (
        "Could not find an `os.environ.get('MG_DASHBOARD_HOST', "
        "'127.0.0.1')`-style read in api/dashboard_api.py. The safe "
        "loopback default is required so developer-laptop runs are "
        "not silently exposed."
    )


def test_S3_reads_MG_DASHBOARD_PORT_with_8585_default_and_int_cast():
    """The __main__ block must read MG_DASHBOARD_PORT from os.environ
    with an 8585 default and cast the result through int()."""
    src = _read(DASHBOARD_API)
    pattern = re.compile(
        r"""(?xs)
        int\s*\(
        \s*(?:os\.environ\.get|os\.getenv)\s*\(
        \s*['"]MG_DASHBOARD_PORT['"]\s*,
        \s*['"]8585['"]\s*\)\s*\)
        """
    )
    assert pattern.search(src) is not None, (
        "Could not find `int(os.environ.get('MG_DASHBOARD_PORT', "
        "'8585'))` in api/dashboard_api.py. The int() cast is "
        "required — uvicorn rejects a string-valued port."
    )


# ---------------------------------------------------------------------------
# S4. uvicorn.run actually uses the env-var-derived locals.
# ---------------------------------------------------------------------------

def test_S4_uvicorn_run_uses_env_derived_host_and_port():
    """uvicorn.run(...) must reference the variables populated from
    the env reads, not stray hardcoded literals. This catches the
    "read env but pass literal anyway" footgun."""
    src = _read(DASHBOARD_API)
    pattern = re.compile(
        r"""(?xs)
        uvicorn\.run\s*\(
        [^)]*?\bhost\s*=\s*_bind_host\b
        [^)]*?\bport\s*=\s*_bind_port\b
        [^)]*?\)
        """
    )
    assert pattern.search(src) is not None, (
        "uvicorn.run(...) does not pass host=_bind_host and "
        "port=_bind_port. The env reads must be plumbed through to "
        "uvicorn or they have no effect."
    )


# ---------------------------------------------------------------------------
# S5. Module docstring documents the W25 change.
# ---------------------------------------------------------------------------

def test_S5_module_docstring_documents_W25_change():
    """The module docstring at the top of dashboard_api.py must mention
    both W25 and MG_DASHBOARD_HOST. This is operator-facing context;
    future Claude/operator readers need to know why the bind is
    configurable before they "fix" it back to loopback."""
    src = _read(DASHBOARD_API)
    # Pull the first triple-quoted docstring (the module-level one).
    m = re.search(r'"""(.*?)"""', src, flags=re.DOTALL)
    assert m is not None, "Module has no top-level docstring."
    docstring = m.group(1)
    assert "W25" in docstring, (
        "Module docstring must reference W25 — operator-facing "
        "context for why the bind is configurable."
    )
    assert "MG_DASHBOARD_HOST" in docstring, (
        "Module docstring must mention the MG_DASHBOARD_HOST env var "
        "so a reader of dashboard_api.py alone (without .env.example) "
        "can see how to override the bind."
    )


# ---------------------------------------------------------------------------
# S6. .env.example documents the vars.
# ---------------------------------------------------------------------------

def test_S6_env_example_documents_the_vars():
    """.env.example must declare both vars with the safe defaults and
    name the trust-boundary rule. This is the customer-facing surface
    for the env contract — if it's not in .env.example, the install
    contract is undocumented."""
    src = _read(ENV_EXAMPLE)
    assert "MG_DASHBOARD_HOST=127.0.0.1" in src, (
        "MG_DASHBOARD_HOST=127.0.0.1 must appear verbatim in "
        ".env.example. The literal loopback default in the file "
        "(rather than a placeholder) makes it obvious to operators "
        "that doing nothing is the safe choice."
    )
    assert "MG_DASHBOARD_PORT=8585" in src, (
        "MG_DASHBOARD_PORT=8585 must appear verbatim in .env.example."
    )
    # The trust-boundary caveat must be visible — it's the whole reason
    # an operator should not just flip the default to 0.0.0.0.
    assert "Tailscale" in src and "public NIC" in src, (
        ".env.example must explain the trust-boundary rule ("
        "Tailscale-only is OK, public NIC is not). Without this the "
        "var looks like a free knob and someone will turn it the "
        "wrong way."
    )


# ---------------------------------------------------------------------------
# S7. Sibling-sweep guard (Failure Mode 9).
# ---------------------------------------------------------------------------

def test_S7_no_other_uvicorn_run_hardcodes_loopback_8585():
    """Failure Mode 9 sweep: no other module in api/ scripts/ ai/ core/
    should hardcode `host="127.0.0.1"` paired with `port=8585` in a
    uvicorn.run(...) call. If a sibling exists with the same bug
    pattern, this work item should expand to cover it rather than
    leaving a latent duplicate."""
    candidate_dirs = [
        REPO_ROOT / "api",
        REPO_ROOT / "scripts",
        REPO_ROOT / "ai",
        REPO_ROOT / "core",
    ]
    # Two-line tolerant pattern — uvicorn.run can wrap args across lines.
    pattern = re.compile(
        r"""(?xs)
        uvicorn\.run\s*\(
        [^)]*?\bhost\s*=\s*['"]127\.0\.0\.1['"]
        [^)]*?\bport\s*=\s*8585\b
        [^)]*?\)
        """
    )
    offenders = []
    for d in candidate_dirs:
        if not d.exists():
            continue
        for p in d.rglob("*.py"):
            # Skip vendored / build artifact trees.
            sp = str(p)
            if any(skip in sp for skip in ("/build/", "/.venv", "/venv/", "/__pycache__/")):
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if pattern.search(text):
                offenders.append(str(p.relative_to(REPO_ROOT)))
    assert not offenders, (
        "Sibling-sweep failure: the following file(s) still have a "
        'hardcoded `uvicorn.run(..., host="127.0.0.1", port=8585)`, '
        "matching the bug pattern that W25 fixed in api/dashboard_api.py. "
        "Either fold them into this PR (same bug class — fits Failure "
        "Mode 9 same-class-cohort rule) or open a sibling ticket and "
        "explicitly carve them out of this guard.\n  " + "\n  ".join(offenders)
    )
