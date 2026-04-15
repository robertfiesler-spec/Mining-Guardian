#!/usr/bin/env python3
"""
intelligence_report_api.py
Mining Guardian — Miner Intelligence Report API

Serves pre-built intelligence report data for any miner model.
Data sources: unified_miner_index.json + miner_enrichment_master.csv + miner_specs.json + guardian.db
Consumed by Grafana Business Text panels via JSON datasource.

Runs on: http://localhost:8590

Endpoints:
  GET /api/report/models          → list of all models (for Grafana variable dropdown)
  GET /api/report/search?q=...    → search models by partial name
  GET /api/report/{slug}          → full intelligence report data for a model
  GET /health                     → health check
"""

import json, csv, os, re, sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ── Configuration ─────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
REPO_DIR = BASE_DIR  # On VPS this would be the repo root
GUARDIAN_DB = os.environ.get("GUARDIAN_DB", str(REPO_DIR / "guardian.db"))
# On VPS: API runs from repo root, data lives in intelligence-catalog/data/
_DATA_DIR = REPO_DIR / "intelligence-catalog" / "data"
ENRICHMENT_CSV = str(_DATA_DIR / "miner_enrichment_master.csv")
SPECS_JSON = str(REPO_DIR / "miner_specs.json")
INDEX_JSON = str(_DATA_DIR / "unified_miner_index.json")

# ── App Setup ─────────────────────────────────────────────────
app = FastAPI(title="Mining Guardian Intelligence Report API", version="1.0.0")
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

# Load data at startup
UNIFIED_INDEX = load_unified_index()
ENRICHMENT = load_enrichment()
SPECS = load_specs()

# Build search-friendly list
MODEL_LIST = []
for slug, info in sorted(UNIFIED_INDEX.items()):
    display = info.get('display_name', slug)
    mfg = info.get('manufacturer', 'unknown').title()
    # Extract hashrate from entity if available
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
    
    MODEL_LIST.append({
        "slug": slug,
        "display_name": display,
        "manufacturer": mfg,
        "hashrate": hashrate,
        "label": f"{mfg} {display}" + (f" ({hashrate})" if hashrate else "")
    })

print(f"Loaded {len(MODEL_LIST)} miner models for Intelligence Reports")


# ── Guardian DB helpers ───────────────────────────────────────
def get_fleet_data(model_pattern: str) -> dict:
    """Query guardian.db for fleet operational data matching a model pattern."""
    if not os.path.exists(GUARDIAN_DB):
        return {"deployed": False, "reason": "guardian.db not found"}
    
    try:
        conn = sqlite3.connect(GUARDIAN_DB, timeout=5)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # Find miners matching this model
        cur.execute("""
            SELECT ip, model, status, hashrate_pct, chip_temp, 
                   last_scan_ts, flagged_count, dead_boards
            FROM miners 
            WHERE LOWER(model) LIKE ?
            ORDER BY ip
        """, (f"%{model_pattern}%",))
        miners = [dict(r) for r in cur.fetchall()]
        
        if not miners:
            conn.close()
            return {"deployed": False, "count": 0}
        
        # Get fleet averages
        total = len(miners)
        online = sum(1 for m in miners if m.get('status') == 'online')
        offline = total - online
        avg_hashrate = sum(m.get('hashrate_pct', 0) or 0 for m in miners) / max(total, 1)
        avg_temp = sum(m.get('chip_temp', 0) or 0 for m in miners if m.get('chip_temp', 0) > 0)
        temp_count = sum(1 for m in miners if (m.get('chip_temp', 0) or 0) > 0)
        avg_temp = avg_temp / max(temp_count, 1)
        
        # Get restart stats
        cur.execute("""
            SELECT COUNT(*) as total_restarts,
                   SUM(CASE WHEN outcome = 'SUCCESS' THEN 1 ELSE 0 END) as successes
            FROM miner_restarts 
            WHERE LOWER(miner_ip) IN ({})
        """.format(",".join(f"'{m['ip']}'" for m in miners)))
        restart_row = cur.fetchone()
        total_restarts = restart_row['total_restarts'] if restart_row else 0
        successes = restart_row['successes'] if restart_row else 0
        
        # Top/bottom performers
        sorted_miners = sorted(miners, key=lambda m: m.get('hashrate_pct', 0) or 0, reverse=True)
        top_3 = sorted_miners[:3]
        bottom_3 = [m for m in sorted_miners[-3:] if (m.get('hashrate_pct', 0) or 0) < 90]
        
        conn.close()
        
        return {
            "deployed": True,
            "count": total,
            "online": online,
            "offline": offline,
            "avg_hashrate_pct": round(avg_hashrate, 1),
            "avg_chip_temp": round(avg_temp, 1),
            "total_restarts": total_restarts,
            "restart_success_rate": round(successes / max(total_restarts, 1) * 100, 1),
            "top_performers": top_3,
            "problem_miners": bottom_3,
            "all_miners": miners
        }
    except Exception as e:
        return {"deployed": False, "error": str(e)}


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
    # Build a search pattern from the display name
    model_search = display_name.split('(')[0].strip()
    # Simplify for DB matching
    model_search_parts = model_search.lower().replace('-', '').replace('+', '')
    fleet = get_fleet_data(model_search_parts)
    
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
    return {"status": "ok", "models": len(MODEL_LIST), "version": "1.0.0"}

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
        return MODEL_LIST[:50]  # Return first 50 if no query
    
    q_lower = q.lower()
    results = [
        m for m in MODEL_LIST
        if q_lower in m["label"].lower() or q_lower in m["slug"]
    ]
    return results[:50]

@app.get("/api/report/{slug}")
def get_report(slug: str):
    """Get full intelligence report for a miner model."""
    report = build_report(slug)
    if not report:
        # Try fuzzy match
        slug_lower = slug.lower().replace(' ', '-').replace('+', 'plus')
        report = build_report(slug_lower)
    if not report:
        return JSONResponse(status_code=404, content={"error": f"Model '{slug}' not found", "available": len(MODEL_LIST)})
    return report

@app.get("/api/report/{slug}/html")
def get_report_html(slug: str):
    """Get intelligence report rendered as HTML for Grafana text panel."""
    report = build_report(slug)
    if not report:
        slug_lower = slug.lower().replace(' ', '-').replace('+', 'plus')
        report = build_report(slug_lower)
    if not report:
        return JSONResponse(
            status_code=404,
            content={"html": f"<div style='color:#ff6b6b; padding:20px; font-size:16px;'>Model '{slug}' not found in Intelligence Catalog ({len(MODEL_LIST)} models available)</div>"}
        )
    
    hw = report["hardware"]
    fleet = report["fleet"]
    deployed = report["fleet_deployed"]
    
    # Build the HTML report
    badge_color = "#10b981" if deployed else "#f59e0b"
    badge_text = "DEPLOYED IN FLEET" if deployed else "CATALOG DATA ONLY"
    
    # Header
    html = f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #e2e8f0; padding: 20px; max-width: 1200px; margin: 0 auto;">
  
  <div style="text-align: center; margin-bottom: 30px;">
    <h1 style="font-size: 28px; font-weight: 700; color: #f8fafc; margin: 0 0 4px 0; letter-spacing: -0.5px;">MINER INTELLIGENCE REPORT</h1>
    <h2 style="font-size: 20px; font-weight: 600; color: #06b6d4; margin: 0 0 12px 0;">{hw.get('manufacturer', '')} {hw.get('model', '')} — {report['report_type']}</h2>
    <span style="display: inline-block; background: {badge_color}22; color: {badge_color}; border: 1px solid {badge_color}44; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: 600; letter-spacing: 0.5px;">{badge_text}</span>
    <div style="color: #94a3b8; font-size: 13px; margin-top: 8px;">
      Generated: {report['generated_at']}<br>
      Data Sources: Intelligence Catalog ({report['data_sources']['catalog_tables']} tables)
      {' + Guardian Fleet Database' if deployed else ''}
    </div>
  </div>
"""
    
    # ── Hardware Specifications Section ──
    html += """
  <div style="background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
    <h3 style="color: #06b6d4; font-size: 16px; margin: 0 0 16px 0; border-bottom: 1px solid #334155; padding-bottom: 8px;">1. HARDWARE SPECIFICATIONS</h3>
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px 32px;">
"""
    
    spec_fields = [
        ("Manufacturer", hw.get('manufacturer', 'N/A')),
        ("Model", hw.get('model', 'N/A')),
        ("Algorithm", hw.get('algorithm', 'SHA-256')),
        ("Cooling", hw.get('cooling_type', hw.get('cooling_details', 'N/A'))),
        ("Release Date", hw.get('release_date', 'N/A')),
        ("Hashrate", f"{hw.get('default_hashrate_th', 'N/A')} TH/s" if hw.get('default_hashrate_th') else 'N/A'),
        ("Power", f"{hw.get('default_power_w', 'N/A')} W" if hw.get('default_power_w') else 'N/A'),
        ("Efficiency", f"{hw.get('efficiency_j_th', 'N/A')} J/TH" if hw.get('efficiency_j_th') else 'N/A'),
        ("Dimensions", hw.get('dimensions', 'N/A')),
        ("Weight", f"{hw.get('weight_kg', 'N/A')} kg" if hw.get('weight_kg') and hw.get('weight_kg') != 'N/A' else 'N/A'),
        ("Operating Temp", hw.get('operating_temp', 'N/A')),
        ("Noise", f"{hw.get('noise_db', 'N/A')} dB" if hw.get('noise_db') and hw.get('noise_db') != 'N/A' else 'N/A'),
        ("Network", hw.get('network', 'N/A')),
        ("PSU", hw.get('psu_requirements', 'N/A')),
        ("Voltage Range", hw.get('voltage_range', 'N/A')),
        ("Warranty", hw.get('warranty', 'N/A')),
    ]
    
    for label, value in spec_fields:
        if value and value != 'N/A' and value != 'None TH/s' and value != 'None W' and value != 'None J/TH' and value != 'None kg':
            val_display = str(value)[:120]
            html += f"""
      <div style="display: flex; padding: 4px 0; border-bottom: 1px solid #1e293b;">
        <span style="color: #94a3b8; font-size: 13px; min-width: 130px; font-weight: 500;">{label}:</span>
        <span style="color: #e2e8f0; font-size: 13px; font-weight: 600;">{val_display}</span>
      </div>"""
    
    html += """
    </div>
  </div>
"""
    
    # ── Variants (if available) ──
    variants = hw.get('variants', [])
    if variants:
        html += """
  <div style="background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
    <h3 style="color: #06b6d4; font-size: 16px; margin: 0 0 16px 0; border-bottom: 1px solid #334155; padding-bottom: 8px;">1.1 MODEL VARIANTS</h3>
    <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
      <thead>
        <tr style="border-bottom: 2px solid #334155;">
          <th style="text-align: left; padding: 8px; color: #94a3b8;">Variant</th>
          <th style="text-align: right; padding: 8px; color: #94a3b8;">Hashrate</th>
          <th style="text-align: right; padding: 8px; color: #94a3b8;">Power</th>
          <th style="text-align: right; padding: 8px; color: #94a3b8;">Efficiency</th>
        </tr>
      </thead>
      <tbody>
"""
        for v in variants:
            html += f"""
        <tr style="border-bottom: 1px solid #1e293b55;">
          <td style="padding: 6px 8px; color: #e2e8f0; font-weight: 500;">{v.get('label', 'N/A')}</td>
          <td style="padding: 6px 8px; color: #e2e8f0; text-align: right;">{v.get('rated_ths', 'N/A')} TH/s</td>
          <td style="padding: 6px 8px; color: #e2e8f0; text-align: right;">{v.get('rated_watts', 'N/A')} W</td>
          <td style="padding: 6px 8px; color: #e2e8f0; text-align: right;">{v.get('efficiency_j_th', 'N/A')} J/TH</td>
        </tr>"""
        html += """
      </tbody>
    </table>
  </div>
"""
    
    # ── Firmware & Known Issues ──
    firmware = hw.get('firmware_support', '')
    known_issues = hw.get('known_issues', '')
    features = hw.get('distinguishing_features', '')
    
    if firmware or known_issues or features:
        html += """
  <div style="background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
    <h3 style="color: #06b6d4; font-size: 16px; margin: 0 0 16px 0; border-bottom: 1px solid #334155; padding-bottom: 8px;">2. FIRMWARE & KNOWN ISSUES</h3>
"""
        if firmware and firmware != 'N/A':
            html += f"""
    <div style="margin-bottom: 16px;">
      <h4 style="color: #e2e8f0; font-size: 14px; margin: 0 0 8px 0;">Firmware Support</h4>
      <p style="color: #cbd5e1; font-size: 13px; line-height: 1.6; margin: 0; white-space: pre-wrap;">{firmware[:800]}</p>
    </div>"""
        
        if known_issues and known_issues != 'None documented' and known_issues != 'N/A':
            html += f"""
    <div style="margin-bottom: 16px;">
      <h4 style="color: #f59e0b; font-size: 14px; margin: 0 0 8px 0;">⚠️ Known Issues</h4>
      <div style="background: #f59e0b11; border: 1px solid #f59e0b33; border-radius: 4px; padding: 12px;">
        <p style="color: #fbbf24; font-size: 13px; line-height: 1.6; margin: 0; white-space: pre-wrap;">{known_issues[:1000]}</p>
      </div>
    </div>"""
        
        if features and features != 'N/A':
            html += f"""
    <div style="margin-bottom: 8px;">
      <h4 style="color: #e2e8f0; font-size: 14px; margin: 0 0 8px 0;">Distinguishing Features</h4>
      <p style="color: #cbd5e1; font-size: 13px; line-height: 1.6; margin: 0; white-space: pre-wrap;">{features[:800]}</p>
    </div>"""
        
        html += """
  </div>
"""
    
    # ── Fleet Performance Section ──
    if deployed:
        html += f"""
  <div style="background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
    <h3 style="color: #10b981; font-size: 16px; margin: 0 0 16px 0; border-bottom: 1px solid #334155; padding-bottom: 8px;">3. FLEET OPERATIONAL PERFORMANCE</h3>
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px;">
      <div style="background: #0f172a; border-radius: 8px; padding: 16px; text-align: center;">
        <div style="font-size: 28px; font-weight: 700; color: #10b981;">{fleet.get('count', 0)}</div>
        <div style="font-size: 12px; color: #94a3b8; margin-top: 4px;">Total Deployed</div>
      </div>
      <div style="background: #0f172a; border-radius: 8px; padding: 16px; text-align: center;">
        <div style="font-size: 28px; font-weight: 700; color: #10b981;">{fleet.get('online', 0)}</div>
        <div style="font-size: 12px; color: #94a3b8; margin-top: 4px;">Online</div>
      </div>
      <div style="background: #0f172a; border-radius: 8px; padding: 16px; text-align: center;">
        <div style="font-size: 28px; font-weight: 700; color: #06b6d4;">{fleet.get('avg_hashrate_pct', 0)}%</div>
        <div style="font-size: 12px; color: #94a3b8; margin-top: 4px;">Avg Hashrate</div>
      </div>
      <div style="background: #0f172a; border-radius: 8px; padding: 16px; text-align: center;">
        <div style="font-size: 28px; font-weight: 700; color: #f59e0b;">{fleet.get('avg_chip_temp', 0)}°C</div>
        <div style="font-size: 12px; color: #94a3b8; margin-top: 4px;">Avg Chip Temp</div>
      </div>
    </div>
"""
        # Top performers
        top = fleet.get('top_performers', [])
        if top:
            html += """
    <h4 style="color: #10b981; font-size: 14px; margin: 16px 0 8px 0;">Top Performers</h4>
    <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
      <thead><tr style="border-bottom: 2px solid #334155;">
        <th style="text-align: left; padding: 6px; color: #94a3b8;">IP</th>
        <th style="text-align: right; padding: 6px; color: #94a3b8;">Hashrate %</th>
        <th style="text-align: right; padding: 6px; color: #94a3b8;">Chip Temp</th>
        <th style="text-align: center; padding: 6px; color: #94a3b8;">Status</th>
      </tr></thead><tbody>
"""
            for m in top:
                hr = m.get('hashrate_pct', 0) or 0
                hr_color = "#10b981" if hr >= 95 else "#f59e0b" if hr >= 85 else "#ef4444"
                status = m.get('status', 'unknown')
                status_color = "#10b981" if status == 'online' else "#ef4444"
                html += f"""
      <tr style="border-bottom: 1px solid #1e293b55;">
        <td style="padding: 6px; color: #e2e8f0; font-family: monospace;">{m.get('ip', 'N/A')}</td>
        <td style="padding: 6px; text-align: right; color: {hr_color}; font-weight: 600;">{hr:.1f}%</td>
        <td style="padding: 6px; text-align: right; color: #e2e8f0;">{m.get('chip_temp', 'N/A')}°C</td>
        <td style="padding: 6px; text-align: center; color: {status_color}; font-weight: 500;">{status.upper()}</td>
      </tr>"""
            html += "</tbody></table>"
        
        html += """
  </div>
"""
    else:
        html += f"""
  <div style="background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
    <h3 style="color: #f59e0b; font-size: 16px; margin: 0 0 16px 0; border-bottom: 1px solid #334155; padding-bottom: 8px;">3. FLEET OPERATIONAL PERFORMANCE</h3>
    <div style="background: #f59e0b11; border: 1px solid #f59e0b33; border-radius: 8px; padding: 20px; text-align: center;">
      <div style="font-size: 16px; color: #fbbf24; font-weight: 600; margin-bottom: 8px;">NOT DEPLOYED IN FLEET</div>
      <div style="color: #94a3b8; font-size: 13px;">This miner model is not currently deployed in your facility.<br>
      Report is based entirely on Intelligence Catalog reference data.</div>
      <div style="color: #94a3b8; font-size: 12px; margin-top: 12px;">
        When deployed, Mining Guardian will automatically:<br>
        • Detect the model via device fingerprinting<br>
        • Load the correct operating profile from the Catalog<br>
        • Begin building fleet-specific performance data within 24 hours
      </div>
    </div>
  </div>
"""
    
    # ── Sources ──
    sources = hw.get('sources', '')
    if sources:
        html += f"""
  <div style="background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
    <h3 style="color: #64748b; font-size: 14px; margin: 0 0 8px 0;">SOURCES</h3>
    <p style="color: #64748b; font-size: 11px; line-height: 1.6; margin: 0; word-break: break-all;">{sources[:600]}</p>
  </div>
"""
    
    html += """
  <div style="text-align: center; color: #475569; font-size: 11px; padding: 10px 0;">
    Mining Guardian Intelligence Report — Generated by AI (Qwen 32B + Claude Sonnet 4.6)<br>
    Intelligence Catalog: 165 tables • {model_count} miner models indexed
  </div>
</div>
""".replace("{model_count}", str(len(MODEL_LIST)))
    
    return {"html": html}


# ── Main ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8590)
