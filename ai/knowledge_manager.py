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
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger("knowledge_manager")

from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = str(_ROOT / "guardian.db")
KNOWLEDGE_PATH = str(_ROOT / "knowledge.json")


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
        # Deduplicate patterns before saving
        seen = []
        unique = []
        for p in self.knowledge.get("patterns", []):
            if p not in seen:
                seen.append(p)
                unique.append(p)
        self.knowledge["patterns"] = unique
        # Atomic write — write to temp file then replace so a crash mid-write
        # never corrupts knowledge.json (which would silently reset to empty on next load)
        tmp_path = self.knowledge_path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(self.knowledge, f, indent=2)
        os.replace(tmp_path, self.knowledge_path)
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
            "insight": insight[:50000],
        }

        # Keep last 50 insights
        self.knowledge["known_issues"] = self.knowledge["known_issues"][-49:] + [entry]
        self.save()

    def build_context_prompt(self) -> str:
        """Build a knowledge context string to include in every LLM prompt.

        Pulls live data from all tables — not just knowledge.json —
        so the LLM has the richest possible context every scan cycle.
        """
        parts = ["FLEET KNOWLEDGE (accumulated from past scans):"]

        # Fleet summary
        fs = self.knowledge.get("fleet_summary", {})
        if fs:
            parts.append(f"Last scan: {fs.get('last_scan', 'unknown')}")
            parts.append(f"Fleet: {fs.get('total_miners', '?')} miners, "
                        f"{fs.get('online', '?')} online, {fs.get('offline', '?')} offline")
            if fs.get("supply_water_f"):
                parts.append(f"HVAC: supply={fs['supply_water_f']}°F return={fs.get('return_water_f')}°F")
            if fs.get("outside_temp_f"):
                parts.append(f"Outside: {fs['outside_temp_f']}°F")

        # Pull live board-level data — chronic HW errors, dead boards
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.row_factory = sqlite3.Row

            # Miners with hardware identity parsed
            hw_count = conn.execute("SELECT COUNT(DISTINCT miner_id) FROM miner_hardware").fetchone()[0]
            parts.append(f"\nHardware identity: {hw_count} miners with full board/chip data")

            # Boards with HW errors in last 7 days
            hwerr = conn.execute("""
                SELECT miner_id, ip, board_index, SUM(hw_errors) as total_errors
                FROM chain_readings
                WHERE scanned_at > datetime('now', '-7 days')
                GROUP BY miner_id, board_index
                HAVING total_errors > 0
                ORDER BY total_errors DESC LIMIT 10
            """).fetchall()
            if hwerr:
                parts.append("\nBoards with HW errors (last 7 days):")
                for h in hwerr:
                    parts.append(f"  - {h['ip']} board {h['board_index']}: {h['total_errors']} errors")

            # Pool rejection spikes
            pool = conn.execute("""
                SELECT miner_id, ip, pool_url,
                       ROUND(MAX(rejected)*100.0/NULLIF(MAX(accepted)+MAX(rejected),0), 2) as reject_pct
                FROM pool_readings
                WHERE scanned_at > datetime('now', '-24 hours')
                GROUP BY miner_id
                HAVING reject_pct > 1.0
                ORDER BY reject_pct DESC LIMIT 5
            """).fetchall()
            if pool:
                parts.append("\nHigh pool rejection rates (last 24h):")
                for p in pool:
                    parts.append(f"  - {p['ip']}: {p['reject_pct']}% rejected")

            # Known dead boards
            dead = conn.execute("""
                SELECT ip, board_indices, ticket_created
                FROM known_dead_boards WHERE resolved_at IS NULL
            """).fetchall()
            if dead:
                parts.append("\nKnown dead boards (awaiting repair):")
                for d in dead:
                    ticket = f"ticket #{d['ticket_created']}" if d['ticket_created'] else "no ticket yet"
                    parts.append(f"  - {d['ip']} boards {d['board_indices']} — {ticket}")

            conn.close()
        except Exception as e:
            parts.append(f"(Live DB context unavailable: {e})")

        # Chronic problem miners from knowledge.json
        profiles = self.knowledge.get("miner_profiles", {})
        chronic = sorted(profiles.items(), key=lambda x: x[1].get("total_flags", 0), reverse=True)[:10]
        if chronic:
            parts.append("\nChronic problem miners (most flagged):")
            for mid, p in chronic:
                if p["total_flags"] >= 3:
                    recent = p["issue_history"][-1]["summary"] if p["issue_history"] else "unknown"
                    parts.append(f"  - Miner {mid} ({p['model']}) @ {p['ip']}: "
                                f"flagged {p['total_flags']}x, last: {recent[:100]}")

        # Recent LLM insights
        insights = self.knowledge.get("known_issues", [])[-5:]
        if insights:
            parts.append("\nRecent AI insights:")
            for i in insights:
                parts.append(f"  [{i['date']}] {i['insight'][:200]}")


        # DG-3 FIX: Critical missing sections
        op_rules = self.knowledge.get("operator_rules", [])
        if op_rules and len(op_rules) > 0:
            parts.append("\n=== OPERATOR RULES ===")
            for idx, rule in enumerate(op_rules, 1):
                if isinstance(rule, dict):
                    parts.append(f"{idx}. {rule.get("rule", "")}")
                else:
                    parts.append(f"{idx}. {rule}")

        refined = self.knowledge.get("refined_insights", {})
        if refined:
            parts.append("\n=== REFINED INSIGHTS ===")
            for cat, insights in refined.items():
                if insights:
                    for ins in insights[-5:]: parts.append(f"  {cat}: {ins}")

        preds = self.knowledge.get("predictions", [])
        if preds:
            parts.append(f"\n=== PREDICTIONS ({len(preds)} total, recent 20)")
            for p in preds[-20:]:
                if isinstance(p, dict):
                    parts.append(f"  {p.get("ip", "?")}: {len(p.get("triggered_signals", []))} signals")


        # DG-3 FULL: Remaining 11 sections

        # 1. Patterns
        patterns = self.knowledge.get("patterns", [])
        if patterns:
            parts.append("\n=== PATTERNS ===")
            for p in patterns:
                if isinstance(p, dict):
                    parts.append(f"  {p.get("pattern", "")}")

        # 2. Cross-miner analysis (recent 10)
        cross = self.knowledge.get("cross_miner_analysis", [])
        if cross:
            parts.append(f"\n=== CROSS-MINER ANALYSIS ({len(cross)} total, recent 10)")
            for c in cross[-10:]:
                if isinstance(c, dict):
                    parts.append(f"  {c.get("insight", "")}")

        # 3. Weekly refinement chain (recent 3)
        weekly = self.knowledge.get("weekly_refinement_chain", [])
        if weekly:
            parts.append(f"\n=== WEEKLY REFINEMENTS (recent 3)")
            for w in weekly[-3:]:
                if isinstance(w, dict):
                    parts.append(f"  {w.get("date", "")} refinement")

        # 4. Daily deep analyses (recent 3)
        daily = self.knowledge.get("daily_deep_analyses", [])
        if daily:
            parts.append(f"\n=== DAILY DEEP ANALYSES (recent 3)")
            for d in daily[-3:]:
                if isinstance(d, dict):
                    parts.append(f"  {d.get("date", "")}: {d.get("summary", "")[:80]}")

        # 5. LLM scan analyses (recent 20)
        scans = self.knowledge.get("llm_scan_analyses", [])
        if scans:
            parts.append(f"\n=== LLM SCAN ANALYSES ({len(scans)} total, recent 20)")
            for s in scans[-20:]:
                if isinstance(s, dict):
                    parts.append(f"  Scan {s.get("scan_id", "?")}: {len(s.get("issues", []))} issues")

        # 6. HVAC correlation
        hvac = self.knowledge.get("hvac_correlation", {})
        if hvac:
            parts.append("\n=== HVAC CORRELATION ===")
            for key, val in hvac.items():
                parts.append(f"  {key}: {val}")

        # 7. Facility events
        events = self.knowledge.get("facility_events", [])
        if events:
            parts.append(f"\n=== FACILITY EVENTS ({len(events)} total)")
            for e in events[-10:]:
                if isinstance(e, dict):
                    parts.append(f"  {e.get("date", "")}: {e.get("event", "")}")

        # 8. Prediction accuracy
        acc = self.knowledge.get("prediction_accuracy", {})
        if acc:
            parts.append("\n=== PREDICTION ACCURACY ===")
            parts.append(f"  Total predictions: {acc.get("total", 0)}")
            parts.append(f"  Correct: {acc.get("correct", 0)}")

        # 9. Miner profiles (chronic problem miners, top 15)
        profiles = self.knowledge.get("miner_profiles", {})
        if profiles:
            parts.append("\n=== CHRONIC PROBLEM MINERS (top 15)")
            sorted_miners = sorted(profiles.items(), key=lambda x: x[1].get('issue_count', 0), reverse=True)[:15]
            for ip, prof in sorted_miners:
                parts.append(f"  {ip}: {prof.get("issue_count", 0)} issues")

        # 10. Miner fingerprints (full 42-field expansion)
        fingerprints = self.knowledge.get("miner_fingerprints", {})
        if fingerprints:
            parts.append(f"\n=== MINER FINGERPRINTS ({len(fingerprints)} miners)")
            for ip, fp in list(fingerprints.items())[:20]:
                if isinstance(fp, dict):
                    model = fp.get("model", "?")
                    issues = fp.get("known_issues", [])
                    parts.append(f"  {ip} ({model}): {len(issues)} known issues")

        return "\n".join(parts)

    def store_operator_rule(self, category: str, rule_text: str, source: str = "operator_denial", confidence: int = 100):
        """Store a new operator rule learned from denial reasons or explicit guidance.
        
        Args:
            category: Rule category (e.g. "temperature", "offline_logic", "timing")
            rule_text: The actual rule text
            source: Where this rule came from ("operator_denial", "manual", "escalation")
            confidence: How confident we are in this rule (0-100)
        """
        from datetime import datetime
        
        # Load current rules
        rules = self.knowledge.get("operator_rules", [])
        
        # Check if similar rule already exists (avoid duplicates)
        for existing_rule in rules:
            if isinstance(existing_rule, dict):
                if existing_rule.get("rule", "").lower() == rule_text.lower():
                    # Rule already exists, dont add duplicate
                    return
            elif isinstance(existing_rule, str) and existing_rule.lower() == rule_text.lower():
                return
        
        # Add new structured rule
        new_rule = {
            "rule": rule_text,
            "category": category,
            "source": source,
            "confidence": confidence,
            "added_at": datetime.now().isoformat(),
            "times_applied": 0
        }
        
        rules.append(new_rule)
        self.knowledge["operator_rules"] = rules
        self.save()
        
        print(f"✓ Stored operator rule: {category} - {rule_text[:60]}...")
