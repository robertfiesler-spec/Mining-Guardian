## Weekly training fleet synthesis silently clobbered (2026-04-10)

**Symptom:** Manual weekly Claude training (PID 263793, fired 03:57:43) completed cleanly per the log — 18 Claude API calls, `Fleet synthesis complete: 12188 chars` at 04:11:57. But `knowledge.json` `cross_miner_analysis` had only 1 stale entry (1038 chars, field `summary`), not the 12188-char `analysis` entry the code wrote. `known_issues` still 50, `patterns` still 7 — identical to pre-run state.

**Root cause:** Ordering bug in `ai/train_cohort.py`. Write sequence was: (1) direct file write to insert new `cross_miner_analysis` entry via atomic replace, then (2) `km.save()` which writes KnowledgeManager's in-memory snapshot to knowledge.json. Step 2 clobbered step 1 because `km` held a snapshot from BEFORE the direct write, so its `save()` serialized stale state over the fresh synthesis. Same class as the April 9 pre/post restart comparison write bug — code paths writing to different state stores that do not see each other.

**Fix:** Reordered so `km.save()` and `conn.close()` fire FIRST, then the direct `cross_miner_analysis` file write fires LAST. Added a CRITICAL ORDERING comment block so a future session does not re-reorder them.

**Impact:** Every Sunday weekly training since this regressed has been silently losing its fleet synthesis. 18 Claude API calls per run producing output that never reached knowledge.json, which meant the Sunday merge block could not pull previous weeks' Claude synthesis into new runs, and OpenClaw's guardian-db skill would never see weekly Claude insights. The local LLM training loop has been running without the Claude feedback signal it was designed to consume.

**Verification:** Re-run `weekly_train.py` manually after fix, then check `knowledge['cross_miner_analysis'][0]['analysis']` for the 12K+ char synthesis with `source='claude_weekly_cohort'`.

**Backups on VPS:** `knowledge.json.bak.20260410-preweeklytrainfix`, `ai/train_cohort.py.bak.20260410`.

---

