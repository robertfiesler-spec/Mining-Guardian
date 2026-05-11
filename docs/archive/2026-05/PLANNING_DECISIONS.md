# Mining Guardian Cutover — Planning Session Decisions

**Date of planning session:** Sun May 11, 2026
**Operator:** Bobby Fiesler
**Context:** This document captures decisions made in a planning conversation with Claude (claude.ai web chat) before handoff to Claude Code running on the Mac Mini. Read alongside CLAUDE.md (the original handoff).

---

## Decision 1: LLM model change — Qwen3 8B, not Qwen 2.5 32B

**Original handoff said:** Mac Mini blocker #2 is downloading qwen2.5:32b-instruct-q4_K_M (~20 GB).

**Decision:** Use qwen3:8b (Q4_K_M, ~5.5 GB) instead.

**Reasoning:**
- 16 GB Mac Mini cannot run a 32B model. q4_K_M weights alone are ~20 GB. Even with mmap/swap it would run at disk-read speed and contend with Lima VM (Postgres), Ollama runtime, and Mining Guardian Python processes for the remaining ~12 GB of usable RAM.
- Per Bobby's requirement: "this needs to be on its own like a customer would have it." That eliminates pointing at ROBS-PC as a permanent inference host — ROBS-PC stays as insurance for this cutover only.
- Qwen3 8B is the 2026 consensus pick for 16 GB Macs running structured analysis workloads. ~5.5 GB loaded, leaves ~10 GB headroom, runs ~30 t/s on M4 base. Has hybrid thinking mode (toggleable chain-of-thought) — gives reasoning-model behavior when needed (training pipeline) and faster non-thinking behavior when not (morning_briefing).
- Kimi K2.6 was considered and ruled out — 1T parameter MoE, smallest usable quant needs 350 GB RAM. Not a Mac story.
- DeepSeek-R1-0528-Qwen3-8B is a viable alternative (same size, R1-distilled reasoning) but produces verbose think outputs requiring post-processing strip. Default Qwen3 8B is cleaner for a production pipeline.

**Implementation impact:**
- Mining Guardian source code currently references qwen2.5:32b-instruct-q4_K_M. Every reference needs to be grep-and-replaced with qwen3:8b. This is a one-time code change, not a config tweak.
- Need to find: model name string in config + any hardcoded references in Python files. Suggest grep -rn "qwen2.5:32b" /Library/Application\ Support/MiningGuardian/ to locate all instances.
- Download time drops from ~30 min to ~5 min.

**Future:** When Bobby's 64 GB Mini PC arrives, revisit. The 64 GB tier opens Qwen3 30B-A3B (MoE, 16.5 GB loaded, ~3B active per token) which would be a significant quality bump while still customer-deployable on one box.

---

## Decision 2: Live observation — current model is violating operator rules in real-time

During the planning session, Bobby pasted live log output showing scans #25 (May 10) and #26 (May 11):

- Scan #25 diagnosis: "invalid temperature readings from two S19JPro miners, indicating a potential issue with the cooling system."
- Scan #26 diagnosis: "S19JPro miners are experiencing a hardware failure due to a dead hashboard."

**Both violate documented operator rules:**
- S19JPro EOL exemption — "Push till they break. No preventive interventions. 12+ decisions deep."
- All container miners are IMMERSION — cooling-system framing on S19JPros is misplaced.
- Single-miner / two-miner pattern claims violate cohort minimum (decision #26: minimum cohort size 4).

**This is the denial-overwrite bug actively chewing through operator work.** Each scan emits rule-violating insights → operator denies → training run flips denials back to REJECT → next scan re-emits. The 152.7% saga cleanup is being silently undone.

**Implication for cutover order:** This raises the priority of the denial-overwrite guard fix in ai/knowledge_manager.py. Original handoff said "should ship before Mac Mini takes over." Confirmed — this should ship as part of the cutover, not after.

---

## Decision 3: Execution model — Claude Code on Mac Mini, full sudo when needed

**Original plan:** Claude (web chat) SSH directly into VPS and Mac Mini.

**Reality discovered:** Anthropic's web chat sandbox blocks outbound port 22. Confirmed via testing.

**Replacement:** Claude Code installed on Mac Mini (~/.local/bin/claude, v2.1.138). Mac Mini has full network access — Tailscale, VPS SSH, Lima VM. None of the web-chat restrictions apply.

**Access mode:** Claude Code asks for tool approval before each command by default. **Keep this on for the cutover** — do not use --dangerously-skip-permissions. Approval-per-step is the right pace for migrating authoritative data.

---

## Decision 4: VPS as jump host for VPS-side work

Claude Code on Mac Mini will SSH to VPS for read-only data extraction (knowledge.json, pg_dump). VPS auth is Bobby's existing root login. No new credentials needed.

When VPS is decommissioned post-cutover, this access path dies naturally.

---

## Decision 5: Pace

Bobby's explicit instruction: "we have as much time as needed to get this right, not quickly but the right way. i am fine with taking longer to do it right."

- Losing a day or two of operations is acceptable. Do not rush.
- Today's (May 10) VPS deep dive SSL crash will NOT be investigated. Pull data, move on. VPS is being retired.
- Audits/improvements Bobby has written stay in the drawer until Mac Mini is authoritative and stable. Get to parity first.

---

## Recommended execution order (revised from original handoff)

1. **Read-only snapshot of both systems.** Confirm VPS knowledge.json size + decision count (handoff says 56 decisions). Confirm Mac Mini .env keys (no values in chat), Ollama models, Postgres schema for recorded_at, git SHA, and whether the three commits from fix/grafana-intelligence-miner-dropdown-2026-04-29 (53f6567, b49cc6e, 2c41ab5) are in the Mac Mini build.

2. **Trace the knowledge.json ingestion pipeline.** Read the installer / app code to understand what knowledge/incoming/ is for. Per Bobby: defer to Claude's recommendation on the right mechanism. Do not scp directly over the symlink target.

3. **Fix blockers in dependency order:**
   - Add ANTHROPIC_API_KEY to Mac Mini .env (copy from VPS, don't paste in any chat)
   - ollama pull qwen3:8b on Mac Mini (~5 min)
   - Grep + update Mining Guardian source for qwen2.5:32b-instruct-q4_K_M → qwen3:8b
   - Migrate knowledge.json from VPS to Mac Mini via the ingestion pipeline identified in step 2
   - Migrate Postgres data from VPS to Mac Mini's Lima Postgres (pg_dump brings schema, fixes the timestamp drift)

4. **Ship the denial-overwrite guard** in ai/knowledge_manager.py (~5 lines) BEFORE re-enabling scheduled jobs on Mac Mini. Otherwise the migrated 56 operator_decisions will be eroded the same way they are today.

5. **Test a manual training cycle on Mac Mini** end-to-end. Verify Qwen3 8B respects S19JPro EOL exemption, cohort minimums, immersion classification. If insights still violate rules, that's a prompt engineering / system prompt issue, not a model size issue — fix at the prompt layer.

6. **Cutover.** Disable VPS cron, Mac Mini becomes authoritative.

7. **Outstanding bugs** — cron auto-collect for warehouse miners, HVAC supply NULL diagnostic, cosmetic _print_report fix.

---

## Operator communication style (from original handoff, restated for emphasis)

- Direct execution over planning discussions.
- Path A vs Path B framing on real decisions.
- Diagnosis and resolution, not apologies.
- Push back when reality doesn't match — Bobby will, and so should Claude.
- Credentials never go in chat. Set a throwaway, let Bobby change it through the UI.

---

## Sticky rules (from CLAUDE.md, restated here so Claude Code can't miss them)

- Never flag overheating below 84°C chip temp.
- Never warn based on cohort averages alone.
- HVAC delta-T at USA 188 is intentionally low — never recommend HVAC investigation based on delta-T.
- All container miners (S19JPro + others) = IMMERSION. Zero air-cooled miners.
- S19JPro fleet is EOL ~3 months out. No preventive interventions on them.
- Minimum cohort size 4 for any pattern claim.
- AMS-first for miner commands. Direct device APIs are fallback only.
- Auto-restart blocked for miners with 3+ FAILURE outcomes.
- Operator decisions take precedence over AI re-emissions.
