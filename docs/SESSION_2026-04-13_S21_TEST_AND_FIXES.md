> ## ⚠️ Historical session log from 2026-04-13
>
> VPS references in this document reflect that day’s architecture. Current state is **Mac Mini local-first** (D-14, install 2026-04-30). The VPS (`root@srv1549463` / 187.124.247.182 / Tailscale 100.106.123.83) has been decommissioned for Mining Guardian; Bobby still uses it for his own facility. Body preserved verbatim as a historical record.

# SESSION LOG — April 13, 2026
## S21 Immersion Stock Test Status + Critical Fixes

**Time:** ~4:15pm - 4:40pm CDT
**Operator:** Bobby (Rob Fiesler)
**Focus:** S21 Imm stock test documentation + 4pm cron job repair

---

## S21 IMMERSION STOCK TEST STATUS

### Test Overview
**Started:** This morning ~8am CDT (April 13, 2026)
**Purpose:** Prove BiXBiT firmware is more efficient at stock profiles than stock firmware
**Status:** RUNNING — environmental data collection only
**Phase:** Stock baseline (Phase 1 of planned 4-phase test)
**Next Action:** Continue at stock until tomorrow morning

### Current Performance (as of 4:27pm)

From AMS screenshots provided by operator:

**Miner .22 (192.168.188.22):**
- Profile Set: 217 TH/s
- Actual Hashrate: 221.22 TH/s
- Miner-Reported Power: 3,375 W
- PDU-Measured Power: 3,300 W (Tank B100 Port 19)
- Chip Temp: 56°C, Board: 41°C

**Miner .23 (192.168.188.23):**
- Profile Set: 208 TH/s  
- Actual Hashrate: 218.29 TH/s
- Miner-Reported Power: 3,351 W
- PDU-Measured Power: 3,100 W (Tank B100 Port 20)
- Chip Temp: 55°C, Board: 39°C

### Key Finding
**PDU power is LOWER than miner-reported:**
- .22: 3,300W vs 3,375W (75W less)
- .23: 3,100W vs 3,351W (251W less)

PDU power = TRUE wall consumption for efficiency calculations (J/TH)

---

## CRITICAL FIX: 4PM DAILY DEEP DIVE CRON

### Problem
4pm cron crashed immediately at 16:00:01 with:
```
TypeError: build_per_miner_prompt() got an unexpected keyword argument 'facility'
```

### Fix Applied (16:35 CDT)
File: ai/daily_deep_dive.py line 403
Added: facility: Optional[Dict] = None parameter

### Result
✅ Deep dive started 16:35:14, PID 421612
✅ Processing 29 miners
✅ Expected completion ~3-4 hours

---

## DATA COLLECTION ISSUES

**Issue 1:** Database hashrate stored in MH/s but code treats as TH/s
**Issue 2:** CSV generation attempted with incorrect calculations
**Resolution:** Operator will create CSV manually for Thursday customer meeting

---

## CLEANUP
Removed temp CSV files from Desktop:
- s21_imm_stock_test.csv
- S21_Imm_Stock_Test_Customer.csv

---

## SYSTEM STATUS (4:40pm)

**All Services:** ✅ RUNNING
**Deep Dive:** ✅ ACTIVE (PID 421612)
**Fleet:** 29 miners online
**Test:** S21 Imm stock baseline continuing

**Session End:** 4:40pm CDT

---

## S19J PRO CONTAINER HVAC INVESTIGATION (6:16pm - 6:30pm)

### Discovery
The S19J Pro Container at 192.168.189.235 is **NOT** a Distech Eclypse BACnet controller like the warehouse system.

**Actual System:** Big Star BlockChain AV-2 Plant
- Custom web interface at https://192.168.189.235
- Same credentials as warehouse (BigStar/BigSt@r2020)
- Completely different API structure

**Visible Readings (from web interface):**
- Outside Air: 86.8°F
- Container Cooling: 98.6°F
- Supply: 91.3°F
- Return: 105.7°F
- Delta-T: +14.4°F

### Tailscale Route Fix ✅
- Added 192.168.189.0/24 to ROBS-PC advertised routes
- Approved route in Tailscale admin console
- VPS can now ping 192.168.189.235 successfully

### Work Started
Created `/root/Mining-Gaurdian/clients/av2_plant_client.py`
- Custom scraper for AV-2 Plant interface
- Designed to extract temps from web interface
- **Status: IN PROGRESS** - needs API endpoint discovery

### Resolution
**POSTPONED TO TOMORROW (April 14, 2026)**

Operator Bobby requested we tackle this tomorrow. Need to:
1. Use browser dev tools to find actual data API endpoint
2. Update av2_plant_client.py with correct URL
3. Integrate into hvac_client.py poll_all_systems
4. Test and deploy

---

## TOMORROW'S TASK LIST (April 14, 2026)

### PRIMARY TASKS
1. **Complete 209-finding audit**
   - Work through remaining HIGH priority items
   - Move systematically through MEDIUM → LOW
   - Close entire audit

2. **S19J Pro Container HVAC (CONTINUED)**
   - Find AV-2 Plant data API endpoint (browser dev tools)
   - Complete av2_plant_client.py implementation
   - Wire into hvac_client.py
   - Test and deploy
   - Verify scan reports show real temps

3. **S21 Imm Stock Test**
   - Check test status after overnight stock run
   - Decide on Phase 2 transition timing
   - Operator creating CSV manually for Thursday customer meeting

### SYSTEM VERIFICATION
- Verify tonight's 4pm deep dive completed (~18:37 CDT)
- Check knowledge.json for daily_deep_analyses results
- Confirm all 8 services running

### TECHNICAL DEBT
- GitHub push (handle secret scanning alert from commit bd47840)
- Database hashrate units fix (MH/s → TH/s conversion)

### ONGOING OPERATIONS
- Overnight automation (24hr test mode)
- Hourly fleet scans
- Daily log collection (29 miners with fresh logs)

---

**Session End:** 6:31pm CDT  
**Total Time:** ~2h 16min (4:15pm - 6:31pm)

**Files Created/Modified:**
- /root/Mining-Gaurdian/docs/SESSION_2026-04-13_S21_TEST_AND_FIXES.md
- /root/Mining-Gaurdian/clients/av2_plant_client.py (in progress)
- /root/Mining-Gaurdian/ai/daily_deep_dive.py (bug fix line 403)

**Critical Fixes:**
- 4pm daily deep dive cron job (missing facility parameter)
- Tailscale route for 192.168.189.0/24 network

**Discoveries:**
- S19J Pro Container uses Big Star BlockChain AV-2 Plant (not Eclypse)
- Database stores hashrate in MH/s (code treats as TH/s)
- S21 Imm PDU power lower than miner-reported (efficiency metric)


---

## S19J PRO CONTAINER HVAC FIX - IN PROGRESS (18:30 CDT)

### Root Cause Discovery
S19J Pro Container at 192.168.189.235 is **NOT a Distech Eclypse controller**.

**What it actually is:**
Big Star BlockChain AV-2 Plant - custom web interface

**Current readings visible on web UI:**
- Supply: 91.3°F
- Return: 105.7°F
- Delta-T: +14.4°F
- Outside Air: 86.8°F
- Container Cooling: 98.6°F

### Work Completed
1. ✅ Tailscale route fix - Added 192.168.189.0/24 to ROBS-PC advertised routes
2. ✅ Route approved in Tailscale admin console
3. ✅ VPS can now reach 192.168.189.235
4. ✅ Created `/root/Mining-Gaurdian/clients/av2_plant_client.py` - custom scraper skeleton

### Work Remaining (Tomorrow)
**File:** `/root/Mining-Gaurdian/clients/av2_plant_client.py`

**Status:** Basic scraper structure created, needs:
1. Discover actual API endpoint or data source from AV-2 Plant web interface
2. Parse temperature data (supply/return/outside/container)
3. Integrate into `hvac_client.py` as new system type
4. Test data extraction
5. Update scan report formatting for S19J Pro Container section

**How to complete:**
- Use browser DevTools (F12) on https://192.168.189.235 to find API calls
- Or view page source to find where temps are loaded from
- Update `av2_plant_client.py` with correct endpoints/parsing
- Wire into main HVAC polling system

**Priority:** MEDIUM - S19JPros are offline anyway, but would be nice to show HVAC data

