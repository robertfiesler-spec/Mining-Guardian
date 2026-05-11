# Mining Guardian — Mac Mini Cutover Handoff

**Date:** Sun May 10, 2026 (CDT)
**Operator:** Bobby Fiesler (BigBobby), CTO BiXBiT USA
**Focus this week:** Get Mac Mini running at full parity with the production-quality system that's been running on the VPS.

---

## Current state

**VPS (`root@187.124.247.182`)** — being phased out, kept running as insurance for first few hours of cutover. Today's (May 10) deep dive crashed mid-run with `psycopg2.OperationalError: SSL connection has been closed unexpectedly` when infrastructure was transferred to Mac Mini. Was authoritative through May 9 (deep dive completed clean at 15:58 with 7,994 char fleet synthesis). Has the real `knowledge.json` — 84 refined_insights, 56 operator_decisions, all 10+ days of cleanup audit trail from the 152.7% saga.

**Mac Mini (`miningguardian@100.69.66.32`, Tailscale)** — M4, 10-core (4P+6E), 16 GB RAM, macOS 26.4.1. Mining Guardian v1.0.3 installer-deployed at `/Library/Application Support/MiningGuardian/`. 22 launchd jobs registered in `/Library/LaunchDaemons/com.miningguardian.scheduled.*.plist`. Postgres runs in a Lima VM (not native). Ollama runs locally on the Mac Mini.

**ROBS-PC** — still running, still advertising `192.168.188.0/24` over Tailscale, still serving Qwen on `100.110.87.1:11434`. Kept as insurance — but Mac Mini is supposed to run Qwen locally going forward.

---

## What's working on Mac Mini

These scheduled jobs succeed (exit_code 0):
- `log_collection` (runs ~10 min)
- `morning_briefing`
- `operator_review`
- `knowledge_backup`

But three of these are essentially no-ops because they operate on an old/stale knowledge.json snapshot.

---

## What's broken on Mac Mini — the cutover blockers

Diagnosed from `/Library/Application Support/MiningGuardian/logs/scheduled/*.err.log` on May 8:

1. **🔴 `ANTHROPIC_API_KEY` missing from Mac Mini `.env`**
   - `weekly_training` fires nightly, runs ~18 min calling Claude, gets empty responses 18+ times in a row
   - `refinement_chain` pre-flight check confirms: "ANTHROPIC_API_KEY not found in env or .env file"
   - Same key already exists in VPS `/root/Mining-Guardian/.env` — needs copying

2. **🔴 Wrong Ollama model installed on Mac Mini**
   - Mac Mini has only `llama3.2:3b` (tiny 3B model)
   - Production needs `qwen2.5:32b-instruct-q4_K_M` (32B, ~20 GB download)
   - Ollama is running (`/Applications/Ollama.app/Contents/Resources/ollama serve` PID 747)

3. **🟡 Postgres timestamp type mismatch**
   - `daily_deep_dive.py:464` query: `recorded_at >= TO_CHAR(...)` failing
   - VPS Postgres has `recorded_at` as `text` (legacy)
   - Mac Mini's Lima Postgres has it as `timestamp with time zone`
   - Schema drift between the two

4. **🟡 `datetime.datetime not subscriptable` in `train_comprehensive.py:290`**
   - `s.get('last_seen', '')[:16]` assumes string but Mac Mini's Postgres returns datetime
   - Same root cause as #3 — schema drift

5. **🟢 `catalog_import` exit 126 (permission denied)** — separate, lower priority

---

## Mac Mini knowledge.json situation

Currently at `/Library/Application Support/MiningGuardian/knowledge/knowledge.json` (symlinked from the root). Contains 61 refined_insights and 37 operator_decisions, but **the data is from April 29** — missing 10+ days of operator decisions (#38 through #56) and the entire 152.7% saga + scrubs + fixes.

There's a `knowledge/incoming/` and `knowledge/quarantine/` directory structure suggesting an intended import pipeline, but the migration script hasn't been used to pull the up-to-date VPS knowledge.json yet.

**VPS has the authoritative knowledge.json with all 56 decisions.** Path forward: figure out the right ingestion mechanism (via `incoming/`?) rather than `scp`'ing directly over the symlink target.

---

## Code fixes from May 4-6 that may or may not be on Mac Mini

VPS feature branch `fix/grafana-intelligence-miner-dropdown-2026-04-29` has three operational commits:
- `53f6567` — Phase 1: hashrate sanity check in `train_cohort.py` (4 guards)
- `b49cc6e` — Phase 1b: extend to `train_comprehensive.py` (4 more guards + 1 in `morning_briefing.py`)
- `2c41ab5` — Phase 1c: NOT LIKE filter on scrubbed past_analyses rows

Mac Mini build stamp: `git_sha: ce9831c1a09a`, stamped 2026-05-07 20:26 UTC. **Need to verify** these three commits are or aren't in that build. Quick grep for `CASE WHEN hashrate_pct < 120` and `NOT LIKE '%[SCRUBBED-DATA-INTEGRITY]%'` in Mac Mini install will confirm.

---

## Outstanding bug regardless of which system runs it

**Operator denials get silently overwritten by training.** Confirmed on May 8 and May 9 — each midnight training run flips 5+ `DENIED_TRAINING_FAILURE` insights back to `REJECT`. Fix is ~5 lines in `ai/knowledge_manager.py` (or wherever in-place insight updates happen): guard `if existing.action == 'DENIED_TRAINING_FAILURE': skip`. Not blocking cutover but should ship before the Mac Mini takes over to avoid losing all the cleanup work from the 152.7% saga.

Also outstanding from before cutover:
- Cron auto-collect fix for warehouse miners (multi-cglog concat for 53529/64407 + Auradine API for 54504/63940). NiceHash 65891 deferred per operator — returning to BiXBiT firmware soon.
- HVAC s19jpro supply NULL bug (192.168.189.235, since Sun 04-26 14:08). Diagnostic plan: bump HVAC client to DEBUG, restart mining-guardian, wait one poll, check journal.
- Cosmetic: `_print_report()` in `core/mining_guardian.py:2219` only displays warehouse HVAC, not s19jpro snapshot.

---

## Key operator rules (permanent, must follow on Mac Mini too)

- **Temp threshold:** Never flag overheating below 84°C chip temp. Never warn based on cohort averages alone.
- **HVAC delta-T at USA 188 is intentionally low** — never recommend HVAC investigation based on delta-T.
- **All container miners (S19JPros + others) = IMMERSION** (not air-cooled).
- **Warehouse cooling map:** S21Imm `.10/.11` = IMMERSION (B100 Fog Hashing); S21e XP Hyd `.25/.26` = HYDRO; Auradine AH3880 `.27/.28` = HYDRO. **Zero air-cooled miners in operation.**
- **S19JPro fleet is EOL** (~3 months out). Push till they break. No preventive interventions. 12+ decisions deep on this exemption.
- **No single-miner rules** (decision #26). Minimum cohort size 4 for any pattern claim.
- **Firmware diversity is intentional** (decision #29).
- **Never mix cooling types** in one insight (decision #28).
- **AMS-first for all miner commands.** Direct device APIs (port 4028, port 8443) are secondary/fallback only.
- **Auto-restart blocked** for miners with 3+ FAILURE outcomes. Dead boards always manual.
- **Operator decisions take precedence over AI re-emissions** — denials must stick.

---

## Infrastructure quick reference

| | |
|---|---|
| VPS | Hostinger KVM 8, 32 GB RAM, IP `187.124.247.182`, Tailscale `100.106.123.83`, repo at `/root/Mining-Guardian/` |
| Mac Mini | SSH `miningguardian@100.69.66.32`, install at `/Library/Application Support/MiningGuardian/`, Postgres in Lima VM, Ollama native |
| ROBS-PC | Windows, Tailscale `100.110.87.1`, serves Qwen on `:11434`, advertises `192.168.188.0/24` subnet |
| Pi (amshub) | `192.168.188.30`, user `bixbit/bixbit`, `amshub` binary in tmux session `hub` |
| Slack | `#mining-guardian` channel `C0AQ8SE1448`, Bobby `U07AGTT8CLD` |
| Grafana | `https://grafana.fieslerfamily.com` — password was reset May 5, Bobby changed to secure |
| AMS workspace | ID `119`, JWT cookie-based auth via `/auth/login` + `/auth/select_workspace` |

---

## Recommended starting order in the new chat

1. **Snapshot both systems first.** Read-only check on Mac Mini's `.env`, Ollama models, Postgres schema for `recorded_at`, code grep for the three operational commits. Read VPS knowledge.json size + decision count to confirm authoritative source. 10 min.

2. **Decide on knowledge.json migration mechanism.** Look at how the installer expects ingestion via `incoming/` (the directory exists for a reason). Don't `scp` over the symlink without understanding the intended flow.

3. **Fix Mac Mini blockers in dependency order:**
   - Add `ANTHROPIC_API_KEY` to Mac Mini `.env` (~2 min)
   - Start `ollama pull qwen2.5:32b-instruct-q4_K_M` in background (~30 min download)
   - Migrate knowledge.json from VPS to Mac Mini via the right path
   - Migrate Postgres data from VPS to Mac Mini's Lima Postgres (this fixes the schema drift since pg_dump brings schema along)

4. **Test a manual training cycle on Mac Mini** before re-enabling scheduled jobs. Verify all 4 issues resolve. If everything succeeds, the cutover is real.

5. **Cutover decision** — once Mac Mini works on real data, disable VPS cron, let Mac Mini run authoritative.

6. **Then circle back to outstanding bugs** — denial-overwrite guard, cron auto-collect, HVAC supply diagnostic.

---

## Communication style preferences

Bobby is hands-on and technically deep. Prefers direct execution over planning discussions. Pushes back immediately when something doesn't match physical reality. Expects diagnosis and resolution rather than apologies. **Always Path A vs Path B framing on real decisions.** Bulk-handle obvious EOL inheritances; focus reviews on genuinely-new items. When in doubt about a credential, never put it in chat — set a throwaway and let Bobby change it through the UI.

---

## Warehouse log injection workflow (interim, until cron auto-collect fix)

While Mac Mini stabilizes, manual log injection continues each morning for 5 warehouse miners (65896 cron handles; 65891 + 53529 + 64407 + 54504 + 63940 need manual). Daily script template at `/tmp/inject_logs_<DATE>.py` on VPS. **MAC mapping must be verified each day** — base.tar.gz → 53529 vs 64407 is NOT deterministic. Use `grep macaddr config/miner_overview.json` on the extracted archive to identify (`0a:43:ce:89:8e:ab` = 53529, `36:8e:24:f7:69:3c` = 64407). Today (May 10) injection went to VPS at 09:13 CDT, but VPS deep dive crashed at the SSL error, so today's analysis may be incomplete.

---

That's the handoff. Good luck with the cutover this week.
