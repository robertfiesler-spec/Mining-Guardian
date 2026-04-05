#!/usr/bin/env python3
"""
weekly_train.py
Mining Guardian — Weekly LLM Training Cron Job

Runs once a week (Sunday 3am) to deep-analyze the full fleet
with ALL accumulated data — logs, chain readings, pool stats,
hardware identity, per-chip data, HVAC/weather correlation.

Cron: 0 3 * * 0 cd /root/Mining-Gaurdian && venv/bin/python weekly_train.py >> /tmp/weekly_train.log 2>&1
"""

import sys
import logging
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "ai") not in sys.path:
    sys.path.insert(0, str(_ROOT / "ai"))

from train_comprehensive import run_comprehensive_training
from knowledge_manager import KnowledgeManager

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("weekly_train")


def run_weekly():
    logger.info("=" * 60)
    logger.info("WEEKLY TRAINING — Starting comprehensive analysis")
    logger.info("Feeds: full logs (no truncation), chain readings, pool data,")
    logger.info("hardware identity, per-chip hashrate, PSU voltage, audit history")
    logger.info("=" * 60)

    try:
        run_comprehensive_training()
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

    logger.info("=" * 60)
    logger.info("WEEKLY TRAINING — Complete")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_weekly()
