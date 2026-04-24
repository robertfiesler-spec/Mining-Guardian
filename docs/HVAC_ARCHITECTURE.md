# HVAC Architecture

**Last updated:** 2026-04-24
**Scope:** evergreen reference — does not become stale as commits land. Update only when physical systems, BAS endpoints, operator rules, or schema change.

---

## Two independent HVAC systems

The Fort Worth facility has **two separate HVAC systems** on separate network subnets, both polled every scan cycle, both writing to the same `hvac_readings` table distinguished by the `system_id` column.

### 1. Warehouse (system_id = 'warehouse')

- **Device:** Distech Eclypse BACnet/IP controller
- **IP:** 192.168.188.235
- **Subnet:** 192.168.188.0/24 (primary facility network, advertised by Tailscale)
- **Scope:** cooling for Hydro racks, S21 immersion, Auradine AH3880 — every miner that is not an S19J Pro.

**Reported fields:**

- supply_temp_f — Chilled water supply temperature (normally ~74°F)
- return_temp_f — Chilled water return temperature (normally ~84°F)
- delta_t_f — supply→return ΔT — **intentionally low — see operator rule below**
- diff_pressure_psi — Differential pressure
- spray_pump_on — Spray pump state (bool)
- cwp1_vfd_pct / cwp2_vfd_pct — Cold water pump VFD speeds
- ct1_vfd_pct / ct2_vfd_pct — Cooling tower fan VFD speeds
- leak_alarm — Leak detection (bool)
- ct1_fault / ct2_fault / pump_fault — Fault signals (bool)
- outside_air_f — Null for warehouse (only populated by s19jpro)
- container_temp_f — Null for warehouse

### 2. S19J Pro Container (system_id = 's19jpro')

- **Device:** Distech Eclypse (different form-factor, form-based login at /j_security_check)
- **IP:** 192.168.189.235
- **Subnet:** 192.168.189.0/24 (added to Tailscale's advertised routes from ROBS-PC in April 2026)
- **Scope:** cooling for the dedicated S19J Pro liquid immersion container only.

**Reported fields:** same schema as warehouse. Notable container-specific values:

- supply_temp_f — ~92°F (higher than warehouse — different loop)
- return_temp_f — ~108°F
- outside_air_f — Tracks Fort Worth ambient
- container_temp_f — Container interior space temp (~102°F)

### The big reason this matters

Before commit e4bc8fa on 2026-04-24, `core/database_pg.py::save_hvac` silently dropped three columns during the Postgres port: system_id, outside_air_f, container_temp_f. The consequence was:

1. Every row since 2026-04-23 had system_id = NULL.
2. Grafana panels filtering by system_id = 'warehouse' or 's19jpro' rendered as No data.
3. The S19 container's container_temp_f was never landing in the database at all, despite the HVAC client successfully polling it.

All three fields now round-trip correctly.

---

## Polling model

`core/mining_guardian.py::run_once()` calls `poll_all_systems_with_db_fallback()` which returns a dict of {system_id: HVACSnapshot} for both warehouse and s19jpro. Each snapshot is saved independently:

    hvac_snapshots = poll_all_systems_with_db_fallback()
    for sys_id, snap in hvac_snapshots.items():
        if snap:
            self.db.save_hvac(snap)

**Two rows per scan** is the correct pattern. One for warehouse, one for s19jpro. If you query hvac_readings and see only one row per recorded_at timestamp, something is wrong — check that both subnets are reachable and both snapshots are non-None.

---

## Operator rule: low delta-T is NORMAL

**This is locked and must not be overridden anywhere.**

The warehouse HVAC system at USA 188 runs with an intentionally low supply→return delta-T. This is correct. The hydro rack and immersion tank cooling loops are sized for high flow, low delta, which is efficient for liquid-cooled miners and matches the facility's design.

**Do NOT:**
- Recommend HVAC investigation based on low delta-T alone
- Describe low delta-T as 'minimal headroom' or 'thermal stress'
- Trigger alerts, flags, or Slack notifications on low delta-T
- Include low delta-T warnings in any LLM prompt, knowledge.json pattern, or dashboard panel

**What a real HVAC problem looks like:** multiple miners simultaneously exceeding chip temp 84°C, rising return temp without corresponding rise in supply, VFD saturation (CT1/CT2 at 100%), or a fault signal going true. Those are the triggers.

This rule is enforced in core/mining_guardian.py (no flags below 84°C), in the SYSTEM_PROMPT constant in core/llm_analyzer.py, and in the operator rules passed to the weekly training loop.

---

## Grafana dependency

Grafana panels that filter by system rely on hvac_readings.system_id being non-NULL. Before commit e4bc8fa, panels showed empty because every row had NULL. After the fix, new rows populate correctly and panels light up as time-series data accumulates.

**Historical NULL rows (~50 rows from 2026-04-23 through 2026-04-24 ~12:30)** are intentionally not backfilled (operator declined). This creates a ~24-hour gap in any 'last 7 days' or similar time-window Grafana query until the window rolls past 2026-04-24 ~12:30. No action needed; the gap heals itself as time passes.

**Suggested index for Grafana query performance** (not yet applied):

    CREATE INDEX IF NOT EXISTS idx_hvac_readings_system_recorded
        ON hvac_readings (system_id, recorded_at);

---

## Separate project: AV-2 Plant scraper

The S19J Pro container has a **separate** Big Star BlockChain AV-2 Plant HVAC controller on the same 192.168.189.0/24 subnet. This is NOT the Distech Eclypse covered above. Early work in `av2_plant_client.py` (browser DevTools endpoint discovery) was started then paused. The Distech Eclypse covers current needs; the AV-2 Plant client is a future project for deeper data if desired, not a blocker for anything.

Do not confuse the two. Any 's19jpro HVAC' data currently flowing through the scan loop is from the Distech at 192.168.189.235, not the AV-2 Plant.

---

## Schema reference

    -- hvac_readings table (Postgres)
    id               serial PRIMARY KEY
    recorded_at      text NOT NULL                  -- ISO 8601 timestamp
    system_id        text DEFAULT 'warehouse'       -- 'warehouse' or 's19jpro'
    supply_temp_f    double precision
    return_temp_f    double precision
    delta_t_f        double precision
    diff_pressure    double precision
    spray_pump_on    integer                        -- 0/1
    cwp1_vfd_pct     double precision
    cwp2_vfd_pct     double precision
    ct1_vfd_pct      double precision
    ct2_vfd_pct      double precision
    leak_alarm       integer                        -- 0/1
    ct1_fault        integer                        -- 0/1
    ct2_fault        integer                        -- 0/1
    pump_fault       integer                        -- 0/1
    outside_air_f    double precision               -- populated for s19jpro only
    container_temp_f double precision               -- populated for s19jpro only

## Code references

- clients/hvac_client.py — HVACClient, HVACSnapshot dataclass, SYSTEMS dict, poll_all_systems_with_db_fallback()
- core/database_pg.py::save_hvac — the 17-column INSERT (verified 2026-04-24)
- core/mining_guardian.py::run_once — the two-system polling loop
- migrations/001_initial_schema.sql — canonical schema for fresh installs
