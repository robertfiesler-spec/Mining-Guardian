"""
fingerprint_builder.py
Mining Guardian — Feature 4: Miner Fingerprinting

Builds a per-miner behavioral profile from accumulated outcome history,
scan data, and restart patterns. Every miner has a personality — some
run hot, some are unstable, some are rock solid.

Fingerprints are stored in knowledge.json under miner_fingerprints and
feed directly into confidence scoring to make it per-miner instead of
fleet-wide.

Runs:
  - After weekly_train.py (automatically)
  - On demand via: python3 -m ai.fingerprint_builder

Fingerprint schema per miner:
  {
    "miner_id": "53499",
    "ip": "192.168.188.125",
    "model": "Antminer S19JPro",
    "restart_success_rate": 0.85,
    "avg_recovery_time_scans": 1.2,
    "flag_frequency_per_week": 0.4,
    "hashrate_stability_score": 92.3,
    "avg_hashrate_pct": 187.4,
    "known_issues": [],
    "confidence_modifier": 0.15,
    "total_restarts": 5,
    "total_scans_flagged": 3,
    "last_updated": "2026-04-05T16:00:00"
  }
"""

import sys
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT / "core"), str(_ROOT / "ai")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logger = logging.getLogger("fingerprint_builder")

DB_PATH        = str(_ROOT / "guardian.db")
KNOWLEDGE_PATH = str(_ROOT / "knowledge.json")

# How far back to look when building fingerprints
LOOKBACK_DAYS  = 30
# Minimum restarts needed before we trust the success rate
MIN_RESTARTS_FOR_RATE = 2


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def build_all_fingerprints() -> dict:
    """
    Build fingerprints for every miner that has scan history.
    Returns summary of what was built.
    """
    conn = get_db()

    # Get all unique miners from miner_readings
    miners = conn.execute("""
        SELECT DISTINCT miner_id, ip, model
        FROM miner_readings
        WHERE miner_id IS NOT NULL
        ORDER BY ip
    """).fetchall()

    conn.close()

    if not miners:
        logger.warning("No miners found in miner_readings")
        return {"built": 0, "miners": []}

    # Load existing knowledge
    knowledge = _load_knowledge()
    fingerprints = knowledge.setdefault("miner_fingerprints", {})

    built = []
    for m in miners:
        try:
            fp = _build_fingerprint(m["miner_id"], m["ip"], m["model"])
            fingerprints[m["miner_id"]] = fp
            built.append(m["ip"])
        except Exception as e:
            logger.warning("Failed to build fingerprint for %s: %s", m["ip"], e)

    knowledge["miner_fingerprints"] = fingerprints
    knowledge["fingerprints_updated_at"] = datetime.now().isoformat()
    _save_knowledge(knowledge)

    logger.info("Built %d miner fingerprints", len(built))
    return {"built": len(built), "miners": built}


def _build_fingerprint(miner_id: str, ip: str, model: str) -> Dict[str, Any]:
    """Build a single miner fingerprint from all available data."""
    conn = get_db()
    cutoff = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).isoformat()

    # ── Restart history and outcomes ─────────────────────────────────────────
    restarts = conn.execute("""
        SELECT outcome, recovery_time_scans, restart_type, restarted_at
        FROM miner_restarts
        WHERE miner_id = ? AND restarted_at >= ?
        ORDER BY restarted_at DESC
    """, (miner_id, cutoff)).fetchall()

    total_restarts  = len(restarts)
    successes       = sum(1 for r in restarts if r["outcome"] == "SUCCESS")
    failures        = sum(1 for r in restarts if r["outcome"] == "FAILURE")
    partials        = sum(1 for r in restarts if r["outcome"] == "PARTIAL")
    pending         = sum(1 for r in restarts if r["outcome"] in ("PENDING", None))

    completed = successes + failures + partials
    if completed >= MIN_RESTARTS_FOR_RATE:
        success_rate = round((successes + partials * 0.5) / completed, 3)
    else:
        success_rate = None  # not enough data

    recovery_times = [r["recovery_time_scans"] for r in restarts
                      if r["recovery_time_scans"] is not None]
    avg_recovery = round(sum(recovery_times) / len(recovery_times), 1) \
        if recovery_times else None

    # ── Hashrate behavior ────────────────────────────────────────────────────
    hr_rows = conn.execute("""
        SELECT hashrate_pct FROM miner_readings
        WHERE miner_id = ? AND status = 'online'
          AND hashrate_pct IS NOT NULL AND hashrate_pct > 0
          AND scan_id IN (
              SELECT id FROM scans WHERE scanned_at >= ? ORDER BY id DESC LIMIT 100
          )
        ORDER BY id DESC LIMIT 50
    """, (miner_id, cutoff)).fetchall()

    hashrates = [float(r["hashrate_pct"]) for r in hr_rows]
    avg_hr    = round(sum(hashrates) / len(hashrates), 1) if hashrates else None

    if len(hashrates) >= 3:
        mean    = sum(hashrates) / len(hashrates)
        std_dev = (sum((h - mean)**2 for h in hashrates) / len(hashrates)) ** 0.5
        cv      = std_dev / mean if mean > 0 else 1.0
        stability = round(max(0.0, min(100.0, (1.0 - cv * 2.0) * 100.0)), 1)
    else:
        stability = None

    # ── Flagging frequency ───────────────────────────────────────────────────
    flagged_scans = conn.execute("""
        SELECT COUNT(*) as cnt FROM miner_readings
        WHERE miner_id = ? AND issue IS NOT NULL AND issue != ''
          AND scan_id IN (SELECT id FROM scans WHERE scanned_at >= ?)
    """, (miner_id, cutoff)).fetchone()["cnt"]

    total_scans = conn.execute("""
        SELECT COUNT(*) as cnt FROM miner_readings
        WHERE miner_id = ?
          AND scan_id IN (SELECT id FROM scans WHERE scanned_at >= ?)
    """, (miner_id, cutoff)).fetchone()["cnt"]

    # Express as flags per week
    weeks = LOOKBACK_DAYS / 7.0
    flag_freq = round(flagged_scans / weeks, 2) if weeks > 0 else 0

    # ── Known issues ─────────────────────────────────────────────────────────
    known_issues = []
    dead = conn.execute("""
        SELECT board_indices FROM known_dead_boards
        WHERE miner_id = ? AND resolved_at IS NULL
    """, (miner_id,)).fetchone()
    if dead:
        known_issues.append(f"dead_boards:{dead['board_indices']}")

    conn.close()

    # ── Confidence modifier ───────────────────────────────────────────────────
    # How much to adjust confidence relative to fleet average
    # +ve = more trustworthy than average, -ve = less trustworthy
    modifier = 0.0
    if success_rate is not None:
        modifier += (success_rate - 0.5) * 0.4   # ±20% based on success rate
    if stability is not None:
        modifier += (stability / 100.0 - 0.5) * 0.2  # ±10% based on stability
    if known_issues:
        modifier -= 0.3  # -30% for known dead boards
    modifier = round(max(-0.5, min(0.5, modifier)), 3)

    return {
        "miner_id":               miner_id,
        "ip":                     ip,
        "model":                  model,
        "restart_success_rate":   success_rate,
        "avg_recovery_time_scans":avg_recovery,
        "flag_frequency_per_week":flag_freq,
        "hashrate_stability_score":stability,
        "avg_hashrate_pct":       avg_hr,
        "known_issues":           known_issues,
        "confidence_modifier":    modifier,
        "total_restarts":         total_restarts,
        "total_scans":            total_scans,
        "total_scans_flagged":    flagged_scans,
        "last_updated":           datetime.now().isoformat()
    }


def get_fingerprint(miner_id: str) -> Optional[Dict[str, Any]]:
    """Get a single miner's fingerprint from knowledge.json."""
    knowledge = _load_knowledge()
    return knowledge.get("miner_fingerprints", {}).get(miner_id)


def get_confidence_modifier(miner_id: str) -> float:
    """
    Return the confidence modifier for a miner (-0.5 to +0.5).
    Used by confidence_scorer.py to adjust per-miner confidence.
    Returns 0.0 if no fingerprint exists yet.
    """
    fp = get_fingerprint(miner_id)
    if fp is None:
        return 0.0
    return float(fp.get("confidence_modifier", 0.0))


def print_fleet_fingerprints():
    """Print a human-readable summary of all miner fingerprints."""
    knowledge = _load_knowledge()
    fps = knowledge.get("miner_fingerprints", {})

    if not fps:
        print("No fingerprints built yet. Run build_all_fingerprints() first.")
        return

    print(f"\n{'='*80}")
    print(f"{'MINER FINGERPRINTS':^80}")
    print(f"{'='*80}")
    print(f"{'IP':<20} {'Model':<18} {'SuccRate':>8} {'Stab':>6} {'FlagWk':>6} {'Modifier':>9} {'Issues'}")
    print(f"{'-'*80}")

    for mid, fp in sorted(fps.items(), key=lambda x: x[1].get("ip","")):
        rate    = f"{fp['restart_success_rate']*100:.0f}%" if fp.get("restart_success_rate") is not None else "N/A"
        stab    = f"{fp['hashrate_stability_score']:.0f}%" if fp.get("hashrate_stability_score") is not None else "N/A"
        freq    = f"{fp.get('flag_frequency_per_week', 0):.1f}"
        mod     = f"{fp.get('confidence_modifier', 0):+.2f}"
        issues  = ", ".join(fp.get("known_issues", [])) or "none"
        model   = (fp.get("model","?") or "?")[:17]
        print(f"{fp.get('ip','?'):<20} {model:<18} {rate:>8} {stab:>6} {freq:>6} {mod:>9}  {issues}")

    print(f"{'='*80}")
    updated = knowledge.get("fingerprints_updated_at", "unknown")
    print(f"Last updated: {updated[:19] if updated else 'never'}")
    print(f"Total miners fingerprinted: {len(fps)}\n")


def _load_knowledge() -> dict:
    path = Path(KNOWLEDGE_PATH)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def _save_knowledge(knowledge: dict):
    with open(KNOWLEDGE_PATH, "w") as f:
        json.dump(knowledge, f, indent=2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    logger.info("Building all miner fingerprints...")
    result = build_all_fingerprints()
    logger.info("Done: %d fingerprints built", result["built"])
    print_fleet_fingerprints()
