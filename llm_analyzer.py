"""
llm_analyzer.py
Mining Guardian — LLM Log Analyzer

Sends miner scan data and collected logs to the local Ollama LLM
for diagnosis and pattern detection. Stores analysis results in the database.
"""

import json
import logging
import sqlite3
import requests
from datetime import datetime
from typing import Optional, Dict, List

logger = logging.getLogger("llm_analyzer")

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.1:8b"
DB_PATH = "guardian.db"

SYSTEM_PROMPT = """You are Mining Guardian AI, an expert Bitcoin mining fleet analyst for BiXBiT USA.
You analyze miner scan data and logs to diagnose problems, identify patterns, and recommend actions.

FACILITY CONTEXT:
- All cooling is liquid (hydro racks + immersion tank). No air cooling.
- HVAC system: supply water ~75°F, return water ~87°F, ΔT ~11°F is normal.
- Chip temp zones: GREEN <76°C, YELLOW 76-85°C, RED 86°C+.
- Outside ambient temp in Fort Worth TX affects cooling efficiency.

REMEDIATION OPTIONS (use the right tool for the job):
- Firmware restart: first-line fix for hashrate drops, software glitches, stuck miners.
- PDU power cycle: for miners that don't respond to firmware restart (hard power reset).
- Lower TH/s profile: for overheating miners — reduces hash rate and power draw, which lowers chip temp. This is often better than adding cooling because it's immediate and doesn't require physical changes. Example: drop from "144 TH/s" profile to "120 TH/s" profile.
- Raise cooling: increase CT fan speed or CW pump speed if multiple miners overheat simultaneously (suggests environmental cause, not individual miner issue).
- Dead hashboard restart: restart + compare logs before/after to check if board recovers.
- Physical inspection: for persistent hardware failures that don't resolve with restarts.

DECISION RULES:
- Single miner running hot while others are fine → lower that miner's TH/s profile first, NOT cooling adjustment.
- Multiple miners running hot simultaneously → environmental cause, check cooling system.
- Hashrate drop without temperature issue → firmware restart.
- Dead hashboard after 1 restart attempt → create maintenance ticket, stop reflagging.
- Miner at 0% hashrate with all boards dead → likely needs physical inspection.

Rules:
- Be concise and actionable — operators read this in Slack
- Focus on ROOT CAUSE, not symptoms
- If multiple miners have the same issue, identify the common pattern
- Flag recurring problems that suggest hardware failure vs temporary issues
- Note any environmental correlations (temperature, power)
- ALWAYS consider profile adjustment as an option for thermal issues before recommending cooling changes

Format your response as:
DIAGNOSIS: (1-2 sentences)
ROOT CAUSE: (best guess)
ACTION: (specific recommendation — include profile adjustment when thermal issues are involved)
PATTERN: (any trend across multiple scans, or "none detected" if first occurrence)"""


class LLMAnalyzer:
    def __init__(self, ollama_url: str = OLLAMA_URL, model: str = MODEL,
                 db_path: str = DB_PATH):
        self.ollama_url = ollama_url
        self.model = model
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_analysis (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id       INTEGER,
                analyzed_at   TEXT NOT NULL,
                miner_id      TEXT,
                ip            TEXT,
                prompt         TEXT,
                response      TEXT,
                model_used    TEXT,
                duration_ms   INTEGER
            )
        """)
        conn.commit()
        conn.close()

    def _query_llm(self, prompt: str) -> tuple:
        """Send prompt to Ollama and return (response_text, duration_ms)."""
        try:
            # Include accumulated fleet knowledge in every prompt
            knowledge_context = ""
            try:
                from knowledge_manager import KnowledgeManager
                km = KnowledgeManager()
                knowledge_context = km.build_context_prompt()
            except Exception:
                pass

            full_prompt = f"{SYSTEM_PROMPT}\n\n{knowledge_context}\n\n{prompt}" if knowledge_context else f"{SYSTEM_PROMPT}\n\n{prompt}"

            start = datetime.now()
            resp = requests.post(self.ollama_url, json={
                "model": self.model,
                "prompt": full_prompt,
                "stream": False
            }, timeout=300)
            elapsed = int((datetime.now() - start).total_seconds() * 1000)
            data = resp.json()
            return data.get("response", ""), elapsed
        except Exception as e:
            logger.error("LLM query failed: %s", e)
            return f"LLM error: {e}", 0

    def analyze_issues(self, scan_id: int, issues: List[Dict],
                       weather: Optional[Dict] = None,
                       hvac: Optional[Dict] = None) -> str:
        """Analyze all flagged miners from a scan in a single LLM call."""
        if not issues:
            return ""

        prompt_parts = [f"Scan #{scan_id} — {len(issues)} miners flagged:\n"]

        # Cap at 10 miners per LLM call to keep prompt manageable for CPU inference
        capped = issues[:10]
        if len(issues) > 10:
            prompt_parts.append(f"(Showing top 10 of {len(issues)} — prioritized by severity)")

        for i in capped:
            # Keep issue descriptions concise — max 150 chars each
            issue_str = ' | '.join(i.get('issues', []))[:150]
            line = (f"- Miner {i['id']} ({i['model']}) @ {i['ip']}: "
                    f"{i.get('action', 'UNKNOWN')} — {issue_str}")
            prompt_parts.append(line)

        if weather:
            prompt_parts.append(f"\nEnvironment: {weather.get('temp_f', '?')}°F, "
                               f"humidity {weather.get('humidity_pct', '?')}%")
        if hvac:
            prompt_parts.append(f"HVAC: Supply {hvac.get('supply_temp_f', '?')}°F, "
                               f"Return {hvac.get('return_temp_f', '?')}°F, "
                               f"ΔT {hvac.get('delta_t_f', '?')}°F")

        prompt_parts.append("\nAnalyze these issues. Identify patterns, root causes, "
                           "and prioritize which miners need attention first.")

        prompt = "\n".join(prompt_parts)
        response, duration = self._query_llm(prompt)

        # Save to database
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO llm_analysis
            (scan_id, analyzed_at, miner_id, ip, prompt, response, model_used, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (scan_id, datetime.now().isoformat(), "fleet", "all",
              prompt, response, self.model, duration))
        conn.commit()
        conn.close()

        logger.info("LLM analysis complete for scan %s (%dms, %d chars)",
                    scan_id, duration, len(response))
        return response

    def analyze_single_miner(self, scan_id: int, miner_id: str,
                             ip: str, model: str, problem: str,
                             logs: Optional[Dict] = None) -> str:
        """Deep analysis of a single miner with its logs."""
        prompt = (f"Deep analysis needed for miner {miner_id} ({model}) @ {ip}:\n"
                  f"Problem: {problem}\n")
        if logs:
            prompt += f"\nMiner logs:\n{json.dumps(logs, indent=2)[:3000]}\n"
        prompt += "\nProvide detailed diagnosis with root cause and recommended fix."

        response, duration = self._query_llm(prompt)

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO llm_analysis
            (scan_id, analyzed_at, miner_id, ip, prompt, response, model_used, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (scan_id, datetime.now().isoformat(), miner_id, ip,
              prompt, response, self.model, duration))
        conn.commit()
        conn.close()

        logger.info("LLM single-miner analysis: %s (%dms)", miner_id, duration)
        return response
