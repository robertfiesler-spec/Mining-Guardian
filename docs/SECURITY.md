# Mining Guardian Security Documentation

## Last Updated: April 21, 2026

---

## Security Hardening Checklist

### 1. Network Exposure

| Service | Port | Binding | Status |
|---------|------|---------|--------|
| Dashboard API | 8585 | 127.0.0.1 | ✅ Secure |
| Approval API | 8686 | 127.0.0.1 | ✅ Secure |
| Prometheus | 9090 | 127.0.0.1 | ✅ FIXED Apr 21 |
| Grafana | 3000 | 127.0.0.1 | ✅ FIXED Apr 21 |

**Access Method:** All services accessible via Cloudflare tunnels only.

**Changes Made (Apr 21 2026):**
- Prometheus: Changed `/etc/systemd/system/prometheus.service` from `--web.listen-address=0.0.0.0:9090` to `127.0.0.1:9090`
- Grafana: Uncommented and set `http_addr = 127.0.0.1` in `/etc/grafana/grafana.ini`

### 2. Authentication

| Component | Method | Notes |
|-----------|--------|-------|
| AMS API | JWT via cookies | Token refresh with lock |
| Dashboard API | None (read-only) | Rate limited |
| Approval API | X-Internal-Secret header | Required for actions |
| Slack Actions | SLACK_SIGNING_SECRET | Signature verification |
| Grafana | Username/password | Via Cloudflare tunnel |
| Prometheus | None | Localhost only |

### 3. Rate Limiting (Added Apr 21 2026)

Using `slowapi` library.

| Endpoint | Limit | Notes |
|----------|-------|-------|
| /metrics | 120/min | Prometheus scraping |
| /fleet/latest | 60/min | Dashboard refresh |
| /fleet/history | 30/min | Historical queries |
| /miners/flagged | 60/min | Current issues |
| /temps/history | 30/min | Temperature queries |
| /notifications/recent | 60/min | Recent alerts |
| /audit/log | 30/min | Audit trail |

### 4. Secrets Management

**Location:** `/root/Mining-Gaurdian/.env`

| Secret | Source | Rotation |
|--------|--------|----------|
| AMS_EMAIL/PASSWORD | BiXBiT | Manual |
| SLACK_BOT_TOKEN | Slack App | Manual |
| SLACK_SIGNING_SECRET | Slack App | Manual |
| ANTHROPIC_API_KEY | Anthropic | Manual |
| INTERNAL_API_SECRET | Generated | Quarterly |
| ECLYPSE_USER/PASS | Distech | Manual |

**Best Practice:** Never commit `.env` to git. Template at `.env.example`.

### 5. CORS Policy

```python
allow_origins=[
    https://dashboard.fieslerfamily.com,
    https://grafana.fieslerfamily.com,
    https://retool.com,
    http://localhost:8585,
    http://127.0.0.1:8585,
]
```

### 6. Known Issues / Resolved

#### GitHub Secret Alert (Apr 5-21, 2026)
- **Issue:** GitHub PAT committed in `git hub paswords.rtfd/TXT.rtf`
- **Token:** `<REDACTED — revoked 2026-04-24>` (full literal scrubbed during CRIT-1 purge 2026-04-27)
- **Status:** RESOLVED — token revoked at GitHub on 2026-04-24, confirmed `Never used` on 2026-04-27. New PAT "3rd" issued in its place.
- **File removed:** Yes, in commit `ac0a215`
- **Note:** Old token literal still exists in pre-2026-04-27 git history; revocation at GitHub is what invalidates it (and that step is complete).

---

## Security Fixes Applied

### April 21, 2026

1. ✅ **Prometheus binding** - Changed from 0.0.0.0:9090 to 127.0.0.1:9090
2. ✅ **Grafana binding** - Changed from 0.0.0.0:3000 to 127.0.0.1:3000  
3. ✅ **Rate limiting** - Added slowapi to dashboard_api.py (7 endpoints)
4. ⏳ **GitHub secret** - Token needs to be revoked manually

---

## Verification Commands

```bash
# Check port bindings (all should be 127.0.0.1)
ss -tlnp | grep -E '8585|8686|9090|3000'

# Test rate limiting
for i in {1..5}; do curl -s http://127.0.0.1:8585/fleet/latest | jq .id; done

# Check Prometheus config
grep listen-address /etc/systemd/system/prometheus.service

# Check Grafana config
grep http_addr /etc/grafana/grafana.ini
```

---

## Incident Response

If you suspect a security breach:

1. Check `/var/log/auth.log` for SSH attempts
2. Check Grafana audit logs
3. Review `action_audit_log` table in guardian.db
4. Check Cloudflare access logs
5. Rotate all secrets in `.env`

---

## Contact

Security issues: robertefiesler@gmail.com
