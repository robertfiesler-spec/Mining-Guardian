#!/usr/bin/env python3
"""
dashboard_api.py
Mining Guardian — Local Dashboard API

Serves pre-built queries from guardian.db as JSON endpoints.
Used by Retool dashboard and future custom React dashboard.
Also available to OpenClaw for AI context.

Usage:
    source venv/bin/activate
    python dashboard_api.py

Runs on: http://localhost:8585
"""

import sys
import sqlite3
import os
import json
import html as html_lib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# ── Path setup ────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT / "core"), str(_ROOT / "clients"), str(_ROOT / "monitoring")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

# ── Rate limiting (added Apr 21 2026) ─────────────────────────
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

# ── Prometheus metrics ────────────────────────────────────────
from prometheus_client import (
    Gauge, generate_latest, CONTENT_TYPE_LATEST, REGISTRY
)

# Per-miner gauges (labels: miner_ip, model, site, map_location)
g_hashrate_pct  = Gauge("mining_guardian_hashrate_pct",  "Hashrate % of rated",         ["miner_ip","model","site","map_location"])
g_temp_chip     = Gauge("mining_guardian_temp_chip",     "Chip temperature °C",          ["miner_ip","model","site","map_location"])
g_pdu_power_kw  = Gauge("mining_guardian_pdu_power_kw",  "PDU outlet power draw kW",    ["miner_ip","model","site","map_location"])
g_consumption_kw= Gauge("mining_guardian_consumption_kw","Miner-reported power draw kW (fallback when no PDU)", ["miner_ip","model","site"])
g_power_kw      = Gauge("mining_guardian_power_kw",      "Best available power kW (PDU if available, else miner-reported)", ["miner_ip","model","site"])
g_flagged       = Gauge("mining_guardian_flagged",       "1 if currently flagged",       ["miner_ip","model","site","map_location"])
g_dead_boards   = Gauge("mining_guardian_dead_boards",   "Known dead hashboards count",  ["miner_ip","model","site"])

# Per-board gauges (labels: miner_ip, board, site)
g_board_rate    = Gauge("mining_guardian_board_rate_ths",   "Board hashrate TH/s",       ["miner_ip","board","site"])
g_board_voltage = Gauge("mining_guardian_board_voltage",    "Board voltage V",            ["miner_ip","board","site"])
g_board_freq    = Gauge("mining_guardian_board_freq_mhz",   "Board frequency MHz",        ["miner_ip","board","site"])
g_board_power   = Gauge("mining_guardian_board_power_w",    "Board consumption W",        ["miner_ip","board","site"])
g_board_hwerr   = Gauge("mining_guardian_board_hw_errors",  "Board HW errors",            ["miner_ip","board","site"])
g_board_temp    = Gauge("mining_guardian_board_temp_c",     "Board temp °C",              ["miner_ip","board","site"])

# Pool gauges (labels: miner_ip, pool_url, site)
g_pool_accepted = Gauge("mining_guardian_pool_accepted",    "Pool accepted shares",       ["miner_ip","pool_url","site"])
g_pool_rejected = Gauge("mining_guardian_pool_rejected",    "Pool rejected shares",       ["miner_ip","pool_url","site"])
g_pool_reject_rate = Gauge("mining_guardian_pool_reject_rate", "Pool rejection rate %",   ["miner_ip","pool_url","site"])

# Fleet gauges
g_fleet_online   = Gauge("mining_guardian_fleet_online",  "Miners online count",  ["site"])
g_fleet_offline  = Gauge("mining_guardian_fleet_offline", "Miners offline count", ["site"])
g_fleet_issues   = Gauge("mining_guardian_fleet_issues",  "Miners with issues",   ["site"])

# HVAC gauges
g_hvac_supply    = Gauge("mining_guardian_hvac_supply_f",      "Supply water temp °F",       ["site"])
g_hvac_return    = Gauge("mining_guardian_hvac_return_f",      "Return water temp °F",       ["site"])
g_hvac_delta_t   = Gauge("mining_guardian_hvac_delta_t_f",     "Delta T °F",                 ["site"])
g_hvac_pressure  = Gauge("mining_guardian_hvac_diff_pressure", "Differential pressure PSI",  ["site"])
g_spray_pump     = Gauge("mining_guardian_spray_pump_on",      "Spray pump on 1/0",          ["site"])

# Environment gauges
g_outside_temp   = Gauge("mining_guardian_outside_temp_f", "Outside temp °F",   ["site"])
g_humidity       = Gauge("mining_guardian_humidity_pct",   "Outside humidity %", ["site"])

# ── Miner Health Score (MHS) metrics ─────────────────────────────────────────
# Formula: hashrate 35% + uptime 25% + efficiency 20% + hw_errors 15% + pool 5%
g_mhs              = Gauge("mining_guardian_mhs",
                            "Miner Health Score 0-100", ["miner_ip","model","site"])
g_hashrate_ths     = Gauge("mining_guardian_hashrate_ths",
                            "Actual hashrate TH/s", ["miner_ip","model","site"])
g_rated_ths        = Gauge("mining_guardian_rated_ths",
                            "Rated/spec hashrate TH/s", ["miner_ip","model","site"])
g_efficiency       = Gauge("mining_guardian_efficiency_ths_per_kw",
                            "Efficiency TH/s per kW", ["miner_ip","model","site"])
g_knowledge_insights  = Gauge("mining_guardian_knowledge_insights_total",
                               "Total insights in knowledge base", ["site"])
g_knowledge_patterns  = Gauge("mining_guardian_knowledge_patterns_total",
                               "Patterns identified by AI", ["site"])
g_knowledge_profiles  = Gauge("mining_guardian_knowledge_miner_profiles_total",
                               "Miner profiles in knowledge base", ["site"])
g_llm_scan_analyses   = Gauge("mining_guardian_llm_scan_analyses_total",
                               "Local LLM scan analyses in knowledge base", ["site"])
g_operator_rules      = Gauge("mining_guardian_operator_rules_total",
                               "Operator rules extracted from denials", ["site"])
g_knowledge_updated   = Gauge("mining_guardian_knowledge_last_updated_timestamp",
                               "Unix timestamp of last knowledge update", ["site"])
g_actions_approved    = Gauge("mining_guardian_actions_approved_total",
                               "Total approved actions (all time)", ["site"])
g_actions_denied      = Gauge("mining_guardian_actions_denied_total",
                               "Total denied actions (all time)", ["site"])
g_actions_auto        = Gauge("mining_guardian_actions_auto_overnight_total",
                               "Total auto-executed overnight actions (all time)", ["site"])
g_actions_expired     = Gauge("mining_guardian_actions_expired_total",
                               "Total auto-expired approvals (all time)", ["site"])
g_restarts_total      = Gauge("mining_guardian_restarts_total",
                               "Total restarts performed (all time)", ["site"])
g_tickets_total       = Gauge("mining_guardian_tickets_created_total",
                               "Total AMS tickets created by AI (all time)", ["site"])
g_knowledge_score     = Gauge("mining_guardian_knowledge_score",
                               "AI total score (0-1000)", ["site"])
g_ai_data_depth       = Gauge("mining_guardian_ai_data_depth",
                               "AI data depth score (0-200)", ["site"])
g_ai_knowledge        = Gauge("mining_guardian_ai_knowledge",
                               "AI knowledge score (0-200)", ["site"])
g_ai_experience       = Gauge("mining_guardian_ai_experience",
                               "AI experience score (0-200)", ["site"])
g_ai_accuracy         = Gauge("mining_guardian_ai_accuracy",
                               "AI accuracy score (0-200)", ["site"])
g_ai_autonomy         = Gauge("mining_guardian_ai_autonomy",
                               "AI autonomy score (0-200)", ["site"])

SITE = "usa_188"

DB_PATH = str(_ROOT / "guardian.db")
app = FastAPI(title="Mining Guardian API", version="1.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Allow Retool and any local client to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://dashboard.fieslerfamily.com",
        "https://grafana.fieslerfamily.com",
        "https://retool.com",
        "http://localhost:8585",
        "http://127.0.0.1:8585",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Chart HTML template ───────────────────────────────────────
ENVIRONMENT_CHART_HTML = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>Mining Guardian — Environment</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f8f9fa; padding: 24px; }
  h1 { font-size: 20px; color: #333; margin-bottom: 4px; }
  .sub { font-size: 13px; color: #888; margin-bottom: 16px; }
  .card { background: #fff; border-radius: 10px; padding: 20px;
          box-shadow: 0 1px 4px rgba(0,0,0,0.08); max-width: 1000px; }
  canvas { width: 100% !important; height: 350px !important; }
  .legend { display:flex; gap:20px; margin-top:12px; font-size:13px; }
  .legend span { display:flex; align-items:center; gap:5px; }
  .dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
</style>
</head><body>
<h1>Environment Monitor — 5 Day Trend</h1>
<p class="sub">Data points every scan cycle &bull; Auto-refreshes every 5 min</p>
<div class="card">
  <canvas id="chart"></canvas>
  <div class="legend">
    <span><i class="dot" style="background:#e67e22"></i> Outside Temp (&deg;F)</span>
    <span><i class="dot" style="background:#2980b9"></i> Supply Water (&deg;F)</span>
    <span><i class="dot" style="background:#c0392b"></i> Return Water (&deg;F)</span>
    <span><i class="dot" style="background:#27ae60"></i> Humidity (%)</span>
  </div>
</div>
<script>
async function load() {
  const r = await fetch('/facility/environment_history?days=5');
  const data = await r.json();
  const labels = data.map(d => d.recorded_at);
  new Chart(document.getElementById('chart'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label:'Outside Temp (°F)', data: data.map(d=>d.outside_temp_f),
          borderColor:'#e67e22', backgroundColor:'transparent', pointRadius:3,
          pointBackgroundColor:'#e67e22', tension:0.3, borderWidth:2 },
        { label:'Supply Water (°F)', data: data.map(d=>d.supply_temp_f),
          borderColor:'#2980b9', backgroundColor:'transparent', pointRadius:3,
          pointBackgroundColor:'#2980b9', tension:0.3, borderWidth:2 },
        { label:'Return Water (°F)', data: data.map(d=>d.return_temp_f),
          borderColor:'#c0392b', backgroundColor:'transparent', pointRadius:3,
          pointBackgroundColor:'#c0392b', tension:0.3, borderWidth:2 },
        { label:'Humidity (%)', data: data.map(d=>d.humidity_pct),
          borderColor:'#27ae60', backgroundColor:'transparent', pointRadius:3,
          pointBackgroundColor:'#27ae60', tension:0.3, borderWidth:2 },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { type:'time', time:{ unit:'hour', stepSize:6,
              displayFormats:{ hour:'MMM d ha' }},
             grid:{ color:'#f0f0f0' },
             ticks:{ maxRotation:45, font:{size:11} }},
        y: { grid:{ color:'#f0f0f0' },
             ticks:{ font:{size:11} }}
      },
      interaction: { intersect:false, mode:'index' }
    }
  });
}
load();
setInterval(load, 300000);
</script>
</body></html>"""

POWER_CHART_HTML = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>Mining Guardian — Warehouse Power</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f8f9fa;padding:24px}
  h1{font-size:20px;color:#333;margin-bottom:4px}
  .sub{font-size:13px;color:#888;margin-bottom:16px}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;max-width:1100px}
  .card{background:#fff;border-radius:10px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
  .card h2{font-size:15px;color:#555;margin-bottom:12px;border-bottom:2px solid #e0e0e0;padding-bottom:6px}
  .total{font-size:32px;font-weight:700;color:#333;margin:8px 0}
  .total small{font-size:14px;color:#888;font-weight:400}
  .total-bar{background:#f0f0f0;border-radius:8px;height:18px;margin:10px 0;overflow:hidden;display:flex}
  .total-bar span{height:100%;display:block;transition:width .5s}
  .outlet{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #f5f5f5}
  .outlet:last-child{border:none}
  .outlet .name{font-size:13px;color:#333;font-weight:500}
  .outlet .kw{font-size:15px;font-weight:600}
  .outlet .detail{font-size:11px;color:#999}
  .c1{color:#e67e22} .c2{color:#2980b9} .c3{color:#c0392b}
  .b1{background:#e67e22} .b2{background:#2980b9} .b3{background:#c0392b}
  .tank-info{font-size:13px;color:#666;margin-bottom:10px}
  .tank-info span{font-weight:600}
  #status{font-size:12px;color:#aaa;margin-top:12px}
</style>
</head><body>
<h1>Warehouse Power — Live</h1>
<p class="sub">Auto-refreshes every 30 seconds</p>
<div class="grid" id="grid"></div>
<p id="status">Loading...</p>
<script>
async function load(){
  try{
    const r=await fetch('/facility/power_live');
    const d=await r.json();
    const grid=document.getElementById('grid');
    grid.innerHTML='';

    // Total card
    const pcts=d.sources.map(s=>s.total_kw);
    const colors=['#e67e22','#2980b9','#c0392b'];
    let totalCard=`<div class="card"><h2>Total Warehouse</h2>
      <div class="total">${d.total_kw.toFixed(1)} kW <small>across ${d.sources.length} sources</small></div>
      <div class="total-bar">`;
    d.sources.forEach((s,i)=>{
      const pct=(s.total_kw/d.total_kw*100).toFixed(0);
      totalCard+=`<span class="b${i+1}" style="width:${pct}%" title="${s.name}: ${s.total_kw.toFixed(1)} kW"></span>`;
    });
    totalCard+=`</div>`;
    d.sources.forEach((s,i)=>{
      totalCard+=`<div class="outlet"><span class="name c${i+1}">${s.name.split('—')[0].trim()}</span><span class="kw c${i+1}">${s.total_kw.toFixed(1)} kW</span></div>`;
    });
    totalCard+=`</div>`;
    grid.innerHTML+=totalCard;

    // Per-source cards
    d.sources.forEach((s,i)=>{
      let card=`<div class="card"><h2>${s.name}</h2>`;
      if(s.fluid_in_c!=null){
        card+=`<div class="tank-info">Fluid: <span>in ${(s.fluid_in_c*9/5+32).toFixed(0)}°F</span> / <span>out ${(s.fluid_out_c*9/5+32).toFixed(0)}°F</span> | Pump: ${s.pump_running?'🟢 ON':'🔴 OFF'}</div>`;
      }
      const items=s.outlets||s.ports||[];
      items.forEach(o=>{
        const label=o.miner||'—';
        const num=o.outlet!=null?'Outlet '+o.outlet:'Port '+o.port;
        card+=`<div class="outlet">
          <div><div class="name">${num} → ${label}</div><div class="detail">${o.voltage}V · ${o.amps}A</div></div>
          <span class="kw">${o.kw.toFixed(2)} kW</span></div>`;
      });
      card+=`</div>`;
      grid.innerHTML+=card;
    });

    document.getElementById('status').textContent='Last updated: '+new Date().toLocaleTimeString();
  }catch(e){document.getElementById('status').textContent='Error: '+e.message}
}
load();
setInterval(load,30000);
</script>
</body></html>"""

LLM_INSIGHTS_HTML = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>Mining Guardian — AI Insights</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f8f9fa;padding:24px}
  h1{font-size:20px;color:#333;margin-bottom:4px}
  .sub{font-size:13px;color:#888;margin-bottom:16px}
  .cards{max-width:1000px;display:flex;flex-direction:column;gap:16px}
  .card{background:#fff;border-radius:10px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.08);border-left:4px solid #3498db}
  .card.fleet{border-left-color:#9b59b6}
  .card-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
  .card-header h3{font-size:14px;color:#555}
  .card-header .time{font-size:12px;color:#aaa}
  .card-header .duration{font-size:11px;color:#bbb;margin-left:8px}
  .miner-tag{display:inline-block;background:#eef;color:#336;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600;margin-right:6px}
  .miner-tag.fleet{background:#f3e8ff;color:#6b21a8}
  .response{font-size:13px;color:#444;line-height:1.6;white-space:pre-wrap;margin-top:8px}
  .response strong{color:#222}
  .empty{text-align:center;color:#aaa;padding:40px;font-size:15px}
  #status{font-size:12px;color:#aaa;margin-top:12px}
</style>
</head><body>
<h1>AI Insights — LLM Analysis History</h1>
<p class="sub">Qwen2.5 32B analyzing fleet patterns • Auto-refreshes every 5 min</p>
<div class="cards" id="cards"></div>
<p id="status">Loading...</p>
<script>
async function load(){
  try{
    const r=await fetch('/llm/history?limit=20');
    const data=await r.json();
    const cards=document.getElementById('cards');
    if(!data||data.length===0){
      cards.innerHTML='<div class="empty">No LLM analysis yet — waiting for first scan with issues</div>';
      document.getElementById('status').textContent='';
      return;
    }
    cards.innerHTML='';
    data.forEach(d=>{
      const isFleet=d.miner_id==='fleet';
      const tag=isFleet?
        '<span class="miner-tag fleet">Fleet Analysis</span>':
        '<span class="miner-tag">Miner '+d.miner_id+'</span>';
      const time=d.analyzed_at?d.analyzed_at.substring(0,16).replace('T',' '):'?';
      const dur=d.duration_ms?(d.duration_ms/1000).toFixed(1)+'s':'?';
      const resp=(d.response||'').replace(/</g,'&lt;').replace(/>/g,'&gt;')
        .replace(/\*\*(.*?)\*\*/g,'<strong>$1<\/strong>');
      cards.innerHTML+=
        '<div class="card '+(isFleet?'fleet':'')+'">'+
        '<div class="card-header"><h3>'+tag+(d.ip&&d.ip!=='all'&&d.ip!=='historical'?' @ '+d.ip:'')+'</h3>'+
        '<span><span class="time">'+time+'</span><span class="duration">'+dur+'</span></span></div>'+
        '<div class="response">'+resp+'</div></div>';
    });
    document.getElementById('status').textContent='Last updated: '+new Date().toLocaleTimeString()+' — '+data.length+' analyses';
  }catch(e){document.getElementById('status').textContent='Error: '+e.message}
}
load();
setInterval(load,300000);
</script>
</body></html>"""

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


from contextlib import contextmanager

@contextmanager
def db_conn():
    """Context manager for DB connections — guarantees close on exceptions."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# ── Prometheus /metrics endpoint ─────────────────────────────

import time as _time
_metrics_cache = {"data": None, "timestamp": 0.0}
_METRICS_CACHE_TTL = 25  # seconds — Prometheus scrapes every 30s

@app.get("/metrics")
@limiter.limit("120/minute")
def metrics(request: Request):
    """Prometheus metrics endpoint — scraped every 30s by Prometheus.
    Cached for 25 seconds to avoid hammering SQLite with ~15 queries per scrape.
    """
    now = _time.monotonic()
    if _metrics_cache["data"] is not None and (now - _metrics_cache["timestamp"]) < _METRICS_CACHE_TTL:
        return PlainTextResponse(_metrics_cache["data"], media_type=CONTENT_TYPE_LATEST)

    conn = get_db()

    # Latest scan summary
    scan = conn.execute(
        "SELECT online, offline, issues FROM scans ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if scan:
        g_fleet_online.labels(site=SITE).set(scan["online"])
        g_fleet_offline.labels(site=SITE).set(scan["offline"])
        g_fleet_issues.labels(site=SITE).set(scan["issues"])

    # Per-miner readings from latest scan
    scan_id_row = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    if scan_id_row:
        miners = conn.execute("""
            SELECT ip, model, hashrate_pct, ROUND(hashrate/1000.0, 2) AS hashrate_ths, temp_chip, pdu_power,
                   consumption, map_location, issue, status
            FROM miner_readings
            WHERE scan_id = ?
        """, (scan_id_row["id"],)).fetchall()

        # HW errors per miner (sum across boards)
        hw_errors_by_ip = {}
        for row in conn.execute("""
            SELECT ip, SUM(hw_errors) as total_hw
            FROM chain_readings WHERE scan_id=? GROUP BY ip
        """, (scan_id_row["id"],)).fetchall():
            hw_errors_by_ip[row["ip"]] = float(row["total_hw"] or 0)

        # Pool rejection rate per miner (latest scan)
        rejection_by_ip = {}
        for row in conn.execute("""
            SELECT ip,
                   CASE WHEN SUM(accepted)+SUM(rejected) > 0
                        THEN CAST(SUM(rejected) AS FLOAT) / (SUM(accepted)+SUM(rejected))
                        ELSE 0 END as rej_rate
            FROM pool_readings WHERE scan_id=? GROUP BY ip
        """, (scan_id_row["id"],)).fetchall():
            rejection_by_ip[row["ip"]] = float(row["rej_rate"] or 0)

        # Get dead board miner IPs
        dead_board_ips = set(
            r["ip"] for r in conn.execute(
                "SELECT ip FROM known_dead_boards WHERE resolved_at IS NULL"
            ).fetchall()
        )

        for m in miners:
            ip  = m["ip"] or "unknown"
            mdl = (m["model"] or "unknown").replace(" ", "_")
            loc = (m["map_location"] or "unknown").replace(" ", "_")

            # hashrate_pct stored as float e.g. 76.2
            try:
                hr = float(m["hashrate_pct"]) if m["hashrate_pct"] else 0.0
            except (ValueError, TypeError):
                hr = 0.0

            temp = m["temp_chip"] if (m["temp_chip"] is not None and m["temp_chip"] >= 0) else float('nan')
            pdu  = m["pdu_power"] if m["pdu_power"] is not None else 0.0
            flag = 1 if m["issue"] else 0
            dead = 1 if ip in dead_board_ips else 0

            g_hashrate_pct.labels(miner_ip=ip, model=mdl, site=SITE, map_location=loc).set(hr)
            if not (temp != temp):  # skip NaN temps — offline miners have no valid reading
                g_temp_chip.labels(miner_ip=ip, model=mdl, site=SITE, map_location=loc).set(temp)
            g_pdu_power_kw.labels(miner_ip=ip, model=mdl, site=SITE, map_location=loc).set(pdu)
            g_flagged.labels(miner_ip=ip, model=mdl, site=SITE, map_location=loc).set(flag)
            g_dead_boards.labels(miner_ip=ip, model=mdl, site=SITE).set(dead)

            # Miner-reported consumption and best-available power
            consumption = float(m["consumption"] or 0) / 1000.0  # W → kW
            g_consumption_kw.labels(miner_ip=ip, model=mdl, site=SITE).set(consumption)
            # Best power: PDU if non-zero, otherwise miner-reported
            best_power = pdu if pdu > 0 else consumption
            g_power_kw.labels(miner_ip=ip, model=mdl, site=SITE).set(best_power)

            # ── Miner Health Score (MHS) — raw component collection ───────────
            # Collect raw scores first; normalize fleet-relative after the loop
            is_online = (m["status"] == "online") and hr > 0
            if is_online:
                hw_errs  = hw_errors_by_ip.get(ip, 0)
                rej_rate = rejection_by_ip.get(ip, 0)
                if hr >= 100:
                    hashrate_score = 100.0
                else:
                    hashrate_score = 100.0 * ((hr / 100.0) ** 2.5)
                uptime_score   = 0.0 if flag else 100.0
                hw_error_score = max(0.0, 100.0 - (hw_errs * 10.0))
                rejection_score = max(0.0, 100.0 - (rej_rate * 20000.0))
                raw_mhs = (
                    hashrate_score   * 0.50 +
                    uptime_score     * 0.30 +
                    hw_error_score   * 0.15 +
                    rejection_score  * 0.05
                )
                # Store for fleet-relative normalization pass below
                if not hasattr(g_mhs, '_raw_batch'):
                    g_mhs._raw_batch = {}
                g_mhs._raw_batch[(ip, mdl)] = raw_mhs

        # ── Fleet-relative MHS normalization ──────────────────────────────────
        # After all miners are scored, normalize so best=100, worst=0.
        # This guarantees a full 0-100 spread regardless of fleet health.
        if hasattr(g_mhs, '_raw_batch') and g_mhs._raw_batch:
            raw_vals = list(g_mhs._raw_batch.values())
            mn, mx = min(raw_vals), max(raw_vals)
            spread = mx - mn if mx != mn else 1.0
            for (ip, mdl), raw in g_mhs._raw_batch.items():
                mhs = round((raw - mn) / spread * 100.0, 1)
                g_mhs.labels(miner_ip=ip, model=mdl, site=SITE).set(mhs)
            g_mhs._raw_batch = {}

        # Hashrate/efficiency gauges (separate from MHS normalization)
        for m in miners:
            ip  = m["ip"] or "unknown"
            mdl = (m["model"] or "unknown").replace(" ", "_")
            hr  = float(m["hashrate_pct"]) if m["hashrate_pct"] else 0.0
            pdu = m["pdu_power"] if m["pdu_power"] is not None else 0.0
            is_online = (m["status"] == "online") and hr > 0
            if is_online:
                actual_ths = float(m["hashrate_ths"] or 0)  # Already converted to TH/s in SQL
                rated_ths  = actual_ths / (hr / 100.0) if hr > 0 else 0
                actual_w   = pdu * 1000 if pdu > 0 else float(m["consumption"] or 0)
                g_hashrate_ths.labels(miner_ip=ip, model=mdl, site=SITE).set(round(actual_ths, 2))
                g_rated_ths.labels(miner_ip=ip, model=mdl, site=SITE).set(round(rated_ths, 2))
                if actual_w > 0:
                    g_efficiency.labels(miner_ip=ip, model=mdl, site=SITE).set(
                        round(actual_ths / (actual_w / 1000.0), 2)
                    )

    # Per-board chain readings from latest scan
    if scan_id_row:
        chains = conn.execute("""
            SELECT ip, board_index, rate_mhs, voltage, freq_mhz,
                   consumption_w, hw_errors, temp_board, temp_chip
            FROM chain_readings WHERE scan_id = ?
        """, (scan_id_row["id"],)).fetchall()
        for c in chains:
            ip    = c["ip"] or "unknown"
            board = str(c["board_index"])
            g_board_rate.labels(miner_ip=ip, board=board, site=SITE).set((c["rate_mhs"] or 0) / 1000)
            g_board_voltage.labels(miner_ip=ip, board=board, site=SITE).set(c["voltage"] or 0)
            g_board_freq.labels(miner_ip=ip, board=board, site=SITE).set(c["freq_mhz"] or 0)
            g_board_power.labels(miner_ip=ip, board=board, site=SITE).set(c["consumption_w"] or 0)
            g_board_hwerr.labels(miner_ip=ip, board=board, site=SITE).set(c["hw_errors"] or 0)
            g_board_temp.labels(miner_ip=ip, board=board, site=SITE).set(c["temp_board"] or 0)

        # Per-pool readings from latest scan
        pools = conn.execute("""
            SELECT ip, pool_url, accepted, rejected
            FROM pool_readings WHERE scan_id = ?
        """, (scan_id_row["id"],)).fetchall()
        for p in pools:
            ip       = p["ip"] or "unknown"
            pool_url = (p["pool_url"] or "unknown")[:60]  # truncate long URLs
            accepted = p["accepted"] or 0
            rejected = p["rejected"] or 0
            total    = accepted + rejected
            rej_rate = round((rejected / total) * 100, 2) if total > 0 else 0.0
            g_pool_accepted.labels(miner_ip=ip, pool_url=pool_url, site=SITE).set(accepted)
            g_pool_rejected.labels(miner_ip=ip, pool_url=pool_url, site=SITE).set(rejected)
            g_pool_reject_rate.labels(miner_ip=ip, pool_url=pool_url, site=SITE).set(rej_rate)

    # Latest HVAC reading
    hvac = conn.execute(
        "SELECT * FROM hvac_readings ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if hvac:
        if hvac["supply_temp_f"] is not None:
            g_hvac_supply.labels(site=SITE).set(hvac["supply_temp_f"])
        if hvac["return_temp_f"] is not None:
            g_hvac_return.labels(site=SITE).set(hvac["return_temp_f"])
        if hvac["delta_t_f"] is not None:
            g_hvac_delta_t.labels(site=SITE).set(hvac["delta_t_f"])
        if hvac["diff_pressure"] is not None:
            g_hvac_pressure.labels(site=SITE).set(hvac["diff_pressure"])
        g_spray_pump.labels(site=SITE).set(hvac["spray_pump_on"] or 0)

    # Latest weather reading
    wx = conn.execute(
        "SELECT temp_f, humidity_pct FROM weather_readings ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if wx:
        if wx["temp_f"] is not None:
            g_outside_temp.labels(site=SITE).set(wx["temp_f"])
        if wx["humidity_pct"] is not None:
            g_humidity.labels(site=SITE).set(wx["humidity_pct"])

    # ── AI / Knowledge metrics ─────────────────────────────────────────────────
    try:
        knowledge_path = str(_ROOT / "knowledge.json")
        with open(knowledge_path) as f:
            k = json.load(f)
        insights  = len(k.get("known_issues", []))
        patterns  = len(k.get("patterns", []))
        profiles  = len(k.get("miner_profiles", {}))
        g_knowledge_insights.labels(site=SITE).set(insights)
        g_knowledge_patterns.labels(site=SITE).set(patterns)
        g_knowledge_profiles.labels(site=SITE).set(profiles)

        # Local LLM learning metrics
        llm_scan_count = len(k.get("llm_scan_analyses", []))
        operator_rule_count = len(k.get("operator_rules", []))
        g_llm_scan_analyses.labels(site=SITE).set(llm_scan_count)
        g_operator_rules.labels(site=SITE).set(operator_rule_count)

        # Full AI score calculation
        try:
            _ai_path = str(_ROOT / "ai")
            if _ai_path not in sys.path:
                sys.path.insert(0, _ai_path)
            from ai_score import calculate_score
            ai = calculate_score(conn=conn, knowledge=k)
            g_knowledge_score.labels(site=SITE).set(ai["total_score"])
            g_ai_data_depth.labels(site=SITE).set(ai["components"]["data_ingested"]["score"])
            g_ai_knowledge.labels(site=SITE).set(ai["components"]["knowledge_depth"]["score"])
            g_ai_experience.labels(site=SITE).set(ai["components"]["actions_taken"]["score"])
            g_ai_accuracy.labels(site=SITE).set(ai["components"]["outcomes_learned"]["score"])
            g_ai_autonomy.labels(site=SITE).set(ai["components"]["autonomy_growth"]["score"])
        except Exception as e:
            # Fallback to simple score if ai_score fails
            score = insights + (patterns * 10) + profiles
            g_knowledge_score.labels(site=SITE).set(score)
        last_updated = k.get("last_updated", "")
        if last_updated:
            from datetime import timezone as _tz
            try:
                ts = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
                g_knowledge_updated.labels(site=SITE).set(ts.timestamp())
            except Exception:
                pass
    except Exception as e:
        logger.warning("Knowledge metrics read failed: %s", e)

    # Audit log action counts
    try:
        approved = conn.execute(
            "SELECT COUNT(*) FROM action_audit_log WHERE decision='APPROVED'"
        ).fetchone()[0]
        denied = conn.execute(
            "SELECT COUNT(*) FROM action_audit_log WHERE decision='DENIED'"
        ).fetchone()[0]
        auto_ov = conn.execute(
            "SELECT COUNT(*) FROM action_audit_log WHERE decision='AUTO_OVERNIGHT'"
        ).fetchone()[0]
        expired = conn.execute(
            "SELECT COUNT(*) FROM action_audit_log WHERE decision='DENIED' "
            "AND approved_by LIKE '%Auto-Expired%'"
        ).fetchone()[0]
        restarts = conn.execute(
            "SELECT COUNT(*) FROM miner_restarts"
        ).fetchone()[0]
        tickets = conn.execute(
            "SELECT COUNT(*) FROM known_dead_boards WHERE ticket_created IS NOT NULL"
        ).fetchone()[0]
        g_actions_approved.labels(site=SITE).set(approved)
        g_actions_denied.labels(site=SITE).set(denied)
        g_actions_auto.labels(site=SITE).set(auto_ov)
        g_actions_expired.labels(site=SITE).set(expired)
        g_restarts_total.labels(site=SITE).set(restarts)
        g_tickets_total.labels(site=SITE).set(tickets)
    except Exception as e:
        logger.warning("Action metrics read failed: %s", e)

    conn.close()
    result = generate_latest(REGISTRY)
    _metrics_cache["data"] = result
    _metrics_cache["timestamp"] = _time.monotonic()
    return PlainTextResponse(result, media_type=CONTENT_TYPE_LATEST)


@app.get("/fleet/board_stats", response_class=HTMLResponse)
def fleet_board_stats():
    """Fleet board health: worst rejection rates + worst HW error miners, side by side."""
    conn = get_db()
    try:
        scan = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
        if not scan:
            conn.close()
            return HTMLResponse("<p>No scan data yet.</p>")

        rej_rows = conn.execute("""
            SELECT p.ip,
                   COALESCE(m.model, 'Unknown') as model,
                   CASE WHEN SUM(p.accepted)+SUM(p.rejected)>0
                        THEN CAST(SUM(p.rejected) AS FLOAT)/(SUM(p.accepted)+SUM(p.rejected))
                        ELSE 0 END as rej_rate
            FROM pool_readings p
            LEFT JOIN (
                SELECT ip, model FROM miner_readings WHERE scan_id=? GROUP BY ip
            ) m ON p.ip = m.ip
            WHERE p.scan_id=? GROUP BY p.ip
            ORDER BY rej_rate DESC LIMIT 10
        """, (scan["id"], scan["id"])).fetchall()

        hw_rows = conn.execute("""
            SELECT c.ip,
                   COALESCE(m.model, 'Unknown') as model,
                   SUM(c.hw_errors) as total_hw
            FROM chain_readings c
            LEFT JOIN (
                SELECT ip, model FROM miner_readings WHERE scan_id=? GROUP BY ip
            ) m ON c.ip = m.ip
            WHERE c.scan_id=?
            GROUP BY c.ip HAVING total_hw > 0
            ORDER BY total_hw DESC LIMIT 10
        """, (scan["id"], scan["id"])).fetchall()

    finally:
        conn.close()

    def rej_color(r):
        if r >= 0.01: return "#ff4d4f"
        if r >= 0.003: return "#fa8c16"
        if r >= 0.001: return "#fadb14"
        return "#52c41a"

    rej_html = ""
    for i, r in enumerate(rej_rows, 1):
        rate = r["rej_rate"] or 0
        if rate == 0: continue
        color = rej_color(rate)
        model = (r["model"] or "?").replace("Antminer_","").replace("_"," ")
        rej_html += f'<tr><td style="color:{color};font-weight:bold;padding:5px 10px">{i}</td><td style="font-family:monospace;padding:5px 10px">{r["ip"]}</td><td style="color:#aaa;padding:5px 10px">{model}</td><td style="color:{color};font-weight:bold;padding:5px 10px">{rate*100:.3f}%</td></tr>'
    if not rej_html:
        rej_html = '<tr><td colspan="4" style="padding:10px;color:#52c41a;text-align:center">✅ No rejections</td></tr>'

    hw_html = ""
    for i, r in enumerate(hw_rows, 1):
        hw = int(r["total_hw"] or 0)
        color = "#ff4d4f" if hw>=50 else "#fa8c16" if hw>=10 else "#fadb14"
        model = (r["model"] or "?").replace("Antminer_","").replace("_"," ")
        hw_html += f'<tr><td style="color:{color};font-weight:bold;padding:5px 10px">{i}</td><td style="font-family:monospace;padding:5px 10px">{r["ip"]}</td><td style="color:#aaa;padding:5px 10px">{model}</td><td style="color:{color};font-weight:bold;padding:5px 10px">{hw}</td></tr>'
    if not hw_html:
        hw_html = '<tr><td colspan="4" style="padding:10px;color:#52c41a;text-align:center">✅ No HW errors</td></tr>'

    return HTMLResponse(f"""<style>
    body{{background:transparent;color:#e0e0e0;font-family:sans-serif;margin:0;padding:8px}}
    .wrap{{display:flex;gap:20px}} .col{{flex:1}}
    h3{{margin:0 0 10px 0;font-size:15px;font-weight:800;text-transform:uppercase;letter-spacing:.12em}}
    h3.rej{{color:#fa8c16}} h3.hw{{color:#ff4d4f}}
    table{{width:100%;border-collapse:collapse;font-size:13px}}
    th{{text-align:left;padding:5px 10px;color:#999;font-weight:700;font-size:11px;text-transform:uppercase;letter-spacing:.06em;border-bottom:1px solid #444}}
    tr:hover{{background:rgba(255,255,255,.06)}}
    </style>
    <div class="wrap">
      <div class="col"><h3 class="rej">⚠️ Worst Pool Rejection Rates</h3>
        <table><thead><tr><th>#</th><th>IP</th><th>Model</th><th>Rej %</th></tr></thead>
        <tbody>{rej_html}</tbody></table></div>
      <div class="col"><h3 class="hw">🔧 Worst HW Error Miners</h3>
        <table><thead><tr><th>#</th><th>IP</th><th>Model</th><th>Errors</th></tr></thead>
        <tbody>{hw_html}</tbody></table></div>
    </div>""")


@app.get("/mhs", response_class=HTMLResponse)
def mhs_panel():
    """Miner Health Score leaderboard — HTML table for Grafana text panel iframe.
    Top 5 healthiest on the left, bottom 5 on the right. Online miners only.
    """
    conn = get_db()
    try:
        scan_id_row = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
        if not scan_id_row:
            conn.close()
            return HTMLResponse("<p>No scan data yet.</p>")

        miners = conn.execute("""
            SELECT ip, model, hashrate_pct, pdu_power, status, issue
            FROM miner_readings
            WHERE scan_id=? AND status='online' AND hashrate_pct > 0
            ORDER BY hashrate_pct DESC
        """, (scan_id_row["id"],)).fetchall()

        hw_errors_by_ip = {}
        for row in conn.execute("""
            SELECT ip, SUM(hw_errors) as total_hw FROM chain_readings WHERE scan_id=? GROUP BY ip
        """, (scan_id_row["id"],)).fetchall():
            hw_errors_by_ip[row["ip"]] = float(row["total_hw"] or 0)

        rejection_by_ip = {}
        for row in conn.execute("""
            SELECT ip,
                   CASE WHEN SUM(accepted)+SUM(rejected) > 0
                        THEN CAST(SUM(rejected) AS FLOAT)/(SUM(accepted)+SUM(rejected))
                        ELSE 0 END as rej_rate
            FROM pool_readings WHERE scan_id=? GROUP BY ip
        """, (scan_id_row["id"],)).fetchall():
            rejection_by_ip[row["ip"]] = float(row["rej_rate"] or 0)

    finally:
        conn.close()

    scores = []
    for m in miners:
        ip  = m["ip"] or "unknown"
        hr  = float(m["hashrate_pct"] or 0)
        rej = rejection_by_ip.get(ip, 0)
        hw  = hw_errors_by_ip.get(ip, 0)
        flg = 1 if m["issue"] else 0
        hr_score  = 100.0 if hr >= 100 else 100.0 * ((hr / 100.0) ** 2.5)
        upt_score = 0.0 if flg else 100.0
        hw_score  = max(0.0, 100.0 - (hw * 10.0))
        rej_score = max(0.0, 100.0 - (rej * 20000.0))
        raw = hr_score*0.50 + upt_score*0.30 + hw_score*0.15 + rej_score*0.05
        model = html_lib.escape((m["model"] or "Unknown").replace("Antminer_", "").replace("_", " "))
        scores.append({"ip": ip, "model": model, "raw": raw})

    # Fleet-relative normalization: best=100, worst=0, always full spread
    if scores:
        mn = min(s["raw"] for s in scores)
        mx = max(s["raw"] for s in scores)
        spread = mx - mn if mx != mn else 1.0
        for s in scores:
            s["mhs"] = round((s["raw"] - mn) / spread * 100.0, 1)

    scores.sort(key=lambda x: x["mhs"], reverse=True)
    top5 = scores[:5]
    bot5 = sorted(scores, key=lambda x: x["mhs"])[:5]

    def rows(lst, color):
        out = ""
        for i, m in enumerate(lst, 1):
            out += f'<tr><td style="color:{color};font-weight:bold;padding:5px 10px">{i}</td>'
            out += f'<td style="font-family:monospace;padding:5px 10px">{m["ip"]}</td>'
            out += f'<td style="color:#aaa;padding:5px 10px">{m["model"]}</td>'
            out += f'<td style="color:{color};font-weight:bold;padding:5px 10px">{m["mhs"]}</td></tr>'
        return out

    return HTMLResponse(f"""<style>
    body{{background:transparent;color:#e0e0e0;font-family:sans-serif;margin:0;padding:8px}}
    .wrap{{display:flex;gap:20px}} .col{{flex:1}}
    h3{{margin:0 0 10px 0;font-size:15px;font-weight:800;text-transform:uppercase;letter-spacing:.12em}}
    h3.top{{color:#52c41a}} h3.bot{{color:#fa8c16}}
    table{{width:100%;border-collapse:collapse;font-size:13px}}
    th{{text-align:left;padding:5px 10px;color:#999;font-weight:700;font-size:11px;text-transform:uppercase;letter-spacing:.06em;border-bottom:1px solid #444}}
    tr:hover{{background:rgba(255,255,255,.06)}}
    </style>
    <div class="wrap">
      <div class="col"><h3 class="top">🏆 Top 5 Healthiest</h3>
        <table><thead><tr><th>#</th><th>IP</th><th>Model</th><th>MHS</th></tr></thead>
        <tbody>{rows(top5,'#52c41a')}</tbody></table></div>
      <div class="col"><h3 class="bot">⚠️ Bottom 5 — Need Attention</h3>
        <table><thead><tr><th>#</th><th>IP</th><th>Model</th><th>MHS</th></tr></thead>
        <tbody>{rows(bot5,'#fa8c16')}</tbody></table></div>
    </div>""")

@app.get("/miner/status/{miner_ip}")
def miner_status(miner_ip: str):
    """Current problem + full action history for a specific miner IP."""
    conn = get_db()
    try:
        miner_ip_clean = miner_ip.replace("_", ".")

        current = conn.execute("""
            SELECT mr.ip, mr.model, mr.issue, mr.action, mr.scanned_at,
                   mr.hashrate_pct, mr.temp_chip, mr.pdu_power, mr.status,
                   mr.current_profile, mr.map_location
            FROM miner_readings mr
            WHERE mr.ip = ?
            ORDER BY mr.id DESC LIMIT 1
        """, (miner_ip_clean,)).fetchone()

        history = conn.execute("""
            SELECT timestamp, problem, action_taken, decision, approved_by, notes
            FROM action_audit_log
            WHERE ip = ?
            ORDER BY timestamp DESC LIMIT 20
        """, (miner_ip_clean,)).fetchall()

        dead_boards = conn.execute("""
            SELECT board_indices, first_seen, restart_attempted,
                   restart_result, ticket_created
            FROM known_dead_boards
            WHERE ip = ? AND resolved_at IS NULL
        """, (miner_ip_clean,)).fetchone()

    finally:
        conn.close()
    return {
        "current": dict(current) if current else None,
        "history": [dict(r) for r in history],
        "dead_boards": dict(dead_boards) if dead_boards else None,
    }

@app.get("/miner/status_html/{miner_ip}", response_class=HTMLResponse)
def miner_status_html(miner_ip: str):
    """Styled HTML status page for a miner — embeddable in Grafana text panel as iframe."""
    # Helper — escape all DB values before interpolating into HTML
    def e(val) -> str:
        return html_lib.escape(str(val)) if val is not None else ""

    conn = get_db()
    try:
        miner_ip_clean = miner_ip.replace("_", ".")

        current = conn.execute("""
            SELECT ip, model, issue, action, scanned_at,
                   hashrate_pct, temp_chip, pdu_power, status,
                   current_profile, map_location
            FROM miner_readings WHERE ip = ?
            ORDER BY id DESC LIMIT 1
        """, (miner_ip_clean,)).fetchone()

        history = conn.execute("""
            SELECT timestamp, problem, action_taken, decision, approved_by, notes
            FROM action_audit_log WHERE ip = ?
            ORDER BY timestamp DESC LIMIT 15
        """, (miner_ip_clean,)).fetchall()

        dead = conn.execute("""
            SELECT board_indices, first_seen, restart_attempted,
                   restart_result, ticket_created
            FROM known_dead_boards WHERE ip = ? AND resolved_at IS NULL
        """, (miner_ip_clean,)).fetchone()

    finally:
        conn.close()

    # Build current status block
    if current:
        status_color = "#2ecc71" if not current["issue"] else "#e74c3c"
        action_colors = {
            "RESTART": "#e67e22", "PDU_CYCLE": "#e74c3c",
            "MONITOR": "#f39c12", "RESTART_CHECK_BOARDS": "#c0392b",
            "PHYSICAL_CYCLE": "#8e44ad", "TEMP_ACTION_REQUIRED": "#e74c3c",
        }
        action_color = action_colors.get(current["action"] or "", "#95a5a6")
        current_html = f"""
        <div class="current-block">
            <div class="row">
                <span class="label">Status</span>
                <span class="badge" style="background:{status_color}">
                    {e(current["status"]).upper() or "UNKNOWN"}
                </span>
                {f'<span class="badge" style="background:{action_color};margin-left:6px">{e(current["action"])}</span>' if current["action"] else ""}
            </div>
            <div class="row"><span class="label">Model</span><span>{e(current["model"]) or "—"}</span></div>
            <div class="row"><span class="label">Profile</span><span>{e(current["current_profile"]) or "—"}</span></div>
            <div class="row"><span class="label">Location</span><span>{e(current["map_location"]) or "not mapped"}</span></div>
            <div class="row"><span class="label">Hashrate</span><span>{e(current["hashrate_pct"])}%</span></div>
            <div class="row"><span class="label">Chip Temp</span><span>{e(current["temp_chip"])}°C</span></div>
            <div class="row"><span class="label">PDU Power</span><span>{e(current["pdu_power"])} kW</span></div>
            <div class="row"><span class="label">Last Scan</span><span>{e(current["scanned_at"])[:16].replace("T"," ")}</span></div>
            {f'<div class="issue-box">⚠️ {e(current["issue"])}</div>' if current["issue"] else '<div class="ok-box">✅ No active issues</div>'}
        </div>"""
    else:
        current_html = '<div class="current-block"><p style="color:#aaa">No data yet</p></div>'

    # Dead board warning
    dead_html = ""
    if dead:
        dead_html = f"""
        <div class="dead-board-box">
            🔴 <strong>Known Dead Boards:</strong> {e(dead["board_indices"])}<br>
            First seen: {e(dead["first_seen"])[:16].replace("T"," ")} |
            Ticket: {e(dead["ticket_created"]) or "pending"}
        </div>"""

    # Audit history table
    if history:
        rows_html = ""
        for h in history:
            dec_color = "#2ecc71" if h["decision"] == "APPROVED" else "#e74c3c" if h["decision"] == "DENIED" else "#f39c12"
            ts = e(h["timestamp"])[:16].replace("T", " ")
            rows_html += f"""<tr>
                <td>{ts}</td>
                <td><span style="color:{dec_color};font-weight:600">{e(h["decision"])}</span></td>
                <td>{e(h["action_taken"]) or "—"}</td>
                <td style="color:#aaa;font-size:11px">{e(h["approved_by"]) or "—"}</td>
                <td style="font-size:11px;max-width:300px;word-break:break-word">{e(h["problem"]) or "—"}</td>
            </tr>"""
        history_html = f"""
        <table>
            <thead><tr>
                <th>Time</th><th>Decision</th><th>Action</th><th>By</th><th>Problem</th>
            </tr></thead>
            <tbody>{rows_html}</tbody>
        </table>"""
    else:
        history_html = '<p style="color:#aaa;font-size:13px">No actions taken yet</p>'

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  * {{margin:0;padding:0;box-sizing:border-box}}
  body {{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:#111;color:#ddd;padding:12px;font-size:13px}}
  h3 {{font-size:14px;color:#fff;margin-bottom:8px;border-bottom:1px solid #333;padding-bottom:6px}}
  .current-block {{margin-bottom:12px}}
  .row {{display:flex;gap:10px;padding:3px 0;border-bottom:1px solid #1a1a1a}}
  .label {{color:#888;width:90px;flex-shrink:0}}
  .badge {{padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;color:#fff}}
  .issue-box {{background:#2a1010;border-left:3px solid #e74c3c;padding:6px 8px;
               margin-top:8px;border-radius:2px;font-size:12px;color:#e74c3c}}
  .ok-box {{background:#0d1f0d;border-left:3px solid #2ecc71;padding:6px 8px;
            margin-top:8px;border-radius:2px;font-size:12px;color:#2ecc71}}
  .dead-board-box {{background:#2a1010;border-left:3px solid #c0392b;padding:8px;
                    margin-bottom:12px;border-radius:2px;font-size:12px;color:#e88}}
  table {{width:100%;border-collapse:collapse;font-size:12px}}
  th {{background:#1a1a1a;color:#888;padding:5px 8px;text-align:left;font-weight:500}}
  td {{padding:5px 8px;border-bottom:1px solid #1a1a1a;vertical-align:top}}
  tr:hover td {{background:#1a1a1a}}
</style>
</head><body>
<h3>Current Status — {miner_ip_clean}</h3>
{current_html}
{dead_html}
<h3 style="margin-top:12px">Action History</h3>
{history_html}
</body></html>"""
@app.get("/fleet/latest")
@limiter.limit("60/minute")
def fleet_latest(request: Request):
    """Latest scan summary — fleet status right now."""
    conn = get_db()
    try:
        scan = conn.execute(
            "SELECT * FROM scans ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not scan:
            return {"error": "No scans yet"}
        scan = dict(scan)

        # Latest readings breakdown
        readings = conn.execute("""
            SELECT action, COUNT(*) as count
            FROM miner_readings
            WHERE scan_id = ? AND action IS NOT NULL
            GROUP BY action
        """, (scan["id"],)).fetchall()

        scan["action_breakdown"] = {r["action"]: r["count"] for r in readings}
    finally:
        conn.close()
    return scan


@app.get("/fleet/history")
@limiter.limit("30/minute")
def fleet_history(request: Request, days: int = 7):
    days = min(max(days, 1), 90)
    """Scan history over the last N days."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM scans WHERE scanned_at > ? ORDER BY id DESC",
            (cutoff,)
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


# ── Miners ───────────────────────────────────────────────────

@app.get("/miners/flagged")
@limiter.limit("60/minute")
def miners_flagged(request: Request):
    """All miners currently flagged in the latest scan."""
    conn = get_db()
    try:
        scan = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
        if not scan:
            return []
        rows = conn.execute("""
            SELECT miner_id, ip, model, status, hashrate_pct,
                   temp_chip, action, issue
            FROM miner_readings
            WHERE scan_id = ? AND action IS NOT NULL
            ORDER BY action, ip
        """, (scan["id"],)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.get("/miners/most_flagged")
def miners_most_flagged(limit: int = 20):
    """Miners flagged most often — trouble list."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT miner_id, ip, model,
                   COUNT(*) as times_flagged,
                   MAX(scanned_at) as last_flagged,
                   action
            FROM miner_readings
            WHERE action IS NOT NULL
            GROUP BY miner_id
            ORDER BY times_flagged DESC
            LIMIT ?
        """, (limit,)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.get("/miners/{miner_id}/history")
def miner_history(miner_id: str, days: int = 7):
    days = min(max(days, 1), 90)
    """Full telemetry history for a specific miner."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT scanned_at, hashrate_pct, temp_chip, status, action, issue
            FROM miner_readings
            WHERE miner_id = ? AND scanned_at > ?
            ORDER BY scanned_at ASC
        """, (miner_id, cutoff)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.get("/miners/{miner_id}/logs")
def miner_logs(miner_id: str, limit: int = 10):
    """Recent log files collected for a miner."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT collected_at, health_status, log_file, content
            FROM miner_logs
            WHERE miner_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (miner_id, limit)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


# ── Temperature ───────────────────────────────────────────────

@app.get("/temps/hot_miners")
def temps_hot_miners():
    """Miners currently in yellow or red temp zones."""
    conn = get_db()
    try:
        scan = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
        if not scan:
            return []
        rows = conn.execute("""
            SELECT miner_id, ip, model, temp_chip, action
            FROM miner_readings
            WHERE scan_id = ? AND temp_chip >= 76
            ORDER BY temp_chip DESC
        """, (scan["id"],)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.get("/temps/history")
@limiter.limit("30/minute")
def temps_history(request: Request, days: int = 7):
    days = min(max(days, 1), 90)
    """Average chip temp across fleet over time."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT s.scanned_at,
                   AVG(r.temp_chip) as avg_temp,
                   MAX(r.temp_chip) as max_temp,
                   MIN(r.temp_chip) as min_temp
            FROM miner_readings r
            JOIN scans s ON r.scan_id = s.id
            WHERE s.scanned_at > ? AND r.temp_chip > 0
            GROUP BY s.id
            ORDER BY s.scanned_at ASC
        """, (cutoff,)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


# ── Power ─────────────────────────────────────────────────────

@app.get("/weather/history")
def weather_history(days: int = 7):
    days = min(max(days, 1), 90)
    """Ambient temp and humidity history."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM weather_readings WHERE recorded_at > ? ORDER BY id ASC",
            (cutoff,)
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


# ── Live Facility Power ───────────────────────────────────────

@app.get("/facility/power_live")
def facility_power_live():
    """Live warehouse power readings from PDUs and immersion tank."""
    from facility_monitor import FacilityMonitor, PDU_OUTLET_MAP
    fm = FacilityMonitor()
    snap = fm.poll()

    result = {"total_kw": round(snap.total_warehouse_kw, 2), "sources": []}

    for label, pdu in [("PDU 163 — 2U Rack (Auradines)", snap.pdu_163),
                       ("PDU 164 — Bitmain Shoebox (S21 EXP Hydro)", snap.pdu_164)]:
        if not pdu:
            continue
        src = {"name": label, "ip": pdu.ip,
               "total_kw": round(pdu.total_power_kw or 0, 2),
               "voltage_v": pdu.l1_voltage_v, "current_a": pdu.l1_current_a,
               "outlets": []}
        for o in pdu.outlets:
            if o.on:
                mid = PDU_OUTLET_MAP.get((pdu.ip, o.index))
                src["outlets"].append({
                    "outlet": o.index,
                    "kw": round(o.power_kw, 2),
                    "voltage": round(o.avg_voltage_v, 1),
                    "amps": round(o.avg_current_a, 1),
                    "miner": f"miner {mid}" if mid else "not mapped"})
        result["sources"].append(src)

    tank = snap.tank_b100
    if tank:
        tsrc = {"name": "Immersion Tank B100", "ip": "192.168.188.20",
                "total_kw": round(tank.total_power_kw or 0, 2),
                "fluid_in_c": tank.in_temp_c, "fluid_out_c": tank.out_temp_c,
                "pump_running": tank.pump_on, "ports": []}
        for p in tank.ports:
            pw = (p.power_a_kw or 0) + (p.power_b_kw or 0) + (p.power_c_kw or 0)
            if pw > 0.1:
                mid = PDU_OUTLET_MAP.get(('192.168.188.20', p.index))
                tsrc["ports"].append({
                    "port": p.index,
                    "kw": round(pw, 2),
                    "voltage": round(p.voltage_a, 1),
                    "amps": round(p.current_a, 1),
                    "miner": f"miner {mid}" if mid else "tank cooling system"})
        result["sources"].append(tsrc)

    return result

@app.get("/facility/environment_history")
def environment_history(days: int = 5):
    days = min(max(days, 1), 90)
    """Combined outside weather + HVAC temps for charting.
    Downsampled to 4 points per day (every 6 hours) for readability.
    Returns at most 20 data points over 5 days.
    """
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = get_db()
    try:

        # Downsample to one point per 6-hour bucket using SQLite strftime
        wx_rows = conn.execute("""
            SELECT
                strftime('%Y-%m-%dT', recorded_at) ||
                CASE CAST(strftime('%H', recorded_at) AS INT)
                    WHEN 0 THEN '00:00:00' WHEN 1 THEN '00:00:00' WHEN 2 THEN '00:00:00'
                    WHEN 3 THEN '00:00:00' WHEN 4 THEN '00:00:00' WHEN 5 THEN '00:00:00'
                    WHEN 6 THEN '06:00:00' WHEN 7 THEN '06:00:00' WHEN 8 THEN '06:00:00'
                    WHEN 9 THEN '06:00:00' WHEN 10 THEN '06:00:00' WHEN 11 THEN '06:00:00'
                    WHEN 12 THEN '12:00:00' WHEN 13 THEN '12:00:00' WHEN 14 THEN '12:00:00'
                    WHEN 15 THEN '12:00:00' WHEN 16 THEN '12:00:00' WHEN 17 THEN '12:00:00'
                    ELSE '18:00:00'
                END as bucket,
                AVG(temp_f) as outside_temp_f,
                AVG(humidity_pct) as humidity_pct
            FROM weather_readings
            WHERE recorded_at > ?
            GROUP BY bucket
            ORDER BY bucket ASC
        """, (cutoff,)).fetchall()

        hvac_rows = conn.execute("""
            SELECT
                strftime('%Y-%m-%dT', recorded_at) ||
                CASE CAST(strftime('%H', recorded_at) AS INT)
                    WHEN 0 THEN '00:00:00' WHEN 1 THEN '00:00:00' WHEN 2 THEN '00:00:00'
                    WHEN 3 THEN '00:00:00' WHEN 4 THEN '00:00:00' WHEN 5 THEN '00:00:00'
                    WHEN 6 THEN '06:00:00' WHEN 7 THEN '06:00:00' WHEN 8 THEN '06:00:00'
                    WHEN 9 THEN '06:00:00' WHEN 10 THEN '06:00:00' WHEN 11 THEN '06:00:00'
                    WHEN 12 THEN '12:00:00' WHEN 13 THEN '12:00:00' WHEN 14 THEN '12:00:00'
                    WHEN 15 THEN '12:00:00' WHEN 16 THEN '12:00:00' WHEN 17 THEN '12:00:00'
                    ELSE '18:00:00'
                END as bucket,
                AVG(supply_temp_f) as supply_temp_f,
                AVG(return_temp_f) as return_temp_f,
                AVG(delta_t_f) as delta_t_f
            FROM hvac_readings
            WHERE recorded_at > ?
            GROUP BY bucket
            ORDER BY bucket ASC
        """, (cutoff,)).fetchall()
    finally:
        conn.close()

    # Merge weather + HVAC on bucket timestamp
    hvac_map = {r["bucket"]: dict(r) for r in hvac_rows}
    result = []
    for wx in wx_rows:
        bucket = wx["bucket"]
        h = hvac_map.get(bucket, {})
        result.append({
            "recorded_at":    bucket,
            "outside_temp_f": round(wx["outside_temp_f"], 1) if wx["outside_temp_f"] else None,
            "humidity_pct":   round(wx["humidity_pct"], 1) if wx["humidity_pct"] else None,
            "supply_temp_f":  round(h["supply_temp_f"], 1) if h.get("supply_temp_f") else None,
            "return_temp_f":  round(h["return_temp_f"], 1) if h.get("return_temp_f") else None,
            "delta_t_f":      round(h["delta_t_f"], 1) if h.get("delta_t_f") else None,
        })
    return result

@app.get("/notifications/recent")
@limiter.limit("60/minute")
def notifications_recent(request: Request, limit: int = 50):
    """Recent AMS notifications grouped by type."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT key, alert_level, miner_ip, recorded_at
            FROM ams_notifications
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.get("/notifications/summary")
def notifications_summary():
    """Notification counts grouped by type and severity."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT key, alert_level, COUNT(*) as count
            FROM ams_notifications
            GROUP BY key, alert_level
            ORDER BY count DESC
        """).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


# ── Restarts ──────────────────────────────────────────────────

@app.get("/restarts/recent")
def restarts_recent(limit: int = 20):
    """Recent restart events."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT * FROM miner_restarts
            ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.get("/audit/log")
@limiter.limit("30/minute")
def audit_log(request: Request, days: int = None, miner_id: str = None, limit: int = 100):
    if days is not None:
        days = min(max(days, 1), 90)
    limit = min(max(limit, 1), 500)
    """Permanent action audit log — every approval and denial ever recorded.

    Filterable by date range (days) and miner_id.
    Grouped by date for easy review. Never expires.
    """
    conn   = get_db()
    query  = "SELECT * FROM action_audit_log WHERE 1=1"
    params = []
    if days:
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        query += " AND date >= ?"
        params.append(cutoff)
    if miner_id:
        query += " AND miner_id = ?"
        params.append(miner_id)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/audit/summary")
def audit_summary():
    """Audit log summary — counts by decision, action, and approver."""
    conn = get_db()
    try:
        by_decision = conn.execute("""
            SELECT decision, COUNT(*) as count
            FROM action_audit_log
            GROUP BY decision
        """).fetchall()
        by_action = conn.execute("""
            SELECT action_taken, decision, COUNT(*) as count
            FROM action_audit_log
            GROUP BY action_taken, decision
            ORDER BY count DESC
        """).fetchall()
        by_approver = conn.execute("""
            SELECT approved_by, decision, COUNT(*) as count
            FROM action_audit_log
            WHERE approved_by IS NOT NULL
            GROUP BY approved_by, decision
            ORDER BY count DESC
        """).fetchall()
    finally:
        conn.close()
    return {
        "by_decision": [dict(r) for r in by_decision],
        "by_action":   [dict(r) for r in by_action],
        "by_approver": [dict(r) for r in by_approver],
    }


# ── LLM Analysis History ──────────────────────────────────────

@app.get("/llm/history")
def llm_history(limit: int = 10):
    limit = min(max(limit, 1), 500)
    """Recent LLM analysis results — proxied from VPS if local DB is empty."""
    conn = get_db()
    try:
        try:
            rows = conn.execute(
                "SELECT * FROM llm_analysis ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        except Exception:
            rows = []
    finally:
        conn.close()
    if rows:
        return [dict(r) for r in rows]
    # Fallback: proxy from VPS
    try:
        import requests as _req
        resp = _req.get(f"{os.getenv("DASHBOARD_URL", "http://127.0.0.1:8585")}/llm/history?limit={limit}", timeout=5)
        return resp.json()
    except Exception:
        return []


# ── Environment Chart (standalone HTML) ───────────────────────


# ── Trend Visualization API (Apr 22 2026) ────────────────────────────────────

@app.get("/trends/fleet")
@limiter.limit("30/minute")
def trends_fleet(request: Request, hours: int = 24):
    """Fleet-wide trends: hashrate, power, efficiency, temps over time."""
    hours = min(max(hours, 1), 720)  # 1 hour to 30 days
    from trends_api import get_fleet_trends
    conn = get_db()
    try:
        return get_fleet_trends(conn, hours)
    finally:
        conn.close()


@app.get("/trends/miner/{miner_id}")
@limiter.limit("30/minute")
def trends_miner(request: Request, miner_id: str, hours: int = 24):
    """Single miner trend data for degradation tracking."""
    hours = min(max(hours, 1), 720)
    from trends_api import get_miner_trend
    conn = get_db()
    try:
        return get_miner_trend(conn, miner_id, hours)
    finally:
        conn.close()


@app.get("/trends/degradation")
@limiter.limit("10/minute")
def trends_degradation(request: Request, days: int = 7):
    """Rank miners by performance degradation over time."""
    days = min(max(days, 1), 30)
    from trends_api import get_degradation_ranking
    conn = get_db()
    try:
        return get_degradation_ranking(conn, days)
    finally:
        conn.close()


@app.get("/trends/profitability")
@limiter.limit("10/minute")
def trends_profitability(request: Request, hours: int = 168):
    """Profitability trend over time (default: 7 days)."""
    hours = min(max(hours, 1), 720)
    from trends_api import get_profitability_trend
    electricity_rate = float(os.getenv("ELECTRICITY_RATE_KWH", "0.042"))
    conn = get_db()
    try:
        return get_profitability_trend(conn, electricity_rate, hours)
    finally:
        conn.close()


@app.get("/trends/temperatures")
@limiter.limit("30/minute")
def trends_temperatures(request: Request, hours: int = 24):
    """Temperature trends with HVAC correlation."""
    hours = min(max(hours, 1), 720)
    from trends_api import get_temperature_trends
    conn = get_db()
    try:
        return get_temperature_trends(conn, hours)
    finally:
        conn.close()

@app.get("/predictions/eta")
@limiter.limit("10/minute")
def predictions_eta(request: Request):
    """Get predictive failure ETA for all at-risk miners."""
    from ai.predictive_eta import get_fleet_eta_ranking
    return get_fleet_eta_ranking()


@app.get("/predictions/eta/{ip_or_id}")
@limiter.limit("30/minute")
def predictions_eta_miner(request: Request, ip_or_id: str):
    """Get predictive failure ETA for a specific miner."""
    from ai.predictive_eta import get_eta_for_miner
    return get_eta_for_miner(ip_or_id)




@app.get("/charts/environment", response_class=HTMLResponse)
def environment_chart():
    """Standalone HTML line chart — outside temp, supply/return water, humidity."""
    return ENVIRONMENT_CHART_HTML


@app.get("/charts/power", response_class=HTMLResponse)
def power_chart():
    """Standalone HTML dashboard — live warehouse power summary."""
    return POWER_CHART_HTML


@app.get("/charts/llm-insights", response_class=HTMLResponse)
def llm_insights_chart():
    """Standalone HTML dashboard — LLM analysis history."""
    return LLM_INSIGHTS_HTML




# ── AI Intelligence Center ────────────────────────────────────

@app.get("/ai/dashboard", response_class=HTMLResponse)
def ai_dashboard():
    """Full AI Intelligence Center — interactive HTML dashboard."""
    try:
        _api_path = str(_ROOT / "api")
        if _api_path not in sys.path:
            sys.path.insert(0, _api_path)
        from ai_dashboard_api import render_ai_dashboard_html
        return HTMLResponse(render_ai_dashboard_html())
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        return HTMLResponse(f"<h1>AI Dashboard Error</h1><pre>{tb}</pre>", status_code=500)


@app.get("/ai/score")
def ai_score_json():
    """AI score as JSON."""
    try:
        _ai_path = str(_ROOT / "ai")
        if _ai_path not in sys.path:
            sys.path.insert(0, _ai_path)
        from ai_score import calculate_score
        return calculate_score()
    except Exception as exc:
        return {"error": str(exc)}


# ── Health Check ──────────────────────────────────────────────

@app.get("/")
def health():
    conn = get_db()
    try:
        scan_count = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
        latest = conn.execute(
            "SELECT scanned_at FROM scans ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    return {
        "status": "online",
        "db": "guardian.db",  # path redacted — don't leak filesystem layout
        "total_scans": scan_count,
        "last_scan": latest[0] if latest else None,
    }


# ── QUERY ENDPOINTS (Bobby/OpenClaw skill-facing) ──
#
# These endpoints are consumed by the guardian-db OpenClaw skill at
# /data/.openclaw/skills/guardian-db/ inside the OpenClaw container.
# The skill makes HTTP calls to these endpoints to answer fleet questions
# in Slack DMs.
#
# TEMP: In the current VPS dev environment, the OpenClaw container reaches
#       these endpoints via the Docker bridge IP of the VPS host
#       (typically 172.18.0.1:8585). On May 1 2026 when Mining Guardian and
#       OpenClaw are both containers in the same docker-compose stack on a
#       Mac mini, this becomes http://mining-guardian:8585/query/... via
#       service-name DNS — a one-line config change in the skill.
#
# Design rules for this block:
#   - Read-only only. No writes under any circumstances.
#   - Compact JSON shapes. Fields named in plain English. No nested wrappers.
#   - Small-integer defaults for `hours` and `limit` so the LLM doesn't
#     accidentally pull the whole database.
#   - Errors return {"error": "..."} with appropriate HTTP status codes.
#   - Every endpoint uses db_conn() context manager — guaranteed close.

def _latest_scan_id(conn):
    """Return the id of the most recent scan, or None if no scans exist."""
    row = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    return row["id"] if row else None


@app.get("/query/fleet_summary")
def query_fleet_summary():
    """
    High-level fleet state from the latest scan.

    Returns counts of online/offline/flagged miners, fleet total hashrate,
    and the scan timestamp so the LLM can say things like
    "as of 10 minutes ago, 55 miners are online and 3 are flagged".
    """
    with db_conn() as conn:
        scan = conn.execute(
            "SELECT id, scanned_at, total_miners, online, offline, issues "
            "FROM scans ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not scan:
            return {"error": "no scans in database yet"}

        agg = conn.execute(
            "SELECT "
            "  COALESCE(SUM(hashrate), 0) AS total_hashrate, "
            "  COALESCE(SUM(max_hashrate), 0) AS total_max_hashrate, "
            "  COALESCE(AVG(hashrate_pct), 0) AS avg_pct, "
            "  COUNT(*) AS miner_count "
            "FROM miner_readings WHERE scan_id = ?",
            (scan["id"],),
        ).fetchone()

        flagged = conn.execute(
            "SELECT COUNT(*) AS n FROM miner_readings "
            "WHERE scan_id = ? AND issue IS NOT NULL AND issue != ''",
            (scan["id"],),
        ).fetchone()["n"]

        return {
            "scan_id": scan["id"],
            "scan_time": scan["scanned_at"],
            "total_miners": scan["total_miners"],
            "online": scan["online"],
            "offline": scan["offline"],
            "flagged": flagged,
            "total_hashrate_ths": round(agg["total_hashrate"] / 1000, 1) if agg["total_hashrate"] else 0,
            "total_max_hashrate_ths": round(agg["total_max_hashrate"] / 1000, 1) if agg["total_max_hashrate"] else 0,
            "avg_hashrate_pct": round(agg["avg_pct"], 1) if agg["avg_pct"] else 0,
        }


@app.get("/query/flagged_miners")
def query_flagged_miners():
    """
    Every miner currently flagged (issue != null) in the most recent scan.
    Returns one row per miner with the full context the LLM needs to
    explain what's wrong to the operator.
    """
    with db_conn() as conn:
        scan_id = _latest_scan_id(conn)
        if scan_id is None:
            return {"error": "no scans in database yet", "miners": []}

        rows = conn.execute(
            "SELECT ip, model, status, ROUND(hashrate/1000.0, 2) AS hashrate_ths, ROUND(max_hashrate/1000.0, 2) AS max_hashrate_ths, hashrate_pct, "
            "       temp_chip, temp_board, issue, action, current_profile, "
            "       firmware_version, map_location, uptime "
            "FROM miner_readings "
            "WHERE scan_id = ? AND issue IS NOT NULL AND issue != '' "
            "ORDER BY "
            "  CASE WHEN status = 'OFFLINE' THEN 0 "
            "       WHEN temp_chip >= 84 THEN 1 "
            "       WHEN hashrate_pct < 80 THEN 2 "
            "       ELSE 3 END, "
            "  ip",
            (scan_id,),
        ).fetchall()

        return {
            "scan_id": scan_id,
            "count": len(rows),
            "miners": [dict(r) for r in rows],
        }


@app.get("/query/miner_history/{ip}")
def query_miner_history(ip: str, hours: int = 24):
    """
    Time-series of readings for one miner over the last N hours.
    Used to answer "what has miner .36 been doing today?"

    hours default 24, max 168 (1 week) to protect the DB from huge queries.
    """
    if hours < 1 or hours > 168:
        return {"error": "hours must be between 1 and 168"}

    with db_conn() as conn:
        rows = conn.execute(
            "SELECT scan_id, scanned_at, status, ROUND(hashrate/1000.0, 2) AS hashrate_ths, hashrate_pct, "
            "       temp_chip, temp_board, issue, action, current_profile "
            "FROM miner_readings "
            "WHERE ip = ? "
            "  AND scanned_at >= datetime('now', ? || ' hours') "
            "ORDER BY scanned_at DESC "
            "LIMIT 500",
            (ip, f"-{hours}"),
        ).fetchall()

        if not rows:
            return {
                "ip": ip,
                "hours": hours,
                "count": 0,
                "readings": [],
                "note": f"no readings for {ip} in the last {hours} hours",
            }

        latest = rows[0]
        oldest = rows[-1]
        return {
            "ip": ip,
            "model": None,  # joined below if possible
            "hours": hours,
            "count": len(rows),
            "latest": dict(latest),
            "oldest_in_window": dict(oldest),
            "readings": [dict(r) for r in rows],
        }


@app.get("/query/recent_actions")
def query_recent_actions(hours: int = 4, limit: int = 50):
    """
    Recent entries from action_audit_log — every approve/deny/auto-execute
    decision the bot has made, with who approved it and any notes.

    Default window 4 hours, max 168 (1 week). Default limit 50, max 500.
    """
    if hours < 1 or hours > 168:
        return {"error": "hours must be between 1 and 168"}
    if limit < 1 or limit > 500:
        return {"error": "limit must be between 1 and 500"}

    with db_conn() as conn:
        rows = conn.execute(
            "SELECT timestamp, miner_id, ip, model, problem, action_taken, "
            "       decision, approved_by, notes "
            "FROM action_audit_log "
            "WHERE timestamp >= datetime('now', ? || ' hours') "
            "ORDER BY timestamp DESC "
            "LIMIT ?",
            (f"-{hours}", limit),
        ).fetchall()

        return {
            "hours": hours,
            "count": len(rows),
            "actions": [dict(r) for r in rows],
        }


@app.get("/query/miner_outcomes/{ip}")
def query_miner_outcomes(ip: str, limit: int = 20):
    """
    Recent restart outcomes for a single miner from miner_restarts table.
    Shows hashrate_before, hashrate_after, and whether the outcome was
    SUCCESS or FAILURE. Used to answer "is the bot's fixing actually
    working on this miner, or is it stuck in a failure loop?"
    """
    if limit < 1 or limit > 200:
        return {"error": "limit must be between 1 and 200"}

    with db_conn() as conn:
        rows = conn.execute(
            "SELECT restarted_at, restart_type, outcome, "
            "       hashrate_before, hashrate_after, recovery_time_scans "
            "FROM miner_restarts "
            "WHERE ip = ? "
            "ORDER BY restarted_at DESC "
            "LIMIT ?",
            (ip, limit),
        ).fetchall()

        if not rows:
            return {"ip": ip, "count": 0, "outcomes": [],
                    "note": f"no restart history for {ip}"}

        success = sum(1 for r in rows if r["outcome"] == "SUCCESS")
        failure = sum(1 for r in rows if r["outcome"] == "FAILURE")

        return {
            "ip": ip,
            "count": len(rows),
            "success_count": success,
            "failure_count": failure,
            "outcomes": [dict(r) for r in rows],
        }


@app.get("/query/board_health/{ip}")
def query_board_health(ip: str):
    """
    Per-board health for a miner from the most recent chain_readings entry.
    Shows hashrate, voltage, frequency, hw_errors, and temperature per board.
    Used to answer "which boards are dying on miner X?"
    """
    with db_conn() as conn:
        scan_id = _latest_scan_id(conn)
        if scan_id is None:
            return {"error": "no scans in database yet"}

        rows = conn.execute(
            "SELECT board_index, rate_mhs, voltage, freq_mhz, consumption_w, "
            "       hw_errors, temp_board, temp_chip "
            "FROM chain_readings "
            "WHERE ip = ? AND scan_id = ? "
            "ORDER BY board_index",
            (ip, scan_id),
        ).fetchall()

        if not rows:
            return {"ip": ip, "count": 0, "boards": [],
                    "note": f"no board readings for {ip} in latest scan"}

        return {
            "ip": ip,
            "scan_id": scan_id,
            "count": len(rows),
            "boards": [dict(r) for r in rows],
        }


@app.get("/query/worst_performers")
def query_worst_performers(limit: int = 5):
    """
    Bottom N miners by hashrate_pct in the most recent scan.
    Excludes OFFLINE miners (they're 0% by definition and not interesting
    for a "who's underperforming" question).
    """
    if limit < 1 or limit > 50:
        return {"error": "limit must be between 1 and 50"}

    with db_conn() as conn:
        scan_id = _latest_scan_id(conn)
        if scan_id is None:
            return {"error": "no scans in database yet", "miners": []}

        rows = conn.execute(
            "SELECT ip, model, status, ROUND(hashrate/1000.0, 2) AS hashrate_ths, ROUND(max_hashrate/1000.0, 2) AS max_hashrate_ths, hashrate_pct, "
            "       temp_chip, issue, map_location "
            "FROM miner_readings "
            "WHERE scan_id = ? AND status != 'OFFLINE' "
            "ORDER BY hashrate_pct ASC "
            "LIMIT ?",
            (scan_id, limit),
        ).fetchall()

        return {
            "scan_id": scan_id,
            "count": len(rows),
            "miners": [dict(r) for r in rows],
        }


@app.get("/query/known_dead_boards")
def query_known_dead_boards():
    """
    Miners in the known_dead_boards table — the ones the bot has given up on
    and ticketed. These are suppressed from flag reports, so the LLM needs
    a dedicated query to surface them when asked.
    """
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT miner_id, ip, model, board_indices, first_seen, "
            "       restart_attempted, restart_result, ticket_created, notes "
            "FROM known_dead_boards "
            "WHERE resolved_at IS NULL "
            "ORDER BY first_seen DESC"
        ).fetchall()

        return {
            "count": len(rows),
            "miners": [dict(r) for r in rows],
        }


@app.get("/query/hvac_latest")
def query_hvac_latest():
    """
    Most recent HVAC reading from the BAS.
    OPERATOR NOTE (per CLAUDE.md memory rules): Low delta-T is intentional
    and expected. Do NOT flag low delta-T as a problem in LLM responses.
    """
    with db_conn() as conn:
        row = conn.execute(
            "SELECT recorded_at, supply_temp_f, return_temp_f, delta_t_f, "
            "       diff_pressure, spray_pump_on, cwp1_vfd_pct, cwp2_vfd_pct, "
            "       ct1_vfd_pct, ct2_vfd_pct, leak_alarm, ct1_fault, ct2_fault, "
            "       pump_fault "
            "FROM hvac_readings "
            "ORDER BY recorded_at DESC LIMIT 1"
        ).fetchone()

        if not row:
            return {"error": "no hvac readings yet"}

        d = dict(row)
        d["operator_note"] = (
            "Low delta-T is intentional and expected for this facility. "
            "Do not flag low delta-T as a problem."
        )
        return d


# ── END QUERY ENDPOINTS ──




# ── ASK PAGE (operator natural-language query interface) ──
#
# A simple text-box page that takes operator questions in plain English,
# keyword-routes them to the right /query/* endpoint, and renders the
# answer in natural language. No LLM in the loop. Deterministic,
# <2 second response time, works offline, works on the Mac mini, works
# for customers without a GPU. This is the primary fleet-query UI.
#
# TEMP: None. This page is portable as-is to the Mac mini on May 1.

import re as _ask_re

ASK_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mining Guardian — Ask</title>
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0b1220;
    color: #e6edf3;
    min-height: 100vh;
    padding: 20px;
  }
  .container { max-width: 820px; margin: 0 auto; }
  h1 {
    font-size: 22px;
    margin: 0 0 4px 0;
    color: #58a6ff;
  }
  .subtitle { color: #8b949e; font-size: 13px; margin-bottom: 20px; }
  .ask-box {
    display: flex;
    gap: 8px;
    margin-bottom: 20px;
  }
  #q {
    flex: 1;
    padding: 14px 16px;
    font-size: 16px;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    color: #e6edf3;
    outline: none;
  }
  #q:focus { border-color: #58a6ff; }
  button {
    padding: 14px 22px;
    font-size: 16px;
    background: #238636;
    border: none;
    border-radius: 8px;
    color: white;
    cursor: pointer;
    font-weight: 600;
  }
  button:hover { background: #2ea043; }
  button:disabled { background: #30363d; cursor: not-allowed; }
  .examples {
    font-size: 12px;
    color: #8b949e;
    margin-bottom: 20px;
  }
  .examples span {
    display: inline-block;
    padding: 4px 10px;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 16px;
    margin: 3px;
    cursor: pointer;
    transition: all 0.15s;
  }
  .examples span:hover { background: #21262d; border-color: #58a6ff; color: #58a6ff; }
  .answer {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 18px 22px;
    margin-top: 20px;
    white-space: pre-wrap;
    line-height: 1.55;
    font-size: 15px;
  }
  .answer.error { border-color: #da3633; background: #2d1114; }
  .answer h3 {
    margin: 0 0 12px 0;
    color: #58a6ff;
    font-size: 16px;
  }
  .answer table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 8px;
    font-size: 13px;
  }
  .answer td, .answer th {
    padding: 6px 10px;
    text-align: left;
    border-bottom: 1px solid #21262d;
  }
  .answer th { color: #8b949e; font-weight: 500; }
  .loading { color: #8b949e; font-style: italic; }
  .meta { color: #8b949e; font-size: 12px; margin-top: 8px; }
  .good { color: #3fb950; }
  .bad { color: #f85149; }
  .warn { color: #d29922; }
  a { color: #58a6ff; text-decoration: none; }
  a:hover { text-decoration: underline; }
</style>
</head>
<body>
<div class="container">
  <h1>🛡️ Mining Guardian — Ask</h1>
  <div class="subtitle">Ask about the fleet in plain English. Answers come from the live database.</div>

  <div class="ask-box">
    <input type="text" id="q" placeholder="how many miners are flagged right now?" autofocus>
    <button id="go" onclick="ask()">Ask</button>
  </div>

  <div class="examples">
    Try:
    <span onclick="setQ(this)">fleet summary</span>
    <span onclick="setQ(this)">flagged miners</span>
    <span onclick="setQ(this)">worst performers</span>
    <span onclick="setQ(this)">recent actions</span>
    <span onclick="setQ(this)">known dead boards</span>
    <span onclick="setQ(this)">hvac</span>
    <span onclick="setQ(this)">history of 192.168.188.36</span>
    <span onclick="setQ(this)">boards on 192.168.188.55</span>
  </div>

  <div id="answer"></div>
</div>

<script>
const qEl = document.getElementById('q');
const ansEl = document.getElementById('answer');
const btn = document.getElementById('go');

function setQ(el) {
  qEl.value = el.textContent;
  qEl.focus();
}

qEl.addEventListener('keydown', e => {
  if (e.key === 'Enter') ask();
});

async function ask() {
  const q = qEl.value.trim();
  if (!q) return;
  btn.disabled = true;
  ansEl.innerHTML = '<div class="answer loading">Thinking…</div>';
  try {
    const r = await fetch('/ask/query?q=' + encodeURIComponent(q));
    const d = await r.json();
    if (d.error) {
      ansEl.innerHTML = '<div class="answer error"><h3>Sorry</h3>' + escapeHtml(d.error) + '</div>';
    } else {
      ansEl.innerHTML = '<div class="answer">' + d.html + '<div class="meta">' + (d.meta || '') + '</div></div>';
    }
  } catch (err) {
    ansEl.innerHTML = '<div class="answer error"><h3>Error</h3>' + escapeHtml(String(err)) + '</div>';
  }
  btn.disabled = false;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}
</script>
</body>
</html>
"""


@app.get("/ask", response_class=HTMLResponse)
def ask_page():
    """Operator natural-language query interface."""
    return ASK_PAGE_HTML


def _fmt_temp(t):
    if t is None:
        return "—"
    try:
        v = float(t)
    except Exception:
        return "—"
    if v >= 84:
        return f'<span class="bad">{v:.0f}°C</span>'
    if v >= 78:
        return f'<span class="warn">{v:.0f}°C</span>'
    return f"{v:.0f}°C"


def _fmt_pct(p):
    if p is None:
        return "—"
    try:
        v = float(p)
    except Exception:
        return "—"
    if v < 80:
        return f'<span class="bad">{v:.1f}%</span>'
    if v < 95:
        return f'<span class="warn">{v:.1f}%</span>'
    return f'<span class="good">{v:.1f}%</span>'


def _fmt_hashrate(h):
    """Format hashrate for display. The DB stores values that look like
    they're in GH/s for some columns and TH/s for others — we normalize
    by dividing large numbers down."""
    if h is None:
        return "—"
    try:
        v = float(h)
    except Exception:
        return "—"
    if v > 1000:
        return f"{v/1000:.1f} TH/s"
    return f"{v:.1f} TH/s"


def _ip_in_query(q):
    """Pull an IP address out of a question if one is present."""
    m = _ask_re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', q)
    return m.group(1) if m else None


def _last_octet_in_query(q):
    """Pull a '.36' style shorthand, return full IP with 192.168.188 prefix."""
    m = _ask_re.search(r'(?:^|\s)\.(\d{1,3})(?:\s|$)', q)
    if m:
        return f"192.168.188.{m.group(1)}"
    return None


@app.get("/ask/query")
def ask_query(q: str):
    """
    Keyword-route a natural-language question to the right /query/* endpoint
    and return an HTML-formatted answer.
    """
    ql = q.lower().strip()
    ip = _ip_in_query(q) or _last_octet_in_query(q)

    # ── Routing logic. Order matters — more specific patterns first.

    # Per-miner history
    if ip and any(w in ql for w in ["history", "history of", "what has", "over the last", "past"]):
        with db_conn() as conn:
            hours = 24
            m = _ask_re.search(r'(\d+)\s*(hour|hr|h)', ql)
            if m:
                hours = min(int(m.group(1)), 168)
            rows = conn.execute(
                "SELECT scanned_at, status, ROUND(hashrate/1000.0, 2) AS hashrate_ths, hashrate_pct, temp_chip, issue, action "
                "FROM miner_readings WHERE ip = ? "
                "AND scanned_at >= datetime('now', ? || ' hours') "
                "ORDER BY scanned_at DESC LIMIT 20",
                (ip, f"-{hours}"),
            ).fetchall()
        if not rows:
            return {"html": f"<h3>No history for {ip}</h3>No readings in the last {hours} hours."}
        html = f"<h3>History of {ip} ({hours}h, showing latest 20)</h3>"
        html += "<table><tr><th>Time</th><th>Status</th><th>%</th><th>Chip</th><th>Issue</th></tr>"
        for r in rows:
            issue = (r["issue"] or "").replace("<", "&lt;")[:40]
            html += (
                f"<tr><td>{r['scanned_at'][:19]}</td>"
                f"<td>{r['status']}</td>"
                f"<td>{_fmt_pct(r['hashrate_pct'])}</td>"
                f"<td>{_fmt_temp(r['temp_chip'])}</td>"
                f"<td>{issue}</td></tr>"
            )
        html += "</table>"
        return {"html": html, "meta": f"Miner {ip}"}

    # Per-miner board health
    if ip and any(w in ql for w in ["board", "chain", "hashboard"]):
        with db_conn() as conn:
            scan = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
            if not scan:
                return {"error": "no scans in DB"}
            rows = conn.execute(
                "SELECT board_index, rate_mhs, voltage, freq_mhz, hw_errors, temp_board, temp_chip "
                "FROM chain_readings WHERE ip = ? AND scan_id = ? ORDER BY board_index",
                (ip, scan["id"]),
            ).fetchall()
        if not rows:
            return {"html": f"<h3>{ip}</h3>No board readings in the latest scan."}
        html = f"<h3>Board health — {ip}</h3>"
        html += "<table><tr><th>Board</th><th>Rate</th><th>Volt</th><th>Freq</th><th>HW Err</th><th>Board T</th><th>Chip T</th></tr>"
        for r in rows:
            html += (
                f"<tr><td>#{r['board_index']}</td>"
                f"<td>{r['rate_mhs']:.0f} MH/s</td>"
                f"<td>{r['voltage']:.1f}V</td>"
                f"<td>{r['freq_mhz']:.0f} MHz</td>"
                f"<td>{r['hw_errors']}</td>"
                f"<td>{_fmt_temp(r['temp_board'])}</td>"
                f"<td>{_fmt_temp(r['temp_chip'])}</td></tr>"
            )
        html += "</table>"
        return {"html": html, "meta": f"Latest scan"}

    # Fleet summary / overall status
    if any(w in ql for w in ["summary", "overall", "how is the fleet", "how's the fleet", "fleet status", "overall status"]):
        with db_conn() as conn:
            scan = conn.execute(
                "SELECT id, scanned_at, total_miners, online, offline, issues FROM scans ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not scan:
                return {"error": "no scans in DB"}
            flagged = conn.execute(
                "SELECT COUNT(*) AS n FROM miner_readings WHERE scan_id = ? AND issue IS NOT NULL AND issue != ''",
                (scan["id"],),
            ).fetchone()["n"]
            avg = conn.execute(
                "SELECT AVG(hashrate_pct) AS p FROM miner_readings WHERE scan_id = ? AND status != 'OFFLINE'",
                (scan["id"],),
            ).fetchone()["p"] or 0
        html = "<h3>Fleet Summary</h3>"
        html += f"<b>{scan['online']}</b> online · "
        html += f"<b class='{'bad' if scan['offline'] > 0 else 'good'}'>{scan['offline']}</b> offline · "
        html += f"<b class='{'warn' if flagged > 0 else 'good'}'>{flagged}</b> flagged<br>"
        html += f"Average hashrate: {_fmt_pct(avg)}<br>"
        html += f"Total tracked: {scan['total_miners']} miners"
        return {"html": html, "meta": f"Scan #{scan['id']} · {scan['scanned_at'][:19]}"}

    # How many online
    if "online" in ql and any(w in ql for w in ["how many", "count", "number"]):
        with db_conn() as conn:
            scan = conn.execute(
                "SELECT id, scanned_at, online, offline, total_miners FROM scans ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not scan:
            return {"error": "no scans in DB"}
        html = f"<h3>{scan['online']} miners online</h3>"
        html += f"{scan['offline']} offline · {scan['total_miners']} total"
        return {"html": html, "meta": f"Scan #{scan['id']} · {scan['scanned_at'][:19]}"}

    # Flagged miners
    if any(w in ql for w in ["flag", "broken", "problem", "issue", "wrong"]):
        with db_conn() as conn:
            scan = conn.execute("SELECT id, scanned_at FROM scans ORDER BY id DESC LIMIT 1").fetchone()
            if not scan:
                return {"error": "no scans in DB"}
            rows = conn.execute(
                "SELECT ip, model, status, hashrate_pct, temp_chip, issue, action "
                "FROM miner_readings WHERE scan_id = ? AND issue IS NOT NULL AND issue != '' "
                "ORDER BY CASE WHEN status='OFFLINE' THEN 0 WHEN temp_chip>=84 THEN 1 ELSE 2 END, ip",
                (scan["id"],),
            ).fetchall()
        if not rows:
            return {"html": "<h3>✅ Nothing flagged</h3>The fleet is healthy right now."}
        html = f"<h3>{len(rows)} flagged miner{'s' if len(rows) != 1 else ''}</h3>"
        html += "<table><tr><th>IP</th><th>Status</th><th>%</th><th>Chip</th><th>Issue</th><th>Action</th></tr>"
        for r in rows:
            issue = (r["issue"] or "").replace("<", "&lt;")[:60]
            html += (
                f"<tr><td>{html.escape(str(r['ip']))}</td>"
                f"<td>{r['status']}</td>"
                f"<td>{_fmt_pct(r['hashrate_pct'])}</td>"
                f"<td>{_fmt_temp(r['temp_chip'])}</td>"
                f"<td>{issue}</td>"
                f"<td>{r['action'] or ''}</td></tr>"
            )
        html += "</table>"
        return {"html": html, "meta": f"Scan #{scan['id']} · {scan['scanned_at'][:19]}"}

    # Worst performers
    if any(w in ql for w in ["worst", "bottom", "lowest", "underperform", "under performing", "performing the worst"]):
        limit = 5
        m = _ask_re.search(r'(\d+)\s*worst', ql)
        if m:
            limit = min(int(m.group(1)), 50)
        m2 = _ask_re.search(r'bottom\s*(\d+)', ql)
        if m2:
            limit = min(int(m2.group(1)), 50)
        with db_conn() as conn:
            scan = conn.execute("SELECT id, scanned_at FROM scans ORDER BY id DESC LIMIT 1").fetchone()
            if not scan:
                return {"error": "no scans in DB"}
            rows = conn.execute(
                "SELECT ip, model, hashrate_pct, temp_chip, issue "
                "FROM miner_readings WHERE scan_id = ? AND status != 'OFFLINE' "
                "ORDER BY hashrate_pct ASC LIMIT ?",
                (scan["id"], limit),
            ).fetchall()
        if not rows:
            return {"html": "<h3>No data</h3>"}
        html = f"<h3>{limit} worst performers</h3>"
        html += "<table><tr><th>IP</th><th>Model</th><th>%</th><th>Chip</th><th>Issue</th></tr>"
        for r in rows:
            issue = (r["issue"] or "").replace("<", "&lt;")[:50]
            html += (
                f"<tr><td>{html.escape(str(r['ip']))}</td>"
                f"<td>{(r['model'] or '')[:18]}</td>"
                f"<td>{_fmt_pct(r['hashrate_pct'])}</td>"
                f"<td>{_fmt_temp(r['temp_chip'])}</td>"
                f"<td>{issue}</td></tr>"
            )
        html += "</table>"
        return {"html": html, "meta": f"Scan #{scan['id']} · {scan['scanned_at'][:19]}"}

    # Best performers
    if any(w in ql for w in ["best", "top", "highest", "performing the best"]):
        limit = 5
        m = _ask_re.search(r'(\d+)\s*best', ql)
        if m:
            limit = min(int(m.group(1)), 50)
        m2 = _ask_re.search(r'top\s*(\d+)', ql)
        if m2:
            limit = min(int(m2.group(1)), 50)
        with db_conn() as conn:
            scan = conn.execute("SELECT id, scanned_at FROM scans ORDER BY id DESC LIMIT 1").fetchone()
            if not scan:
                return {"error": "no scans in DB"}
            rows = conn.execute(
                "SELECT ip, model, hashrate_pct, temp_chip "
                "FROM miner_readings WHERE scan_id = ? AND status != 'OFFLINE' "
                "ORDER BY hashrate_pct DESC LIMIT ?",
                (scan["id"], limit),
            ).fetchall()
        if not rows:
            return {"html": "<h3>No data</h3>"}
        html = f"<h3>{limit} best performers</h3>"
        html += "<table><tr><th>IP</th><th>Model</th><th>%</th><th>Chip</th></tr>"
        for r in rows:
            html += (
                f"<tr><td>{html.escape(str(r['ip']))}</td>"
                f"<td>{(r['model'] or '')[:18]}</td>"
                f"<td>{_fmt_pct(r['hashrate_pct'])}</td>"
                f"<td>{_fmt_temp(r['temp_chip'])}</td></tr>"
            )
        html += "</table>"
        return {"html": html, "meta": f"Scan #{scan['id']} · {scan['scanned_at'][:19]}"}

    # Recent actions
    if any(w in ql for w in ["action", "restart", "approval", "approve", "denied", "done", "doing", "activity"]):
        hours = 4
        m = _ask_re.search(r'(\d+)\s*(hour|hr|h)', ql)
        if m:
            hours = min(int(m.group(1)), 168)
        if "overnight" in ql or "last night" in ql:
            hours = 12
        if "today" in ql:
            hours = 24
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT timestamp, ip, action_taken, decision, approved_by, notes "
                "FROM action_audit_log WHERE timestamp >= datetime('now', ? || ' hours') "
                "ORDER BY timestamp DESC LIMIT 30",
                (f"-{hours}",),
            ).fetchall()
        if not rows:
            return {"html": f"<h3>No actions</h3>Nothing in the last {hours} hours."}
        html = f"<h3>{len(rows)} action{'s' if len(rows) != 1 else ''} — last {hours}h</h3>"
        html += "<table><tr><th>Time</th><th>IP</th><th>Action</th><th>Decision</th><th>By</th></tr>"
        for r in rows:
            dec = r["decision"] or ""
            dec_class = "good" if dec == "APPROVED" else ("bad" if dec == "DENIED" else "warn")
            html += (
                f"<tr><td>{(r['timestamp'] or '')[:19]}</td>"
                f"<td>{html.escape(str(r['ip']))}</td>"
                f"<td>{(r['action_taken'] or '')[:18]}</td>"
                f"<td class='{dec_class}'>{dec}</td>"
                f"<td>{(r['approved_by'] or '')[:20]}</td></tr>"
            )
        html += "</table>"
        return {"html": html, "meta": f"Last {hours} hours"}

    # Dead boards
    if any(w in ql for w in ["dead", "ticketed", "gave up"]):
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT miner_id, ip, model, board_indices, first_seen, ticket_created "
                "FROM known_dead_boards WHERE resolved_at IS NULL ORDER BY first_seen DESC"
            ).fetchall()
        if not rows:
            return {"html": "<h3>No dead boards</h3>"}
        html = f"<h3>{len(rows)} miners with dead boards</h3>"
        html += "<table><tr><th>IP</th><th>Model</th><th>Boards</th><th>First seen</th><th>Ticket</th></tr>"
        for r in rows:
            html += (
                f"<tr><td>{html.escape(str(r['ip']))}</td>"
                f"<td>{(r['model'] or '')[:18]}</td>"
                f"<td>{r['board_indices']}</td>"
                f"<td>{(r['first_seen'] or '')[:19]}</td>"
                f"<td>{r['ticket_created'] or ''}</td></tr>"
            )
        html += "</table>"
        return {"html": html}

    # HVAC
    if any(w in ql for w in ["hvac", "cooling", "water temp", "delta", "pump"]):
        with db_conn() as conn:
            row = conn.execute(
                "SELECT recorded_at, supply_temp_f, return_temp_f, delta_t_f, "
                "cwp1_vfd_pct, cwp2_vfd_pct, ct1_vfd_pct, ct2_vfd_pct, leak_alarm "
                "FROM hvac_readings ORDER BY recorded_at DESC LIMIT 1"
            ).fetchone()
        if not row:
            return {"html": "<h3>No HVAC data</h3>"}
        html = "<h3>HVAC — Latest</h3>"
        html += f"Supply: <b>{row['supply_temp_f']:.1f}°F</b> · Return: <b>{row['return_temp_f']:.1f}°F</b> · ΔT: <b>{row['delta_t_f']:.1f}°F</b><br>"
        html += f"CWP1: {row['cwp1_vfd_pct']:.0f}% · CWP2: {row['cwp2_vfd_pct']:.0f}%<br>"
        html += f"CT1: {row['ct1_vfd_pct']:.0f}% · CT2: {row['ct2_vfd_pct']:.0f}%"
        if row["leak_alarm"]:
            html += "<br><span class='bad'>⚠ LEAK ALARM</span>"
        return {"html": html, "meta": f"{row['recorded_at'][:19]}"}

    # Fallback — didn't match anything
    return {
        "error": (
            "I didn't understand that. Try: fleet summary, flagged miners, "
            "worst performers, best performers, recent actions, dead boards, "
            "hvac, or 'history of 192.168.188.X' / 'boards on 192.168.188.X'."
        )
    }


# ── END ASK PAGE ──






# ── AI Recent Analyses with Confidence (for Grafana) ─────────────────────────

@app.get("/ai/recent_analyses")
def ai_recent_analyses(hours: int = 6):
    """Recent AI analyses with confidence scores.
    
    Returns LLM outputs from the last N hours, each with confidence %.
    Perfect for Grafana table display. 6-hour window keeps it fresh.
    
    Args:
        hours: How many hours back to include (default 6, max 24)
    """
    hours = min(hours, 24)
    cutoff = datetime.now() - timedelta(hours=hours)
    cutoff_str = cutoff.isoformat()
    
    try:
        with open(_ROOT / "knowledge.json", "r") as f:
            knowledge = json.load(f)
    except Exception as e:
        return {"error": f"Cannot read knowledge.json: {e}"}
    
    analyses = []
    conf_map = {"HIGH": 90, "MEDIUM": 70, "LOW": 40}
    
    # 1. Predictions (already have numeric confidence)
    for p in knowledge.get("predictions", []):
        predicted_at = p.get("predicted_at", "")
        if predicted_at >= cutoff_str:
            signals = p.get("signals", [])[:2]
            analyses.append({
                "type": "PREDICTION",
                "timestamp": predicted_at,
                "miner_ip": p.get("ip", "?"),
                "model": p.get("model", "?").replace("Antminer ", ""),
                "statement": f"{p.get('action', '?')}: {', '.join(signals)}",
                "confidence_pct": p.get("confidence", 0),
                "outcome": p.get("outcome")
            })

    # 2. Refined insights (convert HIGH/MEDIUM/LOW to numeric)
    for key, insight in knowledge.get("refined_insights", {}).items():
        last_updated = insight.get("last_updated", "")
        if last_updated >= cutoff_str[:10]:
            miners = insight.get("miners_affected", [])[:3]
            analyses.append({
                "type": "INSIGHT",
                "timestamp": last_updated,
                "miner_ip": ", ".join(miners) if miners else "fleet",
                "model": insight.get("miner_type", "Various").replace("Antminer ", ""),
                "statement": insight.get("insight", "")[:150],
                "confidence_pct": conf_map.get(insight.get("confidence", "MEDIUM"), 70),
                "outcome": insight.get("action")
            })
    
    # 3. Daily deep analysis fleet synthesis (most recent)
    deep_analyses = knowledge.get("daily_deep_analyses", [])
    if isinstance(deep_analyses, list):
        for da in deep_analyses:
            timestamp = da.get("timestamp", "")
            if timestamp >= cutoff_str:
                fleet_syn = da.get("fleet_synthesis", "")
                for line in fleet_syn.split("\n"):
                    line = line.strip()
                    if line and len(line) > 20:
                        conf = 75
                        if "(" in line and "%" in line:
                            try:
                                conf = int(line.split("(")[-1].split("%")[0])
                            except Exception:
                                pass
                        analyses.append({
                            "type": "ANALYSIS",
                            "timestamp": timestamp,
                            "miner_ip": "fleet",
                            "model": "Fleet-wide",
                            "statement": line[:150],
                            "confidence_pct": conf,
                            "outcome": None
                        })

    # Sort by timestamp descending, limit to 50
    analyses.sort(key=lambda x: x["timestamp"], reverse=True)
    analyses = analyses[:50]
    
    # Summary stats
    if analyses:
        avg_conf = sum(a["confidence_pct"] for a in analyses) / len(analyses)
        high_conf = sum(1 for a in analyses if a["confidence_pct"] >= 80)
        med_conf = sum(1 for a in analyses if 50 <= a["confidence_pct"] < 80)
        low_conf = sum(1 for a in analyses if a["confidence_pct"] < 50)
    else:
        avg_conf = high_conf = med_conf = low_conf = 0
    
    return {
        "summary": {
            "total_analyses": len(analyses),
            "avg_confidence_pct": round(avg_conf, 1),
            "high_confidence": high_conf,
            "medium_confidence": med_conf,
            "low_confidence": low_conf,
            "time_window_hours": hours
        },
        "analyses": analyses,
        "generated_at": datetime.now().isoformat()
    }

# ============================================================
# HVAC Data Ingestion Endpoint (receives data from Mac collector)
# Added: April 13, 2026
# ============================================================

@app.post("/api/hvac/ingest")
async def ingest_hvac_data(request: Request):
    """
    Receive HVAC readings from Mac collector and store in DB.
    Expected payload:
    {
        "system_id": "warehouse" | "s19jpro",
        "readings": {
            "supply_temp_f": float,
            "return_temp_f": float,
            "delta_t_f": float,
            ...
        },
        "timestamp": "ISO8601"
    }
    """
    try:
        data = await request.json()
        system_id = data.get("system_id")
        readings = data.get("readings", {})
        timestamp = data.get("timestamp")
        
        if not system_id or not readings:
            return {"error": "Missing system_id or readings"}
        
        # Store in hvac_readings table with system_id
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                INSERT INTO hvac_readings (
                    recorded_at, system_id,
                    supply_temp_f, return_temp_f, delta_t_f, diff_pressure,
                    outside_air_f, container_temp_f,
                    cwp1_vfd_pct, cwp2_vfd_pct, ct1_vfd_pct, ct2_vfd_pct,
                    leak_alarm
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp or datetime.utcnow().isoformat(),
                system_id,
                readings.get("supply_temp_f"),
                readings.get("return_temp_f"),
                readings.get("delta_t_f"),
                readings.get("diff_pressure_psi"),
                readings.get("outside_air_f"),
                readings.get("container_temp_f"),
                readings.get("cwp1_vfd_pct"),
                readings.get("cwp2_vfd_pct"),
                readings.get("ct1_vfd_pct"),
                readings.get("ct2_vfd_pct"),
                1 if readings.get("leak_alarm") else 0,
            ))
        
        return {"status": "ok", "system_id": system_id}
    except Exception as e:
        logger.error(f"HVAC ingest error: {e}")
        return {"error": str(e)}


@app.get("/api/hvac/latest")
async def get_latest_hvac():
    """Get latest HVAC readings for all systems."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
    
        results = {}
        for system_id in ["warehouse", "s19jpro"]:
            row = conn.execute("""
                SELECT * FROM hvac_readings
                WHERE system_id = ?
                ORDER BY recorded_at DESC LIMIT 1
            """, (system_id,)).fetchone()
            if row:
                results[system_id] = dict(row)
    
    finally:
        conn.close()
    return results


# ── Intelligence Report API Proxy ─────────────────────────────────────────────
# Proxies requests to the Intelligence Report API (port 8590) so the Grafana
# Business Text panel can fetch over HTTPS via the Cloudflare tunnel.
# Without this, browsers block mixed content (HTTPS page → HTTP fetch).
import urllib.request
import urllib.error

_REPORT_API = "http://127.0.0.1:8590"

@app.get("/api/report/{slug}/html/render", response_class=HTMLResponse)
def render_intelligence_report(slug: str):
    """Render full HTML page for Intelligence Report (used by iframe in Grafana)."""
    try:
        url = f"{_REPORT_API}/api/report/{slug}/html"
        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as he:
            # Read the error body — intelligence_report_api returns JSON with html/error keys even on 4xx/5xx
            try:
                data = json.loads(he.read().decode())
            except Exception:
                data = {"error": f"HTTP {he.code}: {he.reason}"}
        if "html" in data:
            # Wrap in a full HTML page with dark background matching Grafana
            return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body {{ margin:0; padding:0; background:#181b1f; color:#e2e8f0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; }}
</style></head><body>{data['html']}</body></html>"""
        elif "error" in data:
            return f'<html><body style="background:#181b1f;color:#ef4444;text-align:center;padding:40px;font-size:16px;">{data["error"]}</body></html>'
        return '<html><body style="background:#181b1f;color:#94a3b8;text-align:center;padding:40px;">No report data</body></html>'
    except Exception as e:
        return f'<html><body style="background:#181b1f;color:#ef4444;text-align:center;padding:40px;">Error: {str(e)}</body></html>'


@app.get("/api/report/{path:path}")
def proxy_intelligence_report(path: str, request: Request):
    """Proxy to Intelligence Report API on port 8590."""
    qs = str(request.query_params)
    url = f"{_REPORT_API}/api/report/{path}"
    if qs:
        url += f"?{qs}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data
    except urllib.error.URLError as e:
        return {"error": f"Intelligence Report API unreachable: {str(e)}"}
    except Exception as e:
        return {"error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# MOBILE DASHBOARD — Phone-friendly fleet status
# Added: April 22, 2026
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/mobile", response_class=HTMLResponse)
def mobile_dashboard():
    """Mobile-friendly fleet status page. Works on any phone browser."""
    conn = get_db()
    try:
    
        # Fleet summary
        fleet = conn.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'online' THEN 1 ELSE 0 END) as online,
                SUM(CASE WHEN status != 'online' THEN 1 ELSE 0 END) as offline
            FROM miner_readings 
            WHERE id IN (SELECT MAX(id) FROM miner_readings GROUP BY miner_id)
        ''').fetchone()
    
        # Flagged miners count
        flagged = conn.execute('''
            SELECT COUNT(DISTINCT miner_id) FROM miner_readings
            WHERE id IN (SELECT MAX(id) FROM miner_readings GROUP BY miner_id)
            AND issue IS NOT NULL AND issue != 
        ''').fetchone()[0]
    
        # Latest scan time
        latest_scan = conn.execute(
            "SELECT scanned_at FROM scans ORDER BY id DESC LIMIT 1"
        ).fetchone()
        scan_time = latest_scan[0][:16] if latest_scan else "Unknown"
    
        # Critical miners (0% hashrate, online)
        critical = conn.execute('''
            SELECT ip, model, hashrate_pct, temp_chip
            FROM miner_readings
            WHERE id IN (SELECT MAX(id) FROM miner_readings GROUP BY miner_id)
            AND status = 'online' AND hashrate_pct < 10
            ORDER BY hashrate_pct ASC
            LIMIT 5
        ''').fetchall()
    
        # Hot miners (temp > 75C)
        hot = conn.execute('''
            SELECT ip, model, temp_chip, hashrate_pct
            FROM miner_readings
            WHERE id IN (SELECT MAX(id) FROM miner_readings GROUP BY miner_id)
            AND temp_chip > 75
            ORDER BY temp_chip DESC
            LIMIT 5
        ''').fetchall()
    
        # Weather
        weather = conn.execute(
            "SELECT temp_f, humidity_pct FROM weather_readings ORDER BY id DESC LIMIT 1"
        ).fetchone()
    
    finally:
        conn.close()
    
    # Build critical miners HTML
    critical_html = ""
    if critical:
        for m in critical:
            critical_html += f'''
            <div class="miner-card critical">
                <div class="ip">{m[0]}</div>
                <div class="model">{(m[1] or 'Unknown').replace('Antminer_', '')}</div>
                <div class="stats">
                    <span class="bad">{m[2]:.0f}% HR</span>
                    <span>{m[3]:.0f}°C</span>
                </div>
            </div>'''
    else:
        critical_html = '<div class="no-issues">✓ No critical miners</div>'
    
    # Build hot miners HTML
    hot_html = ""
    if hot:
        for m in hot:
            temp_class = "warn" if m[2] < 84 else "bad"
            hot_html += f'''
            <div class="miner-card hot">
                <div class="ip">{m[0]}</div>
                <div class="model">{(m[1] or 'Unknown').replace('Antminer_', '')}</div>
                <div class="stats">
                    <span class="{temp_class}">{m[2]:.0f}°C</span>
                    <span>{m[3]:.0f}% HR</span>
                </div>
            </div>'''
    else:
        hot_html = '<div class="no-issues">✓ All temps normal</div>'
    
    weather_html = f"{weather[0]:.0f}°F / {weather[1]:.0f}%" if weather else "N/A"
    
    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <title>Mining Guardian</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            padding: 16px;
            padding-top: env(safe-area-inset-top, 16px);
        }}
        .header {{
            text-align: center;
            margin-bottom: 20px;
        }}
        .header h1 {{
            font-size: 1.5rem;
            color: #4ade80;
        }}
        .header .scan-time {{
            font-size: 0.8rem;
            color: #888;
            margin-top: 4px;
        }}
        .weather {{
            font-size: 0.9rem;
            color: #60a5fa;
            margin-top: 4px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
            margin-bottom: 20px;
        }}
        .stat {{
            background: #252542;
            border-radius: 12px;
            padding: 12px 8px;
            text-align: center;
        }}
        .stat .value {{
            font-size: 1.8rem;
            font-weight: bold;
        }}
        .stat .label {{
            font-size: 0.7rem;
            color: #888;
            text-transform: uppercase;
        }}
        .stat.online .value {{ color: #4ade80; }}
        .stat.offline .value {{ color: #f87171; }}
        .stat.flagged .value {{ color: #fbbf24; }}
        .stat.total .value {{ color: #60a5fa; }}
        .section {{
            background: #252542;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 16px;
        }}
        .section h2 {{
            font-size: 1rem;
            margin-bottom: 12px;
            color: #888;
        }}
        .section h2.critical {{ color: #f87171; }}
        .section h2.hot {{ color: #fbbf24; }}
        .miner-card {{
            background: #1a1a2e;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .miner-card .ip {{
            font-family: monospace;
            font-size: 0.9rem;
        }}
        .miner-card .model {{
            font-size: 0.75rem;
            color: #888;
        }}
        .miner-card .stats {{
            text-align: right;
        }}
        .miner-card .stats span {{
            display: block;
            font-size: 0.9rem;
        }}
        .bad {{ color: #f87171; }}
        .warn {{ color: #fbbf24; }}
        .good {{ color: #4ade80; }}
        .no-issues {{
            color: #4ade80;
            text-align: center;
            padding: 20px;
        }}
        .refresh-btn {{
            display: block;
            width: 100%;
            padding: 14px;
            background: #4ade80;
            color: #1a1a2e;
            border: none;
            border-radius: 12px;
            font-size: 1rem;
            font-weight: bold;
            cursor: pointer;
            margin-top: 10px;
        }}
        .refresh-btn:active {{
            background: #22c55e;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>⛏️ Mining Guardian</h1>
        <div class="scan-time">Last scan: {scan_time}</div>
        <div class="weather">🌡️ {weather_html}</div>
    </div>
    
    <div class="stats-grid">
        <div class="stat total">
            <div class="value">{fleet[0] or 0}</div>
            <div class="label">Total</div>
        </div>
        <div class="stat online">
            <div class="value">{fleet[1] or 0}</div>
            <div class="label">Online</div>
        </div>
        <div class="stat offline">
            <div class="value">{fleet[2] or 0}</div>
            <div class="label">Offline</div>
        </div>
        <div class="stat flagged">
            <div class="value">{flagged}</div>
            <div class="label">Flagged</div>
        </div>
    </div>
    
    <div class="section">
        <h2 class="critical">🚨 Critical Miners</h2>
        {critical_html}
    </div>
    
    <div class="section">
        <h2 class="hot">🔥 Hot Miners</h2>
        {hot_html}
    </div>
    
    <button class="refresh-btn" onclick="location.reload()">↻ Refresh</button>
    
    <script>
        // Auto-refresh every 60 seconds
        setTimeout(() => location.reload(), 60000);
    </script>
</body>
</html>'''

if __name__ == "__main__":
    import uvicorn
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Mining Guardian Dashboard API")
    print("  http://localhost:8585")
    print("  http://localhost:8585/docs  ← interactive API docs")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    uvicorn.run(app, host="127.0.0.1", port=8585)


