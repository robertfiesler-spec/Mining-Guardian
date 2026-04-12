PATH = '/Users/BigBobby/Documents/GitHub/Mining Gaurdian/core/mining_guardian.py'
with open(PATH) as f:
    src = f.read()

# The issue: my patch used \\n in a Python string literal which becomes a literal backslash-n
# in the resulting source. Need real newlines via "\n" (single backslash in source).
# Replace the broken Slack formatting block with a clean version.

old = '''            # Post a unified side-by-side message to Slack alerts channel.
            # Operator can see both models' verdicts and learn the differences.
            try:
                if hasattr(self, "slack") and self.slack:
                    msg_parts = [
                        f"🔍 *Pre/Post Log Comparison — `{ip}` ({model})*",
                        f"Action: {action_label} | id: {miner_id}",
                        f"Pre: {len(pre_log):,} bytes  |  Post: {len(post_log):,} bytes",
                        "",
                    ]
                    if qwen_analysis:
                        q = qwen_analysis[:1500]
                        msg_parts.append(f"*🧠 Local Qwen 2.5 32B:*\\n```\\n{q}\\n```")
                    else:
                        msg_parts.append("*🧠 Local Qwen 2.5 32B:* _(no analysis returned)_")
                    msg_parts.append("")
                    if claude_analysis:
                        c = claude_analysis[:1500]
                        msg_parts.append(f"*🤖 Claude Sonnet 4.6:*\\n```\\n{c}\\n```")
                    else:
                        msg_parts.append("*🤖 Claude Sonnet 4.6:* _(no analysis returned)_")
                    full_msg = "\\n".join(msg_parts)
                    self.slack.post_to_alerts_channel(full_msg)
                    logger.info("[%s] Dual-model comparison posted to #mining-guardian-alerts", miner_id)
            except Exception as se:
                logger.warning("[%s] Failed to post dual-model comparison to Slack: %s",
                               miner_id, se)'''

new = '''            # Post a unified side-by-side message to Slack alerts channel.
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
                    self.slack.post_to_alerts_channel(full_msg)
                    logger.info("[%s] Dual-model comparison posted to #mining-guardian-alerts", miner_id)
            except Exception as se:
                logger.warning("[%s] Failed to post dual-model comparison to Slack: %s",
                               miner_id, se)'''

if old not in src:
    print("ERROR: Slack formatting block not found")
    exit(1)
src = src.replace(old, new)
with open(PATH, 'w') as f:
    f.write(src)
print("Fixed Slack formatting newlines")
