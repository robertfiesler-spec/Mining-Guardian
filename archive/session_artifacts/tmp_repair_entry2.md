## llm_scan_analyses stream frozen for 3.5 days — ghost file (2026-04-10)

**Symptom:** `knowledge['llm_scan_analyses']` stream had not written since 2026-04-06 15:33:48, despite the daemon running and the scan loop showing "Local LLM analysis complete for scan #NNNN" log lines every cycle. Discovered while trying to run a Claude → Qwen → Claude refinement loop on the weekly training output — the stream feeding Claude's weekly trainer was 3.5 days stale, meaning both weekly training runs this morning (04:11 and 04:55) analyzed April 6 fleet state, not April 10.

**Root cause (multi-part):**
1. **Ghost file.** `scripts/llm_scan_hook.py` was UNTRACKED in git. It contained `run_post_scan_llm()`, the background-thread LLM path called from `core/mining_guardian.py` line 5629. Because it was untracked, it never showed up in code review and never got the same scrutiny as tracked files.
2. **Missing write path.** `run_post_scan_llm()` called Qwen, got the analysis back, posted it to Slack, and returned it — but NEVER wrote it to `knowledge['llm_scan_analyses']`. The write path that weekly_train.py reads from simply did not exist in the function.
3. **Config key mismatch.** The hook read `cfg.get("local_llm_url")` and `cfg.get("local_llm_model")`, but `config.json` has keys `ollama_url` and `ollama_model`. Result: `llm_url = None`, `model = None`, analyzer fell back to defaults (probably localhost VPS, where Ollama is stopped). Even if the write path had existed, the LLM call itself was hitting the wrong endpoint.
4. **Stale architectural comment.** `core/mining_guardian.py` line 5361 said `# Ollama local LLM removed — too slow on CPU, hangs up scans`. This was written when Ollama ran on VPS CPU, BEFORE the ROBS-PC RTX 4090 migration made Qwen ~4.6s per scan. The comment is stale; the code change that followed it was never reverted when the architectural reason stopped applying.

**Fix:**
1. Patched `scripts/llm_scan_hook.py`: fixed config keys to `ollama_url`/`ollama_model`, added full persist path to `knowledge['llm_scan_analyses']` with schema `{timestamp, analysis, model, scan_id, source: 'qwen_scan_hook'}`, bounded to last 500 entries.
2. Added `scripts/llm_scan_hook.py` to git tracking for the first time (commit `b3a5902`). No more ghost file.
3. Reverted the misguided Option A parallel inline path in `core/mining_guardian.py` (commit `355bad2`) — the hook now handles it cleanly in a background thread.

**Verification:** Stream count went 196 → 198 within 3 minutes of the restart, last timestamp updated from `2026-04-06T15:33:48` to `2026-04-10T07:07:06`. Stream freshness: ~3 minutes. Confirmed the write path works end-to-end.

**Impact:** For 3.5 days (April 6 15:33 → April 10 06:30), the hourly Qwen scan analysis stream was silently dead. Both of today's Claude weekly training runs (04:11 and 04:55) consumed this stale stream and produced output that referenced April 6 fleet state ("47 of 49 miners online" — the actual fleet is 58 but April 6 saw 49 scanned). The "learning loop" that is the main feature of the product had been broken for 3.5 days without any alerts firing, because the Slack post at the end of `run_post_scan_llm` was succeeding — the operator-visible signal (Slack) was fine, only the invisible-but-critical signal (knowledge.json persistence) was broken. Same failure class as the April 9 pre/post restart comparison bug and today's earlier km.save clobber bug — code logs success but state doesn't actually change.

**Meta-lesson:** Three silent-skip bugs in two days, all same class. Your codebase has a systemic weakness around "log success without verifying state change." Worth a design pass on a post-write verification helper: every write to knowledge.json should read it back and assert the new entry is present before the writer's success log line fires. That would have caught all three bugs within one scan cycle instead of letting them bleed for days.

**Also meta:** UNTRACKED files in the working tree are a latent bug source. Four more untracked `.bak.*` and `scripts/fix_*.py` files are still in the tree from yesterday's Step 8 cleanup list. Next session should finish that cleanup so no more ghost files exist.

---

