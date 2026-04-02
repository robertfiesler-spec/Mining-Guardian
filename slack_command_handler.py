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

import os
import re
import time
import json
import logging
import sqlite3
import requests
from datetime import datetime
from slack_sdk import WebClient
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("slack_commands")

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
CHANNEL_ID = "C0AQ8SE1448"
DB_PATH = "guardian.db"
OLLAMA_URL = "http://localhost:11434/api/generate"
POLL_INTERVAL = 5
BOT_USER_ID = None  # populated on startup


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
        conn = sqlite3.connect(DB_PATH)
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

    def cmd_ask_llm(self, channel, thread_ts, question):
        """Forward a question to Ollama LLM with fleet context."""
        try:
            from knowledge_manager import KnowledgeManager
            from llm_analyzer import SYSTEM_PROMPT
            km = KnowledgeManager()
            context = km.build_context_prompt()

            prompt = f"{SYSTEM_PROMPT}\n\n{context}\n\nOperator question: {question}\n\nAnswer concisely."
            resp = requests.post(OLLAMA_URL, json={
                "model": "llama3.1:8b",
                "prompt": prompt,
                "stream": False
            }, timeout=120)
            answer = resp.json().get("response", "No response from LLM")
            self._reply(channel, thread_ts, f"*🧠 Mining Guardian AI:*\n{answer[:2000]}")
        except Exception as e:
            self._reply(channel, thread_ts, f"LLM query failed: {e}")

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
        else:
            # Anything else — send to the LLM as a question
            self.cmd_ask_llm(channel, thread_ts, text)

    def run(self):
        """Main loop — poll for new messages in #mining-guardian."""
        logger.info("Command Handler started — watching #mining-guardian")
        logger.info("Commands: status, miner <ip>, hot, dead, knowledge, btc, or ask anything")

        # Set initial timestamp to NOW so we only process new messages
        self.last_ts = str(time.time())
        logger.info("Starting from timestamp: %s", self.last_ts)

        while True:
            try:
                resp = self.client.conversations_history(
                    channel=CHANNEL_ID, oldest=self.last_ts, limit=10)
                messages = resp.get("messages", [])

                for msg in reversed(messages):  # process oldest first
                    ts = msg.get("ts", "")
                    if ts in self.processed:
                        continue
                    self.processed.add(ts)
                    self.last_ts = ts  # advance past this message

                    # Only respond to human messages (not bot posts)
                    if msg.get("subtype"):
                        continue
                    if msg.get("bot_id"):
                        continue

                    text = msg.get("text", "").strip()
                    logger.info("Received message from %s: %s", msg.get("user", "?"), text[:50])
                    self._handle_message(msg)

            except Exception as e:
                logger.error("Command handler error: %s", e)

            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    print("=" * 50)
    print("Mining Guardian — Slack Command Handler")
    print("Commands: status | miner <ip> | hot | dead |")
    print("          knowledge | btc | or ask anything")
    print("=" * 50)
    handler = CommandHandler()
    handler.run()
