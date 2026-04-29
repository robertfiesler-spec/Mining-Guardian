# Unused Data Opportunities in guardian.db

> **Status (2026-04-29 sweep):** Historical reference. This list catalogs unused datasets discovered on the **VPS-era `guardian.db` SQLite snapshot** as of April 13, 2026. SQLite is **not live** post-2026-04-30; equivalent datasets exist in PostgreSQL `mining_guardian` on the Mac Mini going forward. Row counts below reflect the historical SQLite snapshot, not current state.

**Created:** April 13, 2026 (historical record — VPS era)

## High-Value Datasets (10 opportunities)

1. **Chip-Level Failure Prediction** (2.6M rows in log_metrics.chip_hashrate)
2. **PSU Health Trending** (9.5M rows, voltage curves)
3. **System Health Correlation** (2.3M rows)
4. **Board Serial Batch Correlation** (90 boards, warranty claims)
5. **Pool Rejection Leading Indicator** (30.8K rows)
6. **LLM Drift Detection** (860 analyses)
7. **Operator Approval Patterns** (663 approvals)
8. **Action Effectiveness by Model** (857 actions)
9. **Restart Timing + HVAC Correlation** (78 restarts + 1.4K HVAC)
10. **Weather → Hashrate Correlation** (1.4K weather readings)

## Tier 1 Priority (Highest ROI)
- Chip-level failure prediction
- Board serial batch correlation  
- Pool rejection leading indicator

All data already flowing, no schema changes needed.

See REPAIR_LOG.md 2026-04-13 Comprehensive Audit.
