# CORS Lockdown Plan for Mac Mini Migration

**Created:** April 13, 2026  
**Deadline:** May 5–9, 2026 (Mac mini arrival)  
**Status:** AUDIT COMPLETE, CHANGES NOT YET APPLIED

## Current State (VPS R&D Phase)

### dashboard_api.py
```python
origins = [
    "http://localhost:8585",
    "http://localhost:3000",
    "https://dashboard.fieslerfamily.com",
    "https://grafana.fieslerfamily.com",
]
```

### approval_api.py
```python
origins = [
    "http://localhost:8686",
    "https://slack.fieslerfamily.com",
]
```

## Target State (Mac Mini Production)

### dashboard_api.py
```python
origins = [
    "http://localhost:8585",
    "http://localhost:3000",
    "http://dashboard:8585",      # Docker service name
    "http://grafana:3000",         # Docker service name
]
```

### approval_api.py
```python
# No CORS needed — localhost-bound only, no browser access
# OpenClaw routes button clicks via Socket Mode to localhost:8686
origins = [
    "http://localhost:8686",
]
```

## Change Checklist

- [ ] Remove all `*.fieslerfamily.com` origins from dashboard_api.py
- [ ] Remove all `*.fieslerfamily.com` origins from approval_api.py
- [ ] Add Docker service-name origins to dashboard_api.py
- [ ] Test Grafana → dashboard_api communication via service name
- [ ] Test Retool dashboard → dashboard_api (if Retool is kept)
- [ ] Verify OpenClaw → approval_api localhost routing works
- [ ] Document final CORS config in OPERATOR_GUIDE.md

## Testing Plan (After Containerization)

1. **Grafana → Dashboard API**
   ```bash
   docker exec -it grafana curl http://dashboard:8585/metrics
   ```

2. **OpenClaw → Approval API**
   ```bash
   docker exec -it openclaw curl http://localhost:8686/pending
   ```

3. **Browser → Dashboard (should work)**
   ```bash
   curl http://mac-mini-ip:8585/status
   ```

4. **Browser → Approval API (should fail — localhost-bound)**
   ```bash
   curl http://mac-mini-ip:8686/pending
   # Expected: Connection refused or 403
   ```

## Related Work

- See docs/CLOUDFLARE_MIGRATION.md for tunnel removal checklist
- See AI_ROADMAP.md "Migration to Mac Mini" section

---

*This is a PLAN document. Changes will be applied during May 1-5 containerization work.*
