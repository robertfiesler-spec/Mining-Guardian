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

import sqlite3
import json
import logging
import time
from datetime import datetime, timedelta
from llm_analyzer import LLMAnalyzer
from knowledge_manager import KnowledgeManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("train_comprehensive")

DB_PATH = "guardian.db"


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
    conn = sqlite3.connect(DB_PATH)
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

            # Use Claude for deep analysis if available, else Ollama
            response = analyzer.deep_analyze(prompt)

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
            f"Most flagged: {sorted(results, key=lambda x: x['flagged'], reverse=True)[:5]}",
            "",
            "Individual miner analyses:",
        ]
        for r in results:
            summary_lines.append(
                f"Miner {r['miner_id']} ({r['model']}) @ {r['ip']}: {r['analysis'][:200]}"
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

    km.save()
    logger.info("=" * 60)
    logger.info("COMPREHENSIVE TRAINING COMPLETE — %d miners analyzed", len(results))
    logger.info("=" * 60)


if __name__ == "__main__":
    run_comprehensive_training()
