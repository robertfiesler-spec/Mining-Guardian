# Mining Guardian API Reference

**Status:** PLACEHOLDER - Build starts May 3, 2026

This guide will document:

## Dashboard API (port 8585)
- GET /status
- GET /metrics (Prometheus)
- GET /query/* (OpenClaw guardian-db skill)
- POST /api/hvac/ingest
- GET /api/hvac/latest

## Approval API (port 8686)
- POST /approve
- POST /deny
- POST /approve_selected
- GET /pending
- POST /slack/actions

Per installer/DEPLOYMENT.md requirement.
