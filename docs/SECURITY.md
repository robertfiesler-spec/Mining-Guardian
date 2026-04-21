# Mining Guardian Security Documentation

## Last Updated: April 21, 2026

---

## Security Hardening Checklist

### 1. Network Exposure

| Service | Port | Binding | Status |
|---------|------|---------|--------|
| Dashboard API | 8585 | 127.0.0.1 | ✅ Secure |
| Approval API | 8686 | 127.0.0.1 | ✅ Secure |
| Prometheus | 9090 | 127.0.0.1 | ⚠️ FIXED Apr 21 |
| Grafana | 3000 | 127.0.0.1 | ⚠️ FIXED Apr 21 |

**Access Method:** All services accessible via Cloudflare tunnels only.

### 2. Authentication

| Component | Method | Notes |
|-----------|--------|-------|
| AMS API | JWT via cookies | Token refresh with lock |
| Dashboard API | None (read-only) | Rate limited |
| Approval API | X-Internal-Secret header | Required for actions |
| Slack Actions | SLACK_SIGNING_SECRET | Signature verification |
| Grafana | Username/password | Via Cloudflare tunnel |
| Prometheus | None | Localhost only |

### 3. Secrets Management

**Location:** `/root/Mining-Gaurdian/.env`

| Secret | Source | Rotation |
|--------|--------|----------|
| AMS_EMAIL/PASSWORD | BiXBiT | Manual |
| SLACK_BOT_TOKEN | Slack App | Manual |
| SLACK_SIGNING_SECRET | Slack App | Manual |
| ANTHROPIC_API_KEY | Anthropic | Manual |
| INTERNAL_API_SECRET | Generated | Should rotate quarterly |
| ECLYPSE_USER/PASS | Distech | Manual |

**Best Practice:** Never commit `.env` to git. Template at `.env.example`.

### 4. Rate Limiting

| Endpoint | Limit | Implementation |
|----------|-------|----------------|
| /fleet | 60/min | slowapi |
| /metrics | 120/min | slowapi |
| /miner/* | 60/min | slowapi |
| /approve | 10/min | slowapi |

### 5. Input Validation

- All miner_id parameters: alphanumeric only
- All IP parameters: IPv4 format validation
- All date parameters: ISO format validation

### 6. CORS Policy

```python
allow_origins=[
    "https://dashboard.fieslerfamily.com",
    "https://grafana.fieslerfamily.com",
    "https://retool.com",
    "http://localhost:8585",
    "http://127.0.0.1:8585",
]
```

### 7. Known Issues

#### GitHub Secret Alert (Resolved Apr 21, 2026)
- **Issue:** GitHub PAT committed in `git hub paswords.rtfd/TXT.rtf`
- **Resolution:** Token revoked, file removed from repo
- **Note:** Secret remains in git history; token is now invalid

---

## Security Fixes Applied

### April 21, 2026

1. **Prometheus binding** - Changed from 0.0.0.0:9090 to 127.0.0.1:9090
2. **Grafana binding** - Changed from 0.0.0.0:3000 to 127.0.0.1:3000
3. **Rate limiting** - Added slowapi to dashboard_api.py
4. **GitHub secret** - Token revoked, alert closed

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
