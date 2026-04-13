# Warehouse Mechanical System

> **NOTE**: This document is superseded by [HVAC_SYSTEMS.md](./HVAC_SYSTEMS.md) which covers BOTH cooling systems.

## Quick Reference

Mining Guardian now monitors **TWO HVAC systems**:

1. **Warehouse HVAC** (192.168.188.235) — Hydros, S21 Imm, Auradines
2. **S19J Pro Container** (192.168.189.235) — S19J Pro miners only

See [HVAC_SYSTEMS.md](./HVAC_SYSTEMS.md) for complete documentation including:
- BACnet point mappings
- Typical values
- Data collection architecture
- AI integration details
- Operator rules

## Legacy Notes (for historical reference)

The original XpressENVYSION integration was explored in early April 2026.
The Eclypse BAS controllers use REST API over HTTPS with basic auth.
Both systems share credentials: BigStar / BigSt@r2020

---
*Updated: April 13, 2026 — See HVAC_SYSTEMS.md for current documentation*
