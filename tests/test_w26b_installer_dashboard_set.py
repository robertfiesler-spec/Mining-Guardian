"""
tests/test_w26b_installer_dashboard_set.py

W26b (2026-05-14) — installer Grafana dashboard set + reference-mini/
cohort guard.

After W25 (dashboard_api bind) + W25b (Postgres-strict
/fleet/board_stats) + W26a (Intelligence Catalog dashboard renders on
Grafana 13) brought the developer Mac Mini's Grafana to a fully-working
state with nine dashboards, the repo's installer still shipped only the
four customer-deployable dashboards at the top of
installer/macos-pkg/resources/grafana/dashboards/. The other eight —
the VPS-restored mining_guardian_*.json dashboards — lived only on the
Mini's filesystem and in backup tarballs.

W26b mirrors those eight into the repo under
installer/macos-pkg/resources/grafana/dashboards/reference-mini/ so:
  1. a Mini disk failure doesn't lose them (durability — the repo is
     the disaster-recovery source of truth);
  2. "what does the customer actually see" stops being ambiguous
     (installer parity).

Five of the eight contain hardcoded references to 100.69.66.32 — the
developer Mini's specific Tailscale IP — in iframe-panel URLs and
other panel content. They cannot be customer-deployable as-is, so they
ship in the clearly-labelled reference-mini/ subfolder rather than the
customer-deployable top-level dashboards/ directory. The IP-templating
work is deliberately deferred to a future W-item; see the
"Reference dashboards" section of
installer/macos-pkg/resources/grafana/README.md and W26b_PREP.md §2.

The customer install path (scripts/install_grafana_provisioning.sh)
globs `"$BUNDLE/dashboards"/*.json` — top level only, non-recursive —
so reference-mini/ is never copied to the runtime dashboards path the
Grafana provider watches. No provider-yaml exclude rule is needed; the
top-level-only glob already enforces the boundary.

Asserted by this test module:

  S1. All eight expected mining_guardian_*.json dashboards are present
      under dashboards/reference-mini/. Explicit allowlist — surfaces
      an accidental rename or delete.

  S2. Every dashboard JSON in dashboards/ — both the top-level
      customer-deployable set and everything under reference-mini/ —
      parses as valid JSON. Catches corruption-on-ship.

  S3. Every dashboard JSON has an integer schemaVersion >= 30, i.e. a
      modern Grafana 9.0+ value, so Grafana 13's on-the-fly migrator
      does not run on load. (Same threshold as W26a S4.)

  S4. Files under reference-mini/ are ALLOWED to contain the hardcoded
      100.69.66.32 Tailscale IP — this asserts nothing either way, it
      documents the carve-out so a future reader understands S5 is
      deliberately scoped to exclude reference-mini/.

  S5. Files in dashboards/ DIRECTLY (the customer-deployable set, NOT
      reference-mini/) must NOT contain the hardcoded 100.69.66.32.
      This is the customer-shipability gate — a customer .pkg's
      autoloaded dashboards must work on any network.

  S6. The reference-mini/ folder's purpose is documented — the
      installer's grafana/README.md must explain what reference-mini/
      is and that it is not customer-deployable.

These tests run against the repo on the laptop, not the live service
on the Mini. The live smoke (refresh each of the eight dashboards on
the Mini's Grafana at http://100.69.66.32:3000 and confirm panels
render) is captured in the PR description — W26b only mirrors files
into the repo, it does not deploy anything to the Mini, so the Mini
already has these dashboards and the smoke is a regression check, not
a post-deploy verification.
"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALLER_GRAFANA = REPO_ROOT / "installer" / "macos-pkg" / "resources" / "grafana"
DASHBOARDS_DIR = INSTALLER_GRAFANA / "dashboards"
REFERENCE_MINI_DIR = DASHBOARDS_DIR / "reference-mini"
GRAFANA_README = INSTALLER_GRAFANA / "README.md"

# The developer Mini's Tailscale IP. Allowed inside reference-mini/,
# forbidden in the customer-deployable top-level dashboards/.
MINI_TAILSCALE_IP = "100.69.66.32"

# The eight VPS-restored dashboards W26b mirrors into reference-mini/.
# Explicit allowlist — an accidental rename or delete trips S1.
EXPECTED_REFERENCE_MINI_DASHBOARDS = (
    "mining_guardian_ai_learning.json",
    "mining_guardian_board_health.json",
    "mining_guardian_fleet_overview.json",
    "mining_guardian_intelligence_report.json",
    "mining_guardian_main.json",
    "mining_guardian_mobile.json",
    "mining_guardian_per_miner.json",
    "mining_guardian_pool_stats.json",
)


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _read_json(p: Path) -> dict:
    return json.loads(_read_text(p))


def _top_level_dashboard_files() -> list[Path]:
    """Customer-deployable dashboards — the *.json files at the top of
    dashboards/, NOT including anything under reference-mini/."""
    return sorted(DASHBOARDS_DIR.glob("*.json"))


def _reference_mini_dashboard_files() -> list[Path]:
    """The Mini-specific reference snapshots under reference-mini/."""
    if not REFERENCE_MINI_DIR.exists():
        return []
    return sorted(REFERENCE_MINI_DIR.glob("*.json"))


def _all_dashboard_files() -> list[Path]:
    """Every dashboard JSON shipped in the installer — top-level
    customer-deployable set plus everything under reference-mini/."""
    return _top_level_dashboard_files() + _reference_mini_dashboard_files()


# ---------------------------------------------------------------------------
# S1. All eight expected reference-mini dashboards are present.
# ---------------------------------------------------------------------------

def test_S1_all_expected_reference_mini_dashboards_present():
    """The eight VPS-restored dashboards W26b mirrors must all exist
    under dashboards/reference-mini/. Explicit allowlist so an
    accidental rename or delete is surfaced loudly rather than
    silently shrinking the set."""
    assert REFERENCE_MINI_DIR.exists(), (
        f"reference-mini/ directory does not exist at {REFERENCE_MINI_DIR} "
        "— W26b mirrors the eight VPS-restored dashboards into it."
    )
    present = {p.name for p in _reference_mini_dashboard_files()}
    expected = set(EXPECTED_REFERENCE_MINI_DASHBOARDS)
    missing = sorted(expected - present)
    unexpected = sorted(present - expected)
    assert not missing, (
        "reference-mini/ is missing expected dashboard(s):\n  "
        + "\n  ".join(missing)
        + "\nW26b ships exactly these eight files — a missing one means "
        "an accidental delete or rename."
    )
    assert not unexpected, (
        "reference-mini/ contains unexpected dashboard JSON file(s):\n  "
        + "\n  ".join(unexpected)
        + "\nIf a ninth dashboard was deliberately added, update "
        "EXPECTED_REFERENCE_MINI_DASHBOARDS in this test with a note. "
        "If it was not deliberate, it should not be here."
    )


# ---------------------------------------------------------------------------
# S2. Every installer dashboard JSON parses.
# ---------------------------------------------------------------------------

def test_S2_every_installer_dashboard_json_parses():
    """Every dashboard JSON shipped in the installer — the top-level
    customer-deployable set and everything under reference-mini/ —
    must parse as valid JSON. Catches corruption introduced on ship
    (truncated scp, encoding mangling, an editor's stray byte)."""
    files = _all_dashboard_files()
    assert files, (
        f"No dashboard JSON files found under {DASHBOARDS_DIR} at all — "
        "the installer bundle has been gutted."
    )
    offenders = []
    for f in files:
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            rel = f.relative_to(DASHBOARDS_DIR)
            offenders.append(f"{rel}: {exc}")
    assert not offenders, (
        "Installer dashboard JSON file(s) failed to parse:\n  "
        + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# S3. Every installer dashboard has a modern schemaVersion.
# ---------------------------------------------------------------------------

def test_S3_every_installer_dashboard_schema_version_is_modern():
    """Every dashboard JSON must have an integer schemaVersion >= 30
    (Grafana 9.0+). Below that, Grafana 13's on-the-fly migrator runs
    on load and — as W26a found — can drop panel datasource refs
    inconsistently. Same threshold as W26a S4, applied here across the
    whole installer dashboard set as a cohort guard."""
    offenders = []
    for f in _all_dashboard_files():
        rel = f.relative_to(DASHBOARDS_DIR)
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # S2 owns the parse failure; don't double-report it here.
            continue
        sv = d.get("schemaVersion")
        if not isinstance(sv, int):
            offenders.append(f"{rel}: schemaVersion is {sv!r}, not an int")
        elif sv < 30:
            offenders.append(f"{rel}: schemaVersion is {sv} (need >= 30)")
    assert not offenders, (
        "Installer dashboard(s) with an old or missing schemaVersion — "
        "Grafana 13's auto-migrator runs on load below schemaVersion 30 "
        "and can drop panel datasource refs (see W26a):\n  "
        + "\n  ".join(offenders)
        + "\nIf a reference-mini/ dashboard is genuinely stuck on an old "
        "schema, stop and decide deliberately (bump it, or carve it out "
        "with a documented reason) — do not silently lower this guard."
    )


# ---------------------------------------------------------------------------
# S4. reference-mini/ is ALLOWED to contain the hardcoded Mini IP.
# ---------------------------------------------------------------------------

def test_S4_reference_mini_may_contain_hardcoded_mini_ip():
    """Documentation assertion — asserts nothing either way about the
    presence of 100.69.66.32 inside reference-mini/. It exists so a
    future reader understands that S5's customer-shipability gate is
    DELIBERATELY scoped to exclude reference-mini/: the whole reason
    those eight dashboards live in a separate subfolder is that five
    of them carry the developer Mini's Tailscale IP and are therefore
    not customer-deployable as-is.

    The only thing this test enforces is that reference-mini/ exists
    and is non-empty — i.e. the carve-out it documents is real. The
    presence/absence of the IP within it is intentionally not asserted.
    """
    assert REFERENCE_MINI_DIR.exists(), (
        f"reference-mini/ does not exist at {REFERENCE_MINI_DIR}"
    )
    files = _reference_mini_dashboard_files()
    assert files, (
        "reference-mini/ exists but contains no dashboard JSON files — "
        "the carve-out S5 relies on is empty."
    )
    # No assertion on IP content by design. See docstring.


# ---------------------------------------------------------------------------
# S5. Customer-deployable dashboards must NOT contain the Mini IP.
# ---------------------------------------------------------------------------

def test_S5_top_level_dashboards_have_no_hardcoded_mini_ip():
    """The customer-shipability gate. Every *.json directly in
    dashboards/ (the set the installer autoloads onto a customer Mac
    via scripts/install_grafana_provisioning.sh) must NOT contain the
    hardcoded 100.69.66.32 Tailscale IP. A customer's network has no
    such host; a dashboard carrying it would render broken iframes.

    reference-mini/ is deliberately excluded from this check — that is
    the entire point of the subfolder (see S4)."""
    offenders = []
    for f in _top_level_dashboard_files():
        text = f.read_text(encoding="utf-8")
        if MINI_TAILSCALE_IP in text:
            count = text.count(MINI_TAILSCALE_IP)
            offenders.append(f"{f.name}: {count} occurrence(s)")
    assert not offenders, (
        f"Customer-deployable dashboard(s) contain the developer Mini's "
        f"Tailscale IP {MINI_TAILSCALE_IP!r}:\n  "
        + "\n  ".join(offenders)
        + "\nThese dashboards autoload onto a customer Mac — a hardcoded "
        "Mini IP produces broken iframe panels on the customer's network. "
        "Move the dashboard into reference-mini/ if it is genuinely "
        "Mini-specific, or remove the hardcoded IP."
    )


# ---------------------------------------------------------------------------
# S6. reference-mini/ is documented in the installer README.
# ---------------------------------------------------------------------------

def test_S6_reference_mini_is_documented_in_readme():
    """The installer's grafana/README.md must explain what
    reference-mini/ is and that it is not customer-deployable.
    Documentation is part of the deliverable — an undocumented
    reference-mini/ folder is an invitation for a future contributor
    to either ship its contents to customers or delete it as cruft."""
    assert GRAFANA_README.exists(), (
        f"installer grafana README does not exist at {GRAFANA_README}"
    )
    readme = _read_text(GRAFANA_README)
    assert "reference-mini/" in readme, (
        "installer/macos-pkg/resources/grafana/README.md does not "
        "mention reference-mini/ — the folder's purpose must be "
        "documented (what it is, and that it is not customer-deployable)."
    )
    # The README must convey the not-customer-deployable nature, not
    # merely name-drop the folder. Accept any of the phrasings W26b's
    # README edit uses.
    lowered = readme.lower()
    conveys_not_deployable = any(
        phrase in lowered
        for phrase in (
            "not customer-deployable",
            "not customer deployable",
            "not part of the customer-deployable",
        )
    )
    assert conveys_not_deployable, (
        "grafana/README.md mentions reference-mini/ but does not state "
        "that it is NOT customer-deployable. The documentation must make "
        "the boundary explicit, not just name the folder."
    )
