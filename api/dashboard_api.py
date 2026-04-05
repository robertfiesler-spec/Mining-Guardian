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
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

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
                               "AI knowledge score: insights + patterns * 10 + profiles", ["site"])

SITE = "usa_188"

DB_PATH = str(_ROOT / "guardian.db")
app = FastAPI(title="Mining Guardian API", version="1.0.0")

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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


from contextlib import contextmanager

@contextmanager
def db_conn():
    """Context manager for DB connections — guarantees close on exceptions."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# ── Prometheus /metrics endpoint ─────────────────────────────

@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint — scraped every 30s by Prometheus."""
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
            SELECT ip, model, hashrate_pct, hashrate, temp_chip, pdu_power,
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
                actual_ths = float(m["hashrate"] or 0) / 1000.0
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
        score     = insights + (patterns * 10) + profiles
        g_knowledge_insights.labels(site=SITE).set(insights)
        g_knowledge_patterns.labels(site=SITE).set(patterns)
        g_knowledge_profiles.labels(site=SITE).set(profiles)
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
    return PlainTextResponse(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


@app.get("/fleet/board_stats", response_class=HTMLResponse)
def fleet_board_stats():
    """Fleet board health: worst rejection rates + worst HW error miners, side by side."""
    conn = get_db()
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
def fleet_latest():
    """Latest scan summary — fleet status right now."""
    conn = get_db()
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
    conn.close()
    return scan


@app.get("/fleet/history")
def fleet_history(days: int = 7):
    days = min(max(days, 1), 90)
    """Scan history over the last N days."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM scans WHERE scanned_at > ? ORDER BY id DESC",
        (cutoff,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Miners ───────────────────────────────────────────────────

@app.get("/miners/flagged")
def miners_flagged():
    """All miners currently flagged in the latest scan."""
    conn = get_db()
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
    conn.close()
    return [dict(r) for r in rows]


@app.get("/miners/most_flagged")
def miners_most_flagged(limit: int = 20):
    """Miners flagged most often — trouble list."""
    conn = get_db()
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
    conn.close()
    return [dict(r) for r in rows]


@app.get("/miners/{miner_id}/history")
def miner_history(miner_id: str, days: int = 7):
    days = min(max(days, 1), 90)
    """Full telemetry history for a specific miner."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = get_db()
    rows = conn.execute("""
        SELECT scanned_at, hashrate_pct, temp_chip, status, action, issue
        FROM miner_readings
        WHERE miner_id = ? AND scanned_at > ?
        ORDER BY scanned_at ASC
    """, (miner_id, cutoff)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/miners/{miner_id}/logs")
def miner_logs(miner_id: str, limit: int = 10):
    """Recent log files collected for a miner."""
    conn = get_db()
    rows = conn.execute("""
        SELECT collected_at, health_status, log_file, content
        FROM miner_logs
        WHERE miner_id = ?
        ORDER BY id DESC
        LIMIT ?
    """, (miner_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Temperature ───────────────────────────────────────────────

@app.get("/temps/hot_miners")
def temps_hot_miners():
    """Miners currently in yellow or red temp zones."""
    conn = get_db()
    scan = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    if not scan:
        return []
    rows = conn.execute("""
        SELECT miner_id, ip, model, temp_chip, action
        FROM miner_readings
        WHERE scan_id = ? AND temp_chip >= 76
        ORDER BY temp_chip DESC
    """, (scan["id"],)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/temps/history")
def temps_history(days: int = 7):
    days = min(max(days, 1), 90)
    """Average chip temp across fleet over time."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = get_db()
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
    conn.close()
    return [dict(r) for r in rows]


# ── Power ─────────────────────────────────────────────────────

@app.get("/weather/history")
def weather_history(days: int = 7):
    days = min(max(days, 1), 90)
    """Ambient temp and humidity history."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM weather_readings WHERE recorded_at > ? ORDER BY id ASC",
        (cutoff,)
    ).fetchall()
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
def notifications_recent(limit: int = 50):
    """Recent AMS notifications grouped by type."""
    conn = get_db()
    rows = conn.execute("""
        SELECT key, alert_level, miner_ip, recorded_at
        FROM ams_notifications
        ORDER BY id DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/notifications/summary")
def notifications_summary():
    """Notification counts grouped by type and severity."""
    conn = get_db()
    rows = conn.execute("""
        SELECT key, alert_level, COUNT(*) as count
        FROM ams_notifications
        GROUP BY key, alert_level
        ORDER BY count DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Restarts ──────────────────────────────────────────────────

@app.get("/restarts/recent")
def restarts_recent(limit: int = 20):
    """Recent restart events."""
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM miner_restarts
        ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/audit/log")
def audit_log(days: int = None, miner_id: str = None, limit: int = 100):
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
        rows = conn.execute(
            "SELECT * FROM llm_analysis ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    except Exception:
        rows = []
    conn.close()
    if rows:
        return [dict(r) for r in rows]
    # Fallback: proxy from VPS
    try:
        import requests as _req
        resp = _req.get(f"http://100.106.123.83:8585/llm/history?limit={limit}", timeout=5)
        return resp.json()
    except Exception:
        return []


# ── Environment Chart (standalone HTML) ───────────────────────

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


# ── Health Check ──────────────────────────────────────────────

@app.get("/")
def health():
    conn = get_db()
    scan_count = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
    latest = conn.execute(
        "SELECT scanned_at FROM scans ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return {
        "status": "online",
        "db": "guardian.db",  # path redacted — don't leak filesystem layout
        "total_scans": scan_count,
        "last_scan": latest[0] if latest else None,
    }


if __name__ == "__main__":
    import uvicorn
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Mining Guardian Dashboard API")
    print("  http://localhost:8585")
    print("  http://localhost:8585/docs  ← interactive API docs")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    uvicorn.run(app, host="0.0.0.0", port=8585)
