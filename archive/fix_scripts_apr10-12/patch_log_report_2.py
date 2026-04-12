#!/usr/bin/env python3
"""
Add the _send_log_failure_slack_report method to MiningGuardian.
"""

with open("/root/Mining-Gaurdian/core/mining_guardian.py", "r") as f:
    content = f.read()

# Find the marker and insert the new method before collect_logs
marker = '''    # ── Main entry ────────────────────────────────────────────

    def collect_logs(self, miners: List[Dict], issues: List[Dict]) -> None:'''

new_method = '''    def _send_log_failure_slack_report(self, failed_miners: List[Dict]) -> None:
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
            
            message = "\\n".join(lines)
            self.slack.post_message(message, channel="#mining-guardian")
            logger.info("Sent log failure report to Slack: %d miners", len(enriched))
            
        except Exception as e:
            logger.warning("Failed to send log failure Slack report: %s", e)

    # ── Main entry ────────────────────────────────────────────

    def collect_logs(self, miners: List[Dict], issues: List[Dict]) -> None:'''

if marker in content:
    content = content.replace(marker, new_method)
    print("Added _send_log_failure_slack_report method ✓")
else:
    print("ERROR: Could not find marker")

with open("/root/Mining-Gaurdian/core/mining_guardian.py", "w") as f:
    f.write(content)

print("Done.")
