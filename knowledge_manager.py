"""
knowledge_manager.py
Mining Guardian — Persistent Knowledge System

Maintains a knowledge.json file that accumulates fleet patterns,
miner histories, and LLM insights over time. This file is included
in every LLM prompt so the model has persistent memory across scans.

The knowledge file grows as Mining Guardian learns your fleet.
Weekly training passes update it with deeper analysis.
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger("knowledge_manager")

DB_PATH = "guardian.db"
KNOWLEDGE_PATH = "knowledge.json"


class KnowledgeManager:
    def __init__(self, db_path: str = DB_PATH, knowledge_path: str = KNOWLEDGE_PATH):
        self.db_path = db_path
        self.knowledge_path = knowledge_path
        self.knowledge = self._load()

    def _load(self) -> Dict:
        try:
            with open(self.knowledge_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "version": 1,
                "last_updated": None,
                "fleet_summary": {},
                "miner_profiles": {},
                "known_issues": [],
                "patterns": [],
                "baselines": {},
            }

    def save(self):
        self.knowledge["last_updated"] = datetime.now().isoformat()
        with open(self.knowledge_path, "w") as f:
            json.dump(self.knowledge, f, indent=2)
        logger.info("Knowledge saved — %d known issues, %d patterns",
                     len(self.knowledge["known_issues"]),
                     len(self.knowledge["patterns"]))

    def update_from_scan(self, miners: List[Dict], issues: List[Dict],
                         weather: Optional[Dict] = None, hvac=None):
        """Update knowledge after each scan with fleet stats and issue patterns."""
        now = datetime.now().isoformat()
        online = sum(1 for m in miners if m.get("status") == "online")

        # Update fleet summary
        self.knowledge["fleet_summary"] = {
            "last_scan": now,
            "total_miners": len(miners),
            "online": online,
            "offline": len(miners) - online,
            "issues_this_scan": len(issues),
            "outside_temp_f": weather.get("temp_f") if weather else None,
            "supply_water_f": hvac.supply_temp_f if hvac else None,
            "return_water_f": hvac.return_temp_f if hvac else None,
        }

        # Track recurring issues by miner
        for issue in issues:
            mid = issue.get("id")
            if mid not in self.knowledge.get("miner_profiles", {}):
                self.knowledge["miner_profiles"][mid] = {
                    "model": issue.get("model"),
                    "ip": issue.get("ip"),
                    "total_flags": 0,
                    "last_flagged": None,
                    "issue_history": [],
                }

            profile = self.knowledge["miner_profiles"][mid]
            profile["total_flags"] += 1
            profile["last_flagged"] = now
            # Keep last 10 issues per miner
            profile["issue_history"] = profile["issue_history"][-9:] + [{
                "date": now[:10],
                "action": issue.get("action"),
                "summary": " | ".join(issue.get("issues", []))[:200],
            }]

        self.save()

    def add_llm_insight(self, insight: str, miner_id: str = "fleet"):
        """Add an LLM-generated insight to persistent knowledge."""
        # Extract key patterns from LLM response
        if not insight or "LLM error" in insight:
            return

        entry = {
            "date": datetime.now().isoformat()[:10],
            "miner_id": miner_id,
            "insight": insight[:500],
        }

        # Keep last 50 insights
        self.knowledge["known_issues"] = self.knowledge["known_issues"][-49:] + [entry]
        self.save()

    def build_context_prompt(self) -> str:
        """Build a knowledge context string to include in every LLM prompt."""
        parts = ["FLEET KNOWLEDGE (accumulated from past scans):"]

        # Fleet summary
        fs = self.knowledge.get("fleet_summary", {})
        if fs:
            parts.append(f"Last scan: {fs.get('last_scan', 'unknown')}")
            parts.append(f"Fleet: {fs.get('total_miners', '?')} miners, "
                        f"{fs.get('online', '?')} online, {fs.get('offline', '?')} offline")

        # Chronic problem miners
        profiles = self.knowledge.get("miner_profiles", {})
        chronic = sorted(profiles.items(), key=lambda x: x[1].get("total_flags", 0), reverse=True)[:10]
        if chronic:
            parts.append("\nChronic problem miners (most flagged):")
            for mid, p in chronic:
                if p["total_flags"] >= 3:
                    recent = p["issue_history"][-1]["summary"] if p["issue_history"] else "unknown"
                    parts.append(f"  - Miner {mid} ({p['model']}) @ {p['ip']}: "
                                f"flagged {p['total_flags']}x, last: {recent}")

        # Recent LLM insights
        insights = self.knowledge.get("known_issues", [])[-5:]
        if insights:
            parts.append("\nRecent AI insights:")
            for i in insights:
                parts.append(f"  [{i['date']}] {i['insight'][:200]}")

        return "\n".join(parts)
