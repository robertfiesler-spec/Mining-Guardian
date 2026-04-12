PATH = '/Users/BigBobby/Documents/GitHub/Mining Gaurdian/core/mining_guardian.py'
with open(PATH) as f:
    src = f.read()

# Replace the LLM call section + storage section with the dual-model version
old = '''            logger.info("[%s] Running LLM log comparison: pre=%s bytes, post=%s bytes",
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
                # add_llm_insight signature: (insight, miner_id="fleet")
                # Use a special miner_id format so the dashboard can render
                # these as a distinct "log comparison" category.
                km.add_llm_insight(
                    analysis,
                    miner_id=f"compare:{action_label}:{miner_id}",
                )
                logger.info("[%s] LLM comparison stored in knowledge.json", miner_id)
            except Exception as ke:
                logger.warning("[%s] Failed to store LLM comparison in knowledge.json: %s",
                               miner_id, ke)

        except Exception as e:
            logger.warning("[%s] Post-action LLM comparison failed (non-fatal): %s",
                           miner_id, e)'''

new = '''            logger.info("[%s] Running DUAL-MODEL log comparison: pre=%s bytes, post=%s bytes",
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
                               miner_id, se)

        except Exception as e:
            logger.warning("[%s] Post-action dual-model comparison failed (non-fatal): %s",
                           miner_id, e)'''

if old not in src:
    print("ERROR: helper LLM block not found exactly")
    exit(1)

src = src.replace(old, new)
with open(PATH, 'w') as f:
    f.write(src)

print("PATCHED _run_post_action_log_comparison: dual-model (Qwen + Claude)")
