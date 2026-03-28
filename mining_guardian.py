import os
import json
import time
import sqlite3
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
import websocket
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def _setup_logging() -> logging.Logger:
    """Configure logging to both terminal and a daily rotating log file."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"guardian_{datetime.now().strftime('%Y-%m-%d')}.log"

    fmt = "%(asctime)s %(levelname)s %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt)

    # Add file handler alongside the terminal handler
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter(fmt))
    logging.getLogger().addHandler(fh)

    return logging.getLogger("mining_guardian")

logger = _setup_logging()


# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

@dataclass
class ParameterRule:
    key: str
    operator: str
    expected: Any
    severity: str = "warning"
    recommended_fix: Optional[Any] = None
    note: str = ""

    def evaluate(self, actual: Any) -> bool:
        try:
            if self.operator == "eq":      return actual == self.expected
            if self.operator == "neq":     return actual != self.expected
            if self.operator == "lt":      return actual < self.expected
            if self.operator == "lte":     return actual <= self.expected
            if self.operator == "gt":      return actual > self.expected
            if self.operator == "gte":     return actual >= self.expected
            if self.operator == "between":
                low, high = self.expected
                return low <= actual <= high
            if self.operator == "in":      return actual in self.expected
            raise ValueError(f"Unsupported operator: {self.operator}")
        except Exception:
            return False


@dataclass
class MinerFinding:
    miner_id: str
    ip: str
    key: str
    actual: Any
    expected: Any
    operator: str
    severity: str
    note: str
    recommended_fix: Any


@dataclass
class GuardianConfig:
    ams_base_url: str        # e.g. https://api-staging.dev.bixbit.io/api/v1
    ams_email: str
    ams_password: str
    ams_workspace_id: int
    openclaw_webhook_url: Optional[str] = None
    slack_webhook_url: Optional[str] = None
    dry_run: bool = True
    collect_logs: bool = False  # enable log collection independently of dry_run
    scan_interval_seconds: int = 300
    approval_mode: str = "manual"
    miner_filters: Dict[str, Any] = field(default_factory=dict)
    rules: List[ParameterRule] = field(default_factory=list)

    @staticmethod
    def _resolve(value: str) -> str:
        """Resolve env: prefixed secrets from environment variables."""
        if isinstance(value, str) and value.startswith("env:"):
            env_var = value[4:]
            resolved = os.environ.get(env_var)
            if not resolved:
                raise EnvironmentError(f"Secret '{env_var}' not set in environment.")
            return resolved
        return value

    @staticmethod
    def from_file(path: str) -> "GuardianConfig":
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        rules = [ParameterRule(**item) for item in raw.get("rules", [])]
        return GuardianConfig(
            ams_base_url=raw["ams_base_url"],
            ams_email=GuardianConfig._resolve(raw["ams_email"]),
            ams_password=GuardianConfig._resolve(raw["ams_password"]),
            ams_workspace_id=int(GuardianConfig._resolve(raw["ams_workspace_id"])),
            openclaw_webhook_url=raw.get("openclaw_webhook_url"),
            slack_webhook_url=raw.get("slack_webhook_url"),
            dry_run=raw.get("dry_run", True),
            collect_logs=raw.get("collect_logs", False),
            scan_interval_seconds=raw.get("scan_interval_seconds", 300),
            approval_mode=raw.get("approval_mode", "manual"),
            miner_filters=raw.get("miner_filters", {}),
            rules=rules,
        )


# ------------------------------------------------------------
# AMS Client — real BiXBiT API
# ------------------------------------------------------------
# Auth discovery: tokens are returned as HTTP cookies, not in
# the JSON body. requests.Session() handles cookies automatically.
#
# Read path:  WebSocket (push-based, not REST polling)
# Write path: REST POST/PATCH with workspace token cookie
# ------------------------------------------------------------

class AMSClient:

    _RETRY_POLICY = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist={429, 500, 502, 503, 504},
        allowed_methods={"GET", "POST", "PATCH"},
        raise_on_status=False,
    )

    def __init__(self, config: GuardianConfig):
        self.base_url = config.ams_base_url.rstrip("/")
        self.ws_base  = self.base_url.replace("https://", "wss://").replace("http://", "ws://")
        self.email    = config.ams_email
        self.password = config.ams_password
        self.workspace_id = config.ams_workspace_id
        self.timeout  = 15
        self._ws_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

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
        """
        now = datetime.now(timezone.utc)
        if self._ws_token and self._token_expiry and now < self._token_expiry:
            return self._ws_token

        user_token   = self._login()
        ws_token     = self._select_workspace(user_token)
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

    def pdu_power_cycle(self, pdu_id: int, outlet_index: int, off_delay: int = 5) -> Dict:
        """Power cycle a PDU outlet — turns it off, waits, turns it back on.

        Args:
            pdu_id:       PDU ID (from miner's pduOutlet.pduID field)
            outlet_index: Outlet number (from miner's pduOutlet.outletIndex field)
            off_delay:    Seconds to wait between off and on (default 5)
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
        return resp.json()


# ------------------------------------------------------------
# Policy engine — unchanged
# ------------------------------------------------------------

class PolicyEngine:
    def __init__(self, rules: List[ParameterRule]):
        self.rules = rules

    @staticmethod
    def _lookup(payload: Dict[str, Any], key: str) -> Any:
        current = payload
        for part in key.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current

    def evaluate_miner(self, miner: Dict[str, Any]) -> List[MinerFinding]:
        miner_id = str(miner.get("id", "unknown"))
        ip = str(miner.get("ip", miner.get("network", {}).get("ip", "unknown")))
        findings: List[MinerFinding] = []
        for rule in self.rules:
            actual = self._lookup(miner, rule.key)
            if not rule.evaluate(actual):
                findings.append(MinerFinding(
                    miner_id=miner_id, ip=ip,
                    key=rule.key, actual=actual,
                    expected=rule.expected, operator=rule.operator,
                    severity=rule.severity, note=rule.note,
                    recommended_fix=rule.recommended_fix,
                ))
        return findings


# ------------------------------------------------------------
# Remediation planner — unchanged
# ------------------------------------------------------------

class RemediationPlanner:
    LOW_RISK_KEYS = {
        "config.pools.backup_enabled",
        "config.fans.mode",
        "config.network.dns.primary",
        "config.power.profile",
    }

    def build_patch(self, finding: MinerFinding) -> Dict[str, Any]:
        return self._nested_patch(finding.key, finding.recommended_fix)

    @staticmethod
    def _nested_patch(path: str, value: Any) -> Dict[str, Any]:
        parts = path.split(".")
        result: Dict[str, Any] = value
        for key in reversed(parts):
            result = {key: result}
        return result

    def is_low_risk(self, finding: MinerFinding) -> bool:
        return finding.key in self.LOW_RISK_KEYS and finding.severity != "critical"


# ------------------------------------------------------------
# Approval interface — unchanged
# ------------------------------------------------------------

class ApprovalInterface:
    def __init__(self, config: GuardianConfig):
        self.config = config

    def request_approval(self, finding: MinerFinding) -> bool:
        summary = (
            f"  Miner : {finding.miner_id} ({finding.ip})\n"
            f"  Key   : {finding.key}\n"
            f"  Actual: {finding.actual}  →  Fix: {finding.recommended_fix}\n"
            f"  Note  : {finding.note or '—'}"
        )
        logger.info("Approval required:\n%s", summary)
        if not os.isatty(0):
            logger.warning("Headless — auto-denying miner=%s key=%s", finding.miner_id, finding.key)
            return False
        try:
            answer = input(f"\nApprove patch for {finding.miner_id} [{finding.key}]? [y/N]: ")
            return answer.strip().lower() == "y"
        except (EOFError, KeyboardInterrupt):
            logger.warning("Approval interrupted — denying.")
            return False


# ------------------------------------------------------------
# ------------------------------------------------------------
# OpenClaw notifier
# ------------------------------------------------------------
# Sends a structured JSON payload to the local OpenClaw webhook
# after every scan. OpenClaw's local LLM interprets the findings
# and posts a plain-English summary to Slack for operator review.
#
# Webhook URL format: http://127.0.0.1:<port>/webhook/<token>
# Set openclaw_webhook_url in config.json when OpenClaw is ready.
# Leave it null to disable silently — no errors will be thrown.
# ------------------------------------------------------------

class OpenClawNotifier:
    def __init__(self, webhook_url: Optional[str]):
        self.webhook_url = webhook_url

    def send_scan(self, miners: List[Dict], issues: List[Dict]) -> None:
        """POST scan results to OpenClaw webhook.

        OpenClaw receives this payload, passes it to the local LLM,
        and the LLM posts a plain-English summary + recommendations
        to Slack for operator review and approval.
        """
        if not self.webhook_url:
            logger.debug("OpenClaw webhook not configured — skipping notification")
            return

        now    = datetime.now().strftime("%Y-%m-%d %H:%M")
        online = sum(1 for m in miners if m.get("status") == "online")

        # Build a plain-English summary line for the LLM to work with
        pdu_cycles  = [i for i in issues if i["action"] == "PDU_CYCLE"]
        fw_restarts = [i for i in issues if i["action"] == "RESTART"]
        monitors    = [i for i in issues if i["action"] == "MONITOR"]
        temp_action = [i for i in issues if i["action"] == "TEMP_ACTION_REQUIRED"]

        pdu_cycles_oc  = [i for i in issues if i["action"] == "PDU_CYCLE"]
        fw_restarts_oc = [i for i in issues if i["action"] == "RESTART"]
        phys_oc        = [i for i in issues if i["action"] == "PHYSICAL_CYCLE"]
        monitors_oc    = [i for i in issues if i["action"] == "MONITOR"]
        temp_oc        = [i for i in issues if i["action"] == "TEMP_ACTION_REQUIRED"]

        parts = []
        if pdu_cycles_oc:
            parts.append(f"{len(pdu_cycles_oc)} offline miner(s) need PDU power cycle")
        if fw_restarts_oc:
            parts.append(f"{len(fw_restarts_oc)} miner(s) need firmware restart")
        if phys_oc:
            parts.append(f"{len(phys_oc)} offline miner(s) need physical power cycle at facility")
        if temp_oc:
            parts.append(f"{len(temp_oc)} miner(s) have critical chip temps (86°C+)")
        if monitors_oc:
            parts.append(f"{len(monitors_oc)} miner(s) running warm (76–85°C), monitoring")
        summary = ". ".join(parts) + "." if parts else "All miners operating normally."
        payload = {
            "source":     "mining_guardian",
            "scanned_at": now,
            "fleet": {
                "total":   len(miners),
                "online":  online,
                "offline": len(miners) - online,
                "issues":  len(issues),
            },
            "summary": summary,
            "issues": [
                {
                    "miner_id":   i["id"],
                    "ip":         i["ip"],
                    "model":      i["model"],
                    "status":     i["status"],
                    "hashrate":   i["hashrate_pct"],
                    "temp_chip":  i["temp_chip"],
                    "action":     i["action"],
                    "pdu_action": i.get("pdu_action"),
                    "detail":     " | ".join(i["issues"]),
                }
                for i in issues
            ],
            # Instruction for the LLM — tells it what to do with this data
            "instructions": (
                "You are Mining Guardian's AI analyst for BiXBiT USA. "
                "Review the fleet scan below and post a concise Slack message to the #mining-ops channel. "
                "Include: fleet status summary, list of miners needing action with their recommended fix, "
                "and ask the operator to confirm before any actions are taken. "
                "Keep it professional and brief."
            ),
        }

        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info("OpenClaw notified — scan summary sent")
            else:
                logger.warning("OpenClaw webhook returned %s", resp.status_code)
        except Exception as exc:
            logger.warning("OpenClaw notification failed: %s", exc)



# ------------------------------------------------------------
# Remediation cooldown — unchanged
# ------------------------------------------------------------

class RemediationCooldown:
    def __init__(self, cooldown_minutes: int = 30):
        self.cooldown = timedelta(minutes=cooldown_minutes)
        self._last_remediated: Dict[Tuple[str, str], datetime] = {}

    def is_cooling_down(self, miner_id: str, key: str) -> bool:
        last = self._last_remediated.get((miner_id, key))
        return False if last is None else datetime.now(timezone.utc) - last < self.cooldown

    def record(self, miner_id: str, key: str) -> None:
        self._last_remediated[(miner_id, key)] = datetime.now(timezone.utc)


# ------------------------------------------------------------
# Orchestrator — updated to use new AMSClient interface
# ------------------------------------------------------------

# ------------------------------------------------------------
# Local SQLite database — scan history and miner telemetry
# ------------------------------------------------------------
# Every scan writes:
#   scans          — one row per scan run (summary)
#   miner_readings — one row per miner per scan (full telemetry)
#
# This enables trending, historical analysis, and eventually
# predictive failure detection via the local LLM.
# ------------------------------------------------------------

# ------------------------------------------------------------
# Weather collector — ambient temp and humidity for Fort Worth
# ------------------------------------------------------------
# Uses Open-Meteo API (free, no API key required).
# Data stored per scan and correlated with miner telemetry
# so the LLM can factor ambient conditions into predictions.
# Hot humid days stress cooling — cold dry days are ideal.
# ------------------------------------------------------------

class WeatherCollector:
    API_URL = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, latitude: float = 32.7555, longitude: float = -97.3308):
        self.latitude  = latitude
        self.longitude = longitude

    def fetch(self) -> Optional[Dict[str, Any]]:
        """Fetch current conditions and today's forecast from Open-Meteo."""
        try:
            resp = requests.get(self.API_URL, params={
                "latitude":         self.latitude,
                "longitude":        self.longitude,
                "current":          ["temperature_2m", "relative_humidity_2m", "apparent_temperature"],
                "daily":            ["temperature_2m_max", "temperature_2m_min",
                                     "relative_humidity_2m_max", "relative_humidity_2m_min"],
                "temperature_unit": "fahrenheit",
                "timezone":         "America/Chicago",
                "forecast_days":    1,
            }, timeout=10)
            resp.raise_for_status()
            data    = resp.json()
            current = data.get("current", {})
            daily   = data.get("daily", {})
            return {
                "temp_f":       current.get("temperature_2m"),
                "humidity_pct": current.get("relative_humidity_2m"),
                "feels_like_f": current.get("apparent_temperature"),
                "temp_high_f":  daily.get("temperature_2m_max", [None])[0],
                "temp_low_f":   daily.get("temperature_2m_min", [None])[0],
                "humidity_max": daily.get("relative_humidity_2m_max", [None])[0],
                "humidity_min": daily.get("relative_humidity_2m_min", [None])[0],
            }
        except Exception as e:
            logger.warning("Weather fetch failed: %s", e)
            return None


class GuardianDB:

    def __init__(self, db_path: str = "guardian.db"):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS scans (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    scanned_at    TEXT    NOT NULL,
                    total_miners  INTEGER NOT NULL,
                    online        INTEGER NOT NULL,
                    offline       INTEGER NOT NULL,
                    issues        INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS miner_readings (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id       INTEGER NOT NULL REFERENCES scans(id),
                    scanned_at    TEXT    NOT NULL,
                    miner_id      TEXT    NOT NULL,
                    ip            TEXT,
                    model         TEXT,
                    status        TEXT,
                    hashrate      REAL,
                    max_hashrate  REAL,
                    hashrate_pct  REAL,
                    temp_chip     REAL,
                    issue         TEXT,
                    action        TEXT,
                    pdu_id        INTEGER,
                    outlet        INTEGER
                );

                CREATE INDEX IF NOT EXISTS idx_readings_miner
                    ON miner_readings(miner_id, scanned_at);

                CREATE TABLE IF NOT EXISTS ams_notifications (
                    row_id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at     TEXT    NOT NULL,
                    notification_id INTEGER,
                    device_id       TEXT,
                    type            TEXT,
                    key             TEXT,
                    alert_level     TEXT,
                    miner_ip        TEXT,
                    raw             TEXT
                );

                CREATE TABLE IF NOT EXISTS weather_readings (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at     TEXT    NOT NULL,
                    temp_f          REAL,
                    humidity_pct    REAL,
                    feels_like_f    REAL,
                    temp_high_f     REAL,
                    temp_low_f      REAL,
                    humidity_max    REAL,
                    humidity_min    REAL
                );

                CREATE TABLE IF NOT EXISTS miner_logs (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    collected_at  TEXT    NOT NULL,
                    miner_id      TEXT    NOT NULL,
                    model         TEXT,
                    health_status TEXT,
                    log_file      TEXT    NOT NULL,
                    content       TEXT    NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_logs_miner
                    ON miner_logs(miner_id, collected_at);

                CREATE TABLE IF NOT EXISTS miner_restarts (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    restarted_at    TEXT    NOT NULL,
                    miner_id        TEXT    NOT NULL,
                    ip              TEXT,
                    model           TEXT,
                    restart_type    TEXT,
                    elevated_until  TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_restarts_miner
                    ON miner_restarts(miner_id, restarted_at);
            """)
        logger.info("Database ready at %s", self.db_path)

    def save_notifications(self, notifications: List[Dict]) -> None:
        """Store AMS notifications in the database."""
        if not notifications:
            return
        now = datetime.now().isoformat()
        rows = []
        for n in notifications:
            params = n.get("params", {})
            rows.append((
                now,
                n.get("id"),
                str(n.get("deviceID", "")),
                n.get("type"),
                n.get("key"),
                params.get("alertLevel"),
                params.get("minerIp"),
                json.dumps(n),
            ))
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO ams_notifications "
                "(recorded_at, notification_id, device_id, type, key, "
                " alert_level, miner_ip, raw) VALUES (?,?,?,?,?,?,?,?)",
                rows
            )
        logger.info("Saved %s AMS notifications", len(rows))

    def save_weather(self, weather: Dict[str, Any]) -> None:
        """Store a weather reading alongside scan data."""
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO weather_readings "
                "(recorded_at, temp_f, humidity_pct, feels_like_f, "
                " temp_high_f, temp_low_f, humidity_max, humidity_min) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (now,
                 weather.get("temp_f"),
                 weather.get("humidity_pct"),
                 weather.get("feels_like_f"),
                 weather.get("temp_high_f"),
                 weather.get("temp_low_f"),
                 weather.get("humidity_max"),
                 weather.get("humidity_min"))
            )

    def save_scan(self, miners: List[Dict], issues: List[Dict]) -> int:
        """Write scan summary and all miner readings. Returns scan_id."""
        now      = datetime.now().isoformat()
        online   = sum(1 for m in miners if m.get("status") == "online")
        offline  = len(miners) - online

        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO scans (scanned_at, total_miners, online, offline, issues) "
                "VALUES (?, ?, ?, ?, ?)",
                (now, len(miners), online, offline, len(issues))
            )
            scan_id = cur.lastrowid

            # Build a quick lookup of issues by miner id
            issue_map = {i["id"]: i for i in issues}

            rows = []
            for m in miners:
                miner_id  = str(m.get("id", ""))
                max_hr    = m.get("maxHashrate") or 0
                hashrate  = m.get("hashrate") or 0
                pct       = round((hashrate / max_hr) * 100, 1) if max_hr > 0 else 0.0
                temp_raw  = m.get("tempChip") or 0
                temp      = temp_raw if temp_raw >= 0 else None
                issue     = issue_map.get(miner_id)

                rows.append((
                    scan_id,
                    now,
                    miner_id,
                    m.get("ip"),
                    m.get("shortModel", m.get("name")),
                    m.get("status"),
                    hashrate,
                    max_hr,
                    pct,
                    temp,
                    " | ".join(issue["issues"]) if issue else None,
                    issue["action"] if issue else None,
                    issue.get("pdu_id") if issue else None,
                    issue.get("outlet") if issue else None,
                ))

            conn.executemany(
                "INSERT INTO miner_readings "
                "(scan_id, scanned_at, miner_id, ip, model, status, hashrate, "
                " max_hashrate, hashrate_pct, temp_chip, issue, action, pdu_id, outlet) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                rows
            )

        logger.info("Scan #%s saved to database (%s miners)", scan_id, len(miners))
        return scan_id

    def save_logs(self, miner_id: str, model: str, health_status: str,
                  log_files: Dict[str, str]) -> None:
        """Store extracted log file contents for a miner."""
        now = datetime.now().isoformat()
        rows = [
            (now, miner_id, model, health_status, filename, content)
            for filename, content in log_files.items()
        ]
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO miner_logs "
                "(collected_at, miner_id, model, health_status, log_file, content) "
                "VALUES (?,?,?,?,?,?)",
                rows
            )
        logger.info("Saved %s log files for miner %s (%s)", len(rows), miner_id, health_status)

    def purge_old_logs(self, days: int = 7) -> int:
        """Delete miner log entries older than N days. Returns count deleted.

        Only purges the miner_logs table (raw log content).
        Scan history and miner_readings are kept permanently for trending.
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM miner_logs WHERE collected_at < ?", (cutoff,)
            )
            deleted = cur.rowcount
        if deleted:
            logger.info("Purged %s log entries older than %s days", deleted, days)
        return deleted
        """Return datetime of last log collection for this miner, or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT collected_at FROM miner_logs WHERE miner_id=? "
                "ORDER BY id DESC LIMIT 1",
                (miner_id,)
            ).fetchone()
        if row:
            try:
                return datetime.fromisoformat(row[0])
            except Exception:
                return None
        return None

    def last_log_collected(self, miner_id: str) -> Optional[datetime]:
        """Return datetime of last log collection for this miner, or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT collected_at FROM miner_logs WHERE miner_id=? "
                "ORDER BY id DESC LIMIT 1",
                (miner_id,)
            ).fetchone()
        if row:
            try:
                return datetime.fromisoformat(row[0])
            except Exception:
                return None
        return None

    def record_restart(self, miner_id: str, ip: str, model: str,
                       restart_type: str, elevated_hours: int = 3) -> None:
        """Record a restart event and set elevated monitoring window."""
        now           = datetime.now()
        elevated_until = (now + timedelta(hours=elevated_hours)).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO miner_restarts "
                "(restarted_at, miner_id, ip, model, restart_type, elevated_until) "
                "VALUES (?,?,?,?,?,?)",
                (now.isoformat(), miner_id, ip, model, restart_type, elevated_until)
            )
        logger.info("Restart recorded for miner %s (%s) — elevated monitoring for %sh",
                    miner_id, restart_type, elevated_hours)

    def is_elevated_monitoring(self, miner_id: str) -> bool:
        """Return True if this miner is within its post-restart elevated monitoring window."""
        now = datetime.now().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT elevated_until FROM miner_restarts "
                "WHERE miner_id=? AND elevated_until > ? "
                "ORDER BY id DESC LIMIT 1",
                (miner_id, now)
            ).fetchone()
        return row is not None
        """Return datetime of last log collection for this miner, or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT collected_at FROM miner_logs WHERE miner_id=? "
                "ORDER BY id DESC LIMIT 1",
                (miner_id,)
            ).fetchone()
        if row:
            try:
                return datetime.fromisoformat(row[0])
            except Exception:
                return None
        return None
        return scan_id


# ------------------------------------------------------------
# Slack notifier — direct fleet alerts to #mining-guardian
# ------------------------------------------------------------

class SlackNotifier:

    def __init__(self, webhook_url: Optional[str], channel_id: Optional[str] = None):
        self.webhook_url = webhook_url  # Slack incoming webhook URL
        self.channel_id  = channel_id  # for future direct API use

    def send_scan(self, miners: List[Dict], issues: List[Dict],
                  wx: Optional[Dict] = None,
                  ams_notifs: Optional[List[Dict]] = None) -> None:
        """POST a formatted scan summary to Slack via incoming webhook."""
        if not self.webhook_url:
            logger.debug("Slack webhook not configured — skipping Slack notification")
            return

        now     = datetime.now().strftime("%Y-%m-%d %H:%M")
        online  = sum(1 for m in miners if m.get("status") == "online")
        offline = len(miners) - online

        pdu_cycles   = [i for i in issues if i["action"] == "PDU_CYCLE"]
        fw_restarts  = [i for i in issues if i["action"] == "RESTART"]
        phys_cycles  = [i for i in issues if i["action"] == "PHYSICAL_CYCLE"]
        monitors     = [i for i in issues if i["action"] == "MONITOR"]
        temp_action  = [i for i in issues if i["action"] == "TEMP_ACTION_REQUIRED"]

        # Header
        if not issues:
            status_line = "✅ All miners operating normally."
        else:
            status_line = f"⚠️ {len(issues)} miner(s) need attention."

        lines = [
            f"*🤖 Mining Guardian Scan — {now}*",
            f"Fleet: *{len(miners)} miners* | 🟢 {online} online | 🔴 {offline} offline",
        ]

        # Add weather line if available
        if wx:
            lines.append(
                f"🌡️ Outside: *{wx['temp_f']}°F* | Humidity: *{wx['humidity_pct']}%* | "
                f"Feels like: {wx['feels_like_f']}°F | Today: {wx['temp_low_f']}–{wx['temp_high_f']}°F"
            )

        lines.append(status_line)

        if pdu_cycles:
            lines.append(f"\n*🔴 PDU Power Cycle Recommended ({len(pdu_cycles)} miners)*")
            for i in pdu_cycles:
                lines.append(f"  • `{i['ip']}` {i['model']} — {i.get('pdu_action', 'No PDU info')}")
            lines.append("  _After power cycle: logs collected immediately on boot. Elevated monitoring active for 3 hours._")

        if fw_restarts:
            lines.append(f"\n*🔴 Firmware Restart Recommended ({len(fw_restarts)} miners)*")
            for i in fw_restarts:
                lines.append(f"  • `{i['ip']}` {i['model']} — Hashrate: {i['hashrate_pct']} | Temp: {i['temp_chip']}")

        if phys_cycles:
            lines.append(f"\n*🔴 Physical Power Cycle Required ({len(phys_cycles)} miners)*")
            lines.append("  ⚠️ No PDU assigned — cannot remote restart. Must be done manually at the facility.")
            for i in phys_cycles:
                lines.append(f"  • `{i['ip']}` {i['model']} — OFFLINE, no PDU")

        if temp_action:
            lines.append(f"\n*🔴 High Temp — Action Required ({len(temp_action)} miners)*")
            for i in temp_action:
                lines.append(f"  • `{i['ip']}` {i['model']} — {i['temp_chip']}")
            lines.append("  Options: [1] Restart  [2] Lower power  [3] Raise cooling")

        if monitors:
            lines.append(f"\n*🟡 Monitor — Running Warm ({len(monitors)} miners)*")
            for i in monitors:
                lines.append(f"  • `{i['ip']}` {i['model']} — {i['temp_chip']}")

        if issues:
            lines.append("\n_DRY RUN — no actions taken. Reply to approve actions._")

        # AMS notifications section
        if ams_notifs:
            critical = [n for n in ams_notifs if n.get("params", {}).get("alertLevel") == "Critical"]
            warnings = [n for n in ams_notifs if n.get("params", {}).get("alertLevel") == "Warning"]
            if critical or warnings:
                lines.append(f"\n*⚠️ AMS Notifications ({len(ams_notifs)} total)*")
                if critical:
                    lines.append(f"  🔴 Critical: {len(critical)}")
                    for n in critical[:5]:
                        ip  = n.get("params", {}).get("minerIp", "unknown")
                        key = n.get("key", "unknown")
                        lines.append(f"    • `{ip}` — {key}")
                if warnings:
                    lines.append(f"  🟡 Warning: {len(warnings)}")
                    for n in warnings[:3]:
                        ip  = n.get("params", {}).get("minerIp", "unknown")
                        key = n.get("key", "unknown")
                        lines.append(f"    • `{ip}` — {key}")

        payload = {"text": "\n".join(lines)}

        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info("Slack notified — scan summary posted to #mining-guardian")
            else:
                logger.warning("Slack webhook returned %s: %s", resp.status_code, resp.text)
        except Exception as exc:
            logger.warning("Slack notification failed: %s", exc)


class MiningGuardian:
    HASHRATE_THRESHOLD = 0.90   # flag if below 90% of maxHashrate

    def __init__(self, config: GuardianConfig):
        self.config   = config
        self.ams      = AMSClient(config)
        self.notifier = OpenClawNotifier(config.openclaw_webhook_url)
        self.slack    = SlackNotifier(GuardianConfig._resolve(config.slack_webhook_url) if config.slack_webhook_url else None)
        self.db       = GuardianDB()
        self.weather  = WeatherCollector()

    # ── Per-miner analysis ────────────────────────────────────

    def _analyze_miner(self, miner: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Return an issue dict if the miner has a problem, else None."""
        miner_id   = str(miner.get("id", "unknown"))
        ip         = miner.get("ip", "unknown")
        name       = miner.get("shortModel", miner.get("name", "unknown"))
        status     = miner.get("status", "unknown")
        hashrate   = miner.get("hashrate", 0) or 0
        max_hr     = miner.get("maxHashrate", 0) or 0
        temp_chip_raw = miner.get("tempChip", 0) or 0
        temp_chip     = temp_chip_raw if temp_chip_raw >= 0 else None
        temp_low   = miner.get("tempChipLow", 86)
        temp_med   = miner.get("tempChipMedium", 95)
        temp_max   = miner.get("maxTempChip", 100)
        # Power — prefer PDU outlet reading (more accurate), fall back to miner-reported
        pdu_power    = miner.get("pduOutlet", {}).get("power", 0) or 0
        miner_power  = miner.get("consumption", 0) or 0
        power_watts  = pdu_power if pdu_power > 0 else miner_power
        power_source = "PDU" if pdu_power > 0 else "miner"

        pdu_id       = miner.get("pduOutlet", {}).get("pduID") or 0
        outlet_index = miner.get("pduOutlet", {}).get("outletIndex") or 0
        has_pdu      = pdu_id > 0 and outlet_index > 0

        issues = []
        action = None
        pdu_action = None

        # ── Hashrate check ──────────────────────────────────
        if status == "offline":
            pct = 0.0
            issues.append("OFFLINE")
            if has_pdu:
                action = "PDU_CYCLE"
                pdu_action = f"PDU {pdu_id} → Outlet {outlet_index}"
            else:
                # No PDU assigned — can't remote restart, must physically power cycle
                action = "PHYSICAL_CYCLE"
        elif max_hr > 0:
            pct = (hashrate / max_hr) * 100
            if pct < self.HASHRATE_THRESHOLD * 100:
                issues.append(f"Hashrate {pct:.1f}% of max ({hashrate:,} / {max_hr:,} GH/s)")
                action = "RESTART"
        else:
            pct = None

        # ── Temp check ──────────────────────────────────────
        # Green:  < 76°C  — healthy, no action
        # Yellow: 76–85°C — monitor
        # Red:    86°C+   — operator chooses action
        temp_issue = None
        if temp_chip is None:
            temp_issue = "⚠️ Sensor error — temp reading invalid"
        elif temp_chip >= 86:
            temp_issue = f"🔴 RED — chip {temp_chip}°C (86°C+ threshold)"
            action = "TEMP_ACTION_REQUIRED"
        elif temp_chip >= 76:
            temp_issue = f"🟡 YELLOW — chip {temp_chip}°C (76–85°C range)"
            if not action:
                action = "MONITOR"
        # below 76 is green — no issue logged

        if temp_issue:
            issues.append(temp_issue)

        if not issues:
            return None

        return {
            "id":       miner_id,
            "ip":       ip,
            "model":    name,
            "status":   status,
            "hashrate_pct": f"{pct:.1f}%" if pct is not None else "N/A",
            "temp_chip": f"{temp_chip}°C" if temp_chip is not None else "sensor error",
            "issues":   issues,
            "action":   action,
            "pdu_id":   pdu_id,
            "outlet":   outlet_index,
            "pdu_action": pdu_action,
            "power_watts":  power_watts,
            "power_source": power_source,
        }

    # ── Report printer ────────────────────────────────────────

    @staticmethod
    def _print_report(miners: List[Dict], issues: List[Dict],
                      wx: Optional[Dict] = None,
                      ams_notifs: Optional[List[Dict]] = None) -> None:
        now      = datetime.now().strftime("%Y-%m-%d %H:%M")
        online   = sum(1 for m in miners if m.get("status") == "online")
        offline  = len(miners) - online
        divider  = "━" * 60

        print(f"\n{divider}")
        print(f"  MINING GUARDIAN SCAN — {now}")
        print(divider)
        print(f"  Fleet:   {len(miners)} miners  |  {online} online  |  {offline} offline")

        # Weather line
        if wx:
            print(f"  Weather: {wx['temp_f']}°F  |  Humidity: {wx['humidity_pct']}%  "
                  f"|  Feels like: {wx['feels_like_f']}°F  "
                  f"|  Today: {wx['temp_low_f']}–{wx['temp_high_f']}°F")
        print(divider)

        if not issues:
            print("  ✅ All miners operating within normal parameters.")
        else:
            # Group by action
            pdu_cycles    = [i for i in issues if i["action"] == "PDU_CYCLE"]
            fw_restarts   = [i for i in issues if i["action"] == "RESTART"]
            phys_cycles   = [i for i in issues if i["action"] == "PHYSICAL_CYCLE"]
            monitors      = [i for i in issues if i["action"] == "MONITOR"]
            restarts      = pdu_cycles + fw_restarts + phys_cycles

            if restarts:

                if pdu_cycles:
                    print(f"\n  🔴 OFFLINE — PDU POWER CYCLE RECOMMENDED ({len(pdu_cycles)} miners)\n")
                    print(f"  {'ID':<8} {'IP':<18} {'Model':<14} {'Hashrate':<10} {'PDU Action':<25} Issue")
                    print(f"  {'-'*8} {'-'*18} {'-'*14} {'-'*10} {'-'*25} {'-'*20}")
                    for i in pdu_cycles:
                        issue_str = " | ".join(i["issues"])
                        pdu_str = i["pdu_action"] or "—"
                        print(f"  {i['id']:<8} {i['ip']:<18} {i['model']:<14} {i['hashrate_pct']:<10} {pdu_str:<25} {issue_str}")

                if fw_restarts:
                    print(f"\n  🔴 UNDERPERFORMING — FIRMWARE RESTART RECOMMENDED ({len(fw_restarts)} miners)\n")
                    print(f"  {'ID':<8} {'IP':<18} {'Model':<14} {'Hashrate':<10} {'ChipTemp':<10} Issue")
                    print(f"  {'-'*8} {'-'*18} {'-'*14} {'-'*10} {'-'*10} {'-'*30}")
                    for i in fw_restarts:
                        issue_str = " | ".join(i["issues"])
                        print(f"  {i['id']:<8} {i['ip']:<18} {i['model']:<14} {i['hashrate_pct']:<10} {i['temp_chip']:<10} {issue_str}")

                if phys_cycles:
                    print(f"\n  🔴 OFFLINE — PHYSICAL POWER CYCLE REQUIRED ({len(phys_cycles)} miners)\n")
                    print(f"  ⚠️  No PDU assigned — cannot remote restart. Must be power cycled manually.\n")
                    print(f"  {'ID':<8} {'IP':<18} {'Model':<14} {'Hashrate':<10} Issue")
                    print(f"  {'-'*8} {'-'*18} {'-'*14} {'-'*10} {'-'*30}")
                    for i in phys_cycles:
                        issue_str = " | ".join(i["issues"])
                        print(f"  {i['id']:<8} {i['ip']:<18} {i['model']:<14} {i['hashrate_pct']:<10} {issue_str}")
                    print(f"\n  Action: Go to the facility and manually power cycle these miners.")

            # Miners with high temp — show action menu
            temp_action = [i for i in issues if i["action"] == "TEMP_ACTION_REQUIRED"]
            if temp_action:
                print(f"\n  🔴 HIGH TEMP — ACTION REQUIRED ({len(temp_action)} miners)\n")
                print(f"  {'ID':<8} {'IP':<18} {'Model':<14} {'ChipTemp':<10} Issue")
                print(f"  {'-'*8} {'-'*18} {'-'*14} {'-'*10} {'-'*30}")
                for i in temp_action:
                    issue_str = " | ".join(i["issues"])
                    print(f"  {i['id']:<8} {i['ip']:<18} {i['model']:<14} {i['temp_chip']:<10} {issue_str}")
                print(f"\n  Recommended actions for each miner above:")
                print(f"    [1] Restart the miner")
                print(f"    [2] Lower the power level (reduce hashrate to cut heat)")
                print(f"    [3] Raise cooling — increase fan speed or coolant flow rate")

            if monitors:
                monitor_word = "miner" if len(monitors) == 1 else "miners"
                print(f"\n  🟡 MONITOR ({len(monitors)} {monitor_word})\n")
                print(f"  {'ID':<8} {'IP':<18} {'Model':<14} {'ChipTemp':<10} Issue")
                print(f"  {'-'*8} {'-'*18} {'-'*14} {'-'*10} {'-'*30}")
                for i in monitors:
                    issue_str = " | ".join(i["issues"])
                    print(f"  {i['id']:<8} {i['ip']:<18} {i['model']:<14} {i['temp_chip']:<10} {issue_str}")

        healthy = len(miners) - len(issues)
        print(f"\n  ✅ Healthy: {healthy} miners within normal parameters")
        print(f"  {'[DRY RUN — no actions taken]' if True else ''}")
        print(f"{divider}\n")
        # AMS notifications section
        if ams_notifs:
            critical = [n for n in ams_notifs if n.get("params", {}).get("alertLevel") == "Critical"]
            warnings = [n for n in ams_notifs if n.get("params", {}).get("alertLevel") == "Warning"]
            logger.info("AMS notifications — %s critical, %s warning",
                        len(critical), len(warnings))
        # Mirror the report to the log file
        logger.info("Scan complete — %s miners | %s online | %s offline | %s issues",
                    len(miners), online, offline, len(issues))

    # ── Main entry ────────────────────────────────────────────

    def collect_logs(self, miners: List[Dict], issues: List[Dict]) -> None:
        """Download logs for flagged miners every scan, healthy miners every 6 hours."""
        if not self.config.collect_logs:
            logger.debug("Log collection disabled — set collect_logs: true in config to enable")
            return

        issue_ids = {i["id"] for i in issues}
        now = datetime.now()
        collected = 0

        for miner in miners:
            miner_id  = str(miner.get("id", ""))
            model     = miner.get("shortModel", miner.get("name", "unknown"))
            status    = miner.get("status", "unknown")
            flagged   = miner_id in issue_ids

            # Skip offline miners — no connection means no logs available
            if status == "offline":
                continue

            # Determine collection priority
            elevated  = self.db.is_elevated_monitoring(miner_id)
            last      = self.db.last_log_collected(miner_id)

            if flagged or elevated:
                # Flagged or post-restart elevated — always collect
                should_collect = True
                if elevated:
                    health_status = "post-restart"
                else:
                    health_status = "flagged"
            elif status == "online":
                # Healthy miners — collect every 6 hours
                should_collect = last is None or (now - last).total_seconds() > 21600
                health_status = "healthy"
            else:
                # Offline miners with no PDU — skip log collection
                should_collect = False
                health_status = "offline"

            if not should_collect:
                continue

            try:
                log_files = self.ams.collect_miner_logs(int(miner_id))
                if log_files:
                    self.db.save_logs(miner_id, model, health_status, log_files)
                    collected += 1
            except Exception as e:
                logger.warning("Log collection failed for miner %s: %s", miner_id, e)

        if collected:
            logger.info("Log collection complete — %s miners logged", collected)

    def run_once(self) -> Dict[str, Any]:
        # Fetch weather and AMS notifications first
        wx = self.weather.fetch()
        if wx:
            self.db.save_weather(wx)

        ams_notifs = self.ams.get_notifications("miner")
        if ams_notifs:
            self.db.save_notifications(ams_notifs)
            logger.info("Pulled %s AMS notifications", len(ams_notifs))

        miners   = self.ams.get_miners(self.config.miner_filters)
        issues   = [r for r in (self._analyze_miner(m) for m in miners) if r]
        self._print_report(miners, issues, wx, ams_notifs)
        self.db.save_scan(miners, issues)
        self.db.purge_old_logs(days=7)
        self.collect_logs(miners, issues)
        self.notifier.send_scan(miners, issues)
        self.slack.send_scan(miners, issues, wx, ams_notifs)
        return {
            "scanned": len(miners),
            "issues":  len(issues),
            "pdu_cycle":       [i["id"] for i in issues if i["action"] == "PDU_CYCLE"],
            "firmware_restart":[i["id"] for i in issues if i["action"] == "RESTART"],
            "physical_cycle":  [i["id"] for i in issues if i["action"] == "PHYSICAL_CYCLE"],
            "monitor":         [i["id"] for i in issues if i["action"] == "MONITOR"],
        }

    def loop(self) -> None:
        while True:
            try:
                self.run_once()
            except Exception:
                logger.exception("Guardian loop error")
            time.sleep(self.config.scan_interval_seconds)


# ------------------------------------------------------------
# Example config + entrypoint
# ------------------------------------------------------------

EXAMPLE_CONFIG = {
    "ams_base_url": "https://api-staging.dev.bixbit.io/api/v1",
    "ams_email":        "env:AMS_EMAIL",
    "ams_password":     "env:AMS_PASSWORD",
    "ams_workspace_id": "env:AMS_WORKSPACE_ID",
    "openclaw_webhook_url": None,
    "dry_run": True,
    "scan_interval_seconds": 300,
    "approval_mode": "manual",
    "miner_filters": {},
    "rules": [
        {
            "key": "telemetry.hashrate_ths",
            "operator": "gte",
            "expected": 85,
            "severity": "critical",
            "recommended_fix": None,
            "note": "Hashrate below model minimum — requires operator review"
        },
        {
            "key": "telemetry.chip_temp_c",
            "operator": "between",
            "expected": [40, 80],
            "severity": "critical",
            "recommended_fix": "efficiency",
            "note": "Chip temp outside safe envelope — drop to efficiency profile"
        },
    ]
}


def write_example_config(path: str = "config.example.json") -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(EXAMPLE_CONFIG, f, indent=2)
    logger.info("Wrote %s", path)


if __name__ == "__main__":
    import sys
    config_path = os.environ.get("GUARDIAN_CONFIG", "config.json")
    if not os.path.exists(config_path):
        write_example_config()
        raise SystemExit("Create config.json from config.example.json, then re-run.")

    config   = GuardianConfig.from_file(config_path)
    guardian = MiningGuardian(config)

    if "--loop" in sys.argv:
        logger.info("Starting Mining Guardian in loop mode (interval=%ss)", config.scan_interval_seconds)
        guardian.loop()
    else:
        result = guardian.run_once()
        print(json.dumps(result, indent=2))
