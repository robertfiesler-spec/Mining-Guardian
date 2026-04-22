"""
AMS (Asset Management System) Client
Extracted from mining_guardian.py on April 21, 2026

This module handles all communication with the BiXBiT AMS API
via WebSocket and REST endpoints.
"""

import os
import json
import time
import threading
import logging
from typing import Any, Dict, List, Optional

from datetime import datetime, timezone, timedelta
import requests
import websocket
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

class AMSClient:

    _RETRY_POLICY = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist={429, 500, 502, 503, 504},
        allowed_methods={"GET", "POST", "PATCH"},
        raise_on_status=False,
    )

    def __init__(self, config):  # GuardianConfig
        self.base_url = config.ams_base_url.rstrip("/")
        self.ws_base  = self.base_url.replace("https://", "wss://").replace("http://", "ws://")
        self.email    = config.ams_email
        self.password = config.ams_password
        self.workspace_id = config.ams_workspace_id
        self.timeout  = 15
        self._ws_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        self._token_lock = threading.Lock()  # Protect token access

        self.session = requests.Session()
        adapter = HTTPAdapter(max_retries=self._RETRY_POLICY)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    # ── Auth ─────────────────────────────────────────────────

    def _login(self) -> str:
        """POST /auth/login — returns user-level JWT via cookie."""
        resp = self.session.post(
            f"{self.base_url}/auth/login",
            json={"email": self.email, "password": self.password},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        token = self.session.cookies.get("access_token")
        if not token:
            raise RuntimeError("Login succeeded but no access_token cookie returned.")
        logger.info("AMS login OK")
        return token

    def _select_workspace(self, user_token: str) -> str:
        """POST /auth/select_workspace — returns workspace-scoped JWT via cookie."""
        resp = self.session.post(
            f"{self.base_url}/auth/select_workspace",
            json={"id": self.workspace_id},
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        token = self.session.cookies.get("access_token")
        if not token:
            raise RuntimeError("select_workspace succeeded but no access_token cookie returned.")
        logger.info("AMS workspace %s selected", self.workspace_id)
        return token


    def _ensure_token(self) -> str:
        """Return a valid workspace token, re-authenticating if needed.

        Tokens expire after ~30 minutes (observed from JWT payload).
        We re-auth 60 seconds before expiry to avoid mid-scan failures.

        Thread safety: uses self._token_lock to prevent parallel log workers
        from racing on token refresh and corrupting session state.

        Bug fix (Apr 8 2026): long-running processes (overnight-automation,
        alert-listener) were getting HTTP 400 from select_workspace when the
        token expired. Root cause: stale session cookies were colliding with
        the new Bearer header during re-auth. Fix: clear the cookie jar before
        every re-auth, and on failure, reset _ws_token so the next call retries
        from scratch instead of returning the stale cached value.
        """
        with self._token_lock:
            now = datetime.now(timezone.utc)
            if self._ws_token and self._token_expiry and now < self._token_expiry:
                return self._ws_token

            # CRITICAL: clear the cookie jar before re-auth so stale workspace
            # tokens from a previous expired session do not interfere with the
            # new login + select_workspace flow.
            self.session.cookies.clear()

            try:
                user_token = self._login()
                ws_token   = self._select_workspace(user_token)
            except Exception as e:
                # Hard-reset cached state so the next call re-attempts fresh
                self._ws_token = None
                self._token_expiry = None
                self.session.cookies.clear()
                logger.error("AMS re-auth failed: %s — cleared cached token", e)
                raise

            self._ws_token     = ws_token
            # Parse expiry from JWT payload (middle segment, base64-encoded JSON)
            try:
                import base64
                payload_b64 = ws_token.split(".")[1]
                payload_b64 += "=" * (4 - len(payload_b64) % 4)
                payload = json.loads(base64.b64decode(payload_b64))
                exp = payload.get("exp")
                if exp:
                    self._token_expiry = datetime.fromtimestamp(exp, tz=timezone.utc) - timedelta(seconds=60)
            except Exception:
                # If we can't parse expiry, refresh every 25 minutes to be safe
                self._token_expiry = now + timedelta(minutes=25)

            return self._ws_token

    # ── Read: WebSocket one-shot fetch ───────────────────────
    # The AMS delivers live data via WebSocket, not REST polling.
    # We connect, receive one message, then close — treating the
    # WS like a fast REST call. This is intentional: we want a
    # consistent point-in-time snapshot per scan cycle, not a
    # streaming connection that complicates daemon lifecycle.

    def _ws_fetch(self, path: str, timeout_seconds: int = 10) -> Optional[Dict]:
        """Connect to a WebSocket endpoint, receive one message, return parsed JSON."""
        token   = self._ensure_token()
        ws_url  = f"{self.ws_base}/{path.lstrip('/')}"
        result  = {}
        event   = threading.Event()

        def on_message(ws, message):
            try:
                result.update(json.loads(message))
            except Exception as e:
                logger.warning("WS message parse error: %s", e)
            event.set()
            ws.close()

        def on_error(ws, error):
            logger.warning("WS error on %s: %s", path, error)
            event.set()

        def on_close(ws, *_):
            event.set()

        ws = websocket.WebSocketApp(
            ws_url,
            header={"Authorization": f"Bearer {token}"},
            subprotocols=[token],
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        thread = threading.Thread(target=ws.run_forever, daemon=True)
        thread.start()
        event.wait(timeout=timeout_seconds)
        ws.close()
        return result if result else None


    # ── Public read methods ───────────────────────────────────

    def get_dashboard(self) -> Dict[str, Any]:
        """Fetch fleet-level dashboard stats (hashrate, temps, device counts)."""
        data = self._ws_fetch("miners/dashboard_ws")
        if not data:
            raise RuntimeError("Dashboard WebSocket returned no data.")
        return data

    def _fetch_miner_page(self, page: int, per_page: int = 50) -> Dict[str, Any]:
        """Fetch a single page of miners via WebSocket. Returns raw response dict."""
        token  = self._ensure_token()
        ws_url = f"{self.ws_base}/miners/list_ws"
        result: Dict[str, Any] = {}
        event  = threading.Event()

        def on_open(ws):
            ws.send(json.dumps({
                "limit": per_page,
                "page": page,
                "filter": {
                    "category": "All",
                    "searchWord": "",
                    "workers": [],
                    "models": [],
                    "errors": []
                },
                "sort": {"field": "id", "order": "asc"}
            }))

        def on_message(ws, message):
            try:
                result.update(json.loads(message))
            except Exception as e:
                logger.warning("Miner list WS parse error: %s", e)
            event.set()
            ws.close()

        def on_error(ws, error):
            logger.warning("Miner list WS error on page %s: %s", page, error)
            event.set()

        def on_close(ws, *_):
            event.set()

        ws = websocket.WebSocketApp(ws_url,
            header={"Authorization": f"Bearer {token}"},
            subprotocols=[token],
            on_open=on_open, on_message=on_message,
            on_error=on_error, on_close=on_close)
        thread = threading.Thread(target=ws.run_forever, daemon=True)
        thread.start()
        event.wait(timeout=15)
        ws.close()
        return result

    def get_miners(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Fetch all miners across all pages via WebSocket (miners/list_ws)."""
        per_page   = 50
        all_miners: List[Dict[str, Any]] = []
        page       = 1

        while True:
            data        = self._fetch_miner_page(page, per_page)
            devices     = data.get("devices", [])
            total_count = data.get("totalCount", 0)
            all_miners.extend(devices)

            logger.info(
                "Fetched page %s — %s miners (total %s / %s)",
                page, len(devices), len(all_miners), total_count
            )

            # Stop if we have everything or the page came back empty
            if not devices or len(all_miners) >= total_count:
                break
            page += 1

        logger.info("Fetched %s miners total (totalCount=%s)", len(all_miners), total_count)
        return all_miners

    def get_miner_state(self, miner_id: str) -> Dict[str, Any]:
        """Fetch fresh per-miner state. Falls back to get_miners snapshot if unavailable."""
        # Per-miner WS endpoint not in spec — use REST if available, else return empty
        token = self._ensure_token()
        url   = f"{self.base_url}/miners/{miner_id}"
        resp  = self.session.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.debug("get_miner_state REST returned %s for %s", resp.status_code, miner_id)
        return {}

    # ── Log collection ────────────────────────────────────────

    def trigger_log_export(self, miner_id: int) -> bool:
        """POST /log/export — tells AMS to generate a fresh log zip for this miner."""
        token = self._ensure_token()
        resp = self.session.post(
            f"{self.base_url}/log/export",
            json={"deviceID": miner_id},
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        return resp.status_code == 200

    def get_log_list(self, miner_id: int) -> List[Dict]:
        """POST /log/get_log_list — returns list of available log files for this miner."""
        token = self._ensure_token()
        resp = self.session.post(
            f"{self.base_url}/log/get_log_list",
            json={"deviceID": miner_id},
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        if resp.status_code == 200:
            return resp.json().get("logList", [])
        return []

    def download_log(self, miner_id: int, filename: str) -> Optional[bytes]:
        """POST /log/download — download a log zip file by miner ID and filename."""
        token = self._ensure_token()
        resp = self.session.post(
            f"{self.base_url}/log/download",
            json={"deviceID": miner_id, "fileName": filename},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,  # larger file, longer timeout
        )
        if resp.status_code == 200 and len(resp.content) > 100:
            return resp.content
        return None

    def collect_miner_logs(self, miner_id: int) -> Optional[Dict[str, str]]:
        """Collect logs for a miner — only downloads if existing logs are available.

        Does NOT trigger new exports (slow, 60s wait). That is handled separately.
        If no existing logs are found, returns None immediately.
        """
        import zipfile, io

        # Check existing logs only — no export trigger
        logs = self.get_log_list(miner_id)
        ready_logs = [l for l in logs if l.get("status") == 2]

        if not ready_logs:
            return None  # No logs available — skip silently

        # Download the most recent completed log
        latest   = ready_logs[0]
        filename = latest["fileName"]
        zip_bytes = self.download_log(miner_id, filename)
        if not zip_bytes:
            logger.warning("Log download failed for miner %s", miner_id)
            return None

        # Extract up to 3 key files from the zip
        extracted = {}
        key_files = {
            "cgminer.conf",
            "x-autotune-results.json",
            "allowed_pools",
        }
        MAX_FILES = 3
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                for name in zf.namelist():
                    if len(extracted) >= MAX_FILES:
                        break
                    basename = name.split("/")[-1]
                    if basename in key_files or "cglog" in name:
                        try:
                            content = zf.read(name).decode("utf-8", errors="replace")
                            extracted[name] = content
                        except Exception:
                            pass
        except Exception as e:
            logger.warning("Log zip extraction failed for miner %s: %s", miner_id, e)
            return None

        logger.info("Collected %s log files for miner %s (from %s)",
                    len(extracted), miner_id, filename)
        return extracted


    def collect_fresh_miner_logs(self, miner_id: int,
                                  max_wait_seconds: Optional[int] = None,
                                  poll_interval_seconds: int = 5) -> Optional[Dict[str, str]]:
        """Trigger a NEW log export on AMS, poll until ready, then download.

        Use this when freshness matters — pre/post restart, pre-PDU-cycle,
        any moment where the analysis depends on logs from THIS instant rather
        than whatever AMS happens to have cached.

        Workflow:
          1. POST /log/export to ask AMS to generate a fresh log zip
          2. Poll /log/get_log_list every poll_interval_seconds to detect a NEW
             log file (one that was not in the list before we triggered)
          3. When a new log appears with status==2 (ready), download it
          4. Extract and return the file dict, same shape as collect_miner_logs

        Returns None on timeout or any failure. Never raises.

        Cost: variable per miner — depends on AMS export timing and miner
        state. Typical 30-120 seconds; some miners take several minutes.
        When max_wait_seconds is None (the default) this function waits as
        long as AMS needs. Pass a number to cap. Per operator spec: logs are
        too important to miss due to timing, so default is no cap.
        """
        import zipfile, io, time as _time

        # 1. Snapshot the current log list so we can detect what is NEW
        try:
            before = self.get_log_list(miner_id)
            before_names = {l.get("fileName") for l in before}
        except Exception as e:
            logger.warning("Fresh log: get_log_list snapshot failed for %s: %s", miner_id, e)
            return None

        # 2. Trigger a fresh export
        try:
            ok = self.trigger_log_export(miner_id)
            if not ok:
                logger.warning("Fresh log: trigger_log_export returned False for %s", miner_id)
                return None
            logger.info("Fresh log: export triggered for miner %s", miner_id)
        except Exception as e:
            logger.warning("Fresh log: trigger_log_export raised for %s: %s", miner_id, e)
            return None

        # 3. Poll for a NEW completed log file
        # No cap by default — wait as long as AMS needs. Callers can cap
        # by passing max_wait_seconds. Heartbeat every 5 minutes of waiting.
        start_time = _time.time()
        deadline = (start_time + max_wait_seconds) if max_wait_seconds else None
        new_filename = None
        last_heartbeat = 0
        while True:
            if deadline is not None and _time.time() >= deadline:
                break
            _time.sleep(poll_interval_seconds)
            try:
                logs = self.get_log_list(miner_id)
            except Exception:
                continue

            ready = [l for l in logs if l.get("status") == 2]
            new_ready = [l for l in ready if l.get("fileName") not in before_names]
            if new_ready:
                # Pick the most recent — log lists are usually newest-first
                # but be defensive
                new_ready.sort(
                    key=lambda l: l.get("createdAt") or l.get("fileName") or "",
                    reverse=True,
                )
                new_filename = new_ready[0].get("fileName")
                waited = int(_time.time() - start_time)
                logger.info("Fresh log: new file ready for miner %s after %ds: %s",
                            miner_id, waited, new_filename)
                break

            # Heartbeat every 300s so operators can see progress on long waits
            waited = int(_time.time() - start_time)
            if waited - last_heartbeat >= 300:
                logger.info("Fresh log: still waiting for miner %s export at %ds (no cap)",
                            miner_id, waited)
                last_heartbeat = waited

        if not new_filename:
            waited = int(_time.time() - start_time)
            logger.warning("Fresh log: no new log appeared for miner %s within cap (%ds)",
                           miner_id, waited)
            return None

        # 4. Download and extract the fresh zip
        try:
            zip_bytes = self.download_log(miner_id, new_filename)
            if not zip_bytes:
                logger.warning("Fresh log: download failed for %s", miner_id)
                return None
        except Exception as e:
            logger.warning("Fresh log: download raised for %s: %s", miner_id, e)
            return None

        extracted = {}
        key_files = {
            "cgminer.conf",
            "x-autotune-results.json",
            "allowed_pools",
        }
        MAX_FILES = 3
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                for name in zf.namelist():
                    if len(extracted) >= MAX_FILES:
                        break
                    basename = name.split("/")[-1]
                    if basename in key_files or "cglog" in name:
                        try:
                            content = zf.read(name).decode("utf-8", errors="replace")
                            extracted[name] = content
                        except Exception:
                            pass
        except Exception as e:
            logger.warning("Fresh log: zip extract failed for %s: %s", miner_id, e)
            return None

        logger.info("Fresh log: collected %d files for miner %s from %s",
                    len(extracted), miner_id, new_filename)
        return extracted if extracted else None

    # ── Public write methods ──────────────────────────────────

    def get_pdu_detail(self, pdu_id: int) -> Optional[Dict]:
        """WebSocket pdus/ws — get per-outlet detail for a specific PDU.

        Returns per-outlet: voltage, current, power (watts), counter (MWh),
        on/off status, and assigned miner ID.
        PDU power is the authoritative source — always prefer over miner-reported.
        """
        token  = self._ensure_token()
        ws_url = f"{self.ws_base}/pdus/ws"
        result: Dict = {}
        event  = threading.Event()

        def on_open(ws):
            ws.send(json.dumps({"id": pdu_id}))

        def on_message(ws, message):
            try:
                result.update(json.loads(message))
            except Exception as e:
                logger.warning("pdus/ws parse error: %s", e)
            event.set()
            ws.close()

        def on_error(ws, error):
            logger.warning("pdus/ws error for PDU %s: %s", pdu_id, error)
            event.set()

        def on_close(ws, *_):
            event.set()

        ws = websocket.WebSocketApp(ws_url,
            header={"Authorization": f"Bearer {token}"},
            subprotocols=[token],
            on_open=on_open, on_message=on_message,
            on_error=on_error, on_close=on_close)
        threading.Thread(target=ws.run_forever, daemon=True).start()
        event.wait(timeout=10)
        ws.close()
        return result if result else None

    def get_pdu_stats(self) -> Optional[Dict]:
        """WebSocket pdus/statistic — get real-time PDU power stats.

        POWER DATA PRIORITY RULE:
        Always prefer PDU power numbers over miner-reported numbers.
        Smart PDUs measure at the outlet level and are more accurate.
        Only fall back to miner-reported consumption if no PDU is assigned.

        Returns totalDevices, enabledOuts, totalOuts, voltage, current,
        power (watts), and counter (total energy MWh) for all PDUs.
        """
        token  = self._ensure_token()
        ws_url = f"{self.ws_base}/pdus/statistic"
        result: Dict = {}
        event  = threading.Event()

        def on_message(ws, message):
            try:
                result.update(json.loads(message))
            except Exception as e:
                logger.warning("pdus/statistic parse error: %s", e)
            event.set()
            ws.close()

        def on_error(ws, error):
            logger.warning("pdus/statistic error: %s", error)
            event.set()

        def on_close(ws, *_):
            event.set()

        ws = websocket.WebSocketApp(ws_url,
            header={"Authorization": f"Bearer {token}"},
            subprotocols=[token],
            on_message=on_message, on_error=on_error, on_close=on_close)
        threading.Thread(target=ws.run_forever, daemon=True).start()
        event.wait(timeout=10)
        ws.close()
        return result if result else None

    def get_miner_boards(self, miner_id: int) -> Optional[Dict]:
        """WebSocket miners/chips_ws — get per-chip frequency, temp, and voltage data.

        Returns per-hashboard, per-chip data — critical for diagnosing
        which specific chips are failing or underperforming.
        """
        token  = self._ensure_token()
        ws_url = f"{self.ws_base}/miners/chips_ws"
        result: Dict = {}
        event  = threading.Event()

        def on_open(ws):
            ws.send(json.dumps({"id": miner_id}))

        def on_message(ws, message):
            try:
                result.update(json.loads(message))
            except Exception as e:
                logger.warning("chips_ws parse error: %s", e)
            event.set()
            ws.close()

        def on_error(ws, error):
            logger.warning("chips_ws error for miner %s: %s", miner_id, error)
            event.set()

        def on_close(ws, *_):
            event.set()

        ws = websocket.WebSocketApp(ws_url,
            header={"Authorization": f"Bearer {token}"},
            subprotocols=[token],
            on_open=on_open, on_message=on_message,
            on_error=on_error, on_close=on_close)
        threading.Thread(target=ws.run_forever, daemon=True).start()
        event.wait(timeout=10)
        ws.close()
        return result if result else None

    def get_miner_stats(self, miner_id: int, range: str = "today") -> Dict:
        """POST /miner_stats/device_charts — get hashrate, consumption, temp history.

        Args:
            miner_id: The miner ID
            range: "today", "week", or "month"

        Returns hashrate, power consumption, and temperature charts over time.
        Critical for trending and AI pattern analysis.
        """
        token = self._ensure_token()
        resp  = self.session.post(
            f"{self.base_url}/miner_stats/device_charts",
            json={"id": miner_id, "range": range},
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning("get_miner_stats returned %s for miner %s", resp.status_code, miner_id)
        return {}

    def led_on(self, miner_ids: List[str]) -> Dict:
        """POST /miners/dcs/led_on — flash LED to physically locate a miner."""
        token = self._ensure_token()
        resp  = self.session.post(
            f"{self.base_url}/miners/dcs/led_on",
            json={"ids": [int(i) for i in miner_ids]},
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        logger.info("LED on for miners %s", miner_ids)
        return resp.json()

    def led_off(self, miner_ids: List[str]) -> Dict:
        """POST /miners/dcs/led_off — turn off LED locator on miners."""
        token = self._ensure_token()
        resp  = self.session.post(
            f"{self.base_url}/miners/dcs/led_off",
            json={"ids": [int(i) for i in miner_ids]},
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        logger.info("LED off for miners %s", miner_ids)
        return resp.json()

    def get_notifications(self, type: str = "miner", limit: int = 40) -> List[Dict]:
        """POST /notifications/channels — get notifications by type.

        Args:
            type: "miner", "pdu", "system", or "container"
            limit: max notifications to return (default 40)

        Returns AMS-generated alerts like consumption changes, offline events,
        temperature warnings. Mining Guardian pulls these each scan to catch
        issues AMS detected that our rules may not cover.
        """
        token = self._ensure_token()
        resp  = self.session.post(
            f"{self.base_url}/notifications/channels",
            json={"page": 1, "limit": limit, "type": type},
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("notificationListResponse", {}).get("listNotifications", [])
        logger.warning("get_notifications returned %s", resp.status_code)
        return []

    def delete_notification(self, notification_id: int) -> bool:
        """DELETE /notifications/channels/{id} — dismiss a notification."""
        token = self._ensure_token()
        resp  = self.session.delete(
            f"{self.base_url}/notifications/channels/{notification_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        return resp.status_code == 200

    def get_notifications_count(self) -> int:
        """GET /notifications/count — returns unread notification count."""
        token = self._ensure_token()
        resp  = self.session.get(
            f"{self.base_url}/notifications/count",
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        if resp.status_code == 200:
            return resp.json().get("count", 0)
        return 0

    def reboot_miner(self, miner_ids: List[str]) -> Dict:
        """POST /miners/dcs/reboot — firmware reboot one or more miners."""
        token = self._ensure_token()
        resp  = self.session.post(
            f"{self.base_url}/miners/dcs/reboot",
            json={"ids": [int(i) for i in miner_ids]},
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        logger.info("Reboot command sent to miners %s", miner_ids)
        return resp.json()

    def get_tickets(self) -> List[Dict]:
        """GET /ticket — get all maintenance tickets.

        Returns tickets with status (backlog, in_progress, done),
        title, priority, and timestamps. Used to track maintenance
        work on miners and correlate with performance issues.
        """
        token = self._ensure_token()
        resp  = self.session.get(
            f"{self.base_url}/ticket",
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning("get_tickets returned %s", resp.status_code)
        return []

    def create_ticket(self, title: str, description: str = "",
                      priority: str = "normal",
                      miner_ids: List[int] = None) -> Dict:
        """POST /ticket — create a new maintenance ticket.

        Args:
            title: Short description of the issue
            description: Full details
            priority: "low" (1), "normal" (3), "high" (2)
            miner_ids: List of miner IDs to link to this ticket

        AMS ticket format (confirmed from API inspection):
          priority: int (1=low, 2=high, 3=normal)
          miners: list of int miner IDs
          executorID: int user ID (1 = owner/Test2334)
          statusID: 0 = Backlog (default)
        """
        priority_map = {"low": 1, "high": 2, "normal": 3, "critical": 2}
        priority_num = priority_map.get(priority, 3)
        token = self._ensure_token()
        resp  = self.session.post(
            f"{self.base_url}/ticket",
            json={
                "title":       title,
                "description": description,
                "priority":    priority_num,
                "miners":      miner_ids or [],
                "executorID":  1,    # owner account (Test2334)
                "statusID":    0,    # Backlog
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            ticket = data.get("ticket", data)
            logger.info("Ticket created: %s (id=%s)", title, ticket.get("id"))
            return ticket
        logger.warning("create_ticket returned %s: %s", resp.status_code, resp.text[:100])
        return {}

    def get_ticket_statuses(self) -> List[Dict]:
        """GET /ticket/status — get available ticket status types."""
        token = self._ensure_token()
        resp  = self.session.get(
            f"{self.base_url}/ticket/status",
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        if resp.status_code == 200:
            return resp.json()
        return []

    def get_map_groups(self) -> List[Dict]:
        """GET /map/groups — get facility map groups (rows, racks, sections).

        Returns physical location groups used to identify where a miner
        is located in the facility. When a miner needs attention, Mining
        Guardian uses this to tell the operator exactly where to find it.
        """
        token = self._ensure_token()
        resp  = self.session.get(
            f"{self.base_url}/map/groups",
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning("get_map_groups returned %s", resp.status_code)
        return []

    def get_map_layout(self) -> Optional[Dict]:
        """WebSocket map/ws — get full facility map with miner positions.

        Returns the spatial layout of all miners on the facility map.
        Used to show physical location (row, rack, position) alongside
        alerts so operators know exactly where to go.
        """
        token  = self._ensure_token()
        ws_url = f"{self.ws_base}/map/ws"
        result: Dict = {}
        event  = threading.Event()

        def on_message(ws, message):
            try:
                result.update(json.loads(message))
            except Exception as e:
                logger.warning("map/ws parse error: %s", e)
            event.set()
            ws.close()

        def on_error(ws, error):
            logger.warning("map/ws error: %s", error)
            event.set()

        def on_close(ws, *_):
            event.set()

        ws = websocket.WebSocketApp(ws_url,
            header={"Authorization": f"Bearer {token}"},
            subprotocols=[token],
            on_message=on_message, on_error=on_error, on_close=on_close)
        threading.Thread(target=ws.run_forever, daemon=True).start()
        event.wait(timeout=10)
        ws.close()
        return result if result else None

    def get_event_history(self, device_id: int, limit: int = 20) -> List[Dict]:
        """POST /miners/request_list — get event/action history for a miner or PDU.

        Works for both miners and PDUs — pass the device ID (miner ID or PDU ID).
        Returns control outlet events, reboots, profile changes, etc.
        """
        token = self._ensure_token()
        resp  = self.session.post(
            f"{self.base_url}/miners/request_list",
            json={"id": device_id, "start": "", "end": "", "from": "", "limit": limit},
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        if resp.status_code == 200:
            return resp.json()
        return []

    def start_miner(self, miner_ids: List[str]) -> Dict:
        """POST /miners/dcs/start — start one or more miners."""
        token = self._ensure_token()
        resp  = self.session.post(
            f"{self.base_url}/miners/dcs/start",
            json={"ids": [int(i) for i in miner_ids]},
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        logger.info("Start command sent to miners %s", miner_ids)
        return resp.json()

    def stop_miner(self, miner_ids: List[str]) -> Dict:
        """POST /miners/dcs/stop — stop one or more miners."""
        token = self._ensure_token()
        resp  = self.session.post(
            f"{self.base_url}/miners/dcs/stop",
            json={"ids": [int(i) for i in miner_ids]},
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        logger.info("Stop command sent to miners %s", miner_ids)
        return resp.json()

    def change_power_profile(self, miner_ids: List[str], profile_name: str) -> Dict:
        """POST /miners/dcs/change_overclock_config — change power profile on miners.

        profile_name is the profile ID string (e.g. "21") from x-autotune-profiles.json
        Use get_miner_profiles() to list available profiles for a miner model.
        """
        token = self._ensure_token()
        resp  = self.session.post(
            f"{self.base_url}/miners/dcs/change_overclock_config",
            json={"ids": [int(i) for i in miner_ids],
                  "config": {"command": "set_profile",
                             "data": {"profile_name": profile_name}}},
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        logger.info("Power profile changed to %s for miners %s", profile_name, miner_ids)
        return resp.json()

    def change_settings(self, miner_ids: List[str], settings: Dict[str, Any]) -> Dict:
        """POST /miners/change_settings — apply settings to one or more miners."""
        token = self._ensure_token()
        resp  = self.session.post(
            f"{self.base_url}/miners/change_settings",
            json={"ids": miner_ids, "settings": settings},
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def restart_miner(self, miner_ids: List[str]) -> Dict:
        """POST /miners/dcs/restart — restart one or more miners."""
        token = self._ensure_token()
        resp  = self.session.post(
            f"{self.base_url}/miners/dcs/restart",
            json={"ids": miner_ids},
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def pdu_power_cycle(self, pdu_id: int, outlet_index: int, off_delay: int = 30) -> Dict:
        """Power cycle a PDU outlet — turns it off, waits, turns it back on.

        Args:
            pdu_id:       PDU ID (from miner's pduOutlet.pduID field)
            outlet_index: Outlet number (from miner's pduOutlet.outletIndex field)
            off_delay:    Seconds to wait between off and on (default 30 — PSUs hold charge, need time to drain)
        """
        token = self._ensure_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self.base_url}/pdus/dcs/set_control_outlet"

        # Turn OFF
        resp = self.session.post(url, json=[{
            "id": pdu_id, "open": False, "outlet": [outlet_index]
        }], headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        logger.info("PDU %s outlet %s — turned OFF", pdu_id, outlet_index)

        time.sleep(off_delay)

        # Turn ON
        resp = self.session.post(url, json=[{
            "id": pdu_id, "open": True, "outlet": [outlet_index]
        }], headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        logger.info("PDU %s outlet %s — turned ON (power cycle complete)", pdu_id, outlet_index)

        return {"pdu_id": pdu_id, "outlet": outlet_index, "action": "power_cycled"}

    def change_pools(self, miner_ids: List[str], pools: List[Dict]) -> Dict:
        """POST /miners/dcs/change_pools — update pool config on miners."""
        token = self._ensure_token()
        resp  = self.session.post(
            f"{self.base_url}/miners/dcs/change_pools",
            json={"ids": miner_ids, "pools": pools},
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
