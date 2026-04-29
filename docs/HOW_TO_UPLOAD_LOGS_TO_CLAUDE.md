# How to Upload Logs to Claude for Analysis

This is the workflow Bobby uses today to get a miner log analyzed by Claude
during a Mining Guardian session. It works for ANY format — PDF, zip, tar.gz,
text, json, csv, image — and ANY brand — BiXBiT, Auradine, stock Antminer,
WhatsMiner, future vendors.

This is the **manual interactive workflow**. The fully automated drag-and-drop
ingestion system is described in `OPEN_LOG_UPLOADER_VISION.md` and is a
post-demo build.

---

## The 3-step flow

### Step 1 — Get the file onto Bobby's Mac

Whatever method works for you, doesn't matter to Claude:
- Download from the miner's web UI (Auradine: Support → Display logs → Copy,
  or the green "Download Tech Support File" button)
- AMS export from the BiXBiT staging dashboard
- Email attachment forwarded by a repair shop friend
- USB stick from a site visit
- `scp` from another machine

End state: file lives somewhere on Bobby's Mac, usually `~/Downloads/`.

### Step 2 — Tell Claude the file exists and where

In the Claude chat, send a message that includes:

1. **The filename** (or a description of it)
2. **Where it is** (Downloads, Desktop, a specific folder)
3. **What miner it's from** if you know
4. **What you want done with it** (diagnose, compare to another log,
   extract specific info, etc.)

Example messages that work:

> "I just dropped `log 1.pdf` in Downloads. It's from the AH3880 at
> 192.168.188.28. Run a full diagnosis."

> "There are 4 logs in `~/Downloads/repair_shop_batch/`. They're from
> mixed S19j Pros with various complaints. Triage them and tell me
> which ones are real hardware faults vs misconfig."

> "I exported `cglog_53487_pre.zip` and `cglog_53487_post.zip` from
> AMS. Compare them and tell me what changed."

Claude has filesystem access to `/Users/BigBobby/` (configured in the
MCP `Filesystem` server) so once you tell Claude where the file is, Claude
can read it directly. **No upload through the chat UI required for files
under `/Users/BigBobby/`.**

### Step 3 — Claude reads and analyzes

Claude will:
1. Run `Filesystem:get_file_info` to confirm size + type
2. Read the file (`Filesystem:read_text_file` for text, `bash_tool` + a
   helper script for PDFs/binary)
3. For PDFs: copy to the operational DB host via `scp`, extract with pdfplumber (historically the VPS; now Mac Mini local-first)
4. For zip/tar.gz: extract in-memory
5. Detect miner type from content
6. Run dual-model analysis (Qwen + Claude)
7. Save findings to the production DB and `knowledge.json`
8. Post results to Slack `#mining-guardian-alerts`
9. Report back in the chat with the verdict

---

## What works today (Apr 8, 2026)

- ✅ Plain text logs (`.txt`, `.log`)
- ✅ PDF tech support files (any size — 18 MB / 3,534 pages tested live)
- ✅ Zip / tar.gz / tar (extracted in-memory)
- ✅ Single file or whole folder
- ✅ Auto-detect: BiXBiT cglog format, Auradine FluxOS DVFS format,
  Stock Antminer kern.log format
- ✅ Dual-model analysis via Qwen 2.5 32B (local on Windows PC RTX 4090)
  AND Claude Sonnet 4.6 (Anthropic API)
- ✅ Results stored permanently in `miner_logs` table (Postgres on Mac Mini; historical VPS era used SQLite `guardian.db`)
- ✅ Analysis insights stored in `knowledge.json` for future training
- ✅ Slack notification with side-by-side Qwen/Claude verdicts

## What does NOT work yet (planned post-demo)

- ❌ Drag-and-drop UI on the AI dashboard (planned: Phase 1 of Open Log
  Uploader vision)
- ❌ Folder watcher that picks up files dropped into a designated `inbox/`
- ❌ Email IMAP ingestion
- ❌ Slack file-upload pickup (drag a file into `#mining-guardian-alerts`
  and have it auto-process)
- ❌ Web spec lookup to build `model_specs` entries for unknown miner models
- ❌ Bulk ingestion worker pool for repair-shop-style 1000+ log dumps
- ❌ Cross-log pattern promotion (after N similar findings → known_pattern)

All of these are documented in `OPEN_LOG_UPLOADER_VISION.md` and will be
built in 4 phases over 2-4 weeks after the customer demo lands.

---

## Worked example: `log 1.pdf`

What Bobby did on April 8, 2026 at 06:56 CDT:

1. Downloaded the AH3880 tech support file from the miner's web UI to
   `~/Downloads/log 1.pdf` (18,297,418 bytes, 3,534 pages)
2. Sent Claude a message: "its in downloads as log 1, and pop up
   whatever permissions you need"
3. Claude:
   - Confirmed file via `Filesystem:get_file_info` (18.3 MB)
   - Copied to VPS via `scp` (because the PDF needed pdfplumber and
     the local Mac didn't have it installed) — historical Apr 8 workflow; Mac Mini (2026-04-30 install) runs pdfplumber locally
   - Extracted text with pdfplumber: 12.3 MB / 197,667 lines
   - Computed parser fact sheet: 726 DVFS alarms, 53 PowerState alarms,
     44,901 Board 3 zero-voltage events, hashrate 0–555 TH/s avg 358
   - Saved into `miner_logs` as `auradine_28` / `diagnostic`
   - Built an 80 KB sample (start window + middle window + end window)
   - Sent to Qwen 2.5 32B via local Ollama → 41 sec, 648 char verdict
   - Sent to Claude Sonnet 4.6 via Anthropic API → 25 sec, 3,290 char verdict
   - Stored both in `knowledge.json`
   - Reported back in chat with the side-by-side comparison

**Total elapsed time from "go read it" to "here's the verdict": about 90
seconds of LLM time + parsing time.** Most of the wall clock was spent
copying the 18 MB PDF to the VPS over the SSH tunnel. (Historical Apr 8 note — VPS decommissioned for MG; Mac Mini is now the operational host.)

---

## Tips

- **Big PDFs are fine.** Tested live up to 18 MB / 3,534 pages. The
  workflow handles them.
- **Don't pre-process.** Just tell Claude the filename and let the
  pipeline detect the format. Pre-extracting or re-formatting usually
  loses information the parser needs.
- **Naming matters a little.** A filename like `AH3880_techsupport_*.pdf`
  helps the auto-detector reach a confident answer faster than `log 1.pdf`,
  but both work.
- **Multiple files at once is fine.** Just list them in the message:
  "compare `cglog_pre.zip` and `cglog_post.zip` from Downloads"
- **Operator context matters.** If you know something the log doesn't
  show — "this miner crashed twice yesterday after a power blip" —
  say so in the message. Both LLMs use the operator context as part of
  the diagnostic prompt.
- **Disagreements are valuable.** If Qwen and Claude reach different
  verdicts, that's a training data point, not a bug. Both verdicts get
  stored separately so the cohort training can use the disagreement
  pairs to improve Qwen's prompts over time.
