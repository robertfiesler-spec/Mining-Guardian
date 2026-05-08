"""
P-023 regression guard — no retired hosts in customer-shipped payload.

The customer Mac Mini receives the directories listed in the
`installer/macos-pkg/scripts/build_pkg.sh` rsync `--include` list. This
test enumerates the same shipped dirs and asserts that no file inside
them references the retired hosts:

  * 187.124.247.182  — old VPS (decommissioned on Mac Mini cutover)
  * 100.110.87.1     — old ROBS-PC tailscale endpoint (D-7 / D-9 / S-13)
  * fieslerfamily.com — old public domain (Cloudflare tunnel still in use
                       for the operator console; see ALLOWED_FIESLER_FILES)

The complement of "shipped" — `docs/`, `.env.example`, the test files
themselves, and operator-side tooling that does not appear in the rsync
include list — is exempt. The two existing retired-host tests
(`tests/test_no_retired_host_defaults.py` and
`tests/test_no_retired_host_in_operator_docs.py`) cover those surfaces.

This test is deliberately strict on `187.124.247.182` and `100.110.87.1`
(no live operator path needs them) and tolerant on `fieslerfamily.com`
where the D-19 customer operator console + Cloudflare tunnel CORS
allowlist legitimately reference it. New `fieslerfamily.com` references
in shipped code outside the carve-out list will fail this guard.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent

# Exact rsync `--include` list from installer/macos-pkg/scripts/build_pkg.sh
# (step 4a). Keep this list in sync with the build script — if a new
# directory is added to the payload, add it here so the guard widens.
SHIPPED_DIRS = (
    "core",
    "clients",
    "notifiers",
    "monitoring",
    "api",
    "ai",
    "console",
    "intelligence-catalog",
    "branding",
    "deploy",
    "migrations",
    "scripts",
    "config",
)

# Top-level files that ship.
SHIPPED_FILES = (
    "pyproject.toml",
    "predictor.py",
    "requirements.txt",
)

# `docs/***` ships too but is intentionally exempt from this guard.
# Past-tense doc references are covered by
# `tests/test_no_retired_host_in_operator_docs.py` (operator-facing
# subset). General history/handoff content is allowed to mention the
# retired hosts.
EXEMPT_TOP_LEVEL_DIRS = ("docs",)

VPS_IP = "187.124.247.182"
ROBS_PC_IP = "100.110.87.1"
FIESLER_HOST = "fieslerfamily.com"

# Files where `fieslerfamily.com` is intentionally referenced by active
# operator-facing code. The Cloudflare tunnel that exposes the D-19
# operator console (`docs/CONSOLE_OPERATIONS_GUIDE.md`) and the operator
# Slack actions surface routes through `*.fieslerfamily.com`. These
# references are operator-facing only — the customer data plane stays
# local (VA-6, D-9). Any NEW shipped file that references the host must
# be added here with rationale.
ALLOWED_FIESLER_FILES = {
    "api/dashboard_api.py",      # CORS allowlist for operator dashboard
    "api/approval_api.py",       # CORS allowlist + Slack tunnel comment
    "api/ai_dashboard_api.py",   # APPROVAL_API operator-side constant
    "api/report_builder.py",     # operator download-link template
    "api/slack_command_handler.py",  # operator help-text URL
    "scripts/demo_status.py",    # operator status banner
    "scripts/update_grafana_ai.py",  # operator Grafana iframe src
    "intelligence-catalog/tools/catalog_updater.py",  # operator helper --help text
    "intelligence-catalog/LIVING_CATALOG.md",  # operator how-to example block
}

# Files where the retired IPs are intentional REJECT guards. The strings
# appear so the code can refuse them. These are exempt by design.
ALLOWED_REJECT_GUARD_FILES = {
    "ai/catalog_context.py",  # _http_fallback_url() refuses retired host
}

# Files where the retired IPs would be unambiguous misconfiguration. No
# legitimate operator path references the VPS IP from inside the shipped
# payload — backup tooling that pulled from the VPS was retired with
# P-023 (see `scripts/send_deep_dive_report.py` deletion). Operator
# backup scripts that still ship (`scripts/backup_db.sh`,
# `scripts/backup_mining_guardian.sh`) reference the VPS by design and
# are explicitly excluded — they are operator-only and never invoked on
# the customer Mac Mini. Any NEW shipped file that references the VPS
# must be reviewed before being added here.
ALLOWED_VPS_FILES = {
    "scripts/backup_db.sh",            # operator-side, never invoked on Mini
    "scripts/backup_mining_guardian.sh",  # operator-side, never invoked on Mini
}


def _iter_shipped_files():
    """Yield (rel_posix, abs_path) for every regular file that ships.

    Mirrors the include list from build_pkg.sh step 4a. Directories in
    EXEMPT_TOP_LEVEL_DIRS are skipped. Common rsync excludes
    (`.git`, `__pycache__`, `*.pyc`, `build`, `venv`, `.venv`) are
    likewise skipped.
    """
    for top in SHIPPED_DIRS:
        if top in EXEMPT_TOP_LEVEL_DIRS:
            continue
        root = REPO_ROOT / top
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if any(seg in rel.split("/") for seg in ("__pycache__", ".git", "venv", ".venv", "build")):
                continue
            if rel.endswith(".pyc"):
                continue
            yield rel, path
    for top in SHIPPED_FILES:
        path = REPO_ROOT / top
        if path.is_file():
            yield top, path


def _strip_python_comments_and_docstrings(text: str) -> str:
    """Conservative scrubber matching tests/test_no_retired_host_defaults.py.

    Strips triple-quoted blocks and full-line `#` comments. Inline
    comments after code on the same line are also stripped. The bias
    is to delete too much rather than too little — an active runtime
    reference would still appear OUTSIDE both forms.
    """
    text = re.sub(r"'''.*?'''", "", text, flags=re.DOTALL)
    text = re.sub(r'""".*?"""', "", text, flags=re.DOTALL)
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        out.append(line.split("#", 1)[0])
    return "\n".join(out)


def _strip_shell_comments(text: str) -> str:
    """Drop `#`-leading comment lines from shell scripts. Keeps content
    after a `#` mid-line because that is rare in practice and stripping
    it would also discard URL fragments (`#frag`) inside string
    literals."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def _scrub_for_scan(rel: str, text: str) -> str:
    """Return the comment-stripped form of `text` so the IP scan only
    flags ACTIVE references. Markdown / unknown extensions are returned
    unchanged — those are exempt at the file level via ALLOWED_*."""
    if rel.endswith(".py"):
        return _strip_python_comments_and_docstrings(text)
    if rel.endswith(".sh"):
        return _strip_shell_comments(text)
    return text


def _scan_for(needle: str, allowed: set[str], strip_comments: bool = True) -> list[tuple[str, list[int]]]:
    """Return [(rel_path, [line_numbers])] for every shipped file
    outside `allowed` whose ACTIVE contents contain `needle`.

    When `strip_comments=True`, Python and shell comments are removed
    before the substring check so explanatory comments that name the
    retired host (e.g., "# was 100.110.87.1, now 127.0.0.1") do not
    trip the guard. The reported line numbers are still indexed into
    the ORIGINAL file so failure messages point at the right spot.
    """
    offenders: list[tuple[str, list[int]]] = []
    for rel, path in _iter_shipped_files():
        if rel in allowed:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue
        if needle not in text:
            continue
        scrubbed = _scrub_for_scan(rel, text) if strip_comments else text
        if needle not in scrubbed:
            continue
        bad_lines = [
            i + 1
            for i, line in enumerate(text.splitlines())
            if needle in line and not line.lstrip().startswith("#")
        ]
        offenders.append((rel, bad_lines))
    return offenders


def test_shipped_payload_has_no_vps_ip():
    """No shipped file (outside the operator-only backup carve-out) may
    contain the retired VPS IP. The VPS was decommissioned with the
    Mac Mini cutover; any reference inside the customer payload would
    mislead a future reader or, worse, get re-wired into a runtime
    path."""
    allowed = ALLOWED_VPS_FILES | ALLOWED_REJECT_GUARD_FILES
    offenders = _scan_for(VPS_IP, allowed)
    if offenders:
        msg = "\n".join(f"  {rel}:{lines}" for rel, lines in offenders)
        pytest.fail(
            f"\nShipped payload still references the retired VPS IP "
            f"{VPS_IP!r}:\n{msg}\n"
            "The VPS is not in the customer operating path. Remove the "
            "reference, or — if the file is genuinely operator-only and "
            "must continue to ship — add it to ALLOWED_VPS_FILES with "
            "rationale."
        )


def test_shipped_payload_has_no_robs_pc_ip():
    """No shipped file (outside the intentional reject-guard in
    `ai/catalog_context.py`) may contain the retired ROBS-PC tailscale
    IP. Defaults must point at the Mini's local services."""
    allowed = ALLOWED_REJECT_GUARD_FILES
    offenders = _scan_for(ROBS_PC_IP, allowed)
    if offenders:
        msg = "\n".join(f"  {rel}:{lines}" for rel, lines in offenders)
        pytest.fail(
            f"\nShipped payload still references the retired ROBS-PC "
            f"host {ROBS_PC_IP!r}:\n{msg}\n"
            "Defaults must point at 127.0.0.1 (Ollama) or "
            "core.db_targets.catalog_target() (catalog DB). The only "
            "permitted reference is the refusal guard in "
            "ai/catalog_context.py::_http_fallback_url()."
        )


def test_shipped_payload_fieslerfamily_only_in_allowed_files():
    """`fieslerfamily.com` may appear ONLY in the curated list of
    operator-facing files (CORS allowlists, D-19 console URLs, operator
    helper text). New shipped files that reference the host must be
    audited before being added to ALLOWED_FIESLER_FILES — the customer
    data plane stays local (VA-6)."""
    offenders = _scan_for(FIESLER_HOST, ALLOWED_FIESLER_FILES)
    if offenders:
        msg = "\n".join(f"  {rel}:{lines}" for rel, lines in offenders)
        pytest.fail(
            f"\nShipped payload contains {FIESLER_HOST!r} in files "
            f"outside the operator-tunnel carve-out:\n{msg}\n"
            "The customer Mac Mini data plane is local-only (VA-6). "
            "If the new reference is for the operator console / CORS "
            "tunnel, add the path to ALLOWED_FIESLER_FILES with a "
            "one-line reason."
        )


def test_send_deep_dive_report_is_deleted():
    """P-023 deleted `scripts/send_deep_dive_report.py` — the script
    was dead code that hardcoded the VPS hop and a 2026-04-16 date.
    A regression that re-adds it must trip this test."""
    path = REPO_ROOT / "scripts" / "send_deep_dive_report.py"
    assert not path.exists(), (
        "scripts/send_deep_dive_report.py was deleted in P-023. "
        "Do not re-add it — daily deep-dive output stays local on "
        "the Mac Mini per VA-6 / D-9."
    )


# ---------------------------------------------------------------------------
# P-024 — Bobby-Mac contamination guards
# ---------------------------------------------------------------------------
#
# P-024 narrowed `installer/macos-pkg/scripts/build_pkg.sh` step 4a's
# `scripts/***` rsync include into a per-file allowlist so that operator
# scripts (`scripts/backup_db.sh`, `scripts/backup_mining_guardian.sh`,
# `scripts/start_guardian.sh`, `scripts/setup.sh`) no longer ship to the
# customer Mac Mini. Those files remain in the repo because Bobby still
# runs them on his own workstation. The guards below scan the **repo
# tree** under SHIPPED_DIRS (the same surface as the existing P-023
# tests), so kept-in-repo-but-not-shipped operator files need a
# P-024-specific carve-out documenting why the strings are tolerated.
#
# `tests/installer/test_p024_payload_scripts_allowlist.sh` is the actual
# rsync-replay guard — it confirms those operator scripts are NOT in the
# assembled payload. The pytest guard below catches NEW Bobby-Mac
# contamination introduced into shipped runtime files (api/, core/, ai/,
# etc.) without depending on rsync availability inside CI.
#
# Out of scope for this pytest guard: the post-build `runtime/images/`
# directory (vendored .tar tarballs + .sha256 sidecars copied in by
# build_pkg.sh step 4c from `${HOME}/MiningGuardian-vendor/`). Those
# files do NOT exist in the repo tree — they only land in the assembled
# payload during a real `make pkg` run on the build Mac. The image
# sidecar Bobby-Mac contamination surface is covered separately by the
# rsync-replay-style installer test
# `tests/installer/test_p026_image_sha_sidecar_portability.sh`, which
# re-runs the build_pkg.sh step-4c normalisation against a fixture and
# asserts no `*.sha256` line ends up with `/Users/BigBobby`,
# `/Volumes/`, or `MiningGuardian-vendor` in its filename field.

BIG_BOBBY = "BigBobby"
BOBBY_HOME_PATH = "/Users/BigBobby"
BOBBY_TAILSCALE_IP = "100.103.185.53"

# Repo-resident operator files that may legitimately mention Bobby's Mac
# (username, home path, or Tailscale IP). After P-024 these no longer
# ship to customers; the rsync filter excludes them. Adding a new file
# here documents the allowance — please link the rationale.
ALLOWED_BOBBY_MAC_FILES = {
    # Operator backup tooling — pulls from Bobby's facility VPS to
    # Bobby's Mac. Never invoked on the customer Mac Mini. Excluded
    # from payload by the P-024 build_pkg.sh rsync allowlist.
    "scripts/backup_db.sh",
    "scripts/backup_mining_guardian.sh",
    # Operator dev-laptop launcher with hardcoded /Users/BigBobby path
    # and the typo'd pre-rename repo name. Dead in Mini path. Excluded
    # from payload by P-024.
    "scripts/start_guardian.sh",
    # Operator setup helper — same story.
    "scripts/setup.sh",
}


def test_shipped_payload_has_no_big_bobby_username():
    """No shipped runtime file (outside the kept-in-repo operator
    carve-out) may contain `BigBobby`. P-024 narrowed the payload so
    these files no longer ship to the customer Mac Mini, but they
    remain in the repo for operator use; this guard catches NEW
    contamination in shipped runtime code."""
    offenders = _scan_for(BIG_BOBBY, ALLOWED_BOBBY_MAC_FILES)
    if offenders:
        msg = "\n".join(f"  {rel}:{lines}" for rel, lines in offenders)
        pytest.fail(
            f"\nShipped runtime contains the operator username "
            f"{BIG_BOBBY!r}:\n{msg}\n"
            "Customer Mac Mini code must not reference the operator's "
            "macOS username. If the file is genuinely operator-only "
            "and must remain in the repo, ensure it is excluded from "
            "the payload via build_pkg.sh and add it to "
            "ALLOWED_BOBBY_MAC_FILES with rationale."
        )


def test_shipped_payload_has_no_big_bobby_home_path():
    """No shipped runtime file (outside the operator carve-out) may
    contain `/Users/BigBobby`. Customer Mac Mini paths are rooted at
    `/Library/Application Support/MiningGuardian/` (set by the .pkg);
    a `/Users/BigBobby` reference is build-Mac contamination."""
    offenders = _scan_for(BOBBY_HOME_PATH, ALLOWED_BOBBY_MAC_FILES)
    if offenders:
        msg = "\n".join(f"  {rel}:{lines}" for rel, lines in offenders)
        pytest.fail(
            f"\nShipped runtime contains the operator home path "
            f"{BOBBY_HOME_PATH!r}:\n{msg}\n"
            "Customer Mac Mini paths must be rooted at the install "
            "location, never at the build Mac's home directory."
        )


def test_shipped_payload_has_no_bobby_tailscale_ip():
    """No shipped runtime file (outside the operator carve-out) may
    contain Bobby's Mac Tailscale IP `100.103.185.53`. Surfaced by
    the P-024 audit; this is a CGNAT-range Tailscale endpoint, not a
    customer-runtime address."""
    offenders = _scan_for(BOBBY_TAILSCALE_IP, ALLOWED_BOBBY_MAC_FILES)
    if offenders:
        msg = "\n".join(f"  {rel}:{lines}" for rel, lines in offenders)
        pytest.fail(
            f"\nShipped runtime references Bobby's Mac Tailscale IP "
            f"{BOBBY_TAILSCALE_IP!r}:\n{msg}\n"
            "The customer Mac Mini data plane is local-only (VA-6, "
            "D-9). Tailscale endpoints belong to the operator-access "
            "plane only."
        )
