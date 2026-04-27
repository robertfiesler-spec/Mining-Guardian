"""
Slack Notifier
Extracted from mining_guardian.py on April 21, 2026

This module handles all Slack notifications for Mining Guardian,
including fleet alerts, scan reports, and HVAC status updates.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# GuardianDB is used in two try/except blocks below for known_dead_boards
# lookup and newly_ticketed notification. Historically this import was
# missing — the NameError was silently swallowed by except Exception: pass,
# so the code never actually ran. Added 2026-04-23 during Postgres flip.
from core.database_pg import GuardianPGDB as GuardianDB

logger = logging.getLogger(__name__)

class SlackNotifier:

    # ── Channel routing (Apr 8 2026) ──────────────────────────────────────
    # The fleet operator (Bobby) split #mining-guardian into 6 dedicated
    # channels so each message type lives in its own stream. This makes
    # the AI report channel a clean historical journal of LLM thinking,
    # the approvals channel an at-a-glance pending queue, etc.
    #
    # Each constant can be overridden via environment variable for ops
    # flexibility. Defaults are the production channel IDs in the
    # bixbitusa workspace.

    # Main channel — operator chat, natural language queries, manual ops
    CHANNEL_ID         = "C0AQ8SE1448"  # #mining-guardian
    # Hourly fleet scan posts — the routine operational stream
    SCANS_CHANNEL_ID   = "C0ARLJUJ3BQ"  # #mg-scans
    # Mining Guardian AI Analysis output — LLM interpretations
    AI_CHANNEL_ID      = "C0ARSB1U604"  # #mg-ai-reports
    # Pending approval requests + approve/deny threads
    APPROVALS_CHANNEL_ID = "C0AR79YRZ9V"  # #mg-approvals
    # Critical alerts — firmware regressions, ticket creation, dead boards
    ALERTS_CHANNEL_ID  = "C0ARJP300J0"  # #mining-guardian-alerts (existing)
    # Wake-up level critical alerts — physical inspection required, offline after PDU, dead board escalation
    CRITICAL_CHANNEL_ID = "C0AUX8DNGTB"  # #mg-critical
    # Pre/post log comparisons + dual-model verdicts + manual upload analyses
    LOGS_CHANNEL_ID    = "C0ASH2CPHBJ"  # #mg-logs

    def __init__(self, webhook_url: Optional[str], channel_id: Optional[str] = None,
                 bot_token: Optional[str] = None,
                 alerts_channel_id: Optional[str] = None,
                 db=None):
        self.webhook_url   = webhook_url
        self.bot_token     = bot_token
        self.db            = db

        # Each channel can be overridden via env var for ops flexibility.
        # Falls back to hardcoded constants if env var is not set.
        self.channel_id           = (channel_id
                                     or os.getenv("MG_CHANNEL_MAIN")
                                     or self.CHANNEL_ID)
        self.scans_channel_id     = os.getenv("MG_CHANNEL_SCANS")     or self.SCANS_CHANNEL_ID
        self.ai_channel_id        = os.getenv("MG_CHANNEL_AI")        or self.AI_CHANNEL_ID
        self.approvals_channel_id = os.getenv("MG_CHANNEL_APPROVALS") or self.APPROVALS_CHANNEL_ID
        self.alerts_channel_id    = (alerts_channel_id
                                     or os.getenv("MG_CHANNEL_ALERTS")
                                     or self.ALERTS_CHANNEL_ID)
        self.logs_channel_id      = os.getenv("MG_CHANNEL_LOGS")      or self.LOGS_CHANNEL_ID
        self.critical_channel_id  = os.getenv("MG_CHANNEL_CRITICAL")  or self.CRITICAL_CHANNEL_ID

    def post_to_channel(self, message: str, channel_id: Optional[str] = None) -> str:
        """Post a plain message to a channel. Defaults to the main channel.

        Pass channel_id to override (e.g. self.alerts_channel_id for feed posts).
        Webhook fallback only sends to whatever channel the webhook is configured
        for — bot token path is required for routing.
        """
        target = channel_id or self.channel_id
        try:
            if self.bot_token:
                from slack_sdk import WebClient
                resp = WebClient(token=self.bot_token).chat_postMessage(
                    channel=target, text=message
                )
                return resp.get("ts", "")
            elif self.webhook_url:
                requests.post(self.webhook_url, json={"text": message}, timeout=10)
                return ""
        except Exception as e:
            logger.warning("post_to_channel failed: %s", e)
        return ""

    def post_to_alerts_channel(self, message: str) -> str:
        """Post to the #mining-guardian-alerts channel.

        Critical alerts only — firmware regressions, ticket creation, dead
        board escalations, fleet emergencies. Anything operators need to see
        ASAP and that warrants a notification ping.
        """
        return self.post_to_channel(message, channel_id=self.alerts_channel_id)


    def post_to_critical_channel(self, message: str) -> str:
        """Post to the #mg-critical channel.

        Wake-up level alerts only — physical inspection required, hardware
        failures confirmed, offline after PDU cycle, dead board escalation.
        This is the highest priority channel that should interrupt the operator.
        """
        return self.post_to_channel(message, channel_id=self.critical_channel_id)
    # ── New category-specific helpers (Apr 8 2026 channel split) ──────────

    def post_to_scans(self, message: str) -> str:
        """Post to #mg-scans — hourly fleet scan summaries (the routine feed)."""
        return self.post_to_channel(message, channel_id=self.scans_channel_id)

    def post_to_ai_reports(self, message: str) -> str:
        """Post to #mg-ai-reports — LLM analysis output, post-scan AI interpretations."""
        return self.post_to_channel(message, channel_id=self.ai_channel_id)

    def post_to_approvals(self, message: str) -> str:
        """Post to #mg-approvals — pending approval requests requiring operator decision."""
        return self.post_to_channel(message, channel_id=self.approvals_channel_id)

    def post_to_logs(self, message: str) -> str:
        """Post to #mg-logs — pre/post log comparisons, dual-model verdicts, manual upload analyses."""
        return self.post_to_channel(message, channel_id=self.logs_channel_id)

    def post_blocks_to_channel(self, blocks: list, fallback_text: str = "Mining Guardian update",
                                channel_id: Optional[str] = None) -> str:
        """Post a Block Kit message. Defaults to the main channel.

        Pass channel_id to override (e.g. self.alerts_channel_id for feed posts).
        Outbound-only (chat.postMessage). Works on the VPS today and on the
        production Mac Mini after May 5 — no public ingress required.

        Block Kit messages need a bot token (webhooks do not reliably render
        rich blocks). Falls back to plain text via post_to_channel if bot
        token is not configured. Interactive button click handling is routed
        through the Slack approval listener → localhost approval API, NOT through
        any URL handler that would require public ingress.
        """
        target = channel_id or self.channel_id
        if not self.bot_token:
            logger.warning("post_blocks_to_channel: no bot token, falling back to plain text")
            return self.post_to_channel(fallback_text, channel_id=target)
        try:
            from slack_sdk import WebClient
            resp = WebClient(token=self.bot_token).chat_postMessage(
                channel=target,
                blocks=blocks,
                text=fallback_text,  # required for notifications and accessibility
            )
            return resp.get("ts", "")
        except Exception as e:
            logger.warning("post_blocks_to_channel failed: %s", e)
            return ""

    def get_user_display_name(self, slack_user_id: str) -> Optional[str]:
        """Look up a Slack user's display name from their user ID.

        Requires a Slack bot token with users:read scope.
        Used to log the real name of whoever approved or denied an action.
        """
        if not self.bot_token:
            logger.warning("No Slack bot token configured — cannot look up user name")
            return None
        try:
            resp = requests.get(
                "https://slack.com/api/users.info",
                headers={"Authorization": f"Bearer {self.bot_token}"},
                params={"user": slack_user_id},
                timeout=5,
            )
            data = resp.json()
            if data.get("ok"):
                profile = data["user"].get("profile", {})
                return profile.get("display_name") or profile.get("real_name")
        except Exception as e:
            logger.warning("Slack user lookup failed: %s", e)
        return None

    def send_ams_down(self, miners: List[Dict], wx: Optional[Dict] = None,
                      hvac=None) -> None:
        """Send a simple AMS-is-down message with just weather and mechanical data."""
        if not self.webhook_url:
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [
            f"*🤖 Mining Guardian — {now}*",
            f"🔴 *AMS is offline* — all {len(miners)} miners reporting offline.",
            "Miner analysis suspended until AMS comes back online.",
        ]

        if wx:
            lines.append(
                f"\n🌡️ Outside: *{wx['temp_f']}°F* | Humidity: *{wx['humidity_pct']}%* | "
                f"Feels like: {wx['feels_like_f']}°F | Today: {wx['temp_low_f']}–{wx['temp_high_f']}°F"
            )

        if hvac is not None:
            sup = f"{hvac.supply_temp_f:.1f}°F" if hvac.supply_temp_f is not None else "N/A"
            ret = f"{hvac.return_temp_f:.1f}°F" if hvac.return_temp_f is not None else "N/A"
            dlt = f"{hvac.delta_t_f:+.1f}°F"   if hvac.delta_t_f     is not None else "N/A"
            dp  = f"{hvac.diff_pressure_psi:.1f} PSI" if hvac.diff_pressure_psi is not None else "N/A"
            pump = "🟢 ON" if hvac.spray_pump_on else "🔴 OFF"
            cwp1 = f"{hvac.cwp1_vfd_pct:.0f}%" if hvac.cwp1_vfd_pct is not None else "?"
            cwp2 = f"{hvac.cwp2_vfd_pct:.0f}%" if hvac.cwp2_vfd_pct is not None else "?"
            ct1  = f"{hvac.ct1_vfd_pct:.0f}%"  if hvac.ct1_vfd_pct  is not None else "?"
            ct2  = f"{hvac.ct2_vfd_pct:.0f}%"  if hvac.ct2_vfd_pct  is not None else "?"

            lines.append(f"\n*🏭 Warehouse Mechanical*")
            lines.append(f"  Supply: *{sup}* | Return: *{ret}* | ΔT: *{dlt}* | Diff Press: *{dp}*")
            lines.append(f"  Spray Pump: {pump} | CW Pump 1: {cwp1} | CW Pump 2: {cwp2}")
            lines.append(f"  CT Fan 1: {ct1} | CT Fan 2: {ct2}")

            alarms = []
            if hvac.leak_alarm:       alarms.append("🔴 LEAK DETECTED")
            if hvac.tower_vibration:  alarms.append("🔴 TOWER VIBRATION")
            if hvac.ct1_fault:        alarms.append("🔴 CT Fan 1 FAULT")
            if hvac.ct2_fault:        alarms.append("🔴 CT Fan 2 FAULT")
            if hvac.pump_fault:       alarms.append("🔴 Spray Pump FAULT")

            if alarms:
                lines.append(f"  ⚠️ *ALARMS:* {' | '.join(alarms)}")
            else:
                lines.append("  ✅ All alarms clear")

        payload = {"text": "\n".join(lines)}
        try:
            if self.bot_token:
                from slack_sdk import WebClient
                client = WebClient(token=self.bot_token)
                # AMS-down notifications go to the #mining-guardian-alerts feed
                # channel, NOT the main channel. They are read-only status alerts
                # that don't require operator interaction (no approval, no
                # button click, no thread reply needed).
                client.chat_postMessage(channel=self.alerts_channel_id, text=payload["text"])
            else:
                requests.post(self.webhook_url, json=payload, timeout=10)
            logger.info("AMS-down notification sent to #mining-guardian-alerts")
        except Exception as e:
            logger.warning("Slack AMS-down notification failed: %s", e)

    def send_scan(self, miners: List[Dict], issues: List[Dict],
                  wx: Optional[Dict] = None,
                  ams_notifs: Optional[List[Dict]] = None,
                  hvac=None,
                  hvac_s19jpro=None) -> None:
        """POST a formatted scan summary to Slack via incoming webhook."""
        if not self.webhook_url:
            logger.debug("Slack webhook not configured — skipping Slack notification")
            return

        # Quiet hours — no Slack messages 10pm–5am
        # Overnight automation handles that window; Slack noise at night is unwanted
        current_hour = datetime.now().hour
        if current_hour >= 22 or current_hour < 5:
            logger.debug("Quiet hours (10pm–5am) — suppressing Slack scan report")
            return

        now     = datetime.now().strftime("%Y-%m-%d %H:%M")
        online  = sum(1 for m in miners if m.get("status") == "online")
        offline = len(miners) - online

        pdu_cycles   = [i for i in issues if i["action"] == "PDU_CYCLE"]
        fw_restarts  = [i for i in issues if i["action"] == "RESTART"]
        phys_cycles  = [i for i in issues if i["action"] == "PHYSICAL_CYCLE"]
        monitors     = [i for i in issues if i["action"] == "MONITOR"]
        temp_action  = [i for i in issues if i["action"] == "TEMP_ACTION_REQUIRED"]

        # Header
        if not issues:
            status_line = "✅ All miners operating normally."
        else:
            status_line = f"⚠️ {len(issues)} miner(s) need attention."

        lines = [
            f"*🤖 Mining Guardian Scan — {now}*",
            f"Fleet: *{len(miners)} miners* | 🟢 {online} online | 🔴 {offline} offline",
        ]

        # Add weather line if available
        if wx:
            lines.append(
                f"🌡️ Outside: *{wx['temp_f']}°F* | Humidity: *{wx['humidity_pct']}%* | "
                f"Feels like: {wx['feels_like_f']}°F | Today: {wx['temp_low_f']}–{wx['temp_high_f']}°F"
            )

        # HVAC / warehouse mechanical section
        if hvac is not None:
            sup = f"{hvac.supply_temp_f:.1f}°F" if hvac.supply_temp_f is not None else "N/A"
            ret = f"{hvac.return_temp_f:.1f}°F" if hvac.return_temp_f is not None else "N/A"
            dlt = f"{hvac.delta_t_f:+.1f}°F"   if hvac.delta_t_f     is not None else "N/A"
            dp  = f"{hvac.diff_pressure_psi:.1f} PSI" if hvac.diff_pressure_psi is not None else "N/A"
            pump = "🟢 ON" if hvac.spray_pump_on else "🔴 OFF"
            cwp1 = f"{hvac.cwp1_vfd_pct:.0f}%" if hvac.cwp1_vfd_pct is not None else "?"
            cwp2 = f"{hvac.cwp2_vfd_pct:.0f}%" if hvac.cwp2_vfd_pct is not None else "?"
            ct1  = f"{hvac.ct1_vfd_pct:.0f}%"  if hvac.ct1_vfd_pct  is not None else "?"
            ct2  = f"{hvac.ct2_vfd_pct:.0f}%"  if hvac.ct2_vfd_pct  is not None else "?"

            hvac_lines = [
                f"\n*🏭 Warehouse Mechanical*",
                f"  Supply: *{sup}* | Return: *{ret}* | ΔT: *{dlt}* | Diff Press: *{dp}*",
                f"  Spray Pump: {pump} | CW Pump 1: {cwp1} | CW Pump 2: {cwp2}",
                f"  CT Fan 1: {ct1} | CT Fan 2: {ct2}",
            ]

            # Alarms
            alarms = []
            if hvac.leak_alarm:       alarms.append("🔴 LEAK DETECTED")
            if hvac.tower_vibration:  alarms.append("🔴 TOWER VIBRATION")
            if hvac.ct1_fault:        alarms.append("🔴 CT Fan 1 FAULT")
            if hvac.ct2_fault:        alarms.append("🔴 CT Fan 2 FAULT")
            if hvac.pump_fault:       alarms.append("🔴 Spray Pump FAULT")

            if alarms:
                hvac_lines.append(f"  ⚠️ *ALARMS:* {' | '.join(alarms)}")
            else:
                hvac_lines.append("  ✅ All alarms clear")

            # Feature 5: Add facility stress level to HVAC section
            try:
                from hvac_correlator import get_facility_stress_level
                stress, stress_reasons = get_facility_stress_level()
                if stress >= 51:
                    hvac_lines.append(
                        f"  🏭 *FACILITY STRESS: {stress}%* — "
                        f"{', '.join(stress_reasons[:2])}. "
                        f"Fleet flags may be facility-caused."
                    )
                elif stress >= 26:
                    hvac_lines.append(
                        f"  🏭 Facility watch: {stress}% — {', '.join(stress_reasons[:1])}"
                    )
            except Exception:
                pass

            lines.extend(hvac_lines)

        # S19J Pro Container HVAC (separate system for S19J Pros)
        if hvac_s19jpro is not None:
            s19_lines = [f"\n*🏭 S19J Pro Container*"]
            
            sup = f"{hvac_s19jpro.supply_temp_f:.1f}°F" if hvac_s19jpro.supply_temp_f is not None else "N/A"
            ret = f"{hvac_s19jpro.return_temp_f:.1f}°F" if hvac_s19jpro.return_temp_f is not None else "N/A"
            dlt = f"{hvac_s19jpro.delta_t_f:+.1f}°F" if hvac_s19jpro.delta_t_f is not None else "N/A"
            
            s19_lines.append(f"  Supply: *{sup}* | Return: *{ret}* | ΔT: *{dlt}*")
            
            # S19J Pro container has simpler controls - no CT fans shown (manually at 100%)
            pump = "🟢 ON" if getattr(hvac_s19jpro, 'spray_pump_on', False) else "🔴 OFF"
            cwp1 = f"{hvac_s19jpro.cwp1_vfd_pct:.0f}%" if getattr(hvac_s19jpro, 'cwp1_vfd_pct', None) is not None else "?"
            cwp2 = f"{hvac_s19jpro.cwp2_vfd_pct:.0f}%" if getattr(hvac_s19jpro, 'cwp2_vfd_pct', None) is not None else "?"
            
            s19_lines.append(f"  Spray Pump: {pump} | CW Pump 1: {cwp1} | CW Pump 2: {cwp2}")
            s19_lines.append("  CT Fan 1: 100% | CT Fan 2: 100% (manual)")
            
            # Check alarms
            alarms = []
            if getattr(hvac_s19jpro, 'leak_alarm', False):
                alarms.append("🔴 LEAK DETECTED")
            if getattr(hvac_s19jpro, 'pump_fault', False):
                alarms.append("🔴 Pump FAULT")
            
            if alarms:
                s19_lines.append(f"  ⚠️ *ALARMS:* {' | '.join(alarms)}")
            else:
                s19_lines.append("  ✅ All alarms clear")
            
            lines.extend(s19_lines)

        lines.append(status_line)

        if pdu_cycles:
            lines.append(f"\n*🔴 PDU Power Cycle Recommended ({len(pdu_cycles)} miners)*")
            for i in pdu_cycles:
                location = i.get("map_location", "—")
                lines.append(f"  • `{i['ip']}` {i['model']} — {i.get('pdu_action', 'No PDU info')} | Location: {location}")
            lines.append("  _After power cycle: logs collected on boot, elevated monitoring for 3hrs._")

        if fw_restarts:
            # Split into: has known dead boards (info only) vs approvable
            dead_board_miners = set()
            try:
                db_tmp = GuardianDB()
                with db_tmp._connect() as conn:
                    rows = conn.execute(
                        "SELECT miner_id FROM known_dead_boards WHERE resolved_at IS NULL"
                    ).fetchall()
                    dead_board_miners = {str(r["miner_id"]) for r in rows}
            except Exception:
                pass

            approvable = [i for i in fw_restarts if str(i["id"]) not in dead_board_miners]
            dead_mixed = [i for i in fw_restarts if str(i["id"]) in dead_board_miners]

            from collections import defaultdict
            # Load confidence scorer once for the whole report
            try:
                from ai.confidence_scorer import get_confidence, get_gate
                _has_confidence = True
            except ImportError:
                _has_confidence = False

            if approvable:
                by_model: dict = defaultdict(list)
                for i in approvable:
                    by_model[i["model"]].append(i)
                lines.append(f"\n*🔴 Firmware Restart Recommended ({len(approvable)} miners)*")
                for model, group in by_model.items():
                    if len(group) == 1:
                        i = group[0]
                        conf_str = ""
                        if _has_confidence:
                            try:
                                score, _ = get_confidence(str(i["id"]), i["ip"], "RESTART",
                                                          hashrate_pct=i.get("hashrate_pct"))
                                gate = get_gate(score)
                                gate_emoji = "🟢" if gate == "AUTO" else "🟡" if gate == "ASK" else "🔴"
                                conf_str = f" {gate_emoji} Conf: {score}%"
                            except Exception:
                                pass
                        lines.append(f"  • `{i['ip']}` {model} — HR: {i['hashrate_pct']} | Temp: {i['temp_chip']}{conf_str}")
                    else:
                        ips = ", ".join(f"`{i['ip']}`" for i in group)
                        issue_str = " | ".join(set(" | ".join(i["issues"]) for i in group))
                        lines.append(f"  • *{len(group)}x {model}:* {ips}")
                        lines.append(f"    _{issue_str}_")

            if dead_mixed:
                lines.append(f"\n*🔴 Known Dead Boards — Physical Inspection Required ({len(dead_mixed)} miners)*")
                lines.append("  ⚠️ Restart already attempted — software cannot fix this.")
                for i in dead_mixed:
                    lines.append(f"  • `{i['ip']}` {i['model']} — needs physical board inspection")

        # One-time notice for miners whose AMS ticket was just created this cycle
        try:
            db = GuardianDB()
            newly_ticketed = db.get_newly_ticketed()
            if newly_ticketed:
                lines.append(f"\n*🎫 AMS Tickets Created ({len(newly_ticketed)})*")
                for t in newly_ticketed:
                    lines.append(f"  • `{t['ip']}` ({t['model']}) — ticket #{t['ticket_created']} created, removed from future reports")
                lines.append("  _These miners will no longer appear in scan reports until resolved._")
                # Mark as noticed so this block never shows again for these miners
                db.mark_ticket_noticed([t['miner_id'] for t in newly_ticketed])
        except Exception:
            pass

        if phys_cycles:
            from collections import defaultdict
            by_model2: dict = defaultdict(list)
            for i in phys_cycles:
                by_model2[i["model"]].append(i)
            lines.append(f"\n*🔴 Physical Power Cycle Required ({len(phys_cycles)} miners)*")
            lines.append("  ⚠️ No PDU assigned — must be done manually at the facility.")
            for model, group in by_model2.items():
                ips = ", ".join(f"`{i['ip']}`" for i in group)
                lines.append(f"  • *{len(group)}x {model}:* {ips}")

        if temp_action:
            lines.append(f"\n*🔴 High Temp — Action Required ({len(temp_action)} miners)*")
            for i in temp_action:
                lines.append(f"  • `{i['ip']}` {i['model']} — {i['temp_chip']}")
            lines.append("  Options: [1] Restart  [2] Lower power  [3] Raise cooling")

        if monitors:
            pass  # Yellow temp miners logged to DB for learning — not shown in Slack

        if issues:
            actionable_count = sum(1 for i in issues if i["action"] in ("PDU_CYCLE","RESTART","RESTART_CHECK_BOARDS"))
            if actionable_count > 0:
                lines.append(f"\n_⬇️ *{actionable_count} action(s) pending* — reply in thread to approve._")

        # AMS notifications section — exclude miners already flagged in main report
        if ams_notifs:
            from collections import defaultdict
            key_labels = {
                "consumptionChangeLevel": "Power consumption change",
                "hotBoard":               "Hashboard overheating",
                "workerOffline":          "Miner went offline",
                "workerOnline":           "Miner came back online",
                "hashrateDropped":        "Hashrate dropped",
                "highTemp":               "High temperature",
                "lowHashrate":            "Low hashrate",
            }
            # Suppress ticketed miners from AMS alerts section too
            ticketed_ips = set()
            try:
                with self.db._connect() as _conn:
                    ticketed_ips = {
                        r["ip"] for r in _conn.execute(
                            "SELECT ip FROM known_dead_boards WHERE resolved_at IS NULL"
                        ).fetchall()
                    }
            except Exception:
                pass

            # IPs already covered in the main report or ticketed
            flagged_ips = {i["ip"] for i in issues} | ticketed_ips

            critical = [n for n in ams_notifs
                        if n.get("params", {}).get("alertLevel") == "Critical"
                        and n.get("params", {}).get("minerIp") not in flagged_ips]
            warnings = [n for n in ams_notifs
                        if n.get("params", {}).get("alertLevel") == "Warning"
                        and n.get("params", {}).get("minerIp") not in flagged_ips]

            if False and (critical or warnings):  # AMS alerts stored in DB, suppressed from Slack
                lines.append(f"\n*⚠️ Additional AMS Alerts*")
                if critical:
                    by_key: dict = defaultdict(list)
                    for n in critical:
                        by_key[n.get("key", "unknown")].append(n.get("params", {}).get("minerIp", "unknown"))
                    lines.append(f"  🔴 Critical ({len(critical)})")
                    for key, ips in by_key.items():
                        label = key_labels.get(key, key)
                        ip_list = ", ".join(f"`{ip}`" for ip in ips)
                        lines.append(f"    • *{label}:* {ip_list}")
                if warnings:
                    by_key2: dict = defaultdict(list)
                    for n in warnings:
                        by_key2[n.get("key", "unknown")].append(n.get("params", {}).get("minerIp", "unknown"))
                    lines.append(f"  🟡 Warning ({len(warnings)})")
                    for key, ips in by_key2.items():
                        label = key_labels.get(key, key)
                        # Just show count for noisy alerts, IPs for actionable ones
                        if key in ("workerOnline", "workerOffline", "consumptionChangeLevel"):
                            lines.append(f"    • *{label}:* {len(ips)} miners")
                        else:
                            ip_list = ", ".join(f"`{ip}`" for ip in ips)
                            lines.append(f"    • *{label}:* {ip_list}")

        payload = {"text": "\n".join(lines)}

        thread_ts = None
        try:
            if self.bot_token:
                from slack_sdk import WebClient
                client = WebClient(token=self.bot_token)
                resp   = client.chat_postMessage(
                    channel=self.scans_channel_id,
                    text="\n".join(lines)
                )
                thread_ts = resp["ts"]
                logger.info("Slack notified — scan posted (ts=%s)", thread_ts)

                # Post per-miner interactive Block Kit selection message in thread
                actionable = [i for i in issues if i["action"] in ("PDU_CYCLE","RESTART","RESTART_CHECK_BOARDS")]
                # Skip approval notifications when 24/7 auto-approve is active
                auto_approve = os.getenv("OVERNIGHT_AUTO_APPROVE", "false").lower() == "true"
                auto_low_risk = os.getenv("AUTO_APPROVE_LOW_RISK", "false").lower() == "true"
                if actionable and not (auto_approve and auto_low_risk):
                    self._post_miner_selection(client, thread_ts, actionable)
            else:
                resp = requests.post(self.webhook_url, json=payload, timeout=10)
                if resp.status_code == 200:
                    logger.info("Slack notified — scan summary posted to #mining-guardian")
                else:
                    logger.warning("Slack webhook returned %s: %s",
                                   resp.status_code, resp.text)
        except Exception as exc:
            logger.warning("Slack notification failed: %s", exc)

        return thread_ts

    def _post_miner_selection(self, client, thread_ts: str, actionable: list) -> None:
        """Post a rich Block Kit approval card in the thread.

        Uses display-only blocks (no buttons/checkboxes that need Socket Mode).
        We use polling instead of Bolt/Socket Mode, so interactive elements
        are presented as visual Block Kit cards with ☐ checkboxes plus
        text-reply approval that the listener detects.
        """
        ACTION_ICONS  = {"RESTART": "🔄", "PDU_CYCLE": "🔌", "RESTART_CHECK_BOARDS": "🔴"}
        ACTION_LABELS = {"RESTART": "Firmware Restart", "PDU_CYCLE": "PDU Power Cycle",
                         "RESTART_CHECK_BOARDS": "Dead Board Restart"}

        blocks = []

        # ── Header ────────────────────────────────────────────────────────
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"⬇️  {len(actionable)} Action{'s' if len(actionable) > 1 else ''} Pending Approval",
                "emoji": True
            }
        })
        blocks.append({"type": "divider"})

        # ── One section block per miner ───────────────────────────────────
        for idx, issue in enumerate(actionable, 1):
            icon  = ACTION_ICONS.get(issue["action"], "⚡")
            label = ACTION_LABELS.get(issue["action"], issue["action"])
            loc   = issue.get("map_location") or "—"
            hr    = issue.get("hashrate_pct", "?")
            temp  = issue.get("temp_chip", "?")
            model = issue.get("model", "?")
            ip    = issue["ip"]

            # Determine temp color indicator
            try:
                t = float(temp)
                temp_icon = "🔴" if t >= 84 else "🟢"
            except (TypeError, ValueError):
                temp_icon = "⚪"

            # Get confidence score for this action
            conf_str = ""
            try:
                from ai.confidence_scorer import get_confidence, get_gate
                score, _ = get_confidence(str(issue.get("id", "")), ip, issue["action"],
                                          hashrate_pct=hr if hr != "?" else None)
                gate = get_gate(score)
                gate_emoji = "🟢" if gate == "AUTO" else "🟡" if gate == "ASK" else "🔴"
                conf_str = f"  |  {gate_emoji} Conf: *{score}%*"
            except Exception:
                pass

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{idx}.* ☐  {icon} `{ip}` — *{label}*\n"
                        f"      {model}  |  📍 {loc}  |  ⚡ HR: *{hr}%*  |  {temp_icon} Temp: *{temp}°C*{conf_str}"
                    )
                }
            })

        # ── Divider + approval instructions ──────────────────────────────
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Reply in this thread to approve:*\n"
                    "`APPROVE` — approve all  •  `DENY` — deny all\n"
                    "`approve 1,3` — by number  •  `approve .36,.46` — by IP"
                )
            }
        })
        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": "☑ = approved  •  Approved actions execute immediately via AMS"
            }]
        })

        try:
            client.chat_postMessage(
                channel=self.channel_id,
                thread_ts=thread_ts,
                text=f"{len(actionable)} action(s) pending — reply to approve",  # fallback
                blocks=blocks
            )
            logger.info("Posted Block Kit approval card (%d miners) thread=%s",
                        len(actionable), thread_ts)
        except Exception as e:
            logger.warning("Block Kit card failed, falling back to plain text: %s", e)
            # Plain text fallback
            lines = [f"*{len(actionable)} action(s) pending — reply to approve:*",
                     "_`APPROVE` all | `DENY` all | `approve 1,3` | `approve .36,.46`_", ""]
            for idx, issue in enumerate(actionable, 1):
                icon  = ACTION_ICONS.get(issue["action"], "⚡")
                label = ACTION_LABELS.get(issue["action"], issue["action"])
                lines.append(
                    f"*{idx}.* {icon} `{issue['ip']}` — {issue['model']}\n"
                    f"    {label} | {issue.get('map_location','—')} | HR: {issue.get('hashrate_pct','?')}% | {issue.get('temp_chip','?')}°C"
                )
            try:
                client.chat_postMessage(
                    channel=self.channel_id,
                    thread_ts=thread_ts,
                    text="\n".join(lines)
                )
            except Exception as e2:
                logger.warning("Fallback plain text also failed: %s", e2)


