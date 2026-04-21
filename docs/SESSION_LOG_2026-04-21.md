# Session Log — 2026-04-21

## Overview

Major code fix session: firmware detection, hashrate units, AV-2 Plant API discovery.
All items committed and pushed. Scan verified working.

---

## Fixes Completed

### 1. GitHub Secret Scanning ✅

**Problem:** Secret scanning was disabled on repo (commit bd47840 triggered alert).

**Fix Applied:**
- Enabled Secret Protection (Push protection + Alert scanning)
- Settings → Security → Code security → Secret scanning: ENABLED

---

### 2. Hashrate Units Fix (MH/s → TH/s) ✅

**Problem:** Database stores hashrate in MH/s, display needed TH/s (÷1000).

**Endpoints Fixed:**

| Line | Endpoint | Change |
|------|----------|--------|
| 415 | /metrics | Added hashrate/1000.0 in SQL |
| 521 | /metrics Python | Use hashrate_ths field |
| 1550-1551 | /query/fleet_summary | Added /1000 conversion |
| 1569 | /query/flagged_miners | Added /1000.0 in SQL |
| 1603 | /query/miner_history | Added /1000.0 in SQL |
| 1753 | /query/bottom_miners | Added /1000.0 in SQL |
| 2091 | /ask | Added /1000.0 in SQL |

**Commit:** 332134e fix: Convert hashrate from MH/s to TH/s in all API endpoints

---

### 3. Firmware Detection Fix (Offline Miners) ✅

**Problem:** 20 miners showed empty firmware fields in DB.

**Root Cause:** AMS API returns empty firmware for offline miners.

**Fix:** Added fallback to historical data in save_scan():
- Check if AMS returns empty firmwareManufacturer
- If empty, query miner_readings for last known firmware
- Use historical value in current reading

**Verification:**
- Before: 29/49 miners with firmware
- After: 49/49 miners with firmware ✅
- All 20 offline miners now show BIXBIT firmware from history

**Commit:** 557e037 fix: Fallback to historical firmware data for offline miners

---

### 4. AV-2 Plant Client Implementation ✅

**Problem:** S19J Pro Container HVAC had no data collection client.

**Discovery:** Used Chrome DevTools to capture API:
- Endpoint: POST /eclypse/dgapi
- Auth: Session + Basic (BigStar/BigSt@r2020)
- Format: Subscription-based polling

**Data Paths Implemented:**

| Path | Description |
|------|-------------|
| /Data/Plant/OAT | Outside Air Temp (°F) |
| /Data/Plant/ContainerSpaceTemp | Container Ceiling (°F) |
| /Data/Plant/CDWST | Supply Temp (°F) |
| /Data/Plant/CDWRT | Return Temp (°F) |
| /Data/Plant/CWP1_Fdbk | CW Pump 1 Speed (%) |
| /Data/Plant/CWP2_Fdbk | CW Pump 2 Speed (%) |
| /Data/Plant/CT1VSDFdbk | CT Fan Speed (%) |

**File:** clients/av2_plant_client.py

**Note:** VPS cannot reach 192.168.189.x directly - requires ROBS-PC Tailscale route.

**Commit:** aa4830e feat: Implement AV-2 Plant client for S19J Pro Container HVAC

---

## Git Commits

| Commit | Description |
|--------|-------------|
| 332134e | fix: Convert hashrate from MH/s to TH/s in all API endpoints |
| 557e037 | fix: Fallback to historical firmware data for offline miners |
| aa4830e | feat: Implement AV-2 Plant client for S19J Pro Container HVAC |

---

## Services Restarted

- mining-guardian: Restarted to apply firmware fix
- dashboard-api: (if needed after hashrate fix - verify)

---

## Remaining Tasks

| Task | Status |
|------|--------|
| Power cycle miner 53476 (.31) | PENDING (facility, rain delayed) |
| Signal 6 (hashrate volatility) | PENDING |
| HIGH_OFFLINE_FREQUENCY_PATTERN | PENDING |
| Thursday Apr 24: HVAC complete | SCHEDULED |
| May 5-9: Mac Mini ETA | SCHEDULED |

---

## Scan Verification

Scan #1671 completed successfully:
- 49 miners total
- 29 online / 20 offline
- All 49 miners have firmware data ✅
- Hashrate displaying in TH/s ✅

---

*Session completed: April 21, 2026*
