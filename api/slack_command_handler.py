"""
slack_command_handler.py
Mining Guardian — Slack Command & Question Handler

Listens for messages in #mining-guardian that start with / or @mention the bot.
Handles fleet queries, miner lookups, and forwards questions to the LLM.

Commands:
  /status          — current fleet status
  /miner <ip>      — detailed info on a specific miner
  /hot             — list miners in yellow/red temp zone
  /dead            — list known dead boards
  /knowledge       — what the LLM has learned
  /btc             — current Bitcoin price + daily revenue estimate
  @Mining Guardian  — ask the LLM any mining question

Runs as a systemd service alongside the other listeners.
"""

import sys
import os
import re
import time
import json
import logging
import sqlite3
import requests
from datetime import datetime
from pathlib import Path
from slack_sdk import WebClient
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("slack_commands")

load_dotenv()

_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT / "core"), str(_ROOT / "clients")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
CHANNEL_ID = "C0AQ8SE1448"
DB_PATH = str(_ROOT / "guardian.db")
OLLAMA_URL = "http://localhost:11434/api/generate"
POLL_INTERVAL = 5
BOT_USER_ID = None


class CommandHandler:
    def __init__(self):
        self.client = WebClient(token=SLACK_BOT_TOKEN)
        self.last_ts = str(time.time())
        self.processed = set()
        self._get_bot_id()

    def _get_bot_id(self):
        global BOT_USER_ID
        try:
            resp = self.client.auth_test()
            BOT_USER_ID = resp["user_id"]
            logger.info("Bot user ID: %s", BOT_USER_ID)
        except Exception as e:
            logger.warning("Could not get bot ID: %s", e)

    def _get_db(self):
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _reply(self, channel, thread_ts, text):
        """Post a reply in the channel or thread."""
        try:
            self.client.chat_postMessage(
                channel=channel, thread_ts=thread_ts, text=text)
        except Exception as e:
            logger.error("Reply failed: %s", e)

    def cmd_status(self, channel, thread_ts):
        """Current fleet status from latest scan."""
        conn = self._get_db()
        scan = conn.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1").fetchone()
        if not scan:
            self._reply(channel, thread_ts, "No scan data available.")
            conn.close()
            return
        
        # Get weather
        wx = conn.execute("SELECT * FROM weather_readings ORDER BY id DESC LIMIT 1").fetchone()
        # Get HVAC
        hvac = conn.execute("SELECT * FROM hvac_readings ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()

        lines = [f"*🤖 Fleet Status — {scan['scanned_at'][:16]}*",
                 f"Miners: *{scan['total_miners']}* | 🟢 {scan['online']} online | 🔴 {scan['offline']} offline | ⚠️ {scan['issues']} issues"]
        if wx:
            lines.append(f"🌡️ Outside: *{wx['temp_f']}°F* | Humidity: *{wx['humidity_pct']}%*")
        if hvac:
            lines.append(f"🏭 Supply: *{hvac['supply_temp_f']:.1f}°F* | Return: *{hvac['return_temp_f']:.1f}°F*")
        self._reply(channel, thread_ts, "\n".join(lines))

    def cmd_miner(self, channel, thread_ts, ip_or_id):
        """Detailed info on a specific miner."""
        conn = self._get_db()
        row = conn.execute(
            "SELECT * FROM miner_readings WHERE ip = ? OR miner_id = ? ORDER BY id DESC LIMIT 1",
            (ip_or_id, ip_or_id)).fetchone()
        if not row:
            self._reply(channel, thread_ts, f"Miner `{ip_or_id}` not found in recent scans.")
            conn.close()
            return

        # Count flags
        flags = conn.execute(
            "SELECT COUNT(*) FROM miner_readings WHERE miner_id = ? AND action IS NOT NULL AND action != 'MONITOR'",
            (row['miner_id'],)).fetchone()[0]

        # Check dead boards
        dead = conn.execute(
            "SELECT board_indices FROM known_dead_boards WHERE miner_id = ? AND resolved_at IS NULL",
            (row['miner_id'],)).fetchone()
        conn.close()

        lines = [f"*Miner {row['miner_id']}* ({row['model']}) @ `{row['ip']}`",
                 f"Status: *{row['status']}* | Hashrate: *{row['hashrate_pct']}%* | Temp: *{row['temp_chip']}°C*",
                 f"Profile: {row['current_profile'] or 'unknown'}",
                 f"Firmware: {row['firmware_manufacturer'] or 'unknown'}",
                 f"Times flagged: *{flags}*",
                 f"Location: {row['map_location'] or 'not mapped'}"]
        if dead:
            lines.append(f"🔴 *Known dead boards:* {dead['board_indices']}")
        self._reply(channel, thread_ts, "\n".join(lines))

    def cmd_hot(self, channel, thread_ts):
        """List miners in yellow/red temp zone."""
        conn = self._get_db()
        hot = conn.execute("""
            SELECT miner_id, ip, model, temp_chip FROM miner_readings
            WHERE id IN (SELECT MAX(id) FROM miner_readings GROUP BY miner_id)
            AND temp_chip >= 76 AND status = 'online'
            ORDER BY temp_chip DESC
        """).fetchall()
        conn.close()
        if not hot:
            self._reply(channel, thread_ts, "✅ No miners in yellow or red zone right now.")
            return
        lines = [f"*🌡️ Hot Miners — {len(hot)} above 76°C*"]
        for m in hot:
            zone = "🔴" if m['temp_chip'] >= 86 else "🟡"
            lines.append(f"  {zone} `{m['ip']}` {m['model']} — *{m['temp_chip']}°C*")
        self._reply(channel, thread_ts, "\n".join(lines))

    def cmd_dead(self, channel, thread_ts):
        """List known dead boards."""
        conn = self._get_db()
        dead = conn.execute(
            "SELECT * FROM known_dead_boards WHERE resolved_at IS NULL").fetchall()
        conn.close()
        if not dead:
            self._reply(channel, thread_ts, "✅ No known dead boards.")
            return
        lines = [f"*🔴 Known Dead Boards — {len(dead)} miners*"]
        for d in dead:
            lines.append(f"  • Miner {d['miner_id']} ({d['model']}) @ `{d['ip']}` — Boards: {d['board_indices']}")
        self._reply(channel, thread_ts, "\n".join(lines))

    def cmd_knowledge(self, channel, thread_ts):
        """Show what the LLM has learned."""
        try:
            from knowledge_manager import KnowledgeManager
            km = KnowledgeManager()
            k = km.knowledge
            profiles = k.get("miner_profiles", {})
            chronic = sorted(profiles.items(), key=lambda x: x[1].get("total_flags", 0), reverse=True)[:5]
            patterns = k.get("patterns", [])
            insights = k.get("known_issues", [])[-3:]

            lines = [f"*🧠 LLM Knowledge Summary*",
                     f"Miners tracked: *{len(profiles)}*",
                     f"Patterns learned: *{len(patterns)}*",
                     f"Insights accumulated: *{len(k.get('known_issues', []))}*"]
            if chronic:
                lines.append("\n*Top problem miners:*")
                for mid, p in chronic:
                    lines.append(f"  • Miner {mid} ({p['model']}) — flagged *{p['total_flags']}x*")
            if patterns:
                lines.append("\n*Key patterns:*")
                for p in patterns[:3]:
                    lines.append(f"  • {p[:100]}")
            self._reply(channel, thread_ts, "\n".join(lines))
        except Exception as e:
            self._reply(channel, thread_ts, f"Knowledge unavailable: {e}")

    def cmd_btc(self, channel, thread_ts):
        """Bitcoin price and estimated revenue."""
        try:
            resp = requests.get("https://api.coinbase.com/v2/prices/BTC-USD/spot", timeout=10)
            price = float(resp.json()["data"]["amount"])

            # Estimate fleet hashrate and revenue
            conn = self._get_db()
            scan = conn.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1").fetchone()
            conn.close()

            lines = [f"*₿ Bitcoin: ${price:,.0f}*"]
            if scan and scan['online'] > 0:
                # Rough estimate: S19J Pro fleet avg ~130 TH/s per miner
                est_fleet_ths = scan['online'] * 130
                # Network difficulty-based revenue estimate (very rough)
                daily_btc = (est_fleet_ths / 750_000_000) * 6.25 * 144  # simplified
                daily_usd = daily_btc * price
                lines.append(f"Fleet: ~{est_fleet_ths:,.0f} TH/s ({scan['online']} miners online)")
                lines.append(f"Est. daily: ~{daily_btc:.4f} BTC (~${daily_usd:,.0f})")
            self._reply(channel, thread_ts, "\n".join(lines))
        except Exception as e:
            self._reply(channel, thread_ts, f"BTC price unavailable: {e}")

    def _build_fleet_context(self) -> str:
        """Pull current fleet state to inject into every LLM question."""
        try:
            conn = self._get_db()
            # Latest scan summary
            scan = conn.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1").fetchone()
            # Top 10 most flagged miners with current state
            miners = conn.execute("""
                SELECT r.miner_id, r.ip, r.model, r.status, r.hashrate_pct,
                       r.temp_chip, r.current_profile, r.action, r.firmware_manufacturer,
                       r.map_location,
                       COUNT(h.id) as total_flags
                FROM miner_readings r
                LEFT JOIN miner_readings h ON h.miner_id = r.miner_id
                    AND h.action IS NOT NULL AND h.action != 'MONITOR'
                WHERE r.id IN (SELECT MAX(id) FROM miner_readings GROUP BY miner_id)
                GROUP BY r.miner_id ORDER BY total_flags DESC LIMIT 15
            """).fetchall()
            # Known dead boards
            dead = conn.execute(
                "SELECT miner_id, ip, model, board_indices FROM known_dead_boards WHERE resolved_at IS NULL"
            ).fetchall()
            # Recent audit actions
            recent = conn.execute("""
                SELECT miner_id, ip, action_taken, decision, timestamp
                FROM action_audit_log ORDER BY timestamp DESC LIMIT 10
            """).fetchall()
            # Knowledge patterns
            conn.close()
            lines = ["CURRENT FLEET STATE:"]
            if scan:
                lines.append(f"Latest scan: {scan['total_miners']} miners, "
                             f"{scan['online']} online, {scan['offline']} offline, "
                             f"{scan['issues']} issues")
            lines.append("\nMINER STATUS (most flagged first):")
            for m in miners:
                lines.append(f"  {m['ip']} ({m['model']}) — status:{m['status']} "
                             f"HR:{m['hashrate_pct']}% temp:{m['temp_chip']}°C "
                             f"profile:{m['current_profile']} flags:{m['total_flags']} "
                             f"location:{m['map_location'] or 'unmapped'} "
                             f"action:{m['action'] or 'OK'}")
            if dead:
                lines.append("\nKNOWN DEAD BOARDS:")
                for d in dead:
                    lines.append(f"  {d['ip']} ({d['model']}) — boards {d['board_indices']}")
            if recent:
                lines.append("\nRECENT ACTIONS:")
                for a in recent:
                    lines.append(f"  {a['timestamp'][:16]} {a['ip']} — "
                                f"{a['action_taken']} {a['decision']}")
            try:
                from knowledge_manager import KnowledgeManager
                km = KnowledgeManager()
                patterns = km.knowledge.get("patterns", [])
                if patterns:
                    lines.append("\nLEARNED PATTERNS:")
                    for p in patterns[:5]:
                        lines.append(f"  • {p}")
            except Exception:
                pass
            return "\n".join(lines)
        except Exception as e:
            logger.warning("Could not build fleet context: %s", e)
            return ""

    def _get_miner_deep_history(self, ip_or_id: str) -> str:
        """Pull full history for a specific miner to answer questions about it."""
        try:
            conn = self._get_db()
            # Resolve to miner_id and ip
            row = conn.execute(
                "SELECT miner_id, ip, model FROM miner_readings "
                "WHERE ip=? OR miner_id=? ORDER BY id DESC LIMIT 1",
                (ip_or_id, ip_or_id)
            ).fetchone()
            if not row:
                conn.close()
                return f"No miner found matching '{ip_or_id}'"

            mid   = row["miner_id"]
            ip    = row["ip"]
            model = row["model"]

            # Flag history over time
            flags = conn.execute("""
                SELECT DATE(scanned_at) as day, action, COUNT(*) as cnt,
                       AVG(hashrate_pct) as avg_hr, AVG(temp_chip) as avg_temp
                FROM miner_readings
                WHERE miner_id=? AND action IS NOT NULL AND action!='MONITOR'
                GROUP BY DATE(scanned_at), action
                ORDER BY day DESC LIMIT 14
            """, (mid,)).fetchall()

            # Audit history
            audit = conn.execute("""
                SELECT action_taken, decision, approved_by, timestamp, notes
                FROM action_audit_log WHERE miner_id=?
                ORDER BY timestamp DESC LIMIT 10
            """, (mid,)).fetchall()

            # Dead board history
            dead = conn.execute(
                "SELECT board_indices, first_seen, restart_result, resolved_at "
                "FROM known_dead_boards WHERE miner_id=? ORDER BY first_seen DESC LIMIT 5",
                (mid,)
            ).fetchall()

            # Most recent log snippets
            logs = conn.execute("""
                SELECT health_status, collected_at, content FROM miner_logs
                WHERE miner_id=? ORDER BY id DESC LIMIT 3
            """, (mid,)).fetchall()

            conn.close()

            lines = [f"MINER DEEP HISTORY: {ip} ({model}) ID={mid}"]
            lines.append(f"\nFLAG HISTORY (last 14 days):")
            if flags:
                for f in flags:
                    lines.append(f"  {f['day']}: {f['action']} x{f['cnt']} — "
                                f"avg HR:{f['avg_hr']:.0f}% temp:{f['avg_temp']:.0f}°C")
            else:
                lines.append("  No flags in last 14 days")

            lines.append(f"\nAUDIT TRAIL (last 10 actions):")
            if audit:
                for a in audit:
                    lines.append(f"  {a['timestamp'][:16]}: {a['action_taken']} → "
                                f"{a['decision']} by {a['approved_by'] or 'auto'}")
            else:
                lines.append("  No actions taken yet")

            if dead:
                lines.append(f"\nDEAD BOARD HISTORY:")
                for d in dead:
                    status = "resolved" if d["resolved_at"] else "UNRESOLVED"
                    lines.append(f"  Boards {d['board_indices']} — first seen {d['first_seen'][:10]} "
                                f"— restart result: {d['restart_result'] or 'N/A'} — {status}")

            if logs:
                lines.append(f"\nRECENT LOG SNIPPETS:")
                for log in logs:
                    snippet = log["content"][:300].replace("\n", " ")
                    lines.append(f"  [{log['collected_at'][:16]} {log['health_status']}]: {snippet}")

            return "\n".join(lines)
        except Exception as e:
            return f"Could not retrieve history for {ip_or_id}: {e}"

    def cmd_ask_llm(self, channel, thread_ts, question):
        """
        Intelligent fleet Q&A — automatically pulls relevant context before asking the LLM.

        If question mentions a specific IP or miner, pulls that miner's full history.
        Always includes current fleet state and learned patterns as context.
        Uses Claude API for best answer quality.
        """
        # Sanitize: cap length, strip control characters
        question = question[:500].replace("\x00", "").strip()
        if not question:
            self._reply(channel, thread_ts, "Please ask a question.")
            return

        self._reply(channel, thread_ts, "_🧠 Thinking..._")

        try:
            # Build system context
            fleet_ctx = self._build_fleet_context()

            # Check if question references a specific miner IP
            ip_match = re.search(r'192\.168\.\d+\.(\d+)|\.\d{2,3}\b', question)
            miner_ctx = ""
            if ip_match:
                # Extract the full IP if present, else look up by suffix
                full_ip = re.search(r'192\.168\.\d+\.\d+', question)
                lookup  = full_ip.group(0) if full_ip else ip_match.group(0).lstrip(".")
                miner_ctx = f"\n\n{self._get_miner_deep_history(lookup)}"

            # Build the full prompt
            system = (
                "You are Mining Guardian AI, the fleet intelligence system for BiXBiT USA "
                "in Fort Worth, TX. You have full access to real-time fleet data, miner history, "
                "audit logs, and learned patterns. All cooling is liquid — hydro racks and "
                "immersion tank. No air cooling. Answer the operator's question directly and "
                "specifically using the data provided. Be concise but complete. "
                "If recommending an action, say exactly which miner IPs and what to do."
            )

            prompt = (
                f"{fleet_ctx}"
                f"{miner_ctx}"
                f"\n\nOPERATOR QUESTION: {question}"
                f"\n\nProvide a direct, specific answer using the fleet data above."
            )

            from llm_analyzer import LLMAnalyzer
            analyzer = LLMAnalyzer()

            # Prefer Claude API for conversational questions (faster, smarter)
            import os
            anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
            if anthropic_key:
                resp = requests.post("https://api.anthropic.com/v1/messages", json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 800,
                    "system": system,
                    "messages": [{"role": "user", "content": prompt}]
                }, headers={
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                }, timeout=30)
                answer = resp.json()["content"][0]["text"]
            else:
                # Fallback to local Ollama
                answer, _ = analyzer._query_llm(f"{system}\n\n{prompt}")

            self._reply(channel, thread_ts, f"*🧠 Mining Guardian AI:*\n{answer[:2000]}")

        except Exception as e:
            logger.error("LLM query failed: %s", e)
            self._reply(channel, thread_ts, f"❌ LLM query failed: {e}")

    def cmd_overnight_report(self, channel, thread_ts):
        """Summary of what happened overnight — auto actions, recoveries, failures."""
        conn = self._get_db()
        from datetime import timedelta
        since = (datetime.now() - timedelta(hours=10)).isoformat()
        actions = conn.execute("""
            SELECT miner_id, ip, model, action_taken, decision, approved_by, timestamp
            FROM action_audit_log WHERE timestamp >= ? ORDER BY timestamp
        """, (since,)).fetchall()
        conn.close()
        if not actions:
            self._reply(channel, thread_ts, "No actions taken in the last 10 hours.")
            return
        auto    = [a for a in actions if a["approved_by"] == "Mining Guardian (Overnight Auto)"]
        manual  = [a for a in actions if a["approved_by"] != "Mining Guardian (Overnight Auto)"]
        lines   = [f"*🌙 Overnight Summary (last 10h)*"]
        if auto:
            lines.append(f"\n*Auto-executed ({len(auto)}):*")
            for a in auto:
                lines.append(f"  • `{a['ip']}` — {a['action_taken']} {a['decision']} "
                             f"@ {a['timestamp'][11:16]}")
        if manual:
            lines.append(f"\n*Operator actions ({len(manual)}):*")
            for a in manual:
                lines.append(f"  • `{a['ip']}` — {a['action_taken']} {a['decision']} "
                             f"by {a['approved_by']} @ {a['timestamp'][11:16]}")
        self._reply(channel, thread_ts, "\n".join(lines))

    def cmd_predict(self, channel, thread_ts):
        """Ask the LLM to predict which miners are most likely to fail next."""
        self._reply(channel, thread_ts, "_🔮 Analyzing failure risk patterns..._")
        fleet_ctx = self._build_fleet_context()
        prompt = (
            f"{fleet_ctx}\n\n"
            "Based on the flag history, hashrate trends, temperature patterns, and known issues above, "
            "which 3-5 miners are most likely to need attention in the next 24-48 hours? "
            "For each one explain why — what pattern is concerning. Be specific with IPs."
        )
        self.cmd_ask_llm(channel, thread_ts, prompt)

    def cmd_audit(self, channel, thread_ts):
        """Show recent audit log entries."""
        conn = self._get_db()
        rows = conn.execute("""
            SELECT ip, model, action_taken, decision, approved_by, timestamp
            FROM action_audit_log ORDER BY timestamp DESC LIMIT 10
        """).fetchall()
        conn.close()
        if not rows:
            self._reply(channel, thread_ts, "No audit entries yet.")
            return
        lines = [f"*📋 Recent Actions (last 10)*"]
        for r in rows:
            icon = "✅" if r["decision"] in ("APPROVED","AUTO_OVERNIGHT") else "❌"
            lines.append(f"  {icon} `{r['ip']}` {r['action_taken']} → {r['decision']} "
                        f"by {r['approved_by'] or 'auto'} @ {r['timestamp'][5:16]}")
        self._reply(channel, thread_ts, "\n".join(lines))

    def cmd_help(self, channel, thread_ts):
        """List all available commands."""
        lines = [
            "*🤖 Mining Guardian Commands*",
            "",
            "*Quick commands:*",
            "  `status` — fleet overview",
            "  `hot` — miners running warm",
            "  `dead` — known dead boards",
            "  `btc` — Bitcoin price + revenue",
            "  `knowledge` — what AI has learned",
            "  `audit` — recent actions taken",
            "  `overnight` — what happened overnight",
            "  `predict` — which miners might fail next",
            "  `miner 192.168.188.36` — deep dive on one miner",
            "",
            "*Ask anything:*",
            "  _why does .36 keep failing?_",
            "  _what's wrong with miner .195?_",
            "  _should I lower the profile on .46?_",
            "  _is the high return temp causing issues?_",
            "  _which miners have the worst history this week?_",
        ]
        self._reply(channel, thread_ts, "\n".join(lines))

    def _handle_message(self, msg):
        """Route a message to the right command handler."""
        text = msg.get("text", "").strip()
        channel = msg.get("channel", CHANNEL_ID)
        thread_ts = msg.get("thread_ts", msg.get("ts"))
        user = msg.get("user", "")

        # Ignore bot's own messages
        if user == BOT_USER_ID:
            return

        # Strip bot mention if present
        if BOT_USER_ID:
            text = re.sub(f"<@{BOT_USER_ID}>", "", text).strip()

        lower = text.lower()

        if lower in ("status", "/status", "fleet status"):
            self.cmd_status(channel, thread_ts)
        elif lower.startswith(("miner ", "/miner ")):
            ip_or_id = text.split(None, 1)[1].strip().strip("`")
            self.cmd_miner(channel, thread_ts, ip_or_id)
        elif lower in ("hot", "/hot", "hot miners", "temps"):
            self.cmd_hot(channel, thread_ts)
        elif lower in ("dead", "/dead", "dead boards"):
            self.cmd_dead(channel, thread_ts)
        elif lower in ("knowledge", "/knowledge", "what have you learned"):
            self.cmd_knowledge(channel, thread_ts)
        elif lower in ("btc", "/btc", "bitcoin", "price"):
            self.cmd_btc(channel, thread_ts)
        elif lower.startswith(("history ", "why ", "what's wrong with ", "tell me about ")):
            # Extract IP from the question and ask LLM with full history
            self.cmd_ask_llm(channel, thread_ts, text)
        elif lower in ("overnight", "what happened overnight", "overnight report"):
            self.cmd_overnight_report(channel, thread_ts)
        elif lower in ("predict", "predictions", "who's next", "which miner will fail"):
            self.cmd_predict(channel, thread_ts)
        elif lower in ("audit", "recent actions", "what was done"):
            self.cmd_audit(channel, thread_ts)
        elif lower in ("help", "/help", "commands"):
            self.cmd_help(channel, thread_ts)
        else:
            self.cmd_ask_llm(channel, thread_ts, text)

    def run(self):
        """Main loop — poll for new messages in #mining-guardian."""
        logger.info("Command Handler started — watching #mining-guardian")
        logger.info("Commands: status, miner <ip>, hot, dead, knowledge, btc, or ask anything")

        # Get latest message timestamp as starting point
        try:
            resp = self.client.conversations_history(channel=CHANNEL_ID, limit=1)
            msgs = resp.get("messages", [])
            if msgs:
                self.last_ts = msgs[0]["ts"]
                logger.info("Starting after latest message ts: %s", self.last_ts)
            else:
                self.last_ts = str(time.time())
                logger.info("No messages found, starting from now")
        except Exception as e:
            self.last_ts = str(time.time())
            logger.error("Could not read channel history: %s", e)
            logger.error("Check that bot has groups:history scope for private channels")

        while True:
            try:
                resp = self.client.conversations_history(
                    channel=CHANNEL_ID, oldest=self.last_ts, limit=10)
                messages = resp.get("messages", [])
                if messages:
                    logger.info("Poll returned %d messages (oldest_ts=%s)", len(messages), self.last_ts)

                # Process oldest first
                for msg in sorted(messages, key=lambda m: float(m.get("ts", "0"))):
                    ts = msg.get("ts", "")
                    if ts in self.processed or ts == self.last_ts:
                        continue
                    self.processed.add(ts)
                    self.last_ts = ts

                    # Skip bot messages
                    if msg.get("subtype") or msg.get("bot_id"):
                        continue

                    text = msg.get("text", "").strip()
                    user = msg.get("user", "?")
                    logger.info("Message from %s: '%s'", user, text[:80])
                    self._handle_message(msg)

            except Exception as e:
                logger.error("Poll error: %s", e)

            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    print("=" * 50)
    print("Mining Guardian — Slack Command Handler")
    print("Commands: status | miner <ip> | hot | dead |")
    print("          knowledge | btc | or ask anything")
    print("=" * 50)
    handler = CommandHandler()
    handler.run()
