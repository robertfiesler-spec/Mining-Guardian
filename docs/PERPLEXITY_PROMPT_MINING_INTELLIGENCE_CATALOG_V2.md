# Mining Intelligence Catalog — Comprehensive Database Design Prompt

> **HISTORICAL — design-phase prompt sent to Perplexity (April 2026).** Kept verbatim as the source-of-record for the catalog schema brainstorm. The architecture sections below describe the original Windows / ROBS-PC design intent. The live catalog now runs on PostgreSQL 16 on the Mac Mini under `intelligence-catalog/` (operational + reference DBs colocated, no SQLite, no Tailscale data plane). For the current architecture see `README.md`, `CLAUDE.md`, and `docs/INTELLIGENCE_CATALOG_STATUS.md`.

## Context for the AI

I'm building the **Mining Intelligence Catalog**, a PostgreSQL database that will become the **single source of truth for everything known about Bitcoin ASIC miners**. This isn't just a spec sheet lookup — it's a knowledge base that captures manufacturer data, real-world operational experience, community feedback, repair intelligence, firmware quirks, and lessons learned from thousands of deployments.

Mining Guardian (my monitoring system) will query this database, but it's designed to be valuable beyond just my use case — it could eventually serve the entire mining industry.

---

## Design Philosophy

**Capture everything. Discard nothing.**

If someone somewhere has learned something useful about a miner model, chip variant, firmware version, or failure pattern — it belongs in this database. We're building institutional knowledge that compounds over time.

---

## CATEGORY 1: Miner Hardware Intelligence

### 1.1 Miner Models (comprehensive specs)

Every ASIC model ever made, with full specifications:

**Core Identity:**
- Manufacturer (Bitmain, MicroBT, Canaan, Auradine, Iceriver, etc.)
- Model family (S19, S21, M50, A14, etc.)
- Model variant (S19J Pro, S19J Pro+, S19 XP, S19 Hydro, etc.)
- Generation/series
- Release date
- End of production date
- MSRP at launch
- Current market value range

**Hardware Specs:**
- Algorithm (SHA-256, Scrypt, Ethash, etc.)
- Chip architecture (BM1362, BM1366, etc.)
- Process node (5nm, 7nm, etc.)
- Total chip count
- Board count (typically 3, sometimes 2 or 4)
- Chips per board
- Stock hashrate (TH/s or GH/s)
- Max hashrate (with tuning/OC)
- Min hashrate (efficiency mode)
- Stock power consumption (Watts)
- Max power consumption
- Efficiency at stock (J/TH)
- Best achievable efficiency
- Voltage range
- Frequency range

**Cooling Specs:**
- Cooling type (air, hydro, immersion-ready, immersion-native)
- Fan count and size
- Airflow requirements (CFM)
- Water flow requirements (GPM for hydro)
- Inlet water temp requirements
- Operating ambient temp range
- Operating humidity range

**Physical:**
- Dimensions (L x W x H)
- Weight
- Noise level (dB)
- Rack unit size
- Power connector type(s)
- Network interface (Ethernet speed)
- Control board model

**Certifications & Compliance:**
- FCC certification
- CE marking
- UL listing
- RoHS compliance
- Energy efficiency ratings


### 1.2 Chip/ASIC Intelligence

Every chip variant with quality and performance data:

- Chip model (BM1362, BM1366, etc.)
- Manufacturer
- Process node
- Die size
- Transistor count
- TDP per chip
- Voltage range
- Frequency range
- Known silicon lottery bins (bin 1, 2, 3, etc.)
- Expected hashrate per chip
- Expected efficiency per chip
- Known defect patterns
- Date codes and what they mean
- Fab location (if known)

### 1.3 Board/PCB Intelligence

- PCB version codes (0110, 0130, etc.) and what they mean
- BOM version codes (0010, 0020, etc.) and what they mean
- Known good combinations
- Known bad combinations (with evidence)
- Manufacturing date ranges for each version
- Component changes between versions
- Failure rates by version (if data available)

### 1.4 PSU Intelligence

- Compatible PSU models per miner
- Wattage requirements
- Voltage rail configurations
- Connector types
- Known failure modes
- Quality tiers (OEM vs aftermarket)
- Efficiency ratings

### 1.5 Control Board Intelligence

- Control board models
- Compatible miners
- Firmware compatibility
- Known issues
- LED status codes and meanings
- Diagnostic features

---

## CATEGORY 2: Firmware Intelligence

### 2.1 Firmware Variants

Every firmware option for each model:

**Identity:**
- Firmware name (Stock, BiXBiT, VNish, Braiins OS, LuxOS, etc.)
- Version history
- Supported models
- Developer/vendor
- License type (free, paid, subscription)
- Official download source

**Capabilities:**
- API available (yes/no, type)
- API authentication method
- API endpoints and documentation
- Overclocking support (range)
- Underclocking/efficiency modes
- Auto-tuning features
- Immersion mode support
- Hashboard isolation support
- Remote reboot capability
- Profile management
- Power limiting features
- Temperature limiting features
- Fan control options

**Telemetry:**
- Chip-level temperature reporting
- Board-level voltage reporting
- Per-chip frequency reporting
- Power consumption accuracy
- Error logging detail level
- Historical data retention

**Known Issues:**
- Bugs by version
- Compatibility issues
- Security vulnerabilities
- Update problems
- Bricking risks


### 2.2 API Documentation

For each firmware that exposes an API:

- Base URL pattern
- Port number
- Authentication method (none, basic auth, token, cookie)
- Available endpoints with request/response schemas
- Rate limits
- WebSocket support
- Example code (Python, curl)
- Known quirks and workarounds

---

## CATEGORY 3: Operational Intelligence

### 3.1 Failure Patterns

The heart of predictive maintenance — every known failure mode:

**Symptom Signature:**
- Observable symptoms (array of tags)
- Telemetry patterns that indicate this failure
- How it presents differently across models
- Time from first symptom to failure

**Diagnosis:**
- Root cause
- Which component fails
- Why it fails
- Related failure modes (cascade failures)

**Resolution:**
- Recommended immediate action
- Repair procedure
- Parts needed
- Estimated repair cost
- Estimated repair time
- Can be repaired in field vs needs shop
- Success rate of repair

**Intelligence:**
- Which models affected
- Which firmware versions affected
- Which chip/board variants more prone
- Environmental factors that contribute
- How to prevent this failure

**Evidence:**
- Source of this knowledge
- Number of confirmed cases
- Confidence level
- Date first documented
- Date last updated

### 3.2 Operational Thresholds

What's normal vs concerning vs critical for each cooling type and model:

- Chip temperature thresholds (info/warning/critical)
- Board temperature thresholds
- Inlet water/air temperature limits
- Voltage thresholds (low/normal/high)
- Frequency deviation thresholds
- Hashrate deviation thresholds (% from baseline)
- Power consumption thresholds
- Fan speed thresholds
- Rejection rate thresholds
- Error rate thresholds

### 3.3 Environmental Correlations

What external factors affect performance:

- Ambient temperature impact curves
- Humidity impact
- Altitude impact (affects air cooling)
- Power quality impact (dirty power signatures)
- Seasonal patterns
- Time-of-day patterns


---

## CATEGORY 4: Community & Market Intelligence

### 4.1 User Reviews & Feedback

Aggregated sentiment from the mining community:

**Per Model:**
- Overall rating (1-5 stars)
- Reliability rating
- Efficiency rating
- Ease of use rating
- Value rating
- Number of reviews
- Review sources (Reddit, BitcoinTalk, Telegram groups, etc.)

**Common Praise:**
- What users like most
- Standout features
- Best use cases

**Common Complaints:**
- Recurring issues reported
- Design flaws noted
- Support experience
- Firmware complaints

**Quotes:**
- Notable user testimonials (good and bad)
- Expert reviews and opinions

### 4.2 Market Data

**Pricing History:**
- MSRP history
- Street price history
- Resale value trends
- Price vs hashrate trends
- Best/worst times to buy

**Availability:**
- Current availability status
- Lead times from manufacturer
- Authorized resellers
- Grey market sources
- Counterfeit warnings

### 4.3 Manufacturer Intelligence

**Per Manufacturer:**
- Company background
- Headquarters location
- Support quality rating
- Warranty terms by model
- RMA process
- Spare parts availability
- Typical response times
- Known disputes/lawsuits
- Financial stability indicators

---

## CATEGORY 5: Repair & Service Intelligence

### 5.1 Repair Procedures

Step-by-step repair guides:

- Procedure name
- Applicable models
- Required tools
- Required parts
- Skill level required
- Estimated time
- Step-by-step instructions
- Photos/diagrams (links)
- Common mistakes to avoid
- Safety warnings

### 5.2 Parts Database

**Components:**
- Part name
- Part number(s)
- Compatible models
- Function/purpose
- Failure rate (if known)
- Cost (new/refurb)
- Sources (authorized, aftermarket)
- Quality tiers
- Interchangeable alternatives

### 5.3 Repair Shop Intelligence

**Shop Directory:**
- Shop name
- Location
- Services offered
- Models specialized in
- Turnaround time
- Pricing tier
- Quality rating
- User reviews
- Contact info
- Warranty on repairs

### 5.4 Repair Statistics

Aggregated data from repair shops:

- Failure rates by model
- Failure rates by component
- Average repair cost by failure type
- Success rates by repair type
- Time to repair statistics


---

## CATEGORY 6: Pool & Network Intelligence

### 6.1 Mining Pools

**Pool Directory:**
- Pool name
- URL patterns
- Supported algorithms
- Fee structure
- Payout methods
- Minimum payout
- Payout frequency
- Server locations
- Uptime history
- Hash rate (market share)
- User reviews

**Technical:**
- Stratum versions supported
- Authentication methods
- Status API available
- Known error codes and meanings
- Configuration templates per model

### 6.2 Network Data

- Current network difficulty
- Difficulty history
- Block reward schedule
- Halving dates
- Profitability calculators reference

---

## CATEGORY 7: Facility & Infrastructure

### 7.1 Cooling Solutions

**Per Cooling Type (air, hydro, immersion):**
- Setup requirements
- Infrastructure costs
- Operating costs
- Maintenance requirements
- Compatible miner models
- Vendor options
- Performance impact (hashrate bonus/penalty)
- Reliability impact
- Resale value impact

**Immersion Fluids:**
- Fluid types
- Fluid vendors
- Cost per gallon
- Thermal properties
- Maintenance requirements
- Safety considerations

### 7.2 Power Infrastructure

- PDU recommendations
- UPS considerations
- Electrical requirements by model
- Power factor specifications
- Surge protection
- Monitoring solutions

### 7.3 HVAC Integration

- Cooling load calculations
- Airflow design patterns
- Heat recovery options
- Climate control strategies

---

## CATEGORY 8: Regulatory & Compliance

### 8.1 Legal Considerations

- Mining regulations by jurisdiction
- Tax implications
- Import/export restrictions
- Noise ordinances
- Zoning considerations
- Insurance requirements

### 8.2 Environmental

- Carbon footprint data
- Energy source considerations
- E-waste regulations
- Recycling options

---

## CATEGORY 9: Knowledge Sources & Attribution

### 9.1 Source Tracking

Every piece of data should be traceable:

- Source type (manufacturer, user report, repair shop, research, etc.)
- Source name/URL
- Date captured
- Confidence level (verified, unverified, disputed)
- Corroborating sources count
- Last verification date

### 9.2 Contribution Tracking

If this becomes community-driven:

- Contributor ID
- Contribution history
- Trust score
- Specializations


---

## Technical Requirements

### Database Engine
- **PostgreSQL 16** on the Mac Mini (live as of the 2026-04-30 install). Earlier design intent (above) considered ROBS-PC + a NAS migration; that path was retired when the install consolidated onto the Mini.
- Accessed locally via `localhost:5432`; remote operator access is via Tailscale to the Mini, but the catalog data plane stays on the loopback.

### Schema Features Needed
- **JSONB columns** for semi-structured data (API specs, symptoms, etc.)
- **Array columns** for tags, symptoms, compatible models lists
- **Full-text search** on descriptions, reviews, procedures
- **TSVECTOR indexes** for natural language queries
- **GIN indexes** for JSONB and array containment queries
- **Enum types** for categorical data (cooling_type, severity_level, etc.)
- **Audit columns** (created_at, updated_at, source_id) on all tables
- **Soft deletes** (deleted_at) to preserve history

### Query Patterns Mining Guardian Will Use

```sql
-- Get full specs for a model
SELECT * FROM miner_models 
WHERE model_name ILIKE '%S19J Pro%' OR aliases @> ARRAY['S19JPro'];

-- Find failure patterns matching observed symptoms
SELECT * FROM failure_patterns 
WHERE symptom_tags @> ARRAY['hashrate_zero', 'voltage_drop']
  AND (affected_models IS NULL OR affected_models @> ARRAY['S19JPro'])
ORDER BY confidence DESC, cases_documented DESC;

-- Get temperature thresholds for a cooling/model combo
SELECT * FROM operational_thresholds 
WHERE cooling_type = 'hydro' 
  AND (model_filter IS NULL OR model_filter = 'S19JPro');

-- Search community knowledge for a topic
SELECT * FROM knowledge_base 
WHERE search_vector @@ plainto_tsquery('english', 'S19 overheating fix')
ORDER BY ts_rank(search_vector, plainto_tsquery('english', 'S19 overheating fix')) DESC;

-- Get firmware API info
SELECT api_spec FROM firmware_reference 
WHERE firmware_name = 'BiXBiT' AND version_prefix = '0.1';

-- Check if a PCB/BOM combo is problematic
SELECT * FROM board_quality_intel 
WHERE pcb_version = '0110' AND bom_version = '0020';

-- Get repair shops near a location
SELECT * FROM repair_shops 
WHERE services @> ARRAY['hashboard_repair']
  AND ST_DWithin(location, ST_MakePoint(-97.4, 32.7)::geography, 500000);  -- 500km radius
```

### Access Patterns
- **Mining Guardian (read-only):** Simple key lookups, symptom matching, threshold queries
- **Admin (read-write):** Bulk data loads, updates, manual curation
- **Future API (read-only):** REST API for community access

---

## Data Sources to Import

### Manufacturer Data (Tier 1 - Most Reliable)
- Bitmain spec sheets (PDF scraping)
- MicroBT spec sheets
- Canaan spec sheets  
- Auradine spec sheets
- Official documentation

### My Operational Data (Tier 2 - Verified by Experience)
- config.json model profiles
- knowledge.json refined_insights
- knowledge.json patterns
- knowledge.json known_issues
- `hardware.miner_models` table in the catalog (formerly `miner_hardware` in the legacy local DB)
- Action audit log outcomes

### Repair Shop Data (Tier 3 - High Volume)
- 1M+ data points from repair partners (format TBD)
- Component failure rates
- Repair success rates

### Community Data (Tier 4 - Needs Verification)
- Reddit r/BitcoinMining posts
- BitcoinTalk forums
- Telegram group discussions
- Discord server knowledge
- YouTube teardowns and reviews
- Mining blog posts

### Market Data (Tier 5 - External APIs)
- eBay/marketplace pricing
- Manufacturer pricing
- Network difficulty APIs


---

## Schema Design Questions for Perplexity

1. **Model Variants:** How do I model the relationship between S19J Pro, S19J Pro+, S19 XP when they share many specs but differ in key areas? Inheritance? Separate rows with parent reference?

2. **Versioned Data:** Specs change (firmware updates, etc.). Do I version every field, use SCD Type 2, or just track updates in a history table?

3. **Multi-Source Truth:** When manufacturer says one thing and community reports another, how do I model conflicting data points?

4. **Symptom Matching:** Failure patterns have symptoms like "hashrate at 0%", "board voltage < 11.5V", "chip temp spike > 95°C". What's the best structure for efficient symptom-to-diagnosis queries?

5. **Fuzzy Model Matching:** AMS reports "Antminer S19j Pro", config uses "S19JPro", user says "S19J Pro". I need aliases and fuzzy matching. Best approach?

6. **Geographic Data:** For repair shops, do I need PostGIS, or is a simpler lat/long with distance calculation sufficient?

7. **Review Aggregation:** How do I store individual reviews vs aggregated ratings? Separate tables? JSONB array?

8. **API Specs:** Firmware API documentation is complex (endpoints, params, responses). JSONB blob? Structured tables?

9. **Part Compatibility:** "Part X works with Models A, B, C" — many-to-many or array column?

10. **Search Strategy:** For natural language queries like "S19 running hot after firmware update", what combination of full-text search, trigram similarity, and semantic search should I use?

---

## What I Need From You

1. **Complete PostgreSQL schema** — CREATE TABLE statements with appropriate types, constraints, and indexes

2. **Enum definitions** — For categorical fields (cooling_type, severity, confidence, etc.)

3. **Index strategy** — Which indexes for my query patterns, including GIN for arrays/JSONB

4. **Example INSERTs** — Show me how to load a complete miner model with all related data

5. **Python query patterns** — psycopg2 examples for the queries Mining Guardian will run

6. **Migration strategy** — How to load my existing config.json and knowledge.json data

7. **Normalization decisions** — What to normalize vs denormalize for my read-heavy use case

8. **Future-proofing** — Schema design that can grow as I add more data sources

---

## Constraints & Context

- This is a **read-heavy reference database**, not OLTP
- Data changes slowly (new models quarterly, patterns weekly)
- Mining Guardian queries via **psycopg2** — no ORM
- Must work on **Windows PostgreSQL 16** initially
- Will migrate to **NAS** (Linux-based) in July 2026
- Network access via **Tailscite** VPN
- Original (April 2026) starting point: data lived in a legacy local DB plus **JSON** (`knowledge.json`, `config.json`). Migration to PostgreSQL was completed before the Mac Mini install.

---

## The Vision

This database should be **the Wikipedia of Bitcoin mining hardware** — if it's been learned about an ASIC miner anywhere in the world, it belongs here. Start with the schema that can hold it all, even if we populate it incrementally.

Design for 10 years of data accumulation. Design for eventual community contribution. Design for AI systems to query it and learn from it.
