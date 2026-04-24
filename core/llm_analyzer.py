"""
llm_analyzer.py
Mining Guardian — LLM Log Analyzer

Sends miner scan data and collected logs to the local Ollama LLM
for diagnosis and pattern detection. Stores analysis results in the database.
"""

import os
import json
import logging
import requests
from datetime import datetime
from typing import Optional, Dict, List
from pathlib import Path
from dotenv import load_dotenv

import psycopg2
from psycopg2.extras import DictCursor

load_dotenv()
logger = logging.getLogger("llm_analyzer")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://100.110.87.1:11434/api/generate")
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:32b-instruct-q4_K_M")
_ROOT = Path(__file__).resolve().parent.parent

# DB_PATH kept as legacy module constant for the constructor default.
# Value is ignored — all DB access goes through _pg_dsn() + psycopg2.
DB_PATH = "postgres"  # sentinel; constructor still accepts it for API compat


def _pg_dsn() -> str:
    """Build a Postgres DSN from GUARDIAN_PG_* env vars."""
    return (
        f"host={os.environ.get('GUARDIAN_PG_HOST', 'localhost')} "
        f"port={os.environ.get('GUARDIAN_PG_PORT', '5432')} "
        f"user={os.environ.get('GUARDIAN_PG_USER', 'guardian_app')} "
        f"password={os.environ['GUARDIAN_PG_PASSWORD']} "
        f"dbname={os.environ.get('GUARDIAN_PG_DB', 'mining_guardian')}"
    )

# Claude API for deep analysis (weekly training, knowledge merge)
CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are Mining Guardian AI, an expert Bitcoin mining fleet analyst for BiXBiT USA.
You analyze miner scan data and logs to diagnose problems, identify patterns, and recommend actions.

FACILITY CONTEXT:
- All cooling is liquid (hydro racks + immersion tank). No air cooling.
- HVAC system: supply water ~75°F, return water ~87°F. The supply/return
  delta-T varies seasonally — it is intentionally LOW in cooler months and
  rises as outside temperature climbs. A LOW delta-T is NORMAL and CORRECT.
  Do NOT recommend HVAC investigation based on low delta-T alone.
  Do NOT describe low delta-T as "minimal headroom" or "thermal stress".
  The HVAC system at USA 188 is performing as designed — assume it is fine
  unless multiple miners simultaneously exceed 84°C.
- Chip temp zones: GREEN <84°C (NO action needed), RED ≥84°C (action required).
- IMPORTANT: This is a liquid-cooled fleet. 67-73°C is COMPLETELY NORMAL for these miners.
  Do NOT recommend any thermal action, profile change, or cooling adjustment for any
  miner running below 84°C. Do NOT describe a miner as "running hot" or "overheating"
  unless its chip temp is at or above 84°C.
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
- Chain detachment can indicate a bad/dying hashboard, NOT just a firmware glitch. Compare pre-restart and post-restart logs to determine if the board recovered or if it's hardware failure.
- Always examine CGMiner logs before and after restarts — log patterns (chain errors, voltage drops, ASIC failures) reveal whether the root cause is firmware, PSU, or a failing board.

Rules:
- Be CONCISE — max 10 lines total. Operators are busy.
- Use specific miner IDs and IPs, never ranges like "53480-53590"
- Focus on ROOT CAUSE, not symptoms
- Group miners with the same issue together in one line
- ALWAYS consider profile adjustment for thermal issues before recommending cooling changes
- Dead board after 1 restart = maintenance ticket, stop recommending restarts
- Never recommend air cooling — this facility is 100% liquid cooled

Format (keep it SHORT):
DIAGNOSIS: (1 sentence max)
ACTION: (bullet list, one line per action, include miner IP)
PATTERN: (1 sentence or "none")"""


class LLMAnalyzer:
    def __init__(self, ollama_url: str = OLLAMA_URL, model: str = MODEL,
                 db_path: str = DB_PATH):
        self.ollama_url = ollama_url
        self.model = model
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self):
        """Ensure llm_analysis exists in Postgres. Idempotent — the table
        is usually created by migrations/001_initial_schema.sql at boot,
        but we keep this so LLMAnalyzer() stays self-contained for scripts
        that instantiate it outside the normal app lifecycle."""
        conn = psycopg2.connect(_pg_dsn())
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS llm_analysis (
                        id          SERIAL PRIMARY KEY,
                        scan_id     INTEGER,
                        analyzed_at TEXT NOT NULL,
                        miner_id    TEXT,
                        ip          TEXT,
                        prompt      TEXT,
                        response    TEXT,
                        model_used  TEXT,
                        duration_ms INTEGER
                    )
                """)
            conn.commit()
        finally:
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

    def _query_claude(self, prompt: str) -> tuple:
        """Send prompt to Claude API for deep analysis (weekly training, knowledge merge).

        Returns (response_text, duration_ms, model_used).
        Does NOT fall back to Ollama — callers that need a fallback must handle it
        explicitly. Falling back silently here caused two bugs:
          1. Scan loop could block for 300s on Ollama during Claude outages
          2. model_used in llm_analysis was logged as Claude even when Ollama ran

        Bug fix #3: includes accumulated fleet knowledge context so the Claude
        path has the same operational memory as the Ollama path.
        """
        if not CLAUDE_API_KEY:
            logger.warning("Claude API key not set — returning empty, no Ollama fallback")
            return "", 0, self.model

        # Load fleet knowledge context — same as _query_llm does
        knowledge_context = ""
        try:
            from knowledge_manager import KnowledgeManager
            km = KnowledgeManager()
            knowledge_context = km.build_context_prompt()
        except Exception:
            pass

        full_prompt = (
            f"{SYSTEM_PROMPT}\n\n{knowledge_context}\n\n{prompt}"
            if knowledge_context else
            f"{SYSTEM_PROMPT}\n\n{prompt}"
        )

        try:
            start = datetime.now()
            resp = requests.post("https://api.anthropic.com/v1/messages", json={
                "model": CLAUDE_MODEL,
                "max_tokens": 16384,
                "messages": [{"role": "user", "content": full_prompt}]
            }, headers={
                "x-api-key": CLAUDE_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }, timeout=120)
            elapsed = int((datetime.now() - start).total_seconds() * 1000)
            resp.raise_for_status()
            data = resp.json()
            # Safely extract text block
            for block in data.get("content", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block["text"]
                    logger.info("Claude analysis complete (%dms, %d chars)", elapsed, len(text))
                    return text, elapsed, CLAUDE_MODEL
            logger.error("Claude returned no text block: %s", list(data.keys()))
            return "", elapsed, CLAUDE_MODEL
        except requests.exceptions.Timeout:
            logger.error("Claude API timed out after 120s — no fallback")
            return "", 0, CLAUDE_MODEL
        except requests.exceptions.HTTPError as e:
            logger.error("Claude API HTTP %s — no fallback: %s",
                         e.response.status_code, e.response.text[:200])
            return "", 0, CLAUDE_MODEL
        except Exception as e:
            logger.error("Claude API error — no fallback: %s", e)
            return "", 0, CLAUDE_MODEL

    def deep_analyze(self, prompt: str) -> str:
        """Use Claude API for deep analysis (weekly training, knowledge merge).

        Bug fix #2: records the model that actually ran, not just whether the
        API key is set. If Claude fails, model_used reflects that correctly.
        """
        response, duration, model_used = self._query_claude(prompt)
        conn = psycopg2.connect(_pg_dsn())
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO llm_analysis
                    (scan_id, analyzed_at, miner_id, ip, prompt, response, model_used, duration_ms)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (0, datetime.now().isoformat(), "deep_analysis", "all",
                      prompt[:2000], response, model_used, duration))
            conn.commit()
        finally:
            conn.close()
        return response

    def analyze_issues(self, scan_id: int, issues: List[Dict],
                       weather: Optional[Dict] = None,
                       hvac: Optional[Dict] = None) -> str:
        """Analyze all flagged miners from a scan in a single LLM call."""
        if not issues:
            return ""

        # Intelligence Catalog context for flagged models
        try:
            from ai.catalog_context import get_catalog_context
            models = list({i.get("model", "") for i in issues if i.get("model")})
            catalog_ctx = get_catalog_context(models) if models else ""
        except Exception:
            catalog_ctx = ""

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

        if catalog_ctx:
            prompt_parts.append(f"\n--- INTELLIGENCE CATALOG ---\n{catalog_ctx}")

        prompt_parts.append("\nAnalyze these issues. Identify patterns, root causes, "
                           "and prioritize which miners need attention first.")

        prompt = "\n".join(prompt_parts)
        response, duration = self._query_llm(prompt)

        # Save to database
        conn = psycopg2.connect(_pg_dsn())
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO llm_analysis
                    (scan_id, analyzed_at, miner_id, ip, prompt, response, model_used, duration_ms)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (scan_id, datetime.now().isoformat(), "fleet", "all",
                      prompt, response, self.model, duration))
            conn.commit()
        finally:
            conn.close()

        logger.info("LLM analysis complete for scan %s (%dms, %d chars)",
                    scan_id, duration, len(response))
        return response

    def analyze_single_miner(self, scan_id: int, miner_id: str,
                             ip: str, model: str, problem: str,
                             logs: Optional[Dict] = None) -> str:
        """Deep analysis of a single miner with its full logs.

        Logs are sectioned — boot/init, mid-operation sample, recent tail —
        so the LLM sees the full picture without a hard char truncation.
        """
        prompt = (f"Deep analysis needed for miner {miner_id} ({model}) @ {ip}:\n"
                  f"Problem: {problem}\n")
        if logs:
            for filename, content in logs.items():
                if not content:
                    continue
                if len(content) > 16000:
                    boot   = content[:8000]
                    mid_s  = len(content) // 2
                    mid    = content[mid_s:mid_s + 4000]
                    tail   = content[-4000:]
                    sectioned = (
                        f"[BOOT/INIT — first 8000 chars]\n{boot}\n"
                        f"[MID-OPERATION SAMPLE]\n{mid}\n"
                        f"[RECENT TAIL — last 4000 chars]\n{tail}"
                    )
                else:
                    sectioned = content
                prompt += f"\n--- {filename} ---\n{sectioned}\n"
        # Intelligence Catalog context for this model
        try:
            from ai.catalog_context import get_miner_catalog_context
            catalog_ctx = get_miner_catalog_context(model) if model else ""
        except Exception:
            catalog_ctx = ""

        if catalog_ctx:
            prompt += f"\n--- INTELLIGENCE CATALOG ---\n{catalog_ctx}\n"

        prompt += "\nProvide detailed diagnosis with root cause and recommended fix."

        response, duration = self._query_llm(prompt)

        conn = psycopg2.connect(_pg_dsn())
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO llm_analysis
                    (scan_id, analyzed_at, miner_id, ip, prompt, response, model_used, duration_ms)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (scan_id, datetime.now().isoformat(), miner_id, ip,
                      prompt[:5000], response, self.model, duration))
            conn.commit()
        finally:
            conn.close()

        logger.info("LLM single-miner analysis: %s (%dms)", miner_id, duration)
        return response
