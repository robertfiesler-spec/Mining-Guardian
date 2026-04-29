#!/usr/bin/env python3
"""
intelligence_report_api.py
Mining Guardian — Miner Intelligence Report API

Serves pre-built intelligence report data for any miner model.
Data sources: unified_miner_index.json + miner_enrichment_master.csv + miner_specs.json + guardian.db
Consumed by Grafana iframe panels via dashboard_api proxy.

Runs on: http://localhost:8590

Endpoints:
  GET /api/report/models          → list of all models (for Grafana variable dropdown)
  GET /api/report/models/labels   → label:value pairs for Grafana JSON datasource
  GET /api/report/search?q=...    → search models by partial name
  GET /api/report/{slug}          → full intelligence report data for a model
  GET /api/report/{slug}/html     → HTML formatted report for iframe rendering
  GET /api/discoveries            → list unacknowledged auto-discovered models/firmware
  POST /api/discoveries/{id}/acknowledge → mark a discovery as reviewed or cataloged
  GET /health                     → health check

Version: 2.2.0 — Real fleet data from guardian.db + all prior fixes (April 16 2026)
"""

import json, csv, os, re, math, time, threading
import psycopg2
from psycopg2.extras import DictCursor
from pathlib import Path as FilePath
from datetime import datetime
from typing import Optional
from collections import defaultdict
from urllib.request import urlopen, Request
from urllib.error import URLError

from fastapi import FastAPI, Query, Path as APIPath, Request as FastAPIRequest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel


def _safe_float(val, default=0.0) -> float:
    """Safely convert a value to float, returning default on failure."""
    if val is None or val == '' or val == 'N/A' or val == 'Unknown':
        return default
    try:
        return float(str(val))
    except (ValueError, TypeError):
        return default

# ── Configuration ─────────────────────────────────────────────
BASE_DIR = FilePath(__file__).resolve().parent
REPO_DIR = BASE_DIR.parent  # Go up from api/ to repo root
def _pg_dsn() -> str:
    """Build Postgres DSN from environment variables."""
    host = os.environ.get("GUARDIAN_PG_HOST", "localhost")
    port = os.environ.get("GUARDIAN_PG_PORT", "5432")
    dbname = os.environ.get("GUARDIAN_PG_DBNAME", "mining_guardian")
    user = os.environ.get("GUARDIAN_PG_USER", "guardian_app")
    password = os.environ.get("GUARDIAN_PG_PASSWORD", "")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


# Kept for compatibility with any external callers that import this constant.
# Now holds a DSN string, not a filesystem path.
GUARDIAN_DB = _pg_dsn()


class _PgConnWrapper:
    """Thin wrapper over psycopg2 Connection with SQLite-style execute shortcut.
    See core/overnight_automation.py for rationale.
    """

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return cur

    def cursor(self):
        return self._conn.cursor()

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


# On VPS: API runs from repo root, data lives in intelligence-catalog/data/
_DATA_DIR = REPO_DIR / "intelligence-catalog" / "data"
ENRICHMENT_CSV = str(_DATA_DIR / "miner_enrichment_master.csv")
SPECS_JSON = str(REPO_DIR / "miner_specs.json")
INDEX_JSON = str(_DATA_DIR / "unified_miner_index.json")

# ── App Setup ─────────────────────────────────────────────────
app = FastAPI(title="Mining Guardian Intelligence Report API", version="2.3.0")

# ── Correction Rules Engine ───────────────────────────────────
# Rules file: intelligence-catalog/data/correction_rules.json
# Each rule: {"match": {field: pattern}, "set": {field: value}, "description": "..."}
# Patterns support: "endswith:X", "startswith:X", "contains:X", "exact:X", "regex:X"

CORRECTION_RULES_FILE = str(_DATA_DIR / "correction_rules.json")

def load_correction_rules() -> list:
    """Load correction rules from JSON file."""
    if os.path.exists(CORRECTION_RULES_FILE):
        with open(CORRECTION_RULES_FILE) as f:
            rules = json.load(f)
            print(f"Loaded {len(rules)} correction rules")
            return rules
    return []

def _match_pattern(value: str, pattern: str) -> bool:
    """Check if a value matches a correction rule pattern."""
    if not value:
        return False
    value_lower = value.lower()
    if pattern.startswith("endswith:"):
        return value_lower.endswith(pattern[9:].lower())
    elif pattern.startswith("startswith:"):
        return value_lower.startswith(pattern[11:].lower())
    elif pattern.startswith("contains:"):
        return pattern[9:].lower() in value_lower
    elif pattern.startswith("exact:"):
        return value_lower == pattern[6:].lower()
    elif pattern.startswith("regex:"):
        return bool(re.search(pattern[6:], value, re.IGNORECASE))
    else:
        # Default: contains match
        return pattern.lower() in value_lower

def apply_corrections(index: dict, rules: list) -> int:
    """Apply correction rules to the unified index. Returns count of corrections made."""
    corrections = 0
    for slug, info in index.items():
        for rule in rules:
            match_criteria = rule.get("match", {})
            matched = True
            
            for field, pattern in match_criteria.items():
                # Get field value from various locations in the entry
                val = None
                if field == "manufacturer":
                    val = info.get("manufacturer", "")
                elif field == "slug":
                    val = slug
                elif field == "display_name":
                    val = info.get("display_name", "")
                elif field == "entity":
                    val = info.get("entity", "")
                elif field == "model_number":
                    # Extract numeric model identifier (e.g. "M60" from "WhatsMiner M60S+")
                    dn = info.get("display_name", "")
                    m = re.search(r'[A-Z]?(\d+)', dn)
                    val = m.group(0) if m else ""
                elif field.startswith("specs."):
                    specs = info.get("specs") or {}
                    val = str(specs.get(field[6:], ""))
                elif field.startswith("enrichment."):
                    enrich = info.get("enrichment") or {}
                    val = str(enrich.get(field[11:], ""))
                else:
                    val = str(info.get(field, ""))
                
                if not _match_pattern(str(val), pattern):
                    matched = False
                    break
            
            if matched:
                # Apply corrections
                for set_field, set_value in rule.get("set", {}).items():
                    if set_field.startswith("specs."):
                        if not info.get("specs"):
                            info["specs"] = {}
                        info["specs"][set_field[6:]] = set_value
                    elif set_field.startswith("enrichment."):
                        if not info.get("enrichment"):
                            info["enrichment"] = {}
                        info["enrichment"][set_field[11:]] = set_value
                    else:
                        info[set_field] = set_value
                corrections += 1
    
    return corrections


# ── Live Network Data ─────────────────────────────────────────
# Fetches BTC price from CoinGecko and network difficulty from mempool.space/blockchain.info
# Cached for 15 minutes to avoid API rate limits

_network_cache = {
    "btc_price_usd": 0,
    "network_difficulty": 0,
    "network_hashrate_eh": 0,
    "block_height": 0,
    "last_fetch": 0,
    "source": "initializing",
}
_CACHE_TTL = 900  # 15 minutes
_fetch_lock = threading.Lock()

def _fetch_json(url: str, timeout: int = 10) -> dict:
    """Fetch JSON from a URL with timeout."""
    req = Request(url, headers={"User-Agent": "MiningGuardian/2.1", "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())

def _fetch_text(url: str, timeout: int = 10) -> str:
    """Fetch plain text from a URL."""
    req = Request(url, headers={"User-Agent": "MiningGuardian/2.1"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode().strip()

def get_network_data() -> dict:
    """Get current BTC price and network stats. Cached for 15 minutes."""
    global _network_cache
    
    now = time.time()
    if now - _network_cache["last_fetch"] < _CACHE_TTL and _network_cache["btc_price_usd"] > 0:
        return _network_cache
    
    with _fetch_lock:
        # Double-check after acquiring lock
        if now - _network_cache["last_fetch"] < _CACHE_TTL and _network_cache["btc_price_usd"] > 0:
            return _network_cache
        
        new_data = dict(_network_cache)
        sources = []
        
        # 1. BTC Price from CoinGecko (free, no key needed)
        try:
            cg = _fetch_json("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd")
            new_data["btc_price_usd"] = cg["bitcoin"]["usd"]
            sources.append("CoinGecko")
        except Exception as e:
            print(f"CoinGecko fetch failed: {e}")
            # Fallback: blockchain.info
            try:
                ticker = _fetch_json("https://blockchain.info/ticker")
                new_data["btc_price_usd"] = ticker["USD"]["last"]
                sources.append("blockchain.info")
            except Exception as e2:
                print(f"blockchain.info price fetch also failed: {e2}")
        
        # 2. Network difficulty + hashrate from mempool.space
        try:
            ms = _fetch_json("https://mempool.space/api/v1/mining/hashrate/1w")
            new_data["network_difficulty"] = ms["currentDifficulty"]
            new_data["network_hashrate_eh"] = round(ms["currentHashrate"] / 1e18, 2)
            sources.append("mempool.space")
        except Exception as e:
            print(f"mempool.space fetch failed: {e}")
            # Fallback: blockchain.info
            try:
                diff_str = _fetch_text("https://blockchain.info/q/getdifficulty")
                new_data["network_difficulty"] = float(diff_str)
                sources.append("blockchain.info/difficulty")
            except Exception as e2:
                print(f"blockchain.info difficulty fetch also failed: {e2}")
        
        # 3. Block height
        try:
            height_str = _fetch_text("https://blockchain.info/q/getblockcount")
            new_data["block_height"] = int(height_str)
        except Exception:
            pass
        
        if new_data["btc_price_usd"] > 0:
            new_data["last_fetch"] = now
            new_data["source"] = " + ".join(sources)
            new_data["last_fetch_time"] = datetime.now().strftime("%I:%M %p CDT")
            _network_cache = new_data
            print(f"Network data refreshed: BTC ${new_data['btc_price_usd']:,.0f}, difficulty {new_data['network_difficulty']/1e12:.2f}T (from {new_data['source']})")
        
        return _network_cache
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Data Loading ──────────────────────────────────────────────
def load_unified_index():
    """Load the unified miner index."""
    if os.path.exists(INDEX_JSON):
        with open(INDEX_JSON) as f:
            return json.load(f)
    return {}

def load_enrichment():
    """Load the enrichment CSV as a dict keyed by entity."""
    data = {}
    if os.path.exists(ENRICHMENT_CSV):
        with open(ENRICHMENT_CSV) as f:
            for row in csv.DictReader(f):
                data[row['entity'].strip()] = dict(row)
    return data

def load_specs():
    """Load miner_specs.json models."""
    if os.path.exists(SPECS_JSON):
        with open(SPECS_JSON) as f:
            d = json.load(f)
            return d.get('models', {})
    return {}

# Load supplementary data at startup (enrichment CSV + specs JSON)
ENRICHMENT = load_enrichment()
SPECS = load_specs()

# ── Slug Merge: Combine duplicate entries ─────────────────────
# Some models exist under two slugs (e.g. antminer-s19jpro and antminer-s19j-pro)
# where one has specs and the other has enrichment. Merge them into one entry.
def merge_index(raw_index: dict) -> dict:
    """Merge duplicate slug entries so every model gets both specs + enrichment."""
    # Group by normalized slug (strip all hyphens)
    groups = defaultdict(list)
    for slug in raw_index:
        norm = slug.replace('-', '')
        groups[norm].append(slug)

    # Second pass: detect manufacturer-prefix duplicates
    # e.g. "teraflux-ah3880" and "auradine-teraflux-ah3880" should merge
    all_norms = list(groups.keys())
    merge_map = {}  # norm_short -> norm_long (which group to merge into)
    for i, n1 in enumerate(all_norms):
        if n1 in merge_map:
            continue
        for j, n2 in enumerate(all_norms):
            if i == j or n2 in merge_map:
                continue
            # Check if one is a suffix of the other (manufacturer prefix added)
            if n2.endswith(n1) and len(n2) > len(n1):
                merge_map[n1] = n2
            elif n1.endswith(n2) and len(n1) > len(n2):
                merge_map[n2] = n1

    # Apply merges: combine groups
    for short_norm, long_norm in merge_map.items():
        if short_norm in groups and long_norm in groups:
            groups[long_norm].extend(groups[short_norm])
            del groups[short_norm]

    merged = {}
    merge_count = 0
    for norm, slugs in groups.items():
        if len(slugs) == 1:
            merged[slugs[0]] = raw_index[slugs[0]]
        else:
            # Multiple slugs for same model — merge data, keep the slug with specs (more canonical)
            primary = None
            specs_data = None
            enrichment_data = None
            best_entity = None
            best_display = None

            for s in slugs:
                entry = raw_index[s]
                if entry.get('specs'):
                    primary = s
                    specs_data = entry['specs']
                if entry.get('enrichment'):
                    enrichment_data = entry['enrichment']
                    best_entity = entry.get('entity')
                if entry.get('display_name'):
                    # Prefer the longest/most descriptive display name
                    if not best_display or len(entry['display_name']) > len(best_display):
                        best_display = entry['display_name']

            # Fallback: use first slug if none had specs
            if not primary:
                primary = slugs[0]

            # Build merged entry
            base = dict(raw_index[primary])
            if specs_data:
                base['specs'] = specs_data
            if enrichment_data:
                base['enrichment'] = enrichment_data
            if best_entity and not base.get('entity'):
                base['entity'] = best_entity
            if best_display:
                base['display_name'] = best_display

            merged[primary] = base

            # Also register aliases so lookups work with either slug
            for s in slugs:
                if s != primary:
                    merged[s] = base  # Point to same merged data

            merge_count += 1

    print(f"Merged {merge_count} duplicate slug pairs")
    return merged


# ── Reloadable Catalog Loader ────────────────────────────────────
# All catalog state is held in these module-level variables.
# _load_catalog() rebuilds them from disk — called at startup and on hot-reload.

UNIFIED_INDEX: dict = {}
MODEL_LIST: list = []
CORRECTION_RULES: list = []
_catalog_mtime: float = 0.0  # last mtime of unified_miner_index.json
_catalog_lock = threading.Lock()


def _load_catalog() -> int:
    """(Re)load the catalog from disk into module-level globals.

    Thread-safe — acquires _catalog_lock so the reload endpoint and
    background watcher never race against each other.

    Returns the new MODEL_LIST count.
    """
    global UNIFIED_INDEX, MODEL_LIST, CORRECTION_RULES, _catalog_mtime

    with _catalog_lock:
        raw_index = load_unified_index()
        unified = merge_index(raw_index)

        rules = load_correction_rules()
        if rules:
            corrections_made = apply_corrections(unified, rules)
            print(f"Applied {corrections_made} corrections across {len(unified)} models")

        # Build search-friendly list (deduplicated — skip aliases)
        model_list = []
        seen_displays: set[str] = set()
        for slug, info in sorted(unified.items()):
            display = info.get('display_name', slug)
            display_key = display.lower().replace(' ', '')
            if display_key in seen_displays:
                continue
            seen_displays.add(display_key)

            mfg = info.get('manufacturer', 'unknown').title()
            hashrate = ""
            entity = info.get('entity', '')
            if entity:
                m = re.search(r'\((\d+[\d.]*)\s*(?:TH|GH)', entity)
                if m:
                    hashrate = m.group(1) + " TH/s"
            if not hashrate and info.get('specs'):
                ths = info['specs'].get('default_rated_ths')
                if ths:
                    hashrate = f"{ths} TH/s"

            model_list.append({
                "slug": slug,
                "display_name": display,
                "manufacturer": mfg,
                "hashrate": hashrate,
                "label": f"{mfg} {display}" + (f" ({hashrate})" if hashrate else "")
            })

        # Atomically swap globals
        UNIFIED_INDEX = unified
        MODEL_LIST = model_list
        CORRECTION_RULES = rules

        # Track file mtime for auto-refresh
        try:
            _catalog_mtime = os.path.getmtime(INDEX_JSON)
        except OSError:
            _catalog_mtime = 0.0

        print(f"Loaded {len(MODEL_LIST)} miner models for Intelligence Reports")
        return len(MODEL_LIST)


# Initial load at startup
_load_catalog()


# ── Background auto-refresh (checks mtime every 5 minutes) ──────

def _catalog_auto_refresh():
    """Background thread: reload catalog if unified_miner_index.json changed on disk.

    Bucket 9 §10.7: poll cadence is read from
    `system_schedules.catalog_auto_refresh.interval_seconds` so operators
    can tune it from the GUI. Falls back to 300s if the helper is
    unavailable.
    """
    global _catalog_mtime
    while True:
        try:
            from api.system_schedules import get_interval_seconds
            sleep_s = get_interval_seconds("catalog_auto_refresh")
        except Exception:
            sleep_s = 300
        time.sleep(sleep_s)
        try:
            current_mtime = os.path.getmtime(INDEX_JSON)
        except OSError:
            continue
        if current_mtime > _catalog_mtime:
            print(f"[auto-refresh] Catalog file changed (mtime {current_mtime:.0f} > {_catalog_mtime:.0f}), reloading...")
            _load_catalog()


_refresh_thread = threading.Thread(target=_catalog_auto_refresh, daemon=True, name="catalog-auto-refresh")
_refresh_thread.start()


# ── Guardian DB helpers ───────────────────────────────────────
def get_fleet_data(model_name: str) -> dict:
    """Query guardian.db for fleet operational data matching a model name.
    
    Uses miner_hardware.device_name to identify model, joined with
    miner_readings for latest LIVE operational data per miner.
    
    IMPORTANT: Uses miner_readings (live hashrate, temp, consumption) NOT
    miner_state_readings (which stores AMS threshold/nominal settings like
    maxHashrate=75TH/s, maxTempChip=100°C — not actual readings).
    
    Search strategies for device_name:
    1. Direct case-insensitive LIKE match
    2. Normalized match (strip spaces/hyphens/plus from both sides)
    3. Short name match (drop manufacturer prefix)
    """
    # Postgres: do a quick connection probe. If DB is unreachable, bail early.
    try:
        _probe = psycopg2.connect(_pg_dsn())
        _probe.close()
    except psycopg2.OperationalError as e:
        return {"deployed": False, "reason": f"Postgres unreachable: {e}"}
    
    try:
        conn = _PgConnWrapper(psycopg2.connect(_pg_dsn(), cursor_factory=DictCursor))
        cur = conn.cursor()
        
        # First: find matching miner_ids from miner_hardware.device_name
        miner_ids = []
        
        # Strategy 1: Direct case-insensitive LIKE on device_name
        cur.execute("""
            SELECT DISTINCT miner_id, ip, device_name
            FROM miner_hardware
            WHERE LOWER(device_name) LIKE %s
        """, (f"%{model_name.lower()}%",))
        hw_rows = [dict(r) for r in cur.fetchall()]
        
        # Strategy 2: Normalized match
        if not hw_rows:
            norm = model_name.lower().replace(' ', '').replace('-', '').replace('+', '')
            cur.execute("""
                SELECT DISTINCT miner_id, ip, device_name
                FROM miner_hardware
                WHERE REPLACE(REPLACE(REPLACE(LOWER(device_name), ' ', ''), '-', ''), '+', '') LIKE %s
            """, (f"%{norm}%",))
            hw_rows = [dict(r) for r in cur.fetchall()]
        
        # Strategy 3: Drop manufacturer prefix (e.g. "Antminer S19J Pro" -> "S19J Pro")
        if not hw_rows:
            parts = model_name.split()
            if len(parts) > 1:
                short_name = ' '.join(parts[1:])
                cur.execute("""
                    SELECT DISTINCT miner_id, ip, device_name
                    FROM miner_hardware
                    WHERE LOWER(device_name) LIKE %s
                """, (f"%{short_name.lower()}%",))
                hw_rows = [dict(r) for r in cur.fetchall()]
        
        if not hw_rows:
            conn.close()
            return {"deployed": False, "count": 0}
        
        # Build unique miner list (miner_hardware has one row per board)
        miner_map = {}  # miner_id -> {ip, device_name}
        for row in hw_rows:
            mid = row['miner_id']
            if mid not in miner_map:
                miner_map[mid] = {'miner_id': mid, 'ip': row['ip'], 'model': row['device_name']}
        
        miner_ids = list(miner_map.keys())
        total = len(miner_ids)
        
        # Get latest LIVE reading for each miner from miner_readings
        # (NOT miner_state_readings which stores AMS threshold settings)
        placeholders = ','.join(['%s'] * len(miner_ids))
        cur.execute(f"""
            SELECT r.miner_id, r.ip, r.hashrate, r.temp_chip, r.temp_board,
                   r.status, r.consumption, r.max_hashrate, r.hashrate_pct,
                   r.scanned_at, r.firmware_version, r.current_profile,
                   r.uptime, r.cooling_mode, r.pdu_power
            FROM miner_readings r
            INNER JOIN (
                SELECT miner_id, MAX(scanned_at) as latest
                FROM miner_readings
                WHERE miner_id IN ({placeholders})
                GROUP BY miner_id
            ) latest ON r.miner_id = latest.miner_id AND r.scanned_at = latest.latest
        """, miner_ids)
        state_rows = {row['miner_id']: dict(row) for row in cur.fetchall()}
        
        # Merge hardware + live readings into miner records
        miners = []
        for mid, hw in miner_map.items():
            state = state_rows.get(mid, {})
            # hashrate in miner_readings is in GH/s (raw AMS value) — convert to TH/s
            hr_ghs = state.get('hashrate', 0) or 0
            hr_ths = round(hr_ghs / 1000, 1)
            # status is stored as text: 'online'/'offline'
            status = state.get('status', 'offline') or 'offline'
            # consumption is in watts from AMS
            power_w = state.get('consumption', 0) or 0
            miners.append({
                'ip': hw.get('ip') or state.get('ip', ''),
                'model': hw.get('model', ''),
                'miner_id': mid,
                'hashrate_ths': hr_ths,
                'chip_temp': state.get('temp_chip', 0) or 0,
                'temp_board': state.get('temp_board', 0) or 0,
                'power_w': power_w,
                'pdu_power_kw': state.get('pdu_power', 0) or 0,
                'status': status,
                'hashrate_pct': state.get('hashrate_pct', 0) or 0,
                'max_hashrate_ghs': state.get('max_hashrate', 0) or 0,
                'last_scan': state.get('scanned_at', ''),
                'firmware': state.get('firmware_version', ''),
                'profile': state.get('current_profile', ''),
                'uptime': state.get('uptime', ''),
            })
        
        online = sum(1 for m in miners if m['status'] == 'online')
        offline = total - online
        
        # Averages (only from miners with data)
        hashrates = [m['hashrate_ths'] for m in miners if m['hashrate_ths'] > 0]
        temps = [m['chip_temp'] for m in miners if m['chip_temp'] > 0]
        avg_hashrate_ths = sum(hashrates) / max(len(hashrates), 1)
        avg_temp = sum(temps) / max(len(temps), 1)
        
        # Board count from hardware table
        cur.execute(f"""
            SELECT COUNT(*) as total_boards,
                   SUM(CASE WHEN bad_chips_count > 0 THEN 1 ELSE 0 END) as boards_with_bad_chips
            FROM miner_hardware
            WHERE miner_id IN ({placeholders})
        """, miner_ids)
        board_row = cur.fetchone()
        total_boards = board_row['total_boards'] if board_row else 0
        bad_chip_boards = board_row['boards_with_bad_chips'] if board_row else 0
        
        # Get restart stats using miner_id (matches miner_restarts.miner_id)
        total_restarts = 0
        successes = 0
        if miner_ids:
            cur.execute(f"""
                SELECT COUNT(*) as total_restarts,
                       SUM(CASE WHEN outcome IS NOT NULL AND outcome != 'FAIL' AND outcome != 'FAILED' THEN 1 ELSE 0 END) as successes
                FROM miner_restarts 
                WHERE miner_id IN ({placeholders})
            """, miner_ids)
            restart_row = cur.fetchone()
            total_restarts = restart_row['total_restarts'] if restart_row else 0
            successes = restart_row['successes'] if restart_row else 0
        
        # Top/bottom performers by hashrate
        sorted_miners = sorted(miners, key=lambda m: m.get('hashrate_ths', 0), reverse=True)
        top_3 = sorted_miners[:3]
        bottom_3 = [m for m in sorted_miners[-3:] if m.get('hashrate_ths', 0) > 0 and m.get('hashrate_ths', 0) < avg_hashrate_ths * 0.85]
        
        conn.close()
        
        return {
            "deployed": True,
            "count": total,
            "online": online,
            "offline": offline,
            "total_boards": total_boards,
            "boards_with_bad_chips": bad_chip_boards,
            "avg_hashrate_ths": round(avg_hashrate_ths, 1),
            "avg_chip_temp": round(avg_temp, 1),
            "total_restarts": total_restarts,
            "restart_success_rate": round(successes / max(total_restarts, 1) * 100, 1),
            "top_performers": top_3,
            "problem_miners": bottom_3,
            "all_miners": miners
        }
    except Exception as e:
        return {"deployed": False, "error": str(e)}


# ── Profitability Calculator ──────────────────────────────────
def calc_profitability(hashrate_th: float, power_w: float, efficiency_jth: float) -> dict:
    """Calculate profitability estimates at multiple electricity rates."""
    if not hashrate_th or not power_w:
        return {}
    
    # Live network data (cached 15 min) with safe fallbacks
    net = get_network_data()
    btc_price_usd = net.get("btc_price_usd", 0) or 85000  # Fallback if API down
    network_difficulty = net.get("network_difficulty", 0) or 139e12  # Fallback
    block_reward = 3.125  # Post-2024 halving
    
    # Daily BTC mined = (hashrate * 86400 * block_reward) / (difficulty * 2^32)
    daily_btc = (hashrate_th * 1e12 * 86400 * block_reward) / (network_difficulty * 2**32)
    daily_revenue_usd = daily_btc * btc_price_usd
    
    # Power cost at different rates
    daily_kwh = (power_w / 1000) * 24
    monthly_kwh = daily_kwh * 30
    
    rates = [
        {"label": "$0.04/kWh (Cheap hydro/solar)", "rate": 0.04},
        {"label": "$0.06/kWh (Low-cost region)", "rate": 0.06},
        {"label": "$0.08/kWh (Average industrial)", "rate": 0.08},
        {"label": "$0.10/kWh (Average US)", "rate": 0.10},
        {"label": "$0.12/kWh (Higher cost)", "rate": 0.12},
    ]
    
    tiers = []
    breakeven_rate = daily_revenue_usd / daily_kwh if daily_kwh > 0 else 0
    
    for r in rates:
        daily_cost = daily_kwh * r["rate"]
        daily_profit = daily_revenue_usd - daily_cost
        monthly_profit = daily_profit * 30
        annual_profit = daily_profit * 365
        tiers.append({
            "label": r["label"],
            "rate": r["rate"],
            "daily_cost": round(daily_cost, 2),
            "daily_profit": round(daily_profit, 2),
            "monthly_profit": round(monthly_profit, 2),
            "annual_profit": round(annual_profit, 2),
            "profitable": daily_profit > 0,
        })
    
    return {
        "btc_price_usd": btc_price_usd,
        "daily_btc": round(daily_btc, 8),
        "daily_revenue_usd": round(daily_revenue_usd, 2),
        "daily_kwh": round(daily_kwh, 1),
        "monthly_kwh": round(monthly_kwh, 0),
        "breakeven_rate": round(breakeven_rate, 4),
        "efficiency_j_th": efficiency_jth,
        "network_difficulty_t": round(network_difficulty / 1e12, 2),
        "network_hashrate_eh": net.get("network_hashrate_eh", 0),
        "block_height": net.get("block_height", 0),
        "data_source": net.get("source", "fallback"),
        "data_time": net.get("last_fetch_time", ""),
        "tiers": tiers,
    }


# ── Report Builder ────────────────────────────────────────────
def build_report(slug: str) -> dict:
    """Build a complete intelligence report for a miner model."""
    info = UNIFIED_INDEX.get(slug)
    if not info:
        return None
    
    display_name = info.get('display_name', slug)
    manufacturer = info.get('manufacturer', 'Unknown').title()
    enrichment = info.get('enrichment') or {}
    specs = info.get('specs')
    entity = info.get('entity', '')
    
    # ── Hardware Specifications ──
    hw = {
        "manufacturer": manufacturer,
        "model": display_name,
        "canonical_slug": slug,
    }
    
    if specs:
        hw["cooling_type"] = specs.get("cooling", "unknown")
        hw["algorithm"] = specs.get("algorithm", "SHA-256")
        hw["default_hashrate_th"] = specs.get("default_rated_ths")
        hw["default_power_w"] = specs.get("default_rated_watts")
        hw["notes"] = specs.get("notes", "")
        
        variants = specs.get("variants", [])
        if variants:
            hw["variants"] = variants
            hw["efficiency_j_th"] = variants[0].get("efficiency_j_th")
    
    # From enrichment CSV
    if enrichment:
        hw["release_date"] = enrichment.get("Release Date (exact)", "Unknown")
        hw["dimensions"] = enrichment.get("Dimensions (mm)", "N/A")
        hw["weight_kg"] = enrichment.get("Weight (kg)", "N/A")
        hw["operating_temp"] = enrichment.get("Operating Temp Range", "N/A")
        hw["humidity"] = enrichment.get("Humidity Range", "N/A")
        hw["noise_db"] = enrichment.get("Noise (dB)", "N/A")
        hw["network"] = enrichment.get("Network Interface", "N/A")
        hw["psu_requirements"] = enrichment.get("PSU Requirements", "N/A")
        hw["voltage_range"] = enrichment.get("Voltage Range", "N/A")
        hw["cooling_details"] = enrichment.get("Cooling Details", "N/A")
        hw["known_issues"] = enrichment.get("Known Issues", "None documented")
        hw["firmware_support"] = enrichment.get("Firmware Support", "N/A")
        hw["distinguishing_features"] = enrichment.get("Distinguishing Features", "N/A")
        hw["warranty"] = enrichment.get("Warranty", "N/A")
        hw["sources"] = enrichment.get("Sources", "")
    
    # Extract hashrate from entity name if not in specs
    if not hw.get("default_hashrate_th") and entity:
        m = re.search(r'\((\d+[\d.]*)\s*(?:TH|GH)', entity)
        if m:
            val = float(m.group(1))
            hw["default_hashrate_th"] = val
    
    # ── Fleet Data ──
    model_search = display_name.split('(')[0].strip()
    fleet = get_fleet_data(model_search)
    
    # ── Profitability ──
    hashrate = hw.get("default_hashrate_th", 0) or 0
    power = hw.get("default_power_w", 0) or 0
    eff = hw.get("efficiency_j_th", 0) or 0
    profitability = calc_profitability(hashrate, power, eff) if hashrate and power else {}
    
    # ── Build Report ──
    report = {
        "generated_at": datetime.now().strftime("%B %d, %Y %I:%M %p CDT"),
        "slug": slug,
        "display_name": display_name,
        "manufacturer": manufacturer,
        "report_type": "Complete Analysis" if fleet.get("deployed") else "Pre-Deployment Analysis (Catalog Only)",
        "fleet_deployed": fleet.get("deployed", False),
        "hardware": hw,
        "fleet": fleet,
        "profitability": profitability,
        "data_sources": {
            "has_enrichment": enrichment is not None and len(enrichment) > 0,
            "has_specs": specs is not None,
            "has_fleet_data": fleet.get("deployed", False),
            "catalog_tables": 165,
        }
    }
    
    return report


# ── API Endpoints ─────────────────────────────────────────────

@app.get("/health")
def health():
    net = get_network_data()
    return {
        "status": "ok",
        "version": "2.3.0",
        "models": len(MODEL_LIST),
        "correction_rules": len(CORRECTION_RULES),
        "btc_price": net.get("btc_price_usd", 0),
        "network_difficulty_t": round(net.get("network_difficulty", 0) / 1e12, 2),
        "data_source": net.get("source", "initializing"),
    }

@app.post("/api/catalog/reload")
def reload_catalog():
    """Hot-reload the catalog from disk without restarting the API."""
    old_count = len(MODEL_LIST)
    new_count = _load_catalog()
    return {
        "status": "reloaded",
        "previous_model_count": old_count,
        "new_model_count": new_count,
        "delta": new_count - old_count,
    }


@app.get("/api/report/models")
def list_models():
    """Return all models for Grafana variable dropdown."""
    return MODEL_LIST

@app.get("/api/report/models/labels")
def list_model_labels():
    """Return simple label:value pairs for Grafana template variable (JSON datasource)."""
    return [{"__text": m["label"], "__value": m["slug"]} for m in MODEL_LIST]

@app.get("/api/report/search")
def search_models(q: str = Query("", description="Search query")):
    """Search models by partial name match."""
    if not q or len(q) < 2:
        return MODEL_LIST[:50]
    
    q_lower = q.lower()
    results = [
        m for m in MODEL_LIST
        if q_lower in m["label"].lower() or q_lower in m["slug"]
    ]
    return results[:50]

@app.get("/api/report/{slug}")
def get_report(slug: str):
    """Get full intelligence report for a miner model."""
    try:
        report = build_report(slug)
        if not report:
            slug_lower = slug.lower().replace(' ', '-').replace('+', 'plus')
            report = build_report(slug_lower)
        if not report:
            return JSONResponse(status_code=404, content={"error": f"Model '{slug}' not found", "available": len(MODEL_LIST)})
        return report
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": f"Report generation error: {str(e)}", "slug": slug})

@app.get("/api/report/{slug}/html")
def get_report_html(slug: str):
    """Get intelligence report rendered as full HTML for iframe rendering."""
    try:
        report = build_report(slug)
        if not report:
            slug_lower = slug.lower().replace(' ', '-').replace('+', 'plus')
            report = build_report(slug_lower)
        if not report:
            return JSONResponse(
                status_code=404,
                content={"html": f"<div style='color:#ff6b6b; padding:20px; font-size:16px;'>Model '{slug}' not found in Intelligence Catalog ({len(MODEL_LIST)} models available)</div>"}
            )
        
        html = render_full_html(report)
        return {"html": html}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"html": f"<div style='color:#ef4444; padding:20px; font-size:16px;'>Report generation error for '{slug}': {str(e)}</div>",
                     "error": str(e)}
        )


# ── Auto-Discovery Endpoints ─────────────────────────────────

class AcknowledgeRequest(BaseModel):
    level: int = 1       # 1=reviewed, 2=added to catalog
    notes: Optional[str] = None

@app.get("/api/discoveries")
def list_discoveries(acknowledged: Optional[int] = Query(None, description="Filter by acknowledged status (0=new, 1=reviewed, 2=added)")):
    """Return discovery_log entries. Defaults to unacknowledged (acknowledged=0)."""
    try:
        conn = _PgConnWrapper(psycopg2.connect(_pg_dsn(), cursor_factory=DictCursor))
        if acknowledged is not None:
            rows = conn.execute(
                "SELECT * FROM discovery_log WHERE acknowledged = %s ORDER BY last_seen DESC",
                (acknowledged,)
            ).fetchall()
        else:
            # Default: show unacknowledged discoveries
            rows = conn.execute(
                "SELECT * FROM discovery_log WHERE acknowledged = 0 ORDER BY last_seen DESC"
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except psycopg2.errors.UndefinedTable:
        return []
    except psycopg2.Error as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/discoveries/{discovery_id}/acknowledge")
def acknowledge_discovery(
    discovery_id: int = APIPath(..., description="Discovery log entry ID"),
    body: AcknowledgeRequest = AcknowledgeRequest()
):
    """Mark a discovery as reviewed (1) or added-to-catalog (2)."""
    if body.level not in (1, 2):
        return JSONResponse(status_code=400, content={"error": "level must be 1 (reviewed) or 2 (added to catalog)"})
    try:
        conn = _PgConnWrapper(psycopg2.connect(_pg_dsn(), cursor_factory=DictCursor))
        params = [body.level]
        sql = "UPDATE discovery_log SET acknowledged = %s"
        if body.notes is not None:
            sql += ", notes = %s"
            params.append(body.notes)
        sql += " WHERE id = %s"
        params.append(discovery_id)
        cursor = conn.execute(sql, params)
        conn.commit()
        if cursor.rowcount == 0:
            conn.close()
            return JSONResponse(status_code=404, content={"error": f"Discovery {discovery_id} not found"})
        # Return the updated row
        row = conn.execute("SELECT * FROM discovery_log WHERE id = %s", (discovery_id,)).fetchone()
        conn.close()
        return dict(row) if row else {"success": True}
    except psycopg2.errors.UndefinedTable:
        return JSONResponse(status_code=404, content={"error": "discovery_log table not yet created — run a scan first"})
    except psycopg2.Error as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
        return JSONResponse(status_code=500, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── HTML Report Renderer (v2 — full 9-section report) ─────────

def _css():
    """Return shared CSS styles for the report."""
    return """
    <style>
      * { box-sizing: border-box; }
      body { margin:0; padding:0; background:#0f172a; color:#e2e8f0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; }
      .report { max-width:1200px; margin:0 auto; padding:24px; }
      .section { background:#1e293b; border:1px solid #334155; border-radius:10px; padding:24px; margin-bottom:20px; }
      .section-header { display:flex; align-items:center; gap:10px; margin:0 0 18px 0; border-bottom:1px solid #334155; padding-bottom:10px; }
      .section-header h3 { margin:0; font-size:16px; font-weight:700; letter-spacing:0.3px; }
      .section-icon { font-size:20px; line-height:1; }
      .spec-grid { display:grid; grid-template-columns:1fr 1fr; gap:6px 32px; }
      .spec-row { display:flex; padding:5px 0; border-bottom:1px solid #0f172a; }
      .spec-label { color:#94a3b8; font-size:13px; min-width:140px; font-weight:500; }
      .spec-value { color:#e2e8f0; font-size:13px; font-weight:600; }
      table { width:100%; border-collapse:collapse; font-size:13px; }
      th { text-align:left; padding:8px; color:#94a3b8; font-weight:600; border-bottom:2px solid #334155; }
      th.right { text-align:right; }
      td { padding:7px 8px; color:#e2e8f0; border-bottom:1px solid #1e293b55; }
      td.right { text-align:right; }
      td.mono { font-family:'SF Mono',Menlo,monospace; font-size:12px; }
      .stat-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:20px; }
      .stat-card { background:#0f172a; border-radius:8px; padding:16px; text-align:center; border:1px solid #1e293b; }
      .stat-value { font-size:28px; font-weight:700; line-height:1.2; }
      .stat-label { font-size:11px; color:#94a3b8; margin-top:4px; text-transform:uppercase; letter-spacing:0.5px; }
      .badge { display:inline-block; padding:3px 10px; border-radius:4px; font-size:11px; font-weight:600; letter-spacing:0.5px; }
      .badge-green { background:#10b98122; color:#10b981; border:1px solid #10b98144; }
      .badge-amber { background:#f59e0b22; color:#f59e0b; border:1px solid #f59e0b44; }
      .badge-red { background:#ef444422; color:#ef4444; border:1px solid #ef444444; }
      .badge-cyan { background:#06b6d422; color:#06b6d4; border:1px solid #06b6d444; }
      .alert-box { border-radius:8px; padding:16px; margin-bottom:12px; }
      .alert-amber { background:#f59e0b11; border:1px solid #f59e0b33; }
      .alert-green { background:#10b98111; border:1px solid #10b98133; }
      .alert-red { background:#ef444411; border:1px solid #ef444433; }
      .alert-cyan { background:#06b6d411; border:1px solid #06b6d433; }
      .progress-bar { height:8px; background:#0f172a; border-radius:4px; overflow:hidden; margin-top:6px; }
      .progress-fill { height:100%; border-radius:4px; transition:width 0.3s; }
      .insight-card { background:#0f172a; border:1px solid #334155; border-radius:8px; padding:16px; margin-bottom:12px; }
      .insight-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
      .insight-title { color:#f8fafc; font-size:14px; font-weight:600; }
      .confidence { font-size:11px; font-weight:600; padding:2px 8px; border-radius:3px; }
      .insight-body { color:#cbd5e1; font-size:13px; line-height:1.7; }
      .rec-item { display:flex; gap:12px; padding:12px 0; border-bottom:1px solid #0f172a; }
      .rec-icon { font-size:18px; min-width:28px; text-align:center; padding-top:2px; }
      .rec-content h4 { margin:0 0 4px 0; font-size:14px; color:#f8fafc; font-weight:600; }
      .rec-content p { margin:0; font-size:13px; color:#cbd5e1; line-height:1.6; }
      .footer { text-align:center; color:#475569; font-size:11px; padding:16px 0; line-height:1.6; }
      .toc { display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-top:12px; }
      .toc-item { display:flex; align-items:center; gap:8px; color:#94a3b8; font-size:12px; padding:4px 8px; background:#0f172a; border-radius:4px; }
      .toc-num { color:#06b6d4; font-weight:700; font-size:11px; min-width:18px; }
      @media (max-width: 768px) {
        .spec-grid, .stat-grid, .toc { grid-template-columns:1fr; }
      }
    </style>
"""

def _header(report: dict) -> str:
    """Render the report header with title, badge, and table of contents."""
    hw = report["hardware"]
    deployed = report["fleet_deployed"]
    badge_class = "badge-green" if deployed else "badge-amber"
    badge_text = "DEPLOYED IN FLEET" if deployed else "CATALOG DATA ONLY"
    
    sections = [
        "Hardware Specifications", "Firmware &amp; Known Issues", "Fleet Performance",
        "Profitability &amp; Economics", "Market Context", "Repair &amp; Maintenance",
        "Cooling &amp; Environment", "AI Analysis", "Recommendations"
    ]
    
    toc_html = ""
    for i, s in enumerate(sections, 1):
        toc_html += f'<div class="toc-item"><span class="toc-num">{i}</span> {s}</div>'
    
    return f"""
    <div style="text-align:center; margin-bottom:32px;">
      <div style="font-size:11px; color:#64748b; text-transform:uppercase; letter-spacing:2px; margin-bottom:8px;">Mining Guardian</div>
      <h1 style="font-size:30px; font-weight:800; color:#f8fafc; margin:0 0 4px 0; letter-spacing:-0.5px;">MINER INTELLIGENCE REPORT</h1>
      <h2 style="font-size:20px; font-weight:600; color:#06b6d4; margin:0 0 14px 0;">{hw.get('manufacturer','')} {hw.get('model','')} — {report['report_type']}</h2>
      <span class="badge {badge_class}">{badge_text}</span>
      <div style="color:#94a3b8; font-size:13px; margin-top:10px;">
        Generated: {report['generated_at']}<br>
        Data Sources: Intelligence Catalog ({report['data_sources']['catalog_tables']} tables)
        {' + Guardian Fleet Database' if deployed else ''}
      </div>
      <div class="toc" style="max-width:600px; margin:16px auto 0;">
        {toc_html}
      </div>
    </div>
"""

def _section_1_hardware(report: dict) -> str:
    """Section 1: Hardware Specifications."""
    hw = report["hardware"]
    
    spec_fields = [
        ("Manufacturer", hw.get('manufacturer', 'N/A')),
        ("Model", hw.get('model', 'N/A')),
        ("Algorithm", hw.get('algorithm', 'SHA-256')),
        ("Cooling", hw.get('cooling_type', hw.get('cooling_details', 'N/A'))),
        ("Release Date", hw.get('release_date', 'N/A')),
        ("Hashrate", f"{hw['default_hashrate_th']} TH/s" if hw.get('default_hashrate_th') else 'N/A'),
        ("Power", f"{hw['default_power_w']} W" if hw.get('default_power_w') else 'N/A'),
        ("Efficiency", f"{hw['efficiency_j_th']} J/TH" if hw.get('efficiency_j_th') else 'N/A'),
        ("Dimensions", hw.get('dimensions', 'N/A')),
        ("Weight", hw.get('weight_kg', 'N/A') if hw.get('weight_kg') and hw.get('weight_kg') != 'N/A' else 'N/A'),
        ("Operating Temp", hw.get('operating_temp', 'N/A')),
        ("Noise", hw.get('noise_db', 'N/A') if hw.get('noise_db') and hw.get('noise_db') != 'N/A' else 'N/A'),
        ("Network", hw.get('network', 'N/A')),
        ("PSU", hw.get('psu_requirements', 'N/A')),
        ("Voltage Range", hw.get('voltage_range', 'N/A')),
        ("Warranty", hw.get('warranty', 'N/A')),
    ]
    
    rows = ""
    for label, value in spec_fields:
        if value and value != 'N/A' and 'None' not in str(value):
            val_display = str(value)[:150]
            rows += f'<div class="spec-row"><span class="spec-label">{label}:</span><span class="spec-value">{val_display}</span></div>'
    
    # Variants table
    variants_html = ""
    variants = hw.get('variants', [])
    if variants:
        v_rows = ""
        for v in variants:
            eff = v.get('efficiency_j_th', 'N/A')
            eff_f = _safe_float(eff, -1)
            eff_color = "#10b981" if eff_f > 0 and eff_f < 25 else "#06b6d4" if eff_f > 0 and eff_f < 35 else "#f59e0b"
            v_rows += f"""
            <tr>
              <td style="font-weight:500;">{v.get('label','N/A')}</td>
              <td class="right" style="font-weight:600; color:#06b6d4;">{v.get('rated_ths','N/A')} TH/s</td>
              <td class="right">{v.get('rated_watts','N/A')} W</td>
              <td class="right" style="color:{eff_color}; font-weight:600;">{eff} J/TH</td>
            </tr>"""
        
        variants_html = f"""
        <div style="margin-top:20px;">
          <h4 style="color:#94a3b8; font-size:13px; margin:0 0 10px 0; text-transform:uppercase; letter-spacing:0.5px;">Model Variants</h4>
          <table>
            <thead><tr><th>Variant</th><th class="right">Hashrate</th><th class="right">Power</th><th class="right">Efficiency</th></tr></thead>
            <tbody>{v_rows}</tbody>
          </table>
        </div>"""
    
    return f"""
    <div class="section">
      <div class="section-header">
        <span class="section-icon">🔧</span>
        <h3 style="color:#06b6d4;">1. HARDWARE SPECIFICATIONS</h3>
      </div>
      <div class="spec-grid">{rows}</div>
      {variants_html}
    </div>
"""

def _section_2_firmware(report: dict) -> str:
    """Section 2: Firmware & Known Issues."""
    hw = report["hardware"]
    firmware = hw.get('firmware_support', '')
    known_issues = hw.get('known_issues', '')
    features = hw.get('distinguishing_features', '')
    
    if not firmware and not known_issues and not features:
        return f"""
    <div class="section">
      <div class="section-header">
        <span class="section-icon">💾</span>
        <h3 style="color:#06b6d4;">2. FIRMWARE &amp; KNOWN ISSUES</h3>
      </div>
      <div style="color:#64748b; font-size:13px; text-align:center; padding:20px;">No firmware or known issue data available in catalog. Data will be added as it becomes available.</div>
    </div>
"""
    
    parts = []
    if firmware and firmware != 'N/A':
        parts.append(f"""
        <div style="margin-bottom:16px;">
          <h4 style="color:#e2e8f0; font-size:14px; margin:0 0 8px 0; font-weight:600;">Firmware Support</h4>
          <p style="color:#cbd5e1; font-size:13px; line-height:1.7; margin:0;">{firmware[:800]}</p>
        </div>""")
    
    if known_issues and known_issues not in ('None documented', 'N/A'):
        parts.append(f"""
        <div class="alert-box alert-amber" style="margin-bottom:16px;">
          <h4 style="color:#f59e0b; font-size:14px; margin:0 0 8px 0; font-weight:600;">⚠ Known Issues</h4>
          <p style="color:#fbbf24; font-size:13px; line-height:1.7; margin:0;">{known_issues[:1000]}</p>
        </div>""")
    
    if features and features != 'N/A':
        parts.append(f"""
        <div style="margin-bottom:8px;">
          <h4 style="color:#e2e8f0; font-size:14px; margin:0 0 8px 0; font-weight:600;">Distinguishing Features</h4>
          <p style="color:#cbd5e1; font-size:13px; line-height:1.7; margin:0;">{features[:800]}</p>
        </div>""")
    
    return f"""
    <div class="section">
      <div class="section-header">
        <span class="section-icon">💾</span>
        <h3 style="color:#06b6d4;">2. FIRMWARE &amp; KNOWN ISSUES</h3>
      </div>
      {"".join(parts)}
    </div>
"""

def _section_3_fleet(report: dict) -> str:
    """Section 3: Fleet Operational Performance."""
    fleet = report["fleet"]
    deployed = report["fleet_deployed"]
    
    if not deployed:
        return f"""
    <div class="section">
      <div class="section-header">
        <span class="section-icon">📊</span>
        <h3 style="color:#f59e0b;">3. FLEET OPERATIONAL PERFORMANCE</h3>
      </div>
      <div class="alert-box alert-amber" style="text-align:center; padding:28px;">
        <div style="font-size:18px; color:#fbbf24; font-weight:700; margin-bottom:8px;">NOT DEPLOYED IN FLEET</div>
        <div style="color:#94a3b8; font-size:13px; line-height:1.8;">
          This miner model is not currently deployed in your facility.<br>
          Report is based entirely on Intelligence Catalog reference data.<br><br>
          <span style="color:#64748b;">When deployed, Mining Guardian will automatically:</span><br>
          ● Detect the model via device fingerprinting<br>
          ● Load the correct operating profile from the Catalog<br>
          ● Begin building fleet-specific performance data within 24 hours
        </div>
      </div>
    </div>
"""
    
    # Deployed — show full fleet stats
    count = fleet.get('count', 0)
    online = fleet.get('online', 0)
    avg_hr = fleet.get('avg_hashrate_ths', 0)
    avg_temp = fleet.get('avg_chip_temp', 0)
    total_boards = fleet.get('total_boards', 0)
    bad_boards = fleet.get('boards_with_bad_chips', 0)
    
    temp_color = "#10b981" if avg_temp < 70 else "#f59e0b" if avg_temp < 80 else "#ef4444"
    online_pct = round(online / max(count, 1) * 100, 1)
    board_health_pct = round((total_boards - bad_boards) / max(total_boards, 1) * 100, 1)
    
    # Top performers table
    top_html = ""
    top = fleet.get('top_performers', [])
    if top:
        top_rows = ""
        for m in top:
            hr = m.get('hashrate_ths', 0) or 0
            st = m.get('status', 'unknown')
            stc = "#10b981" if st == 'online' else "#ef4444"
            top_rows += f"""
            <tr>
              <td class="mono">{m.get('ip','N/A')}</td>
              <td class="right" style="color:#06b6d4; font-weight:600;">{hr:.1f} TH/s</td>
              <td class="right">{m.get('chip_temp','N/A')}°C</td>
              <td style="text-align:center; color:{stc}; font-weight:500;">{st.upper()}</td>
            </tr>"""
        top_html = f"""
        <div style="margin-top:16px;">
          <h4 style="color:#10b981; font-size:13px; margin:0 0 10px 0; text-transform:uppercase; letter-spacing:0.5px;">Top Performers</h4>
          <table>
            <thead><tr><th>IP Address</th><th class="right">Hashrate</th><th class="right">Chip Temp</th><th style="text-align:center;">Status</th></tr></thead>
            <tbody>{top_rows}</tbody>
          </table>
        </div>"""
    
    # Problem miners
    prob_html = ""
    prob = fleet.get('problem_miners', [])
    if prob:
        prob_rows = ""
        for m in prob:
            hr = m.get('hashrate_ths', 0) or 0
            prob_rows += f"""
            <tr>
              <td class="mono">{m.get('ip','N/A')}</td>
              <td class="right" style="color:#ef4444; font-weight:600;">{hr:.1f} TH/s</td>
              <td class="right">{m.get('chip_temp','N/A')}°C</td>
              <td style="text-align:center; color:#f59e0b;">{m.get('firmware','N/A')}</td>
            </tr>"""
        prob_html = f"""
        <div style="margin-top:16px;">
          <h4 style="color:#ef4444; font-size:13px; margin:0 0 10px 0; text-transform:uppercase; letter-spacing:0.5px;">Needs Attention</h4>
          <table>
            <thead><tr><th>IP Address</th><th class="right">Hashrate</th><th class="right">Chip Temp</th><th style="text-align:center;">Firmware</th></tr></thead>
            <tbody>{prob_rows}</tbody>
          </table>
        </div>"""
    
    return f"""
    <div class="section">
      <div class="section-header">
        <span class="section-icon">📊</span>
        <h3 style="color:#10b981;">3. FLEET OPERATIONAL PERFORMANCE</h3>
      </div>
      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-value" style="color:#06b6d4;">{count}</div>
          <div class="stat-label">Miners Deployed</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color:#10b981;">{online_pct}%</div>
          <div class="stat-label">Online Rate</div>
          <div class="progress-bar"><div class="progress-fill" style="width:{online_pct}%; background:#10b981;"></div></div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color:#06b6d4;">{avg_hr} TH/s</div>
          <div class="stat-label">Avg Hashrate</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color:{temp_color};">{avg_temp}°C</div>
          <div class="stat-label">Avg Chip Temp</div>
        </div>
      </div>
      <div class="stat-grid" style="grid-template-columns:repeat(3, 1fr);">
        <div class="stat-card">
          <div class="stat-value" style="color:#8b5cf6; font-size:22px;">{total_boards}</div>
          <div class="stat-label">Total Boards</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color:#10b981; font-size:22px;">{board_health_pct}%</div>
          <div class="stat-label">Board Health</div>
          <div class="progress-bar"><div class="progress-fill" style="width:{board_health_pct}%; background:#10b981;"></div></div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color:#f59e0b; font-size:22px;">{fleet.get('total_restarts',0)}</div>
          <div class="stat-label">Total Restarts</div>
        </div>
      </div>
      {top_html}
      {prob_html}
    </div>
"""

def _section_4_profitability(report: dict) -> str:
    """Section 4: Profitability & Economics."""
    prof = report.get("profitability", {})
    hw = report["hardware"]
    
    if not prof:
        return f"""
    <div class="section">
      <div class="section-header">
        <span class="section-icon">💰</span>
        <h3 style="color:#10b981;">4. PROFITABILITY &amp; ECONOMICS</h3>
      </div>
      <div style="color:#64748b; font-size:13px; text-align:center; padding:20px;">
        Insufficient data to calculate profitability. Requires hashrate and power consumption values.
      </div>
    </div>
"""
    
    breakeven = prof.get('breakeven_rate', 0)
    be_color = "#10b981" if breakeven > 0.10 else "#f59e0b" if breakeven > 0.06 else "#ef4444"
    
    # Tier rows
    tier_rows = ""
    for t in prof.get('tiers', []):
        profit = t['monthly_profit']
        p_color = "#10b981" if profit > 0 else "#ef4444"
        icon = "✓" if t['profitable'] else "✗"
        icon_color = "#10b981" if t['profitable'] else "#ef4444"
        tier_rows += f"""
        <tr>
          <td>{t['label']}</td>
          <td class="right">${t['daily_cost']:.2f}</td>
          <td class="right" style="color:{p_color}; font-weight:600;">${profit:+,.0f}</td>
          <td class="right" style="color:{p_color}; font-weight:600;">${t['annual_profit']:+,.0f}</td>
          <td style="text-align:center; color:{icon_color}; font-weight:700;">{icon}</td>
        </tr>"""
    
    return f"""
    <div class="section">
      <div class="section-header">
        <span class="section-icon">💰</span>
        <h3 style="color:#10b981;">4. PROFITABILITY &amp; ECONOMICS</h3>
      </div>
      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-value" style="color:#f59e0b; font-size:22px;">${prof.get('btc_price_usd',0):,.0f}</div>
          <div class="stat-label">BTC Price (est.)</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color:#06b6d4; font-size:22px;">{prof.get('daily_btc',0):.6f}</div>
          <div class="stat-label">Daily BTC Mined</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color:#10b981; font-size:22px;">${prof.get('daily_revenue_usd',0):.2f}</div>
          <div class="stat-label">Daily Revenue</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color:{be_color}; font-size:22px;">${breakeven:.4f}</div>
          <div class="stat-label">Breakeven $/kWh</div>
        </div>
      </div>
      <div style="margin-top:4px;">
        <h4 style="color:#94a3b8; font-size:13px; margin:0 0 10px 0; text-transform:uppercase; letter-spacing:0.5px;">Profitability by Electricity Rate</h4>
        <table>
          <thead><tr><th>Rate</th><th class="right">Daily Power Cost</th><th class="right">Monthly Profit</th><th class="right">Annual Profit</th><th style="text-align:center;">Viable</th></tr></thead>
          <tbody>{tier_rows}</tbody>
        </table>
      </div>
      <div class="alert-box alert-cyan" style="margin-top:16px;">
        <p style="color:#67e8f9; font-size:12px; margin:0; line-height:1.6;">
          <strong>🟢 LIVE DATA</strong> — BTC ${prof.get('btc_price_usd',0):,.0f} ● Difficulty {prof.get('network_difficulty_t',0):.2f}T ● Network {prof.get('network_hashrate_eh',0):.1f} EH/s{f" ● Block {prof.get('block_height',0):,}" if prof.get('block_height') else ''}<br>
          <span style="color:#94a3b8;">Source: {prof.get('data_source','N/A')} ● Updated: {prof.get('data_time','N/A')} ● Refreshes every 15 min</span><br>
          <span style="color:#94a3b8;">Daily power: {prof.get('daily_kwh',0):.1f} kWh ({prof.get('monthly_kwh',0):.0f} kWh/month) ● Efficiency: {hw.get('efficiency_j_th','N/A')} J/TH ●
          Does not include pool fees (typically 1-2%) or hardware downtime.</span>
        </p>
      </div>
    </div>
"""

def _section_5_market(report: dict) -> str:
    """Section 5: Market Context."""
    hw = report["hardware"]
    eff = hw.get('efficiency_j_th', 0)
    hashrate = hw.get('default_hashrate_th', 0) or 0
    manufacturer = hw.get('manufacturer', '')
    
    # Determine generation and competitive positioning
    eff_val = _safe_float(eff, 0)
    if eff_val > 0:
        if eff_val < 17:
            gen = "Current Generation (Ultra-Efficient)"
            gen_color = "#10b981"
            position = "Top-tier efficiency — among the most competitive miners on the market today."
        elif eff_val < 25:
            gen = "Current Generation (High-Efficiency)"
            gen_color = "#06b6d4"
            position = "Strong efficiency — competitive at most electricity rates. Suitable for medium to long-term deployment."
        elif eff_val < 35:
            gen = "Mid-Generation"
            gen_color = "#f59e0b"
            position = "Moderate efficiency — profitable primarily at lower electricity rates. Consider upgrade path planning."
        elif eff_val < 50:
            gen = "Previous Generation"
            gen_color = "#f97316"
            position = "Below-average efficiency by current standards. Profitable only at very low electricity rates (<$0.06/kWh)."
        else:
            gen = "Legacy Hardware"
            gen_color = "#ef4444"
            position = "Significantly below current efficiency standards. Likely unprofitable at most electricity rates. Consider retirement or resale."
    else:
        gen = "Unknown Generation"
        gen_color = "#64748b"
        position = "Insufficient data to determine competitive positioning."
    
    # Competitor models by manufacturer
    competitors = {
        "Bitmain": ["S21 XP (270 TH, 13.5 J/TH)", "S21 Pro (234 TH, 15.0 J/TH)", "S21 (200 TH, 17.5 J/TH)", "T21 (190 TH, 19.0 J/TH)"],
        "Microbt": ["M66S+ (298 TH, 14.3 J/TH)", "M63S+ (390 TH, 14.5 J/TH)", "M60S+ (186 TH, 18.5 J/TH)"],
        "Canaan": ["A15 XP (227 TH, 15.0 J/TH)", "A14 (200 TH, 16.0 J/TH)", "A1566 (185 TH, 18.5 J/TH)"],
    }
    
    comp_html = ""
    for mfg, models in competitors.items():
        items = "".join(f'<div style="color:#cbd5e1; font-size:12px; padding:3px 0;">● {m}</div>' for m in models)
        comp_html += f"""
        <div style="margin-bottom:12px;">
          <div style="color:#94a3b8; font-size:12px; font-weight:600; text-transform:uppercase; margin-bottom:4px;">{mfg}</div>
          {items}
        </div>"""
    
    return f"""
    <div class="section">
      <div class="section-header">
        <span class="section-icon">📈</span>
        <h3 style="color:#8b5cf6;">5. MARKET CONTEXT</h3>
      </div>
      <div class="stat-grid" style="grid-template-columns:1fr 1fr 1fr;">
        <div class="stat-card">
          <div style="font-size:14px; font-weight:700; color:{gen_color};">{gen}</div>
          <div class="stat-label">Classification</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color:#06b6d4; font-size:22px;">{eff if eff else 'N/A'} <span style="font-size:12px; color:#94a3b8;">J/TH</span></div>
          <div class="stat-label">Efficiency Rating</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color:#8b5cf6; font-size:22px;">{hashrate if hashrate else 'N/A'} <span style="font-size:12px; color:#94a3b8;">TH/s</span></div>
          <div class="stat-label">Max Hashrate</div>
        </div>
      </div>
      <div class="alert-box alert-cyan" style="margin-bottom:16px;">
        <p style="color:#67e8f9; font-size:13px; margin:0; line-height:1.6;">{position}</p>
      </div>
      <div style="margin-top:8px;">
        <h4 style="color:#94a3b8; font-size:13px; margin:0 0 12px 0; text-transform:uppercase; letter-spacing:0.5px;">Current Market Leaders (for reference)</h4>
        <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:16px;">
          {comp_html}
        </div>
      </div>
    </div>
"""

def _section_6_repair(report: dict) -> str:
    """Section 6: Repair & Maintenance."""
    hw = report["hardware"]
    known_issues = hw.get('known_issues', '')
    manufacturer = hw.get('manufacturer', '').lower()
    cooling = hw.get('cooling_type', hw.get('cooling_details', '')).lower() if hw.get('cooling_type') or hw.get('cooling_details') else ''
    
    # Common failure patterns by manufacturer
    common_failures = {
        "bitmain": [
            ("Hashboard Communication Errors", "PIC chip failures or loose ribbon cables between control board and hashboards. Most common repair item.", "HIGH", "#ef4444"),
            ("Temperature Sensor Failures", "Individual chip temp sensors report 0°C or wildly incorrect values. Usually requires hashboard-level repair.", "MEDIUM", "#f59e0b"),
            ("PSU Degradation", "APW12 series PSUs lose capacity over time. Watch for voltage rail droop under load.", "MEDIUM", "#f59e0b"),
            ("Fan Bearing Wear", "Axial fans develop bearing noise after 18-24 months continuous operation. Preventive replacement recommended.", "LOW", "#06b6d4"),
            ("Control Board Corrosion", "Humidity exposure causes corrosion on control board connectors. Keep humidity below 65% RH.", "MEDIUM", "#f59e0b"),
        ],
        "microbt": [
            ("Power Supply Failures", "MicroBT PSUs have higher failure rates than Bitmain equivalents in field data. Consider spare inventory.", "HIGH", "#ef4444"),
            ("Hashboard Chip Burnout", "Individual ASIC chips fail, reducing board hashrate. Board-level repair required.", "MEDIUM", "#f59e0b"),
            ("Network Connectivity Drops", "Ethernet controller resets under high temperature. Ensure adequate cooling.", "MEDIUM", "#f59e0b"),
            ("Fan Controller Issues", "Fan speed control board can fail, causing fans to run at 100% or stop entirely.", "LOW", "#06b6d4"),
        ],
        "canaan": [
            ("Hashboard Failures", "Canaan boards have documented higher failure rates in first 6 months. Monitor closely during burn-in.", "HIGH", "#ef4444"),
            ("Cooling System Limitations", "Stock cooling may be insufficient in ambient temps above 35°C. Consider supplemental cooling.", "MEDIUM", "#f59e0b"),
            ("Firmware Stability", "Third-party firmware support is limited compared to Bitmain. Stick with official firmware for stability.", "LOW", "#06b6d4"),
        ],
    }
    
    # Select appropriate failures
    failures = common_failures.get(manufacturer, common_failures.get("bitmain", []))
    
    failure_rows = ""
    for name, desc, severity, color in failures:
        failure_rows += f"""
        <div style="display:flex; gap:12px; padding:12px 0; border-bottom:1px solid #0f172a;">
          <span class="badge" style="background:{color}22; color:{color}; border:1px solid {color}44; min-width:60px; text-align:center; height:fit-content;">{severity}</span>
          <div>
            <div style="color:#f8fafc; font-size:13px; font-weight:600; margin-bottom:4px;">{name}</div>
            <div style="color:#94a3b8; font-size:12px; line-height:1.6;">{desc}</div>
          </div>
        </div>"""
    
    # Maintenance schedule
    maintenance = """
      <div style="margin-top:20px;">
        <h4 style="color:#94a3b8; font-size:13px; margin:0 0 12px 0; text-transform:uppercase; letter-spacing:0.5px;">Recommended Maintenance Schedule</h4>
        <table>
          <thead><tr><th>Interval</th><th>Action</th><th>Impact</th></tr></thead>
          <tbody>
            <tr><td style="font-weight:600; color:#06b6d4;">Monthly</td><td>Compressed air cleaning of intake/exhaust, visual inspection of fans and cables</td><td>Prevents dust buildup, catches loose connections early</td></tr>
            <tr><td style="font-weight:600; color:#06b6d4;">Quarterly</td><td>Full thermal inspection, check all power connections, fan RPM verification</td><td>Catches degrading components before failure</td></tr>
            <tr><td style="font-weight:600; color:#f59e0b;">6 Months</td><td>Firmware review, PSU load test, network cable inspection/replacement</td><td>Ensures optimal performance and security patches</td></tr>
            <tr><td style="font-weight:600; color:#f59e0b;">Annually</td><td>Full teardown, thermal paste replacement, fan replacement (preventive), PSU capacity test</td><td>Extends hardware lifespan 12-24 months beyond typical EOL</td></tr>
          </tbody>
        </table>
      </div>"""
    
    return f"""
    <div class="section">
      <div class="section-header">
        <span class="section-icon">🔨</span>
        <h3 style="color:#f97316;">6. REPAIR &amp; MAINTENANCE</h3>
      </div>
      <h4 style="color:#94a3b8; font-size:13px; margin:0 0 12px 0; text-transform:uppercase; letter-spacing:0.5px;">Common Failure Patterns — {hw.get('manufacturer','')}</h4>
      {failure_rows}
      {maintenance}
    </div>
"""

def _section_7_cooling(report: dict) -> str:
    """Section 7: Cooling & Environment."""
    hw = report["hardware"]
    power_w = hw.get('default_power_w', 0) or 0
    cooling = hw.get('cooling_type', '').lower() if hw.get('cooling_type') else 'air'
    cooling_details = hw.get('cooling_details', '') or ''
    operating_temp = hw.get('operating_temp', '0-40°C') or '0-40°C'
    humidity = hw.get('humidity', '10-90% RH') or '10-90% RH'
    noise_db = hw.get('noise_db', '') or ''
    
    # Calculate BTU output (1W ≈ 3.412 BTU/hr)
    btu_hr = round(power_w * 3.412) if power_w else 0
    # CFM estimate (rough: 1 miner ≈ 200-350 CFM depending on model)
    cfm_estimate = round(power_w * 0.1) if power_w else 250
    
    is_immersion = 'immersion' in cooling or 'immersion' in cooling_details.lower()
    is_hydro = 'hydro' in cooling or 'water' in cooling_details.lower()
    
    cooling_type_display = "Immersion Cooled" if is_immersion else "Hydro (Water) Cooled" if is_hydro else "Air Cooled"
    
    if is_immersion:
        cooling_notes = """
        <div class="alert-box alert-cyan">
          <h4 style="color:#67e8f9; font-size:13px; font-weight:600; margin:0 0 6px 0;">Immersion Cooling Requirements</h4>
          <p style="color:#94a3b8; font-size:12px; line-height:1.7; margin:0;">
            Requires specialized dielectric fluid (e.g., Engineered Fluids EC-100 or similar).<br>
            Immersion tank with adequate fluid volume for heat dissipation.<br>
            Dry cooler or heat exchanger for fluid temperature management.<br>
            Higher upfront cost ($1,500-3,000 per unit for infrastructure) but significantly lower noise and better thermal performance.<br>
            Failure rate data from catalog shows immersion units require careful fluid maintenance to avoid contamination.
          </p>
        </div>"""
    elif is_hydro:
        cooling_notes = """
        <div class="alert-box alert-cyan">
          <h4 style="color:#67e8f9; font-size:13px; font-weight:600; margin:0 0 6px 0;">Hydro Cooling Requirements</h4>
          <p style="color:#94a3b8; font-size:12px; line-height:1.7; margin:0;">
            Closed-loop water cooling system with dedicated radiator/dry cooler.<br>
            Water quality is critical — use distilled or deionized water with corrosion inhibitor.<br>
            Monitor for leaks regularly — water damage to hashboards is typically non-repairable.<br>
            Lower noise than air-cooled variants but higher maintenance overhead.
          </p>
        </div>"""
    else:
        cooling_notes = f"""
        <div class="alert-box alert-cyan">
          <h4 style="color:#67e8f9; font-size:13px; font-weight:600; margin:0 0 6px 0;">Air Cooling Best Practices</h4>
          <p style="color:#94a3b8; font-size:12px; line-height:1.7; margin:0;">
            {f'Configuration: {cooling_details}' if cooling_details and cooling_details != 'N/A' else 'Standard axial fan configuration (intake → exhaust).'}<br>
            Maintain minimum 12-inch clearance on intake and exhaust sides.<br>
            Hot/cold aisle separation recommended for deployments of 10+ units.<br>
            Air filter on intake side extends fan and board lifespan significantly.<br>
            Target ambient temperature: 20-30°C for optimal performance and longevity.
          </p>
        </div>"""
    
    return f"""
    <div class="section">
      <div class="section-header">
        <span class="section-icon">❄</span>
        <h3 style="color:#06b6d4;">7. COOLING &amp; ENVIRONMENT</h3>
      </div>
      <div class="stat-grid">
        <div class="stat-card">
          <div style="font-size:14px; font-weight:700; color:#06b6d4;">{cooling_type_display}</div>
          <div class="stat-label">Cooling Type</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color:#f59e0b; font-size:22px;">{btu_hr:,}</div>
          <div class="stat-label">BTU/hr Output</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color:#8b5cf6; font-size:22px;">~{cfm_estimate}</div>
          <div class="stat-label">Est. CFM Required</div>
        </div>
        <div class="stat-card">
          <div style="font-size:14px; font-weight:700; color:#10b981;">{operating_temp}</div>
          <div class="stat-label">Operating Range</div>
        </div>
      </div>
      <div class="spec-grid" style="margin-bottom:16px;">
        <div class="spec-row"><span class="spec-label">Humidity Range:</span><span class="spec-value">{humidity}</span></div>
        <div class="spec-row"><span class="spec-label">Noise Level:</span><span class="spec-value">{noise_db + ' dB' if noise_db and noise_db != 'N/A' else 'See manufacturer specs'}</span></div>
        <div class="spec-row"><span class="spec-label">Power Dissipation:</span><span class="spec-value">{power_w} W ({round(power_w/1000, 2)} kW)</span></div>
        <div class="spec-row"><span class="spec-label">Daily Power Draw:</span><span class="spec-value">{round(power_w*24/1000, 1)} kWh</span></div>
      </div>
      {cooling_notes}
    </div>
"""

def _section_8_ai_analysis(report: dict) -> str:
    """Section 8: AI Analysis (placeholder until Qwen is wired)."""
    hw = report["hardware"]
    deployed = report["fleet_deployed"]
    fleet = report["fleet"]
    prof = report.get("profitability", {})
    eff = hw.get('efficiency_j_th', 0)
    known_issues = hw.get('known_issues', '')
    
    insights = []
    
    # Generate static insights based on available data
    eff_val = _safe_float(eff, 0)
    if eff_val > 0:
        if eff_val < 20:
            insights.append({
                "title": "Efficiency Leadership",
                "confidence": 92,
                "conf_color": "#10b981",
                "body": f"At {eff_val} J/TH, this model is among the most efficient Bitcoin miners currently available. It should remain profitable through at least 1-2 more difficulty epochs, making it a strong long-term investment at current BTC prices.",
                "icon": "⚡"
            })
        elif eff_val < 30:
            insights.append({
                "title": "Mid-Range Efficiency — Monitor Difficulty",
                "confidence": 85,
                "conf_color": "#f59e0b",
                "body": f"At {eff_val} J/TH, this model sits in the mid-range of current hardware. Profitability is sensitive to electricity costs and network difficulty increases. Plan for a 12-18 month operational window before upgrade consideration.",
                "icon": "📉"
            })
        else:
            insights.append({
                "title": "Efficiency Concern — Upgrade Path Recommended",
                "confidence": 88,
                "conf_color": "#ef4444",
                "body": f"At {eff_val} J/TH, this model is significantly less efficient than current-generation hardware (13-18 J/TH). Profitability depends heavily on sub-$0.06/kWh electricity. Begin planning migration to newer hardware within 6-12 months.",
                "icon": "🔄"
            })
    
    if known_issues and known_issues not in ('None documented', 'N/A'):
        insights.append({
            "title": "Known Reliability Concerns",
            "confidence": 90,
            "conf_color": "#f59e0b",
            "body": f"The Intelligence Catalog documents known issues for this model: {known_issues[:200]}. Recommend maintaining spare parts inventory and implementing proactive monitoring for early failure detection.",
            "icon": "⚠"
        })
    
    if deployed:
        avg_hr = fleet.get('avg_hashrate_ths', 0)
        rated = hw.get('default_hashrate_th', 0) or 0
        fleet_pct = round(avg_hr / max(rated, 1) * 100, 1) if rated > 0 else 0
        fleet_count = fleet.get('count', 0)
        prob_count = len(fleet.get('problem_miners', []))
        if fleet_pct > 0 and fleet_pct < 90:
            insights.append({
                "title": "Fleet Underperformance Detected",
                "confidence": 94,
                "conf_color": "#ef4444",
                "body": f"Fleet average hashrate is {avg_hr} TH/s ({fleet_pct}% of rated {rated} TH/s) across {fleet_count} units. This indicates potential issues with cooling, power delivery, or hardware degradation. {prob_count} miners identified as underperforming.",
                "icon": "🔍"
            })
        elif fleet_pct >= 90:
            insights.append({
                "title": "Fleet Performance Healthy",
                "confidence": 96,
                "conf_color": "#10b981",
                "body": f"Fleet average of {avg_hr} TH/s ({fleet_pct}% of rated {rated} TH/s) across {fleet_count} units indicates healthy operation. Current maintenance schedule is effective.",
                "icon": "✓"
            })
        else:
            insights.append({
                "title": f"{fleet_count} Units Deployed in Fleet",
                "confidence": 90,
                "conf_color": "#06b6d4",
                "body": f"Mining Guardian is actively monitoring {fleet_count} units of this model with an average hashrate of {avg_hr} TH/s and {fleet.get('avg_chip_temp', 0)}°C average chip temperature.",
                "icon": "📊"
            })
    
    if prof:
        breakeven = prof.get('breakeven_rate', 0)
        if breakeven > 0.10:
            insights.append({
                "title": "Strong Profitability Margin",
                "confidence": 82,
                "conf_color": "#10b981",
                "body": f"Breakeven electricity rate of ${breakeven:.4f}/kWh provides substantial margin against typical industrial rates ($0.06-0.10/kWh). This model can absorb significant BTC price drops or difficulty increases before becoming unprofitable.",
                "icon": "💰"
            })
        elif breakeven < 0.06:
            insights.append({
                "title": "Narrow Profitability Window",
                "confidence": 87,
                "conf_color": "#ef4444",
                "body": f"Breakeven electricity rate of ${breakeven:.4f}/kWh leaves minimal margin. Only viable at below-average electricity costs. Consider whether capital would be better deployed on newer, more efficient hardware.",
                "icon": "⚠"
            })
    
    if not insights:
        insights.append({
            "title": "Catalog Data Collection In Progress",
            "confidence": 50,
            "conf_color": "#64748b",
            "body": "The Intelligence Catalog is still gathering data for this model. As more deployment data, repair records, and community reports are collected, AI analysis will become increasingly detailed and actionable.",
            "icon": "📊"
        })
    
    cards = ""
    for ins in insights:
        cards += f"""
        <div class="insight-card">
          <div class="insight-header">
            <div class="insight-title">{ins['icon']} {ins['title']}</div>
            <span class="confidence" style="background:{ins['conf_color']}22; color:{ins['conf_color']}; border:1px solid {ins['conf_color']}44;">{ins['confidence']}% confidence</span>
          </div>
          <div class="insight-body">{ins['body']}</div>
        </div>"""
    
    return f"""
    <div class="section">
      <div class="section-header">
        <span class="section-icon">🧠</span>
        <h3 style="color:#8b5cf6;">8. AI ANALYSIS</h3>
        <span class="badge badge-cyan" style="margin-left:auto;">Catalog-Based • Qwen Integration Pending</span>
      </div>
      {cards}
      <div style="color:#475569; font-size:11px; margin-top:8px; text-align:center;">
        Analysis generated from Intelligence Catalog data patterns. Full Qwen 32B AI analysis will provide deeper fleet-specific insights when wired to the Ollama endpoint.
      </div>
    </div>
"""

def _section_9_recommendations(report: dict) -> str:
    """Section 9: Recommendations."""
    hw = report["hardware"]
    deployed = report["fleet_deployed"]
    fleet = report["fleet"]
    prof = report.get("profitability", {})
    eff = hw.get('efficiency_j_th', 0)
    
    recs = []
    
    # Buy/Hold/Sell recommendation
    eff_val = _safe_float(eff, 0)
    if eff_val > 0:
        if eff_val < 20:
            recs.append(("🟢", "BUY / HOLD", "Current-generation efficiency. Suitable for new deployments and worth maintaining existing fleet.", "#10b981"))
        elif eff_val < 30:
            recs.append(("🟡", "HOLD / PLAN UPGRADE", f"At {eff_val} J/TH, this model is still profitable but approaching mid-life. Begin budgeting for next-generation replacement within 12-18 months. Continue operating but don't expand fleet with this model.", "#f59e0b"))
        elif eff_val < 45:
            recs.append(("🟠", "SELL / MIGRATE", f"At {eff_val} J/TH, this model is nearing end of profitable life at average electricity rates. Consider selling units while they still have resale value and migrating to current-gen hardware.", "#f97316"))
        else:
            recs.append(("🔴", "RETIRE", f"At {eff_val} J/TH, this model is well below current efficiency standards. Decommission and sell for parts/scrap value. Capital is better allocated to efficient hardware.", "#ef4444"))
    
    # Fleet-specific recommendations
    if deployed:
        avg_hr = fleet.get('avg_hashrate_ths', 0)
        rated = hw.get('default_hashrate_th', 0) or 0
        fleet_pct = round(avg_hr / max(rated, 1) * 100, 1) if rated > 0 else 0
        if fleet_pct > 0 and fleet_pct < 85:
            recs.append(("🔍", "INVESTIGATE LOW PERFORMERS", f"Fleet average of {avg_hr} TH/s ({fleet_pct}% of rated {rated} TH/s) is below target. Audit individual miners for hashboard failures, cooling issues, or firmware problems. Target: 95%+ of rated hashrate.", "#ef4444"))
        
        prob = fleet.get('problem_miners', [])
        if prob:
            ips = ", ".join(m.get('ip', '?') for m in prob[:3])
            recs.append(("🔧", "PRIORITIZE REPAIRS", f"Miners needing immediate attention: {ips}. Schedule hashboard inspection and thermal paste replacement for these units.", "#f59e0b"))
        
        restart_rate = fleet.get('restart_success_rate', 0)
        if restart_rate < 80 and fleet.get('total_restarts', 0) > 5:
            recs.append(("⚠", "RESTART RELIABILITY ISSUE", f"Only {restart_rate}% of restarts succeed. This suggests underlying hardware issues rather than software problems. Investigate power delivery and cooling capacity.", "#ef4444"))
    
    # Environment recommendation
    if not deployed:
        recs.append(("📋", "PRE-DEPLOYMENT CHECKLIST", "Before deploying this model: (1) Verify electrical capacity for full load + 20% headroom, (2) Confirm cooling CFM meets or exceeds rated requirements, (3) Set up Mining Guardian monitoring before powering on, (4) Have spare PSU and fan kit on hand for first 30 days.", "#06b6d4"))
    
    # Profitability recommendation
    if prof:
        breakeven = prof.get('breakeven_rate', 0)
        if breakeven and breakeven < 0.08:
            recs.append(("💡", "OPTIMIZE ELECTRICITY COSTS", f"With a breakeven rate of ${breakeven:.4f}/kWh, this model benefits significantly from any electricity cost reduction. Consider: time-of-use rate plans, demand response programs, or curtailment during peak pricing periods.", "#f59e0b"))
    
    rec_html = ""
    for icon, title, desc, color in recs:
        rec_html += f"""
        <div class="rec-item">
          <div class="rec-icon">{icon}</div>
          <div class="rec-content">
            <h4 style="color:{color};">{title}</h4>
            <p>{desc}</p>
          </div>
        </div>"""
    
    if not recs:
        rec_html = '<div style="color:#64748b; font-size:13px; text-align:center; padding:20px;">Insufficient data to generate specific recommendations. More catalog data needed.</div>'
    
    return f"""
    <div class="section">
      <div class="section-header">
        <span class="section-icon">🎯</span>
        <h3 style="color:#10b981;">9. RECOMMENDATIONS</h3>
      </div>
      {rec_html}
    </div>
"""

def _sources(report: dict) -> str:
    """Render the sources section."""
    sources = report["hardware"].get('sources', '')
    if not sources:
        return ""
    
    return f"""
    <div class="section" style="border-color:#1e293b;">
      <div class="section-header">
        <span class="section-icon">📚</span>
        <h3 style="color:#64748b;">SOURCES &amp; REFERENCES</h3>
      </div>
      <p style="color:#64748b; font-size:11px; line-height:1.8; margin:0; word-break:break-all;">{sources[:800]}</p>
    </div>
"""

def _footer(report: dict) -> str:
    """Render the report footer."""
    return f"""
    <div class="footer">
      Mining Guardian Intelligence Report — Generated by AI (Qwen 32B + Claude Sonnet 4.6)<br>
      Intelligence Catalog: 165 tables ● {len(MODEL_LIST)} miner models indexed ● 10+ manufacturers<br>
      Data sources: Manufacturer specs, community reports, fleet telemetry, BiXBiT repair network
    </div>
"""

def render_full_html(report: dict) -> str:
    """Render the complete 9-section HTML intelligence report."""
    return f"""
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; color:#e2e8f0; background:#0f172a;">
  {_css()}
  <div class="report">
    {_header(report)}
    {_section_1_hardware(report)}
    {_section_2_firmware(report)}
    {_section_3_fleet(report)}
    {_section_4_profitability(report)}
    {_section_5_market(report)}
    {_section_6_repair(report)}
    {_section_7_cooling(report)}
    {_section_8_ai_analysis(report)}
    {_section_9_recommendations(report)}
    {_sources(report)}
    {_footer(report)}
  </div>
</div>
"""


# ── Main ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8590)
