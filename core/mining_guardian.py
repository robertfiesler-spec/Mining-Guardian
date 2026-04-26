import os
import sys
import json
import time
import threading
import logging
from logging.handlers import TimedRotatingFileHandler
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Path setup — works whether run from repo root or core/ directory ──────────
_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT), str(_ROOT / "core"), str(_ROOT / "clients"), str(_ROOT / "monitoring")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import requests
import websocket
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from hashrate_evaluation import (
    MinerSpecsLoader, BaselineManager, HashrateTierResolver,
    parse_bixbit_profile,
)
from miner_verify import verify_miner_online
from facility_monitor import FacilityMonitor

# Database layer extracted to separate module
from database_pg import GuardianPGDB as GuardianDB
from clients.ams_client import AMSClient
from notifiers.slack_notifier import SlackNotifier

from hvac_client import HVACClient, format_hvac_report, poll_all_systems, poll_all_systems_with_db_fallback


def _setup_logging() -> logging.Logger:
    """Configure logging to both terminal and a daily rotating log file."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"guardian_{datetime.now().strftime('%Y-%m-%d')}.log"

    fmt = "%(asctime)s %(levelname)s %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt)

    # Add file handler alongside the terminal handler
    # TimedRotatingFileHandler rolls logs at midnight, keeps 14 days
    fh = TimedRotatingFileHandler(
        log_dir / "guardian.log",
        when="midnight",
        interval=1,
        backupCount=14,
        encoding="utf-8"
    )
    fh.setFormatter(logging.Formatter(fmt))
    logging.getLogger().addHandler(fh)

    return logging.getLogger("mining_guardian")

logger = _setup_logging()


# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------


# Extracted modules
from core.models import ParameterRule, MinerFinding, GuardianConfig, PolicyEngine, RemediationPlanner, RemediationCooldown
from monitoring.weather_collector import WeatherCollector
from notifiers.openclaw_notifier import OpenClawNotifier

from notifiers.approval_interface import ApprovalInterface

class MiningGuardian:
    HASHRATE_THRESHOLD = 0.80   # flag if below 80% of rated TH/s

    def __init__(self, config: GuardianConfig):
        self.config   = config
        self.ams      = AMSClient(config)
        self.notifier = OpenClawNotifier(config.openclaw_webhook_url)
        self.db       = GuardianDB()
        self.slack    = SlackNotifier(
            webhook_url=GuardianConfig._resolve(config.slack_webhook_url) if config.slack_webhook_url else None,
            bot_token=GuardianConfig._resolve(config.slack_bot_token) if hasattr(config, "slack_bot_token") and config.slack_bot_token else None,
            channel_id=getattr(config, "slack_channel_id", None),
            alerts_channel_id=getattr(config, "slack_alerts_channel_id", None),
            db=self.db,
        )
        self._last_slack_post = 0  # timestamp of last Slack post
        self._reported_notif_ids = set()  # AMS notification IDs already reported to Slack
        self.weather  = WeatherCollector()

        # ── Three-tier hashrate evaluation ───────────────────────────────
        self.specs    = MinerSpecsLoader("miner_specs.json")
        self.baseline = BaselineManager(
            # db_path omitted — BaselineManager now reads GUARDIAN_PG_* env
            # vars and builds its own Postgres DSN. Previously read
            # self.db.db_path which was the SQLite file path.
            learning_window_hours= self.specs.learning_window_hours,
            minimum_samples      = self.specs.minimum_samples,
            tolerance_pct        = self.specs.baseline_tolerance_pct,
            notify_callback      = self._on_baseline_locked,
        )
        self.tier_resolver = HashrateTierResolver(self.specs, self.baseline)

        # ── Facility infrastructure monitor ──────────────────────────────
        # Polls PDUs and immersion tank each scan cycle.
        # S19JPros (outside container) have no PDU — not polled here.
        self.facility = FacilityMonitor()
        self.hvac     = HVACClient()

        # ── Auto-discovery cache ─────────────────────────────────────────
        _catalog_path = str(_ROOT / "intelligence-catalog" / "data" / "unified_miner_index.json")
        self._known_models = self.db.load_known_models(_catalog_path)
        self._known_firmware = self.db.load_known_firmware()

    def _check_discoveries(self, miners: List[Dict]) -> None:
        """Check each miner for unknown models or firmware versions.

        Bobby's rule: if a new data point comes up that we've never seen before,
        register it — never skip over it.
        """
        for m in miners:
            if m.get("status") != "online":
                continue

            # ── Model check ──────────────────────────────────────────
            device_name = m.get("shortModel") or m.get("name") or ""
            if device_name:
                normalized = GuardianDB._normalize_model_name(device_name)
                if normalized and normalized not in self._known_models:
                    self.db.save_discovery("new_model", m, normalized, device_name)
                    logger.warning(
                        "DISCOVERY: Unknown model detected: %s at %s",
                        device_name, m.get("ip", "?")
                    )
                    # Add to in-memory cache so we only log once per session
                    self._known_models.add(normalized)

            # ── Firmware check ───────────────────────────────────────
            firmware = m.get("firmwareVersion") or ""
            if firmware and firmware not in self._known_firmware:
                normalized = GuardianDB._normalize_model_name(device_name) if device_name else ""
                self.db.save_discovery("new_firmware", m, normalized, device_name)
                logger.info(
                    "DISCOVERY: New firmware version detected: %s on %s",
                    firmware, device_name or "unknown"
                )
                self._known_firmware.add(firmware)

    def _on_baseline_locked(self, miner_id: str, model: str,
                             ip: str, baseline_ths: float, samples: int) -> None:
        """Called when a Tier 3 miner's baseline is locked — post to Slack."""
        msg = (
            f"📊 *Baseline locked for miner {miner_id}* ({model} @ {ip})\n"
            f"Learned hashrate: *{baseline_ths:.1f} TH/s* from {samples} samples over "
            f"{self.specs.learning_window_hours}h. Now actively monitoring."
        )
        logger.info("Baseline locked: %s → %.1f TH/s", miner_id, baseline_ths)
        try:
            if self.slack and hasattr(self.slack, "post_message"):
                self.slack.post_message(msg)
        except Exception as e:
            logger.warning("Failed to post baseline lock notification: %s", e)

    # ── Per-miner analysis ────────────────────────────────────

    @staticmethod
    def _analyze_chains(chains: list, expected_boards: int = 3) -> dict:
        """
        Analyse per-hashboard chain data from AMS.
        Returns a dict with:
          total_boards      — how many boards reported
          active_boards     — boards with rate > 1000 MH/s (1 TH/s floor)
          dead_boards       — boards with rate == 0 or None
          dead_indices      — list of dead board index numbers
          chain_rates_ths   — list of per-board rates in TH/s
          expected_boards   — expected board count for this model (2 or 3)
          pct_capacity      — hashrate as % of full-board capacity

        Bug fix: expected_boards is now a parameter so 2-board models like
        the AH3880 are reported correctly. Callers should pass the value from
        miner_specs.json; defaults to 3 for backward compatibility.
        """
        if not chains:
            return {"total_boards": 0, "active_boards": 0, "dead_boards": 0,
                    "dead_indices": [], "chain_rates_ths": [], "pct_capacity": None,
                    "expected_boards": expected_boards}

        rates_mhs    = [c.get("rate", 0) or 0 for c in chains]
        dead_indices = [chains[i].get("index", i) for i, r in enumerate(rates_mhs) if r < 1000]
        active       = [r for r in rates_mhs if r >= 1000]
        rates_ths    = [round(r / 1000, 1) for r in rates_mhs]

        avg_active   = (sum(active) / len(active)) if active else 0
        pct_capacity = round((len(active) / expected_boards) * 100, 1) if expected_boards > 0 else None

        return {
            "total_boards":    len(chains),
            "active_boards":   len(active),
            "dead_boards":     len(dead_indices),
            "dead_indices":    dead_indices,
            "chain_rates_ths": rates_ths,
            "avg_active_ths":  round(avg_active / 1000, 1),
            "expected_boards": expected_boards,
            "pct_capacity":    pct_capacity,
        }

    def _analyze_miner(self, miner: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Return an issue dict if the miner has a problem, else None.

        Hashrate evaluation uses three tiers:
          Tier 1 — BiXBiT firmware:  parse currentProfile string (live)
          Tier 2 — Known model spec: look up default_rated_ths in miner_specs.json
          Tier 3 — Unknown model:    use 3-day running average baseline
        During Tier 3 learning window, hashrate is NOT flagged — only hard faults.
        """
        miner_id   = str(miner.get("id", "unknown"))
        ip         = miner.get("ip", "unknown")
        name       = miner.get("shortModel", miner.get("name", "unknown"))
        model_code = miner.get("model", "")
        status     = miner.get("status", "unknown")
        hashrate   = miner.get("hashrate", 0) or 0     # MH/s from AMS
        firmware   = miner.get("firmwareManufacturer", "") or ""

        # ── Post-restart grace period ─────────────────────────────────
        # Skip action recommendations for miners that aren't fully stable.
        # Check 1: MG-tracked restarts via elevated_until (3hr window)
        # Check 2: AMS minerStatus != 0 (initializing/starting/auto-tuning)
        #   minerStatus 0 = mining (stable, ready for actions)
        #   minerStatus 3 = auto-tuning (still calibrating, don't touch)
        #   minerStatus 6 = initializing (just booted, too early)
        #   Any non-zero = not ready for actions
        # Check 3: Uptime < 20 min as fallback if minerStatus unavailable
        if self.db.is_elevated_monitoring(miner_id):
            logger.debug("[%s] Post-restart grace — elevated monitoring active", miner_id)
            return None
        miner_status = miner.get("minerStatus")
        if miner_status is not None and miner_status != 0 and status == "online":
            logger.info("[%s] minerStatus=%s (not mining) — skipping actions", miner_id, miner_status)
            return None
        uptime_str = str(miner.get("uptime", "") or "")
        if uptime_str and status == "online":
            try:
                import re as _re
                uptime_secs = 0
                if uptime_str.isdigit():
                    uptime_secs = int(uptime_str)
                if 0 < uptime_secs < 1200:  # < 20 minutes fallback
                    logger.debug("[%s] Uptime %ss < 20min — skipping actions", miner_id, uptime_secs)
                    return None
            except Exception:
                pass
        temp_chip_raw = miner.get("tempChip", 0) or 0
        temp_chip     = temp_chip_raw if temp_chip_raw >= 0 else None

        # Power — PDU reading is authoritative, fall back to miner-reported
        pdu_power    = miner.get("pduOutlet", {}).get("power", 0) or 0
        miner_power  = miner.get("consumption", 0) or 0
        power_watts  = pdu_power if pdu_power > 0 else miner_power
        power_source = "PDU" if pdu_power > 0 else "miner"
        power_kw     = round(power_watts / 1000, 3) if power_watts else None

        pdu_id       = miner.get("pduOutlet", {}).get("pduID") or 0
        outlet_index = miner.get("pduOutlet", {}).get("outletIndex") or 0
        has_pdu      = pdu_id > 0 and outlet_index > 0

        issues    = []
        action    = None
        pdu_action = None

        # ── OFFLINE check ────────────────────────────────────────────────
        if status == "offline":
            # AMS can report false-offline after a restart or WebSocket sync lag.
            # Verify directly before taking any action.
            verify = verify_miner_online(ip)
            if verify["actually_online"]:
                # Count how many consecutive scans this miner has been in AMS SYNC state
                ams_sync_count = 0
                try:
                    with self.db._connect() as conn:
                        rows = conn.execute("""
                            SELECT issue FROM miner_readings
                            WHERE miner_id=? ORDER BY id DESC LIMIT 20
                        """, (miner_id,)).fetchall()
                        for row in rows:
                            if row["issue"] and "AMS SYNC" in str(row["issue"]):
                                ams_sync_count += 1
                            else:
                                break  # stop at first non-AMS-SYNC scan
                except Exception:
                    pass

                if ams_sync_count >= 10:
                    # Been in AMS SYNC state for 10+ scans — suppress from report
                    # This miner is reachable but AMS is persistently out of sync.
                    # Don't flood reports with it — let it resolve itself.
                    logger.debug(
                        "[%s] AMS SYNC suppressed — %d consecutive scans, miner is reachable",
                        miner_id, ams_sync_count
                    )
                    return None  # exclude from issues entirely

                logger.info(
                    "[%s] AMS reports offline but miner is reachable — %s (scan %d).",
                    miner_id, verify["status_detail"], ams_sync_count + 1
                )
                issues.append(
                    f"⚠️ AMS SYNC ({ams_sync_count+1} scans): Miner is ONLINE (verified) "
                    f"but AMS reports offline — check AMS"
                )
                action = "MONITOR"
                return self._build_issue(
                    miner, issues, action, pdu_action, power_watts,
                    power_source, power_kw, pdu_id, outlet_index,
                    hashrate_pct="N/A", tier="ams_sync",
                    tier_note="AMS offline but miner reachable",
                    chain_info=None,
                )
            else:
                logger.debug(
                    "[%s] AMS offline confirmed by direct check — %s",
                    miner_id, verify["status_detail"]
                )
                offline_msg = "OFFLINE"  # Will be refined below

                # ── Offline remediation decision tree ─────────────────────
                # Domain rules from operator:
                #   S19JPros have NO PDU access — restart → still offline → bad PSU ticket
                #   S21 Hydro/Imm MAY have PDU via AMS — restart → PDU cycle → ticket
                #   has_pdu = AMS reports a PDU outlet for this miner
                #
                offline_restarts   = self.db.get_failed_restart_count(miner_id, days=1)
                offline_pdu_cycles = self.db._count_pdu_cycles(miner_id, days=1)

                # OPERATOR RULE: Firmware restart requires network connectivity.
                # If miner is truly offline (unreachable), restart command can't reach it.
                # Go straight to PDU cycle (if available) or physical inspection.
                
                if has_pdu and offline_pdu_cycles == 0:
                    # Has PDU → power cycle is the correct first action for offline miner
                    action     = "PDU_CYCLE"
                    pdu_action = f"PDU {pdu_id} → Outlet {outlet_index}"
                    offline_msg = (
                        "OFFLINE — miner unreachable. PDU power cycle recommended "
                        "(firmware restart won't work without power)"
                    )

                elif has_pdu and offline_pdu_cycles > 0:
                    # PDU cycle already tried → needs physical inspection
                    action = "PHYSICAL_INSPECTION"
                    offline_msg = (
                        "OFFLINE — PDU cycle attempted but miner still offline. "
                        "Bad PSU, bad control board, or blown fuse — physical inspection required"
                    )

                else:
                    # No PDU access (S19JPros etc.) → can't recover remotely
                    action = "PHYSICAL_INSPECTION"
                    offline_msg = (
                        "OFFLINE — no PDU access, cannot recover remotely. "
                        "Physical inspection required — likely bad PSU or control board"
                    )


                issues.append(offline_msg)
                return self._build_issue(
                    miner, issues, action, pdu_action, power_watts,
                    power_source, power_kw, pdu_id, outlet_index,
                    hashrate_pct="0%", tier="offline",
                    tier_note="Miner offline — confirmed by direct check",
                    chain_info=None,
                )

        # ── HASHBOARD check (always evaluated when online) ───────────────
        chains     = miner.get("chains", []) or []
        # Bug fix: look up correct board count from specs — AH3880 has 2, not 3
        model_code = miner.get("model", "")
        expected_boards = self.specs.get_boards(model_code, fallback=3)
        chain_info = self._analyze_chains(chains, expected_boards=expected_boards)

        if chain_info["dead_boards"] > 0:
            # Check if this miner already has known dead boards — skip reflagging
            if self.db.has_known_dead_boards(miner_id):
                logger.debug("[%s] Known dead boards — suppressed (ticket already created)", miner_id)
            else:
                dead_idx   = chain_info["dead_indices"]
                dead_count = chain_info["dead_boards"]
                issues.append(
                    f"🔴 DEAD HASHBOARD{'S' if dead_count > 1 else ''}: "
                    f"Board{'s' if dead_count > 1 else ''} {dead_idx} offline "
                    f"({chain_info['active_boards']}/{chain_info['expected_boards']} boards active, "
                    f"~{chain_info['pct_capacity']:.0f}% capacity)"
                )
                # Restart is the first-line fix — logs collected before and after
                action = "RESTART_CHECK_BOARDS"

        # ── Record baseline sample for Tier 3 learning ───────────────────
        # AMS hashrate field is in GH/s — divide by 1000 to get TH/s
        hashrate_ths = hashrate / 1_000 if hashrate > 0 else 0
        just_locked  = self.baseline.record_sample(
            miner_id, hashrate_ths, power_kw
        )
        if just_locked:
            logger.info("Baseline just locked for miner %s during this scan", miner_id)

        # ── Resolve rated TH/s (the three-tier lookup) ───────────────────
        rated_ths, tier, tier_note = self.tier_resolver.resolve(miner)

        # ── HASHRATE check ───────────────────────────────────────────────
        hashrate_pct_str = "N/A"
        if tier == "3_learning" or rated_ths is None:
            # In learning window — skip hashrate evaluation
            pass
        elif rated_ths > 0:
            pct = (hashrate_ths / rated_ths) * 100
            hashrate_pct_str = f"{pct:.1f}%"
            if pct < self.HASHRATE_THRESHOLD * 100:
                # ── Ticketed miners — never re-queue ─────────────────────
                # If this miner already has a ticket (known dead boards with
                # ticket_created set), suppress entirely. Don't add to issues,
                # don't set action, don't show in Slack. Ticket handles it.
                if self.db.has_known_dead_boards(miner_id):
                    logger.debug(
                        "[%s] Low hashrate suppressed — known dead board ticket already open",
                        miner_id
                    )
                    return None  # fully suppress — don't appear in report at all

                issues.append(
                    f"Hashrate {pct:.1f}% of rated "
                    f"({hashrate_ths:.1f} / {rated_ths:.0f} TH/s) "
                    f"[{tier}]"
                )
                # Only set RESTART if a dead board hasn't already claimed the action
                if action != "RESTART_CHECK_BOARDS":
                    # Escalation: 2+ failed restarts → ticket flow
                    # Also check outcome-labeled failures from Feature 1
                    failed_restarts = self.db.get_failed_restart_count(miner_id, days=7)
                    outcome_failures = self.db.count_outcome_failures(miner_id)
                    if failed_restarts >= 2 or outcome_failures >= 2:
                        action = "RESTART_CHECK_BOARDS"
                        issues.append(
                            f"⚠️ Escalated: {failed_restarts} restarts, "
                            f"{outcome_failures} FAILURE outcomes — ticket required"
                        )
                        logger.info(
                            "[%s] Escalating to RESTART_CHECK_BOARDS — restarts=%d outcomes=%d",
                            miner_id, failed_restarts, outcome_failures
                        )
                    else:
                        action = "RESTART"

        # ── TEMP check ───────────────────────────────────────────────────
        # Same thresholds regardless of cooling type.
        # Immersion miners are overclocked and run hotter than stock —
        # the same 76/86 limits apply across air, immersion, and hydro.
        if temp_chip is None:
            issues.append("⚠️ Sensor error — temp reading invalid")
        elif temp_chip >= 84:
            issues.append(f"🔴 RED — chip {temp_chip}°C (≥84°C, action required)")
            action = "TEMP_ACTION_REQUIRED"
        # OPERATOR RULE: No yellow tier. Liquid-cooled fleet runs 67-73°C normally.
        # Do not flag any miner below 84°C as warm/yellow/monitor.

        # ── Learning window advisory (non-blocking) ──────────────────────
        if tier == "3_learning":
            # Don't add as an "issue" — just annotate in the return dict
            pass

        if not issues:
            return None

        return self._build_issue(
            miner, issues, action, pdu_action, power_watts,
            power_source, power_kw, pdu_id, outlet_index,
            hashrate_pct=hashrate_pct_str, tier=tier,
            tier_note=tier_note,
            chain_info=chain_info,
        )

    def _build_issue(self, miner: Dict[str, Any], issues: list,
                     action: Optional[str], pdu_action: Optional[str],
                     power_watts: float, power_source: str,
                     power_kw: Optional[float], pdu_id: int, outlet_index: int,
                     hashrate_pct: str = "N/A", tier: str = "unknown",
                     tier_note: str = "",
                     chain_info: Optional[dict] = None) -> Dict[str, Any]:
        """Build the standardised issue dict returned by _analyze_miner."""
        temp_chip  = miner.get("tempChip", None)
        model_code = miner.get("model", "")
        profile    = miner.get("currentProfile", "") or ""

        # Use name (e.g. "Antminer S19JPro") as display model when AMS model
        # code is misregistered but name/profile reveal the real hardware.
        # A parseable BiXBiT profile string is the most reliable identity signal.
        short_model = miner.get("shortModel", miner.get("name", "unknown"))
        full_name   = miner.get("name", "")
        if parse_bixbit_profile(profile) and full_name:
            # Profile confirms BiXBiT firmware — trust name over shortModel
            display_model = full_name
        else:
            display_model = short_model

        return {
            "id":           str(miner.get("id", "unknown")),
            "ip":           miner.get("ip", "unknown"),
            "model":        display_model,
            "model_code":   model_code,
            "firmware":     miner.get("firmwareManufacturer", "") or "",
            "status":       miner.get("status", "unknown"),
            "hashrate_pct": hashrate_pct,
            "tier":         tier,
            "tier_note":    tier_note,
            "temp_chip":    f"{temp_chip}°C" if temp_chip is not None else "sensor error",
            "issues":       issues,
            "action":       action,
            "pdu_id":       pdu_id,
            "outlet":       outlet_index,
            "pdu_action":   pdu_action,
            "power_watts":  power_watts,
            "power_source": power_source,
            "pdu_power_kw": power_kw,
            "map_location": miner.get("mapLocation", {}).get("title") or "not mapped",
            "active_profile": miner.get("currentProfile", "") or "N/A",
            "chain_info":   chain_info,
        }

    # ── Hashboard restart + verification flow ─────────────────
    # NO TIME CAPS on the restart wait — logs are too important to miss
    # due to arbitrary timeouts. The only exits from _wait_for_stable are:
    # stable mining, emergency state, or miner removed from AMS by the
    # ticketing flow (after 5 consecutive polls where the miner disappears).

    REBOOT_POLL_FAST   = 15     # poll interval during phase 1 (seconds)
    REBOOT_POLL_SLOW   = 60     # poll interval during phase 2 (seconds) — per operator spec
    STABLE_CONFIRM     = 2      # consecutive stable polls required before collecting logs
    LOG_COLLECT_TIMEOUT = 30    # seconds to attempt log collection before giving up
    BOARD_DEAD_THRESHOLD = 1000  # MH/s — below this a board is considered dead

    def _get_common_status_direct(self, ip: str, timeout: float = 5.0) -> Optional[str]:
        """Query common_status directly from the device via TCP port 4029.

        This is the authoritative post-restart state signal from BiXBiT firmware.
        AMS is always the primary command path — this is used only during the
        post-restart stability wait where device-level status is more reliable
        than AMS polling lag.

        Returns the common_status string (e.g. "mining", "auto-tuning",
        "starting") or None if the device is unreachable or the response
        cannot be parsed.
        """
        import socket, base64, json as _json
        try:
            cmd = _json.dumps({"command": "common_status"})
            payload = _json.dumps({"enc": False, "data": base64.b64encode(cmd.encode()).decode()}) + "\n"
            with socket.create_connection((ip, 4029), timeout=timeout) as sock:
                sock.sendall(payload.encode())
                chunks = []
                sock.settimeout(timeout)
                while True:
                    try:
                        chunk = sock.recv(4096)
                        if not chunk:
                            break
                        chunks.append(chunk)
                    except socket.timeout:
                        break
                raw = b"".join(chunks).decode(errors="replace").strip()
                resp = _json.loads(raw)
                status_val = resp.get("COMMON_STATUS", [{}])[0].get("common_status")
                return status_val
        except Exception:
            return None

    def _collect_logs_nonblocking(self, miner_id: str, model: str,
                                   label: str, ip: str = "") -> dict:
        """
        Attempt log collection via direct HTTP to the miner.

        Changed 2026-04-24: the AMS /log/export path proved unreliable
        (4-hour exports, 5-of-N success rates, stuck jobs). We now hit each
        miner's /cgi-bin/create_log_backup.cgi endpoint directly with
        HTTP Digest auth (root/root), same pattern used by the 1pm cron in
        scripts/direct_collect_logs.py. No AMS dependency for logs.

        Pre/post restart pairing is preserved by the label parameter —
        save_logs writes (miner_id, model, label, content) so the AI can
        learn from before/after pairs by matching labels.

        Returns log dict {filename: content} — empty dict on any failure,
        never raises. The DB save is best-effort.

        Requires ip. If ip is empty/None the caller did not have it; we
        look it up from miner_readings before giving up.
        """
        import io
        import tarfile
        import requests
        from requests.auth import HTTPDigestAuth

        # IP fallback — look up most recent IP from DB if caller did not pass it
        if not ip:
            try:
                with self.db._connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT ip FROM miner_readings WHERE miner_id = %s "
                            "AND ip IS NOT NULL ORDER BY id DESC LIMIT 1",
                            (miner_id,),
                        )
                        row = cur.fetchone()
                        ip = row["ip"] if row else ""
            except Exception:
                ip = ""

        if not ip:
            logger.info("[%s] Log collection skipped (%s) — no IP available",
                        miner_id, label)
            return {}

        # Direct HTTP path — mirrors scripts/direct_collect_logs.py
        auth = HTTPDigestAuth("root", "root")
        from datetime import date
        target_date = date.today()
        date_path = f"/{target_date.strftime('%Y-%m')}/{target_date.strftime('%d')}"

        try:
            logger.info("[%s] Direct log fetch at %s (%s)", miner_id, ip, label)

            # Step 1: request backup creation
            resp = requests.post(
                f"http://{ip}/cgi-bin/create_log_backup.cgi",
                json=[date_path],
                auth=auth,
                timeout=60,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code != 200:
                logger.warning("[%s] Log backup create failed HTTP %s (%s) — continuing",
                               miner_id, resp.status_code, label)
                return {}

            data = resp.json()
            if data.get("stats") != "success":
                logger.warning("[%s] Log backup create returned stats=%s (%s) — continuing",
                               miner_id, data.get("stats"), label)
                return {}

            filename = data.get("msg")
            if not filename:
                logger.warning("[%s] Log backup create returned no filename (%s)",
                               miner_id, label)
                return {}

            # Step 2: download the tar
            resp = requests.get(
                f"http://{ip}/log/{filename}",
                auth=auth,
                timeout=60,
            )
            if resp.status_code != 200:
                logger.warning("[%s] Log download failed HTTP %s (%s) — continuing",
                               miner_id, resp.status_code, label)
                return {}
            if len(resp.content) < 100:
                logger.warning("[%s] Log download returned %d bytes (too small) (%s)",
                               miner_id, len(resp.content), label)
                return {}

            # Step 3: extract miner.log from tar
            logs: Dict[str, str] = {}
            with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:*") as tar:
                for member in tar.getmembers():
                    if member.name.endswith("miner.log"):
                        f = tar.extractfile(member)
                        if f:
                            content = f.read().decode("utf-8", errors="replace")
                            logs[member.name] = content
                            break

            if not logs:
                logger.info("[%s] No miner.log in tar (%s) — skipping save",
                            miner_id, label)
                return {}

            # Step 4: persist via existing save_logs (label drives pairing)
            self.db.save_logs(miner_id, model, label, logs)
            logger.info("[%s] Logs collected (%s): %d files, %d bytes",
                        miner_id, label,
                        len(logs),
                        sum(len(v) for v in logs.values()))
            return logs

        except requests.exceptions.Timeout:
            logger.warning("[%s] Log fetch timed out (%s) — continuing", miner_id, label)
            return {}
        except requests.exceptions.ConnectionError:
            logger.warning("[%s] Log fetch connection error (%s) — continuing",
                           miner_id, label)
            return {}
        except Exception as e:
            logger.warning("[%s] Log collection failed (%s): %s — continuing",
                           miner_id, label, e)
            return {}

    def _wait_for_stable(self, miner_id: str, ip: str) -> Optional[Dict]:
        """
        Two-phase state-based wait after a restart. NO TIME CAPS.

        Phase 1 — wait for AMS status == 'online'. Poll every REBOOT_POLL_FAST
                  seconds, forever, until the miner reports online OR
                  disappears from AMS entirely (sent to ticketing).

        Phase 2 — wait for stable mining state: common_status == 'mining' via
                  direct TCP port 4029 (primary) or AMS minerStatus == 0 AND
                  hashrate > 0 (fallback), on STABLE_CONFIRM consecutive polls.
                  Poll every REBOOT_POLL_SLOW seconds, forever, until stable,
                  emergency, or miner disappears from AMS.

        Rationale: logs are too important to miss due to arbitrary timeouts.
        Some miners take 45+ minutes to reach mining state after a restart
        and that is normal. We wait as long as it takes. The only ways out
        are: success (stable), emergency (escalate to ticket), or the miner
        is removed from AMS (handled upstream by the ticketing flow).

        Returns the stable miner dict on success, or None if the miner
        disappeared from AMS or entered emergency mode.
        """
        # ── Phase 1: wait for online ──────────────────────────────────────
        waited  = 0
        current = None
        logger.info("[%s] Phase 1 — waiting for status=online (no cap, polling every %ss)",
                    miner_id, self.REBOOT_POLL_FAST)
        consecutive_missing = 0
        while True:
            time.sleep(self.REBOOT_POLL_FAST)
            waited += self.REBOOT_POLL_FAST
            try:
                all_miners = self.ams.get_miners()
                current    = next(
                    (m for m in all_miners if str(m.get("id")) == str(miner_id)),
                    None
                )
                if current is None:
                    # Miner not in AMS list — could be momentary, could be
                    # that ticketing flow pulled it. Allow a few consecutive
                    # misses before giving up.
                    consecutive_missing += 1
                    if consecutive_missing >= 5:
                        logger.warning(
                            "[%s] Phase 1: miner not in AMS for %s consecutive polls — "
                            "likely pulled by ticketing flow, aborting wait",
                            miner_id, consecutive_missing
                        )
                        return None
                    logger.debug("[%s] Phase 1: miner missing from AMS (%s/5) at %ss",
                                 miner_id, consecutive_missing, waited)
                    continue
                consecutive_missing = 0
                if current.get("status") == "online":
                    logger.info("[%s] Phase 1 complete — online after %ss", miner_id, waited)
                    break
                logger.debug("[%s] Phase 1: still offline at %ss", miner_id, waited)
                # Periodic heartbeat at 10-minute marks so operators can see
                # the wait is still progressing on long-running restarts.
                if waited % 600 == 0:
                    logger.info("[%s] Phase 1: still waiting for online at %ss (no cap)",
                                miner_id, waited)
            except Exception as e:
                logger.warning("[%s] Phase 1 poll error at %ss: %s", miner_id, waited, e)

        # ── Phase 2: wait for stable mining state ────────────────────────
        # Primary signal: common_status == "mining" via TCP port 4029
        #   This is the authoritative device state from BiXBiT firmware.
        #   States like "starting", "auto-tuning", "initializing" mean not ready.
        #   "emergency" means escalate immediately.
        # Fallback signal: AMS minerStatus == 0 AND hashrate > 0
        #   Used when direct TCP is not available (e.g. different network segment).
        # We require STABLE_CONFIRM consecutive passing polls either way.
        # NO TIME CAP — wait as long as it takes.
        stable_count = 0
        waited2      = 0
        logger.info("[%s] Phase 2 — waiting for stable mining state (no cap, polling every %ss, need %s consecutive)",
                    miner_id, self.REBOOT_POLL_SLOW, self.STABLE_CONFIRM)
        consecutive_missing = 0
        while True:
            time.sleep(self.REBOOT_POLL_SLOW)
            waited2 += self.REBOOT_POLL_SLOW
            try:
                # --- Primary: direct common_status via TCP 4029 ---
                device_status = None
                try:
                    device_status = self._get_common_status_direct(ip)
                except Exception:
                    pass  # fallback to AMS below

                if device_status == "emergency":
                    logger.error(
                        "[%s] Phase 2: device entered EMERGENCY mode at %ss — escalating",
                        miner_id, waited2
                    )
                    return current  # exit, board comparison will escalate to ticket

                if device_status is not None:
                    # We have a direct device answer — trust it over AMS
                    is_stable = (device_status == "mining")
                    status_source = f"direct({device_status})"
                else:
                    # --- Fallback: AMS minerStatus + hashrate ---
                    all_miners = self.ams.get_miners()
                    current    = next(
                        (m for m in all_miners if str(m.get("id")) == str(miner_id)),
                        None
                    )
                    if not current:
                        # Miner disappeared from AMS — could be momentary,
                        # could be ticketing flow. Allow a few consecutive
                        # misses before giving up.
                        consecutive_missing += 1
                        if consecutive_missing >= 5:
                            logger.warning(
                                "[%s] Phase 2: miner not in AMS for %s consecutive polls — "
                                "likely pulled by ticketing flow, aborting wait",
                                miner_id, consecutive_missing
                            )
                            return None
                        stable_count = 0
                        continue
                    consecutive_missing = 0
                    hashrate     = current.get("hashrate", 0) or 0
                    miner_status = current.get("minerStatus", -1)
                    is_stable    = (hashrate > 0 and miner_status == 0)
                    status_source = f"ams(hr={hashrate:.0f} ms={miner_status})"

                if is_stable:
                    stable_count += 1
                    logger.info(
                        "[%s] Phase 2: stable poll %s/%s — %s",
                        miner_id, stable_count, self.STABLE_CONFIRM, status_source
                    )
                    if stable_count >= self.STABLE_CONFIRM:
                        total = waited + waited2
                        logger.info(
                            "[%s] Phase 2 complete — stable after %ss total (%ss + %ss)",
                            miner_id, total, waited, waited2
                        )
                        # Refresh AMS data one final time before returning
                        try:
                            all_miners = self.ams.get_miners()
                            current = next(
                                (m for m in all_miners if str(m.get("id")) == str(miner_id)),
                                current
                            )
                        except Exception:
                            pass
                        return current
                else:
                    if stable_count > 0:
                        logger.debug(
                            "[%s] Phase 2: stability reset at %ss — %s",
                            miner_id, waited2, status_source
                        )
                    stable_count = 0
                    # Periodic heartbeat at 10-minute marks so operators can
                    # see the wait is still progressing on long-running tunes.
                    if waited2 % 600 == 0:
                        logger.info("[%s] Phase 2: still waiting for stable mining at %ss (%s)",
                                    miner_id, waited2, status_source)
            except Exception as e:
                logger.warning("[%s] Phase 2 poll error at %ss: %s", miner_id, waited2, e)
                stable_count = 0

    def execute_board_restart(self, issue: Dict[str, Any]) -> None:
        """
        Full dead-hashboard remediation sequence:

          1. Attempt pre-restart log collection (non-blocking, 30s timeout)
             — if miner is offline or logs unavailable, skip and continue
          2. Restart miner via AMS
          3. Phase 1 wait: poll for status=online (up to 10 min)
          4. Phase 2 wait: poll for stable hashrate + minerStatus=0 (up to 45 min)
          5. Collect post-restart logs (non-blocking)
          6. Compare board states before vs after
          7a. All boards recovered → log success + Slack
          7b. Partial recovery → Slack + escalate remaining dead boards
          7c. Still dead → AMS ticket + Slack escalation

        Called after operator approves RESTART_CHECK_BOARDS action.
        """
        miner_id   = issue["id"]
        ip         = issue["ip"]
        model      = issue["model"]
        chain_info = issue.get("chain_info") or {}
        dead_before = chain_info.get("dead_boards", 0)
        dead_idx    = chain_info.get("dead_indices", [])

        logger.info(
            "Board restart flow — miner %s (%s @ %s) dead boards: %s",
            miner_id, model, ip, dead_idx
        )

        # ── Step 1: Pre-restart logs (best-effort, never blocks) ─────────
        logger.info("[%s] Step 1 — pre-restart log collection (best-effort)", miner_id)
        self._collect_logs_nonblocking(miner_id, model, "pre-restart-board-check", ip)

        # ── Step 2: Restart via AMS ───────────────────────────────────────
        logger.info("[%s] Step 2 — sending restart via AMS", miner_id)

        # Bug fix: respect dry_run in the dead-board path too
        if self.config.dry_run:
            logger.info("[%s] DRY RUN — dead-board restart skipped (set dry_run: false to enable)", miner_id)
            return

        try:
            self.ams.reboot_miner([miner_id])
            self.db.record_restart(
                miner_id, ip, model,
                f"Dead board restart — boards {dead_idx} offline before restart",
                hashrate_before=float(issue.get("hashrate_pct") or 0)
            )
            logger.info("[%s] Restart command sent", miner_id)
        except Exception as e:
            logger.error("[%s] Restart command failed: %s", miner_id, e)
            self.db.log_action(
                miner_id, ip, model,
                problem=f"Dead boards {dead_idx}",
                action_taken="RESTART_CHECK_BOARDS",
                decision="ERROR",
                notes=f"Restart command failed: {e}"
            )
            return

        # ── Steps 3+4: Wait for stable (two-phase) ───────────────────────
        logger.info("[%s] Step 3+4 — waiting for stable operation", miner_id)
        post_miner = self._wait_for_stable(miner_id, ip)

        if post_miner is None:
            self._escalate_board_issue(
                miner_id, ip, model, dead_idx,
                reason="Miner did not come back online within 10 minutes after restart"
            )
            return

        # ── Step 5: Post-restart logs (best-effort) ───────────────────────
        logger.info("[%s] Step 5 — post-restart log collection (best-effort)", miner_id)
        self._collect_logs_nonblocking(miner_id, model, "post-restart-board-check", ip)

        # ── Step 6: Compare board states ─────────────────────────────────
        logger.info("[%s] Step 6 — comparing board states", miner_id)
        post_chains    = post_miner.get("chains", []) or []
        post_info      = self._analyze_chains(post_chains, expected_boards=chain_info.get("expected_boards", 3))
        still_dead     = post_info.get("dead_boards", 0)
        still_dead_idx = post_info.get("dead_indices", [])
        recovered_idx  = [i for i in dead_idx if i not in still_dead_idx]

        logger.info(
            "[%s] Board comparison — before: %s dead %s | after: %s dead %s | recovered: %s",
            miner_id, dead_before, dead_idx, still_dead, still_dead_idx, recovered_idx
        )

        # ── Step 7: Outcome ───────────────────────────────────────────────
        if still_dead == 0:
            # Full recovery
            msg = (
                f"✅ *Board restart successful* — Miner {miner_id} ({model} @ {ip})\n"
                f"Dead board(s) {dead_idx} recovered after restart.\n"
                f"All {post_info.get('active_boards')}/{post_info.get('expected_boards')} "
                f"boards now active."
            )
            logger.info("[%s] All boards recovered", miner_id)
            self.db.log_action(
                miner_id, ip, model,
                problem=f"Dead boards {dead_idx}",
                action_taken="RESTART_CHECK_BOARDS",
                decision="RESOLVED",
                notes=f"All boards recovered. Pre/post logs saved. Recovered: {recovered_idx}"
            )
            try:
                self.slack.post_to_scans(msg)
            except Exception as e:
                logger.warning("[%s] Slack notification failed: %s", miner_id, e)

        elif still_dead < dead_before:
            # Partial recovery
            msg = (
                f"⚠️ *Partial board recovery* — Miner {miner_id} ({model} @ {ip})\n"
                f"Boards {recovered_idx} recovered. Boards {still_dead_idx} still dead.\n"
                f"Escalating to ticket for physical inspection."
            )
            logger.info("[%s] Partial recovery — escalating boards %s", miner_id, still_dead_idx)
            self.db.log_action(
                miner_id, ip, model,
                problem=f"Dead boards {dead_idx}",
                action_taken="RESTART_CHECK_BOARDS",
                decision="PARTIAL",
                notes=f"Partial recovery. Recovered: {recovered_idx}. Still dead: {still_dead_idx}"
            )
            try:
                self.slack.post_to_alerts_channel(msg)
            except Exception as e:
                logger.warning("[%s] Slack notification failed: %s", miner_id, e)
            self._escalate_board_issue(
                miner_id, ip, model, still_dead_idx,
                reason=f"Partial recovery — boards {still_dead_idx} still dead after restart"
            )

        else:
            # No recovery
            self._escalate_board_issue(
                miner_id, ip, model, still_dead_idx,
                reason=f"Board(s) {still_dead_idx} still dead after restart"
            )

    def _auto_create_missing_tickets(self, miners: list) -> None:
        """
        Scan-level ticket creation for miners that have accumulated 3+ FAILURE
        outcomes but never had an AMS ticket created — this handles the case where
        miners kept getting plain RESTART approvals instead of RESTART_CHECK_BOARDS,
        bypassing the normal ticket creation flow in execute_board_restart().

        Runs every scan. Only creates a ticket once — marks ticket_created so it
        won't repeat. Suppresses the miner from future reports automatically.
        """
        # Trigger on 3+ FAILURE outcomes OR 2+ restarts that escalated to RESTART_CHECK_BOARDS
        FAILURE_THRESHOLD = 3
        ESCALATION_THRESHOLD = 1  # even 1 dead board restart = needs inspection

        with self.db._connect() as conn:
            # Find miners with enough failures and no ticket
            # Two paths:
            # 1. 3+ FAILURE outcomes (confirmed bad)
            # 2. 2+ total restarts escalated to RESTART_CHECK_BOARDS (oscillating pattern)
            # Don't count failures from restarts in the last 30 minutes (miner may still be booting)
            candidates_failures = conn.execute("""
                SELECT miner_id, ip, model,
                       COUNT(*) as failure_count, 'failure_outcomes' as reason
                FROM miner_restarts
                WHERE outcome = 'FAILURE'
                  AND restarted_at < datetime('now', '-30 minutes')
                GROUP BY miner_id
                HAVING failure_count >= ?
            """, (FAILURE_THRESHOLD,)).fetchall()

            candidates_escalated = conn.execute("""
                SELECT miner_id, ip, model,
                       COUNT(*) as failure_count, 'escalated_restarts' as reason
                FROM miner_restarts
                WHERE restart_type LIKE '%Dead board%'
                   OR restart_type LIKE '%board%'
                GROUP BY miner_id
                HAVING failure_count >= ?
            """, (ESCALATION_THRESHOLD,)).fetchall()

            # Path 3: miners currently pending RESTART_CHECK_BOARDS approval
            candidates_pending = conn.execute("""
                SELECT DISTINCT miner_id, ip, model,
                       1 as failure_count, 'pending_board_check' as reason
                FROM pending_approvals
                WHERE action_type = 'RESTART_CHECK_BOARDS'
                  AND status = 'PENDING'
            """).fetchall()

            # Path 4: offline miners stuck in PHYSICAL_CYCLE for 3+ consecutive scans
            # These are miners where restart was tried, no PDU, needs bad PSU ticket
            candidates_offline = conn.execute("""
                SELECT miner_id, ip, model,
                       COUNT(*) as failure_count, 'offline_no_pdu' as reason
                FROM miner_readings
                WHERE action = 'PHYSICAL_CYCLE'
                  AND status = 'offline'
                  AND scan_id IN (SELECT id FROM scans ORDER BY id DESC LIMIT 10)
                GROUP BY miner_id
                HAVING failure_count >= 3
            """).fetchall()

            # Merge all paths, dedup by miner_id
            seen = set()
            candidates = []
            for c in (list(candidates_failures) + list(candidates_escalated) +
                      list(candidates_pending) + list(candidates_offline)):
                if c["miner_id"] not in seen:
                    seen.add(c["miner_id"])
                    candidates.append(c)

        logger.info(
            "Auto-ticket check: %d candidates (%d failure + %d escalated + %d pending board check + %d offline no-pdu)",
            len(candidates), len(candidates_failures),
            len(candidates_escalated), len(candidates_pending), len(candidates_offline)
        )
        for c in candidates:
            miner_id = str(c["miner_id"])
            ip       = c["ip"]
            model    = c["model"]
            failures = c["failure_count"]

            # Skip if already in known_dead_boards with a ticket
            with self.db._connect() as conn:
                existing = conn.execute("""
                    SELECT ticket_created FROM known_dead_boards
                    WHERE miner_id=? AND resolved_at IS NULL
                """, (miner_id,)).fetchone()

            if existing and existing["ticket_created"]:
                continue  # already has a ticket

            # Create the AMS ticket with diagnostic context
            reason_str = c["reason"] if "reason" in c.keys() else "persistent_failure"
            if reason_str == "offline_no_pdu":
                title = f"Offline — bad PSU suspected — {model} @ {ip}"
                description = (
                    f"Miner: {miner_id} ({model})\nIP: {ip}\n"
                    f"Issue: Miner offline, firmware restart attempted, no PDU access to power cycle.\n"
                    f"Likely cause: Bad PSU — miner cannot restart itself.\n"
                    f"Action: Physical inspection — check PSU, power connections, fuses.\n"
                    f"Note: S19JPros have no PDU outlet; PSU replacement most common fix."
                )
            elif reason_str == "pending_board_check":
                title = f"Dead hashboards — {model} @ {ip} (physical inspection required)"
                description = (
                    f"Miner: {miner_id} ({model})\nIP: {ip}\n"
                    f"Issue: Hashboards not recovering after restart attempts.\n"
                    f"Likely cause: Dead hashboard(s) — needs physical inspection and board replacement.\n"
                    f"Action: Check each board, test with known-good board if available."
                )
            elif reason_str == "escalated_restarts":
                title = f"Persistent hashrate failure — {model} @ {ip} (dead boards)"
                description = (
                    f"Miner: {miner_id} ({model})\nIP: {ip}\n"
                    f"Board check restarts: {failures}\n"
                    f"Likely cause: Dead hashboard(s) that restart cannot fix.\n"
                    f"Action: Physical board inspection and replacement required."
                )
            else:
                title = f"Persistent FAILURE outcomes — {model} @ {ip} ({failures} restarts)"
                description = (
                    f"Miner: {miner_id} ({model})\nIP: {ip}\n"
                    f"Failed restarts: {failures}\n"
                    f"Outcome: Every restart attempt returned FAILURE — miner not recovering.\n"
                    f"Possible causes: Dead hashboard, bad PSU, bad control board.\n"
                    f"Action: Physical inspection required."
                )
            try:
                ticket = self.ams.create_ticket(
                    title=title,
                    description=description,
                    priority="high",
                    miner_ids=[int(miner_id)]
                )
                ticket_id = str(ticket.get("id", "unknown"))
                logger.info(
                    "[%s] Auto-ticket created: #%s (%d failures)",
                    ip, ticket_id, failures
                )
                # Register in known_dead_boards so miner is suppressed
                if not existing:
                    self.db.register_dead_boards(
                        miner_id, ip, model,
                        board_indices=[], restart_result="failed"
                    )
                self.db.mark_ticket_created(miner_id, ticket_id)

                # Slack notification
                try:
                    self.slack.post_to_alerts_channel(
                        f"🎫 *Auto-ticket created: #{ticket_id}*\n"
                        f"  `{ip}` ({model}) — {failures} FAILURE outcomes, "
                        f"no recovery after repeated restarts.\n"
                        f"  Miner removed from reports. Physical inspection required."
                    )
                except Exception:
                    pass

            except Exception as e:
                logger.error("[%s] Auto-ticket creation failed: %s", ip, e)

    def _escalate_board_issue(self, miner_id: str, ip: str, model: str,
                               dead_idx: list, reason: str) -> None:
        """
        Escalate a persistent dead hashboard to AMS ticket + Slack alert.
        Called when restart did not resolve the board issue.
        """
        title = (
            f"Dead hashboard — {model} @ {ip} "
            f"(Miner {miner_id}, board(s) {dead_idx})"
        )
        description = (
            f"Miner: {miner_id} ({model})\n"
            f"IP: {ip}\n"
            f"Dead board(s): {dead_idx}\n"
            f"Reason: {reason}\n"
            f"Action taken: Restart attempted — board(s) did not recover.\n"
            f"Pre and post-restart logs have been collected and saved to guardian.db.\n"
            f"Physical inspection and board replacement required."
        )

        # Create AMS ticket
        try:
            ticket = self.ams.create_ticket(
                title=title,
                description=description,
                priority="high",
                miner_ids=[int(miner_id)]
            )
            ticket_id = ticket.get("id", "unknown")
            logger.info("[%s] AMS ticket created: %s", miner_id, ticket_id)
            # Mark ticket created so this miner is suppressed from future Slack reports
            self.db.register_dead_boards(miner_id, ip, model, dead_idx, restart_result="failed")
            self.db.mark_ticket_created(miner_id, str(ticket_id))
        except Exception as e:
            ticket_id = "failed"
            logger.error("[%s] AMS ticket creation failed: %s", miner_id, e)

        # Log to audit
        self.db.log_action(
            miner_id, ip, model,
            problem=f"Dead boards {dead_idx}",
            action_taken="RESTART_CHECK_BOARDS",
            decision="ESCALATED",
            notes=f"{reason}. AMS ticket #{ticket_id} created. Physical inspection required."
        )

        # Enable elevated monitoring so next scans watch it closely
        self.db.record_restart(miner_id, ip, model, reason,
                               hashrate_before=0)

        # Slack alert
        slack_msg = (
            f"🔴 *Dead hashboard — physical inspection required*\n"
            f"*Miner:* {miner_id} | {model} @ {ip}\n"
            f"*Dead board(s):* {dead_idx}\n"
            f"*Reason:* {reason}\n"
            f"*AMS Ticket:* #{ticket_id}\n"
            f"*Action:* Pre and post-restart logs saved. Board did not recover after restart.\n"
            f"Physical inspection and board replacement needed."
        )
        try:
            self.slack.post_to_critical_channel(slack_msg)
        except Exception as e:
            logger.warning("[%s] Slack escalation alert failed: %s", miner_id, e)

        logger.info(
            "[%s] Escalated — dead boards %s, ticket #%s, Slack notified",
            miner_id, dead_idx, ticket_id
        )

    # ── Execute approved actions ──────────────────────────────

    def execute_restart(self, issue: Dict[str, Any]) -> None:
        """
        Execute an approved firmware restart with pre AND post log collection.

        Flow:
          1. Capture FRESH pre-restart logs (blocks up to 120s)
          2. Restart miner via AMS
          3. Spawn background thread that waits ~75s for the miner to come
             back online, then captures FRESH post-restart logs
          4. Record action to audit log

        Both pre and post logs are stored with distinct labels in miner_logs
        so the LLM can compare them when learning whether the restart actually
        helped. The background thread is fire-and-forget — failures there do
        not block this method or affect the main daemon loop.

        Called when operator approves a RESTART action OR overnight automation
        auto-approves it.
        """
        miner_id = issue["id"]
        ip       = issue["ip"]
        model    = issue["model"]

        logger.info("[%s] Executing approved firmware restart for %s @ %s", miner_id, model, ip)

        # Bug fix: respect dry_run — log intent but do not touch AMS
        if self.config.dry_run:
            logger.info("[%s] DRY RUN — firmware restart skipped (set dry_run: false to enable)", miner_id)
            return

        # Step 1 — collect FRESH pre-restart logs
        self._collect_logs_nonblocking(miner_id, model, "pre-restart", ip)

        # Step 2 — restart via AMS
        try:
            self.ams.reboot_miner([miner_id])
            logger.info("[%s] Firmware restart sent via AMS", miner_id)
            self.db.record_restart(miner_id, ip, model, restart_type="MANUAL_APPROVED",
                                   hashrate_before=float(issue.get("hashrate_pct") or 0))
        except Exception as e:
            logger.error("[%s] Firmware restart failed: %s", miner_id, e)
            return

        # Step 3 — spawn background thread for post-restart log capture.
        # OPERATOR RULE (Bobby, Apr 8 2026): NO maximum wait time. Bobby has
        # seen miners take 5-6 HOURS to reach fully-mining-with-settled-hashrate
        # state. The number one goal is capturing the log AT THE RIGHT MOMENT
        # (not capturing it quickly). Settled hashrate detection: track the
        # last 4 hashrate readings; the miner is "settled" when the standard
        # deviation of those 4 readings is within 5% of their mean.
        # Fire-and-forget daemon thread; failures are logged but do not raise.
        # If the parent process exits before the capture completes, the daemon
        # thread is killed and we accept the post-capture gap for that one
        # action (the action itself is already in the audit log).
        def _post_restart_capture():
            import time as _time
            from collections import deque
            try:
                # Wait 60s before first poll — even reaching AMS takes time
                _time.sleep(60)

                poll_interval_seconds = 60
                history_size = 4
                settled_tolerance_pct = 5.0
                hashrate_history = deque(maxlen=history_size)
                poll_num = 0
                start_time = _time.time()

                while True:  # NO maximum — wait as long as it takes
                    poll_num += 1
                    try:
                        all_miners = self.ams.get_miners()
                        current = next(
                            (m for m in all_miners if str(m.get("id")) == str(miner_id)),
                            None
                        )
                        if current is None:
                            logger.info("[%s] Post-restart poll %d: miner not in fleet list yet",
                                        miner_id, poll_num)
                            hashrate_history.clear()
                        else:
                            status        = current.get("status", "?")
                            miner_status  = current.get("minerStatus", -1)
                            hashrate      = current.get("hashrate", 0) or 0
                            is_mining = (status == "online" and miner_status == 0 and hashrate > 0)

                            if is_mining:
                                hashrate_history.append(float(hashrate))
                                if len(hashrate_history) == history_size:
                                    mean_hr = sum(hashrate_history) / len(hashrate_history)
                                    if mean_hr > 0:
                                        variance = sum((h - mean_hr) ** 2 for h in hashrate_history) / len(hashrate_history)
                                        stddev = variance ** 0.5
                                        stddev_pct = (stddev / mean_hr) * 100
                                        is_settled = stddev_pct < settled_tolerance_pct
                                        elapsed_min = (_time.time() - start_time) / 60
                                        logger.info("[%s] Post-restart poll %d (%.1f min): mining=True hashrate=%.1f mean=%.1f stddev=%.2f%% settled=%s",
                                                    miner_id, poll_num, elapsed_min, hashrate, mean_hr, stddev_pct, is_settled)
                                        if is_settled:
                                            logger.info("[%s] Miner is fully mining with SETTLED hashrate after %.1f min — capturing post-restart logs",
                                                        miner_id, elapsed_min)
                                            self._collect_logs_nonblocking(miner_id, model, "post-restart", ip)
                                            # Wire LLM pre/post comparison — runs against local Qwen,
                                            # stores result in knowledge.json, posts to Slack
                                            self._run_post_action_log_comparison(
                                                miner_id, ip, model, "restart"
                                            )
                                            return
                                    else:
                                        hashrate_history.clear()
                                else:
                                    elapsed_min = (_time.time() - start_time) / 60
                                    logger.info("[%s] Post-restart poll %d (%.1f min): mining=True hashrate=%.1f (building history %d/%d)",
                                                miner_id, poll_num, elapsed_min, hashrate, len(hashrate_history), history_size)
                            else:
                                elapsed_min = (_time.time() - start_time) / 60
                                logger.info("[%s] Post-restart poll %d (%.1f min): status=%s minerStatus=%s hashrate=%s — not yet mining",
                                            miner_id, poll_num, elapsed_min, status, miner_status, hashrate)
                                hashrate_history.clear()
                    except Exception as poll_e:
                        logger.warning("[%s] Post-restart poll %d failed: %s", miner_id, poll_num, poll_e)
                        hashrate_history.clear()

                    _time.sleep(poll_interval_seconds)
            except Exception as e:
                logger.warning("[%s] Post-restart log capture thread failed: %s", miner_id, e)

        t = threading.Thread(target=_post_restart_capture, daemon=True,
                             name=f"post-restart-{miner_id}")
        t.start()
        logger.info("[%s] Post-restart log capture scheduled (background, polls until hashrate is fully settled — NO max wait)",
                    miner_id)

    def _run_post_action_log_comparison(self, miner_id: str, ip: str,
                                         model: str, action_label: str) -> None:
        """Compare the most recent pre/post log pair for a miner via local LLM.

        Called from the background polling thread after a successful
        post-action fresh log capture lands in the DB. Fetches the most
        recent pre and post miner.log content for the given action_label
        ('restart' or 'pdu-cycle'), passes them to the local LLM analyzer,
        stores the analysis in knowledge.json, and posts a summary to Slack.

        action_label maps to health_status:
            'restart'    -> ('pre-restart',    'post-restart')
            'pdu-cycle'  -> ('pre-pdu-cycle',  'post-pdu-cycle')

        NEVER raises. All errors logged and swallowed because this is a
        non-critical analysis step that runs in a background thread and
        must not affect the main remediation flow.
        """
        pre_label, post_label = {
            'restart':   ('pre-restart',   'post-restart'),
            'pdu-cycle': ('pre-pdu-cycle', 'post-pdu-cycle'),
        }.get(action_label, (None, None))
        if not pre_label:
            logger.warning("[%s] Unknown action_label %r — skipping LLM comparison",
                           miner_id, action_label)
            return

        try:
            # Fetch the most recent pre and post miner.log content. We only
            # care about miner.log here because it has the structured DVFS,
            # PSU, chip, and event data the LLM uses. power.log and
            # autotune.log are usually empty in our captures anyway.
            with self.db._connect() as conn:
                pre_row = conn.execute(
                    "SELECT content, datetime(collected_at) FROM miner_logs "
                    "WHERE miner_id=? AND health_status=? AND log_file LIKE ?"
                    " ORDER BY collected_at DESC LIMIT 1",
                    (miner_id, pre_label, '%miner.log')
                ).fetchone()
                post_row = conn.execute(
                    "SELECT content, datetime(collected_at) FROM miner_logs "
                    "WHERE miner_id=? AND health_status=? AND log_file LIKE ?"
                    " ORDER BY collected_at DESC LIMIT 1",
                    (miner_id, post_label, '%miner.log')
                ).fetchone()

            if not pre_row or not post_row:
                logger.info("[%s] Skipping LLM log comparison — pre or post miner.log missing (pre=%s post=%s)",
                            miner_id, bool(pre_row), bool(post_row))
                return

            pre_log  = pre_row['content'] or ""
            post_log = post_row['content'] or ""
            if not pre_log or not post_log:
                logger.info("[%s] Skipping LLM log comparison — pre or post log content empty",
                            miner_id)
                return

            logger.info("[%s] Running DUAL-MODEL log comparison: pre=%s bytes, post=%s bytes",
                        miner_id, len(pre_log), len(post_log))

            # Import both models. Either may be missing — handle each
            # independently so a single import error doesn't lose the other
            # model's analysis.
            import sys as _sys
            from pathlib import Path as _Path
            _ai = str(_Path(__file__).resolve().parent.parent / "ai")
            if _ai not in _sys.path:
                _sys.path.insert(0, _ai)

            qwen_available = False
            claude_available = False
            try:
                from llm_scan_hook import run_log_comparison_llm
                qwen_available = True
            except ImportError as ie:
                logger.warning("[%s] Qwen log comparison module unavailable: %s", miner_id, ie)
            try:
                import claude_log_comparison
                claude_available = claude_log_comparison.is_available()
                if not claude_available:
                    logger.warning("[%s] Claude API key not configured — Claude comparison disabled", miner_id)
            except ImportError as ie:
                logger.warning("[%s] Claude log comparison module unavailable: %s", miner_id, ie)

            if not qwen_available and not claude_available:
                logger.warning("[%s] Neither Qwen nor Claude log comparison available — skipping", miner_id)
                return

            miner_info = {
                "ip":     ip,
                "model":  model,
                "action": action_label,
                "pre_collected_at":  pre_row[1],
                "post_collected_at": post_row[1],
                "pre_log_size":      len(pre_log),
                "post_log_size":     len(post_log),
            }

            qwen_analysis = None
            claude_analysis = None

            # Run Qwen first (fast, free, local — usually returns in 25-90s)
            if qwen_available:
                try:
                    logger.info("[%s] Running Qwen 2.5 32B comparison...", miner_id)
                    qwen_analysis = run_log_comparison_llm(
                        miner_id=miner_id,
                        pre_log=pre_log,
                        post_log=post_log,
                        miner_info=miner_info,
                        slack_client=None,  # we'll post a unified message below
                    )
                    if qwen_analysis:
                        logger.info("[%s] Qwen comparison complete (%s chars)", miner_id, len(qwen_analysis))
                    else:
                        logger.info("[%s] Qwen comparison returned no analysis", miner_id)
                except Exception as qe:
                    logger.warning("[%s] Qwen comparison failed: %s", miner_id, qe)

            # Run Claude in parallel-ish (sequential because we want to compare
            # outputs side by side, and Claude is faster anyway — usually 8-15s)
            if claude_available:
                try:
                    logger.info("[%s] Running Claude Sonnet 4.6 comparison...", miner_id)
                    claude_analysis = claude_log_comparison.compare_logs_via_claude(
                        miner_id=miner_id,
                        pre_log=pre_log,
                        post_log=post_log,
                        miner_info=miner_info,
                    )
                    if claude_analysis:
                        logger.info("[%s] Claude comparison complete (%s chars)", miner_id, len(claude_analysis))
                    else:
                        logger.info("[%s] Claude comparison returned no analysis", miner_id)
                except Exception as ce:
                    logger.warning("[%s] Claude comparison failed: %s", miner_id, ce)

            if not qwen_analysis and not claude_analysis:
                logger.info("[%s] Both models returned no analysis", miner_id)
                return

            # Store BOTH analyses in knowledge.json with distinct miner_ids so
            # they can be retrieved separately and compared.
            try:
                from knowledge_manager import KnowledgeManager
                km = KnowledgeManager()
                if qwen_analysis:
                    km.add_llm_insight(
                        qwen_analysis,
                        miner_id=f"compare:{action_label}:qwen:{miner_id}",
                    )
                if claude_analysis:
                    km.add_llm_insight(
                        claude_analysis,
                        miner_id=f"compare:{action_label}:claude:{miner_id}",
                    )
                logger.info("[%s] Dual-model comparisons stored in knowledge.json", miner_id)
            except Exception as ke:
                logger.warning("[%s] Failed to store comparisons in knowledge.json: %s",
                               miner_id, ke)

            # Post a unified side-by-side message to Slack alerts channel.
            # Operator can see both models' verdicts and learn the differences.
            try:
                if hasattr(self, "slack") and self.slack:
                    NL = chr(10)
                    msg_parts = [
                        f"🔍 *Pre/Post Log Comparison — `{ip}` ({model})*",
                        f"Action: {action_label} | id: {miner_id}",
                        f"Pre: {len(pre_log):,} bytes  |  Post: {len(post_log):,} bytes",
                        "",
                    ]
                    if qwen_analysis:
                        q = qwen_analysis[:1500]
                        msg_parts.append(f"*🧠 Local Qwen 2.5 32B:*{NL}```{NL}{q}{NL}```")
                    else:
                        msg_parts.append("*🧠 Local Qwen 2.5 32B:* _(no analysis returned)_")
                    msg_parts.append("")
                    if claude_analysis:
                        c = claude_analysis[:1500]
                        msg_parts.append(f"*🤖 Claude Sonnet 4.6:*{NL}```{NL}{c}{NL}```")
                    else:
                        msg_parts.append("*🤖 Claude Sonnet 4.6:* _(no analysis returned)_")
                    full_msg = NL.join(msg_parts)
                    self.slack.post_to_logs(full_msg)
                    logger.info("[%s] Dual-model comparison posted to #mg-logs", miner_id)
            except Exception as se:
                logger.warning("[%s] Failed to post dual-model comparison to Slack: %s",
                               miner_id, se)

        except Exception as e:
            logger.warning("[%s] Post-action dual-model comparison failed (non-fatal): %s",
                           miner_id, e)

    def execute_pdu_cycle(self, issue: Dict[str, Any]) -> None:
        """
        Execute an approved PDU power cycle with pre-restart log collection.

        Flow:
          1. Attempt pre-restart log collection (non-blocking, 30s timeout)
          2. Turn PDU outlet OFF via AMS
          3. Wait 10 seconds
          4. Turn PDU outlet ON via AMS
          5. Log the action to audit log

        Called when operator approves a PDU_CYCLE action.
        """
        miner_id  = issue["id"]
        ip        = issue["ip"]
        model     = issue["model"]
        pdu_id    = issue.get("pdu_id")
        outlet    = issue.get("outlet")

        if not pdu_id or not outlet:
            logger.error("[%s] PDU cycle approved but no PDU/outlet info — skipping", miner_id)
            return

        logger.info("[%s] Executing approved PDU power cycle — PDU %s outlet %s",
                    miner_id, pdu_id, outlet)

        # Bug fix: respect dry_run — log intent but do not touch AMS or PDU
        if self.config.dry_run:
            logger.info("[%s] DRY RUN — PDU cycle skipped (set dry_run: false to enable)", miner_id)
            return

        # Step 1 — collect FRESH pre-pdu-cycle logs
        self._collect_logs_nonblocking(miner_id, model, "pre-pdu-cycle", ip)

        # Step 2 — power cycle via AMS
        import time
        try:
            self.ams.pdu_power_cycle(pdu_id, outlet)
            logger.info("[%s] PDU %s outlet %s — power cycled", miner_id, pdu_id, outlet)
        except Exception as e:
            logger.error("[%s] PDU cycle failed: %s", miner_id, e)
            return

        # Step 3 — wait 90 seconds for the miner to come back online enough
        # to do basic TCP-level verification. The fresh post-pdu-cycle log
        # capture happens in the background once the miner is fully mining
        # with settled hashrate (see step 5).
        logger.info("[%s] Waiting 90s for miner to recover after PDU cycle...", miner_id)
        time.sleep(90)

        # Step 4 — re-verify miner status (TCP-level check)
        from miner_verify import verify_miner_online
        result = verify_miner_online(ip)

        # Step 5 — spawn background thread for FRESH post-pdu-cycle log capture.
        # OPERATOR RULE (Bobby, Apr 8 2026): NO maximum wait. Wait as long as
        # it takes for the miner to be fully mining with settled hashrate.
        # Bobby has seen this take 5-6 hours.
        if result.get("actually_online"):
            def _post_pdu_capture():
                import time as _time
                from collections import deque
                try:
                    _time.sleep(60)  # extra cushion before first poll

                    poll_interval_seconds = 60
                    history_size = 4
                    settled_tolerance_pct = 5.0
                    hashrate_history = deque(maxlen=history_size)
                    poll_num = 0
                    start_time = _time.time()

                    while True:  # NO maximum
                        poll_num += 1
                        try:
                            all_miners = self.ams.get_miners()
                            current = next(
                                (m for m in all_miners if str(m.get("id")) == str(miner_id)),
                                None
                            )
                            if current is None:
                                logger.info("[%s] Post-PDU poll %d: miner not in fleet list yet",
                                            miner_id, poll_num)
                                hashrate_history.clear()
                            else:
                                status        = current.get("status", "?")
                                miner_status  = current.get("minerStatus", -1)
                                hashrate      = current.get("hashrate", 0) or 0
                                is_mining = (status == "online" and miner_status == 0 and hashrate > 0)

                                if is_mining:
                                    hashrate_history.append(float(hashrate))
                                    if len(hashrate_history) == history_size:
                                        mean_hr = sum(hashrate_history) / len(hashrate_history)
                                        if mean_hr > 0:
                                            variance = sum((h - mean_hr) ** 2 for h in hashrate_history) / len(hashrate_history)
                                            stddev = variance ** 0.5
                                            stddev_pct = (stddev / mean_hr) * 100
                                            is_settled = stddev_pct < settled_tolerance_pct
                                            elapsed_min = (_time.time() - start_time) / 60
                                            logger.info("[%s] Post-PDU poll %d (%.1f min): mining=True hashrate=%.1f mean=%.1f stddev=%.2f%% settled=%s",
                                                        miner_id, poll_num, elapsed_min, hashrate, mean_hr, stddev_pct, is_settled)
                                            if is_settled:
                                                logger.info("[%s] Miner is fully mining with SETTLED hashrate after %.1f min — capturing post-pdu-cycle logs",
                                                            miner_id, elapsed_min)
                                                self._collect_logs_nonblocking(miner_id, model, "post-pdu-cycle", ip)
                                                # Wire LLM pre/post comparison
                                                self._run_post_action_log_comparison(
                                                    miner_id, ip, model, "pdu-cycle"
                                                )
                                                return
                                        else:
                                            hashrate_history.clear()
                                    else:
                                        elapsed_min = (_time.time() - start_time) / 60
                                        logger.info("[%s] Post-PDU poll %d (%.1f min): mining=True hashrate=%.1f (building history %d/%d)",
                                                    miner_id, poll_num, elapsed_min, hashrate, len(hashrate_history), history_size)
                                else:
                                    elapsed_min = (_time.time() - start_time) / 60
                                    logger.info("[%s] Post-PDU poll %d (%.1f min): status=%s minerStatus=%s hashrate=%s — not yet mining",
                                                miner_id, poll_num, elapsed_min, status, miner_status, hashrate)
                                    hashrate_history.clear()
                        except Exception as poll_e:
                            logger.warning("[%s] Post-PDU poll %d failed: %s", miner_id, poll_num, poll_e)
                            hashrate_history.clear()

                        _time.sleep(poll_interval_seconds)
                except Exception as e:
                    logger.warning("[%s] Post-PDU log capture thread failed: %s", miner_id, e)

            t = threading.Thread(target=_post_pdu_capture, daemon=True,
                                 name=f"post-pdu-{miner_id}")
            t.start()
            logger.info("[%s] Post-PDU log capture scheduled (background, polls until settled — NO max wait)",
                        miner_id)
        else:
            logger.info("[%s] Skipping post-PDU log capture — miner did not come back online", miner_id)
        self.db.log_action(
            miner_id, ip, model,
            problem="Offline — PDU cycle executed",
            action_taken="PDU_CYCLE",
            decision="APPROVED",
            notes=f"Post-cycle check: {'ONLINE' if result['actually_online'] else 'STILL OFFLINE'}"
        )

        if not result["actually_online"]:
            # Still offline after PDU cycle — bad PSU or control board
            logger.warning(
                "[%s] Still offline after PDU cycle — likely bad PSU or control board",
                miner_id
            )
            # Create AMS ticket
            try:
                ticket = self.ams.create_ticket(
                    title=f"Offline after PDU cycle — {model} @ {ip} (bad PSU / control board)",
                    description=(
                        f"Miner: {miner_id} ({model})\n"
                        f"IP: {ip}\n"
                        f"Steps taken: Firmware restart attempted → PDU power cycle (off 10s, on)\n"
                        f"Result: Miner still offline after PDU cycle.\n"
                        f"Likely cause: Bad PSU, bad control board, blown fuse, or physical fault.\n"
                        f"Action required: Physical inspection — check PSU, control board, fuses."
                    ),
                    priority="high",
                    miner_ids=[int(miner_id)]
                )
                ticket_id = str(ticket.get("id", "unknown"))
                logger.info("[%s] Auto-ticket created after PDU failure: #%s", ip, ticket_id)

                # Register in known_dead_boards to suppress from future reports
                self.db.register_dead_boards(miner_id, ip, model, [], restart_result="pdu_failed")
                self.db.mark_ticket_created(miner_id, ticket_id)

                # Slack alert
                try:
                    self.slack.post_to_critical_channel(
                        f"🔴 *Offline after PDU cycle — physical inspection required*\n"
                        f"  `{ip}` ({model})\n"
                        f"  Ticket #{ticket_id} created.\n"
                        f"  Likely: bad PSU, bad control board, or blown fuse.\n"
                        f"  Miner removed from reports until ticket resolved."
                    )
                except Exception:
                    pass
            except Exception as e:
                logger.error("[%s] Failed to create post-PDU ticket: %s", ip, e)
        else:
            logger.info("[%s] Back online after PDU cycle — power issue resolved", miner_id)

    # ── Report printer ────────────────────────────────────────

    @staticmethod
    def _print_report(miners: List[Dict], issues: List[Dict],
                      wx: Optional[Dict] = None,
                      ams_notifs: Optional[List[Dict]] = None,
                      facility=None,
                      hvac=None,
                      dry_run: bool = False) -> None:
        now      = datetime.now().strftime("%Y-%m-%d %H:%M")
        online   = sum(1 for m in miners if m.get("status") == "online")
        offline  = len(miners) - online
        divider  = "━" * 60

        print(f"\n{divider}")
        print(f"  MINING GUARDIAN SCAN — {now}")
        print(divider)
        print(f"  Fleet:   {len(miners)} miners  |  {online} online  |  {offline} offline")

        # Weather line
        if wx:
            print(f"  Weather: {wx['temp_f']}°F  |  Humidity: {wx['humidity_pct']}%  "
                  f"|  Feels like: {wx['feels_like_f']}°F  "
                  f"|  Today: {wx['temp_low_f']}–{wx['temp_high_f']}°F")
        print(divider)

        # HVAC / warehouse mechanical section
        if hvac is not None:
            print(format_hvac_report(hvac))
            print(divider)

        if not issues:
            print("  ✅ All miners operating within normal parameters.")
        else:
            # Group by action
            pdu_cycles    = [i for i in issues if i["action"] == "PDU_CYCLE"]
            fw_restarts   = [i for i in issues if i["action"] == "RESTART"]
            board_restarts = [i for i in issues if i["action"] == "RESTART_CHECK_BOARDS"]
            phys_cycles   = [i for i in issues if i["action"] == "PHYSICAL_CYCLE"]
            monitors      = [i for i in issues if i["action"] == "MONITOR"]
            restarts      = pdu_cycles + fw_restarts + phys_cycles + board_restarts

            if restarts:

                if pdu_cycles:
                    print(f"\n  🔴 OFFLINE — PDU POWER CYCLE RECOMMENDED ({len(pdu_cycles)} miners)\n")
                    print(f"  {'ID':<8} {'IP':<18} {'Model':<14} {'Hashrate':<10} {'PDU Action':<25} Issue")
                    print(f"  {'-'*8} {'-'*18} {'-'*14} {'-'*10} {'-'*25} {'-'*20}")
                    for i in pdu_cycles:
                        issue_str = " | ".join(i["issues"])
                        pdu_str = i["pdu_action"] or "—"
                        print(f"  {i['id']:<8} {i['ip']:<18} {i['model']:<14} {i['hashrate_pct']:<10} {pdu_str:<25} {issue_str}")

                if fw_restarts:
                    print(f"\n  🔴 UNDERPERFORMING — FIRMWARE RESTART RECOMMENDED ({len(fw_restarts)} miners)\n")
                    print(f"  {'ID':<8} {'IP':<18} {'Model':<14} {'Hashrate':<10} {'ChipTemp':<10} Issue")
                    print(f"  {'-'*8} {'-'*18} {'-'*14} {'-'*10} {'-'*10} {'-'*30}")
                    for i in fw_restarts:
                        issue_str = " | ".join(i["issues"])
                        print(f"  {i['id']:<8} {i['ip']:<18} {i['model']:<14} {i['hashrate_pct']:<10} {i['temp_chip']:<10} {issue_str}")

                if board_restarts:
                    print(f"\n  🔴 DEAD HASHBOARD — RESTART + LOG COMPARISON REQUIRED ({len(board_restarts)} miners)\n")
                    print(f"  {'ID':<8} {'IP':<18} {'Model':<14} {'Dead Boards':<14} {'Active':<10} {'Hashrate':<10} Location")
                    print(f"  {'-'*8} {'-'*18} {'-'*14} {'-'*14} {'-'*10} {'-'*10} {'-'*20}")
                    for i in board_restarts:
                        ci = i.get("chain_info") or {}
                        dead_str   = str(ci.get("dead_indices", []))
                        active_str = f"{ci.get('active_boards',0)}/{ci.get('expected_boards',3)}"
                        print(f"  {i['id']:<8} {i['ip']:<18} {i['model']:<14} {dead_str:<14} {active_str:<10} {i['hashrate_pct']:<10} {i.get('map_location','not mapped')}")
                    print(f"\n  Flow: collect logs → restart → wait → collect logs → compare → ticket if still dead")

                if phys_cycles:
                    print(f"\n  🔴 OFFLINE — PHYSICAL POWER CYCLE REQUIRED ({len(phys_cycles)} miners)\n")
                    print(f"  ⚠️  No PDU assigned — cannot remote restart. Must be power cycled manually.\n")
                    print(f"  {'ID':<8} {'IP':<18} {'Model':<14} {'Hashrate':<10} Issue")
                    print(f"  {'-'*8} {'-'*18} {'-'*14} {'-'*10} {'-'*30}")
                    for i in phys_cycles:
                        issue_str = " | ".join(i["issues"])
                        print(f"  {i['id']:<8} {i['ip']:<18} {i['model']:<14} {i['hashrate_pct']:<10} {issue_str}")
                    print(f"\n  Action: Go to the facility and manually power cycle these miners.")

            # Miners with high temp — show action menu
            temp_action = [i for i in issues if i["action"] == "TEMP_ACTION_REQUIRED"]
            if temp_action:
                print(f"\n  🔴 HIGH TEMP — ACTION REQUIRED ({len(temp_action)} miners)\n")
                print(f"  {'ID':<8} {'IP':<18} {'Model':<14} {'ChipTemp':<10} Issue")
                print(f"  {'-'*8} {'-'*18} {'-'*14} {'-'*10} {'-'*30}")
                for i in temp_action:
                    issue_str = " | ".join(i["issues"])
                    print(f"  {i['id']:<8} {i['ip']:<18} {i['model']:<14} {i['temp_chip']:<10} {issue_str}")
                print(f"\n  Recommended actions for each miner above:")
                print(f"    [1] Restart the miner")
                print(f"    [2] Lower the power level (reduce hashrate to cut heat)")
                print(f"    [3] Raise cooling — increase fan speed or coolant flow rate")

            if monitors:
                monitor_word = "miner" if len(monitors) == 1 else "miners"
                print(f"\n  🟡 MONITOR ({len(monitors)} {monitor_word})\n")
                print(f"  {'ID':<8} {'IP':<18} {'Model':<14} {'ChipTemp':<10} Issue")
                print(f"  {'-'*8} {'-'*18} {'-'*14} {'-'*10} {'-'*30}")
                for i in monitors:
                    issue_str = " | ".join(i["issues"])
                    print(f"  {i['id']:<8} {i['ip']:<18} {i['model']:<14} {i['temp_chip']:<10} {issue_str}")

        healthy = len(miners) - len(issues)
        print(f"\n  ✅ Healthy: {healthy} miners within normal parameters")
        print(f"  {'[DRY RUN — no actions taken]' if dry_run else '[LIVE — actions will execute]'}")

        # ── Facility infrastructure section ──────────────────────────────
        if facility is not None:
            try:
                from facility_monitor import format_facility_report
                print(format_facility_report(facility))
            except Exception as e:
                logger.warning("Facility report section failed: %s", e)

        print(f"{divider}\n")
        # AMS notifications section
        if ams_notifs:
            critical = [n for n in ams_notifs if n.get("params", {}).get("alertLevel") == "Critical"]
            warnings = [n for n in ams_notifs if n.get("params", {}).get("alertLevel") == "Warning"]
            logger.info("AMS notifications — %s critical, %s warning",
                        len(critical), len(warnings))
        # Mirror the report to the log file
        logger.info("Scan complete — %s miners | %s online | %s offline | %s issues",
                    len(miners), online, offline, len(issues))

    def _send_log_failure_slack_report(self, failed_miners: List[Dict]) -> None:
        """Send Slack report of miners that failed log collection.
        
        OPERATOR REQUIREMENT (April 11 2026):
        Report problem miners so Bobby can fix them physically.
        """
        if not failed_miners:
            return
        
        try:
            # Get last successful log time for each miner
            with self.db._connect() as conn:
                enriched = []
                for m in failed_miners:
                    miner_id = m.get("id", "")
                    row = conn.execute(
                        "SELECT MAX(collected_at) FROM miner_logs WHERE miner_id = ?",
                        (miner_id,)
                    ).fetchone()
                    last_log = row[0][:10] if row and row[0] else "never"
                    enriched.append({
                        "id": miner_id,
                        "ip": m.get("ip", "?"),
                        "model": m.get("model", "?")[:20],
                        "last_log": last_log,
                    })
            
            # Build message
            lines = [
                ":warning: *LOG COLLECTION FAILURES*",
                "",
                f"{len(enriched)} miners failed to export logs after 2 attempts:",
                "",
            ]
            
            for m in enriched:
                lines.append(f":red_circle: `{m['ip']}` ({m['model']}) — last log: {m['last_log']}")
            
            lines.extend([
                "",
                "_These miners may need physical inspection:_",
                "• Check AMS for export errors",
                "• Verify miner has storage space",
                "• Try manual log export in AMS web UI",
                "• Consider SSH-based log collection",
            ])
            
            message = "\n".join(lines)
            # self.slack.post_to_logs(message)  # Send to #mg-logs, not #mining-guardian
            logger.info("Sent log failure report to #mg-logs: %d miners", len(enriched))
            
        except Exception as e:
            logger.warning("Failed to send log failure Slack report: %s", e)

    # ── Main entry ────────────────────────────────────────────

    def collect_logs(self, miners: List[Dict], issues: List[Dict]) -> None:
        """Daily baseline log collection — NOW A NO-OP at scan time.

        Changed 2026-04-24: the daily baseline AMS-based collection was
        unreliable (4-hour stuck exports, 5-of-N success rates, parallel
        retry logic that never actually recovered well). We removed the
        entire AMS log-pull block from the hourly scan path.

        Log collection now happens in exactly two places:

        1. scripts/direct_collect_logs.py (1pm daily cron) — pulls every
           online miner's log directly via HTTP Digest to the miner's
           /cgi-bin/create_log_backup.cgi endpoint. Proven reliable.

        2. Pre/post-restart pairs in execute_restart, execute_board_restart,
           execute_pdu_cycle — via _collect_logs_nonblocking, also using
           direct HTTP as of 2026-04-24.

        This method is kept so run_once() does not have to change. It
        just no-ops with a debug message.
        """
        if not self.config.collect_logs:
            return
        logger.debug(
            "collect_logs: daily baseline is now handled by 1pm cron "
            "(scripts/direct_collect_logs.py). Skipping in-scan collection."
        )
        return

    def run_once(self) -> Dict[str, Any]:
        # ── Poll facility infrastructure first ───────────────────────────
        facility_snapshot = self.facility.poll()

        # Fetch weather and AMS notifications
        wx = self.weather.fetch()
        if wx:
            self.db.save_weather(wx)

        # Poll BOTH HVAC systems (warehouse + s19jpro container)
        hvac_snapshots = poll_all_systems_with_db_fallback()
        hvac_snapshot = hvac_snapshots.get('warehouse')  # Primary for Hydros/S21/AH3880
        hvac_s19jpro = hvac_snapshots.get('s19jpro')     # For S19J Pros only
        for sys_id, snap in hvac_snapshots.items():
            if snap:
                self.db.save_hvac(snap)

        ams_notifs = self.ams.get_notifications("miner")
        if ams_notifs:
            self.db.save_notifications(ams_notifs)
            logger.info("Pulled %s AMS notifications", len(ams_notifs))

        # Filter out already-reported notifications for Slack
        new_notifs = []
        if ams_notifs:
            for n in ams_notifs:
                nid = n.get("id")
                if nid and nid not in self._reported_notif_ids:
                    new_notifs.append(n)
                    self._reported_notif_ids.add(nid)
            if len(new_notifs) < len(ams_notifs):
                logger.info("AMS notifications: %d new, %d already reported",
                            len(new_notifs), len(ams_notifs) - len(new_notifs))

        miners   = self.ams.get_miners(self.config.miner_filters)

        # AMS-down detection — if ALL miners are offline, AMS is likely down
        online_count = sum(1 for m in miners if m.get("status") == "online")
        ams_is_down = len(miners) > 0 and online_count == 0

        if ams_is_down:
            logger.warning("AMS appears down — all %d miners reporting offline", len(miners))
            # Only post once per hour, just weather + mechanical
            import time as _time
            now_ts = _time.time()
            if now_ts - self._last_slack_post >= self.config.slack_interval_seconds:
                self._last_slack_post = now_ts
                self.slack.send_ams_down(miners, wx, hvac_snapshot)
            else:
                logger.info("AMS down — Slack throttled, next post in %ds",
                            int(self.config.slack_interval_seconds - (now_ts - self._last_slack_post)))
            # Still save scan to DB for tracking, but skip everything else
            self.db.save_scan(miners, [])
            # Update knowledge
            try:
                from knowledge_manager import KnowledgeManager
                km = KnowledgeManager()
                km.update_from_scan(miners, [], wx, hvac_snapshot)
            except Exception:
                pass
            return {"scanned": len(miners), "issues": 0, "ams_down": True}

        # ── Auto-discovery: flag unknown models and firmware ─────────
        try:
            self._check_discoveries(miners)
        except Exception:
            logger.exception("Auto-discovery check failed (non-fatal)")

        issues   = [r for r in (self._analyze_miner(m) for m in miners) if r]
        self._print_report(miners, issues, wx, ams_notifs, facility_snapshot, hvac_snapshot,
                           dry_run=self.config.dry_run)
        scan_id   = self.db.save_scan(miners, issues)

        # Expire unanswered approvals older than 1 hour before saving new ones
        # This keeps the queue clean — only the current scan's actions are ever pending
        expired = self.db.expire_old_pending_approvals(max_age_minutes=60)
        if expired:
            logger.info("Expired %d stale pending approvals", expired)

        # Cancel pending approvals for miners that now have tickets
        # Prevents stale RESTART_CHECK_BOARDS approvals from sitting in queue
        # after a ticket has been auto-created for that miner
        try:
            with self.db._connect() as conn:
                ticketed_ids = [r["miner_id"] for r in conn.execute(
                    "SELECT miner_id FROM known_dead_boards WHERE resolved_at IS NULL"
                ).fetchall()]
                if ticketed_ids:
                    placeholders = ",".join("?" for _ in ticketed_ids)
                    cancelled = conn.execute(f"""
                        UPDATE pending_approvals
                        SET status='CANCELLED', responded_at=datetime('now')
                        WHERE miner_id IN ({placeholders}) AND status='PENDING'
                    """, ticketed_ids).rowcount
                    if cancelled:
                        logger.info(
                            "Cancelled %d pending approvals for ticketed miners", cancelled
                        )
                    conn.commit()
        except Exception:
            logger.exception("Failed to cancel ticketed pending approvals (non-fatal)")

        # ── Auto-ticket: miners with 3+ FAILURE outcomes and no ticket yet ──
        # This handles miners that kept getting plain RESTART approvals but never
        # went through the RESTART_CHECK_BOARDS flow that normally creates tickets.
        try:
            self._auto_create_missing_tickets(miners)
        except Exception:
            logger.exception("Auto-ticket creation failed (non-fatal)")

        self.db.save_chain_readings(scan_id, datetime.now().isoformat(), miners)
        self.db.save_pool_readings(scan_id, datetime.now().isoformat(), miners)
        self.db.save_miner_state_readings(scan_id, datetime.now().isoformat(), miners)
        self.db.save_ams_extended(scan_id, datetime.now().isoformat(), miners)
        self.db.purge_old_logs(days=30)
        self.collect_logs(miners, issues)
        self.notifier.send_scan(miners, issues)

        # Slack throttle — only post at most once per slack_interval_seconds
        import time as _time
        now_ts = _time.time()
        if now_ts - self._last_slack_post >= self.config.slack_interval_seconds:
            thread_ts = self.slack.send_scan(miners, issues, wx, new_notifs, hvac_snapshot, hvac_s19jpro)
            self._last_slack_post = now_ts
            if thread_ts and issues:
                self.db.save_pending_approvals(thread_ts, scan_id, issues)
        else:
            logger.info("Slack throttled — next post in %ds",
                        int(self.config.slack_interval_seconds - (now_ts - self._last_slack_post)))

        # LLM analysis — feed scan data to local Ollama model
        # Skip when scan data is clearly bad (AMS down = all offline)
        online = sum(1 for m in miners if m.get("status") == "online")
        actionable_issues = [i for i in issues if i["action"] not in ("MONITOR", "PHYSICAL_CYCLE")]
        # LLM analysis — Qwen on ROBS-PC via Tailscale (RTX 4090, ~4.6s per scan)
        # Restored 2026-04-10 after diagnosing frozen llm_scan_analyses stream.
        # Writes to knowledge['llm_scan_analyses'] which weekly_train.py reads.
        # Two-tier AI: Qwen on every scan here, Claude only in Sunday weekly trainer.
        if actionable_issues and online > 0 and len(actionable_issues) <= 20:
            try:
                import json as _json
                import urllib.request as _urlreq
                from datetime import datetime as _dt
                from pathlib import Path as _P
                wx_data = {"temp_f": wx.get("temp_f"), "humidity_pct": wx.get("humidity_pct")} if wx else None
                # Include BOTH HVAC systems in context
                hvac_data = {}
                if hvac_snapshot:  # Warehouse (Hydros, S21 Imm, AH3880)
                    hvac_data["warehouse"] = {
                        "supply_f": hvac_snapshot.supply_temp_f,
                        "return_f": hvac_snapshot.return_temp_f,
                        "delta_t": hvac_snapshot.delta_t_f
                    }
                if hvac_s19jpro:  # S19J Pro container
                    hvac_data["s19jpro"] = {
                        "supply_f": hvac_s19jpro.supply_temp_f,
                        "return_f": hvac_s19jpro.return_temp_f,
                        "delta_t": hvac_s19jpro.delta_t_f,
                        "container_f": getattr(hvac_s19jpro, 'container_temp_f', None),
                        "outside_air_f": getattr(hvac_s19jpro, 'outside_air_f', None)
                    }
                qwen_prompt = (
                    "You are the local LLM for a 58-miner liquid-cooled Bitcoin mining facility with TWO HVAC systems: warehouse (Hydros/S21/AH3880) and s19jpro container (S19J Pros only). "
                    "Operator rules: do NOT flag chip temps below 84C (normal in liquid cooling), "
                    "do NOT recommend HVAC investigation (HVAC is confirmed correct), "
                    "2+ failed restarts in 7 days auto-escalates to board check.\n\n"
                    f"Scan #{scan_id} — {len(actionable_issues)} miners flagged:\n" +
                    "\n".join(f"- Miner {i['id']} ({i['model']}) @ {i['ip']}: {i.get('action','?')} — {' | '.join(i.get('issues',[]))[:150]}" for i in actionable_issues[:10]) +
                    f"\nWeather: {wx_data}\nHVAC (both systems): {hvac_data}\n\n"
                    "Provide: DIAGNOSIS (1 sentence), ACTION (bullet list with miner IPs), PATTERN (1 sentence or 'none')."
                )
                payload = {
                    "model": getattr(self.config, "ollama_model", "qwen2.5:32b-instruct-q4_K_M"),
                    "prompt": qwen_prompt,
                    "stream": False,
                    "options": {"temperature": 0.3, "num_ctx": 16384},
                }
                req = _urlreq.Request(
                    getattr(self.config, "ollama_url", os.getenv("OLLAMA_URL", "http://100.110.87.1:11434/api/generate")),
                    data=_json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with _urlreq.urlopen(req, timeout=60) as r:
                    resp = _json.loads(r.read().decode())
                analysis_text = resp.get("response", "").strip()
                if analysis_text:
                    logger.info("Qwen scan analysis: %s", analysis_text[:200])
                    # Write to llm_scan_analyses stream (the one weekly_train.py reads)
                    kpath = _P("/root/Mining-Guardian/knowledge.json")
                    knowledge = _json.loads(kpath.read_text()) if kpath.exists() else {}
                    if not isinstance(knowledge.get("llm_scan_analyses"), list):
                        knowledge["llm_scan_analyses"] = []
                    knowledge["llm_scan_analyses"].append({
                        "timestamp": _dt.now().isoformat(),
                        "analysis": analysis_text,
                        "model": payload["model"],
                        "scan_id": scan_id,
                        "source": "qwen_scan_loop",
                    })
                    # Keep last 500 entries to bound file size
                    knowledge["llm_scan_analyses"] = knowledge["llm_scan_analyses"][-500:]
                    tmp = str(kpath) + ".tmp"
                    with open(tmp, "w") as f:
                        _json.dump(knowledge, f, indent=2)
                    import os as _os
                    _os.replace(tmp, str(kpath))
                    logger.info("llm_scan_analyses written, now %d entries", len(knowledge["llm_scan_analyses"]))
                else:
                    logger.warning("Qwen returned empty response for scan #%d", scan_id)
            except Exception as e:
                logger.warning("Qwen scan analysis failed: %s", e)
        elif issues and online == 0:
            logger.info("LLM analysis skipped — all miners offline (AMS likely down)")
        elif len(actionable_issues) > 20:
            logger.info("LLM analysis skipped — too many issues (%d), likely systemic problem", len(actionable_issues))

        # Update persistent knowledge with scan results
        try:
            from knowledge_manager import KnowledgeManager
            km = KnowledgeManager()
            km.update_from_scan(miners, issues, wx, hvac_snapshot)
        except Exception as e:
            logger.warning("Knowledge update skipped: %s", e)

        return {
            "scanned": len(miners),
            "issues":  len(issues),
            "pdu_cycle":         [i["id"] for i in issues if i["action"] == "PDU_CYCLE"],
            "firmware_restart":  [i["id"] for i in issues if i["action"] == "RESTART"],
            "board_restart":     [i["id"] for i in issues if i["action"] == "RESTART_CHECK_BOARDS"],
            "physical_cycle":    [i["id"] for i in issues if i["action"] == "PHYSICAL_CYCLE"],
            "monitor":           [i["id"] for i in issues if i["action"] == "MONITOR"],
        }

    def loop(self) -> None:
        # Ensure ai/ directory is in sys.path for all feature imports
        import sys as _sys
        _ai_path = str(Path(__file__).resolve().parent.parent / "ai")
        if _ai_path not in _sys.path:
            _sys.path.insert(0, _ai_path)

        # Import outcome checker once at loop start
        try:
            from outcome_checker import check_outcomes
            _has_outcome_checker = True
        except ImportError:
            logger.warning("outcome_checker not found — outcome feedback disabled")
            _has_outcome_checker = False

        while True:
            try:
                self.run_once()

                # Feature 1: Outcome Feedback Loop
                # Runs after every scan to evaluate restart outcomes
                if _has_outcome_checker:
                    try:
                        check_outcomes()
                    except Exception:
                        logger.exception("Outcome checker error (non-fatal)")

                # Feature 5: HVAC/Environment Correlation
                # Check if fleet flags correlate with facility stress
                try:
                    from hvac_correlator import check_fleet_correlation, get_facility_stress_level
                    stress, reasons = get_facility_stress_level()
                    if stress >= 26:
                        logger.info("Facility stress %d%%: %s", stress, reasons)
                    # check_fleet_correlation uses the latest scan id
                    latest_scan_id = self.db._latest_scan_id()
                    if latest_scan_id:
                        check_fleet_correlation(latest_scan_id)
                except Exception:
                    logger.debug("HVAC correlator skipped (non-fatal)")

                # Feature 6: Pre-Failure Prediction
                # Detect miners showing pre-failure signals before they break
                try:
                    from predictor import run_predictions, format_prediction_alert
                    latest_scan_id = self.db._latest_scan_id()
                    if latest_scan_id:
                        preds = run_predictions(latest_scan_id)
                        for pred in preds:
                            # Only alert for high-confidence predictions (>= 75%)
                            if pred.get("confidence", 0) < 75:
                                logger.debug("Prediction skipped (low conf): %s conf=%d%%",
                                           pred.get("ip"), pred.get("confidence", 0))
                                continue
                            
                            logger.info("Prediction alert: %s %s conf=%d%%",
                                       pred.get("ip"), pred.get("action"), pred.get("confidence", 0))

                            # Skip ticketed miners — they already have a ticket open
                            if self.db.has_known_dead_boards(pred["miner_id"]):
                                logger.debug(
                                    "Prediction suppressed for %s — dead board ticket open", pred["ip"]
                                )
                                continue

                            # Skip Auradine voltage signal — 0.29V is their firmware format
                            firmware = ""
                            try:
                                with self.db._connect() as _c:
                                    _fw = _c.execute(
                                        "SELECT firmware_manufacturer FROM miner_readings "
                                        "WHERE miner_id=? ORDER BY id DESC LIMIT 1", (pred["miner_id"],)
                                    ).fetchone()
                                    firmware = (_fw["firmware_manufacturer"] or "").upper() if _fw else ""
                            except Exception:
                                pass
                            if "AURADINE" in firmware:
                                filtered = [s for s in pred.get("signals", [])
                                            if "voltage" not in s.lower()]
                                if not filtered:
                                    logger.debug("Prediction suppressed for %s — Auradine voltage false positive", pred["ip"])
                                    continue
                                pred["signals"] = filtered

                            if pred["action"] == "PREEMPTIVE_RESTART":
                                # Skip Slack notification if auto-approve is active (noise reduction)
                                if self.auto_approve_enabled:
                                    logger.info("Prediction suppressed (auto-approve active): %s", pred["ip"])
                                    continue
                                try:
                                    # Post as approval request so you can APPROVE or DENY
                                    msg = format_prediction_alert(pred)
                                    thread = self.slack.post_to_approvals(
                                        msg + "\n\n_Reply `APPROVE` to execute restart or `DENY` to skip._"
                                    )
                                    # Register as pending approval so listener picks it up
                                    if thread and isinstance(thread, str):
                                        self.db.save_pending_approvals(
                                            thread, latest_scan_id,
                                            [{
                                                "id":          pred["miner_id"],
                                                "ip":          pred["ip"],
                                                "model":       pred.get("model", ""),
                                                "action":      "RESTART",
                                                "issues":      pred.get("signals", []),
                                                "hashrate_pct":f"{pred.get('current_hr', 0):.1f}%",
                                                "temp_chip":   pred.get("current_chip_temp", 0),
                                            }]
                                        )
                                except Exception:
                                    pass
                            logger.info("Prediction: %s %s conf=%d%%",
                                       pred["ip"], pred["action"], pred["confidence"])
                except Exception:
                    logger.debug("Predictor skipped (non-fatal)")

                # Feature 8: Action Diversity
                # Evaluate power tuning, eco mode, pool failover
                try:
                    from action_diversity import evaluate_all_actions
                    latest_scan_id = self.db._latest_scan_id()
                    if latest_scan_id:
                        new_actions = evaluate_all_actions(latest_scan_id)
                        for act in new_actions:
                            logger.info(
                                "Action diversity: %s for %s conf=%d%% reasons=%s",
                                act["action"], act["ip"],
                                act["confidence"], act.get("reasons", [])[:1]
                            )
                            # Log to audit trail for tracking
                            try:
                                self.db.log_action(
                                    act["miner_id"], act["ip"],
                                    act["model"],
                                    problem="; ".join(act.get("reasons", [])),
                                    action_taken=act["action"],
                                    decision="PENDING_APPROVAL",
                                    notes=f"confidence={act['confidence']}% data={act.get('data_used',[])}",
                                )
                            except Exception:
                                pass
                            # Post to Slack so operator can approve/deny
                            try:
                                reasons_str = ", ".join(act.get("reasons", []))[:100]
                                msg = (
                                    f":crystal_ball: *AI Recommendation — {act['action']}*\n"
                                    f"Miner: `{act['ip']}` ({act['model']})\n"
                                    f"Confidence: *{act['confidence']}%*\n"
                                    f"Reason: {reasons_str}\n\n"
                                    f"_Reply `APPROVE` to execute or `DENY` to skip._"
                                )
                                thread = self.slack.post_to_approvals(msg)
                                if thread and isinstance(thread, str) and thread:
                                    issue_entry = [{
                                        "id": act["miner_id"],
                                        "ip": act["ip"],
                                        "model": act["model"],
                                        "action": act["action"],
                                        "issues": act.get("reasons", []),
                                    }]
                                    self.db.save_pending_approvals(
                                        thread, latest_scan_id, issue_entry
                                    )
                            except Exception as ex:
                                logger.warning("Action diversity Slack post failed: %s", ex)
                            
                except Exception:
                    logger.debug("Action diversity skipped (non-fatal)")

                # ── Local LLM scan analysis (background thread) ──────────
                # Sends fleet data to Qwen 32B on RTX 4090 for real-time analysis.
                # Runs in background thread — never blocks the next scan.
                try:
                    import threading
                    from llm_scan_hook import run_post_scan_llm
                    # scan_id is local to run_once() — fetch latest from DB instead
                    with self.db._connect() as conn:
                        _latest = conn.execute(
                        "SELECT id FROM scans ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                    if _latest:
                        _scan_id = _latest["id"]
                        logger.info("Local LLM analysis scheduled for scan #%s", _scan_id)
                        def _llm_analysis():
                            try:
                                run_post_scan_llm(_scan_id, self.slack)
                                logger.info("Local LLM analysis complete for scan #%s", _scan_id)
                            except Exception as ex:
                                logger.warning("Local LLM analysis thread error: %s", ex)
                        threading.Thread(target=_llm_analysis, daemon=True).start()
                    else:
                        logger.debug("Local LLM analysis skipped — no scans yet")
                except Exception as ex:
                    logger.warning("Local LLM analysis setup failed: %s", ex)

            except Exception:
                logger.exception("Guardian loop error")
            time.sleep(self.config.scan_interval_seconds)


# ------------------------------------------------------------
# Example config + entrypoint
# ------------------------------------------------------------

EXAMPLE_CONFIG = {
    "ams_base_url": "https://api-staging.dev.bixbit.io/api/v1",
    "ams_email":        "env:AMS_EMAIL",
    "ams_password":     "env:AMS_PASSWORD",
    "ams_workspace_id": "env:AMS_WORKSPACE_ID",
    "openclaw_webhook_url": "http://127.0.0.1:18789/hooks",
    "dry_run": True,
    "scan_interval_seconds": 300,
    "approval_mode": "manual",
    "miner_filters": {},
    "rules": [
        {
            "key": "telemetry.hashrate_ths",
            "operator": "gte",
            "expected": 85,
            "severity": "critical",
            "recommended_fix": None,
            "note": "Hashrate below model minimum — requires operator review"
        },
        {
            "key": "telemetry.chip_temp_c",
            "operator": "between",
            "expected": [40, 80],
            "severity": "critical",
            "recommended_fix": "efficiency",
            "note": "Chip temp outside safe envelope — drop to efficiency profile"
        },
    ]
}


def write_example_config(path: str = "config.example.json") -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(EXAMPLE_CONFIG, f, indent=2)
    logger.info("Wrote %s", path)


if __name__ == "__main__":
    import sys
    config_path = os.environ.get("GUARDIAN_CONFIG", "config.json")
    if not os.path.exists(config_path):
        write_example_config()
        raise SystemExit("Create config.json from config.example.json, then re-run.")

    config   = GuardianConfig.from_file(config_path)
    guardian = MiningGuardian(config)

    if "--loop" in sys.argv:
        logger.info("Starting Mining Guardian in loop mode (interval=%ss)", config.scan_interval_seconds)
        guardian.loop()
    else:
        result = guardian.run_once()
        print(json.dumps(result, indent=2))
