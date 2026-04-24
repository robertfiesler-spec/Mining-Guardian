# Log Collection Architecture

**Last updated:** 2026-04-24
**Last major refactor:** commit 8191aa6 (2026-04-24) — unified all log collection onto direct HTTP
**Scope:** evergreen reference. Update when log paths, auth, or storage schema change.
**See also:** `DIRECT_LOG_COLLECTION.md` (cron-specific details), `OPERATOR_RULES.md`, `SESSION_LOG_2026-04-24.md` (the refactor context)

---

## The Rule (for future Claude instances reading this)

**All log collection uses direct HTTP. No code should call `ams.collect_fresh_miner_logs`, `ams.collect_miner_logs`, or `ams.trigger_log_export` in the runtime path.** If you see those method names in an edit context, you are about to regress the fix from commit 8191aa6.

The AMS log export path was abandoned on 2026-04-17 because it was unreliable in practice:
- Exports would take 4+ hours to complete
- Success rates were as low as 5 of 55 miners in a daily sweep
- The parallel retry logic (15 workers, 10-minute timeout, 20-minute retry pass) never recovered well
- Every hourly scan was spawning a background thread to retry AMS exports, accumulating load

Direct HTTP to each miner hits the BiXBiT firmware's own log-generation CGI endpoint, returns a tar of that day's logs in ~30-60 seconds, and has consistent high success rates.

---

## The two log collection paths

There are exactly two places where logs get written to the `miner_logs` table. Both use direct HTTP Digest auth. Both converge on `GuardianPGDB.save_logs` for persistence.

### Path 1 — Daily baseline sweep (1pm cron)

**Script:** `scripts/direct_collect_logs.py`
**Trigger:** `0 13 * * *` daily cron entry on the VPS
**Scope:** every currently-online miner in the most recent scan that has `hashrate_medium > 0`
**Storage:** `miner_logs` rows with `health_status = 'daily_baseline'`
**Existing docs:** see `DIRECT_LOG_COLLECTION.md` for the cron-specific details (this doc avoids duplication)

Key mechanics relevant to the architecture:
- Pulls miner IP list dynamically from `miner_state_readings WHERE scan_id = <latest> AND hashrate_medium > 0`
- NO hardcoded IP list anywhere. If the scan sees a miner, this cron picks it up automatically.
- Hardcoded `SKIP_MINER_IDS = {"54504", "63940"}` — stock-firmware Teraflux AH3880s that lack the `/cgi-bin/create_log_backup.cgi` endpoint. These are the only exclusions.
- Per-day de-duplication: if a row for the same `miner_id` + `collected_at::date` + `log_file LIKE '%miner.log'` already exists, the INSERT becomes an UPDATE.

### Path 2 — Pre/post restart pairs (event-driven)

**Helper:** `core/mining_guardian.py::_collect_logs_nonblocking(miner_id, model, label, ip)`
**Triggers:** called from three places, always as a pre/post pair surrounding a remediation action

| Remediation method          | Pre-label                    | Post-label                   |
|-----------------------------|------------------------------|------------------------------|
| `execute_board_restart`     | `pre-restart-board-check`    | `post-restart-board-check`   |
| `execute_restart`           | `pre-restart`                | `post-restart`               |
| `execute_pdu_cycle`         | `pre-pdu-cycle`              | `post-pdu-cycle`             |

**Storage:** `miner_logs` rows with the matching label in `health_status`
**Pairing:** the AI joins pre+post rows on `(miner_id, label-prefix)` to learn what a restart changed. The label-prefix match is literally how the learning works — `pre-restart` and `post-restart` share the `restart` semantic.

**Why this matters:** when modifying `_collect_logs_nonblocking`, preserve the label strings exactly. Changing `"pre-restart"` to `"pre_restart"` (underscore) breaks the learning.

---

## The HTTP dance — what the direct path actually does

Both paths run the same 3-step dance against each miner:

### Step 1 — Request backup creation
```
POST http://<ip>/cgi-bin/create_log_backup.cgi
Authorization: Digest username="root", realm=...
Content-Type: application/json
Body:  ["/YYYY-MM/DD"]
```

Body format is a JSON array with a single date-scoped path string. The miner builds a tar of its logs for that date.

Response body JSON:
```
{
  "stats": "success",
  "code": "L000",
  "msg": "Antminer_S19j_Pro_2026-04-24.tar.bz2"
}
```

The `msg` field is the filename on the miner's file system. A `stats` value other than `"success"` means the creation failed — log and skip that miner.

### Step 2 — Download the tar
```
GET http://<ip>/log/<filename>
Authorization: Digest username="root", realm=...
```

Returns the bz2-compressed tar as raw bytes. Payload is typically 400KB to 1MB depending on how much the miner logged that day.

Hard sanity check: responses under 100 bytes are treated as failures (miner returned an error page instead of a tar).

### Step 3 — Extract miner.log
Standard `tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:*")`. Walk members, find the one ending in `miner.log`, decode with `utf-8 errors='replace'`. Store as-is (the 1pm cron path also applies a filter to strip frequency-tuning noise — see `filter_log_content` in direct_collect_logs.py). The pre/post restart path does NOT filter — we want to see every line around a remediation event.

---

## Authentication

- **Protocol:** HTTP Digest Auth
- **Credentials:** `root` / `root` (BiXBiT firmware default, also works on stock Antminer firmware)
- **Library:** `requests.auth.HTTPDigestAuth`
- **NOT stored in .env** — the credentials are public knowledge (same across all miners from this vendor). Not secrets.

**Auradine miners** use a different auth scheme entirely (see `AURADINE_API.md`) and are in the `SKIP_MINER_IDS` list for this reason. Direct log collection does NOT support them today.

---

## Storage schema

Both paths write to `miner_logs`:

```sql
CREATE TABLE miner_logs (
    id             serial PRIMARY KEY,
    collected_at   text NOT NULL,              -- ISO 8601
    miner_id       text NOT NULL,
    model          text,                       -- Antminer S19JPro, etc
    health_status  text NOT NULL,              -- 'daily_baseline' | 'pre-restart' | 'post-restart' | etc
    log_file       text NOT NULL,              -- filename from the tar (nvdata/YYYY-MM/DD/cglog_init_.../miner.log)
    content        text NOT NULL               -- the full miner.log content, filtered (cron) or unfiltered (restart path)
);
```

`health_status` is reused across Mining Guardian — it labels why a log was captured. The pre/post restart labels (see table above) are what pairs them for AI learning.

**Retention:** logs are purged after 30 days via `purge_old_logs` called from the scan loop. Hardware identity parsed from miner.log (board serial, chip bin, PCB version) is extracted separately and stored permanently in `miner_hardware` — that table is never purged.

---

## Discovery: how the system knows which miners to collect from

**Critical architectural property:** there is NO hardcoded miner IP list in this codebase. The list is always derived from the most recent scan:

```sql
-- From direct_collect_logs.py::get_online_miners()
SELECT DISTINCT miner_id, ip
FROM miner_state_readings
WHERE scan_id = (SELECT id FROM scans ORDER BY id DESC LIMIT 1)
  AND ip IS NOT NULL
  AND hashrate_medium > 0
```

This means:
- If AMS adds a new miner to the workspace, it lands in the next scan, lands in miner_state_readings, and the next 1pm cron picks it up — zero code change needed
- If a miner comes back online after being down, the first scan that sees it online lands it back in the eligible list
- If a miner's IP changes, the next scan overwrites the old record (miner_id is the join key, not IP)

**Gotcha documented in AMS_INTEGRATION.md:** AMS WebSocket sessions can go stale and miss recently-surfaced miners. If the scan loop is missing miners that the AMS UI shows, restart mining-guardian to force a fresh AMS login.

---

## Concurrency and rate limits

**Path 1 (cron):** uses `ThreadPoolExecutor(max_workers=5)`. 5 parallel workers hitting 5 different miner IPs — no single miner gets more than 1 concurrent request. Miners handle this fine. VPS egress is never the bottleneck (this is LAN-scale traffic over Tailscale).

**Path 2 (pre/post restart):** single-threaded, synchronous. Runs on the main mining-guardian thread or a background remediation thread depending on the caller. No concurrency concerns because restart events are sequential and one-at-a-time.

---

## Failure modes and what happens

| Failure                            | Where                | Behavior                                                |
|------------------------------------|----------------------|---------------------------------------------------------|
| Miner offline / unreachable         | Both paths           | requests.exceptions.ConnectionError → row not written; helper returns {} |
| HTTP timeout (60s)                  | Both paths           | requests.exceptions.Timeout → row not written           |
| Miner returns stats != success      | Both paths           | Log warning, skip miner                                 |
| Tar download < 100 bytes            | Both paths           | Log warning, treat as failure                           |
| miner.log missing from tar          | Both paths           | Log info, return {} (no save)                           |
| DB insert fails                     | save_logs            | Exception propagates, logged by caller                  |
| No IP available (restart path)      | _collect_logs_nonblocking | DB fallback lookup; if that also fails, log info and return {} |

**The guiding philosophy:** log collection must never block or crash a scan. It's best-effort. A miner missing a log for a day is annoying; a scan loop crashing because log collection broke is a fleet outage.

---

## Debugging workflows

### "Why are no logs being collected?"

1. Check services: `systemctl is-active mining-guardian`
2. Check last scan: `SELECT id, scanned_at, online FROM scans ORDER BY id DESC LIMIT 1` — is the scan loop even running?
3. Check eligible miners: `SELECT COUNT(*) FROM miner_state_readings WHERE scan_id = <latest> AND ip IS NOT NULL AND hashrate_medium > 0;`
4. Run the cron manually: `cd /root/Mining-Gaurdian && set -a && source .env && set +a && venv/bin/python scripts/direct_collect_logs.py` and watch the output
5. If a specific miner is failing, curl it directly: `curl -sS --digest -u root:root -X POST -H 'Content-Type: application/json' -d '["/2026-04/24"]' http://192.168.188.125/cgi-bin/create_log_backup.cgi`

### "Why are pre/post restart pairs missing?"

1. Verify the remediation method actually ran: `SELECT * FROM action_audit_log WHERE action_taken LIKE 'RESTART%' ORDER BY timestamp DESC LIMIT 5`
2. Check for paired rows: `SELECT health_status, COUNT(*) FROM miner_logs WHERE miner_id = '<X>' AND collected_at::timestamp > NOW() - INTERVAL '1 day' GROUP BY health_status;`
3. If pre exists but post is missing: the miner didn't come back online after restart (background post thread gave up). Check `_wait_for_stable` logs in the journal.
4. If both are missing: the direct HTTP calls failed. Look for "Direct log fetch" warnings in the mining-guardian journal around the action timestamp.

### "Why is log content huge/noisy?"

- 1pm cron path applies `filter_log_content` which strips frequency-tuning and PSU spam
- Pre/post restart path does NOT filter — raw content is preserved for forensic analysis
- If you want filtered restart-pair logs, modify `_collect_logs_nonblocking` to call `filter_log_content` before `save_logs` (this is a conscious choice to keep pre/post raw)

---

## Historical notes

- **Before 2026-04-17:** only the AMS path existed. Hourly scans triggered AMS exports. Success rate was terrible.
- **2026-04-17:** `scripts/direct_collect_logs.py` created, replaced the AMS daily sweep for the 1pm cron. Success rate jumped to 75-80%. AMS path stayed in place for pre/post pairs and as a backup.
- **2026-04-24:** commit 8191aa6 removed the AMS path from `core/mining_guardian.py` entirely. Pre/post pairs converted to direct HTTP. Daily baseline sweep in `collect_logs()` became a no-op because the 1pm cron already covers it.
- **Current state:** single log collection mechanism (direct HTTP), two entry points (1pm cron + event-driven). Zero AMS dependencies.

---

## For the Mac Mini cutover (Monday 2026-04-27)

Direct log collection relies on the Mac Mini being able to reach every miner IP in the facility. On local LAN this is trivial — it's just HTTP to `192.168.188.x` and `192.168.189.x`. No Tailscale needed from on-site. Verify during cutover by running the 1pm cron manually once the Mac is on the LAN:

```bash
cd "/Users/BigBobby/Documents/GitHub/Mining Gaurdian"
set -a && source .env && set +a
venv/bin/python scripts/direct_collect_logs.py
# Expect: ~50 logs collected in ~2-3 minutes
```

If it works, logs are sorted for the day. If it doesn't, the most likely causes are:
1. firewall on the Mac blocking outbound HTTP (unlikely but check)
2. DNS or ARP issue reaching the miner IPs — try `ping 192.168.188.125` first
3. Python env missing `requests` — `pip install -r requirements.txt`
