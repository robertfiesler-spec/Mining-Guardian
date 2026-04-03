# Mining Guardian — Miner Profile Map
# COMPLETED April 2, 2026 — all answers confirmed and built into config.json
# Kept for reference only.

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## YOUR FLEET BREAKDOWN (from scan data):

### 1. Antminer S19J Pro (BiXBiT firmware) — ~36 miners
### 2. Antminer S19J Pro (Stock firmware) — 5 miners
### 3. Antminer S19j Pro (different AMS name) — 4 miners
### 4. Teraflux AH3880 (Auradine firmware) — 2 miners
### 5. Antminer S21 EXP Hydro (BiXBiT firmware) — 2 miners
### 6. Antminer S21 Immersion (BiXBiT firmware) — 2 miners

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## QUESTIONS FOR EACH MINER MODEL:

### Model 1: Antminer S19J Pro (BiXBiT firmware)

**Q1.** How many distinct TH/s profiles can this model run?
  - We've seen: 118, 133, 134, 138, 139, 144, 149, 154 TH/s
  - Are ALL of these valid profiles, or are some errors/transitional states?

**Q2.** For each valid profile, what is the RATED TH/s?
  - Example: "139 TH/s - ~4501 W" → rated = 139 TH/s
  - Some profiles show MHz instead of watts (e.g., "133 TH/s - 707 MHz") — is that a valid profile or a display bug?

**Q3.** What is the DEFAULT profile these miners should run at?
  - Is there a "standard" TH/s setting for your facility?

**Q4.** What is the MAX safe TH/s for this model in your liquid cooling setup?

**Q5.** What is the MIN TH/s you'd ever run (efficiency floor)?

**Q6.** At what chip temperature should Mining Guardian recommend lowering the profile?
  - Currently using 76°C for yellow, 86°C for red
  - Are these thresholds right for liquid-cooled S19J Pros?

**Q7.** How many hashboards does this model have? (Expecting 3)

**Q8.** Are there any S19J Pros that are KNOWN to have different specs?
  - Different batch, revision, or custom configuration?

---

### Model 2: Antminer S19J Pro (Stock firmware — 5 miners)

**Q9.** Why are these 5 on Stock firmware instead of BiXBiT?
  - Plan to flash them, or staying on Stock?

**Q10.** Since Stock firmware doesn't expose profiles through AMS, how do you currently manage their TH/s?
  - Through the miner's web UI directly?
  - CGMiner API?

**Q11.** What profile/TH/s are these 5 miners running at?

**Q12.** Same temp thresholds as the BiXBiT ones? (76°C yellow, 86°C red)

---

### Model 3: Teraflux AH3880 (Auradine firmware — 2 miners)

**Q13.** These show profile "turbo" — what is the rated TH/s for "turbo" mode?

**Q14.** What other profiles does the AH3880 support? 
  - Names and their TH/s ratings (e.g., turbo = ??? TH/s, normal = ??? TH/s, eco = ??? TH/s)

**Q15.** These are on PDU 163, outlets 3 and 4 — confirmed correct?

**Q16.** What port/API does the Auradine firmware expose?
  - Port 8443 with HTTPS? REST API? Different from Bitmain?

**Q17.** How many hashboards does the AH3880 have?

**Q18.** What chip temp thresholds should we use for the AH3880?
  - Same as S19J Pro or different?

---

### Model 4: Antminer S21 EXP Hydro (BiXBiT firmware — 2 miners)

**Q19.** Profiles seen: 385 TH/s, 429 TH/s, 440 TH/s — are ALL valid?

**Q20.** What is the DEFAULT profile for these?

**Q21.** What is the MAX rated TH/s?

**Q22.** These are hydro-cooled — what chip temp thresholds?
  - Hydro cooling typically runs cooler — should yellow/red be different?

**Q23.** How many hashboards does the S21 EXP Hydro have?

**Q24.** These are on PDU 164, outlets 3 and 4 — confirmed correct?

---

### Model 5: Antminer S21 Immersion (BiXBiT firmware — 2 miners)

**Q25.** Profiles seen: 355 TH/s (610 MHz), 360 TH/s (6480 W) — both valid?

**Q26.** What is the DEFAULT and MAX profile?

**Q27.** These are in the immersion tank on ports 19 and 20 — what chip temp thresholds for immersion?
  - Immersion cooling runs much cooler — should we adjust?

**Q28.** How many hashboards does the S21 Imm have?

---

### GENERAL FLEET QUESTIONS:

**Q29.** What hashrate percentage should trigger a RESTART recommendation?
  - Currently: below 90% of rated TH/s
  - Too aggressive? Too lenient? 

**Q30.** What hashrate percentage should trigger a MONITOR (yellow) vs RESTART (action)?
  - Currently: 85-90% = yellow monitor, below 85% = restart
  - Right thresholds?

**Q31.** Should Mining Guardian auto-execute restarts for obvious issues (0% hashrate, all boards dead) without waiting for approval? Or always wait?

**Q32.** Are there any miners that should be EXCLUDED from scanning?
  - Test miners, broken miners waiting for parts, etc.

**Q33.** For the "A2" model showing in AMS for miner 53476 at .31 — this is actually an S19J Pro, correct? Is this a known AMS bug or a different hardware unit?

**Q34.** Any miners planned to be added or removed from the fleet in the next month?
