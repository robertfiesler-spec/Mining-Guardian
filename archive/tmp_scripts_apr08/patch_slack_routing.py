"""Patch core/mining_guardian.py and ai/llm_scan_hook.py for 6-channel routing.

Adds 5 new channel constants + 5 new helper methods to SlackNotifier, then
updates 13 call sites across both files to use the right helper.

Channels (with env var overrides):
  MG_CHANNEL_MAIN      -> #mining-guardian        (operator chat)
  MG_CHANNEL_SCANS     -> #mg-scans               (hourly fleet scans)
  MG_CHANNEL_AI        -> #mg-ai-reports          (LLM analyses)
  MG_CHANNEL_APPROVALS -> #mg-approvals           (pending approval requests)
  MG_CHANNEL_ALERTS    -> #mining-guardian-alerts (existing, repurposed for critical alerts)
  MG_CHANNEL_LOGS      -> #mg-logs                (pre/post log comparisons)
"""
from pathlib import Path

REPO = Path("/Users/BigBobby/Documents/GitHub/Mining Gaurdian")
MG = REPO / "core" / "mining_guardian.py"
HOOK = REPO / "ai" / "llm_scan_hook.py"

# ─── PART 1: SlackNotifier class — add new constants + helpers ────────────

mg_src = MG.read_text()

OLD_CLASS_HEAD = '''class SlackNotifier:

    # Main channel — approvals, dead-board escalations, OpenClaw conversations,
    # interactive operator messages
    CHANNEL_ID = "C0AQ8SE1448"  # #mining-guardian
    # Alerts feed channel — periodic scan summaries, AMS-down notifications,
    # automated status updates that don't need operator interaction
    ALERTS_CHANNEL_ID = "C0ARJP300J0"  # #mining-guardian-alerts

    def __init__(self, webhook_url: Optional[str], channel_id: Optional[str] = None,
                 bot_token: Optional[str] = None,
                 alerts_channel_id: Optional[str] = None):
        self.webhook_url        = webhook_url
        self.channel_id         = channel_id or self.CHANNEL_ID
        self.alerts_channel_id  = alerts_channel_id or self.ALERTS_CHANNEL_ID
        self.bot_token          = bot_token'''

NEW_CLASS_HEAD = '''class SlackNotifier:

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
    # Pre/post log comparisons + dual-model verdicts + manual upload analyses
    LOGS_CHANNEL_ID    = "C0ASH2CPHBJ"  # #mg-logs

    def __init__(self, webhook_url: Optional[str], channel_id: Optional[str] = None,
                 bot_token: Optional[str] = None,
                 alerts_channel_id: Optional[str] = None):
        self.webhook_url   = webhook_url
        self.bot_token     = bot_token

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
        self.logs_channel_id      = os.getenv("MG_CHANNEL_LOGS")      or self.LOGS_CHANNEL_ID'''

assert OLD_CLASS_HEAD in mg_src, "SlackNotifier class head not found verbatim"
mg_src = mg_src.replace(OLD_CLASS_HEAD, NEW_CLASS_HEAD)

# ─── PART 2: Add new helper methods after post_to_alerts_channel ──────────

OLD_ALERTS_HELPER = '''    def post_to_alerts_channel(self, message: str) -> str:
        """Post to the #mining-guardian-alerts feed channel.

        Use this for periodic scan summaries, AMS-down notifications, and other
        automated status updates that don't need operator interaction. Approval
        requests, dead-board escalations, and OpenClaw conversations stay in
        the main channel via the regular post_to_channel call.
        """
        return self.post_to_channel(message, channel_id=self.alerts_channel_id)'''

NEW_ALERTS_HELPER = '''    def post_to_alerts_channel(self, message: str) -> str:
        """Post to the #mining-guardian-alerts channel.

        Critical alerts only — firmware regressions, ticket creation, dead
        board escalations, fleet emergencies. Anything operators need to see
        ASAP and that warrants a notification ping.
        """
        return self.post_to_channel(message, channel_id=self.alerts_channel_id)

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
        return self.post_to_channel(message, channel_id=self.logs_channel_id)'''

assert OLD_ALERTS_HELPER in mg_src, "post_to_alerts_channel block not found"
mg_src = mg_src.replace(OLD_ALERTS_HELPER, NEW_ALERTS_HELPER)

# ─── PART 3: Update call sites in mining_guardian.py ──────────────────────

# Note: Each replacement is uniquely scoped using surrounding context lines
# so we don't accidentally replace the wrong instance of post_to_channel.

# Line 4025 — dead board recovery → mg-alerts
old = '''                notes=f"All boards recovered. Pre/post logs saved. Recovered: {recovered_idx}"
            )
            try:
                self.slack.post_to_channel(msg)'''
new = '''                notes=f"All boards recovered. Pre/post logs saved. Recovered: {recovered_idx}"
            )
            try:
                self.slack.post_to_alerts_channel(msg)'''
assert old in mg_src, "dead board recovery (line ~4025) not found"
mg_src = mg_src.replace(old, new)

# Line 4045 — partial recovery → mg-alerts
old = '''                notes=f"Partial recovery. Recovered: {recovered_idx}. Still dead: {still_dead_idx}"
            )
            try:
                self.slack.post_to_channel(msg)'''
new = '''                notes=f"Partial recovery. Recovered: {recovered_idx}. Still dead: {still_dead_idx}"
            )
            try:
                self.slack.post_to_alerts_channel(msg)'''
assert old in mg_src, "partial recovery (line ~4045) not found"
mg_src = mg_src.replace(old, new)

# Line 4210 — auto-ticket → mg-alerts
old = '''                # Slack notification
                try:
                    self.slack.post_to_channel(
                        f"🎫 *Auto-ticket created: #{ticket_id}*\\n"'''
new = '''                # Slack notification
                try:
                    self.slack.post_to_alerts_channel(
                        f"🎫 *Auto-ticket created: #{ticket_id}*\\n"'''
assert old in mg_src, "auto-ticket (line ~4210) not found"
mg_src = mg_src.replace(old, new)

# Line 4283 — physical inspection → mg-alerts
old = '''            f"Physical inspection and board replacement needed."
        )
        try:
            self.slack.post_to_channel(slack_msg)'''
new = '''            f"Physical inspection and board replacement needed."
        )
        try:
            self.slack.post_to_alerts_channel(slack_msg)'''
assert old in mg_src, "physical inspection (line ~4283) not found"
mg_src = mg_src.replace(old, new)

# Line 4612 — dual-model log comparison → mg-logs (was mg-alerts)
old = '''                    full_msg = NL.join(msg_parts)
                    self.slack.post_to_alerts_channel(full_msg)
                    logger.info("[%s] Dual-model comparison posted to #mining-guardian-alerts", miner_id)'''
new = '''                    full_msg = NL.join(msg_parts)
                    self.slack.post_to_logs(full_msg)
                    logger.info("[%s] Dual-model comparison posted to #mg-logs", miner_id)'''
assert old in mg_src, "dual-model comparison (line ~4612) not found"
mg_src = mg_src.replace(old, new)

# Line 4797 — offline after PDU cycle → mg-alerts
old = '''                # Slack alert
                try:
                    self.slack.post_to_channel(
                        f"🔴 *Offline after PDU cycle — physical inspection required*\\n"'''
new = '''                # Slack alert
                try:
                    self.slack.post_to_alerts_channel(
                        f"🔴 *Offline after PDU cycle — physical inspection required*\\n"'''
assert old in mg_src, "offline after PDU cycle (line ~4797) not found"
mg_src = mg_src.replace(old, new)

# Line 5271 — pre-failure prediction approval → mg-approvals
old = '''                                try:
                                    # Post as approval request so you can APPROVE or DENY
                                    msg = format_prediction_alert(pred)
                                    thread = self.slack.post_to_channel(
                                        msg + "\\n\\n_Reply `APPROVE` to execute restart or `DENY` to skip._"'''
new = '''                                try:
                                    # Post as approval request so you can APPROVE or DENY
                                    msg = format_prediction_alert(pred)
                                    thread = self.slack.post_to_approvals(
                                        msg + "\\n\\n_Reply `APPROVE` to execute restart or `DENY` to skip._"'''
assert old in mg_src, "pre-failure prediction approval (line ~5271) not found"
mg_src = mg_src.replace(old, new)

# Line 5332 — POWER_PROFILE_UP approval → mg-approvals
old = '''                                    f"Reason: {reasons_str}\\n\\n"
                                    f"_Reply `APPROVE` to execute or `DENY` to skip._"
                                )
                                thread = self.slack.post_to_channel(msg)'''
new = '''                                    f"Reason: {reasons_str}\\n\\n"
                                    f"_Reply `APPROVE` to execute or `DENY` to skip._"
                                )
                                thread = self.slack.post_to_approvals(msg)'''
assert old in mg_src, "POWER_PROFILE_UP approval (line ~5332) not found"
mg_src = mg_src.replace(old, new)

# Line 5112 — send_scan (hourly summary) — this one's special, send_scan
# is a method on SlackNotifier itself, so we need to change where IT posts.
# Find the actual posting calls inside send_scan and route them to mg-scans.
# Look for the chat_postMessage / requests.post calls inside send_scan body.
# For now, the cleanest fix is to override the channel inside send_scan.
# We'll find the channel=self.channel_id inside send_scan's body and change
# it to channel=self.scans_channel_id.

# send_scan body — find the posting calls
# It's around line 3147, 3244, 3265 from earlier grep
# Let's find them with surrounding context
old = '''                    channel=self.channel_id,
                    text=fallback_text,
                    blocks=blocks,
                    thread_ts=thread_ts'''
# This is for the in-thread reply, leave it on main channel? Actually wait,
# this whole pattern needs more context. Let me handle send_scan separately
# below — it's a method, not a call site, so the routing change is internal.

# Find all 3 chat_postMessage instances inside send_scan and update them to
# use scans_channel_id instead of channel_id. Use unique surrounding lines
# from line 3147, 3244, 3265.

# Easier approach: read the send_scan body, change all instances of
# self.channel_id to self.scans_channel_id WITHIN that method only.
# Find the start and end of send_scan and do a scoped replace.

# Find send_scan definition
import re
send_scan_match = re.search(
    r'(    def send_scan\(self, miners: List\[Dict\], issues: List\[Dict\],.*?)(?=\n    def |\nclass )',
    mg_src,
    re.DOTALL
)
if not send_scan_match:
    raise SystemExit("send_scan method body not found")

send_scan_body = send_scan_match.group(1)
new_send_scan_body = send_scan_body.replace("self.channel_id", "self.scans_channel_id")
mg_src = mg_src.replace(send_scan_body, new_send_scan_body)

# Now write the patched mining_guardian.py
MG.write_text(mg_src)
print(f"PATCHED {MG.name}")

# ─── PART 4: Update llm_scan_hook.py ──────────────────────────────────────

hook_src = HOOK.read_text()

# 1. Post-scan AI analysis -> mg-ai-reports
old = '''        if analysis and slack_client:
            # Post to Slack as the AI's interpretation
            try:
                msg = f":brain: *Mining Guardian AI Analysis — Scan #{scan_id}*\\n{analysis}"
                # Truncate if too long for Slack
                if len(msg) > 3000:
                    msg = msg[:2950] + "\\n_...truncated_"
                slack_client.post_to_channel(msg)'''
new = '''        if analysis and slack_client:
            # Post to Slack as the AI's interpretation -> #mg-ai-reports
            try:
                msg = f":brain: *Mining Guardian AI Analysis — Scan #{scan_id}*\\n{analysis}"
                # Truncate if too long for Slack
                if len(msg) > 3000:
                    msg = msg[:2950] + "\\n_...truncated_"
                slack_client.post_to_ai_reports(msg)'''
assert old in hook_src, "post-scan AI analysis call site not found in hook"
hook_src = hook_src.replace(old, new)

# 2. Restart log analysis -> mg-logs
old = '''        if analysis and slack_client:
            ip = miner_info.get("ip", miner_id)
            model = miner_info.get("model", "?")
            try:
                msg = (
                    f":mag: *Restart Log Analysis — {ip} ({model})*\\n"
                    f"{analysis}"
                )
                if len(msg) > 3000:
                    msg = msg[:2950] + "\\n_...truncated_"
                slack_client.post_to_channel(msg)'''
new = '''        if analysis and slack_client:
            ip = miner_info.get("ip", miner_id)
            model = miner_info.get("model", "?")
            try:
                msg = (
                    f":mag: *Restart Log Analysis — {ip} ({model})*\\n"
                    f"{analysis}"
                )
                if len(msg) > 3000:
                    msg = msg[:2950] + "\\n_...truncated_"
                slack_client.post_to_logs(msg)'''
assert old in hook_src, "restart log analysis call site not found in hook"
hook_src = hook_src.replace(old, new)

# 3. Denial learning -> mg-ai-reports (this is AI learning output)
old = '''        if rule and slack_client:
            try:
                msg = (
                    f":bulb: *AI Learning from Denial*\\n"
                    f"Operator denied {action} on {ip}\\n"
                    f"Reason: _{reason}_\\n\\n"
                    f"*Suggested rule:* {rule}"
                )
                slack_client.post_to_channel(msg)'''
new = '''        if rule and slack_client:
            try:
                msg = (
                    f":bulb: *AI Learning from Denial*\\n"
                    f"Operator denied {action} on {ip}\\n"
                    f"Reason: _{reason}_\\n\\n"
                    f"*Suggested rule:* {rule}"
                )
                slack_client.post_to_ai_reports(msg)'''
assert old in hook_src, "denial learning call site not found in hook"
hook_src = hook_src.replace(old, new)

HOOK.write_text(hook_src)
print(f"PATCHED {HOOK.name}")

print()
print("All patches applied successfully.")
print(f"  {MG}: {len(mg_src)} chars")
print(f"  {HOOK}: {len(hook_src)} chars")
