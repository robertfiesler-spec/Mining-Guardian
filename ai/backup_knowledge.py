#!/usr/bin/env python3
"""
backup_knowledge.py
Mining Guardian — Daily Knowledge Backup to GitHub

Copies knowledge.json to knowledge_backup.json (tracked in git)
and pushes to GitHub. Runs daily via cron.

Schedule: managed by a launchd plist on the Mac Mini install (see
docs/CRON_SCHEDULE.md for the canonical schedule). Ad-hoc runs use
`venv/bin/python ai/backup_knowledge.py` from ${MG_INSTALL_ROOT} (or
the dev clone root).
"""

import json
import shutil
import subprocess
import logging
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backup_knowledge")


def backup():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    logger.info("Knowledge backup starting — %s", now)

    knowledge_path = str(_ROOT / "knowledge.json")
    backup_path = str(_ROOT / "knowledge_backup.json")

    try:
        # Load and validate knowledge.json
        with open(knowledge_path) as f:
            data = json.load(f)

        miners = len(data.get("miner_profiles", {}))
        insights = len(data.get("known_issues", []))
        patterns = len(data.get("patterns", []))
        logger.info("Knowledge: %d miners, %d insights, %d patterns", miners, insights, patterns)

        # Copy to tracked backup file
        shutil.copy2(knowledge_path, backup_path)

        # Git add, commit, push — all from repo root
        subprocess.run(["git", "add", "knowledge_backup.json"], cwd=str(_ROOT), check=True)
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet", "knowledge_backup.json"],
            cwd=str(_ROOT), capture_output=True)

        if result.returncode != 0:
            # There are changes to commit
            msg = f"Daily knowledge backup — {now} — {miners} miners, {insights} insights, {patterns} patterns"
            subprocess.run(["git", "commit", "-m", msg], cwd=str(_ROOT), check=True)
            subprocess.run(["git", "push"], cwd=str(_ROOT), check=True)
            logger.info("Backup pushed to GitHub: %s", msg)
        else:
            logger.info("No changes since last backup — skipping push")

    except FileNotFoundError:
        logger.error("knowledge.json not found at %s — nothing to backup", knowledge_path)
    except Exception as e:
        logger.error("Backup failed: %s", e)


if __name__ == "__main__":
    backup()
