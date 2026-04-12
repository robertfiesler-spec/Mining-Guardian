# Mining Guardian Cron Schedule

Last Updated: April 12, 2026

## Daily Schedule Overview

| Time | Job | Script | Purpose |
|------|-----|--------|---------|
| **10:00 AM** | AMS Log Cleanup | scripts/cleanup_ams_logs.py | Delete all logs from AMS to prevent "too many log files" errors |
| **1:00 PM** | Daily Log Collection | scripts/daily_collect_logs.py | Fresh miner.log export from all online miners |
| **4:00 PM** | Qwen Deep Dive | ai/daily_deep_dive.py | Pass 1: Per-miner + fleet analysis via local LLM |
| **12:00 AM** | Claude Training | ai/weekly_train.py | Pass 2: Cohort synthesis + pattern discovery via Claude API |
| **1:00 AM** | Refinement Chain | ai/refinement_chain.py | Pass 3+4: Qwen reflection + Claude final merge |
| **4:00 AM** | Knowledge Backup | ai/backup_knowledge.py | Push knowledge.json to GitHub |
| **7:00 AM** | Morning Briefing | scripts/morning_briefing.py | Slack summary of overnight activity |

## Detailed Job Descriptions

### 10:00 AM — AMS Log Cleanup
**Script:** scripts/cleanup_ams_logs.py  
**Log:** /tmp/ams_cleanup.log  
**Purpose:** 
- Deletes ALL log files from AMS for every miner
- Prevents "too many log files" error (AMS has a per-miner limit)
- Safe because logs are already stored in guardian.db after download
- Must run BEFORE 1pm log collection

**Added:** April 12, 2026

---

### 1:00 PM — Daily Log Collection
**Script:** scripts/daily_collect_logs.py  
**Log:** /tmp/daily_log_collection.log  
**Purpose:**
- Triggers fresh miner.log export for every online miner
- Downloads and stores logs in guardian.db (miner_logs table)
- Parses hardware identity (PSU serial, PCB rev, chip bins)
- Critical for AI learning — fresh logs contain PSU voltages, chain events, errors

**Configuration:**
- 10 parallel workers (reduced from 15 on April 12)
- 10-minute timeout per miner (Pass 1)
- 20-minute timeout for retry pass (Pass 2)
- Slack report sent for any miners that fail

**Runtime:** ~30-60 minutes depending on fleet size

---

### 4:00 PM — Qwen Daily Deep Dive (Pass 1)
**Script:** ai/daily_deep_dive.py  
**Log:** /tmp/daily_deep_dive.log  
**Purpose:**
- Analyzes EVERY miner individually using local Qwen LLM
- Uses: fresh logs + telemetry + fingerprints + operator rules
- Generates per-miner analysis + fleet synthesis
- Stored in knowledge.json under daily_deep_analyses

**Runtime:** 6-8 hours for full fleet (~40 miners)

---

### 12:00 AM (Midnight) — Claude Training (Pass 2)
**Script:** ai/weekly_train.py  
**Log:** /tmp/daily_claude_training.log  
**Purpose:**
- Groups miners into cohorts (by model, cooling, firmware)
- Cross-references Qwen's analysis with full fleet data
- Synthesizes patterns, validates predictions, discovers correlations
- Uses Claude API for advanced reasoning

**Runtime:** ~30-60 minutes

---

### 1:00 AM — Refinement Chain (Pass 3 & 4)
**Script:** ai/refinement_chain.py  
**Log:** /tmp/daily_refinement_chain.log  
**Purpose:**
- Pass 3: Qwen reflects on Claude's synthesis
- Pass 4: Claude merges reflection into final knowledge update
- Ensures both AI tiers contribute to learning

**Runtime:** ~10-15 minutes

---

### 4:00 AM — Knowledge Backup
**Script:** ai/backup_knowledge.py  
**Log:** /tmp/knowledge_backup.log  
**Purpose:**
- Pushes knowledge.json to GitHub
- Ensures no knowledge loss if VPS fails
- Maintains version history of AI learning

---

### 7:00 AM — Morning Briefing
**Script:** scripts/morning_briefing.py  
**Log:** /tmp/morning_briefing.log  
**Purpose:**
- Sends Slack summary of overnight activity
- Includes: fleet health, issues, predictions, actions taken

---

## Data Retention

| Data | Location | Retention |
|------|----------|-----------|
| AMS logs | BiXBiT AMS | Deleted daily at 10am |
| DB logs (miner_logs) | guardian.db | 30 days (auto-purged) |
| Telemetry (miner_readings) | guardian.db | Permanent |
| Knowledge (knowledge.json) | VPS + GitHub | Permanent |

---

## Notes

- All times are CDT (Central Daylight Time)
- The accelerated daily training schedule (midnight Claude) is temporary — scheduled to revert to Sunday-only after April 25, 2026
- Log files in /tmp/ are not persistent across reboots but are useful for debugging
