#!/usr/bin/env python3
"""
backup_knowledge.py
Mining Guardian — Daily Knowledge Backup to GitHub

Copies knowledge.json to knowledge_backup.json (tracked in git)
and pushes to GitHub. Runs daily via cron.

Cron: 0 4 * * * cd /root/Mining-Gaurdian && venv/bin/python backup_knowledge.py >> /tmp/knowledge_backup.log 2>&1
"""

import json
import shutil
import subprocess
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backup_knowledge")


def backup():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    logger.info("Knowledge backup starting — %s", now)

    try:
        # Load and validate knowledge.json
        with open("knowledge.json") as f:
            data = json.load(f)

        miners = len(data.get("miner_profiles", {}))
        insights = len(data.get("known_issues", []))
        patterns = len(data.get("patterns", []))
        logger.info("Knowledge: %d miners, %d insights, %d patterns", miners, insights, patterns)

        # Copy to tracked backup file
        shutil.copy2("knowledge.json", "knowledge_backup.json")

        # Git add, commit, push
        subprocess.run(["git", "add", "knowledge_backup.json"], check=True)
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet", "knowledge_backup.json"],
            capture_output=True)

        if result.returncode != 0:
            # There are changes to commit
            msg = f"Daily knowledge backup — {now} — {miners} miners, {insights} insights, {patterns} patterns"
            subprocess.run(["git", "commit", "-m", msg], check=True)
            subprocess.run(["git", "push"], check=True)
            logger.info("Backup pushed to GitHub: %s", msg)
        else:
            logger.info("No changes since last backup — skipping push")

    except FileNotFoundError:
        logger.error("knowledge.json not found — nothing to backup")
    except Exception as e:
        logger.error("Backup failed: %s", e)


if __name__ == "__main__":
    backup()
