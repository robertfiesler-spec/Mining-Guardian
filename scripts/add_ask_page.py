#!/usr/bin/env python3
"""
Adds an /ask page and /ask/query handler to dashboard_api.py.
Idempotent via the ASK_MARKER check.
Inserts immediately before `if __name__ == "__main__":`.
"""
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "api" / "dashboard_api.py"
ASK_MARKER = "# ── ASK PAGE (operator natural-language query interface) ──"
INSERT_BEFORE = 'if __name__ == "__main__":'

NEW_BLOCK = '''
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
                "SELECT scanned_at, status, hashrate, hashrate_pct, temp_chip, issue, action "
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
                f"<tr><td>{r['ip']}</td>"
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
                f"<tr><td>{r['ip']}</td>"
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
                f"<tr><td>{r['ip']}</td>"
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
                f"<td>{r['ip']}</td>"
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
                f"<tr><td>{r['ip']}</td>"
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


'''


def main():
    text = TARGET.read_text()
    if ASK_MARKER in text:
        print(f"Marker already present in {TARGET}; nothing to do.")
        return 0
    if INSERT_BEFORE not in text:
        print(f"ERROR: insertion anchor not found in {TARGET}")
        return 1
    new_text = text.replace(INSERT_BEFORE, NEW_BLOCK.lstrip("\n") + "\n\n" + INSERT_BEFORE, 1)
    tmp = TARGET.with_suffix(TARGET.suffix + ".tmp")
    tmp.write_text(new_text)
    tmp.replace(TARGET)
    print(f"Inserted {new_text.count(chr(10)) - text.count(chr(10))} lines into {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
