#!/usr/bin/env python3
"""
Mining Guardian — Daily Deep Dive LLM Analysis

Purpose:
    Once per day, the local Qwen 32B LLM on ROBS-PC (RTX 4090) does a long,
    uninterrupted study session of the entire fleet state. Every online
    miner gets individual attention with its full daily baseline log, its
    24-hour metric trends, its restart history, its hardware identity, and
    any operator interactions involving it. Then a fleet-wide synthesis
    pass ties it all together against the facility context (HVAC, weather,
    pool performance, operator rules, previous days' deep dives).

    Output: structured daily deep dive report stored in knowledge.json
    under the key 'daily_deep_analyses'. Each entry is a dict with
    per-miner analyses and a fleet synthesis. The Sunday Claude weekly
    training reads this array alongside llm_scan_analyses via the
    TEMP_MAY_REMOVE merge block in train_cohort.py.

Design philosophy (per operator Bobby, April 9 2026):
    - No caps on anything. This is ROBS-PC sitting mostly idle, the
      compute is free, let Qwen chew on it as long as it needs.
    - num_predict = -1 (Ollama unlimited output)
    - num_ctx = 32768 (Qwen's full quantized context window)
    - requests timeout = 14400 seconds (4 hours) per LLM call
    - Sequential per-miner (48 miners @ ~2-4 min each = 90-180 min)
      then one fleet synthesis pass (~5-10 min)
    - Total expected runtime: 2-4 hours, fine because scheduled 4pm
      after daily collection finishes at 1pm

Scheduling:
    - TODAY (April 9 2026): MANUAL only — run via `python3 ai/daily_deep_dive.py --manual`
    - Starting April 10 2026: cron at 16:00 local (America/Chicago)
      cron entry: `0 16 * * * cd /root/Mining-Guardian && venv/bin/python3 ai/daily_deep_dive.py >> /tmp/daily_deep_dive.log 2>&1`

What this does NOT do:
    - It does NOT call Claude. Claude weekly training stays on its own
      Sunday 3am cron unchanged, and picks up these daily deep dives
      automatically via the TEMP_MAY_REMOVE merge block.
    - It does NOT collect logs. Daily log collection is a separate job
      (in core/mining_guardian.py's collect_logs function, running in
      a background thread from the hourly scan loop). This script
      ASSUMES daily collection has already run and fresh logs are in
      miner_logs with health_status='daily_baseline'.
    - It does NOT replace the per-scan Qwen analysis. That still runs
      every hour in local_llm_analyzer.py. This is the DEEP DIVE, not
      a replacement for the quick reactive analysis.

Safety/resume:
    - Each per-miner analysis is written to working dir as it completes
      so a mid-run crash doesn't lose hours of work.
    - Working dir: /root/Mining-Guardian/daily_deep_dive_wip/{YYYY-MM-DD}/
    - On restart, completed miners are skipped automatically.
"""

import argparse
import json
import logging
import os
import psycopg2
from psycopg2.extras import DictCursor
import sys
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Setup ────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
def _pg_dsn() -> str:
    """Build Postgres DSN from environment variables."""
    host = os.environ.get("GUARDIAN_PG_HOST", "localhost")
    port = os.environ.get("GUARDIAN_PG_PORT", "5432")
    dbname = os.environ.get("GUARDIAN_PG_DBNAME", "mining_guardian")
    user = os.environ.get("GUARDIAN_PG_USER", "guardian_app")
    password = os.environ.get("GUARDIAN_PG_PASSWORD", "")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


class _PgConnWrapper:
    """psycopg2 Connection wrapper with SQLite-style conn.execute shortcut.
    See core/overnight_automation.py for rationale (Phase 7.2).
    """

    def __init__(self, dsn: str):
        self._conn = psycopg2.connect(dsn, cursor_factory=DictCursor)

    def execute(self, sql, params=()):
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()
        return False


DB_PATH = _pg_dsn()
KNOWLEDGE_PATH = _ROOT / "knowledge.json"
CONFIG_PATH = _ROOT / "config.json"
WIP_ROOT = _ROOT / "daily_deep_dive_wip"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger("daily_deep_dive")

# Late import to avoid circular deps — catalog_context is optional
try:
    from ai.catalog_context import get_miner_catalog_context, get_catalog_context
except ImportError:
    def get_miner_catalog_context(model_name):
        return ""
    def get_catalog_context(miner_models, active_issues=None):
        return ""

# ── Qwen/Ollama settings — NO CAPS ───────────────────────────────────────
# Read llm_url from config.json, fall back to ROBS-PC tailscale
try:
    _cfg = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
except Exception:
    _cfg = {}
LLM_URL = _cfg.get("local_llm_url") or _cfg.get("ollama_url") or os.getenv("OLLAMA_URL", "http://100.110.87.1:11434")
# ollama_url in config points at /api/generate; strip it
if LLM_URL.endswith("/api/generate"):
    LLM_URL = LLM_URL[: -len("/api/generate")]
LLM_MODEL = _cfg.get("local_llm_model") or "qwen2.5:32b-instruct-q4_K_M"

NUM_CTX = 32768        # Qwen 2.5 32B quantized model's full context window
NUM_PREDICT = -1       # -1 = unlimited output tokens per Ollama
TEMPERATURE = 0.3      # low for factual analysis
OLLAMA_TIMEOUT_SEC = 14400  # 4 hours per call
MAX_PROMPT_CHARS = 45000   # Skip miners with prompts > 45K chars (~12K tokens)
                           # Prevents multi-hour analysis of miners with huge logs


# ── LLM call helper ──────────────────────────────────────────────────────

def query_qwen(prompt: str, label: str = "") -> Optional[str]:
    """Call Qwen 32B on ROBS-PC via Ollama /api/generate. No caps.

    Returns the response text, or None on hard failure after retries.
    Label is used only for logging clarity (e.g. 'miner 53487' or 'fleet synthesis').
    """
    api_url = f"{LLM_URL}/api/generate"
    payload = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": NUM_CTX,
            "num_predict": NUM_PREDICT,
            "temperature": TEMPERATURE,
        },
    }
    data = json.dumps(payload).encode()

    prompt_chars = len(prompt)
    logger.info("Qwen call [%s]: prompt=%d chars, ctx=%d, num_predict=%d, timeout=%ds",
                label, prompt_chars, NUM_CTX, NUM_PREDICT, OLLAMA_TIMEOUT_SEC)

    start = time.time()
    try:
        req = urllib.request.Request(
            api_url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT_SEC) as resp:
            body = resp.read().decode()
        d = json.loads(body)
    except urllib.error.HTTPError as he:
        logger.error("Qwen HTTP error [%s]: %s %s", label, he.code, he.reason)
        return None
    except urllib.error.URLError as ue:
        logger.error("Qwen connection error [%s]: %s", label, ue.reason)
        return None
    except Exception as e:
        logger.error("Qwen call failed [%s]: %s: %s", label, type(e).__name__, e)
        return None

    elapsed = time.time() - start
    response = d.get("response", "")
    prompt_tokens = d.get("prompt_eval_count", 0)
    output_tokens = d.get("eval_count", 0)
    eval_duration_ms = d.get("eval_duration", 0) // 1_000_000

    logger.info(
        "Qwen OK [%s]: %.1fs wall, prompt=%d tokens, output=%d tokens (%d chars), eval=%dms",
        label, elapsed, prompt_tokens, output_tokens, len(response), eval_duration_ms,
    )
    return response


def _get_anthropic_api_key() -> Optional[str]:
    """Get ANTHROPIC_API_KEY from env, falling back to .env file.

    Cron starts with a clean environment, so reading .env is required.
    Mirrors the pattern in ai/refinement_chain.py get_api_key().
    """
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    env_path = _ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def query_claude_for_fleet(prompt: str, label: str = "fleet synthesis") -> Optional[str]:
    """Call Claude API for fleet synthesis only (200K context, no truncation).

    Per-miner analyses run on Qwen (small prompts, fits in 32K easily).
    Fleet synthesis runs on Claude because the prompt is ~195K chars and Qwen
    truncates to 32K — we were losing ~50%% of premier per-miner data at the
    aggregation step.

    This is a temporary deviation from the local-LLM-only design principle.
    When the Mac Mini ships, fleet synthesis flips back to local Qwen plus
    a hierarchical (cohort -> fleet) chunking pass that fits in 32K.
    """
    api_key = _get_anthropic_api_key()
    if not api_key:
        logger.error('Claude API key not found in env or .env file — cannot run fleet synthesis')
        return None

    model = 'claude-sonnet-4-20250514'
    prompt_chars = len(prompt)
    logger.info(
        'Claude call [%s]: prompt=%d chars (estimated %d tokens), model=%s',
        label, prompt_chars, prompt_chars // 4, model,
    )

    start = time.time()
    try:
        body = json.dumps({
            'model': model,
            'max_tokens': 8192,  # synthesis output is typically 3-13K chars; 8192 tokens = ~32K chars
            'messages': [{'role': 'user', 'content': prompt}],
        }).encode()
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=body,
            method='POST',
            headers={
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'Content-Type': 'application/json',
            },
        )
        # Generous timeout: 195K-char prompts can take 60-120s to process
        with urllib.request.urlopen(req, timeout=300) as resp:
            data_bytes = resp.read()
        d = json.loads(data_bytes.decode())
    except urllib.error.HTTPError as he:
        body_preview = ''
        try:
            body_preview = he.read().decode()[:300]
        except Exception:
            pass
        logger.error('Claude HTTP error [%s]: %s %s body=%s', label, he.code, he.reason, body_preview)
        return None
    except urllib.error.URLError as ue:
        logger.error('Claude connection error [%s]: %s', label, ue.reason)
        return None
    except Exception as e:
        logger.error('Claude call failed [%s]: %s: %s', label, type(e).__name__, e)
        return None

    elapsed = time.time() - start
    text = ''
    for block in d.get('content', []):
        if isinstance(block, dict) and block.get('type') == 'text':
            text = block['text']
            break
    if not text:
        logger.error('Claude returned no text block [%s]: keys=%s', label, list(d.keys()))
        return None

    usage = d.get('usage', {})
    in_tok = usage.get('input_tokens', 0)
    out_tok = usage.get('output_tokens', 0)
    logger.info(
        'Claude OK [%s]: %.1fs wall, in=%d tok, out=%d tok (%d chars)',
        label, elapsed, in_tok, out_tok, len(text),
    )
    return text


# ── Data gathering ───────────────────────────────────────────────────────

def get_online_miners(conn: "_PgConnWrapper",
                       scan_id_override: Optional[int] = None) -> List[Dict]:
    """Return the online miner list from the latest scan, or from scan_id_override if given.

    Override is intended for manual recovery when the most recent scan had an
    AMS transient (all miners flagged offline). Pass a known-good scan ID and
    the deep dive will analyze that snapshot of the fleet instead.
    """
    if scan_id_override is not None:
        scan_id = scan_id_override
        logger.info("get_online_miners: using scan_id_override=%d", scan_id)
    else:
        latest = conn.execute(
            "SELECT id FROM scans ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not latest:
            return []
        scan_id = latest["id"]
    rows = conn.execute("""
        SELECT miner_id, ip, model, hashrate_pct, temp_chip, current_profile,
               status, action, uptime, temp_board, consumption
        FROM miner_readings
        WHERE scan_id = %s AND status = 'online'
        ORDER BY ip
    """, (scan_id,)).fetchall()
    return [dict(r) for r in rows]


def get_miner_daily_log(conn: "_PgConnWrapper", miner_id: str,
                         label: str = "daily_baseline") -> Optional[str]:
    """Get the most recent miner.log content for this miner (prefers today)."""
    # Look for any recent miner.log from last 12 hours first (today)
    row = conn.execute("""
        SELECT content, collected_at, health_status FROM miner_logs
        WHERE miner_id = %s
          AND log_file LIKE '%%miner.log'
          AND collected_at >= TO_CHAR(NOW() - INTERVAL '12 hours', 'YYYY-MM-DD"T"HH24:MI:SS.US')
        ORDER BY collected_at DESC LIMIT 1
    """, (miner_id,)).fetchone()
    if row:
        return row["content"]
    # Fallback to 36 hours if nothing in last 12
    row = conn.execute("""
        SELECT content, collected_at, health_status FROM miner_logs
        WHERE miner_id = %s
          AND log_file LIKE '%%miner.log'
          AND collected_at >= TO_CHAR(NOW() - INTERVAL '36 hours', 'YYYY-MM-DD"T"HH24:MI:SS.US')
        ORDER BY collected_at DESC LIMIT 1
    """, (miner_id,)).fetchone()
    if row:
        logger.info("Miner %s: using older log %s from %s",
                    miner_id, row["health_status"], row["collected_at"])
        return row["content"]
    return None


def get_miner_yesterday_log(conn: "_PgConnWrapper", miner_id: str) -> Optional[str]:
    """Get the most recent log from 24-72 hours ago for baseline comparison."""
    row = conn.execute("""
        SELECT content FROM miner_logs
        WHERE miner_id = %s
          AND log_file LIKE '%%miner.log'
          AND collected_at < TO_CHAR(NOW() - INTERVAL '24 hours', 'YYYY-MM-DD"T"HH24:MI:SS.US')
          AND collected_at >= TO_CHAR(NOW() - INTERVAL '72 hours', 'YYYY-MM-DD"T"HH24:MI:SS.US')
        ORDER BY collected_at DESC LIMIT 1
    """, (miner_id,)).fetchone()
    return row["content"] if row else None


def get_miner_24h_trends(conn: "_PgConnWrapper", miner_id: str) -> Dict:
    """Get 24-hour per-board trends and summary stats for a miner."""
    trends = {}

    # Chain readings (per-board) over 24h
    chains = conn.execute("""
        SELECT scanned_at, board_index, rate_mhs, temp_chip, temp_board,
               voltage, freq_mhz, hw_errors
        FROM chain_readings
        WHERE miner_id = %s AND scanned_at >= TO_CHAR(NOW() - INTERVAL '24 hours', 'YYYY-MM-DD"T"HH24:MI:SS.US')
        ORDER BY scanned_at ASC, board_index ASC
    """, (miner_id,)).fetchall()
    trends["chain_readings"] = [dict(r) for r in chains]

    # Hashrate percent trend from miner_readings
    readings = conn.execute("""
        SELECT scanned_at, hashrate_pct, temp_chip, temp_board, current_profile,
               consumption
        FROM miner_readings
        WHERE miner_id = %s AND scanned_at >= TO_CHAR(NOW() - INTERVAL '24 hours', 'YYYY-MM-DD"T"HH24:MI:SS.US')
        ORDER BY scanned_at ASC
    """, (miner_id,)).fetchall()
    trends["readings"] = [dict(r) for r in readings]

    # Restart outcomes in last 24h
    restarts = conn.execute("""
        SELECT restarted_at, restart_type, outcome, hashrate_before, hashrate_after,
               recovery_time_scans
        FROM miner_restarts
        WHERE miner_id = %s AND restarted_at >= TO_CHAR(NOW() - INTERVAL '24 hours', 'YYYY-MM-DD"T"HH24:MI:SS.US')
        ORDER BY restarted_at ASC
    """, (miner_id,)).fetchall()
    trends["restarts"] = [dict(r) for r in restarts]

    # Operator actions touching this miner in last 24h
    actions = conn.execute("""
        SELECT timestamp, action_taken, decision, approved_by, notes
        FROM action_audit_log
        WHERE miner_id = %s AND timestamp >= TO_CHAR(NOW() - INTERVAL '24 hours', 'YYYY-MM-DD"T"HH24:MI:SS.US')
        ORDER BY timestamp ASC
    """, (miner_id,)).fetchall()
    trends["operator_actions"] = [dict(r) for r in actions]

    # Pool readings in last 24h (accepted/rejected/stale shares)
    pools = conn.execute("""
        SELECT scanned_at, pool_url, accepted, rejected, accepted_diff, rejected_diff, status
        FROM pool_readings
        WHERE miner_id = %s AND scanned_at >= TO_CHAR(NOW() - INTERVAL '24 hours', 'YYYY-MM-DD"T"HH24:MI:SS.US')
        ORDER BY scanned_at ASC
    """, (miner_id,)).fetchall()
    trends["pool_readings"] = [dict(r) for r in pools]

    return trends


def get_miner_hardware(conn: "_PgConnWrapper", miner_id: str) -> Optional[Dict]:
    """Get the permanent hardware identity for this miner."""
    row = conn.execute("""
        SELECT * FROM miner_hardware WHERE miner_id = %s LIMIT 1
    """, (miner_id,)).fetchone()
    return dict(row) if row else None


def get_miner_fingerprint(knowledge: Dict, miner_id: str) -> Optional[Dict]:
    """Get the miner fingerprint from knowledge.json if present."""
    fingerprints = knowledge.get("miner_fingerprints", {})
    return fingerprints.get(miner_id) or fingerprints.get(str(miner_id))


def get_facility_24h(conn: "_PgConnWrapper") -> Dict:
    """Get 24-hour facility state: HVAC by system, weather, fleet-level stats."""
    facility = {}

    # Get HVAC data for both systems
    for system_id in ['warehouse', 's19jpro']:
        hvac = conn.execute("""
            SELECT recorded_at, supply_temp_f, return_temp_f, delta_t_f,
                   diff_pressure, spray_pump_on, cwp2_vfd_pct, ct1_vfd_pct, ct2_vfd_pct,
                   outside_air_f, container_temp_f
            FROM hvac_readings
            WHERE system_id = %s AND recorded_at >= TO_CHAR(NOW() - INTERVAL '24 hours', 'YYYY-MM-DD"T"HH24:MI:SS.US')
            ORDER BY recorded_at ASC
        """, (system_id,)).fetchall()
        facility[f"hvac_{system_id}"] = [dict(r) for r in hvac]
    
    # Keep backward compatibility - warehouse is default
    facility["hvac"] = facility.get("hvac_warehouse", [])

    weather = conn.execute("""
        SELECT recorded_at, temp_f, humidity_pct, feels_like_f,
               temp_high_f, temp_low_f
        FROM weather_readings
        WHERE recorded_at >= TO_CHAR(NOW() - INTERVAL '24 hours', 'YYYY-MM-DD"T"HH24:MI:SS.US')
        ORDER BY recorded_at ASC
    """).fetchall()
    facility["weather"] = [dict(r) for r in weather]

    scans = conn.execute("""
        SELECT id, scanned_at, total_miners, online, offline, issues
        FROM scans
        WHERE scanned_at >= TO_CHAR(NOW() - INTERVAL '24 hours', 'YYYY-MM-DD"T"HH24:MI:SS.US')
        ORDER BY scanned_at ASC
    """).fetchall()
    facility["scans"] = [dict(r) for r in scans]

    return facility


def get_operator_rules(knowledge: Dict) -> List[str]:
    """Get all operator rules from knowledge.json."""
    return knowledge.get("operator_rules", [])


def get_yesterday_deep_dive(knowledge: Dict) -> Optional[Dict]:
    """Get the most recent previous daily deep dive for continuity."""
    dd = knowledge.get("daily_deep_analyses", [])
    if dd:
        return dd[0] if isinstance(dd, list) and dd else None
    return None


# ── Prompt builders ──────────────────────────────────────────────────────

def compress_chain_trend(chains: List[Dict]) -> str:
    """Summarize per-board 24h chain readings into a compact text block.

    Instead of dumping every row, give per-board min/max/avg for the key
    metrics across the 24h window. Keeps the prompt scannable for Qwen.
    """
    if not chains:
        return "(no chain readings in last 24h)"

    by_board = {}
    for c in chains:
        bi = c.get("board_index", 0)
        by_board.setdefault(bi, []).append(c)

    lines = []
    for bi in sorted(by_board.keys()):
        rows = by_board[bi]
        hrs = [r.get("rate_mhs", 0) or 0 for r in rows]
        temps = [r.get("temp_chip", 0) or 0 for r in rows]
        volts = [r.get("voltage", 0) or 0 for r in rows]
        freqs = [r.get("freq_mhz", 0) or 0 for r in rows]
        hwerr = [r.get("hw_errors", 0) or 0 for r in rows]
        # chip_count not in schema; use board count as a proxy for presence
        chips = [1 for _ in rows]

        def mm(vals):
            if not vals:
                return "%s"
            return f"{min(vals):.0f}/{max(vals):.0f}/{sum(vals)/len(vals):.0f}"

        lines.append(
            f"  Board {bi}: HR={mm(hrs)} MH/s | temp={mm(temps)}°C | "
            f"V={mm(volts)} | freq={mm(freqs)} | HW errs={sum(hwerr)} total | "
            f"scans={len(rows)}"
        )
    return "\n".join(lines)


def compress_readings_trend(readings: List[Dict]) -> str:
    """Compact 24h hashrate % / temp trend summary."""
    if not readings:
        return "(no readings in last 24h)"
    hrs = [r.get("hashrate_pct", 0) or 0 for r in readings]
    temps = [r.get("temp_chip", 0) or 0 for r in readings]
    profiles = list({r.get("current_profile") for r in readings if r.get("current_profile")})
    return (
        f"  Hashrate %: min={min(hrs):.0f}% max={max(hrs):.0f}% avg={sum(hrs)/len(hrs):.0f}%\n"
        f"  Chip temp: min={min(temps):.0f}°C max={max(temps):.0f}°C avg={sum(temps)/len(temps):.0f}°C\n"
        f"  Profiles seen: {', '.join(profiles) if profiles else '(none)'}\n"
        f"  Scan count: {len(readings)}"
    )


def build_per_miner_prompt(
    miner: Dict,
    daily_log: Optional[str],
    yesterday_log: Optional[str],
    trends: Dict,
    hardware: Optional[Dict],
    fingerprint: Optional[Dict],
    operator_rules: List[str],
    facility: Optional[Dict] = None,
    catalog_context: str = "",
    past_analyses: Optional[List[Dict]] = None,
) -> str:
    """Build the Qwen prompt for a single miner's deep dive analysis."""
    lines = [
        "You are Mining Guardian's deep-dive fleet analyst running on ROBS-PC (RTX 4090).",
        "This is the DAILY DEEP DIVE — a long-running, comprehensive per-miner analysis.",
        "Take your time. Be thorough. Cite specific data points. No word count limit.",
        "",
        f"=== MINER {miner.get('miner_id')} ({miner.get('ip')}) — {miner.get('model') or 'unknown model'} ===",
        f"Current state: status={miner.get('status')} action={miner.get('action') or 'none'} "
        f"profile={miner.get('current_profile') or '%s'} uptime={miner.get('uptime') or '%s'}",
        "",
    ]

    # Hardware identity
    if hardware:
        lines.append("--- HARDWARE IDENTITY (permanent) ---")
        for k in ["serial_number", "firmware", "model_string", "mac_address",
                  "board_serials", "chip_bin", "pcb_version"]:
            v = hardware.get(k)
            if v:
                lines.append(f"  {k}: {v}")
        lines.append("")

    # Intelligence Catalog (manufacturer specs, known issues for this model)
    if catalog_context:
        lines.append("--- INTELLIGENCE CATALOG ---")
        lines.append(catalog_context)
        lines.append("")

    # Fingerprint from knowledge
    if fingerprint:
        lines.append("--- FINGERPRINT (learned over time) ---")
        for k, v in list(fingerprint.items())[:20]:
            lines.append(f"  {k}: {str(v)[:200]}")
        lines.append("")

    # 24h trends — compact
    chains = trends.get("chain_readings", [])
    if chains:
        lines.append("--- 24-HOUR PER-BOARD TRENDS (min/max/avg) ---")
        lines.append(compress_chain_trend(chains))
        lines.append("")

    readings = trends.get("readings", [])
    if readings:
        lines.append("--- 24-HOUR FLEET-LEVEL TRENDS ---")
        lines.append(compress_readings_trend(readings))
        lines.append("")

    # Restarts in last 24h
    restarts = trends.get("restarts", [])
    if restarts:
        lines.append(f"--- RESTARTS IN LAST 24H ({len(restarts)}) ---")
        for r in restarts:
            lines.append(
                f"  [{r.get('restarted_at', '%s')[:16]}] {r.get('restart_type') or '%s'} "
                f"outcome={r.get('outcome') or '%s'} "
                f"HR: {r.get('hashrate_before', '%s')}% → {r.get('hashrate_after', '%s')}%"
            )
            # miner_restarts has no notes column; recovery_time_scans captured above
        lines.append("")

    # Operator actions in last 24h
    actions = trends.get("operator_actions", [])
    if actions:
        lines.append(f"--- OPERATOR ACTIONS IN LAST 24H ({len(actions)}) ---")
        for a in actions:
            lines.append(
                f"  [{a.get('timestamp', '%s')[:16]}] {a.get('action_taken') or '%s'} "
                f"decision={a.get('decision') or '%s'} by={a.get('approved_by') or '%s'}"
            )
            if a.get("notes"):
                lines.append(f"    notes: {str(a['notes'])[:300]}")
        lines.append("")

    # Pool performance
    pools = trends.get("pool_readings", [])
    if pools:
        total_accepted = sum(p.get("accepted", 0) or 0 for p in pools)
        total_rejected = sum(p.get("rejected", 0) or 0 for p in pools)
        total_stale = sum(p.get("stale", 0) or 0 for p in pools)
        lines.append("--- 24-HOUR POOL PERFORMANCE ---")
        lines.append(
            f"  Accepted: {total_accepted} | Rejected: {total_rejected} | Stale: {total_stale}"
        )
        if total_accepted + total_rejected > 0:
            reject_pct = 100.0 * total_rejected / (total_accepted + total_rejected)
            lines.append(f"  Reject rate: {reject_pct:.2f}%")
        lines.append("")

    # Past LLM analyses for this miner (last 7 days)
    if past_analyses:
        lines.append("\n--- PAST AI ANALYSES (last 7 days) ---")
        lines.append("What AI previously said about this miner (do NOT repeat, focus on what changed):")
        for pa in past_analyses:
            ts = pa["analyzed_at"][:16] if pa["analyzed_at"] else "%s"
            model = pa["model_used"] or "%s"
            text = (pa["response"] or "")[:300]
            lines.append(f"  [{ts}] ({model}): {text}...")
        lines.append("")

    # Operator rules — compact (capped for prompt budget)
    if operator_rules:
        lines.append("--- OPERATOR RULES (KEY POINTS) ---")
        rules_chars = 0
        for rule in operator_rules:
            title = rule.split(chr(10))[0][:120]
            if rules_chars < 2000:
                lines.append(f"  • {title}")
                rules_chars += len(title)
        lines.append("")

    # Critical operator rules hardcoded as a reminder
    lines.extend([
        "--- CRITICAL OPERATOR RULES ---",
        "• TEMPERATURE: do not flag or warn about any chip temp BELOW 84°C. "
        "The fleet is liquid-cooled; 67-80°C is NORMAL. Only >=84°C warrants concern.",
        "• HVAC: the USA 188 HVAC is working correctly. Low supply/return delta-T "
        "is intentional and will rise with outside temp. Do NOT recommend checking HVAC "
        "based on low delta-T.",
        "• Bias toward documenting hardware patterns over environmental recommendations.",
        "",
    ])

    # Today's daily log (the main event)
    if daily_log:
        # Cap the log at 60KB to leave room for the rest of the prompt within
        # Qwen's 32K token context. 60KB of log text ~= 15-20K tokens.
        MAX_LOG_CHARS = 30_000  # Reduced - rules grew  # Reduced to fit prompt budget
        log_text = daily_log[:MAX_LOG_CHARS]
        lines.append(f"--- TODAY'S DAILY BASELINE LOG ({len(daily_log)} chars, showing first {len(log_text)}) ---")
        lines.append(log_text)
        lines.append("")
    else:
        lines.append("--- TODAY'S DAILY BASELINE LOG ---")
        lines.append("(not available — log collection may still be in progress or this miner was skipped)")
        lines.append("")

    # Yesterday's log excerpt for comparison
    if yesterday_log:
        MAX_YEST_CHARS = 20_000
        yest_text = yesterday_log[:MAX_YEST_CHARS]
        lines.append(f"--- YESTERDAY'S LOG EXCERPT ({len(yesterday_log)} chars, showing first {len(yest_text)}) ---")
        lines.append("Compare today's log against this baseline to detect firmware regressions,")
        lines.append("new error patterns, board count changes, voltage drift, etc.")
        lines.append(yest_text)
        lines.append("")
    else:
        lines.append("--- YESTERDAY'S LOG EXCERPT ---")
        lines.append("(no yesterday log on file — first-time baseline for this miner)")
        lines.append("")

    # The task
    lines.extend([
        "=== YOUR DEEP DIVE TASK ===",
        "",
        "Produce a thorough analysis of THIS miner covering:",
        "",
        "1. CURRENT STATE: Is this miner healthy, degraded, or failing%s What does the",
        "   current hashrate, temp, and profile tell you%s",
        "",
        "2. 24-HOUR STABILITY: Has performance been stable, trending down, spiking,",
        "   or flapping%s Cite specific board numbers and metrics from the trends above.",
        "",
        "3. LOG ANALYSIS (today vs yesterday): What changed between yesterday's log",
        "   and today's%s Any new errors, warnings, board detachments, voltage faults,",
        "   chip count changes, firmware messages, power events%s If today looks identical",
        "   to yesterday, say so — that's also valuable information.",
        "",
        "4. RESTART HISTORY (if any in last 24h): Did restarts fix the root cause or",
        "   just mask the symptom%s Was the 'after' state materially better than 'before'%s",
        "",
        "5. CROSS-CORRELATION: Is this miner's behavior consistent with neighboring",
        "   miners in the same cooling zone, same model, same firmware version%s Or is",
        "   it an outlier%s (You'll see the full fleet in the synthesis pass — for now",
        "   just note anything that looks distinctive about this one miner.)",
        "",
        "6. PREDICTION: Based on the 24h trend, what do you expect from this miner in",
        "   the next 24h%s Stable%s Degrading%s At risk of failure%s Needs physical attention%s",
        "",
        "7. RECOMMENDATION: What, if anything, should the operator do about this miner%s",
        "   If the answer is 'nothing, it's fine,' say that clearly — a no-action",
        "   analysis is just as valuable as a flagged one.",
        "",
        "Be specific. Cite board numbers, voltages, error codes, hashrate deltas. No",
        "fluff, no hedging for the sake of hedging. You are the expert analyst. Take",
        "as long as you need to do this well.",
    ])

    return "\n".join(lines)


def build_fleet_synthesis_prompt(
    per_miner_analyses: Dict[str, str],
    facility: Dict,
    operator_rules: List[str],
    yesterday_deep_dive: Optional[Dict],
    miners_online: int,
    miners_analyzed: int,
    catalog_context: str = "",
    fleet_analyses: Optional[List[Dict]] = None,
) -> str:
    """Build the final fleet-wide synthesis prompt."""
    lines = [
        "You are Mining Guardian's deep-dive fleet analyst.",
        "You have just finished reading individual per-miner analyses for every online",
        "miner in the fleet. Now produce the FLEET-WIDE SYNTHESIS for today.",
        "",
        f"Date: {datetime.now().strftime('%Y-%m-%d')}",
        f"Miners online: {miners_online}",
        f"Miners analyzed in per-miner pass: {miners_analyzed}",
        "",
    ]

    # Previous day's synthesis for continuity
    if yesterday_deep_dive and yesterday_deep_dive.get("fleet_synthesis"):
        prev_synth = yesterday_deep_dive.get("fleet_synthesis", "")[:4000]
        prev_date = yesterday_deep_dive.get("date", "%s")
        lines.append(f"--- PREVIOUS DAILY SYNTHESIS ({prev_date}) — for continuity ---")
        lines.append(prev_synth)
        lines.append("")

    # Intelligence Catalog fleet context (model specs for all fleet models)
    if catalog_context:
        lines.append("--- INTELLIGENCE CATALOG (fleet model specs) ---")
        lines.append(catalog_context)
        lines.append("")

    # Facility context - fleet synthesis always uses warehouse HVAC
    hvac = facility.get("hvac_warehouse", facility.get("hvac", []))
    system_label = "Warehouse"
    if hvac:
        supply = [h.get("supply_temp_f", 0) or 0 for h in hvac]
        retur = [h.get("return_temp_f", 0) or 0 for h in hvac]
        delta = [h.get("delta_t_f", 0) or 0 for h in hvac]
        lines.append(f"--- 24-HOUR HVAC TREND ({system_label}) ---")
        if system_label.lower() == "s19jpro":
            lines.append("  NOTE: S19J Pro CT fans are manually at 100% - no VFD feedback shown. This is intentional.")
        lines.append(
            f"  Supply: min={min(supply):.1f}°F max={max(supply):.1f}°F avg={sum(supply)/len(supply):.1f}°F"
        )
        lines.append(
            f"  Return: min={min(retur):.1f}°F max={max(retur):.1f}°F avg={sum(retur)/len(retur):.1f}°F"
        )
        lines.append(
            f"  Delta-T: min={min(delta):.1f}°F max={max(delta):.1f}°F avg={sum(delta)/len(delta):.1f}°F"
        )
        lines.append(
            f"  Reading count: {len(hvac)}"
        )
        lines.append(
            "  NOTE: HVAC is performing correctly. Low delta-T is intentional (seasonal)."
        )
        lines.append("")

    weather = facility.get("weather", [])
    if weather:
        temps = [w.get("temp_f", 0) or 0 for w in weather]
        humid = [w.get("humidity_pct", 0) or 0 for w in weather]
        lines.append("--- 24-HOUR WEATHER TREND (Fort Worth) ---")
        lines.append(
            f"  Temp: min={min(temps):.0f}°F max={max(temps):.0f}°F avg={sum(temps)/len(temps):.0f}°F"
        )
        lines.append(
            f"  Humidity: {min(humid):.0f}%-{max(humid):.0f}%"
        )
        lines.append("")

    scans = facility.get("scans", [])
    if scans:
        avg_online = sum(s.get("online", 0) or 0 for s in scans) / len(scans)
        avg_offline = sum(s.get("offline", 0) or 0 for s in scans) / len(scans)
        total_issues = sum(s.get("issues", 0) or 0 for s in scans)
        lines.append("--- 24-HOUR FLEET-LEVEL STATS ---")
        lines.append(f"  Scans: {len(scans)} | avg online: {avg_online:.1f} | avg offline: {avg_offline:.1f}")
        lines.append(f"  Total issues flagged across day: {total_issues}")
        lines.append("")

    # Fleet-wide LLM analysis summary (last 7 days)
    if fleet_analyses:
        lines.append("\n--- AI ANALYSIS ACTIVITY (last 7 days) ---")
        for fa in fleet_analyses:
            lines.append(f"  {fa['day']}: {fa['cnt']} analyses across {fa['miners_analyzed']} miners")
        lines.append("")

    # Operator rules
    if operator_rules:
        lines.append("--- OPERATOR RULES (MUST FOLLOW) ---")
        for rule in operator_rules:
            lines.append(f"  • {rule}")
        lines.append("")

    lines.extend([
        "--- CRITICAL OPERATOR RULES (reminder) ---",
        "• TEMPERATURE: chip temps below 84°C are NORMAL — do not flag or warn.",
        "• HVAC: performing correctly, do not recommend checking it based on low delta-T.",
        "• Bias toward hardware patterns, not environmental changes.",
        "",
    ])

    # Per-miner analyses — compact so they fit in 32K context
    lines.append(f"=== PER-MINER ANALYSES ({len(per_miner_analyses)}) ===")
    lines.append("Below are the individual deep-dive analyses from the per-miner pass.")
    lines.append("Synthesize these into fleet-wide patterns. Look for:")
    lines.append("  • Cohort-level issues (same model, same firmware, same cooling zone)")
    lines.append("  • Outliers worth operator attention")
    lines.append("  • Trends that appear across multiple miners")
    lines.append("  • New patterns that were NOT in yesterday's synthesis")
    lines.append("")

    for mid in sorted(per_miner_analyses.keys()):
        analysis = per_miner_analyses[mid]
        # Cap each per-miner summary to keep fleet prompt within context
        MAX_PER_MINER_CHARS = 2000
        excerpt = analysis[:MAX_PER_MINER_CHARS]
        lines.append(f"--- miner {mid} ---")
        lines.append(excerpt)
        lines.append("")

    lines.extend([
        "=== YOUR FLEET SYNTHESIS TASK ===",
        "",
        "Produce a structured fleet-wide report covering:",
        "",
        "1. EXECUTIVE SUMMARY (3-5 sentences): What is the headline of today%s What",
        "   single thing should the operator know first thing tomorrow morning%s",
        "",
        "2. FLEET HEALTH: Overall fleet state. How many miners are genuinely healthy%s",
        "   How many have mild concerns%s How many need real attention%s",
        "",
        "3. COHORT PATTERNS: Group findings by model / firmware / cooling zone.",
        "   Are the S19JPros behaving as a group%s Are the S21 EXP Hydros%s The",
        "   Auradine AH3880s%s Any model-wide issues%s",
        "",
        "4. OUTLIERS: Which miners stand out (positively or negatively) from their",
        "   cohort%s Cite specific miners by ID and explain why.",
        "",
        "5. DAY-OVER-DAY CHANGES: Comparing to yesterday's synthesis above, what is",
        "   materially different today%s New issues%s Resolved issues%s Drift%s",
        "",
        "6. ENVIRONMENTAL CORRELATION: Does the day's performance track with HVAC",
        "   or weather%s (Remember: HVAC is fine — only call this out if there's a",
        "   REAL correlation worth noting, not a default assumption.)",
        "",
        "7. OPERATOR LEARNING: What rules has the operator been reinforcing today",
        "   via denials, approvals, or manual actions%s What should the system learn%s",
        "",
        "8. TOMORROW'S FOCUS: Specific things to watch tomorrow. Which miners",
        "   should get extra attention%s Which patterns need confirmation%s",
        "",
        "9. RECOMMENDATIONS: Concrete actions the operator should take, ranked by",
        "   priority. If there's nothing to do, say that clearly.",
        "",
        "Take as long as you need. Be specific and cite miners by ID. This report",
        "will be read by Claude in the Sunday weekly training alongside the raw scan",
        "analyses and restart comparisons, so make it rich enough to be a fair",
        "summary of the day that Claude can build on.",
    ])

    return "\n".join(lines)


# ── Main orchestration ──────────────────────────────────────────────────

def run_daily_deep_dive(dry_run: bool = False, manual: bool = False, scan_id_override: Optional[int] = None) -> int:
    """Main entry point. Returns exit code (0 = success, nonzero = failure)."""
    start_time = time.time()
    today = datetime.now().strftime("%Y-%m-%d")
    logger.info("=" * 70)
    logger.info("DAILY DEEP DIVE starting — date=%s manual=%s dry_run=%s",
                today, manual, dry_run)
    logger.info("=" * 70)

    # Load knowledge
    knowledge = {}
    if KNOWLEDGE_PATH.exists():
        try:
            knowledge = json.loads(KNOWLEDGE_PATH.read_text())
        except Exception as e:
            logger.error("Could not load knowledge.json: %s", e)
            return 2

    operator_rules = get_operator_rules(knowledge)
    yesterday_dd = get_yesterday_deep_dive(knowledge)
    logger.info("Loaded %d operator rules; yesterday's deep dive: %s",
                len(operator_rules),
                yesterday_dd.get("date", "none") if yesterday_dd else "none")

    # Set up working directory for resume safety
    wip_dir = WIP_ROOT / today
    wip_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Working directory: %s", wip_dir)

    # Load list of already-completed miners (for resume)
    completed_files = list(wip_dir.glob("miner_*.json"))
    completed_ids = {f.stem.replace("miner_", "") for f in completed_files}
    if completed_ids:
        logger.info("Resume: %d miner analyses already completed in working dir",
                    len(completed_ids))

    # Connect to DB and get the online fleet
    conn = _PgConnWrapper(DB_PATH)
    online_miners = get_online_miners(conn, scan_id_override=scan_id_override)
    if scan_id_override is not None:
        logger.info("Online miners in scan %d (override): %d",
                    scan_id_override, len(online_miners))
    else:
        logger.info("Online miners in latest scan: %d", len(online_miners))

    if not online_miners:
        logger.error("No online miners found in latest scan — cannot run deep dive")
        conn.close()
        return 3

    if dry_run:
        logger.info("DRY RUN: would analyze %d miners", len(online_miners))
        for m in online_miners[:5]:
            logger.info("  %s (%s) %s", m.get("miner_id"), m.get("ip"), m.get("model"))
        if len(online_miners) > 5:
            logger.info("  ... and %d more", len(online_miners) - 5)
        conn.close()
        return 0

    # Get facility context once (used by fleet synthesis only)
    facility = get_facility_24h(conn)

    # Pre-fetch catalog context per unique model (cache handles dedup)
    model_catalog_cache = {}
    try:
        unique_models = list({m.get("model", "") for m in online_miners if m.get("model")})
        for mdl in unique_models:
            model_catalog_cache[mdl] = get_miner_catalog_context(mdl)
        logger.info("Catalog context fetched for %d unique models", len(unique_models))
    except Exception as e:
        logger.warning("Catalog pre-fetch failed (continuing without): %s", e)

    # Fleet-wide catalog context for synthesis pass
    fleet_catalog_context = ""
    try:
        all_models = list({m.get("model", "") for m in online_miners if m.get("model")})
        if all_models:
            fleet_catalog_context = get_catalog_context(all_models)
    except Exception as e:
        logger.warning("Fleet catalog context failed (continuing without): %s", e)

    # Per-miner pass
    per_miner_analyses = {}
    per_miner_failures = []
    for idx, miner in enumerate(online_miners, 1):
        mid = str(miner.get("miner_id", ""))
        if not mid:
            continue

        # Resume check
        if mid in completed_ids:
            wip_file = wip_dir / f"miner_{mid}.json"
            try:
                prev = json.loads(wip_file.read_text())
                per_miner_analyses[mid] = prev.get("analysis", "")
                logger.info("[%d/%d] miner %s: using cached analysis from %s",
                            idx, len(online_miners), mid, prev.get("timestamp", "%s"))
                continue
            except Exception:
                pass  # fall through and re-analyze

        logger.info("[%d/%d] miner %s (%s) %s — gathering data...",
                    idx, len(online_miners), mid, miner.get("ip"), miner.get("model"))

        daily_log = get_miner_daily_log(conn, mid)
        # REMOVED: yesterday log not needed - 1PM cron provides todays logs
        yesterday_log = None  # Always None now
        trends = get_miner_24h_trends(conn, mid)
        hardware = get_miner_hardware(conn, mid)
        fingerprint = get_miner_fingerprint(knowledge, mid)

        # Past LLM analyses for this miner (last 7 days)
        miner_ip = miner.get("ip", "")
        try:
            past_analyses = conn.execute("""
                SELECT analyzed_at, response, model_used
                FROM llm_analysis
                WHERE (miner_id=%s OR ip=%s)
                  AND analyzed_at >= TO_CHAR(NOW() - INTERVAL '7 days', 'YYYY-MM-DD"T"HH24:MI:SS.US')
                  AND response IS NOT NULL AND response != ''
                ORDER BY analyzed_at DESC LIMIT 3
            """, (mid, miner_ip)).fetchall()
            past_analyses = [dict(r) for r in past_analyses]
        except Exception:
            past_analyses = []

        miner_cat_ctx = model_catalog_cache.get(miner.get("model", ""), "")
        prompt = build_per_miner_prompt(
            miner=miner,
            daily_log=daily_log,
            yesterday_log=yesterday_log,
            trends=trends,
            hardware=hardware,
            fingerprint=fingerprint,
            operator_rules=operator_rules,
            facility=facility,
            catalog_context=miner_cat_ctx,
            past_analyses=past_analyses,
        )

        # Skip miners with prompts too large (would take hours)
        if len(prompt) > MAX_PROMPT_CHARS:
            logger.warning("[%d/%d] miner %s: SKIPPED — prompt too large (%d chars > %d max)",
                          idx, len(online_miners), mid, len(prompt), MAX_PROMPT_CHARS)
            # Write skip marker for resume
            wip_file = wip_dir / f"miner_{mid}.json"
            wip_file.write_text(json.dumps({
                "miner_id": mid,
                "ip": miner.get("ip"),
                "model": miner.get("model"),
                "timestamp": datetime.now().isoformat(),
                "prompt_chars": len(prompt),
                "skipped": True,
                "skip_reason": f"prompt too large: {len(prompt)} chars",
            }, indent=2))
            continue

        analysis = query_qwen(prompt, label=f"miner {mid} ({idx}/{len(online_miners)})")
        if not analysis:
            logger.warning("[%d/%d] miner %s: Qwen returned no analysis", idx, len(online_miners), mid)
            per_miner_failures.append(mid)
            continue

        per_miner_analyses[mid] = analysis

        # Persist immediately for resume safety
        wip_file = wip_dir / f"miner_{mid}.json"
        wip_file.write_text(json.dumps({
            "miner_id": mid,
            "ip": miner.get("ip"),
            "model": miner.get("model"),
            "timestamp": datetime.now().isoformat(),
            "prompt_chars": len(prompt),
            "analysis": analysis,
        }, indent=2))

    logger.info("Per-miner pass complete: %d analyzed, %d failed",
                len(per_miner_analyses), len(per_miner_failures))

    if not per_miner_analyses:
        logger.error("Per-miner pass produced no analyses — aborting fleet synthesis")
        conn.close()
        return 4

    # Fleet synthesis pass
    logger.info("Starting FLEET SYNTHESIS pass...")

    # Fleet-wide LLM analysis summary (last 7 days)
    try:
        fleet_analyses = conn.execute("""
            SELECT DATE(analyzed_at) as day, COUNT(*) as cnt,
                   COUNT(DISTINCT miner_id) as miners_analyzed
            FROM llm_analysis
            WHERE analyzed_at >= TO_CHAR(NOW() - INTERVAL '7 days', 'YYYY-MM-DD"T"HH24:MI:SS.US')
              AND response IS NOT NULL AND response != ''
            GROUP BY DATE(analyzed_at)
            ORDER BY day DESC
        """).fetchall()
        fleet_analyses = [dict(r) for r in fleet_analyses]
    except Exception:
        fleet_analyses = []

    fleet_prompt = build_fleet_synthesis_prompt(
        per_miner_analyses=per_miner_analyses,
        facility=facility,
        operator_rules=operator_rules,
        yesterday_deep_dive=yesterday_dd,
        miners_online=len(online_miners),
        miners_analyzed=len(per_miner_analyses),
        catalog_context=fleet_catalog_context,
        fleet_analyses=fleet_analyses,
    )

    # FLEET SYNTHESIS uses Claude (200K context) instead of Qwen (32K) until Mac Mini arrives.
    # See query_claude_for_fleet() docstring for details. Per-miner pass above keeps using Qwen.
    fleet_synthesis = query_claude_for_fleet(fleet_prompt, label="fleet synthesis")
    if not fleet_synthesis:
        logger.error("Fleet synthesis returned no result")
        conn.close()
        return 5

    # Persist fleet synthesis
    fleet_file = wip_dir / "fleet_synthesis.json"
    fleet_file.write_text(json.dumps({
        "date": today,
        "timestamp": datetime.now().isoformat(),
        "prompt_chars": len(fleet_prompt),
        "synthesis": fleet_synthesis,
        "miners_analyzed": len(per_miner_analyses),
        "miners_failed": per_miner_failures,
    }, indent=2))

    # Write to knowledge.json under daily_deep_analyses
    conn.close()
    _save_to_knowledge(today, per_miner_analyses, fleet_synthesis,
                        per_miner_failures, len(online_miners), start_time)

    elapsed_total = time.time() - start_time
    logger.info("=" * 70)
    logger.info("DAILY DEEP DIVE complete — total wall time: %.1f minutes",
                elapsed_total / 60)
    logger.info("  Per-miner analyses: %d", len(per_miner_analyses))
    logger.info("  Per-miner failures: %d", len(per_miner_failures))
    logger.info("  Fleet synthesis: %d chars", len(fleet_synthesis))
    logger.info("=" * 70)

    return 0


def _save_to_knowledge(date: str, per_miner: Dict[str, str], fleet_synth: str,
                        failures: List[str], miners_online: int,
                        start_time: float):
    """Append today's deep dive to knowledge.json under daily_deep_analyses."""
    knowledge = {}
    if KNOWLEDGE_PATH.exists():
        try:
            knowledge = json.loads(KNOWLEDGE_PATH.read_text())
        except Exception:
            pass

    if not isinstance(knowledge.get("daily_deep_analyses"), list):
        knowledge["daily_deep_analyses"] = []

    # Dedup: remove any existing entry for the same date (in case of re-run)
    knowledge["daily_deep_analyses"] = [
        e for e in knowledge["daily_deep_analyses"]
        if e.get("date") != date
    ]

    entry = {
        "date": date,
        "timestamp": datetime.now().isoformat(),
        "wall_time_seconds": int(time.time() - start_time),
        "miners_online": miners_online,
        "miners_analyzed": len(per_miner),
        "miners_failed": failures,
        "per_miner": per_miner,
        "fleet_synthesis": fleet_synth,
        "source": "qwen_daily_deep_dive",
    }

    # Keep last 30 days of deep dives
    knowledge["daily_deep_analyses"] = [entry] + knowledge["daily_deep_analyses"][:29]
    knowledge["last_updated"] = datetime.now().isoformat()

    KNOWLEDGE_PATH.write_text(json.dumps(knowledge, indent=2))
    logger.info("Saved deep dive to knowledge.json under daily_deep_analyses[0]")


def main():
    parser = argparse.ArgumentParser(description="Mining Guardian Daily Deep Dive LLM Analysis")
    parser.add_argument("--manual", action="store_true",
                        help="Manual run (identical behavior to scheduled, just logs it)")
    parser.add_argument("--dry-run", action="store_true",
                        help="List what would be analyzed without calling Qwen")
    parser.add_argument("--scan-id", type=int, default=None,
                        help="Override: use this specific scan ID for the online fleet "
                             "snapshot instead of the latest scan. Useful when the latest "
                             "scan had an AMS transient (all miners flagged offline).")
    args = parser.parse_args()

    try:
        code = run_daily_deep_dive(dry_run=args.dry_run, manual=args.manual,
                                    scan_id_override=args.scan_id)
        sys.exit(code)
    except KeyboardInterrupt:
        logger.error("Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error("Fatal error: %s", e)
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
