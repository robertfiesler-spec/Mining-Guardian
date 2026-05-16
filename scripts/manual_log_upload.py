#!/usr/bin/env python3
"""manual_log_upload.py — Manual miner log ingestion tool

USAGE
=====
    python manual_log_upload.py \\
        --miner-id 53487 \\
        --ip 192.168.188.57 \\
        --label pre-restart \\
        --source-dir /path/to/logs

    python manual_log_upload.py \\
        --miner-id 99999 \\
        --ip 192.168.188.28 \\
        --label diagnostic \\
        --source-dir ~/Downloads/auradine_AH3880_logs/ \\
        --auto-detect

    python manual_log_upload.py \\
        --miner-id 99999 \\
        --ip 192.168.188.28 \\
        --tech-support-zip ~/Downloads/AH3880_tech_support.zip

WHAT IT DOES
============
1. Reads every file in the source directory (or extracts a tech-support zip)
2. Auto-detects miner type from log structure:
     - BiXBiT firmware:    nvdata/.../cglog_init_*/miner.log + power.log + autotune.log
     - Stock Antminer:     kern.log, monitorAPI.log, single miner.log without nvdata path
     - Auradine:           gcminer/log/* + monitord/* + osutil/* (per-daemon directories)
                           OR a single download containing 'AH3880' / 'auradine' markers
3. Saves each log file into the miner_logs table under the requested label
4. Runs the appropriate parser:
     - BiXBiT/Stock:  parse_and_save_hardware + parse_log_metrics
     - Auradine:      auradine_parse_alarms + auradine_parse_dvfs + auradine_parse_chains
5. If --label starts with 'pre-' or 'post-' AND a matching opposite label
   exists in the DB for this miner, automatically runs the LLM comparison
6. If only one label is uploaded (e.g. 'diagnostic'), runs a single-pass
   diagnostic prompt instead of pre/post comparison
7. Posts results to Slack #mining-guardian-alerts channel
8. Stores everything in knowledge.json so it shows up in the AI dashboard

Designed to handle the full Auradine log set you can download from the web UI:
  Daemons:    monitord, osutil, kernel, webui-server, gcminer, api-server,
              etc-files, factory-files
  File types: alarms, log, crash, audit
"""

import argparse
import logging
import os
import re
import sqlite3
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Make sure we can import the daemon modules
_REPO = Path(__file__).resolve().parent.parent
for _p in [str(_REPO / "core"), str(_REPO / "ai"), str(_REPO / "api")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("manual_log_upload")


# ─────────────────────────────────────────────────────────────────────────
# MINER TYPE DETECTION
# ─────────────────────────────────────────────────────────────────────────

def detect_miner_type(file_paths: List[Path]) -> str:
    """Auto-detect the miner firmware type from a set of log file paths.

    Heuristics:
      - BiXBiT firmware:    any path contains 'nvdata/' AND 'cglog_init_'
      - Auradine:           any path/content contains 'AH3880', 'gcminer', or
                            'auradine', or has the per-daemon directory layout
      - Stock Antminer:     contains 'kern.log' or 'monitorAPI.log' but no
                            nvdata/cglog markers

    Returns: 'bixbit' | 'auradine' | 'stock_antminer' | 'unknown'
    """
    paths_str = " ".join(str(p).lower() for p in file_paths)
    names_str = " ".join(p.name.lower() for p in file_paths)

    # BiXBiT signature
    if 'nvdata' in paths_str and 'cglog_init' in paths_str:
        return 'bixbit'

    # Auradine signature — directory structure with daemon names
    auradine_daemons = ('gcminer', 'monitord', 'osutil', 'webui-server',
                        'api-server', 'etc-files', 'factory-files')
    if any(d in paths_str for d in auradine_daemons):
        return 'auradine'

    # Auradine signature in content
    for p in file_paths[:10]:  # check first 10 files only for speed
        try:
            with open(p, 'rb') as f:
                head = f.read(2048).decode('utf-8', errors='ignore').lower()
                if 'ah3880' in head or 'auradine' in head or 'dvfs alarm' in head:
                    return 'auradine'
        except Exception:
            pass

    # Stock Antminer signature
    if 'kern.log' in names_str or 'monitorapi.log' in names_str:
        return 'stock_antminer'

    return 'unknown'


# ─────────────────────────────────────────────────────────────────────────
# AURADINE LOG PARSER
# ─────────────────────────────────────────────────────────────────────────
#
# Auradine logs have a different format than BiXBiT cglog. Examples from
# the AH3880 web UI screenshot:
#
#   2026-04-08T02:55:09Z: PowerState ALARM: voltage 47.000003 is above Vmax,
#                         clipped to 47.000000
#   2026-04-08T02:55:12Z: DVFS ALARM: power is 9780.0; reducing hash rate
#   2026-04-08T08:00:06Z: DVFS ALARM: Voltage for chip 2/0 is 0.0008V; out
#                         of range 0.1050V - 0.4400V
#   2026-04-08T08:44:00Z: DVFS ALARM: power is 10205.0; reducing hash rate
#
# Patterns we extract:
#   - Per-chip voltage out-of-range events (chain/chip identification)
#   - Power reduction events (hashrate impact)
#   - PowerState clipping events (voltage rail anomalies)
#   - Crash markers (from the 'crash' filter)
#   - Audit markers (admin actions, profile changes)
# ─────────────────────────────────────────────────────────────────────────

# Auradine log line patterns
AUR_DVFS_VOLTAGE_RE = re.compile(
    r'(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?):\s*DVFS ALARM:\s*Voltage for chip\s+(?P<chip>\d+/\d+)\s+is\s+(?P<v>[\d.]+)V;\s*out of range\s+(?P<lo>[\d.]+)V\s*-\s*(?P<hi>[\d.]+)V'
)
AUR_DVFS_POWER_RE = re.compile(
    r'(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?):\s*DVFS ALARM:\s*power is\s+(?P<p>[\d.]+);\s*reducing hash rate'
)
AUR_POWERSTATE_RE = re.compile(
    r'(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?):\s*PowerState ALARM:\s*voltage\s+(?P<v>[\d.]+)\s+is above Vmax,\s*clipped to\s+(?P<clip>[\d.]+)'
)
AUR_CRASH_RE = re.compile(
    r'(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?):\s*(crash|panic|fatal|core dumped|segfault)',
    re.IGNORECASE
)


def parse_auradine_logs(file_contents: Dict[str, str]) -> Dict:
    """Parse Auradine log files and return structured findings.

    Input: dict of {filename: file_content}
    Output: dict with these keys:
      - dead_chips:     list of dicts {chip, voltage, expected_lo, expected_hi, ts}
      - dead_chains:    list of chain numbers where ALL chips are dead
      - power_reductions: list of dicts {ts, power}
      - voltage_clips:  list of dicts {ts, voltage, clipped_to}
      - crashes:        list of dicts {ts, file, line}
      - alarm_count:    total alarm lines seen
      - earliest_ts:    ISO timestamp of earliest event seen
      - latest_ts:      ISO timestamp of latest event seen
      - chips_by_chain: {chain_num: set(chip_ids)}
    """
    findings = {
        'dead_chips':       [],
        'dead_chains':      [],
        'power_reductions': [],
        'voltage_clips':    [],
        'crashes':          [],
        'alarm_count':      0,
        'earliest_ts':      None,
        'latest_ts':        None,
        'chips_by_chain':   defaultdict(set),
    }
    chip_voltages_by_chain = defaultdict(dict)  # chain -> {chip_id: voltage}

    for filename, content in file_contents.items():
        if not content:
            continue
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue

            # DVFS chip voltage out of range
            m = AUR_DVFS_VOLTAGE_RE.search(line)
            if m:
                findings['alarm_count'] += 1
                ts = m.group('ts')
                chip = m.group('chip')
                v = float(m.group('v'))
                lo = float(m.group('lo'))
                hi = float(m.group('hi'))
                chain_num, chip_num = chip.split('/')
                chip_voltages_by_chain[chain_num][chip_num] = v
                findings['chips_by_chain'][chain_num].add(chip_num)
                # Only record if voltage is actually out of range (defense)
                if v < lo or v > hi:
                    findings['dead_chips'].append({
                        'chip':         chip,
                        'chain':        chain_num,
                        'voltage':      v,
                        'expected_lo':  lo,
                        'expected_hi':  hi,
                        'ts':           ts,
                        'file':         filename,
                    })
                _track_ts(findings, ts)
                continue

            # DVFS power reduction
            m = AUR_DVFS_POWER_RE.search(line)
            if m:
                findings['alarm_count'] += 1
                findings['power_reductions'].append({
                    'ts':    m.group('ts'),
                    'power': float(m.group('p')),
                    'file':  filename,
                })
                _track_ts(findings, m.group('ts'))
                continue

            # PowerState voltage clip
            m = AUR_POWERSTATE_RE.search(line)
            if m:
                findings['alarm_count'] += 1
                findings['voltage_clips'].append({
                    'ts':         m.group('ts'),
                    'voltage':    float(m.group('v')),
                    'clipped_to': float(m.group('clip')),
                    'file':       filename,
                })
                _track_ts(findings, m.group('ts'))
                continue

            # Crashes
            m = AUR_CRASH_RE.search(line)
            if m:
                findings['crashes'].append({
                    'ts':   m.group('ts'),
                    'file': filename,
                    'line': line[:200],
                })
                _track_ts(findings, m.group('ts'))

    # Identify fully-dead chains: all observed chips on the chain showed out-of-range voltage
    for chain_num, chip_voltages in chip_voltages_by_chain.items():
        if not chip_voltages:
            continue
        all_dead = all(v < 0.1 for v in chip_voltages.values())
        if all_dead and len(chip_voltages) >= 4:  # need at least 4 chips reported
            findings['dead_chains'].append(chain_num)

    # Convert sets to sorted lists for JSON-friendly output
    findings['chips_by_chain'] = {
        k: sorted(v, key=lambda x: int(x))
        for k, v in findings['chips_by_chain'].items()
    }

    return findings


def _track_ts(findings: Dict, ts: str) -> None:
    if not findings['earliest_ts'] or ts < findings['earliest_ts']:
        findings['earliest_ts'] = ts
    if not findings['latest_ts'] or ts > findings['latest_ts']:
        findings['latest_ts'] = ts


def auradine_findings_summary(findings: Dict) -> str:
    """Render Auradine findings as a human-readable summary string."""
    lines = []
    lines.append(f"Auradine log analysis ({findings['alarm_count']} total alarms)")
    if findings['earliest_ts']:
        lines.append(f"  Time range: {findings['earliest_ts']} → {findings['latest_ts']}")
    lines.append("")

    if findings['dead_chains']:
        lines.append(f"🔴 DEAD CHAINS: {', '.join(sorted(findings['dead_chains']))}")
        for chain in sorted(findings['dead_chains']):
            chips = findings['chips_by_chain'].get(chain, [])
            lines.append(f"   chain {chain}: {len(chips)} chips reading near zero voltage (electrical failure or disconnected)")

    if findings['dead_chips'] and not findings['dead_chains']:
        # Group by chain
        by_chain = defaultdict(list)
        for c in findings['dead_chips']:
            by_chain[c['chain']].append(c['chip'])
        lines.append(f"⚠️ Chips out of voltage range: {len(findings['dead_chips'])} unique events")
        for chain, chips in sorted(by_chain.items()):
            unique_chips = sorted(set(chips), key=lambda x: int(x.split('/')[1]))
            lines.append(f"   chain {chain}: chips {', '.join(c.split('/')[1] for c in unique_chips[:10])}{' ...' if len(unique_chips) > 10 else ''}")

    if findings['power_reductions']:
        powers = [p['power'] for p in findings['power_reductions']]
        lines.append(f"⚡ DVFS power reductions: {len(powers)} events, "
                     f"range {min(powers):.0f}W → {max(powers):.0f}W")

    if findings['voltage_clips']:
        lines.append(f"⚡ PowerState voltage clips: {len(findings['voltage_clips'])} events "
                     f"(voltage being driven above Vmax and clipped down)")

    if findings['crashes']:
        lines.append(f"💥 Crashes/panics: {len(findings['crashes'])} events")
        for c in findings['crashes'][:3]:
            lines.append(f"   {c['ts']}: {c['line'][:150]}")

    if not (findings['dead_chains'] or findings['dead_chips'] or
            findings['power_reductions'] or findings['voltage_clips'] or findings['crashes']):
        lines.append("✅ No obvious hardware issues found in alarms/log content")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────
# FILE GATHERING
# ─────────────────────────────────────────────────────────────────────────

def gather_log_files(source: Path) -> Dict[str, str]:
    """Read all log-like files under source. Returns {relative_path: content}.

    If source is a directory, walks it recursively.
    If source is a zip file, extracts in-memory.
    """
    files = {}
    if source.is_file() and source.suffix.lower() == '.zip':
        with zipfile.ZipFile(source) as zf:
            for name in zf.namelist():
                if name.endswith('/'):
                    continue
                try:
                    raw = zf.read(name)
                    # Try utf-8 first, fall back to latin-1
                    try:
                        files[name] = raw.decode('utf-8')
                    except UnicodeDecodeError:
                        files[name] = raw.decode('latin-1', errors='replace')
                except Exception as e:
                    logger.warning("Failed to read %s from zip: %s", name, e)
    elif source.is_dir():
        for p in source.rglob('*'):
            if not p.is_file():
                continue
            # Skip obviously non-log files
            if p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.gif', '.pdf', '.bin', '.zip', '.tar', '.gz'}:
                continue
            try:
                rel = str(p.relative_to(source))
                with open(p, 'rb') as f:
                    raw = f.read()
                try:
                    files[rel] = raw.decode('utf-8')
                except UnicodeDecodeError:
                    files[rel] = raw.decode('latin-1', errors='replace')
            except Exception as e:
                logger.warning("Failed to read %s: %s", p, e)
    else:
        raise ValueError(f"Source must be a directory or .zip file: {source}")

    return files


# ─────────────────────────────────────────────────────────────────────────
# DB SAVE
# ─────────────────────────────────────────────────────────────────────────

def save_logs_to_db(miner_id: str, model: str, label: str, files: Dict[str, str],
                    db_path: str = "guardian.db") -> int:
    """Save log files into the miner_logs table under the given label.

    Returns the number of rows inserted (excluding dedup skips).
    """
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    with sqlite3.connect(db_path, timeout=30) as conn:
        for filename, content in files.items():
            # Dedup by (miner_id, log_file, health_status) — same as the daemon
            existing = conn.execute(
                "SELECT id FROM miner_logs WHERE miner_id=? AND log_file=? AND health_status=?",
                (miner_id, filename, label)
            ).fetchone()
            if existing:
                continue
            conn.execute(
                "INSERT INTO miner_logs "
                "(collected_at, miner_id, model, health_status, log_file, content) "
                "VALUES (?,?,?,?,?,?)",
                (now, miner_id, model, label, filename, content)
            )
            saved += 1
    return saved


# ─────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Manually upload miner logs into Mining Guardian",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--miner-id', required=True,
                        help='Miner ID (use AMS ID if known, or any unique string)')
    parser.add_argument('--ip', required=True, help='Miner IP address')
    parser.add_argument('--label', default='diagnostic',
                        help="Label: pre-restart, post-restart, pre-pdu-cycle, "
                             "post-pdu-cycle, healthy, diagnostic (default)")
    parser.add_argument('--source-dir', help='Directory containing log files')
    parser.add_argument('--tech-support-zip',
                        help='Tech support .zip file (e.g. Auradine "Download Tech Support File")')
    parser.add_argument('--model', default='Unknown',
                        help='Miner model string (auto-detected if empty)')
    parser.add_argument('--db-path', default=str(_REPO / 'guardian.db'),
                        help='Path to guardian.db (default: repo/guardian.db)')
    parser.add_argument('--no-llm', action='store_true',
                        help='Skip LLM analysis (just parse and save)')
    parser.add_argument('--no-slack', action='store_true',
                        help='Skip Slack notification')
    args = parser.parse_args()

    # Resolve source
    if args.tech_support_zip:
        source = Path(args.tech_support_zip).expanduser()
    elif args.source_dir:
        source = Path(args.source_dir).expanduser()
    else:
        parser.error("Must provide either --source-dir or --tech-support-zip")

    if not source.exists():
        parser.error(f"Source not found: {source}")

    print("=" * 75)
    print(f"MANUAL LOG UPLOAD")
    print(f"  miner_id:  {args.miner_id}")
    print(f"  ip:        {args.ip}")
    print(f"  label:     {args.label}")
    print(f"  source:    {source}")
    print("=" * 75)

    # Step 1 — gather files
    print("\n[1/5] Reading log files...")
    files = gather_log_files(source)
    print(f"      {len(files)} files read")
    if not files:
        print("ERROR: no files found")
        sys.exit(1)

    # Step 2 — detect miner type
    print("\n[2/5] Detecting miner type...")
    file_paths = [Path(f) for f in files.keys()]
    miner_type = detect_miner_type(file_paths)
    print(f"      Detected: {miner_type}")
    if args.model == 'Unknown':
        if miner_type == 'auradine':
            args.model = 'Auradine AH3880'
        elif miner_type == 'bixbit':
            args.model = 'Antminer (BiXBiT firmware)'
        elif miner_type == 'stock_antminer':
            args.model = 'Antminer (stock firmware)'

    # Step 3 — save to DB
    print(f"\n[3/5] Saving to {args.db_path} under label '{args.label}'...")
    saved = save_logs_to_db(args.miner_id, args.model, args.label, files, args.db_path)
    print(f"      {saved} new rows inserted ({len(files) - saved} skipped as duplicates)")

    # Step 4 — parse
    print(f"\n[4/5] Parsing {miner_type} logs...")
    summary = ""
    findings = None
    if miner_type == 'auradine':
        findings = parse_auradine_logs(files)
        summary = auradine_findings_summary(findings)
        print()
        for line in summary.splitlines():
            print(f"      {line}")
    elif miner_type in ('bixbit', 'stock_antminer'):
        # Use the existing daemon parsers via GuardianDB
        try:
            from mining_guardian import GuardianDB
            db = GuardianDB(args.db_path)
            for filename, content in files.items():
                if 'miner.log' in filename and content:
                    db.parse_and_save_hardware(args.miner_id, args.ip, '', content, filename)
                    db.parse_log_metrics(args.miner_id, args.ip, content, filename)
            summary = f"Parsed {len(files)} files via daemon parsers (BiXBiT/Stock format)"
            print(f"      {summary}")
        except Exception as e:
            print(f"      WARN: parser failed: {e}")
            summary = f"Parser failed: {e}"
    else:
        summary = f"Unknown miner type — files saved but not parsed"
        print(f"      {summary}")

    # Step 5 — LLM analysis
    print(f"\n[5/5] LLM analysis...")
    if args.no_llm:
        print("      Skipped (--no-llm)")
    else:
        analysis = run_llm_analysis(args.miner_id, args.ip, args.model,
                                     miner_type, args.label, files, findings,
                                     args.db_path)
        if analysis:
            print()
            for line in analysis.splitlines()[:30]:
                print(f"      {line}")
            if len(analysis.splitlines()) > 30:
                print(f"      ... ({len(analysis.splitlines()) - 30} more lines)")

            # Slack post
            if not args.no_slack:
                post_to_slack_alerts(args.miner_id, args.ip, args.model,
                                      args.label, miner_type, summary, analysis)

    print()
    print("=" * 75)
    print("DONE")
    print("=" * 75)


def run_llm_analysis(miner_id: str, ip: str, model: str, miner_type: str,
                     label: str, files: Dict[str, str], findings: Optional[Dict],
                     db_path: str) -> Optional[str]:
    """Run LLM analysis on the uploaded logs.

    If a matching opposite-label exists in the DB, runs pre/post comparison.
    Otherwise, runs single-pass diagnostic.
    """
    # Determine opposite label
    opposite = None
    if label.startswith('pre-'):
        opposite = label.replace('pre-', 'post-', 1)
    elif label.startswith('post-'):
        opposite = label.replace('post-', 'pre-', 1)

    # Check if opposite exists in DB
    opposite_content = None
    if opposite:
        try:
            with sqlite3.connect(db_path, timeout=30) as conn:
                row = conn.execute(
                    "SELECT content FROM miner_logs WHERE miner_id=? AND health_status=? "
                    "AND log_file LIKE '%miner.log' ORDER BY collected_at DESC LIMIT 1",
                    (miner_id, opposite)
                ).fetchone()
                if row:
                    opposite_content = row[0]
        except Exception as e:
            logger.warning("Could not check for opposite label: %s", e)

    # Get the main miner.log content from this upload
    main_content = ""
    for fname, content in files.items():
        if 'miner.log' in fname.lower() or fname.endswith('.log'):
            if content and len(content) > len(main_content):
                main_content = content

    if not main_content and findings:
        # Fall back to a synthesized text from Auradine findings
        main_content = auradine_findings_summary(findings)

    if not main_content:
        print("      No content to analyze")
        return None

    try:
        from llm_scan_hook import run_log_comparison_llm
        from local_llm_analyzer import LocalLLMAnalyzer
    except ImportError as e:
        print(f"      LLM modules not available: {e}")
        return None

    analyzer = LocalLLMAnalyzer()
    if not analyzer.is_available():
        print("      Local LLM not reachable — skipping analysis")
        return None

    miner_info = {
        'ip':         ip,
        'model':      model,
        'miner_type': miner_type,
        'label':      label,
    }

    if opposite_content:
        print(f"      Found {opposite} in DB — running pre/post comparison")
        # Order: pre comes first in the prompt regardless of which we just uploaded
        if label.startswith('pre-'):
            pre, post = main_content, opposite_content
        else:
            pre, post = opposite_content, main_content
        analysis = run_log_comparison_llm(
            miner_id=miner_id, pre_log=pre, post_log=post,
            miner_info=miner_info, slack_client=None,
        )
    else:
        print(f"      No opposite label in DB — running single-pass diagnostic")
        # Use analyze_restart_logs with empty 'pre' to get a diagnostic
        analysis = analyzer.analyze_restart_logs(
            miner_id=miner_id,
            pre_log="(no prior log available — single-snapshot diagnostic)",
            post_log=main_content,
            miner_info=miner_info,
        )

    # Store in knowledge.json
    if analysis:
        try:
            from knowledge_manager import KnowledgeManager
            km = KnowledgeManager()
            km.add_llm_insight(analysis, miner_id=f"manual:{label}:{miner_id}")
            print(f"      Stored in knowledge.json")
        except Exception as e:
            print(f"      WARN: could not store in knowledge.json: {e}")

    return analysis


def post_to_slack_alerts(miner_id: str, ip: str, model: str, label: str,
                          miner_type: str, summary: str, analysis: str) -> None:
    """Post analysis results to #mining-guardian-alerts."""
    try:
        from mining_guardian import GuardianConfig, SlackNotifier
        cfg = GuardianConfig.from_file(str(_REPO / 'config.json'))
        notifier = SlackNotifier(
            webhook_url=GuardianConfig._resolve(cfg.slack_webhook_url) if cfg.slack_webhook_url else None,
            bot_token=GuardianConfig._resolve(cfg.slack_bot_token) if hasattr(cfg, 'slack_bot_token') and cfg.slack_bot_token else None,
        )
        msg = (
            f"📥 *Manual log upload — {model}*\n"
            f"`{ip}` (id={miner_id}) | type: {miner_type} | label: {label}\n\n"
            f"*Parser findings:*\n```\n{summary[:1500]}\n```\n\n"
            f"*LLM analysis:*\n{analysis[:2500]}"
        )
        notifier.post_to_alerts_channel(msg)
        print(f"      Posted to #mining-guardian-alerts")
    except Exception as e:
        print(f"      WARN: Slack post failed: {e}")


if __name__ == '__main__':
    main()
