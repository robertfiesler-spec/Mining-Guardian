#!/usr/bin/env python3
"""
ai_dashboard_api.py
Mining Guardian — AI Intelligence Center Dashboard

The flagship customer-facing page. Shows the full AI system:
score, actions, predictions, insights, features, data signals.

Served as HTML at /ai/dashboard via dashboard_api.py
"""

import sys
import sqlite3
import json
import re
import html as html_lib
from datetime import datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT / "ai"), str(_ROOT / "core")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

DB_PATH = str(_ROOT / "guardian.db")
KNOWLEDGE_PATH = str(_ROOT / "knowledge.json")
APPROVAL_API = "https://slack.fieslerfamily.com"


def _db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _e(val):
    return html_lib.escape(str(val)) if val else ""


# ── Data fetchers ────────────────────────────────────────────

def get_action_queue():
    conn = _db()
    rows = conn.execute("""
        SELECT pa.id, pa.miner_id, pa.ip, pa.model, pa.action_type, pa.problem,
               pa.created_at, pa.scan_id,
               mr.hashrate_pct, mr.temp_chip, mr.temp_board, mr.current_profile
        FROM pending_approvals pa
        LEFT JOIN miner_readings mr ON pa.miner_id = mr.miner_id
            AND mr.id = (SELECT MAX(id) FROM miner_readings WHERE miner_id = pa.miner_id)
        WHERE pa.status = 'PENDING'
        ORDER BY pa.created_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_auto_actions(limit=20):
    conn = _db()
    rows = conn.execute("""
        SELECT a.timestamp, a.ip, a.model, a.action_taken, a.problem,
               a.decision, a.approved_by, a.notes,
               r.outcome, r.hashrate_before, r.hashrate_after, r.recovery_time_scans
        FROM action_audit_log a
        LEFT JOIN miner_restarts r ON a.miner_id = r.miner_id
            AND r.restarted_at >= a.timestamp
            AND r.restarted_at <= datetime(a.timestamp, '+5 minutes')
        WHERE a.decision IN ('AUTO_OVERNIGHT', 'APPROVED')
        ORDER BY a.timestamp DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_training_insights():
    try:
        with open(KNOWLEDGE_PATH) as f:
            k = json.load(f)
    except Exception:
        return {}
    return {
        "cross_miner": k.get("cross_miner_analysis", []),
        "patterns": k.get("patterns", []),
        "last_5_insights": k.get("known_issues", [])[-5:],
        "fleet_summary": k.get("fleet_summary", {}),
    }


def get_prediction_status():
    conn = _db()
    preds = conn.execute("""
        SELECT timestamp, ip, model, action_taken, problem, notes
        FROM action_audit_log
        WHERE action_taken LIKE '%PREEMPTIVE%' OR action_taken LIKE '%POWER_PROFILE%'
        ORDER BY timestamp DESC LIMIT 15
    """).fetchall()
    conn.close()
    return [dict(r) for r in preds]


def get_feature_status():
    conn = _db()
    outcomes = conn.execute("SELECT COUNT(*) FROM miner_restarts WHERE outcome IS NOT NULL AND outcome != 'PENDING'").fetchone()[0] or 0
    conf = conn.execute("SELECT COUNT(*) FROM action_audit_log WHERE notes LIKE '%confidence%' OR notes LIKE '%Conf:%'").fetchone()[0] or 0
    denials = conn.execute("SELECT COUNT(*) FROM action_audit_log WHERE notes LIKE '%DENIAL_REASON%'").fetchone()[0] or 0
    try:
        with open(KNOWLEDGE_PATH) as f:
            fps = len(json.load(f).get("miner_profiles", {}))
    except Exception:
        fps = 0
    hvac = conn.execute("SELECT COUNT(*) FROM hvac_readings").fetchone()[0] or 0
    preds = conn.execute("SELECT COUNT(*) FROM action_audit_log WHERE action_taken LIKE '%PREEMPTIVE%'").fetchone()[0] or 0
    diverse = conn.execute("SELECT COUNT(*) FROM action_audit_log WHERE action_taken LIKE '%POWER_PROFILE%' OR action_taken LIKE '%ECO_MODE%'").fetchone()[0] or 0
    conn.close()
    return [
        {"name": "Outcome Feedback", "status": "ACTIVE", "metric": f"{outcomes} labeled", "desc": "Labels every restart SUCCESS/FAILURE/PARTIAL to learn what works"},
        {"name": "Confidence Scoring", "status": "ACTIVE", "metric": f"{conf} scored", "desc": "Rates confidence before every decision — high confidence = auto-execute"},
        {"name": "Denial Reason Capture", "status": "ACTIVE", "metric": f"{denials} reasons", "desc": "Asks why when you deny — turns your judgment into training data"},
        {"name": "Miner Fingerprinting", "status": "ACTIVE", "metric": f"{fps} fingerprints", "desc": "Builds behavioral profiles — every miner has a personality"},
        {"name": "HVAC Correlation", "status": "ACTIVE", "metric": f"{hvac} readings", "desc": "Distinguishes facility problems from miner problems"},
        {"name": "Pre-Failure Prediction", "status": "ACTIVE", "metric": f"{preds} predictions", "desc": "12 signal types detect failures before they happen"},
        {"name": "Repair Shop Data", "status": "PENDING", "metric": "Awaiting dataset", "desc": "Will ingest 1M+ repair records for failure pattern matching"},
        {"name": "Action Diversity", "status": "ACTIVE", "metric": f"{diverse} smart actions", "desc": "Profile tuning, eco mode, pool failover — beyond just restarts"},
    ]


DATA_SIGNALS = [
    # AMS WebSocket signals — pulled per scan (60 min) + monitored continuously
    # by the alert listener every 15 seconds for urgent state changes
    ("Hashrate %", "AMS WebSocket", "60 min + 15s alerts"),
    ("Chip Temperature", "AMS WebSocket", "60 min + 15s alerts"),
    ("Board Temperature", "AMS WebSocket", "60 min + 15s alerts"),
    ("Miner Consumption (W)", "AMS WebSocket", "60 min + 15s alerts"),
    ("Uptime", "AMS WebSocket", "60 min"),
    ("Error Codes", "AMS WebSocket", "60 min + 15s alerts"),
    ("Firmware Version", "AMS WebSocket", "60 min"),
    ("Current Profile", "AMS WebSocket", "60 min"),
    # Chain Readings — per-board structured data, parsed each scan
    ("Board Voltage", "Chain Readings", "60 min"),
    ("Board Frequency", "Chain Readings", "60 min"),
    ("Board HW Errors", "Chain Readings", "60 min"),
    ("Board Power (W)", "Chain Readings", "60 min"),
    # Pool Readings — share counts pulled each scan
    ("Pool Accepted Shares", "Pool Readings", "60 min"),
    ("Pool Rejected Shares", "Pool Readings", "60 min"),
    ("Pool Rejection Rate", "Calculated", "60 min"),
    # PDU — per-outlet power draw, polled with the scan
    ("PDU Power (kW)", "PDU API", "60 min"),
    # HVAC BAS — supply/return water temps, pressures, polled with the scan
    ("Supply Water Temp", "HVAC BAS API", "60 min"),
    ("Return Water Temp", "HVAC BAS API", "60 min"),
    ("Differential Pressure", "HVAC BAS API", "60 min"),
    # Weather — Open-Meteo API call per scan
    ("Outside Temperature", "Open-Meteo", "60 min"),
    ("Outside Humidity", "Open-Meteo", "60 min"),
    # CGMiner Logs — parsed each scan from logs collected once per cycle
    ("Per-Chip Hashrate", "CGMiner Logs", "60 min"),
    ("PSU Voltage", "CGMiner Logs", "60 min"),
    ("System CPU/Memory", "CGMiner Logs", "60 min"),
    ("Board Attach/Detach", "CGMiner Logs", "60 min"),
    # Hardware identity — parsed once and stored permanently (immutable)
    ("Board Serial Number", "CGMiner Logs", "Once"),
    ("Chip Die/Bin/Grade", "CGMiner Logs", "Once"),
    ("PCB/BOM Version", "CGMiner Logs", "Once"),
    ("Control Board Type", "CGMiner Logs", "Once"),
    ("PSU Version", "CGMiner Logs", "Once"),
    # AMS REST + Extended — scan-cadence pulls
    ("AMS Notifications", "AMS REST API", "60 min + 15s alerts"),
    ("Map Location (X,Y)", "AMS Extended", "60 min"),
]


# ── HTML Builder ─────────────────────────────────────────────

def render_ai_dashboard_html():
    from ai_score import calculate_score, format_number

    conn = _db()
    score = calculate_score(conn=conn)
    queue = get_action_queue()
    autos = get_recent_auto_actions(15)
    insights = get_training_insights()
    predictions = get_prediction_status()
    features = get_feature_status()

    G = "#10b981"; B = "#3b82f6"; O = "#f59e0b"; R = "#ef4444"
    P = "#8b5cf6"; C = "#06b6d4"; BG = "#0f172a"; CB = "#1e293b"
    T = "#e2e8f0"; TD = "#94a3b8"

    comp = score["components"]
    fn = format_number

    # ── Build dynamic sections as plain strings ──────────────

    # Action queue rows
    qr = ""
    for q in queue[:10]:
        hr = q.get("hashrate_pct") or 0
        tp = q.get("temp_chip") or 0
        hc = G if hr > 80 else O if hr > 50 else R
        tc = G if tp < 76 else O if tp < 86 else R
        qid = q.get("id", "")
        qr += (
            f'<tr><td style="font-family:monospace;color:{C}">{_e(q.get("ip",""))}</td>'
            f'<td>{_e(q.get("model",""))}</td>'
            f'<td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{_e(str(q.get("problem",""))[:100])}</td>'
            f'<td><span style="background:{B};color:white;padding:2px 8px;border-radius:4px;font-size:11px">{_e(q.get("action_type",""))}</span></td>'
            f'<td style="color:{hc};font-weight:bold">{hr:.0f}%</td>'
            f'<td style="color:{tc}">{tp:.0f}°C</td>'
            f'<td><button onclick="approveAction(\'{qid}\')" style="background:{G};color:white;border:none;padding:4px 12px;border-radius:4px;cursor:pointer;margin-right:4px;font-size:12px">✓ Approve</button>'
            f'<button onclick="denyAction(\'{qid}\')" style="background:{R};color:white;border:none;padding:4px 12px;border-radius:4px;cursor:pointer;font-size:12px">✗ Deny</button></td></tr>'
        )
    if not qr:
        qr = f'<tr><td colspan="7" style="text-align:center;color:{G};padding:20px">✓ No pending actions — system is running autonomously</td></tr>'

    # Auto-action rows
    ar = ""
    for a in autos:
        oc = a.get("outcome") or "—"
        bc = {
            "SUCCESS": G, "FAILURE": R, "PARTIAL": O
        }.get(oc, TD)
        badge = f'<span style="background:{bc};color:white;padding:2px 8px;border-radius:4px;font-size:11px">{_e(oc)}</span>'
        ts = str(a.get("timestamp", ""))[:16]
        ar += (
            f'<tr><td style="color:{TD};font-size:12px">{_e(ts)}</td>'
            f'<td style="font-family:monospace;color:{C}">{_e(a.get("ip",""))}</td>'
            f'<td>{_e(a.get("model",""))}</td>'
            f'<td>{_e(a.get("action_taken",""))}</td>'
            f'<td>{badge}</td>'
            f'<td style="color:{TD}">{_e(str(a.get("problem",""))[:60])}</td></tr>'
        )
    if not ar:
        ar = f'<tr><td colspan="6" style="text-align:center;color:{TD}">No auto-actions yet</td></tr>'

    # Prediction rows
    pr = ""
    for p in predictions:
        ts = str(p.get("timestamp", ""))[:16]
        pr += (
            f'<tr><td style="color:{TD};font-size:12px">{_e(ts)}</td>'
            f'<td style="font-family:monospace;color:{C}">{_e(p.get("ip",""))}</td>'
            f'<td>{_e(p.get("action_taken",""))}</td>'
            f'<td style="color:{TD};font-size:12px">{_e(str(p.get("problem",""))[:80])}</td></tr>'
        )
    if not pr:
        pr = f'<tr><td colspan="4" style="text-align:center;color:{TD}">Predictions paused — re-enabling at 7am</td></tr>'

    # Feature cards
    fc = ""
    for f in features:
        sc = G if f["status"] == "ACTIVE" else O
        fc += (
            f'<div style="background:{CB};border-radius:8px;padding:12px;border-left:3px solid {sc}">'
            f'<div style="display:flex;justify-content:space-between;align-items:center">'
            f'<div><span style="color:{T};font-weight:bold">{_e(f["name"])}</span>'
            f'<span style="background:{sc};color:white;padding:1px 6px;border-radius:3px;font-size:10px;margin-left:8px">{_e(f["status"])}</span></div>'
            f'<span style="color:{C};font-size:13px">{_e(f["metric"])}</span></div>'
            f'<div style="color:{TD};font-size:12px;margin-top:4px">{_e(f["desc"])}</div></div>'
        )

    # Cross-miner analysis — show ALL entries in scrollable container
    cm_html = ""
    cma = insights.get("cross_miner", [])
    if cma:
        entries_html = ""
        for i, entry in enumerate(cma):
            text = entry.get("analysis") or entry.get("summary") or ""
            if not text:
                continue
            ts = entry.get("timestamp") or entry.get("analyzed_at") or "unknown"
            source = entry.get("source", "legacy")
            # Format timestamp nicely
            if "T" in str(ts):
                ts_display = str(ts).replace("T", " ").split(".")[0]
            else:
                ts_display = str(ts)
            raw = _e(text)
            styled = re.sub(r'\*\*(.+?)\*\*', r'<strong style="color:#e2e8f0">\1</strong>', raw)
            # Each entry gets a card with header
            entries_html += f'<div style="background:{CB};border-radius:8px;padding:12px;margin-bottom:12px;border-left:3px solid {C}"><div style="display:flex;justify-content:space-between;margin-bottom:8px"><span style="color:{C};font-weight:600;font-size:12px">{ts_display}</span><span style="color:{TD};font-size:11px">{_e(source)}</span></div><div style="color:{TD};font-size:13px;line-height:1.6;white-space:pre-wrap">{styled}</div></div>'
        if entries_html:
            cm_html = f'<div style="max-height:400px;overflow-y:auto;padding-right:8px">{entries_html}</div>'

    # Patterns
    pt_html = ""
    for p in insights.get("patterns", []):
        pt_html += f'<div style="background:{CB};padding:8px 12px;border-radius:6px;margin-bottom:4px;color:{T};font-size:13px;border-left:3px solid {P}">🔍 {_e(str(p)[:150])}</div>'

    # Signal rows
    sr = ""
    for sig, src, freq in DATA_SIGNALS:
        sr += f'<tr><td style="color:{T}">{_e(sig)}</td><td style="color:{C};font-size:12px">{_e(src)}</td><td style="color:{TD};font-size:12px">{_e(freq)}</td></tr>'

    conn.close()

    # ── Assemble final HTML (no nested f-strings) ────────────
    css = f"""* {{margin:0;padding:0;box-sizing:border-box}}
body {{background:{BG};color:{T};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;padding:20px}}
.hero {{text-align:center;padding:30px 0}}
.hero-num {{font-size:72px;font-weight:900;background:linear-gradient(135deg,{C},{B},{P});-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.hero-lbl {{font-size:14px;color:{TD};letter-spacing:2px;text-transform:uppercase}}
.hero-sub {{font-size:18px;color:{TD};margin-top:8px}}
.g {{display:grid;gap:16px;margin:20px 0}}
.g5 {{grid-template-columns:repeat(5,1fr)}}
.g2 {{grid-template-columns:repeat(2,1fr)}}
.cd {{background:{CB};border-radius:12px;padding:16px}}
.ct {{color:{TD};font-size:11px;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px}}
.cv {{font-size:28px;font-weight:700}}
.cd2 {{font-size:12px;color:{TD};margin-top:4px}}
.st {{font-size:18px;font-weight:700;color:{T};margin:24px 0 12px;display:flex;align-items:center;gap:8px}}
table {{width:100%;border-collapse:collapse}}
th {{text-align:left;color:{TD};font-size:11px;text-transform:uppercase;letter-spacing:1px;padding:8px;border-bottom:1px solid #334155}}
td {{padding:8px;border-bottom:1px solid #1e293b;font-size:13px;color:{T}}}
tr:hover {{background:rgba(59,130,246,0.05)}}
.fg {{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}}
.stbl {{max-height:400px;overflow-y:auto}}
#dm {{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:1000;align-items:center;justify-content:center}}
#dm.active {{display:flex}}
.mc {{background:{CB};padding:24px;border-radius:12px;width:400px}}
.mi {{width:100%;padding:10px;border-radius:6px;border:1px solid #475569;background:#0f172a;color:{T};font-size:14px;margin:12px 0}}
.mb {{padding:8px 20px;border:none;border-radius:6px;cursor:pointer;font-size:14px;margin-right:8px}}"""

    js = """
let did=null;
function approveAction(id){fetch('""" + APPROVAL_API + """/approve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({approval_id:id})}).then(r=>r.json()).then(d=>{alert('Approved!');location.reload()}).catch(e=>alert('Error: '+e))}
function denyAction(id){did=id;document.getElementById('dm').classList.add('active');document.getElementById('dr').focus()}
function closeDM(){document.getElementById('dm').classList.remove('active');did=null}
function submitDeny(){let r=document.getElementById('dr').value;fetch('""" + APPROVAL_API + """/deny',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({approval_id:did,reason:r})}).then(r=>r.json()).then(d=>{closeDM();alert('Denied. Reason logged.');location.reload()}).catch(e=>alert('Error: '+e))}"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta http-equiv="refresh" content="30">
<style>{css}</style></head><body>

<div class="hero">
<div class="hero-lbl">Mining Guardian AI Intelligence Score</div>
<div class="hero-num">{fn(score['total_score'])}</div>
<div class="hero-sub">{fn(score['total_data_points'])} data points analyzed &bull; {comp['knowledge_depth']['detail']['llm_analyses']} AI analyses &bull; {comp['actions_taken']['detail']['tickets_created']} tickets auto-created</div>
</div>

<div class="g g5">
<div class="cd" style="border-top:3px solid {C}"><div class="ct">📊 Data Ingested</div><div class="cv" style="color:{C}">{fn(comp['data_ingested']['score'])}</div><div class="cd2">{fn(score['total_data_points'])} total readings</div></div>
<div class="cd" style="border-top:3px solid {P}"><div class="ct">🧠 Knowledge</div><div class="cv" style="color:{P}">{fn(comp['knowledge_depth']['score'])}</div><div class="cd2">{comp['knowledge_depth']['detail']['insights']} insights &bull; {comp['knowledge_depth']['detail']['patterns']} patterns</div></div>
<div class="cd" style="border-top:3px solid {B}"><div class="ct">🎯 Actions</div><div class="cv" style="color:{B}">{fn(comp['actions_taken']['score'])}</div><div class="cd2">{comp['actions_taken']['detail']['approved']} approved &bull; {comp['actions_taken']['detail']['auto_overnight']} autonomous</div></div>
<div class="cd" style="border-top:3px solid {G}"><div class="ct">✅ Outcomes</div><div class="cv" style="color:{G}">{fn(comp['outcomes_learned']['score'])}</div><div class="cd2">{comp['outcomes_learned']['detail']['success']} success &bull; {comp['outcomes_learned']['detail']['failure']} failure</div></div>
<div class="cd" style="border-top:3px solid {O}"><div class="ct">🤖 Autonomy</div><div class="cv" style="color:{O}">{fn(comp['autonomy_growth']['score'])}</div><div class="cd2">{comp['autonomy_growth']['detail']['auto_rate_pct']}% autonomous</div></div>
</div>

<div class="st">⚡ Live Action Queue</div>
<div class="cd"><table><thead><tr><th>Miner IP</th><th>Model</th><th>Issue</th><th>Action</th><th>HR</th><th>Temp</th><th>Decision</th></tr></thead><tbody>{qr}</tbody></table></div>

<div class="g g2">
<div><div class="st">🤖 Recent Autonomous Actions</div>
<div class="cd" style="max-height:350px;overflow-y:auto"><table><thead><tr><th>Time</th><th>Miner</th><th>Model</th><th>Action</th><th>Outcome</th><th>Issue</th></tr></thead><tbody>{ar}</tbody></table></div></div>
<div><div class="st">🔮 Pre-Failure Predictions</div>
<div class="cd" style="max-height:350px;overflow-y:auto"><table><thead><tr><th>Time</th><th>Miner</th><th>Action</th><th>Detail</th></tr></thead><tbody>{pr}</tbody></table></div></div>
</div>

<div class="st">🎓 AI Training Insights</div>
<div class="g g2">
<div class="cd"><div class="ct">Cross-Miner Correlation Analysis</div>{cm_html if cm_html else f'<div style="color:{TD}">Awaiting first training run</div>'}</div>
<div class="cd"><div class="ct">Discovered Patterns ({len(insights.get("patterns",[]))})</div>{pt_html if pt_html else f'<div style="color:{TD}">No patterns yet</div>'}</div>
</div>

<div class="st">⚙️ AI Features — 8 Active Learning Modules</div>
<div class="fg">{fc}</div>

<div class="st">📡 Data Signals — {len(DATA_SIGNALS)} per miner × 58 miners</div>
<div class="cd stbl"><table><thead><tr><th>Signal</th><th>Source</th><th>Frequency</th></tr></thead><tbody>{sr}</tbody></table></div>

<div id="dm"><div class="mc">
<div style="font-size:16px;font-weight:bold;color:{T}">Why are you denying this action?</div>
<div style="color:{TD};font-size:13px;margin-top:4px">Your reason helps the AI learn what NOT to do.</div>
<textarea id="dr" class="mi" rows="3" placeholder="e.g., Miner just restarted 10 min ago..."></textarea>
<div><button onclick="submitDeny()" class="mb" style="background:{R};color:white">Submit Denial</button>
<button onclick="closeDM()" class="mb" style="background:#475569;color:white">Cancel</button></div>
</div></div>

<script>{js}</script>

<div style="text-align:center;color:{TD};font-size:11px;margin-top:24px;padding:12px">
Mining Guardian v2.0 — BiXBiT USA &bull; {datetime.now().strftime('%Y-%m-%d %H:%M')} &bull; Auto-refreshes every 30s
</div>
</body></html>"""

    return html
