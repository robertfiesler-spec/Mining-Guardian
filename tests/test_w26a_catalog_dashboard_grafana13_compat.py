"""
tests/test_w26a_catalog_dashboard_grafana13_compat.py

W26a (2026-05-13) — Intelligence Catalog dashboard renders correctly
under Grafana 13.

This work item closes three distinct breakage modes that all surfaced
on the Mini after W25/W25b unblocked the iframe + dashboard_api paths
and the Intelligence Catalog dashboard finally tried to render. The
Mini had already been patched live; this test module locks the fixes
into the repo so future installs ship a working dashboard from day one.

Live evidence (Safari Web Inspector console on
/d/cfj6drj3pbk74b/intelligence-catalog):

  1. Markdown text panel rendering raw literal "\\n" escape characters
     (visible as `\n` in the rendered output, not as line breaks),
     producing one giant unbroken run-on paragraph that filled the
     viewport in panel-view mode.

  2. Four data panels (Database Overview, Tables by Schema, All 165
     Tables, Example: Firmware Tables) all returning "No data" with
     amber warning triangles. Browser console error:

         Error: You do not currently have a default database
         configured for this data source. Postgres requires a default
         database with which to connect. Please configure one through
         the Data Sources Configuration page, or if you are using a
         provisioning file, update that configuration file with a
         default database.
            at runRequest.catchError (runRequest.ts:164)

     This is a Grafana 12.2+ regression (grafana/grafana#112418).
     Grafana's frontend no longer reads the top-level `database` field
     from a provisioned Postgres datasource at panel-query time; it
     reads only `jsonData.database`. Datasources provisioned with the
     legacy top-level form pass their "Save & Test" check but fail
     every query thereafter.

  3. Dashboard JSON authored against `schemaVersion: 16` (Grafana 6.x
     era), with panel `datasource` set but target-level `datasource`
     missing. Grafana 13's on-the-fly dashboard migrator handles this
     inconsistently and occasionally drops the datasource reference on
     the target, leaving the SQL panel orphaned (no datasource, no
     query, no data).

Fixes shipped in this PR:

  A. installer/macos-pkg/resources/grafana/provisioning/datasources/
     mining_guardian.yml — `database: <name>` duplicated into the
     `jsonData:` block of each Postgres datasource (operational +
     2 catalog entries). The legacy top-level `database` is kept too,
     so old-Grafana-compatible installs still read it correctly.
     This is the bug-#112418 workaround.

  B. installer/macos-pkg/resources/grafana/dashboards/
     intelligence_catalog_live_queries.json:
       - Markdown text panel content: literal "\\n" sequences replaced
         with real newline characters.
       - `schemaVersion` bumped 16 → 39 so Grafana 13's auto-migrator
         doesn't run on load.
       - `datasource` ref pushed down onto every SQL target so the
         migrator can't lose it.

Asserted by this test module:

  S1. No plaintext-looking Postgres password in
      mining_guardian.yml. All postgres `password:` lines must use
      the `${GUARDIAN_PG_PASSWORD}` env-var form. This is a
      defence-in-depth guard against a future re-leak of the kind
      that produced the hardcoded hash on the Mini's copy of the
      yaml on 2026-05-13 — we don't want that shape to ever land
      in the repo.

  S2. Every Postgres datasource in mining_guardian.yml has a
      `database:` key inside its `jsonData:` block (the bug-#112418
      workaround). Without this, Grafana 12.2+ panels using these
      datasources will return "No data" at query time.

  S3. The Intelligence Catalog dashboard's markdown text panel
      contains real newline characters, not literal "\\n" escape
      sequences, in its content field.

  S4. The Intelligence Catalog dashboard's `schemaVersion` is >= 30,
      i.e. a modern Grafana 9.x+ value. The pre-fix value was 16,
      which forced Grafana 13's auto-migrator to run and produced
      flaky panel state.

  S5. Every SQL panel in the Intelligence Catalog dashboard has an
      explicit `datasource` on each of its targets (not just at the
      panel level). This pins the resolution path so Grafana's
      dashboard migrator cannot drop it during the load-time upgrade
      pass.

  S6. Failure Mode 9 sibling sweep — no other dashboard JSON shipped
      in installer/macos-pkg/resources/grafana/dashboards/ has the
      same `schemaVersion <= 20` + missing-target-datasource
      combination. If a sibling exists with the same bug pattern,
      W26a should expand to fix it rather than leaving a latent
      duplicate "No data" failure.

These tests run against the repo on the laptop, not the live
service on the Mini. The live smoke (refresh
/d/cfj6drj3pbk74b/intelligence-catalog in Safari and confirm all 5
panels populate with real data) is captured in the PR description.
"""
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALLER_GRAFANA = REPO_ROOT / "installer" / "macos-pkg" / "resources" / "grafana"
DATASOURCES_YAML = (
    INSTALLER_GRAFANA / "provisioning" / "datasources" / "mining_guardian.yml"
)
DASHBOARDS_DIR = INSTALLER_GRAFANA / "dashboards"
CATALOG_DASHBOARD = DASHBOARDS_DIR / "intelligence_catalog_live_queries.json"


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _read_json(p: Path) -> dict:
    return json.loads(_read_text(p))


# ---------------------------------------------------------------------------
# S1. No plaintext Postgres password in the yaml.
# ---------------------------------------------------------------------------

def test_S1_no_hardcoded_postgres_password_in_yaml():
    """Defence-in-depth guard: every postgres `password:` line in
    mining_guardian.yml must use the ${GUARDIAN_PG_PASSWORD} env-var
    form, never a literal value. Catches the regression where the
    Mini's live yaml had a 64-hex-char hash baked in, and would have
    landed in the repo if W26a hadn't sanitized it before committing.

    A literal password is anything that:
      - looks like a long hex string (>= 32 chars of [0-9a-f]),
      - or any non-env-var form for postgres datasources.
    """
    src = _read_text(DATASOURCES_YAML)
    # Find every `password: "..."` line and inspect the value.
    pw_lines = re.findall(r'password:\s*"([^"]*)"', src)
    assert pw_lines, "No password lines found at all — yaml is malformed."
    offenders = []
    for v in pw_lines:
        # The only acceptable form for postgres password is the env-var
        # interpolation. Bare strings or hex hashes are rejected.
        if v != "${GUARDIAN_PG_PASSWORD}":
            offenders.append(v[:8] + "..." if len(v) > 8 else v)
    assert not offenders, (
        "mining_guardian.yml contains plaintext-looking password "
        "value(s) — every postgres `password:` line must use the "
        "${GUARDIAN_PG_PASSWORD} env-var form. Offending value(s) "
        "(first 8 chars shown): " + ", ".join(offenders)
    )


# ---------------------------------------------------------------------------
# S2. `database` is inside jsonData for every postgres datasource.
# ---------------------------------------------------------------------------

def test_S2_database_inside_jsonData_for_every_postgres_datasource():
    """Grafana 12.2+ bug #112418 workaround: each Postgres datasource
    must have `database: <name>` inside its `jsonData:` block, not
    only at the top level. Without this, panels return 'No data'
    with the runRequest.catchError 'no default database configured'
    error in the browser console."""
    src = _read_text(DATASOURCES_YAML)
    # Find each datasource block. They start with `  - name:` and end
    # at the next `  - name:` or EOF. For each block whose `type:` is
    # postgres, the `jsonData:` block must contain a `database:` key.
    blocks = re.split(r"(?m)^\s{2}-\s+name:", src)[1:]
    postgres_blocks_seen = 0
    offenders = []
    for block in blocks:
        if re.search(r"(?m)^\s+type:\s+postgres\b", block) is None:
            continue
        postgres_blocks_seen += 1
        name_match = re.search(r"^\s*(.+?)$", block, flags=re.MULTILINE)
        name = (name_match.group(1).strip() if name_match else "<unknown>")
        # Pull the jsonData: block — everything indented deeper than
        # the `jsonData:` line itself.
        js_match = re.search(
            r"(?m)^\s+jsonData:\s*$\n((?:\s+\S.*\n?)+)", block
        )
        if not js_match:
            offenders.append(f"{name}: has no jsonData block at all")
            continue
        js_body = js_match.group(1)
        if not re.search(r"(?m)^\s+database:\s+\S+", js_body):
            offenders.append(f"{name}: jsonData lacks `database:` key")
    assert postgres_blocks_seen >= 3, (
        f"Expected at least 3 postgres datasources in yaml, found "
        f"{postgres_blocks_seen}. Test guard may be too strict, or "
        "the yaml has been gutted."
    )
    assert not offenders, (
        "Grafana 12.2+ bug #112418 workaround missing on the following "
        "postgres datasource(s) — each must have `database: <name>` "
        "inside its `jsonData:` block:\n  " + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# S3. Catalog dashboard text panel: no literal "\\n" escape sequences.
# ---------------------------------------------------------------------------

def test_S3_catalog_text_panel_has_real_newlines_not_escapes():
    """The markdown text panel in the Intelligence Catalog dashboard
    must contain real newline characters in its `content` field. If
    the JSON-encoded content contains the literal two-character
    sequence backslash-n inside the in-memory Python string, markdown
    renders one giant run-on paragraph."""
    d = _read_json(CATALOG_DASHBOARD)
    text_panels_seen = 0
    offenders = []
    for p in d.get("panels", []):
        if p.get("type") != "text":
            continue
        text_panels_seen += 1
        content = (p.get("options") or {}).get("content", "")
        if "\\n" in content:
            offenders.append(
                f"panel id={p.get('id')!r} "
                f"title={p.get('title', '<no title>')!r} "
                "still contains literal backslash-n in content"
            )
    assert text_panels_seen >= 1, (
        "Intelligence Catalog dashboard has no text panel. Expected at "
        "least one (the documentation panel). Test guard may be too "
        "strict, or the dashboard has been gutted."
    )
    assert not offenders, (
        "Text panel(s) contain literal backslash-n escape sequences "
        "instead of real newlines — markdown will render as one "
        "run-on paragraph:\n  " + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# S4. Catalog dashboard schemaVersion is modern.
# ---------------------------------------------------------------------------

def test_S4_catalog_dashboard_schema_version_is_modern():
    """The pre-W26a dashboard had `schemaVersion: 16` (Grafana 6.x
    era), which forced Grafana 13's auto-migrator to run on load and
    produced flaky panel state. The fix bumps it to a modern value
    (>= 30 covers Grafana 9.0+)."""
    d = _read_json(CATALOG_DASHBOARD)
    sv = d.get("schemaVersion")
    assert isinstance(sv, int), (
        f"Catalog dashboard has no integer schemaVersion (got {sv!r}). "
        "Grafana will reject the dashboard on load."
    )
    assert sv >= 30, (
        f"Catalog dashboard schemaVersion is {sv} — too old. Grafana "
        "13's on-the-fly migrator handles old schemas inconsistently "
        "and the catalog dashboard's panels lost their datasource refs "
        "during migration on the Mini. Bump to >= 30 (Grafana 9.0+)."
    )


# ---------------------------------------------------------------------------
# S5. Every SQL panel target has an explicit datasource.
# ---------------------------------------------------------------------------

def test_S5_catalog_sql_panel_targets_have_explicit_datasource():
    """Each SQL panel target in the Intelligence Catalog dashboard
    must have its own `datasource` key. The panel-level `datasource`
    alone isn't enough — Grafana's dashboard migrator can drop the
    target-level reference during the schemaVersion upgrade pass,
    leaving the SQL orphaned at query time."""
    d = _read_json(CATALOG_DASHBOARD)
    sql_panel_types = {"stat", "bargauge", "table", "timeseries", "gauge"}
    offenders = []
    sql_panels_seen = 0
    for p in d.get("panels", []):
        if p.get("type") not in sql_panel_types:
            continue
        sql_panels_seen += 1
        for t in p.get("targets", []) or []:
            ds = t.get("datasource")
            if not ds or not isinstance(ds, dict) or not ds.get("uid"):
                offenders.append(
                    f"panel id={p.get('id')!r} "
                    f"title={p.get('title', '<no title>')!r} "
                    f"target refId={t.get('refId', '<?>')} "
                    "is missing a target-level datasource"
                )
    assert sql_panels_seen >= 1, (
        "Catalog dashboard has no SQL data panels. Test guard may be "
        "too strict, or the dashboard has been gutted."
    )
    assert not offenders, (
        "SQL panel target(s) without an explicit datasource — "
        "Grafana's dashboard migrator may drop the panel-level ref:\n  "
        + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# S6. Sibling-sweep (Failure Mode 9).
# ---------------------------------------------------------------------------

def test_S6_no_other_dashboard_has_old_schema_with_targetless_datasources():
    """Failure Mode 9 sweep: no other dashboard JSON shipped in the
    installer should have the same `schemaVersion <= 20` plus
    missing-target-datasource combination that produced the W26a
    breakage. If a sibling does, this PR should expand to cover it
    rather than leave a latent 'No data' failure waiting to surface
    on the next dashboard refresh."""
    if not DASHBOARDS_DIR.exists():
        return  # no installer dashboards yet — nothing to sweep
    sql_panel_types = {"stat", "bargauge", "table", "timeseries", "gauge"}
    offenders = []
    for f in sorted(DASHBOARDS_DIR.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        sv = d.get("schemaVersion")
        if not isinstance(sv, int) or sv > 20:
            continue
        # Old schema — check whether SQL panels have target-level
        # datasource refs. If any are missing, this is the same bug
        # class as W26a and should be fixed in the same PR.
        for p in d.get("panels", []):
            if p.get("type") not in sql_panel_types:
                continue
            for t in p.get("targets", []) or []:
                ds = t.get("datasource")
                if not ds or not isinstance(ds, dict) or not ds.get("uid"):
                    offenders.append(
                        f"{f.name}: panel id={p.get('id')!r} "
                        f"target refId={t.get('refId', '<?>')} — "
                        f"old schemaVersion={sv} + missing target ds"
                    )
    assert not offenders, (
        "Sibling-sweep failure: the following dashboard JSON file(s) "
        "have the same bug pattern that W26a fixes in "
        "intelligence_catalog_live_queries.json — old schemaVersion "
        "AND missing target-level datasource. Either fold them into "
        "this PR (same bug class — fits Failure Mode 9 same-class-"
        "cohort rule) or open a sibling ticket and explicitly carve "
        "them out of this guard.\n  " + "\n  ".join(offenders)
    )
