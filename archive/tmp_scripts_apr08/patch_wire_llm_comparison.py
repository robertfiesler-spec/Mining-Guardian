#!/usr/bin/env python3
"""Wire run_log_comparison_llm into the post-restart and post-pdu-cycle paths.

The LLM comparison capability has existed in ai/llm_scan_hook.py +
ai/local_llm_analyzer.py for a while but no caller ever invoked it. This
patch fixes that gap by:

1. Adding a small _run_post_action_log_comparison helper on MiningGuardian
   that fetches the most recent pre and post miner.log entries from the DB
   for a given miner_id and label pair, calls run_log_comparison_llm with
   the local Qwen instance, stores the resulting analysis text into
   knowledge.json under known_issues with a special miner_id format
   ("compare:<miner_id>") so it shows up in the AI dashboard, and posts to
   Slack if a notifier is available. NEVER raises — log + return on error.

2. Calling that helper from the post-restart polling thread immediately
   after the post-restart _collect_logs_nonblocking call returns
   successfully (and the thread is about to return).

3. Calling that helper from the post-pdu-cycle polling thread at the same
   point.

The whole comparison runs against the LOCAL LLM (Windows PC RTX 4090 over
Tailscale, Qwen 2.5 32B Q4) — no Claude API token used. This matches the
production architecture: local LLM does the day-to-day comparisons; Claude
API is only used for weekly cohort training and federated knowledge merge.
"""

import re

PATH = '/Users/BigBobby/Documents/GitHub/Mining Gaurdian/core/mining_guardian.py'

with open(PATH) as f:
    src = f.read()

# ============================================================
# CHANGE 1: Add the _run_post_action_log_comparison helper method.
# Insert it right before def execute_pdu_cycle so it sits next to the
# code that uses it.
# ============================================================

helper_method = '''    def _run_post_action_log_comparison(self, miner_id: str, ip: str,
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

            logger.info("[%s] Running LLM log comparison: pre=%s bytes, post=%s bytes",
                        miner_id, len(pre_log), len(post_log))

            # Import here so missing optional dep doesn't break daemon startup
            try:
                import sys as _sys
                from pathlib import Path as _Path
                _ai = str(_Path(__file__).resolve().parent.parent / "ai")
                if _ai not in _sys.path:
                    _sys.path.insert(0, _ai)
                from llm_scan_hook import run_log_comparison_llm
            except ImportError as ie:
                logger.warning("[%s] LLM log comparison unavailable: %s", miner_id, ie)
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

            analysis = run_log_comparison_llm(
                miner_id=miner_id,
                pre_log=pre_log,
                post_log=post_log,
                miner_info=miner_info,
                slack_client=self.slack if hasattr(self, "slack") else None,
            )

            if not analysis:
                logger.info("[%s] LLM log comparison returned no analysis", miner_id)
                return

            logger.info("[%s] LLM log comparison complete (%s chars)", miner_id, len(analysis))

            # Store the analysis in knowledge.json so it shows up in the AI
            # dashboard alongside cohort/outlier insights. Use a special
            # miner_id format so the dashboard can render these as a
            # distinct category.
            try:
                from knowledge_manager import KnowledgeManager
                km = KnowledgeManager()
                km.add_llm_insight(
                    miner_id=f"compare:{miner_id}",
                    insight=analysis,
                    source=f"log_comparison_{action_label}",
                    confidence=None,
                )
                logger.info("[%s] LLM comparison stored in knowledge.json", miner_id)
            except Exception as ke:
                logger.warning("[%s] Failed to store LLM comparison in knowledge.json: %s",
                               miner_id, ke)

        except Exception as e:
            logger.warning("[%s] Post-action LLM comparison failed (non-fatal): %s",
                           miner_id, e)

'''

# Insert the helper right before "    def execute_pdu_cycle("
marker = '    def execute_pdu_cycle(self, issue: Dict[str, Any]) -> None:'
if marker not in src:
    print("ERROR: insertion marker for helper not found")
    exit(1)
src = src.replace(marker, helper_method + marker)
print("  ✓ _run_post_action_log_comparison helper added")

# ============================================================
# CHANGE 2: call the helper from post-restart polling thread
# ============================================================

old_post_restart_call = '''                                        if is_settled:
                                            logger.info("[%s] Miner is fully mining with SETTLED hashrate after %.1f min — capturing post-restart logs",
                                                        miner_id, elapsed_min)
                                            self._collect_logs_nonblocking(miner_id, model, "post-restart")
                                            return'''

new_post_restart_call = '''                                        if is_settled:
                                            logger.info("[%s] Miner is fully mining with SETTLED hashrate after %.1f min — capturing post-restart logs",
                                                        miner_id, elapsed_min)
                                            self._collect_logs_nonblocking(miner_id, model, "post-restart")
                                            # Wire LLM pre/post comparison — runs against local Qwen,
                                            # stores result in knowledge.json, posts to Slack
                                            self._run_post_action_log_comparison(
                                                miner_id, ip, model, "restart"
                                            )
                                            return'''

if old_post_restart_call not in src:
    print("ERROR: post-restart call site not found")
    exit(1)
src = src.replace(old_post_restart_call, new_post_restart_call)
print("  ✓ post-restart polling thread now calls LLM comparison")

# ============================================================
# CHANGE 3: call the helper from post-pdu polling thread
# ============================================================

old_post_pdu_call = '''                                            if is_settled:
                                                logger.info("[%s] Miner is fully mining with SETTLED hashrate after %.1f min — capturing post-pdu-cycle logs",
                                                            miner_id, elapsed_min)
                                                self._collect_logs_nonblocking(miner_id, model, "post-pdu-cycle")
                                                return'''

new_post_pdu_call = '''                                            if is_settled:
                                                logger.info("[%s] Miner is fully mining with SETTLED hashrate after %.1f min — capturing post-pdu-cycle logs",
                                                            miner_id, elapsed_min)
                                                self._collect_logs_nonblocking(miner_id, model, "post-pdu-cycle")
                                                # Wire LLM pre/post comparison
                                                self._run_post_action_log_comparison(
                                                    miner_id, ip, model, "pdu-cycle"
                                                )
                                                return'''

if old_post_pdu_call not in src:
    print("ERROR: post-pdu call site not found")
    exit(1)
src = src.replace(old_post_pdu_call, new_post_pdu_call)
print("  ✓ post-pdu polling thread now calls LLM comparison")

with open(PATH, 'w') as f:
    f.write(src)

print()
print("LLM pre/post comparison wiring complete")
