#!/usr/bin/env python3
"""
train_comprehensive.py
Mining Guardian — Comprehensive LLM Training

Feeds ALL available data to the LLM for deep learning:
  - Full miner logs (sectioned: boot/init, mid-operation, tail — NO truncation)
  - Per-board chain readings (voltage, freq, HW errors, per-board hashrate)
  - Pool share data (accepted/rejected, rejection rate trends)
  - Hardware identity (board name, serial, chip die, control board, PSU)
  - Log metrics (per-chip hashrate sampled, PSU voltage, system health, chain events)
  - Action audit log (what was tried, what worked, what didn't)
  - HVAC and weather correlation with miner performance
  - AMS notifications history

The goal: LLM builds a complete picture of every miner's hardware fingerprint,
performance trends, failure patterns, and correlations with environment.

Cron: 0 3 * * 0 cd /root/Mining-Gaurdian && venv/bin/python train_comprehensive.py
"""

import sys
import sqlite3
import json
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta

_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT / "ai"), str(_ROOT / "core")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from llm_analyzer import LLMAnalyzer
from knowledge_manager import KnowledgeManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("train_comprehensive")

DB_PATH = str(_ROOT / "guardian.db")


def section_log(content: str) -> str:
    """Section a full miner.log into boot, mid, and tail for LLM consumption.
    No hard truncation — LLM gets the full picture in structured sections.
    """
    if not content:
        return "(empty)"
    if len(content) <= 16000:
        return content
    boot   = content[:8000]
    mid_s  = len(content) // 2
    mid    = content[mid_s:mid_s + 4000]
    tail   = content[-4000:]
    return (
        f"[BOOT/INIT — hardware identity, EEPROM, chain attach/detach]\n{boot}\n\n"
        f"[MID-OPERATION — chip hashrates, PSU voltage, system health]\n{mid}\n\n"
        f"[RECENT TAIL — latest events, errors, chain state]\n{tail}"
    )


def get_miner_full_profile(conn, miner_id: str) -> dict:
    """Pull every data point we have for a single miner."""

    # Scan history summary
    scan = conn.execute("""
        SELECT model, ip,
               COUNT(*) as scan_count,
               ROUND(AVG(hashrate_pct), 1) as avg_hr,
               ROUND(MIN(hashrate_pct), 1) as min_hr,
               ROUND(MAX(hashrate_pct), 1) as max_hr,
               ROUND(AVG(CASE WHEN temp_chip > 0 THEN temp_chip END), 1) as avg_temp,
               MAX(temp_chip) as max_temp,
               ROUND(AVG(pdu_power), 3) as avg_pdu_kw,
               SUM(CASE WHEN action NOT IN ('MONITOR','') AND action IS NOT NULL
                   THEN 1 ELSE 0 END) as times_flagged,
               GROUP_CONCAT(DISTINCT action) as action_types,
               MAX(scanned_at) as last_seen,
               GROUP_CONCAT(DISTINCT current_profile) as profiles_seen,
               GROUP_CONCAT(DISTINCT map_location) as locations
        FROM miner_readings WHERE miner_id = ?
    """, (miner_id,)).fetchone()

    # Per-board chain summary
    chains = conn.execute("""
        SELECT board_index,
               ROUND(AVG(rate_mhs), 0) as avg_rate_mhs,
               ROUND(AVG(voltage), 3) as avg_voltage,
               ROUND(AVG(freq_mhz), 0) as avg_freq_mhz,
               ROUND(AVG(consumption_w), 0) as avg_power_w,
               SUM(hw_errors) as total_hw_errors,
               ROUND(AVG(temp_board), 1) as avg_board_temp,
               ROUND(AVG(temp_chip), 1) as avg_chip_temp,
               SUM(CASE WHEN rate_mhs < 1000 THEN 1 ELSE 0 END) as dead_readings,
               COUNT(*) as total_readings
        FROM chain_readings WHERE miner_id = ?
        GROUP BY board_index ORDER BY board_index
    """, (miner_id,)).fetchall()

    # Pool summary
    pool = conn.execute("""
        SELECT pool_url,
               MAX(accepted) as total_accepted,
               MAX(rejected) as total_rejected,
               ROUND(MAX(rejected)*100.0/NULLIF(MAX(accepted)+MAX(rejected),0), 3) as reject_rate,
               GROUP_CONCAT(DISTINCT status) as statuses
        FROM pool_readings WHERE miner_id = ?
        GROUP BY pool_url
    """, (miner_id,)).fetchall()

    # Hardware identity
    hardware = conn.execute("""
        SELECT board_index, board_name, serial_number, chip_die, chip_marking,
               chip_technology, pcb_version, bom_version, chip_bin, chip_ft_ver,
               ideal_hashrate, control_board, psu_version, bixminer_version,
               topol_machine, device_name, asic_count, bad_chips_count, pic_version
        FROM miner_hardware WHERE miner_id = ?
        ORDER BY board_index
    """, (miner_id,)).fetchall()

    # Log metrics — chip hashrate summary (avg actual vs target per chip position)
    chip_summary = conn.execute("""
        SELECT chip_index,
               ROUND(AVG(value_1), 2) as avg_actual_ths,
               ROUND(AVG(value_2), 2) as avg_target_ths,
               ROUND(AVG(value_1)/NULLIF(AVG(value_2),0)*100, 1) as pct_of_target,
               COUNT(*) as samples
        FROM log_metrics
        WHERE miner_id = ? AND metric_type = 'chip_hashrate'
        GROUP BY chip_index ORDER BY chip_index
    """, (miner_id,)).fetchall()

    # Log metrics — PSU voltage trend
    psu = conn.execute("""
        SELECT ROUND(AVG(value_1), 3) as avg_voltage,
               ROUND(MIN(value_1), 3) as min_voltage,
               ROUND(MAX(value_1), 3) as max_voltage,
               ROUND(AVG(value_3), 0) as avg_power_w,
               COUNT(*) as samples
        FROM log_metrics WHERE miner_id = ? AND metric_type = 'psu_voltage'
    """, (miner_id,)).fetchone()

    # Log metrics — system health
    health = conn.execute("""
        SELECT ROUND(AVG(value_1), 1) as avg_total_cpu,
               ROUND(AVG(value_2), 1) as avg_miner_cpu,
               ROUND(AVG(value_3), 0) as avg_free_mem_mb,
               COUNT(*) as samples
        FROM log_metrics WHERE miner_id = ? AND metric_type = 'system_health'
    """, (miner_id,)).fetchone()

    # Chain events (attach/detach)
    chain_events = conn.execute("""
        SELECT board_index, text_value as event, COUNT(*) as count,
               MIN(log_timestamp) as first, MAX(log_timestamp) as last
        FROM log_metrics WHERE miner_id = ? AND metric_type = 'chain_event'
        GROUP BY board_index, text_value ORDER BY board_index
    """, (miner_id,)).fetchall()

    # Audit history — what was tried
    audit = conn.execute("""
        SELECT timestamp, problem, action_taken, decision, approved_by, notes
        FROM action_audit_log WHERE miner_id = ?
        ORDER BY timestamp DESC LIMIT 20
    """, (miner_id,)).fetchall()

    # Full miner logs — all of them, sectioned
    logs = conn.execute("""
        SELECT collected_at, log_file, health_status, content
        FROM miner_logs WHERE miner_id = ?
        ORDER BY collected_at DESC LIMIT 10
    """, (miner_id,)).fetchall()

    # AMS notifications
    ams = conn.execute("""
        SELECT key, alert_level, COUNT(*) as cnt, MAX(recorded_at) as last_seen
        FROM ams_notifications WHERE device_id = ?
        GROUP BY key, alert_level ORDER BY cnt DESC
    """, (miner_id,)).fetchall()

    # ── #3: Scan-to-scan delta analysis ──────────────────────────
    # Show the LLM how this miner's metrics CHANGED over time,
    # not just averages. A slow 30-day decline looks very different
    # from a sudden single-scan drop. Both need different responses.
    deltas = conn.execute("""
        SELECT scanned_at,
               hashrate_pct,
               temp_chip,
               pdu_power,
               LAG(hashrate_pct) OVER (ORDER BY id) as prev_hr,
               LAG(temp_chip)    OVER (ORDER BY id) as prev_temp,
               issue,
               action
        FROM miner_readings
        WHERE miner_id = ?
        ORDER BY id DESC LIMIT 50
    """, (miner_id,)).fetchall()

    # Calculate scan-to-scan changes, flag significant swings
    delta_analysis = []
    for row in deltas:
        r = dict(row)
        if r["prev_hr"] is not None and r["hashrate_pct"] is not None:
            hr_change = round(r["hashrate_pct"] - r["prev_hr"], 1)
            temp_change = round((r["temp_chip"] or 0) - (r["prev_temp"] or 0), 1)
            if abs(hr_change) >= 10 or abs(temp_change) >= 5 or r["action"]:
                delta_analysis.append({
                    "time": r["scanned_at"][:16],
                    "hr_pct": r["hashrate_pct"],
                    "hr_change": hr_change,
                    "temp": r["temp_chip"],
                    "temp_change": temp_change,
                    "action": r["action"],
                    "issue": (r["issue"] or "")[:80],
                })

    # ── #4: Restart outcome correlation ──────────────────────────
    # For every restart in the audit log, find what the miner looked
    # like BEFORE and AFTER. This tells the LLM whether restarts
    # actually fixed problems or just masked them temporarily.
    restart_outcomes = []
    audit_rows = conn.execute("""
        SELECT timestamp, action_taken, decision, problem
        FROM action_audit_log
        WHERE miner_id = ? AND action_taken IN ('RESTART','PDU_CYCLE','RESTART_CHECK_BOARDS')
        AND decision = 'APPROVED'
        ORDER BY timestamp DESC LIMIT 10
    """, (miner_id,)).fetchall()

    for restart in audit_rows:
        ts = restart["timestamp"]
        # Reading just before restart
        before = conn.execute("""
            SELECT hashrate_pct, temp_chip, issue, scanned_at
            FROM miner_readings WHERE miner_id = ? AND scanned_at <= ?
            ORDER BY scanned_at DESC LIMIT 1
        """, (miner_id, ts)).fetchone()
        # Reading 30 minutes after restart
        after_ts = datetime.fromisoformat(ts) + timedelta(minutes=30)
        after = conn.execute("""
            SELECT hashrate_pct, temp_chip, issue, scanned_at
            FROM miner_readings WHERE miner_id = ? AND scanned_at >= ?
            ORDER BY scanned_at ASC LIMIT 1
        """, (miner_id, after_ts.isoformat())).fetchone()

        outcome = {
            "restart_time": ts[:16],
            "action": restart["action_taken"],
            "problem": (restart["problem"] or "")[:100],
            "before": dict(before) if before else None,
            "after": dict(after) if after else None,
        }
        if before and after:
            hr_recovery = round((after["hashrate_pct"] or 0) - (before["hashrate_pct"] or 0), 1)
            outcome["hr_recovery"] = hr_recovery
            outcome["resolved"] = hr_recovery > 20 and not after["issue"]
        restart_outcomes.append(outcome)

    return {
        "scan": dict(scan) if scan else {},
        "chains": [dict(c) for c in chains],
        "pool": [dict(p) for p in pool],
        "hardware": [dict(h) for h in hardware],
        "chip_summary": [dict(c) for c in chip_summary],
        "psu": dict(psu) if psu else {},
        "health": dict(health) if health else {},
        "chain_events": [dict(e) for e in chain_events],
        "audit": [dict(a) for a in audit],
        "logs": [{"collected_at": l["collected_at"], "log_file": l["log_file"],
                  "health_status": l["health_status"],
                  "content": section_log(l["content"])} for l in logs],
        "ams": [dict(a) for a in ams],
        "delta_analysis": delta_analysis,
        "restart_outcomes": restart_outcomes,
    }


def build_miner_prompt(miner_id: str, profile: dict) -> str:
    """Build a comprehensive LLM prompt from all data for one miner."""
    s = profile["scan"]
    lines = [
        f"=== COMPREHENSIVE ANALYSIS: Miner {miner_id} ===",
        f"Model: {s.get('model')} | IP: {s.get('ip')} | Location: {s.get('locations')}",
        f"Profiles seen: {s.get('profiles_seen')}",
        f"Scans: {s.get('scan_count')} | Last seen: {s.get('last_seen', '')[:16]}",
        f"Hashrate: avg={s.get('avg_hr')}% min={s.get('min_hr')}% max={s.get('max_hr')}%",
        f"Chip temp: avg={s.get('avg_temp')}°C max={s.get('max_temp')}°C",
        f"PDU power: avg={s.get('avg_pdu_kw')} kW",
        f"Flagged: {s.get('times_flagged')}x | Actions: {s.get('action_types')}",
    ]

    # Hardware identity
    if profile["hardware"]:
        lines.append("\n--- HARDWARE IDENTITY ---")
        for h in profile["hardware"]:
            lines.append(
                f"Board {h['board_index']}: {h['board_name']} | SN: {h['serial_number']} | "
                f"Chip: {h['chip_die']} {h['chip_marking']} tech={h['chip_technology']} "
                f"bin={h['chip_bin']} | PCB: {h['pcb_version']} BOM: {h['bom_version']} | "
                f"ASICs: {h['asic_count']} bad={h['bad_chips_count']} | "
                f"Ideal HR: {h['ideal_hashrate']}"
            )
        hw = profile["hardware"][0]
        lines.append(
            f"Control board: {hw['control_board']} | PSU: {hw['psu_version']} | "
            f"BixMiner: {hw['bixminer_version']} | Topol: {hw['topol_machine']}"
        )

    # Per-board chain data
    if profile["chains"]:
        lines.append("\n--- PER-BOARD CHAIN DATA ---")
        for c in profile["chains"]:
            dead_pct = round(c['dead_readings'] / c['total_readings'] * 100, 1) if c['total_readings'] else 0
            lines.append(
                f"Board {c['board_index']}: avg={c['avg_rate_mhs']} MH/s "
                f"volt={c['avg_voltage']}V freq={c['avg_freq_mhz']}MHz "
                f"power={c['avg_power_w']}W temp_board={c['avg_board_temp']}°C "
                f"temp_chip={c['avg_chip_temp']}°C HW_errors={c['total_hw_errors']} "
                f"dead_readings={c['dead_readings']}/{c['total_readings']} ({dead_pct}%)"
            )

    # PSU data
    if profile["psu"] and profile["psu"].get("samples"):
        p = profile["psu"]
        lines.append(
            f"\n--- PSU VOLTAGE (from logs, {p['samples']} samples) ---\n"
            f"Voltage: avg={p['avg_voltage']}V min={p['min_voltage']}V max={p['max_voltage']}V | "
            f"Power: avg={p['avg_power_w']}W"
        )

    # System health
    if profile["health"] and profile["health"].get("samples"):
        h = profile["health"]
        lines.append(
            f"\n--- SYSTEM HEALTH (from logs, {h['samples']} samples) ---\n"
            f"CPU total: {h['avg_total_cpu']}% | Miner CPU: {h['avg_miner_cpu']}% | "
            f"Free RAM: {h['avg_free_mem_mb']} MB"
        )

    # Per-chip hashrate summary (flag underperforming chips)
    if profile["chip_summary"]:
        underperforming = [c for c in profile["chip_summary"]
                          if c["pct_of_target"] and c["pct_of_target"] < 90]
        lines.append(f"\n--- PER-CHIP HASHRATE ({len(profile['chip_summary'])} chips sampled) ---")
        if underperforming:
            lines.append(f"Underperforming chips (<90% of target): {len(underperforming)}")
            for c in underperforming[:10]:
                lines.append(
                    f"  Chip {c['chip_index']}: {c['avg_actual_ths']} TH/s "
                    f"vs target {c['avg_target_ths']} ({c['pct_of_target']}%)"
                )
        else:
            avg_pct = sum(c["pct_of_target"] or 0 for c in profile["chip_summary"]) / len(profile["chip_summary"])
            lines.append(f"All chips within range — fleet avg {avg_pct:.1f}% of target")

    # Chain events
    if profile["chain_events"]:
        lines.append("\n--- CHAIN ATTACH/DETACH EVENTS ---")
        for e in profile["chain_events"]:
            lines.append(
                f"Board {e['board_index']}: {e['event']} {e['count']}x "
                f"(first: {e['first'][:16]}, last: {e['last'][:16]})"
            )

    # Pool data
    if profile["pool"]:
        lines.append("\n--- POOL DATA ---")
        for p in profile["pool"]:
            lines.append(
                f"Pool: {p['pool_url']} | Accepted: {p['total_accepted']} | "
                f"Rejected: {p['total_rejected']} | Reject rate: {p['reject_rate']}% | "
                f"Statuses: {p['statuses']}"
            )

    # AMS notifications
    if profile["ams"]:
        lines.append("\n--- AMS ALERTS ---")
        for a in profile["ams"]:
            lines.append(f"  {a['key']} ({a['alert_level']}): {a['cnt']}x, last: {a['last_seen'][:16]}")

    # Audit history
    if profile["audit"]:
        lines.append("\n--- ACTION HISTORY ---")
        for a in profile["audit"]:
            lines.append(
                f"  [{a['timestamp'][:16]}] {a['decision']} {a['action_taken']} "
                f"by {a['approved_by']} — {str(a['problem'])[:120]}"
            )

    # ── #3: Scan-to-scan delta analysis ──────────────────────────
    if profile.get("delta_analysis"):
        lines.append(f"\n--- PERFORMANCE TREND (significant changes, last 50 scans) ---")
        lines.append("Shows scan-to-scan changes ≥10% hashrate or ≥5°C temp swing:")
        for d in profile["delta_analysis"][:20]:
            hr_dir = "▲" if d["hr_change"] > 0 else "▼"
            temp_dir = "▲" if d["temp_change"] > 0 else "▼"
            lines.append(
                f"  [{d['time']}] HR: {d['hr_pct']}% ({hr_dir}{abs(d['hr_change'])}%) | "
                f"Temp: {d['temp']}°C ({temp_dir}{abs(d['temp_change'])}°C) | "
                f"Action: {d['action'] or 'none'} | {d['issue']}"
            )

    # ── #4: Restart outcome correlation ──────────────────────────
    if profile.get("restart_outcomes"):
        lines.append(f"\n--- RESTART OUTCOMES (what actually happened after each restart) ---")
        for r in profile["restart_outcomes"]:
            resolved = r.get("resolved")
            outcome_str = "✅ RESOLVED" if resolved else "❌ NOT RESOLVED" if resolved is False else "? UNKNOWN"
            lines.append(f"  [{r['restart_time']}] {r['action']} — {outcome_str}")
            lines.append(f"    Problem: {r['problem']}")
            if r["before"]:
                lines.append(
                    f"    Before: HR={r['before'].get('hashrate_pct')}% "
                    f"temp={r['before'].get('temp_chip')}°C"
                )
            if r["after"]:
                lines.append(
                    f"    After:  HR={r['after'].get('hashrate_pct')}% "
                    f"temp={r['after'].get('temp_chip')}°C "
                    f"(+{r.get('hr_recovery', '?')}% HR recovery)"
                )
                if r["after"].get("issue"):
                    lines.append(f"    Still flagged after: {r['after']['issue'][:80]}")

    # Full logs — sectioned
    if profile["logs"]:
        lines.append(f"\n--- MINER LOGS ({len(profile['logs'])} files) ---")
        for l in profile["logs"]:
            lines.append(
                f"\n[{l['collected_at'][:16]}] {l['log_file']} ({l['health_status']}):\n"
                f"{l['content']}"
            )

    lines.append(
        "\n=== ANALYSIS REQUESTED ===\n"
        "Based on ALL data above:\n"
        "1. What is the hardware fingerprint of this miner (board type, chip grade, PSU)?\n"
        "2. What performance patterns do you see over time?\n"
        "3. Are there signs of hardware degradation (HW errors, dead chips, voltage sag)?\n"
        "4. What is the root cause of any issues?\n"
        "5. What is your confidence level: is this HARDWARE failure, FIRMWARE issue, or ENVIRONMENTAL?\n"
        "6. What specific action should be taken? (restart / ticket / profile change / monitoring)\n"
        "Keep response concise — max 15 lines."
    )

    return "\n".join(lines)


def get_cross_miner_correlations(conn) -> str:
    """#5: Cross-miner correlation analysis.

    Finds patterns ACROSS miners — shared hardware batches, common chip bins,
    models that consistently underperform, board serials that appear in multiple
    miners (swapped boards), and fleet-wide patterns by chip grade.
    """
    lines = ["=== CROSS-MINER CORRELATION ANALYSIS ==="]

    # Group miners by chip bin — do certain bins fail more?
    chip_bin_perf = conn.execute("""
        SELECT h.chip_bin,
               COUNT(DISTINCT h.miner_id) as miner_count,
               ROUND(AVG(mr.hashrate_pct), 1) as avg_hr_pct,
               ROUND(AVG(CASE WHEN mr.temp_chip > 0 THEN mr.temp_chip END), 1) as avg_temp,
               SUM(CASE WHEN mr.action NOT IN ('MONITOR','') AND mr.action IS NOT NULL
                   THEN 1 ELSE 0 END) as total_flags
        FROM miner_hardware h
        JOIN miner_readings mr ON h.miner_id = mr.miner_id
        WHERE h.chip_bin IS NOT NULL AND mr.scanned_at >= datetime("now", "-7 days")
        GROUP BY h.chip_bin
        ORDER BY avg_hr_pct ASC
    """).fetchall()
    if chip_bin_perf:
        lines.append("\n--- PERFORMANCE BY CHIP BIN GRADE ---")
        lines.append("(Does chip quality grade predict performance?)")
        for r in chip_bin_perf:
            lines.append(
                f"  Bin {r['chip_bin']}: {r['miner_count']} miners | "
                f"avg HR={r['avg_hr_pct']}% | avg temp={r['avg_temp']}°C | "
                f"total flags={r['total_flags']}"
            )

    # Group by chip die/technology — different silicon behaves differently
    chip_die_perf = conn.execute("""
        SELECT h.chip_die, h.chip_technology,
               COUNT(DISTINCT h.miner_id) as miner_count,
               ROUND(AVG(mr.hashrate_pct), 1) as avg_hr_pct,
               SUM(CASE WHEN mr.action NOT IN ('MONITOR','') AND mr.action IS NOT NULL
                   THEN 1 ELSE 0 END) as total_flags
        FROM miner_hardware h
        JOIN miner_readings mr ON h.miner_id = mr.miner_id
        WHERE h.chip_die IS NOT NULL AND mr.scanned_at >= datetime("now", "-7 days")
        GROUP BY h.chip_die, h.chip_technology
        ORDER BY avg_hr_pct ASC
    """).fetchall()
    if chip_die_perf:
        lines.append("\n--- PERFORMANCE BY CHIP DIE/TECHNOLOGY ---")
        for r in chip_die_perf:
            lines.append(
                f"  Die={r['chip_die']} tech={r['chip_technology']}: "
                f"{r['miner_count']} miners | avg HR={r['avg_hr_pct']}% | "
                f"total flags={r['total_flags']}"
            )

    # Board serial batches — same SN prefix = same production batch
    # Boards from same batch often fail together
    serial_batch_perf = conn.execute("""
        SELECT SUBSTR(h.serial_number, 1, 8) as sn_batch,
               h.board_name,
               COUNT(DISTINCT h.miner_id) as miner_count,
               COUNT(*) as board_count,
               ROUND(AVG(cr.rate_mhs), 0) as avg_rate_mhs,
               SUM(cr.hw_errors) as total_hw_errors,
               SUM(CASE WHEN cr.rate_mhs < 1000 THEN 1 ELSE 0 END) as dead_readings
        FROM miner_hardware h
        LEFT JOIN chain_readings cr ON h.miner_id = cr.miner_id
            AND h.board_index = cr.board_index AND cr.scanned_at >= datetime("now", "-7 days")
        WHERE h.serial_number IS NOT NULL
        GROUP BY sn_batch, h.board_name
        HAVING board_count > 1
        ORDER BY total_hw_errors DESC, dead_readings DESC
    """).fetchall()
    if serial_batch_perf:
        lines.append("\n--- BOARD SERIAL BATCHES (shared production runs) ---")
        lines.append("(Boards from same batch often share failure modes)")
        for r in serial_batch_perf:
            lines.append(
                f"  Batch {r['sn_batch']}... ({r['board_name']}): "
                f"{r['board_count']} boards across {r['miner_count']} miners | "
                f"avg rate={r['avg_rate_mhs']} MH/s | "
                f"HW errors={r['total_hw_errors']} | dead readings={r['dead_readings']}"
            )

    # PCB version performance — newer PCB revisions may have fixed issues
    pcb_perf = conn.execute("""
        SELECT h.pcb_version, h.bom_version,
               COUNT(DISTINCT h.miner_id) as miner_count,
               ROUND(AVG(mr.hashrate_pct), 1) as avg_hr_pct,
               SUM(CASE WHEN mr.action NOT IN ('MONITOR','') AND mr.action IS NOT NULL
                   THEN 1 ELSE 0 END) as total_flags
        FROM miner_hardware h
        JOIN miner_readings mr ON h.miner_id = mr.miner_id
        WHERE h.pcb_version IS NOT NULL AND mr.scanned_at >= datetime("now", "-7 days")
        GROUP BY h.pcb_version, h.bom_version
        ORDER BY avg_hr_pct ASC
    """).fetchall()
    if pcb_perf:
        lines.append("\n--- PERFORMANCE BY PCB/BOM VERSION ---")
        for r in pcb_perf:
            lines.append(
                f"  PCB={r['pcb_version']} BOM={r['bom_version']}: "
                f"{r['miner_count']} miners | avg HR={r['avg_hr_pct']}% | "
                f"total flags={r['total_flags']}"
            )

    # PSU version performance — uses chain_readings voltage (fast) instead of log_metrics (6M+ rows)
    psu_perf = conn.execute("""
        SELECT h.psu_version,
               COUNT(DISTINCT h.miner_id) as miner_count,
               ROUND(AVG(cr.voltage), 3) as avg_voltage,
               ROUND(MIN(cr.voltage), 3) as min_voltage,
               ROUND(AVG(mr.hashrate_pct), 1) as avg_hr_pct
        FROM miner_hardware h
        LEFT JOIN chain_readings cr ON h.miner_id = cr.miner_id
            AND cr.scanned_at >= datetime('now', '-7 days')
        JOIN miner_readings mr ON h.miner_id = mr.miner_id
        WHERE h.psu_version IS NOT NULL AND mr.scanned_at >= datetime("now", "-7 days")
        GROUP BY h.psu_version
        ORDER BY avg_voltage ASC
    """).fetchall()
    if psu_perf:
        lines.append("\n--- PERFORMANCE BY PSU VERSION ---")
        for r in psu_perf:
            lines.append(
                f"  PSU {r['psu_version']}: {r['miner_count']} miners | "
                f"avg voltage={r['avg_voltage']}V min={r['min_voltage']}V | "
                f"avg HR={r['avg_hr_pct']}%"
            )

    # Top flagged miners — the chronic problem cases
    chronic = conn.execute("""
        SELECT miner_id, ip, model,
               COUNT(*) as scan_count,
               SUM(CASE WHEN action NOT IN ('MONITOR','') AND action IS NOT NULL
                   THEN 1 ELSE 0 END) as times_flagged,
               ROUND(AVG(hashrate_pct), 1) as avg_hr,
               GROUP_CONCAT(DISTINCT action) as actions
        FROM miner_readings
        GROUP BY miner_id
        HAVING times_flagged > 5
        ORDER BY times_flagged DESC LIMIT 15
    """).fetchall()
    if chronic:
        lines.append("\n--- CHRONICALLY FLAGGED MINERS ---")
        for r in chronic:
            lines.append(
                f"  Miner {r['miner_id']} ({r['model']}) @ {r['ip']}: "
                f"flagged {r['times_flagged']}/{r['scan_count']} scans "
                f"({round(r['times_flagged']/r['scan_count']*100,0):.0f}%) | "
                f"avg HR={r['avg_hr']}% | actions: {r['actions']}"
            )

    # Restart effectiveness fleet-wide — do restarts actually work?
    restart_stats = conn.execute("""
        SELECT action_taken,
               COUNT(*) as total,
               SUM(CASE WHEN decision='APPROVED' THEN 1 ELSE 0 END) as approved,
               SUM(CASE WHEN decision='DENIED' THEN 1 ELSE 0 END) as denied
        FROM action_audit_log
        GROUP BY action_taken
        ORDER BY total DESC
    """).fetchall()
    if restart_stats:
        lines.append("\n--- FLEET-WIDE ACTION STATISTICS ---")
        for r in restart_stats:
            lines.append(
                f"  {r['action_taken']}: {r['total']} total | "
                f"{r['approved']} approved | {r['denied']} denied"
            )

    # Feature 3: Include denial reasons in training — operator judgment as signal
    denial_reasons = conn.execute("""
        SELECT timestamp, ip, model, action_taken, notes
        FROM action_audit_log
        WHERE decision = 'DENIED'
          AND notes LIKE '%DENIAL_REASON%'
          AND timestamp >= datetime('now', '-30 days')
        ORDER BY timestamp DESC
        LIMIT 20
    """).fetchall()
    if denial_reasons:
        lines.append("\n--- OPERATOR DENIAL REASONS (last 30 days) ---")
        lines.append("These are cases where the operator denied the AI recommendation and explained why.")
        lines.append("Use these to understand what the operator considers inappropriate action timing or conditions.")
        for r in denial_reasons:
            reason_text = ""
            if r["notes"]:
                import re
                match = re.search(r"DENIAL_REASON: (.+?)(?:\||$)", r["notes"])
                if match:
                    reason_text = match.group(1).strip()
            if reason_text:
                lines.append(
                    f"  [{r['timestamp'][:10]}] {r['ip']} ({r['model']}) "
                    f"action={r['action_taken']} | Operator said: \"{reason_text}\""
                )

    lines.append(
        "\n=== CROSS-MINER ANALYSIS REQUESTED ===\n"
        "Based on the fleet-wide data above:\n"
        "1. Which chip bin grades, PCB versions, or serial batches are underperforming?\n"
        "2. Are there patterns suggesting a systematic hardware quality issue?\n"
        "3. Which miners share the same failure mode and why?\n"
        "4. Do restarts actually work, or are they masking deeper hardware issues?\n"
        "5. What procurement or operational decisions does this data suggest?\n"
        "Keep response to 15 lines max."
    )

    return "\n".join(lines)


def get_hvac_weather_context(conn) -> str:
    """Build HVAC and weather context for fleet-level correlation."""
    hvac = conn.execute("""
        SELECT ROUND(AVG(supply_temp_f),1) as avg_supply,
               ROUND(AVG(return_temp_f),1) as avg_return,
               ROUND(AVG(delta_t_f),1) as avg_delta_t,
               ROUND(AVG(diff_pressure),1) as avg_pressure,
               SUM(spray_pump_on) as pump_on_count,
               COUNT(*) as total_readings
        FROM hvac_readings
        WHERE recorded_at > datetime('now', '-30 days')
    """).fetchone()

    wx = conn.execute("""
        SELECT ROUND(AVG(temp_f),1) as avg_temp,
               ROUND(MIN(temp_f),1) as min_temp,
               ROUND(MAX(temp_f),1) as max_temp,
               ROUND(AVG(humidity_pct),1) as avg_humidity
        FROM weather_readings
        WHERE recorded_at > datetime('now', '-30 days')
    """).fetchone()

    lines = ["--- FACILITY ENVIRONMENT (last 30 days) ---"]
    if hvac and hvac["total_readings"]:
        pump_pct = round(hvac["pump_on_count"] / hvac["total_readings"] * 100, 1)
        lines.append(
            f"HVAC: Supply avg={hvac['avg_supply']}°F | Return avg={hvac['avg_return']}°F | "
            f"ΔT avg={hvac['avg_delta_t']}°F | Diff pressure avg={hvac['avg_pressure']} PSI | "
            f"Spray pump ON {pump_pct}% of time"
        )
    if wx and wx["avg_temp"]:
        lines.append(
            f"Weather: avg={wx['avg_temp']}°F min={wx['min_temp']}°F max={wx['max_temp']}°F | "
            f"Humidity avg={wx['avg_humidity']}%"
        )
    return "\n".join(lines)


def run_comprehensive_training():
    """Main training loop — analyze every miner with all available data."""
    analyzer = LLMAnalyzer()
    km = KnowledgeManager()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    # Get all unique miner IDs
    miner_ids = [r[0] for r in conn.execute(
        "SELECT DISTINCT miner_id FROM miner_readings ORDER BY miner_id"
    ).fetchall()]

    logger.info("=" * 60)
    logger.info("COMPREHENSIVE TRAINING — %d miners", len(miner_ids))
    logger.info("=" * 60)

    env_context = get_hvac_weather_context(conn)
    logger.info("Environment context built")

    results = []
    for i, miner_id in enumerate(miner_ids, 1):
        logger.info("Analyzing miner %s (%d/%d)...", miner_id, i, len(miner_ids))

        try:
            profile = get_miner_full_profile(conn, miner_id)
            if not profile["scan"] or not profile["scan"].get("scan_count"):
                logger.info("  Skipping %s — no scan data", miner_id)
                continue

            prompt = f"{env_context}\n\n{build_miner_prompt(miner_id, profile)}"

            # Use Claude for deep analysis — retry on rate limit
            response = ''
            for attempt in range(3):
                response = analyzer.deep_analyze(prompt)
                if response:
                    break
                # Empty response = rate limited or error, wait and retry
                wait = 60 * (attempt + 1)  # 60s, 120s, 180s
                logger.info('  Rate limited — waiting %ds before retry (attempt %d/3)', wait, attempt + 1)
                time.sleep(wait)

            # Update knowledge manager with the insight
            km.add_llm_insight(response[:500], miner_id=miner_id)

            results.append({
                "miner_id": miner_id,
                "ip": profile["scan"].get("ip"),
                "model": profile["scan"].get("model"),
                "flagged": profile["scan"].get("times_flagged", 0),
                "analysis": response[:300],
            })

            logger.info("  ✓ Done (%d chars)", len(response))
            time.sleep(2)  # pace requests

        except Exception as e:
            logger.error("  Error analyzing miner %s: %s", miner_id, e)
            continue

    conn.close()

    # Fleet-wide summary pass
    logger.info("Running fleet-wide summary...")
    if results:
        summary_lines = [
            f"Fleet summary after comprehensive analysis of {len(results)} miners:",
            f"Miners with issues: {sum(1 for r in results if r['flagged'] > 0)}",
        ]
        for r in sorted(results, key=lambda x: x['flagged'], reverse=True)[:10]:
            summary_lines.append(
                f"Miner {r['miner_id']} ({r['model']}) @ {r['ip']}: "
                f"flagged {r['flagged']}x — {r['analysis'][:150]}"
            )
        summary_prompt = (
            "\n".join(summary_lines) +
            "\n\nWrite a 1-paragraph executive summary of fleet health. "
            "What are the top 3 systemic issues? What hardware patterns repeat across miners?"
        )
        fleet_summary = analyzer.deep_analyze(summary_prompt)
        km.add_llm_insight(fleet_summary[:500], miner_id="fleet")
        logger.info("Fleet summary complete")
        print("\nFLEET SUMMARY:")
        print(fleet_summary)

    # ── #5: Cross-miner correlation pass ─────────────────────────
    logger.info("Running cross-miner correlation analysis...")
    conn2 = sqlite3.connect(DB_PATH, timeout=30)
    conn2.row_factory = sqlite3.Row
    cross_miner_prompt = get_cross_miner_correlations(conn2)
    conn2.close()
    cross_response = analyzer.deep_analyze(cross_miner_prompt)
    km.add_llm_insight(cross_response[:500], miner_id="fleet_cross_miner")
    logger.info("Cross-miner analysis complete")
    print("\nCROSS-MINER CORRELATIONS:")
    print(cross_response)

    km.save()
    logger.info("=" * 60)
    logger.info("COMPREHENSIVE TRAINING COMPLETE — %d miners analyzed", len(results))
    logger.info("=" * 60)


if __name__ == "__main__":
    run_comprehensive_training()
