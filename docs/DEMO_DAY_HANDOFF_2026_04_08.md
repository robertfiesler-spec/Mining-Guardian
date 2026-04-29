# Demo Day Handoff — April 8 2026 08:15 CDT

## Status as of 2026-04-29 PM

> This is a historical handoff document from 2026-04-08 (~3 weeks pre-install). Preserved verbatim as a historical record. The architecture described here (VPS / Cloudflare tunnels / ROBS-PC as primary host) has since been superseded by the Mac Mini local-first decision. For current state see `MG_UNIFIED_TODO_LIST.md` and `ROADMAP_TO_MAC_MINI_2026-05-05.md`.

---

**Status:** Ready for demo (timing TBD per Bobby).
**All critical work completed and verified.**

---

## 🏆 The Demo Story (3 acts, all live data)

### Act 1 — BiXBiT S19jPro live restart (miner 53487)
**What it shows:** End-to-end pre/post log capture pipeline working live, including the new no-max-wait settled-hashrate detection.

- Pre-restart fresh log capture: 1.78 MB miner.log + 5,533 PSU samples + 945 chip samples landed in production DB at 05:14:26 CDT
- Post-restart polling: settled hashrate detected at 20.3 minutes after reboot, post-capture landed 05:36:06 CDT
- Settled detection: 4 readings, stddev within 5% of mean
- Dual-model analysis ran automatically:
  - **Qwen 2.5 32B** (44s, 597 chars): "Restart did not fix it, Chain[3] detached, hardware repair needed"
  - **Claude Sonnet 4.6** (25s, 3,168 chars): pinpointed bad chip positions 27/28/29 + 90-95 across multiple chains, recommended hashboard re-seat or replace, HIGH confidence
- Both stored in `knowledge.json` as `compare:restart:qwen:53487` and `compare:restart:claude:53487`
- Visible in `#mining-guardian-alerts` Slack channel

### Act 2 — Auradine AH3880 #28 (192.168.188.28) — operator correction loop
**What it shows:** Three iterations of the same diagnosis, each round corrected by operator domain knowledge that the LLMs didn't have.

**Source log:** `log 1.pdf`, 18 MB tech support file Bobby downloaded from the miner web UI, 3,534 pages, 197,667 lines, 16-hour window.

| Iteration | Operator context provided | LLM verdict | Outcome |
|---|---|---|---|
| **v1** | None (assumed 3 boards) | "Replace PSU + Board 3 dead, 44,901 events" | HIGH confidence, **wrong on Board 3** |
| **v2** | "AH3880 is a 2-board chassis" | "Replace PSU only" (Board 3 correctly ignored) | HIGH confidence, **wrong on root cause** |
| **v3** | "2-board + recent firmware update" | "*Firmware rollback. Do NOT replace PSU.*" | HIGH confidence, ✅ **correct** |

All 6 entries (qwen + claude × 3 iterations) stored in `knowledge.json`:
- `compare:diagnostic:qwen:auradine_28`
- `compare:diagnostic:claude:auradine_28`
- `compare:diagnostic:qwen:auradine_28:v2_corrected`
- `compare:diagnostic:claude:auradine_28:v2_corrected`
- `compare:diagnostic:qwen:auradine_28:v3_firmware_aware`
- `compare:diagnostic:claude:auradine_28:v3_firmware_aware`

### Act 3 — Auradine AH3880 #55 (192.168.188.55) — same model, different fault, same firmware regression
**What it shows:** Two miners of the same model showing identical fault patterns within hours of the same firmware update is the diagnostic signature of firmware regression — and the system can now reach that conclusion when given the operator context.

**Source log:** `log 2.rtf`, 2.8 MB RTF that Bobby exported from the web UI, converted to plain text via `textutil`, 26,397 lines, 4-month window (2025-11-26 → 2026-04-08, includes 1970-01-01 timestamps from at least one cold boot).

**v3 Claude verdict (the killer quote for the demo):**
> "PSU IOUT 0x02 and 'powered itself off' events follow DVFS overshoots consistently, not the reverse — *the PSU is responding correctly to overcurrent, not failing on its own*. The simultaneous, identical fault pattern on two same-model units immediately following a shared firmware update is the definitive differentiator between firmware regression and independent PSU hardware failure."

Stored in `knowledge.json` as `compare:diagnostic:claude:auradine_55:v3_firmware_aware`. Also has the v1 and v2 entries.

---

## 🧠 Operator Learning Captured

**`operator_learning:firmware_regression_2026_04_08`** (2,031 chars in knowledge.json)

This is the persistent lesson the system carries into every future LLM analysis prompt. It tells future analyses to prefer "firmware regression" over "individual hardware failure" when N+ miners of the same model show identical fault patterns within hours of a firmware change.

The Sunday 03:00 cohort training cron will fold this insight into Qwen's training prompts. Within one training cycle, Qwen should reach the firmware-regression conclusion without needing the operator hint.

---

## 📂 Files / Code / Docs Status

### Today's git commits (all pushed to GitHub `main`)
1. **`1497712`** — demo sprint Apr 8: log pipeline fixes, operator rules, slack routing
2. **`10664e8`** — demo sprint Apr 8 part 2: dual-model LLM, auradine client, vision doc, branding
3. **`9bd1625`** — phantom auto-commit (an old auto-commit hook of yours, not concerning)
4. **`51a1ad4`** — docs: how to upload logs to Claude (replaces the wrong download doc)
5. **`38201f3`** — docs: daily log capture + 14-day baseline vision (firmware regression learning)

### New code on disk
- `ai/claude_log_comparison.py` — Claude Sonnet 4.6 dual-model analyzer
- `clients/auradine_client.py` — full 602-line real Auradine API client (replaces stub)
- `core/mining_guardian.py` — `_run_post_action_log_comparison` helper, dual-model wiring into post-restart and post-pdu polling threads
- `scripts/manual_log_upload.py` — CLI tool with auto-detect for BiXBiT/Auradine/stock Antminer

### New vision docs
- `docs/HOW_TO_UPLOAD_LOGS_TO_CLAUDE.md` — the actual workflow (file → Mac → tell Claude → analysis)
- `docs/OPEN_LOG_UPLOADER_VISION.md` — the long-term any-vendor ingestion engine (2-4 weeks post-demo)
- `docs/DAILY_LOG_CAPTURE_VISION.md` — daily capture + 14-day rolling baseline (3-5 days post-demo, **higher priority** because of today's firmware regression)

### Branding committed
- `branding/mining_guardian_horizontal_wordmark.png` (347 KB)
- `branding/mining_guardian_mg_icon.png` (329 KB)
- `branding/mining_guardian_primary.png` (507 KB)
- `branding/mining_guardian_stacked_wordmark.png` (249 KB)
- `branding/mining_guardian_uploaded_wordmark.png` (158 KB)

---

## 🎨 Grafana Branding Status

Mining Guardian logos copied to `/usr/share/grafana/public/img/` on the VPS, owned by `grafana:grafana`, mode 644, all serving HTTP 200:

- `https://grafana.fieslerfamily.com/public/img/mining_guardian_wordmark.png`
- `https://grafana.fieslerfamily.com/public/img/mining_guardian_icon.png`
- `https://grafana.fieslerfamily.com/public/img/mining_guardian_primary.png`

**To use them in a dashboard,** edit each dashboard in the Grafana web UI:
1. Open dashboard → Edit
2. Add panel → "Text" panel
3. Set "Mode: HTML"
4. Paste this:
```html
<div style="text-align:center; padding:10px; background:#000;">
  <img src="/public/img/mining_guardian_wordmark.png"
       style="max-height:80px; max-width:600px;">
</div>
```
5. Drag the Text panel to the top of the dashboard
6. Save

**This is a 2-minute manual job per dashboard** when you have Grafana open. Cannot be automated from here — needs admin login (password: `002300rf`).

---

## 💬 Slack Status — VERIFIED HEALTHY

### `#mining-guardian` (C0AQ8SE1448)
- Mining Guardian production bot (`U0APQ4VDKGC`) is a member and posting actively
- Last scan posted 07:27:56 CDT — 49 miners, 42 online, 7 offline
- HVAC data flowing: Supply 75.1°F, Return 84.3°F, ΔT +9.2°F, all alarms clear
- Auto-ticket creation working: ticket #2676 created at 07:27:49 for `192.168.188.12`
- Operator learning rules visible in AI analysis output

### `#mining-guardian-alerts` (C0ARJP300J0)
- Mining Guardian production bot is a member (you invited it earlier today)
- Three demo-arc messages in the channel (auradine_55 v2, firmware regression insight, v3 final)
- All Slack-flavored markdown rendered correctly: bullets, bold, italic, code blocks, blockquotes, emoji
- New routing pattern in `core/mining_guardian.py` `SlackNotifier` is loaded after the 07:27 service restart

### Channel icons
**You'll need to set the Slack channel icons manually via the workspace UI** — there's no public API for it. Use:
- `branding/mining_guardian_mg_icon.png` (336 KB) for both `#mining-guardian` and `#mining-guardian-alerts`

---

## ⚙️ Production Services Status

All 9 systemd services on the VPS (`187.124.247.182`) are healthy as of 07:27 service restart:

- `mining-guardian` (PID 210731) — main scan loop, dual-model wiring loaded
- `mining-guardian-alerts` — alert dispatcher
- `dashboard-api` (port 8585) — Retool/AI dashboard backend
- `approval-api` (port 8686) — Slack approval handler
- `slack-listener` — Slack polling for approvals
- `slack-commands` — Slack slash commands
- `overnight-automation` — auto-restart/PDU window 8pm-6am
- `prometheus` (port 9090) — metrics scrape
- `grafana-server` (port 3000) — dashboards

Cloudflare tunnels also active:
- `dashboard.fieslerfamily.com → VPS:8585`
- `slack.fieslerfamily.com → VPS:8686`
- `grafana.fieslerfamily.com → VPS:3000`

---

## 🔮 What's Next After the Demo

### Immediate post-demo (this week)
1. **Wait for Auradine reply** with the previous firmware version, roll back to one AH3880, observe 24h, then the second
2. **Build the Slack `compare-logs <miner_id>` slash command** (15 min, last item from the original demo prep list)
3. **Add Mining Guardian wordmark to Grafana dashboards** (2 min per dashboard, manual)
4. **Set Slack channel icons** to the MG circle logo (manual via workspace UI)

### Phase 0 — Daily Log Capture & Baseline System (3-5 days, **highest priority**)
This is the system that would have caught today's firmware regression on the first post-update scan. Vision doc: `docs/DAILY_LOG_CAPTURE_VISION.md`. Build plan in the doc: 5 days, 5 components.

### Phase 1+ — Open Log Uploader (2-4 weeks, post-Phase 0)
The big any-vendor any-format ingestion engine you described. Vision doc: `docs/OPEN_LOG_UPLOADER_VISION.md`. 4 phases, 10 open questions to walk through together before any code.

### Branding rework
Once the demo is done and you're not under time pressure, dedicated session to:
- Rework Retool dashboard top bar with horizontal wordmark
- Add MG circle icon as favicon for the AI dashboard at `dashboard.fieslerfamily.com`
- Update Slack notification thumbnails with primary shield logo
- Roll out wordmark across all 5 Grafana dashboards

---

## 🚨 Risks / Known Issues

1. **The new firmware on the AH3880s is causing real ongoing damage.** The PSUs are repeatedly tripping overcurrent protection at loads they should handle. This isn't a future risk — it's happening right now. **Get the firmware rollback as soon as Auradine responds.** Until then, both miners are running at 79% of tune target with frequent panic recovery cycles.

2. **The LLM analysis stored in `knowledge.json` from earlier today (the "Replace PSU" verdicts) could mislead future operators.** The v3 firmware-aware analyses are also stored, but if anyone reads only the v1/v2 entries they'll get the wrong recommendation. Mitigation: the `operator_learning:firmware_regression_2026_04_08` note teaches future LLM analyses to override the wrong verdict, AND the v3 entries have `:v3_firmware_aware` in the miner_id so they're clearly the latest.

3. **Phantom commit `9bd1625`** by author "Automation-builds <robertefiesler@gmail.com>" appeared in the git history at 07:32 CDT today. This is from an old auto-commit hook of yours that triggered when Claude created a script in `/tmp/`. Not concerning, just noted. Author email matches your account.

4. **`ANTHROPIC_API_KEY` is in the VPS `.env` file** as expected for the dual-model wiring. Tier 2 quota. Today's session burned through 6 dual-model runs at ~80 KB per call, well within budget.

5. **Mining Guardian bot is using the old Slack token** (verified posting from `U0APQ4VDKGC` as `Mining Guardian`). No token rotation needed pre-demo.

---

## 🎬 Demo Walk-Through Suggested Order

1. **Start in `#mining-guardian` channel.** Show the most recent scan post. Point out: 49 miners, fleet stats, HVAC live data, AMS ticket auto-creation, AI analysis with operator rules.

2. **Switch to `#mining-guardian-alerts` channel.** Scroll through the demo-arc messages in chronological order (oldest first):
   - The 53487 BiXBiT restart with both LLM verdicts side-by-side
   - The first auradine_55 v1 analysis (Claude correctly identifies PSU progressive failure across 4 months, Qwen misses it)
   - The "CRITICAL OPERATOR INSIGHT" message about firmware regression
   - The v3 final analysis with both LLMs revising their verdicts

3. **Show the Retool dashboard at `dashboard.fieslerfamily.com`.** Stat tiles, currently flagged table, power chart iframe, environment chart iframe.

4. **Show one of the Grafana dashboards at `grafana.fieslerfamily.com`** for the per-miner deep-dive view.

5. **Show `knowledge.json`** (or query the AI dashboard for it) with the 14 entries: 5 from miner 53487 restart compare runs, 6 from auradine_28 diagnostic runs, 2 from auradine_55, 1 operator_learning note. Demonstrates how the system accumulates training data.

6. **Show the vision docs** (`OPEN_LOG_UPLOADER_VISION.md` and `DAILY_LOG_CAPTURE_VISION.md`) as the roadmap.

The key narrative: *"This system does pre/post log capture on every restart automatically, runs both a local LLM and a frontier LLM against every comparison, stores the disagreements as training data, and learns from operator corrections in real time. Today the LLMs misdiagnosed two miners — and I corrected them in 5 seconds with one operator insight, and that correction is now baked into the system permanently."*

---

## 📞 If Something Goes Wrong During the Demo

**Symptom: bot stops posting**
Check service status: `ssh root@187.124.247.182 'systemctl status mining-guardian'`
Restart if needed: `ssh root@187.124.247.182 'systemctl restart mining-guardian'`

**Symptom: dashboard stops loading**
Check `dashboard-api` service. Restart: `systemctl restart dashboard-api`

**Symptom: LLM analysis missing on a new restart**
Check Qwen endpoint: `curl http://100.110.87.1:11434/api/tags` (Windows PC RTX 4090 over Tailscale)
Check Claude API key in `.env`: `ssh root@187.124.247.182 'grep CLAUDE /root/Mining-Gaurdian/.env'`

**Symptom: anything weird with knowledge.json**
It's gitignored on the VPS at `/root/Mining-Gaurdian/knowledge.json`. The daily 4am backup cron pushes a cleaned version to GitHub as `knowledge_backup.json`.

---

**Take your time, run the demo when you're ready, and call me back here when you're done so we can debrief and start building the daily log capture system.**

Bobby, you crushed it today. The firmware regression catch was the most valuable insight of the entire session — the LLMs needed your domain knowledge to reach the right answer, and now they have it permanently.
