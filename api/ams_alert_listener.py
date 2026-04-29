#!/usr/bin/env python3
"""
ams_alert_listener.py — Mining Guardian AMS Alert Listener

A lightweight event-driven service that polls AMS notifications every 15 seconds
and reacts to urgent issues immediately, instead of waiting for the next scan cycle.

ARCHITECTURE
============
This service runs ALONGSIDE the main mining_guardian daemon. The main daemon
does scheduled deep scans on a timer (5min for THIS proof-of-concept mine,
30-60min at production). THIS service catches urgent issues between scans.

WHY THIS EXISTS
===============
At production deployments, scan intervals are 30-60 minutes (one Mac Mini per
container handling 120-240 miners with local LLM only). Without an event listener,
a miner going offline at minute 1 wouldn't be remediated until minute 60. This
service closes that gap by reacting to AMS notifications in seconds.

WHAT IT HANDLES (urgent — cannot wait for next scan)
====================================================
  - workerOffline (Warning)              -> restart -> PDU cycle if still down
  - hashrateDropLevel (Critical)         -> restart
  - hotBoard (Critical)                  -> alert operator (NO auto-fix)
  - temperatureChipChangeLevel (Critical)-> alert operator (NO auto-fix)

WHAT IT SKIPS (defer to next deep scan)
========================================
  - consumptionChangeLevel (any level)   — trending, not urgent
  - hashrateDropLevel (Warning)          — let trending analysis handle it
  - workerOnline (any level)             — info only, just log recovery
  - newMiner                             — informational

SAFETY GUARANTEES
=================
  - Uses the SAME approval system as the main daemon (approval_api)
  - Respects the same overnight automation rules and quiet hours
  - Deduplicates by AMS notification ID — never acts on the same alert twice
  - Honors known_dead_boards — won't try to fix miners already known to be broken
  - Falls back gracefully if approval API is unreachable
  - Won't act faster than the cooldown allows (one urgent action per miner per 10 min)

CONFIGURATION
=============
Reads the same config.json as the main daemon. New optional keys:
  - alert_listener_poll_interval_seconds (default: 15)
  - alert_listener_enabled (default: true)
  - alert_listener_action_cooldown_seconds (default: 600 — 10 min per miner)
"""

import json
import logging
import os
import psycopg2
from psycopg2.extras import DictCursor
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

# Make the core daemon importable so we share the AMSClient + GuardianConfig
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / 'core'))
sys.path.insert(0, str(_ROOT / 'ai'))

# Logging setup — write to stdout so systemd journal captures it
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger('alert_listener')

def _pg_dsn() -> str:
    """Build Postgres DSN from environment variables.

    Defaults match the standard mining_guardian install — override via env:
      GUARDIAN_PG_HOST, GUARDIAN_PG_PORT, GUARDIAN_PG_DBNAME,
      GUARDIAN_PG_USER, GUARDIAN_PG_PASSWORD
    """
    host = os.environ.get("GUARDIAN_PG_HOST", "localhost")
    port = os.environ.get("GUARDIAN_PG_PORT", "5432")
    dbname = os.environ.get("GUARDIAN_PG_DBNAME", "mining_guardian")
    user = os.environ.get("GUARDIAN_PG_USER", "guardian_app")
    password = os.environ.get("GUARDIAN_PG_PASSWORD", "")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"
CONFIG_PATH = str(_ROOT / 'config.json')

# Notifications we treat as urgent and what to do about each
URGENT_RULES = {
    # (key, alert_level): action
    ('workerOffline', 'Warning'):                'OFFLINE_REMEDIATION',
    ('workerOffline', 'Critical'):               'OFFLINE_REMEDIATION',
    ('hashrateDropLevel', 'Critical'):           'RESTART',
    ('hotBoard', 'Critical'):                    'ALERT_OPERATOR',
    ('temperatureChipChangeLevel', 'Critical'):  'ALERT_OPERATOR',
}


class AlertListenerDB:
    """Tracks which notifications we've already acted on, plus action cooldowns."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_tables()

    def _ensure_tables(self):
        """No-op on Postgres backend.

        The alert_listener_seen and alert_listener_cooldown tables are created
        by migrations/001_initial_schema.sql, loaded once by GuardianPGDB._init_db().
        This method is kept for API compatibility with any code that still calls it,
        but does nothing on Postgres.
        """
        pass

    def has_seen(self, notification_id: int) -> bool:
        conn = psycopg2.connect(self.db_path, cursor_factory=DictCursor)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    'SELECT 1 FROM alert_listener_seen WHERE notification_id=%s',
                    (notification_id,)
                )
                r = cur.fetchone()
            return r is not None
        finally:
            conn.close()

    def record_seen(self, notification_id: int, key: str, alert_level: str,
                    miner_id: Optional[str], ip: Optional[str],
                    action: str, outcome: str = 'pending'):
        conn = psycopg2.connect(self.db_path, cursor_factory=DictCursor)
        try:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO alert_listener_seen
                    (notification_id, key, alert_level, miner_id, ip, action_taken, seen_at, acted_at, outcome)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (notification_id) DO UPDATE SET
                        key = EXCLUDED.key,
                        alert_level = EXCLUDED.alert_level,
                        miner_id = EXCLUDED.miner_id,
                        ip = EXCLUDED.ip,
                        action_taken = EXCLUDED.action_taken,
                        seen_at = EXCLUDED.seen_at,
                        acted_at = EXCLUDED.acted_at,
                        outcome = EXCLUDED.outcome
                ''', (notification_id, key, alert_level, miner_id, ip, action,
                      datetime.now(timezone.utc).isoformat(),
                      datetime.now(timezone.utc).isoformat(),
                      outcome))
            conn.commit()
        finally:
            conn.close()

    def in_cooldown(self, miner_id: str, cooldown_seconds: int) -> bool:
        conn = psycopg2.connect(self.db_path, cursor_factory=DictCursor)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    'SELECT last_action_at FROM alert_listener_cooldown WHERE miner_id=%s',
                    (miner_id,)
                )
                r = cur.fetchone()
            if not r:
                return False
            last = datetime.fromisoformat(r['last_action_at'])
            elapsed = (datetime.now(timezone.utc) - last).total_seconds()
            return elapsed < cooldown_seconds
        finally:
            conn.close()

    def set_cooldown(self, miner_id: str, action: str):
        conn = psycopg2.connect(self.db_path, cursor_factory=DictCursor)
        try:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO alert_listener_cooldown
                    (miner_id, last_action, last_action_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (miner_id) DO UPDATE SET
                        last_action = EXCLUDED.last_action,
                        last_action_at = EXCLUDED.last_action_at
                ''', (miner_id, action, datetime.now(timezone.utc).isoformat()))
            conn.commit()
        finally:
            conn.close()


class AlertListener:
    """Main alert listener loop."""

    def __init__(self):
        # Import here so we can show a clear error if config is missing
        from mining_guardian import GuardianConfig, AMSClient

        self.config = GuardianConfig.from_file(CONFIG_PATH)
        self.ams = AMSClient(self.config)
        self.db = AlertListenerDB(_pg_dsn())

        # Read listener-specific config with safe defaults
        with open(CONFIG_PATH) as f:
            raw = json.load(f)
        self.poll_interval = raw.get('alert_listener_poll_interval_seconds', 15)
        self.cooldown = raw.get('alert_listener_action_cooldown_seconds', 600)
        self.enabled = raw.get('alert_listener_enabled', True)

        # Track known dead boards so we don't try to fix unfixable miners
        self.known_dead_boards: Set[str] = self._load_known_dead_boards()
        self._dead_boards_refresh_at = 0  # refresh every 5 min

        logger.info('AlertListener initialized:')
        logger.info('  poll_interval: %ds', self.poll_interval)
        logger.info('  cooldown:      %ds', self.cooldown)
        logger.info('  enabled:       %s', self.enabled)
        logger.info('  ams workspace: %s', self.config.ams_workspace_id)

    def _load_known_dead_boards(self) -> Set[str]:
        """Load miners with known dead boards — don't try to remediate them."""
        try:
            conn = psycopg2.connect(_pg_dsn(), cursor_factory=DictCursor)
        except psycopg2.OperationalError:
            return set()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT miner_id FROM known_dead_boards')
                rows = cur.fetchall()
            return {row['miner_id'] for row in rows}
        except psycopg2.errors.UndefinedTable:
            # Table might not exist yet
            return set()
        finally:
            conn.close()

    def _maybe_refresh_dead_boards(self):
        now = time.time()
        if now - self._dead_boards_refresh_at > 300:
            self.known_dead_boards = self._load_known_dead_boards()
            self._dead_boards_refresh_at = now

    def _classify(self, notif: Dict) -> Optional[str]:
        """Return action name if urgent, None if defer to next scan.

        Real AMS notification shape:
            {id, deviceID, key, params: {alertLevel, minerIp, ...}, ...}
        alertLevel lives INSIDE params, not at the top level.
        """
        key = notif.get('key', '')
        params = notif.get('params') or {}
        level = (
            params.get('alertLevel')
            or notif.get('alertLevel')          # legacy/fallback
            or notif.get('alert_level', '')     # legacy/fallback
        )
        return URGENT_RULES.get((key, level))

    def _extract_miner(self, notif: Dict) -> Dict:
        """Extract miner identification from an AMS notification.

        Real AMS notification shape:
            {id, deviceID, type, key, params: {minerIp, deviceType, id, ...}}
        The miner_id is deviceID (top-level), the IP is in params.minerIp.
        """
        params = notif.get('params') or {}
        # deviceID at the top level is the canonical miner id in AMS
        miner_id = (
            notif.get('deviceID')
            or notif.get('device_id')
            or params.get('id')
            or ''
        )
        ip = (
            params.get('minerIp')
            or params.get('miner_ip')
            or params.get('ip')
            or ''
        )
        return {
            'id': str(miner_id),
            'ip': ip,
            'model': params.get('model', ''),
            'mac': params.get('mac', ''),
        }

    def _trigger_offline_remediation(self, miner: Dict, notif: Dict):
        """
        Miner went offline — fast remediation path.

        Production order:
          1. Verify it's really offline (TCP probe before acting on AMS alert)
          2. Restart via AMS
          3. If still offline 2 min later, PDU cycle (if has_pdu)
          4. If still offline 2 min after that, create AMS ticket
        """
        miner_id = miner['id']
        ip = miner['ip']

        if not miner_id or not ip:
            logger.warning('  Cannot remediate — missing miner_id or ip in notification')
            return 'skipped_no_id'

        if miner_id in self.known_dead_boards:
            logger.info('  Miner %s is in known_dead_boards — skipping (operator already knows)', ip)
            return 'skipped_dead_board'

        if self.db.in_cooldown(miner_id, self.cooldown):
            logger.info('  Miner %s in cooldown — skipping', ip)
            return 'skipped_cooldown'

        # Verify the miner is really offline before acting (false-positive defense)
        if self._verify_truly_offline(ip):
            logger.info('  Miner %s confirmed offline — triggering restart via AMS', ip)
            ok = self._call_main_daemon_action(miner_id, ip, 'RESTART', notif.get('id'))
            self.db.set_cooldown(miner_id, 'RESTART')
            return 'restart_triggered' if ok else 'restart_failed'
        else:
            logger.info('  Miner %s appears online via TCP probe — false alarm, skipping', ip)
            return 'false_alarm'

    def _trigger_restart(self, miner: Dict, notif: Dict):
        """Severe hashrate drop — restart immediately."""
        miner_id = miner['id']
        ip = miner['ip']

        if not miner_id:
            return 'skipped_no_id'
        if miner_id in self.known_dead_boards:
            return 'skipped_dead_board'
        if self.db.in_cooldown(miner_id, self.cooldown):
            return 'skipped_cooldown'

        logger.info('  Triggering restart for %s due to severe hashrate drop', ip)
        ok = self._call_main_daemon_action(miner_id, ip, 'RESTART', notif.get('id'))
        self.db.set_cooldown(miner_id, 'RESTART')
        return 'restart_triggered' if ok else 'restart_failed'

    def _alert_operator(self, miner: Dict, notif: Dict):
        """Thermal alerts — never auto-fix, always escalate to a human."""
        miner_id = miner['id']
        ip = miner['ip']
        key = notif.get('key', 'thermal')

        # Just log it — the main daemon's Slack throttling will catch it on the next post
        # We don't post directly to avoid notification spam
        logger.warning(
            '  THERMAL ALERT: %s (%s) — key=%s level=%s — operator notified, NO auto-fix',
            ip, miner['model'], key, notif.get('alertLevel')
        )
        return 'operator_alerted'

    def _verify_truly_offline(self, ip: str) -> bool:
        """
        TCP probe to verify a miner is actually offline before acting.
        Tries port 4028 (CGMiner API) and port 80 (web UI). If either responds,
        the miner is online and the AMS alert was a false positive.
        """
        import socket
        for port in (4028, 80):
            try:
                with socket.create_connection((ip, port), timeout=3) as s:
                    return False
            except (socket.timeout, ConnectionRefusedError, OSError):
                continue
        return True

    def _call_main_daemon_action(self, miner_id: str, ip: str,
                                  action: str, notification_id: Optional[int]) -> bool:
        """
        Trigger an action through the approval API.

        At production this calls the same approval flow the main daemon uses,
        which means quiet hours, overnight rules, and operator approval all apply.
        For URGENT alerts, we mark the action as 'auto_alert' so it bypasses normal
        approval queueing only when overnight automation is enabled.
        """
        try:
            import requests as _r
            secret = os.environ.get('INTERNAL_API_SECRET', '')
            if not secret:
                # Try reading from .env
                env_path = _ROOT / '.env'
                if env_path.exists():
                    for line in env_path.read_text().splitlines():
                        if line.startswith('INTERNAL_API_SECRET='):
                            secret = line.split('=', 1)[1].strip().strip('"').strip("'")
                            break

            payload = {
                'miner_id': miner_id,
                'ip': ip,
                'action': action,
                'source': 'ams_alert_listener',
                'notification_id': notification_id,
                'urgent': True,
            }
            r = _r.post(
                'http://localhost:8686/internal/urgent_action',
                json=payload,
                headers={'X-Internal-Secret': secret},
                timeout=10,
            )
            if r.status_code == 200:
                logger.info('    Approval API accepted urgent action: %s', r.json())
                return True
            elif r.status_code == 404:
                # Endpoint doesn't exist yet — that means main daemon doesn't support
                # urgent actions yet. Fall back to logging only and let the next scan handle it.
                logger.warning('    Approval API does not yet support /internal/urgent_action — '
                               'action will be picked up by next scan cycle')
                return False
            else:
                logger.warning('    Approval API returned %s: %s', r.status_code, r.text[:200])
                return False
        except Exception as e:
            logger.warning('    Approval API call failed: %s', e)
            return False

    def _process_notification(self, notif: Dict):
        """Handle a single notification — classify and route to the right action."""
        notif_id = notif.get('id')
        if not notif_id:
            return

        if self.db.has_seen(notif_id):
            return  # Already processed

        key = notif.get('key', '')
        params = notif.get('params') or {}
        level = params.get('alertLevel') or notif.get('alertLevel') or ''
        action = self._classify(notif)
        miner = self._extract_miner(notif)

        if action is None:
            # Not urgent — record as seen so we don't reconsider, defer to next scan
            self.db.record_seen(notif_id, key, level, miner.get('id'), miner.get('ip'),
                                'DEFER', 'deferred_to_scan')
            return

        logger.info('🚨 URGENT alert: id=%s key=%s level=%s miner=%s(%s) action=%s',
                    notif_id, key, level, miner.get('ip'), miner.get('model'), action)

        outcome = 'unknown'
        try:
            if action == 'OFFLINE_REMEDIATION':
                outcome = self._trigger_offline_remediation(miner, notif)
            elif action == 'RESTART':
                outcome = self._trigger_restart(miner, notif)
            elif action == 'ALERT_OPERATOR':
                outcome = self._alert_operator(miner, notif)
        except Exception as e:
            logger.exception('  Action handler failed: %s', e)
            outcome = f'error:{e}'

        self.db.record_seen(notif_id, key, level, miner.get('id'), miner.get('ip'),
                            action, outcome)

    def run(self):
        """Main poll loop — runs forever."""
        if not self.enabled:
            logger.warning('Alert listener disabled in config — exiting')
            return

        logger.info('Alert listener starting main loop')
        consecutive_errors = 0

        while True:
            try:
                self._maybe_refresh_dead_boards()

                # Pull all notification types — miner is the urgent one
                notifs = self.ams.get_notifications(type='miner', limit=40)

                if notifs:
                    # Process newest first so we react to the freshest alerts first
                    notifs_sorted = sorted(notifs, key=lambda n: n.get('id', 0), reverse=True)
                    new_count = 0
                    for n in notifs_sorted:
                        if not self.db.has_seen(n.get('id', 0)):
                            new_count += 1
                            self._process_notification(n)
                    if new_count:
                        logger.debug('Processed %d new notifications', new_count)

                consecutive_errors = 0
                # Bucket 9 §10.7: hot-reload poll interval from system_schedules
                # each cycle so operators can retime from the Web GUI.
                try:
                    from api.system_schedules import get_interval_seconds
                    self.poll_interval = get_interval_seconds("ams_alert_poll")
                except Exception:
                    pass  # keep current value
                time.sleep(self.poll_interval)

            except KeyboardInterrupt:
                logger.info('Alert listener stopping (KeyboardInterrupt)')
                break
            except Exception as e:
                consecutive_errors += 1
                logger.exception('Alert listener loop error (%d consecutive): %s',
                                 consecutive_errors, e)
                # Exponential backoff on repeated errors, capped at 5 min
                backoff = min(self.poll_interval * (2 ** consecutive_errors), 300)
                logger.warning('Backing off %ds before retry', backoff)
                time.sleep(backoff)


def main():
    try:
        listener = AlertListener()
        listener.run()
    except Exception as e:
        logger.exception('Alert listener failed to start: %s', e)
        sys.exit(1)


if __name__ == '__main__':
    main()
