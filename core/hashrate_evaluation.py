"""
hashrate_evaluation.py — Three-Tier Hashrate Evaluation System
===============================================================
Determines the correct rated hashrate for any miner regardless of firmware.

Tier 1 — BiXBiT firmware:
    Parse currentProfile string from AMS miner_config.
    Format: "{TH/s} TH/s - ~{W} W"  (strip ~ before parsing)
    Most accurate — live profile data.

Tier 2 — Stock/other firmware, known model:
    Look up default_rated_ths in miner_specs.json.
    Uses published manufacturer specs.

Tier 3 — Unknown model or model not in specs:
    Use 3-5 day running average baseline from miner_baselines table.
    During learning window: no hashrate flagging, only hard faults.
    After baseline locked: flag if below baseline × (1 - tolerance).
"""

import json
import re
import psycopg2
from psycopg2.extras import DictCursor
import logging
import statistics
from datetime import datetime, timezone, timedelta
from pathlib import Path

from core.db_targets import operational_target

_ROOT = Path(__file__).resolve().parent.parent
from typing import Optional, Tuple

logger = logging.getLogger("mining_guardian")


def _coerce_to_datetime(value, *, default=None):
    """Best-effort coercion of a heterogeneous baseline-state value to a
    timezone-aware UTC datetime.

    Why this exists (P-021-runtime-fix, 2026-05-08):
        `BaselineManager` was originally written against a SQLite schema
        that stored timestamps as ISO strings (see this file's docstring
        line ~333: "learning_start TEXT — ISO timestamp"). The
        2026-04-23 Postgres migration (`migrations/001_initial_schema.sql:151`)
        declared `learning_start TIMESTAMP WITH TIME ZONE NOT NULL`, and
        psycopg2 returns native `datetime` objects for TIMESTAMPTZ
        columns. `_ensure_table` here still says `TEXT NOT NULL` but it
        is `CREATE TABLE IF NOT EXISTS` — on a real install the migration
        runs first, so the live column is `timestamptz` and `get_state`
        returns `state["learning_start"]` as a `datetime`. The legacy
        `datetime.fromisoformat(state["learning_start"])` then crashes:
            TypeError: fromisoformat: argument must be str
        Observed live on the 2026-05-08 P-021-fix install: scanner exit
        1 in `_analyze_miner` after AMS discovery, every miner blocked.

    Acceptable input types and behaviour:
        - `datetime` (naive) → assumed UTC; tzinfo attached.
        - `datetime` (aware) → returned as-is.
        - ISO 8601 string (with or without trailing 'Z') → parsed; UTC if no tz.
        - empty string / None / junk type → `default` is returned (caller
          decides whether `None` means "reset learning" or just "skip
          this sample").

    Returns the coerced datetime, or `default` if the input is unusable.
    Never raises — the scanner can't afford to crash on a single
    legacy-shaped row.
    """
    from datetime import date as _date_cls
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, _date_cls):
        # Plain date (no time) — promote to midnight UTC.
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return default
        # `datetime.fromisoformat` on Python 3.11+ accepts trailing 'Z',
        # but be defensive for 3.10. Replace the literal 'Z' with '+00:00'.
        if s.endswith("Z") and "+" not in s:
            s = s[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(s)
        except ValueError:
            return default
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    return default


# ---------------------------------------------------------------------------
# MinerSpecsLoader — Tier 2 lookup table
# ---------------------------------------------------------------------------

class _PgConnWrapper:
    """Thin wrapper over psycopg2 Connection with SQLite-style conn.execute() shortcut.

    Same wrapper pattern used across Phase 7 files. Supports with-statement,
    commit/rollback. Wraps a per-connection DictCursor so rows behave
    like dicts (parallel to SQLite Row factory).
    """

    def __init__(self, dsn: str):
        self._conn = psycopg2.connect(dsn, cursor_factory=DictCursor)

    def execute(self, sql, params=()):
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()
        return False


class MinerSpecsLoader:
    """Loads miner_specs.json and resolves rated TH/s for known models."""

    def __init__(self, specs_path: str = str(_ROOT / "miner_specs.json")):
        self._specs = {}
        self._baseline_config = {}
        path = Path(specs_path)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._specs = data.get("models", {})
            self._baseline_config = data.get("baseline_config", {})
            logger.info("MinerSpecsLoader: loaded %d model specs", len(self._specs))
        else:
            logger.warning("MinerSpecsLoader: %s not found — Tier 2 disabled", specs_path)

    def get_rated_ths(self, ams_model_code: str) -> Optional[float]:
        """
        Return default_rated_ths for a given AMS model code.
        Returns None if model not found (triggers Tier 3).
        """
        entry = self._specs.get(ams_model_code)
        if entry:
            return entry.get("default_rated_ths")
        return None

    def get_rated_watts(self, ams_model_code: str) -> Optional[float]:
        """Return default_rated_watts for power evaluation."""
        entry = self._specs.get(ams_model_code)
        if entry:
            return entry.get("default_rated_watts")
        return None

    def get_boards(self, ams_model_code: str, fallback: int = 3) -> int:
        """Return the expected hashboard count for a model.

        Uses the 'boards' field from miner_specs.json when available.
        Falls back to the provided default (3) for unknown models.
        AH3880 (Auradine) is 2 boards; all standard Antminer/BiXBiT are 3.
        """
        entry = self._specs.get(ams_model_code)
        if entry:
            return int(entry.get("boards", fallback))
        return fallback

    def get_profile_map(self, ams_model_code: str) -> dict:
        """Return named profile → TH/s map for mode-based miners (e.g. AH3880)."""
        entry = self._specs.get(ams_model_code)
        if entry:
            return entry.get("profile_map", {})
        return {}

    @property
    def learning_window_hours(self) -> int:
        return self._baseline_config.get("learning_window_hours", 72)

    @property
    def minimum_samples(self) -> int:
        return self._baseline_config.get("minimum_samples", 36)

    @property
    def baseline_tolerance_pct(self) -> float:
        return self._baseline_config.get("baseline_tolerance_low_pct", 10)

    @property
    def notify_on_lock(self) -> bool:
        return self._baseline_config.get("slack_notification_on_lock", True)


# ---------------------------------------------------------------------------
# Profile parsers
# ---------------------------------------------------------------------------

def parse_bixbit_profile(profile_str: str) -> Optional[float]:
    """
    Parse BiXBiT/Bitmain profile string to rated TH/s.
    Handles formats:
      "144 TH/s - ~4913 W"   → 144.0
      "440 TH/s - ~5396 W"   → 440.0
      "56 TH/s - ~1429 W"    → 56.0
    Returns None if string doesn't match expected format.
    """
    if not profile_str:
        return None
    # Match leading number before " TH/s"
    match = re.match(r"^\s*(\d+(%s:\.\d+)%s)\s*TH/s", profile_str, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def resolve_auradine_mode(mode_str: str, profile_map: dict) -> Optional[float]:
    """
    Resolve Auradine mode name to TH/s via profile_map.
    e.g. "turbo" → 600, "normal" → 500
    Returns None if mode unknown or maps to None.
    """
    if not mode_str or not profile_map:
        return None
    return profile_map.get(mode_str.lower())


# ---------------------------------------------------------------------------
# Tier resolver — combines all three tiers
# ---------------------------------------------------------------------------

class HashrateTierResolver:
    """
    Determines the correct rated TH/s for a miner and which tier was used.

    Returns:
        rated_ths  — the TH/s target to compare actual against (or None)
        tier       — "1_bixbit_profile", "2_spec_lookup", "3_baseline",
                     "3_learning", or "unknown"
        note       — human-readable explanation
    """

    def __init__(self, specs_loader: MinerSpecsLoader, baseline_mgr: "BaselineManager"):
        self.specs   = specs_loader
        self.baseline = baseline_mgr

    def resolve(self, miner: dict) -> Tuple[Optional[float], str, str]:
        """
        Returns (rated_ths, tier, note).
        rated_ths is None if in learning window or truly unknown.
        """
        miner_id   = str(miner.get("id", ""))
        ip         = miner.get("ip", "")
        model_code = miner.get("model", "")
        firmware   = miner.get("firmwareManufacturer", "") or ""
        profile    = miner.get("currentProfile", "") or ""

        # ── TIER 1: BiXBiT firmware with active profile ──────────────────
        if firmware.upper() == "BIXBIT" and profile:
            rated = parse_bixbit_profile(profile)
            if rated:
                return (
                    rated,
                    "1_bixbit_profile",
                    f"BiXBiT firmware — active profile '{profile}' → {rated} TH/s"
                )

        # ── TIER 1b: Empty firmware but parseable BiXBiT-format profile ──
        # Offline miners lose their firmwareManufacturer field in AMS even
        # when they run BiXBiT firmware — profile string is the signal.
        if not firmware and profile:
            rated = parse_bixbit_profile(profile)
            if rated:
                return (
                    rated,
                    "1_bixbit_profile_inferred",
                    f"BiXBiT firmware inferred from profile '{profile}' → {rated} TH/s"
                )

        # ── TIER 1d: BiXBiT firmware but empty profile — check last known ──
        # AMS sometimes returns empty currentProfile for miners that ARE on
        # BiXBiT firmware. Check the DB for the last non-empty profile.
        if firmware.upper() == "BIXBIT" and not profile:
            try:
                # W14a (2026-05-12): was reading env vars directly;
                # delegate to core.db_targets.operational_target() so this
                # query stays on the right Postgres instance after W14.
                # The lookup hits `miner_readings`, an operational table.
                conn = psycopg2.connect(
                    **operational_target().connect_kwargs(),
                    cursor_factory=DictCursor,
                )
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT current_profile FROM miner_readings "
                        "WHERE miner_id=%s AND current_profile IS NOT NULL AND current_profile != '' "
                        "ORDER BY id DESC LIMIT 1",
                        (miner_id,)
                    )
                    row = cur.fetchone()
                conn.close()
                if row and row.get("current_profile"):
                    rated = parse_bixbit_profile(row["current_profile"])
                    if rated:
                        return (
                            rated,
                            "1_bixbit_profile_cached",
                            f"BiXBiT firmware — last known profile '{row[0]}' → {rated} TH/s"
                        )
            except Exception:
                pass

        # ── TIER 1c: Auradine mode-based ─────────────────────────────────
        if firmware.upper() == "AURADINE":
            pmap = self.specs.get_profile_map(model_code)
            if pmap and profile:
                rated = resolve_auradine_mode(profile, pmap)
                if rated:
                    return (
                        rated,
                        "1_auradine_mode",
                        f"Auradine firmware — mode '{profile}' → {rated} TH/s"
                    )

        # ── TIER 2: Known model spec lookup ──────────────────────────────
        rated = self.specs.get_rated_ths(model_code)
        if rated:
            return (
                rated,
                "2_spec_lookup",
                f"Stock spec lookup — model '{model_code}' → {rated} TH/s"
            )

        # ── TIER 3: Running average baseline ─────────────────────────────
        state = self.baseline.get_state(miner_id)

        if state is None:
            self.baseline.start_learning(miner_id, ip, model_code, firmware)
            return (
                None,
                "3_learning",
                f"New miner — baseline learning started (0/{self.specs.minimum_samples} samples)"
            )

        if not state["learning_complete"]:
            samples    = state["samples_collected"]
            hours      = state["hours_observed"]
            needed_hrs = self.specs.learning_window_hours
            needed_smp = self.specs.minimum_samples
            return (
                None,
                "3_learning",
                f"Baseline learning: {samples}/{needed_smp} samples, "
                f"{hours:.1f}/{needed_hrs}h elapsed"
            )

        baseline_ths = state["baseline_hashrate_ths"]
        if baseline_ths:
            return (
                baseline_ths,
                "3_baseline",
                f"Learned baseline — {baseline_ths:.1f} TH/s "
                f"(locked {state['locked_at'][:10]})"
            )

        return (None, "unknown", "No rated TH/s available — cannot evaluate hashrate")


# ---------------------------------------------------------------------------
# BaselineManager — Tier 3 running average baseline (DB-backed)
# ---------------------------------------------------------------------------

class BaselineManager:
    """
    Manages per-miner hashrate baselines for miners without known specs.

    DB table: miner_baselines
      miner_id            TEXT PRIMARY KEY
      ip                  TEXT
      model               TEXT
      firmware            TEXT
      learning_start      TEXT    -- ISO timestamp when first seen
      learning_complete   INTEGER -- 0/1 boolean
      baseline_hashrate_ths REAL  -- locked average once complete
      baseline_power_kw   REAL
      samples_collected   INTEGER
      hours_observed      REAL
      locked_at           TEXT    -- when baseline was finalized
      last_updated        TEXT
    """

    def __init__(self, db_path: Optional[str] = None,
                 learning_window_hours: int = 72,
                 minimum_samples: int = 36,
                 tolerance_pct: float = 10.0,
                 notify_callback=None):
        """Initialize BaselineManager.

        db_path is retained for API compatibility but now holds a Postgres DSN
        (not a file path). External callers that read self.db_path (like
        mining_guardian.py line 100) get the DSN string. If caller passes a
        legacy path like "guardian.db", we ignore it and build DSN from env.
        """
        # W14a (2026-05-12): was building DSN by reading env vars directly
        # in a nested _build_dsn() helper. Delegate to
        # core.db_targets.operational_target() so callers stay on the right
        # Postgres instance after W14 splits catalog onto port 5433. The
        # BaselineManager only touches `miner_baselines` and `miner_readings`,
        # both operational tables.
        if db_path is None or db_path.endswith(".db") or db_path.startswith("/"):
            self.db_path = operational_target().dsn()
        else:
            self.db_path = db_path

        self.learning_window_hrs = learning_window_hours
        self.minimum_samples     = minimum_samples
        self.tolerance_pct       = tolerance_pct
        self.notify_callback     = notify_callback
        self._ensure_table()

    def _connect(self) -> "_PgConnWrapper":
        """Return a psycopg2-backed connection wrapper with SQLite-style .execute() shortcut."""
        return _PgConnWrapper(self.db_path)

    def _ensure_table(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS miner_baselines (
                    miner_id              TEXT PRIMARY KEY,
                    ip                    TEXT,
                    model                 TEXT,
                    firmware              TEXT,
                    learning_start        TEXT NOT NULL,
                    learning_complete     INTEGER DEFAULT 0,
                    baseline_hashrate_ths REAL,
                    baseline_power_kw     REAL,
                    samples_collected     INTEGER DEFAULT 0,
                    hours_observed        REAL DEFAULT 0,
                    locked_at             TEXT,
                    last_updated          TEXT
                )
            """)
            conn.commit()

    def get_state(self, miner_id: str) -> Optional[dict]:
        """Return baseline state dict or None if miner never seen."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM miner_baselines WHERE miner_id = %s", (miner_id,)
            ).fetchone()
        if row:
            return dict(row)
        return None

    def start_learning(self, miner_id: str, ip: str,
                       model: str, firmware: str) -> None:
        """Register a new miner for baseline learning."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO miner_baselines
                    (miner_id, ip, model, firmware, learning_start,
                     learning_complete, samples_collected, last_updated)
                VALUES (%s, %s, %s, %s, %s, 0, 0, %s)
                ON CONFLICT (miner_id) DO NOTHING
            """, (miner_id, ip, model, firmware, now, now))
            conn.commit()
        logger.info("BaselineManager: started learning for miner %s (%s)", miner_id, model)

    def record_sample(self, miner_id: str, hashrate_ths: float,
                      power_kw: Optional[float] = None) -> bool:
        """
        Record one scan's hashrate reading for this miner.
        Returns True if the baseline just locked on this sample.
        Only records if miner is online and hashrate > 0.
        """
        if hashrate_ths <= 0:
            return False

        state = self.get_state(miner_id)
        if state is None or state["learning_complete"]:
            return False

        now      = datetime.now(timezone.utc)
        # P-021-runtime-fix (2026-05-08): coerce learning_start through
        # `_coerce_to_datetime`. The schema disagrees with itself —
        # `_ensure_table` declares TEXT but the migration creates
        # TIMESTAMPTZ, so psycopg2 returns datetime, which crashes the
        # legacy `datetime.fromisoformat()` path. The helper accepts
        # datetime, ISO string, date, or None and returns a UTC-aware
        # datetime (or `default=None` for junk).
        start = _coerce_to_datetime(state.get("learning_start"))
        if start is None:
            # Legacy/corrupted state row — surface in the log and skip
            # this sample. The next call to `start_learning` will re-
            # initialize the row; refusing here is safer than silently
            # mis-reading the learning window or crashing the scanner.
            logger.warning(
                "BaselineManager: miner %s has invalid/missing learning_start "
                "(%r) — skipping sample. Will retry next scan.",
                miner_id, state.get("learning_start"),
            )
            return False
        elapsed_hrs  = (now - start).total_seconds() / 3600
        new_samples  = state["samples_collected"] + 1

        with self._connect() as conn:
            conn.execute("""
                UPDATE miner_baselines
                SET samples_collected = %s,
                    hours_observed    = %s,
                    last_updated      = %s
                WHERE miner_id = %s
            """, (new_samples, elapsed_hrs, now.isoformat(), miner_id))
            conn.commit()

        # Check if window is complete
        window_done   = elapsed_hrs >= self.learning_window_hrs
        samples_done  = new_samples >= self.minimum_samples

        if window_done and samples_done:
            self._lock_baseline(miner_id, now)
            return True
        return False

    def _lock_baseline(self, miner_id: str, now: datetime) -> None:
        """
        Calculate and lock the baseline from historical scan data.
        Uses average hashrate from miner_readings over the learning window.
        """
        state = self.get_state(miner_id)
        if not state:
            return

        # P-021-runtime-fix (2026-05-08): coerce learning_start the
        # same way record_sample does. psycopg2 may return a datetime
        # (TIMESTAMPTZ column) or a string (legacy SQLite-shaped TEXT
        # column on a freshly _ensure_table-only install). Both work
        # as a SQL bound, but normalising here keeps the value type
        # predictable for any future caller and matches record_sample's
        # invariant.
        start = _coerce_to_datetime(state.get("learning_start"))
        if start is None:
            logger.warning(
                "BaselineManager: miner %s has invalid/missing learning_start "
                "(%r) — cannot lock baseline. Aborting lock.",
                miner_id, state.get("learning_start"),
            )
            return

        with self._connect() as conn:
            # Pull all readings during the learning window
            rows = conn.execute("""
                SELECT hashrate, pdu_power
                FROM miner_readings
                WHERE miner_id = %s
                  AND scanned_at >= %s
                  AND hashrate > 0
                  AND status = 'online'
                ORDER BY scanned_at
            """, (miner_id, start)).fetchall()

        if not rows:
            logger.warning("BaselineManager: no valid readings for %s — cannot lock", miner_id)
            return

        # Calculate median — use statistics.median() which correctly averages
        # the two middle values for even-length lists (integer division biases low)
        hashrates = sorted(r["hashrate"] for r in rows)
        # Convert from GH/s (AMS units) to TH/s
        median_ths = statistics.median(hashrates) / 1_000

        power_readings = [r["pdu_power"] for r in rows if r["pdu_power"] and r["pdu_power"] > 0]
        avg_power_kw   = (sum(power_readings) / len(power_readings) / 1000) if power_readings else None

        with self._connect() as conn:
            conn.execute("""
                UPDATE miner_baselines
                SET learning_complete     = 1,
                    baseline_hashrate_ths = %s,
                    baseline_power_kw     = %s,
                    locked_at             = %s,
                    last_updated          = %s
                WHERE miner_id = %s
            """, (round(median_ths, 2), avg_power_kw, now.isoformat(),
                  now.isoformat(), miner_id))
            conn.commit()

        logger.info(
            "BaselineManager: LOCKED baseline for %s — %.1f TH/s "
            "(from %d samples)", miner_id, median_ths, len(rows)
        )

        # Notify via callback if provided
        if self.notify_callback:
            try:
                self.notify_callback(
                    miner_id=miner_id,
                    model=state["model"],
                    ip=state["ip"],
                    baseline_ths=round(median_ths, 2),
                    samples=len(rows),
                )
            except Exception as e:
                logger.warning("BaselineManager: notify_callback failed: %s", e)

    def get_threshold(self, miner_id: str) -> Optional[float]:
        """
        Return the low threshold TH/s for this miner (baseline × tolerance).
        Returns None if baseline not locked yet.
        """
        state = self.get_state(miner_id)
        if state and state["learning_complete"] and state["baseline_hashrate_ths"]:
            return state["baseline_hashrate_ths"] * (1 - self.tolerance_pct / 100)
        return None

    def get_all_learning(self) -> list:
        """Return list of miners still in learning window."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM miner_baselines WHERE learning_complete = 0
            """).fetchall()
        return [dict(r) for r in rows]

    def get_all_locked(self) -> list:
        """Return list of miners with locked baselines."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM miner_baselines WHERE learning_complete = 1
            """).fetchall()
        return [dict(r) for r in rows]
