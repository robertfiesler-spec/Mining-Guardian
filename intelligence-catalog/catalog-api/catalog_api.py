"""
Catalog API Service — FastAPI on port 8420
Serves knowledge bundles from the Mining Intelligence Catalog for local LLM injection (Qwen on Mac Mini).

Phase 1: READ-only path. Queries PostgreSQL catalog tables, returns structured
knowledge bundles and pre-formatted prompt text for LLM system prompt injection.
"""

import hashlib
import hmac
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Literal, Optional

import psycopg2
import psycopg2.pool
from cachetools import TTLCache
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("catalog-api")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_HOST = os.getenv("DB_HOST", "mining-guardian-db")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "mining_guardian")
DB_USER = os.getenv("DB_USER", "guardian_admin")
DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise EnvironmentError(
        "DB_PASSWORD must be set in the environment. Populate the catalog-api .env file."
    )

# CRIT-6: API key must be set explicitly. The old default
# "CHANGE_ME_TO_A_REAL_SECRET" is REJECTED — if you see that string in your
# .env, the installer never ran (or you copied .env.example without editing).
# Generate one with:  python -c "import secrets; print(secrets.token_hex(32))"
API_KEY = os.getenv("CATALOG_API_KEY")
_FORBIDDEN_API_KEYS = {
    None, "", "CHANGE_ME_TO_A_REAL_SECRET",
    "__GENERATE_AT_INSTALL_TIME__", "__SET_BY_INSTALLER__",
}
if API_KEY in _FORBIDDEN_API_KEYS:
    raise EnvironmentError(
        "CATALOG_API_KEY must be set to a real secret in the environment. "
        "The placeholder value is rejected. "
        'Generate one with:  python -c "import secrets; print(secrets.token_hex(32))"'
    )
if len(API_KEY) < 32:
    raise EnvironmentError(
        f"CATALOG_API_KEY is too short ({len(API_KEY)} chars; need ≥ 32). "
        'Generate one with:  python -c "import secrets; print(secrets.token_hex(32))"'
    )

# CRIT-6: default to loopback. Docker port mapping in docker-compose.yml is
# what exposes this to the host — the FastAPI process itself should bind
# loopback only inside the container. If you need external reach, override
# with API_HOST=0.0.0.0 + ensure auth + TLS upstream.
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8420"))

# CRIT-6: rate limit defaults. Override with env vars if needed (e.g. fleet
# of 1000 miners scanning every 5 min would need a higher cap).
RATE_LIMIT_SCAN_BUNDLE = os.getenv("CATALOG_RATE_LIMIT_SCAN_BUNDLE", "60/minute")
RATE_LIMIT_MINER = os.getenv("CATALOG_RATE_LIMIT_MINER", "120/minute")
RATE_LIMIT_HEALTH = os.getenv("CATALOG_RATE_LIMIT_HEALTH", "600/minute")

# ---------------------------------------------------------------------------
# Connection pool (created at startup, closed at shutdown)
# ---------------------------------------------------------------------------
pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None

# In-memory caches
bundle_cache: TTLCache = TTLCache(maxsize=256, ttl=300)       # 5 min
model_cache: TTLCache = TTLCache(maxsize=512, ttl=3600)       # 1 hour


def _create_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Create a threaded connection pool to PostgreSQL."""
    return psycopg2.pool.ThreadedConnectionPool(
        minconn=2,
        maxconn=20,
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        options="-c search_path=public,hardware,firmware,ops,market,repair,pool,facility,regulatory,knowledge,seed",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage connection pool lifecycle."""
    global pool
    try:
        pool = _create_pool()
        logger.info("PostgreSQL connection pool created (%s:%s/%s)", DB_HOST, DB_PORT, DB_NAME)
    except Exception as exc:
        logger.error("Failed to create DB pool: %s", exc)
        pool = None
    yield
    if pool:
        pool.closeall()
        logger.info("PostgreSQL connection pool closed")


app = FastAPI(
    title="Mining Intelligence Catalog API",
    version="1.0.0",
    description="READ-only API serving knowledge bundles from the Intelligence Catalog.",
    lifespan=lifespan,
)

# CRIT-6: rate limiter, keyed by client IP (X-Forwarded-For aware via slowapi).
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------
async def verify_token(authorization: Optional[str] = Header(None)) -> None:
    """Validate Bearer token from Authorization header.

    CRIT-6: comparison uses hmac.compare_digest to defeat timing oracles.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Malformed Authorization header")
    submitted = parts[1]
    # hmac.compare_digest requires both args to be the same type and is
    # constant-time relative to the shorter of the two.
    if not hmac.compare_digest(submitted, API_KEY):
        raise HTTPException(status_code=403, detail="Invalid API key")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
# CRIT-6: section names are restricted to this allow-list. Anything else
# is rejected by Pydantic at request time.
SectionName = Literal[
    "failure_patterns", "firmware", "thresholds",
    "repair", "env_factors", "baselines",
]

# CRIT-6: per-field length caps to defeat trivial DoS / memory-blowup attempts.
# A real fleet has at most ~30 unique miner models; ~50 active issue codes is
# already on the high side. These caps are intentionally generous so a normal
# operator never hits them, but a bad actor cannot send a 10MB JSON list.
_MAX_MODELS = 200
_MAX_ISSUES = 100
_MAX_CHIPS = 100
_MAX_FW = 100
_MAX_STR_LEN = 256


class ScanBundleRequest(BaseModel):
    """Request body for the scan-bundle endpoint."""
    miner_models: list[str] = Field(
        default_factory=list,
        description="Model names from scan",
        max_length=_MAX_MODELS,
    )
    active_issues: list[str] = Field(
        default_factory=list,
        description="Active issue codes",
        max_length=_MAX_ISSUES,
    )
    chip_dies: list[str] = Field(
        default_factory=list,
        description="Chip die identifiers",
        max_length=_MAX_CHIPS,
    )
    firmware_versions: list[str] = Field(
        default_factory=list,
        description="Firmware versions in fleet",
        max_length=_MAX_FW,
    )
    include_sections: list[SectionName] = Field(
        default_factory=lambda: [
            "failure_patterns", "firmware", "thresholds", "repair", "env_factors", "baselines"
        ],
        description="Sections to include in the bundle (allow-listed)",
        max_length=len([
            "failure_patterns", "firmware", "thresholds",
            "repair", "env_factors", "baselines",
        ]),
    )

    @classmethod
    def _trim_strs(cls, values: list[str], field: str) -> list[str]:
        for v in values:
            if not isinstance(v, str):
                raise ValueError(f"{field}: list items must be strings")
            if len(v) > _MAX_STR_LEN:
                raise ValueError(
                    f"{field}: individual entries must be ≤ {_MAX_STR_LEN} chars"
                )
        return values

    def model_post_init(self, __context: Any) -> None:  # type: ignore[override]
        self._trim_strs(self.miner_models, "miner_models")
        self._trim_strs(self.active_issues, "active_issues")
        self._trim_strs(self.chip_dies, "chip_dies")
        self._trim_strs(self.firmware_versions, "firmware_versions")


class ScanBundleResponse(BaseModel):
    """Response from the scan-bundle endpoint."""
    context_bundle: dict[str, Any]
    prompt_text: str
    cache_key: str
    generated_at: str
    sources: list[str]


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def _get_conn():
    """Get a connection from the pool."""
    if pool is None:
        raise HTTPException(status_code=503, detail="Database pool not available")
    return pool.getconn()


def _put_conn(conn):
    """Return a connection to the pool."""
    if pool is not None:
        pool.putconn(conn)


def _query(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a query and return rows as dicts."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description is None:
                return []
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as exc:
        logger.error("Query error: %s | SQL: %s", exc, sql[:200])
        conn.rollback()
        return []
    finally:
        _put_conn(conn)


def _check_table_exists(table_name: str) -> bool:
    """Check if a table exists in any of the catalog schemas."""
    # Handle schema-qualified names (e.g., 'hardware.miner_models')
    if '.' in table_name:
        schema, tname = table_name.split('.', 1)
    else:
        schema = None
        tname = table_name

    if schema:
        rows = _query(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s",
            (schema, tname),
        )
    else:
        rows = _query(
            """SELECT 1 FROM information_schema.tables
               WHERE table_schema IN ('public','hardware','firmware','ops','market',
                                      'repair','pool','facility','regulatory','knowledge','seed')
                 AND table_name = %s""",
            (tname,),
        )
    return len(rows) > 0


def _safe_query(table: str, sql: str, params: tuple = ()) -> list[dict]:
    """Query a table, returning empty list if the table doesn't exist."""
    if not _check_table_exists(table):
        logger.warning("Table '%s' not found — skipping", table)
        return []
    return _query(sql, params)


# ---------------------------------------------------------------------------
# Fuzzy model matching using pg_trgm
# ---------------------------------------------------------------------------
def _fuzzy_match_models(model_names: list[str]) -> list[dict]:
    """
    Fuzzy-match scan model names against the miner_models table.
    Uses pg_trgm similarity for fuzzy matching with a fallback to ILIKE.
    Returns matched rows with similarity scores.
    """
    if not model_names or not _check_table_exists("hardware.miner_models"):
        return []

    all_matches = []
    for name in model_names:
        # Try pg_trgm similarity first
        rows = _query(
            """
            SELECT *, similarity(model_name, %s) AS sim_score
            FROM hardware.miner_models
            WHERE similarity(model_name, %s) > 0.25
            ORDER BY sim_score DESC
            LIMIT 3
            """,
            (name, name),
        )
        if rows:
            all_matches.extend(rows)
            logger.info("Fuzzy match for '%s': %d results (best sim=%.2f)",
                        name, len(rows), rows[0].get("sim_score", 0))
        else:
            # Fallback to ILIKE
            pattern = f"%{name}%"
            rows = _query(
                "SELECT *, 0.5 AS sim_score FROM hardware.miner_models WHERE model_name ILIKE %s LIMIT 3",
                (pattern,),
            )
            if rows:
                all_matches.extend(rows)
                logger.info("ILIKE match for '%s': %d results", name, len(rows))
            else:
                logger.warning("No match for model '%s'", name)

    # Deduplicate by model id
    seen = set()
    unique = []
    for row in all_matches:
        mid = row.get("id") or row.get("model_id") or id(row)
        if mid not in seen:
            seen.add(mid)
            unique.append(row)
    return unique


# ---------------------------------------------------------------------------
# Bundle assembly
# ---------------------------------------------------------------------------
def _fetch_failure_patterns(model_ids: list[int], active_issues: list[str]) -> list[dict]:
    """Fetch failure patterns relevant to matched models and active issues."""
    results = []

    # Failure mode catalog
    # ops.failure_patterns — operational failure data
    if model_ids and _check_table_exists("ops.failure_patterns"):
        placeholders = ",".join(["%s"] * len(model_ids))
        rows = _query(
            f"SELECT * FROM ops.failure_patterns WHERE model_id IN ({placeholders}) LIMIT 50",
            tuple(model_ids),
        )
        results.extend(rows)

    # ops.failure_symptoms — symptom descriptions
    if _check_table_exists("ops.failure_symptoms") and active_issues:
        for issue in active_issues:
            rows = _query(
                "SELECT * FROM ops.failure_symptoms WHERE UPPER(symptom_name) ILIKE %s LIMIT 10",
                (f"%{issue}%",),
            )
            results.extend(rows)

    # ops.miner_error_codes — error code reference
    if _check_table_exists("ops.miner_error_codes") and active_issues:
        for issue in active_issues:
            rows = _query(
                "SELECT * FROM ops.miner_error_codes WHERE UPPER(error_code) ILIKE %s LIMIT 10",
                (f"%{issue}%",),
            )
            results.extend(rows)

    # hardware.model_known_issues — known hardware issues
    if model_ids and _check_table_exists("hardware.model_known_issues"):
        placeholders = ",".join(["%s"] * len(model_ids))
        rows = _query(
            f"SELECT * FROM hardware.model_known_issues WHERE model_id IN ({placeholders}) LIMIT 20",
            tuple(model_ids),
        )
        results.extend(rows)

    return results


def _fetch_firmware_data(model_ids: list[int], firmware_versions: list[str]) -> dict:
    """Fetch firmware versions, compatibility, and known bugs."""
    data: dict[str, list] = {"versions": [], "compatibility": [], "bugs": []}

    if model_ids and _check_table_exists("firmware.firmware_releases"):
        placeholders = ",".join(["%s"] * len(model_ids))
        data["versions"] = _query(
            f"SELECT * FROM firmware.firmware_releases WHERE model_id IN ({placeholders}) ORDER BY release_date DESC LIMIT 20",
            tuple(model_ids),
        )

    if model_ids and _check_table_exists("firmware.firmware_compatibility"):
        placeholders = ",".join(["%s"] * len(model_ids))
        data["compatibility"] = _query(
            f"SELECT * FROM firmware.firmware_compatibility WHERE model_id IN ({placeholders}) LIMIT 20",
            tuple(model_ids),
        )

    if _check_table_exists("firmware.firmware_bugs"):
        if firmware_versions:
            placeholders = ",".join(["%s"] * len(firmware_versions))
            data["bugs"] = _query(
                f"SELECT * FROM firmware.firmware_bugs WHERE firmware_version IN ({placeholders}) LIMIT 20",
                tuple(firmware_versions),
            )
        elif model_ids:
            placeholders = ",".join(["%s"] * len(model_ids))
            data["bugs"] = _query(
                f"SELECT * FROM firmware.firmware_bugs WHERE model_id IN ({placeholders}) LIMIT 20",
                tuple(model_ids),
            )

    return data


def _fetch_thresholds(model_ids: list[int]) -> dict:
    """Fetch operational thresholds and baselines."""
    data: dict[str, list] = {"thresholds": [], "baselines": [], "profiles": [], "env_matrix": []}

    if model_ids and _check_table_exists("ops.operational_thresholds"):
        placeholders = ",".join(["%s"] * len(model_ids))
        data["thresholds"] = _query(
            f"SELECT * FROM ops.operational_thresholds WHERE model_id IN ({placeholders}) LIMIT 20",
            tuple(model_ids),
        )

    if model_ids and _check_table_exists("ops.miner_baseline_reference"):
        placeholders = ",".join(["%s"] * len(model_ids))
        data["baselines"] = _query(
            f"SELECT * FROM ops.miner_baseline_reference WHERE model_id IN ({placeholders}) LIMIT 20",
            tuple(model_ids),
        )

    if model_ids and _check_table_exists("ops.operational_profiles"):
        placeholders = ",".join(["%s"] * len(model_ids))
        data["profiles"] = _query(
            f"SELECT * FROM ops.operational_profiles WHERE model_id IN ({placeholders}) LIMIT 10",
            tuple(model_ids),
        )

    if _check_table_exists("ops.environmental_correlations"):
        data["env_matrix"] = _query(
            "SELECT * FROM ops.environmental_correlations LIMIT 20",
        )

    return data


def _fetch_repair_data(model_ids: list[int]) -> dict:
    """Fetch repair procedures and parts references."""
    data: dict[str, list] = {"procedures": [], "parts_diagnostic": [], "parts_cross_ref": []}

    if model_ids and _check_table_exists("repair.repair_procedures"):
        placeholders = ",".join(["%s"] * len(model_ids))
        data["procedures"] = _query(
            f"SELECT * FROM repair.repair_procedures WHERE model_id IN ({placeholders}) LIMIT 20",
            tuple(model_ids),
        )

    if _check_table_exists("repair.diagnostic_tools"):
        data["diagnostic_tools"] = _query("SELECT * FROM repair.diagnostic_tools LIMIT 20")

    if _check_table_exists("repair.parts"):
        data["parts"] = _query("SELECT * FROM repair.parts LIMIT 30")

    return data


def _fetch_environmental_data() -> dict:
    """Fetch environmental/facility data."""
    data: dict[str, list] = {"safety_systems": [], "cooling_specs": []}

    if _check_table_exists("facility.cooling_solutions"):
        data["cooling_specs"] = _query("SELECT * FROM facility.cooling_solutions LIMIT 10")

    if _check_table_exists("facility.container_environment_reference"):
        data["safety_systems"] = _query("SELECT * FROM facility.container_environment_reference LIMIT 10")

    return data


def _fetch_chip_specs(chip_dies: list[str]) -> list[dict]:
    """Fetch chip specifications by die identifier."""
    if not chip_dies or not _check_table_exists("hardware.chips"):
        return []
    results = []
    for die in chip_dies:
        rows = _query(
            "SELECT * FROM hardware.chips WHERE chip_name ILIKE %s LIMIT 5",
            (f"%{die}%",),
        )
        results.extend(rows)
    return results


# ---------------------------------------------------------------------------
# Prompt text formatting
# ---------------------------------------------------------------------------
def _serialize_value(val: Any) -> str:
    """Safely serialize a value for prompt text."""
    if val is None:
        return "N/A"
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, (dict, list)):
        return json.dumps(val, default=str)
    return str(val)


def _format_prompt_text(bundle: dict[str, Any], request: ScanBundleRequest) -> str:
    """
    Format a context bundle into LLM-ready prompt text.
    Token budget: ~2300 tokens (~9200 chars). Priority-ranked sections.
    """
    sections: list[str] = []
    char_budget = 9200
    used = 0

    def _add_section(title: str, content: str, max_chars: int) -> None:
        nonlocal used
        remaining = char_budget - used
        allowed = min(max_chars, remaining)
        if allowed <= 0 or not content.strip():
            return
        text = f"\n### {title}\n{content[:allowed]}"
        sections.append(text)
        used += len(text)

    # 1. Active issue failure patterns (~800 tokens = ~3200 chars)
    failure_lines = []
    for fp in bundle.get("failure_patterns", [])[:15]:
        name = fp.get("failure_mode") or fp.get("name") or fp.get("signature_type") or "Unknown"
        desc = fp.get("description") or fp.get("root_cause") or ""
        severity = fp.get("severity") or fp.get("risk_level") or ""
        line = f"- **{name}**"
        if severity:
            line += f" [{severity}]"
        if desc:
            line += f": {_serialize_value(desc)}"
        failure_lines.append(line)
    if failure_lines:
        _add_section("Known Failure Patterns", "\n".join(failure_lines), 3200)

    # 2. Model specs + baselines (~400 tokens = ~1600 chars)
    model_lines = []
    for m in bundle.get("matched_models", [])[:5]:
        name = m.get("model_name") or m.get("name") or "Unknown"
        hashrate = m.get("hashrate_th") or m.get("hashrate") or "?"
        power = m.get("power_consumption_w") or m.get("power_w") or "?"
        chip = m.get("chip_name") or m.get("asic_chip") or "?"
        model_lines.append(f"- **{name}**: {hashrate} TH/s, {power}W, chip: {chip}")

    baseline_lines = []
    for b in bundle.get("thresholds", {}).get("baselines", [])[:5]:
        name = b.get("metric_name") or b.get("parameter") or "metric"
        expected = b.get("expected_value") or b.get("baseline_value") or "?"
        baseline_lines.append(f"- {name}: {expected}")

    spec_content = ""
    if model_lines:
        spec_content += "**Models:**\n" + "\n".join(model_lines) + "\n"
    if baseline_lines:
        spec_content += "**Baselines:**\n" + "\n".join(baseline_lines)
    if spec_content:
        _add_section("Model Specs & Baselines", spec_content, 1600)

    # 3. Firmware guidance (~200 tokens = ~800 chars)
    fw_data = bundle.get("firmware", {})
    fw_lines = []
    for v in fw_data.get("versions", [])[:5]:
        ver = v.get("version") or v.get("firmware_version") or "?"
        status = v.get("status") or v.get("stability_rating") or ""
        fw_lines.append(f"- v{ver} {f'({status})' if status else ''}")
    for bug in fw_data.get("bugs", [])[:3]:
        desc = bug.get("description") or bug.get("bug_description") or "bug"
        fw_lines.append(f"- BUG: {_serialize_value(desc)[:150]}")
    if fw_lines:
        _add_section("Firmware Intelligence", "\n".join(fw_lines), 800)

    # 4. Environmental context (~200 tokens = ~800 chars)
    env_data = bundle.get("environmental", {})
    env_lines = []
    for s in env_data.get("safety_systems", [])[:3]:
        name = s.get("system_name") or s.get("name") or "system"
        env_lines.append(f"- {name}")
    for c in env_data.get("cooling_specs", [])[:3]:
        name = c.get("cooling_type") or c.get("name") or "cooling"
        env_lines.append(f"- Cooling: {name}")
    threshold_data = bundle.get("thresholds", {})
    for t in threshold_data.get("env_matrix", [])[:3]:
        param = t.get("parameter") or t.get("metric") or "param"
        val = t.get("threshold_value") or t.get("max_value") or "?"
        env_lines.append(f"- {param}: {val}")
    if env_lines:
        _add_section("Environmental Context", "\n".join(env_lines), 800)

    # 5. Repair notes (~300 tokens = ~1200 chars)
    repair_data = bundle.get("repair", {})
    repair_lines = []
    for proc in repair_data.get("procedures", [])[:5]:
        title = proc.get("procedure_name") or proc.get("title") or "Procedure"
        steps = proc.get("steps") or proc.get("procedure_steps") or ""
        line = f"- **{title}**"
        if steps:
            line += f": {_serialize_value(steps)[:200]}"
        repair_lines.append(line)
    if repair_lines:
        _add_section("Repair Procedures", "\n".join(repair_lines), 1200)

    # 6. Chip specifications (remaining budget)
    chip_lines = []
    for c in bundle.get("chip_specs", [])[:5]:
        name = c.get("chip_name") or c.get("name") or "chip"
        process = c.get("process_node") or c.get("process_nm") or "?"
        chip_lines.append(f"- {name}: {process}nm process")
    if chip_lines:
        _add_section("Chip Specifications", "\n".join(chip_lines), 800)

    if not sections:
        return "No catalog intelligence available for the current scan context."

    header = "## Intelligence Catalog Context\nThe following knowledge is from the Mining Intelligence Catalog and should inform your analysis:\n"
    return header + "".join(sections)


def _build_cache_key(request: ScanBundleRequest) -> str:
    """Generate a deterministic cache key for a scan bundle request."""
    payload = json.dumps({
        "models": sorted(request.miner_models),
        "issues": sorted(request.active_issues),
        "chips": sorted(request.chip_dies),
        "fw": sorted(request.firmware_versions),
        "sections": sorted(request.include_sections),
    }, sort_keys=True)
    return f"sha256:{hashlib.sha256(payload.encode()).hexdigest()[:16]}"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/v1/health")
@limiter.limit(RATE_LIMIT_HEALTH)
async def health(request: Request):
    """Public health check — minimal information for unauthenticated callers.

    S-5 hardening (2026-04-29): the previous version of this endpoint returned
    `total_tables` and a per-schema row-count breakdown. That leaked the
    catalog's schema layout to anyone who could reach the port (which, with
    S-3 fixed, is loopback-by-default — but defense in depth still matters).
    The verbose payload is now only available on `/api/v1/health/detail`,
    which requires a valid bearer token. The unauthenticated `/health` keeps
    a tiny, opaque payload suitable for load-balancer / liveness probes.
    """
    db_ok = False
    try:
        rows = _query("SELECT 1 AS ok")
        if rows:
            db_ok = True
    except Exception as exc:
        logger.error("Health check DB query failed: %s", exc)

    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/health/detail")
@limiter.limit(RATE_LIMIT_HEALTH)
async def health_detail(request: Request, _auth: None = Depends(verify_token)):
    """Authenticated, verbose health — returns table counts per schema.

    Same payload the old unauthenticated `/health` used to return. Useful for
    operators and dashboards that need to confirm the seed-data load worked.
    Requires the catalog API key (same Bearer token as scan-bundle / model
    lookup).
    """
    db_ok = False
    db_tables = 0
    schema_rows = []
    try:
        rows = _query(
            """SELECT count(*) AS cnt FROM information_schema.tables
               WHERE table_schema IN ('public','hardware','firmware','ops','market',
                                      'repair','pool','facility','regulatory','knowledge','seed')""")
        schema_rows = _query(
            """SELECT table_schema, count(*) AS cnt FROM information_schema.tables
               WHERE table_schema IN ('hardware','firmware','ops','market',
                                      'repair','pool','facility','regulatory','knowledge','seed')
               GROUP BY table_schema ORDER BY table_schema""")
        if rows:
            db_ok = True
            db_tables = rows[0].get("cnt", 0)
    except Exception as exc:
        logger.error("Health-detail DB query failed: %s", exc)

    schema_breakdown = {r["table_schema"]: r["cnt"] for r in schema_rows}
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "total_tables": db_tables,
        "schemas": schema_breakdown,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/v1/context/scan-bundle", response_model=ScanBundleResponse)
@limiter.limit(RATE_LIMIT_SCAN_BUNDLE)
async def scan_bundle(
    request: Request,
    body: ScanBundleRequest,
    _auth: None = Depends(verify_token),
):
    """
    Main endpoint — hot path. Given miner models and active issues from a scan,
    query the Intelligence Catalog and return a knowledge bundle with pre-formatted
    prompt text for LLM injection.

    Target: <200ms p95.
    """
    start = time.monotonic()
    cache_key = _build_cache_key(body)

    # Check in-memory cache
    if cache_key in bundle_cache:
        logger.info("Cache HIT for %s", cache_key)
        return bundle_cache[cache_key]

    logger.info("Cache MISS — building bundle for models=%s issues=%s",
                body.miner_models, body.active_issues)

    sources: list[str] = []
    bundle: dict[str, Any] = {}

    # Fuzzy-match miner models
    matched_models = _fuzzy_match_models(body.miner_models)
    bundle["matched_models"] = matched_models
    model_ids = [m.get("id") or m.get("model_id") for m in matched_models if m.get("id") or m.get("model_id")]
    if matched_models:
        sources.append("hardware.miner_models")

    # Chip specs
    if body.chip_dies:
        bundle["chip_specs"] = _fetch_chip_specs(body.chip_dies)
        if bundle["chip_specs"]:
            sources.append("hardware.chips")

    # Sections
    sections = set(body.include_sections)

    if "failure_patterns" in sections:
        bundle["failure_patterns"] = _fetch_failure_patterns(model_ids, body.active_issues)
        if bundle["failure_patterns"]:
            sources.extend(["ops.failure_patterns", "ops.failure_symptoms",
                            "ops.miner_error_codes", "hardware.model_known_issues"])

    if "firmware" in sections:
        bundle["firmware"] = _fetch_firmware_data(model_ids, body.firmware_versions)
        if any(bundle["firmware"].values()):
            sources.extend(["firmware.firmware_releases", "firmware.firmware_compatibility",
                            "firmware.firmware_bugs"])

    if "thresholds" in sections or "baselines" in sections:
        bundle["thresholds"] = _fetch_thresholds(model_ids)
        if any(bundle["thresholds"].values()):
            sources.extend(["ops.operational_thresholds", "ops.miner_baseline_reference",
                            "ops.operational_profiles", "ops.environmental_correlations"])

    if "repair" in sections:
        bundle["repair"] = _fetch_repair_data(model_ids)
        if any(bundle["repair"].values()):
            sources.extend(["repair.repair_procedures", "repair.diagnostic_tools", "repair.parts"])

    if "env_factors" in sections:
        bundle["environmental"] = _fetch_environmental_data()
        if any(bundle["environmental"].values()):
            sources.extend(["facility.cooling_solutions", "facility.container_environment_reference"])

    # Deduplicate sources
    sources = list(dict.fromkeys(sources))

    # Generate prompt text
    prompt_text = _format_prompt_text(bundle, body)

    # Sanitize bundle for JSON (remove sim_score floats, convert datetimes)
    def _sanitize(obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize(i) for i in obj]
        if isinstance(obj, float) and (obj != obj):  # NaN check
            return None
        return obj

    bundle = _sanitize(bundle)

    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info("Bundle built in %.1fms — %d sources, %d chars prompt",
                elapsed_ms, len(sources), len(prompt_text))

    response = ScanBundleResponse(
        context_bundle=bundle,
        prompt_text=prompt_text,
        cache_key=cache_key,
        generated_at=datetime.now(timezone.utc).isoformat(),
        sources=sources,
    )

    # Cache the response
    bundle_cache[cache_key] = response

    return response


@app.get("/api/v1/knowledge/miner/{model_slug}")
@limiter.limit(RATE_LIMIT_MINER)
async def get_miner_knowledge(
    request: Request,
    model_slug: str,
    include: str = Query(
        default="specs,firmware,failures,repair,thresholds",
        description="Comma-separated sections: specs,firmware,failures,repair,thresholds",
        max_length=256,
    ),
    _auth: None = Depends(verify_token),
):
    """
    Single model lookup. Returns specs, known issues, recommended firmware,
    repair notes, and baselines for one miner model.
    """
    cache_key = f"miner:{model_slug}:{include}"
    if cache_key in model_cache:
        logger.info("Model cache HIT for %s", model_slug)
        return model_cache[cache_key]

    logger.info("Model cache MISS — looking up '%s'", model_slug)

    # Convert slug to search term (e.g., "antminer-s19j-pro" -> "antminer s19j pro")
    search_term = model_slug.replace("-", " ").replace("_", " ")
    matched = _fuzzy_match_models([search_term])

    if not matched:
        raise HTTPException(status_code=404, detail=f"No model matching '{model_slug}' found in catalog")

    model = matched[0]
    model_id = model.get("id") or model.get("model_id")
    model_ids = [model_id] if model_id else []

    include_set = set(s.strip() for s in include.split(","))
    result: dict[str, Any] = {"model": model}

    if "specs" in include_set:
        if _check_table_exists("hardware.chips"):
            chip_name = model.get("chip_name") or model.get("asic_chip") or ""
            if chip_name:
                result["chip_specs"] = _query(
                    "SELECT * FROM hardware.chips WHERE chip_name ILIKE %s LIMIT 5",
                    (f"%{chip_name}%",),
                )
        if _check_table_exists("hardware.psu_models") and model_ids:
            result["psu_specs"] = _query(
                "SELECT * FROM hardware.psu_models WHERE model_id = %s LIMIT 5",
                (model_ids[0],),
            )

    if "firmware" in include_set and model_ids:
        result["firmware"] = _fetch_firmware_data(model_ids, [])

    if "failures" in include_set and model_ids:
        result["failures"] = _fetch_failure_patterns(model_ids, [])

    if "repair" in include_set and model_ids:
        result["repair"] = _fetch_repair_data(model_ids)

    if "thresholds" in include_set and model_ids:
        result["thresholds"] = _fetch_thresholds(model_ids)

    # Sanitize datetimes
    def _sanitize(obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize(i) for i in obj]
        return obj

    result = _sanitize(result)

    model_cache[cache_key] = result
    logger.info("Model lookup for '%s' complete", model_slug)
    return result


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Catch-all error handler — never crash, never leak.

    S-10 hardening (2026-04-29): the previous version returned `str(exc)` to
    the client. That leaks internal exception messages (which often contain
    SQL fragments, file paths, environment variable names, or stack-trace
    hints — anything an attacker can use to map the system). The full
    exception is still logged server-side at ERROR level with `exc_info=True`
    so operators retain full debuggability; the client only sees a generic
    failure message.
    """
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "code": "INTERNAL_ERROR"},
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Catalog API on %s:%d", API_HOST, API_PORT)
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="info")
