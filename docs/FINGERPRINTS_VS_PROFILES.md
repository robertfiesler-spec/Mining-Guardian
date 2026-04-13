# miner_fingerprints vs miner_profiles in knowledge.json

**Created:** April 13, 2026

## Summary

Both structures have 58 entries but serve different purposes:

**miner_fingerprints** (42 fields): ML features for behavioral learning
**miner_profiles** (5 fields): Operational state tracking

## miner_fingerprints
- Source: ai/fingerprint_builder.py
- Updated: Weekly (Sunday 3am)
- Purpose: Behavioral patterns for confidence scoring
- Fields: restart_success_rate, hashrate_stability, temp patterns, board health

## miner_profiles  
- Source: core/mining_guardian.py
- Updated: Every scan
- Purpose: Operational flagging history
- Fields: total_flags, last_flagged, issue_history

## Why Both?
- profiles = short-term operational state
- fingerprints = long-term behavioral learning
- Different update frequencies, different purposes
- NOT duplicates, complementary data

See REPAIR_LOG.md 2026-04-13 Comprehensive Audit for context.
