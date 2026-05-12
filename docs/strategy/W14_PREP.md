# W14 Prep — Two-Postgres-Instance Split

> **Status:** Plan. Not executed yet.
> **Read first:** [`AMENDMENTS_2026-05-12.md`](AMENDMENTS_2026-05-12.md) §A01 for the why and the sequencing decision.
> **Effort:** W14a M (3-5 days) → W14 M (3-4 days) → W14b XS (under an hour). Total ~5-9 days.
> **Risk:** Medium. Data migration involved. Plan a maintenance window.
> **Rollback:** Every step has a defined rollback. Documented inline.

---

## Mental model

**Today (State A).** One Docker container, one Postgres process, two databases inside it.

```
Mini host
└── Docker container "mining-guardian-db"
    └── Postgres 16 on port 5432
        ├── database: mining_guardian            (operational)
        └── database: mining_guardian_catalog    (catalog)
```

**Target (State B).** Two Docker containers, each running one Postgres process with one database.

```
Mini host
├── Docker container "mg-operational-db"        (continues to be "mining-guardian-db" if we don't rename — see decision D1 below)
│   └── Postgres 16 on port 5432
│       └── database: mining_guardian           (operational)
└── Docker container "mg-catalog-db"
    └── Postgres 16 on port 5433
        └── database: mining_guardian_catalog   (catalog)
```

Everything else (Ollama, Grafana, the 9 launchd services, the .env file) stays as-is. Only the Postgres surface changes.

---

## Open decisions before execution

These need a Yes/No or a value before W14 starts. None are blockers for W14a.

| ID | Decision | Default if not chosen | Why it matters |
|---|---|---|---|
| **D1** | Rename `mining-guardian-db` → `mg-operational-db`, or keep it? | **Keep** (less risk; one fewer thing to migrate) | Rename means updating every script that does `docker exec mining-guardian-db ...`; `db_maintenance.sh` and `daily_backup.sh` reference it by name |
| **D2** | Same password for both instances, or different? | **Same** (one `GUARDIAN_PG_PASSWORD` covers both) | Different is more secure but means two `.env` vars and two backup-script credentials |
| **D3** | Same data directory parent, or two separate parents? | **One parent dir** (`/Library/Application Support/MiningGuardian/pgdata-{operational,catalog}/`) | One parent makes backup-scripts simpler; two parents protect against shared-filesystem corruption |
| **D4** | Catalog instance `shared_buffers` size | `512MB` | Catalog is smaller and read-mostly; doesn't need operational's 1GB. After W04 lands, both get explicit tuning |
| **D5** | Apply Phase 1 tuning (W02, W04) before or after the split? | **After**, per A01 sequencing | If tuned before, tunables get re-applied after the split anyway |
| **D6** | Backup script changes — single combined script or two separate scripts? | **Two scripts** (`backup_operational.sh`, `backup_catalog.sh`) called by a wrapper | Clearer rollback if one backup fails; aligns with future federation where catalog goes to master and operational stays local |
| **D7** | First customer-ship .pkg builds include the two-container provisioning, or wait one cycle? | **Include** | Otherwise the next customer install would be State A and W14 would have to happen on every customer Mini |

---

## W14a — The cleanup PR (Phase 0)

### Goal

Refactor 27 files that bypass `core/db_targets.py` to go through it. **No behavior change.** All connections still go to port 5432; only the *path* through code changes.

### File list

3 mixed + 24 pure Pattern 2 = 27 files. Authoritative list in `AMENDMENTS_2026-05-12.md` §A01.

### Refactor pattern

**Before (Pattern 2):**
```python
import psycopg2
import os

def _get_db_connection():
    host = os.environ.get("GUARDIAN_PG_HOST", "localhost")
    port = os.environ.get("GUARDIAN_PG_PORT", "5432")
    user = os.environ.get("GUARDIAN_PG_USER", "mg")
    password = os.environ.get("GUARDIAN_PG_PASSWORD", "")
    dbname = os.environ.get("GUARDIAN_PG_DBNAME", "mining_guardian")
    return psycopg2.connect(host=host, port=port, user=user, password=password, dbname=dbname)
```

**After (Pattern 1):**
```python
import psycopg2
from core.db_targets import operational_target

def _get_db_connection():
    return psycopg2.connect(**operational_target().connect_kwargs())
```

For catalog readers: substitute `catalog_target()`.

### Order to do the refactor in

Touch small, low-blast-radius files first to validate the pattern, then work up to the workhorses. Suggested order:

1. **Scripts first (3 files):** `scripts/daily_log_failure_report.py`, `scripts/direct_collect_logs.py`, `scripts/morning_briefing.py` — short, daily-run scope, easy to smoke-test.
2. **Monitoring / single-purpose (2 files):** `console/system_state.py`, `core/hashrate_evaluation.py`.
3. **API services (8 files):** `api/system_settings.py`, `api/approval_api.py`, `api/slack_approval_listener.py`, `api/slack_command_handler.py`, `api/ams_alert_listener.py`, `api/ai_dashboard_api.py`, `api/dashboard_api.py`, `api/intelligence_report_api.py`. Restart each service after its refactor and run a `curl /health` against it.
4. **AI workers (8 files):** `ai/ai_score.py`, `ai/confidence_scorer.py`, `ai/predictor.py`, `ai/fingerprint_builder.py`, `ai/hvac_correlator.py`, `ai/local_llm_analyzer.py`, `ai/train_cohort.py`, `ai/daily_deep_dive.py`. Smoke-test by triggering one scan or a `--smoke-test` mode.
5. **Mixed-pattern stragglers (3 files):** `ai/catalog_context.py`, `intelligence-catalog/catalog-api/catalog_api.py`, `intelligence-catalog/db/dual_writer.py`. These already partly use Pattern 1; finish them.
6. **Long-running services / core (3 files):** `core/llm_analyzer.py`, `core/overnight_automation.py`, `core/database_pg.py`. Save for last — they have the broadest impact if a refactor breaks them.

Group the PRs as makes sense (one PR per group, or one big PR — operator's call). The handoff convention says one PR per W-item is ideal, but Failure Mode 9 ("sibling sweeps OK in one PR") permits a single W14a PR covering all 27 files. Recommend a single PR.

### The cohort guard test

Land with W14a. Save as `tests/test_w14a_no_direct_pg_env_reads.py`:

```python
"""W14a cohort guard — every Postgres connector goes through core.db_targets.

Pattern 2 (reading os.environ.get('GUARDIAN_PG_HOST') etc. directly) silently
breaks when catalog moves to a separate instance in W14. See A01 in
docs/strategy/AMENDMENTS_2026-05-12.md.

This test fails on any new file that reintroduces Pattern 2.
"""
from __future__ import annotations
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# core/db_targets.py is the ONE place that resolves these env vars.
# Tests are allowed to set/inspect them.
ALLOWED_BYPASSES = {
    "core/db_targets.py",
}

# Patterns we consider "Pattern 2" — direct env reads of the connect params.
PATTERN_2_REGEX = re.compile(
    r"GUARDIAN_PG_(HOST|PORT)"
)

# Roots to scan. Anything outside these can read env vars freely.
SCAN_ROOTS = ["ai", "api", "core", "console", "monitoring", "scripts",
              "intelligence-catalog"]


def _scan() -> list[str]:
    offenders: list[str] = []
    for root in SCAN_ROOTS:
        root_path = REPO_ROOT / root
        if not root_path.exists():
            continue
        for py in root_path.rglob("*.py"):
            rel = py.relative_to(REPO_ROOT).as_posix()
            if rel in ALLOWED_BYPASSES:
                continue
            if rel.startswith("tests/"):
                continue
            try:
                text = py.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            if PATTERN_2_REGEX.search(text):
                offenders.append(rel)
    return sorted(offenders)


def test_no_pattern_2_outside_db_targets():
    offenders = _scan()
    assert not offenders, (
        f"\n{len(offenders)} file(s) read GUARDIAN_PG_HOST/PORT directly, "
        "bypassing core.db_targets:\n  " + "\n  ".join(offenders) +
        "\n\nUse core.db_targets.operational_target() or catalog_target() "
        "instead.\n"
        "See docs/strategy/AMENDMENTS_2026-05-12.md A01 for rationale."
    )
```

This test currently *would fail* on the 27 unfixed files. It will pass the moment W14a's refactor completes — that's the gate that W14a is done. If somebody later reintroduces Pattern 2, the test fires.

### W14a smoke tests

After the refactor PR lands and is deployed to the Mini:

```bash
# 1. All 9 always-on services start and stay up
launchctl list | grep com.miningguardian | wc -l       # expect: 9 (with -1 for the scanner being scheduled-shaped)
launchctl list | grep com.miningguardian | grep -v -E ' [0-9]+ '   # expect: empty (no '-' PIDs)

# 2. One daily-deep-dive smoke run
"${INSTALL_ROOT}/venv/bin/python" -m ai.daily_deep_dive --smoke-test --miner-ip 192.168.188.10

# 3. One scan completes
"${INSTALL_ROOT}/venv/bin/python" -m core.mining_guardian --once

# 4. Slack listener responds to /ping (or whatever its health command is)

# 5. The new cohort guard test
cd "${REPO_ROOT}" && pytest tests/test_w14a_no_direct_pg_env_reads.py
```

### W14a rollback

`git revert <W14a-PR-merge-commit>`. Behavior is identical before and after the refactor, so revert is purely cosmetic and risk-free.

---

## W14 — The topology change

### Pre-flight checklist

- [ ] W14a merged to main, deployed to Mini, smoke tests green
- [ ] Decisions D1-D7 made
- [ ] Maintenance window scheduled (~2 hours; mostly waits)
- [ ] Operational and catalog backups taken NOW, not at the start of the window — see Step 0 below
- [ ] `.env` on Mini backed up to `.env.pre-w14`

### Step 0 — Take baseline backups (do these the day before, not during the window)

```bash
# On the Mini, against the current single-container setup
docker exec mining-guardian-db pg_dump -U mg -d mining_guardian \
  | gzip > /Library/Application\ Support/MiningGuardian/backups/pre-w14-operational-$(date +%Y%m%d).sql.gz

docker exec mining-guardian-db pg_dump -U mg -d mining_guardian_catalog \
  | gzip > /Library/Application\ Support/MiningGuardian/backups/pre-w14-catalog-$(date +%Y%m%d).sql.gz

# Verify each restores cleanly to a scratch DB BEFORE proceeding
docker exec mining-guardian-db createdb -U mg mining_guardian_catalog_test
gunzip -c /Library/Application\ Support/MiningGuardian/backups/pre-w14-catalog-*.sql.gz \
  | docker exec -i mining-guardian-db psql -U mg -d mining_guardian_catalog_test
# Spot-check: row counts of hardware.miner_models, ops.failure_patterns, etc.
docker exec mining-guardian-db psql -U mg -d mining_guardian_catalog_test \
  -c "SELECT 'miner_models' AS table, count(*) FROM hardware.miner_models
      UNION ALL
      SELECT 'failure_patterns', count(*) FROM ops.failure_patterns;"
docker exec mining-guardian-db dropdb -U mg mining_guardian_catalog_test
```

If the restore-and-verify fails, **stop W14**. Do not proceed without a known-good backup.

### Step 1 — Stop the 12 launchd scheduled jobs from firing during the window

Pause the launchd schedules; leave the 9 always-on services running for now (they'll glitch briefly when the catalog moves but their callers all tolerate brief disconnects via the existing circuit-breaker pattern in `ai/catalog_context.py`).

```bash
for f in /Library/LaunchDaemons/com.miningguardian.scheduled.*.plist; do
  sudo launchctl unload "$f"
done
```

### Step 2 — Start the second Postgres container

```bash
# Create the new data directory
sudo mkdir -p "/Library/Application Support/MiningGuardian/pgdata-catalog"
sudo chown -R "${INSTALL_USER}:" "/Library/Application Support/MiningGuardian/pgdata-catalog"

# Start the catalog container
docker run -d \
    --name mg-catalog-db \
    --restart unless-stopped \
    -p 127.0.0.1:5433:5432 \
    -e POSTGRES_DB=mining_guardian_catalog \
    -e POSTGRES_USER=mg \
    -e POSTGRES_PASSWORD="${MG_DB_PASSWORD}" \
    -v "/Library/Application Support/MiningGuardian/pgdata-catalog:/var/lib/postgresql/data" \
    postgres:16-bookworm

# Wait for it to be ready
for i in {1..60}; do
    docker exec mg-catalog-db pg_isready -U mg -d mining_guardian_catalog >/dev/null 2>&1 \
      && { echo "ready after ${i}s"; break; }
    sleep 1
done
```

### Step 3 — Restore catalog into the new instance

The container's bootstrap created an empty `mining_guardian_catalog` database. Drop it (so the restore doesn't fight with the schema bootstrap) and restore from the backup:

```bash
# Drop the empty bootstrap DB and recreate (POSTGRES_DB created it on first start)
docker exec mg-catalog-db psql -U mg -d postgres -c "DROP DATABASE mining_guardian_catalog;"
docker exec mg-catalog-db psql -U mg -d postgres -c "CREATE DATABASE mining_guardian_catalog OWNER mg;"

# Restore
gunzip -c /Library/Application\ Support/MiningGuardian/backups/pre-w14-catalog-*.sql.gz \
  | docker exec -i mg-catalog-db psql -U mg -d mining_guardian_catalog

# Verify row counts match the source
docker exec mg-catalog-db psql -U mg -d mining_guardian_catalog \
  -c "SELECT 'miner_models' AS t, count(*) FROM hardware.miner_models
      UNION ALL SELECT 'failure_patterns', count(*) FROM ops.failure_patterns
      UNION ALL SELECT 'war_stories', count(*) FROM market.war_stories;"
# Compare against the same query against the original container
```

Numbers must match exactly. If they don't, drop the new container and investigate before proceeding.

### Step 4 — Update `.env` and `db_targets.py`

```bash
# Add to /Library/Application Support/MiningGuardian/.env
echo "" >> /Library/Application\ Support/MiningGuardian/.env
echo "# W14 — catalog DB now on a separate Postgres instance on port 5433" >> /Library/Application\ Support/MiningGuardian/.env
echo "GUARDIAN_PG_CATALOG_HOST=127.0.0.1" >> /Library/Application\ Support/MiningGuardian/.env
echo "GUARDIAN_PG_CATALOG_PORT=5433" >> /Library/Application\ Support/MiningGuardian/.env
```

Then in `core/db_targets.py` (this is the only Python file W14 itself touches):

```python
# Add alongside _resolve_host() and _resolve_port():

def _resolve_catalog_host() -> str:
    """W14: catalog can live on a different host. Default falls back to the
    operational host for backward compatibility with State A deployments."""
    return os.environ.get("GUARDIAN_PG_CATALOG_HOST") or _resolve_host()

def _resolve_catalog_port() -> int:
    """W14: catalog can live on a different port."""
    raw = os.environ.get("GUARDIAN_PG_CATALOG_PORT", "")
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return _resolve_port()  # fall back to operational port


# Update catalog_target() to use the new resolvers:
def catalog_target() -> DBTarget:
    """..."""
    return DBTarget(
        host=_resolve_catalog_host(),
        port=_resolve_catalog_port(),
        user=_resolve_user(),
        password=_resolve_password(),
        dbname=os.environ.get("GUARDIAN_PG_CATALOG_DBNAME", _DEFAULT_CATALOG_DBNAME),
    )
```

**Why the fallback design.** If `GUARDIAN_PG_CATALOG_HOST` and `GUARDIAN_PG_CATALOG_PORT` aren't set, catalog reads still work — they hit the operational host/port. This means rolling back W14 is config-only: remove the two new env vars and catalog reads point at port 5432 again.

### Step 5 — Bounce the always-on services so they pick up the new env

```bash
for svc in scanner alerts approval-api dashboard-api slack-listener slack-commands console intelligence-report overnight-automation; do
  sudo launchctl bootout system "/Library/LaunchDaemons/com.miningguardian.${svc}.plist"
  sudo launchctl bootstrap system "/Library/LaunchDaemons/com.miningguardian.${svc}.plist"
done

# Confirm all 9 are running
launchctl list | grep com.miningguardian | head -20
```

### Step 6 — Smoke-test before re-enabling scheduled jobs

```bash
# Verify catalog reads come from port 5433
"${INSTALL_ROOT}/venv/bin/python" -c "
from core.db_targets import operational_target, catalog_target
print('operational:', operational_target().host, operational_target().port, operational_target().dbname)
print('catalog:    ', catalog_target().host, catalog_target().port, catalog_target().dbname)
"
# Expect: operational 127.0.0.1 5432 mining_guardian
#         catalog     127.0.0.1 5433 mining_guardian_catalog

# Run the daily deep dive smoke test
"${INSTALL_ROOT}/venv/bin/python" -m ai.daily_deep_dive --smoke-test --miner-ip 192.168.188.10

# Trigger one normal scan
"${INSTALL_ROOT}/venv/bin/python" -m core.mining_guardian --once
```

If catalog queries return data, the split worked.

### Step 7 — Drop the catalog DB from the operational instance

**Only after** confirming the new instance is serving reads correctly:

```bash
docker exec mining-guardian-db psql -U mg -d postgres \
  -c "DROP DATABASE mining_guardian_catalog;"
```

This is irreversible without restoring from the backup. **Do not skip Step 6 before Step 7.**

### Step 8 — Re-enable scheduled jobs

```bash
for f in /Library/LaunchDaemons/com.miningguardian.scheduled.*.plist; do
  sudo launchctl load "$f"
done
```

Watch the next morning briefing (~07:00 CDT) and the 16:00 daily deep dive to confirm catalog queries succeed in production.

### Step 9 — Update backup scripts

`scripts/daily_backup.sh` (or wherever the daily backup lives) should now run `pg_dump` against each container separately. Per D6, two scripts called by a wrapper.

### Step 10 — Update the installer

`installer/macos-pkg/scripts/lib/install_colima.sh` and `installer/macos-pkg/scripts/postinstall.sh` need updates so fresh customer installs come up in State B directly. This is the bulk of the "installer" work for W14. Concretely:

- `install_colima.sh` gains a second `docker run` block for `mg-catalog-db` on port 5433
- `postinstall.sh::step_provision_postgres` issues `CREATE DATABASE mining_guardian_catalog OWNER mg` against the catalog container, not the operational one
- `.env` template gets the two new `GUARDIAN_PG_CATALOG_*` variables

### W14 rollback

If something breaks after Step 7 (the irreversible step), the rollback is:

1. Drop the data dir for the catalog container: `docker stop mg-catalog-db && docker rm -f mg-catalog-db && sudo rm -rf "/Library/Application Support/MiningGuardian/pgdata-catalog"`
2. Restore the catalog into the operational container: `docker exec mining-guardian-db psql -U mg -d postgres -c "CREATE DATABASE mining_guardian_catalog OWNER mg;" && gunzip -c .../pre-w14-catalog-*.sql.gz | docker exec -i mining-guardian-db psql -U mg -d mining_guardian_catalog`
3. Remove the two new env vars from `.env`
4. Bootout/bootstrap all 9 services
5. Re-enable scheduled jobs

Time-to-rollback: ~10 minutes. The pre-w14 backup is the rollback artifact.

If breakage happens before Step 7, rollback is trivial — just `docker stop mg-catalog-db && docker rm -f mg-catalog-db` and remove the env vars.

---

## W14b — Lock the convention

After W14 lands and is stable for at least one full day (one daily deep dive + one weekly training):

### Edit 1 — `CLAUDE.md`

Add under "Coding Conventions" (or create the section if it doesn't yet exist):

```markdown
### Postgres connections

All Postgres access goes through `core.db_targets.operational_target()` or
`core.db_targets.catalog_target()`. **Never read `GUARDIAN_PG_HOST` /
`GUARDIAN_PG_PORT` directly** outside `core/db_targets.py` itself — the
cohort guard test `tests/test_w14a_no_direct_pg_env_reads.py` will fail CI.

Why: the operational and catalog DBs live on **different ports** (W14, 2026-05).
The resolver handles host/port/dbname for whichever target you ask for; reading
the env vars directly silently misroutes catalog reads to the operational
instance.

```python
# Right
from core.db_targets import operational_target, catalog_target
op_conn = psycopg2.connect(**operational_target().connect_kwargs())
cat_conn = psycopg2.connect(**catalog_target().connect_kwargs())

# Wrong — fails CI via cohort guard test
host = os.environ.get("GUARDIAN_PG_HOST", "localhost")
port = os.environ.get("GUARDIAN_PG_PORT", "5432")
```
```

### Edit 2 — `.env.example`

Add a comment block above the `GUARDIAN_PG_*` lines:

```
# ──────────────────────────────────────────────────────────────────────
# Postgres connection (W14: two-instance topology since 2026-05)
# ──────────────────────────────────────────────────────────────────────
# Mining Guardian runs TWO separate Postgres instances on the Mini:
#   - operational DB on $GUARDIAN_PG_HOST:$GUARDIAN_PG_PORT (default 5432)
#   - catalog DB on $GUARDIAN_PG_CATALOG_HOST:$GUARDIAN_PG_CATALOG_PORT (default 5433)
# Python code MUST go through core.db_targets — do NOT read these vars directly.
# See docs/strategy/AMENDMENTS_2026-05-12.md §A01 for the rationale.
# ──────────────────────────────────────────────────────────────────────
GUARDIAN_PG_HOST=127.0.0.1
GUARDIAN_PG_PORT=5432
GUARDIAN_PG_USER=mg
GUARDIAN_PG_PASSWORD=<set during install>
GUARDIAN_PG_DBNAME=mining_guardian

GUARDIAN_PG_CATALOG_HOST=127.0.0.1
GUARDIAN_PG_CATALOG_PORT=5433
GUARDIAN_PG_CATALOG_DBNAME=mining_guardian_catalog
```

### Edit 3 — `installer/macos-pkg/scripts/lib/install_colima.sh` docstring

Document the two-container assumption at the top of the file:

```bash
# ──────────────────────────────────────────────────────────────────────
# install_colima.sh — Colima runtime + Postgres container(s) provisioning
#
# W14 (2026-05): provisions TWO Postgres containers on the Mini:
#   - mining-guardian-db (operational) on 127.0.0.1:5432
#   - mg-catalog-db     (catalog)      on 127.0.0.1:5433
# Each has its own data volume; backups run separately per instance.
# See docs/strategy/AMENDMENTS_2026-05-12.md §A01.
# ──────────────────────────────────────────────────────────────────────
```

---

## Open questions for operator before kickoff

1. Decisions D1-D7 above — pick defaults or override.
2. When is the maintenance window? The catalog read path goes through a circuit breaker, so brief outages are tolerated by the always-on services. The risk window is Step 7 (DROP DATABASE on the old catalog) — that needs to happen between scan cycles, not during one. Quietest hour is 02:00-04:00 CDT (between the 01:00 refinement chain and the 04:00 db_maintenance).
3. Do we want a "dry run" Mini-side rehearsal in a sandbox before doing it on the live Mini? Not strictly necessary given the rollback design, but cheap insurance.
4. After W14 lands, are we ready to start W02/W04 (Postgres tuning + pg_stat_statements) against the new topology? Or defer those?
