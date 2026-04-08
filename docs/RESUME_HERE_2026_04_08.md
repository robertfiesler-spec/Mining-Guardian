# Resume Here — April 8 2026

**Bobby left the office around 08:30 CDT to drive somewhere.**
**Picking back up when Bobby returns.**

---

## ⏸️ Where we paused

Last thing we did before Bobby left:
1. ✅ Three-version diagnostic timeline complete on both AH3880s (v1 → v2 → v3 firmware-aware), all stored in knowledge.json
2. ✅ Operator learning note about firmware regression stored in knowledge.json
3. ✅ Final v3 dual-model results posted to `#mining-guardian-alerts`
4. ✅ Mining Guardian logos copied to Grafana static directory at `/usr/share/grafana/public/img/`
5. ✅ Bobby manually started adding the wordmark to one Grafana dashboard (Mining Guardian — AI & Learning)
6. ⏸️ **Paused mid-Grafana-branding** — Bobby noted the logo panel needed three fixes:
   - Background color clashes (panel uses `#000` but Grafana uses `#111217`)
   - Logo too small (was 80px max-height)
   - Panel still showed "Logo" title and panel border

The fix instructions are in this conversation — replace HTML with the transparent-background version, set max-height to 130px, delete the panel title, toggle "Transparent background" ON.

---

## 🎯 First thing to do when Bobby returns

1. **Ask how the demo went** (if it happened while he was out)
2. **If demo hasn't happened yet**, finish the Grafana branding on remaining 4 dashboards (2 min each) — see the corrected HTML in the chat above
3. **If demo already happened**, debrief, capture lessons learned, then start the post-demo build queue

---

## 📋 Outstanding items (in priority order)

### Pre-demo loose ends
- Finish Grafana branding on the other 4 dashboards (Board Health, Fleet Overview, Main, Per Miner, Pool Stats)
- Set Slack channel icons manually via workspace UI (use `branding/mining_guardian_mg_icon.png`)
- Build the Slack `compare-logs <miner_id>` slash command (last item from the original demo prep list, ~15 min)

### Post-demo Phase 0 (highest priority new build)
- **Daily Log Capture & 14-Day Rolling Baseline System** — would have caught today's firmware regression on the first post-update scan
- Vision doc: `docs/DAILY_LOG_CAPTURE_VISION.md`
- ETA: 3-5 days of focused work
- 5 components: cron entry script, label-aware retention, firmware_changes table + scan-loop detector, generalized comparison helper, regression detector module

### Post-demo Phase 1+
- **Open Log Uploader** — any-vendor any-format ingestion engine
- Vision doc: `docs/OPEN_LOG_UPLOADER_VISION.md`
- ETA: 2-4 weeks across 4 phases
- Walk through the 10 open questions with Bobby BEFORE writing any code

### Auradine firmware rollback
- Bobby emailed Auradine for the previous firmware version
- When they reply: roll back to one AH3880 first (recommend `192.168.188.55` since `auradine_28` is the more sick of the two), observe 24 hours, then roll back the second
- Validates the firmware-regression diagnosis

---

## 🏆 Demo Story Recap (if Bobby needs to refresh)

**Three production-quality dual-model diagnoses stored in `knowledge.json`:**

| Miner | Source | Story |
|---|---|---|
| **53487** (BiXBiT S19jPro) | Live restart pre+post logs | End-to-end pipeline working: settled hashrate detection, dual-model comparison, Claude pinpoints exact bad chip positions |
| **auradine_28** (AH3880) | log 1.pdf, 18 MB | Three-iteration diagnostic showing operator-correction loop: v1 wrong on Board 3, v2 wrong on root cause, v3 correct (firmware regression) |
| **auradine_55** (AH3880) | log 2.rtf, 2.8 MB | Different miner, identical fault pattern, confirms firmware regression hypothesis. Both LLMs at HIGH confidence retracted PSU verdicts in v3. |

**The killer demo moment:** Bobby's 5-second operator insight ("I just updated the firmware") corrected two HIGH-confidence LLM verdicts and the system stored the lesson permanently for future analyses.

---

## 🔌 System Status (verified at 08:15 CDT before Bobby left)

- **VPS Mining Guardian services:** all 9 systemd units active and healthy
- **OpenClaw Docker container:** running (status verified 08:35 CDT, Socket Mode connected)
- **Mining Guardian production bot** (`U0APQ4VDKGC`): posting active scans to `#mining-guardian` every hour
- **Grafana logos:** serving HTTP 200 from `https://grafana.fieslerfamily.com/public/img/mining_guardian_*.png`
- **GitHub:** working tree clean, last push `2676d77` (demo day handoff doc)
- **Local LLM (Qwen 2.5 32B Q4):** healthy on Windows PC RTX 4090 over Tailscale
- **Claude API:** Tier 2, plenty of headroom

---

## 💬 OpenClaw Slack Reference

**Channel to use:** `#mining-guardian` (C0AQ8SE1448) — NOT the alerts channel
**How to address it:** Always start with `@OpenClaw` mention, OR use a slash command if registered

**Commands to try (most likely to work):**
- `@OpenClaw help`
- `@OpenClaw status`
- `@OpenClaw scan`
- `@OpenClaw miner 192.168.188.XX`
- `@OpenClaw show offline`
- `@OpenClaw analyze 192.168.188.XX`

**If natural language fails entirely:** DM the OpenClaw bot directly. Some bots only respond in DMs.

**Container check command** (run as root on VPS):
```
docker logs openclaw-5b5o-openclaw-1 --tail 30
```
Look for "socket mode connected" lines — should appear every 35 min.

---

## ☕ Caffeinate while away

Bobby's Mac is running with `caffeinate -dimsu &` to stay awake while he drives.
To stop it when he's back: `killall caffeinate`

---

**File saved at: `/Users/BigBobby/Documents/GitHub/Mining Gaurdian/docs/RESUME_HERE_2026_04_08.md`**
**Open this file when you're back — it has everything you need to pick up exactly where we left off.**
