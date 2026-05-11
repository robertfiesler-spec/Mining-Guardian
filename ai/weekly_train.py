#!/usr/bin/env python3
"""
weekly_train.py
Mining Guardian — Weekly LLM Training Cron Job

Runs once a week (Sunday 3am) to deep-analyze the full fleet
with ALL accumulated data — logs, chain readings, pool stats,
hardware identity, per-chip data, HVAC/weather correlation.

Schedule: managed by a launchd plist on the Mac Mini install (see
docs/CRON_SCHEDULE.md for the canonical schedule).
"""

import sys
import logging
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "ai") not in sys.path:
    sys.path.insert(0, str(_ROOT / "ai"))
# P-038 items #4 + #5 env-gate (2026-05-11): need _ROOT itself on sys.path
# for `from core.anthropic_gate import ...`. The existing line above only
# inserts `_ROOT / "ai"` to enable bare-name imports like
# `from train_cohort import ...`; core.* full-path imports need _ROOT.
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from train_cohort import run_cohort_training
from knowledge_manager import KnowledgeManager
from core.anthropic_gate import require_anthropic_or_exit

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("weekly_train")


def run_weekly():
    # P-038 items #4 + #5 env-gate (2026-05-11): exit cleanly when
    # Anthropic is not provisioned at install time. Customer Minis
    # that opt out of Anthropic skip this entire job with exit 0
    # rather than running 18 minutes producing empty Claude output.
    # See core/anthropic_gate.py for the full contract.
    require_anthropic_or_exit("weekly_training", logger)

    logger.info("=" * 60)
    logger.info("WEEKLY TRAINING — Starting cohort-based analysis")
    logger.info("Feeds: full logs (no truncation), chain readings, pool data,")
    logger.info("hardware identity, per-chip hashrate, PSU voltage, audit history")
    logger.info("=" * 60)

    try:
        run_cohort_training()
    except Exception as e:
        logger.error("Comprehensive training failed: %s", e)
        raise

    # Feature 4: Rebuild miner fingerprints after training
    try:
        from fingerprint_builder import build_all_fingerprints
        logger.info("Building miner fingerprints...")
        result = build_all_fingerprints()
        logger.info("Fingerprints built: %d miners", result["built"])
    except Exception as e:
        logger.warning("Fingerprint building failed (non-fatal): %s", e)

    # Feature 5: Compute HVAC correlation patterns and add to knowledge
    try:
        from hvac_correlator import get_hvac_correlation_patterns
        logger.info("Computing HVAC correlation patterns...")
        patterns = get_hvac_correlation_patterns(lookback_days=30)
        if "error" not in patterns:
            import json
            from pathlib import Path
            kpath = Path(_ROOT / "knowledge.json")
            knowledge = json.loads(kpath.read_text()) if kpath.exists() else {}
            knowledge["hvac_correlation"] = patterns
            kpath.write_text(json.dumps(knowledge, indent=2))
            corr = patterns.get("supply_temp_flag_correlation", 0)
            logger.info("HVAC correlation: supply_temp vs flags = %.3f", corr)
    except Exception as e:
        logger.warning("HVAC correlation failed (non-fatal): %s", e)

    # Feature 6: Log prediction accuracy into knowledge for training
    try:
        from predictor import get_prediction_accuracy
        accuracy = get_prediction_accuracy()
        logger.info("Prediction accuracy: %s", accuracy)
    except Exception as e:
        logger.warning("Prediction accuracy check failed (non-fatal): %s", e)

    logger.info("=" * 60)
    logger.info("WEEKLY TRAINING — Complete")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_weekly()
