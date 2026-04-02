#!/usr/bin/env python3
"""
weekly_train.py
Mining Guardian — Weekly LLM Training Cron Job

Runs once a week to re-analyze the full fleet with accumulated data.
Updates knowledge.json with fresh patterns and insights.

Usage: python3 weekly_train.py
Cron:  0 3 * * 0 cd /root/Mining-Gaurdian && venv/bin/python weekly_train.py >> /tmp/weekly_train.log 2>&1
"""

import logging
from train_llm import train_on_logs
from train_llm_pass2 import train_pass2
from knowledge_manager import KnowledgeManager

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("weekly_train")


def run_weekly():
    logger.info("=" * 60)
    logger.info("WEEKLY TRAINING — Starting")
    logger.info("=" * 60)

    # Pass 1 — analyze miners with CGMiner logs
    logger.info("Pass 1 — CGMiner log analysis")
    try:
        train_on_logs()
    except Exception as e:
        logger.error("Pass 1 failed: %s", e)

    # Pass 2 — fleet-wide scan data + AMS notifications
    logger.info("Pass 2 — Fleet-wide scan analysis")
    try:
        train_pass2()
    except Exception as e:
        logger.error("Pass 2 failed: %s", e)

    # Update knowledge.json with latest insights
    logger.info("Updating knowledge.json")
    km = KnowledgeManager()
    km.save()

    logger.info("=" * 60)
    logger.info("WEEKLY TRAINING — Complete")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_weekly()
