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

from hashrate_evaluation import (
    MinerSpecsLoader, BaselineManager, HashrateTierResolver,
    parse_bixbit_profile,
)
from miner_verify import verify_miner_online
from facility_monitor import FacilityMonitor
from hvac_client import HVACClient, format_hvac_report


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
    slack_bot_token:   Optional[str] = None
    dry_run: bool = True
    collect_logs: bool = False  # enable log collection independently of dry_run
    scan_interval_seconds: int = 300
    slack_interval_seconds: int = 3600  # post to Slack at most once per hour
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
            slack_bot_token=raw.get("slack_bot_token"),
            dry_run=raw.get("dry_run", True),
            collect_logs=raw.get("collect_logs", False),
            scan_interval_seconds=raw.get("scan_interval_seconds", 300),
            slack_interval_seconds=raw.get("slack_interval_seconds", 3600),
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
                      priority: str = "normal") -> Dict:
        """POST /ticket — create a new maintenance ticket.

        Args:
            title: Short description of the issue
            description: Full details
            priority: "low", "normal", "high", or "critical"

        Mining Guardian can auto-create tickets when miners are flagged
        for physical intervention (no PDU assigned, needs manual visit).
        """
        token = self._ensure_token()
        resp  = self.session.post(
            f"{self.base_url}/ticket",
            json={"title": title, "description": description, "priority": priority},
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        if resp.status_code == 200:
            logger.info("Ticket created: %s", title)
            return resp.json()
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
# OpenClaw Gateway runs at http://127.0.0.1:18789 by default.
# Webhook URL format: http://127.0.0.1:18789/hooks
# Requires hooks.enabled: true and hooks.token set in ~/.openclaw/openclaw.json
# Full URL example: http://127.0.0.1:18789/hooks  (token sent as Authorization header)
#
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
        board_restarts_oc = [i for i in issues if i["action"] == "RESTART_CHECK_BOARDS"]
        phys_oc        = [i for i in issues if i["action"] == "PHYSICAL_CYCLE"]
        monitors_oc    = [i for i in issues if i["action"] == "MONITOR"]
        temp_oc        = [i for i in issues if i["action"] == "TEMP_ACTION_REQUIRED"]

        parts = []
        if pdu_cycles_oc:
            parts.append(f"{len(pdu_cycles_oc)} offline miner(s) need PDU power cycle")
        if fw_restarts_oc:
            parts.append(f"{len(fw_restarts_oc)} miner(s) need firmware restart")
        if board_restarts_oc:
            dead_details = ", ".join(
                f"{i['ip']} boards {i.get('chain_info', {}).get('dead_indices', [])}"
                for i in board_restarts_oc
            )
            parts.append(
                f"{len(board_restarts_oc)} miner(s) have dead hashboard(s) — "
                f"restart + log comparison required ({dead_details})"
            )
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
                    "miner_id":    i["id"],
                    "ip":          i["ip"],
                    "model":       i["model"],
                    "status":      i["status"],
                    "hashrate":    i["hashrate_pct"],
                    "temp_chip":   i["temp_chip"],
                    "action":      i["action"],
                    "pdu_action":  i.get("pdu_action"),
                    "detail":      " | ".join(i["issues"]),
                    "map_location": i.get("map_location", "N/A"),
                    "active_profile": i.get("active_profile", "N/A"),
                    "pdu_power_kw":   i.get("pdu_power_kw", None),
                }
                for i in issues
            ],
            # Instruction for the LLM — tells it what to do with this data
            "instructions": (
                "You are Mining Guardian's AI analyst for BiXBiT USA in Fort Worth, TX. "
                "Review the fleet scan below and post a concise Slack message to #mining-guardian. "
                "For each miner needing action, include: IP, model, map location, active profile, "
                "PDU power draw, and recommended fix. "
                "Ask the operator to reply APPROVE or DENY in the thread to confirm actions. "
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
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id             INTEGER NOT NULL REFERENCES scans(id),
                    scanned_at          TEXT    NOT NULL,
                    miner_id            TEXT    NOT NULL,
                    ip                  TEXT,
                    mac                 TEXT,
                    model               TEXT,
                    status              TEXT,
                    hashrate            REAL,
                    max_hashrate        REAL,
                    hashrate_pct        REAL,
                    temp_chip           REAL,
                    temp_board          REAL,
                    cooling_mode        INTEGER,
                    current_profile     TEXT,
                    firmware_manufacturer TEXT,
                    firmware_version    TEXT,
                    uptime              TEXT,
                    consumption         REAL,
                    max_consumption     REAL,
                    pdu_power           REAL,
                    map_location        TEXT,
                    error_codes         TEXT,
                    issue               TEXT,
                    action              TEXT,
                    pdu_id              INTEGER,
                    outlet              INTEGER
                );

                CREATE INDEX IF NOT EXISTS idx_readings_miner
                    ON miner_readings(miner_id, scanned_at);

                CREATE TABLE IF NOT EXISTS pending_approvals (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at    TEXT    NOT NULL,
                    scan_id       INTEGER,
                    thread_ts     TEXT    NOT NULL,
                    miner_id      TEXT    NOT NULL,
                    ip            TEXT    NOT NULL,
                    model         TEXT,
                    action_type   TEXT    NOT NULL,
                    problem       TEXT,
                    pdu_id        INTEGER,
                    outlet        INTEGER,
                    status        TEXT    DEFAULT 'PENDING',
                    responded_at  TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_pending_thread
                    ON pending_approvals(thread_ts, status);

                CREATE TABLE IF NOT EXISTS action_audit_log (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp     TEXT    NOT NULL,
                    date          TEXT    NOT NULL,
                    scan_id       INTEGER,
                    miner_id      TEXT    NOT NULL,
                    ip            TEXT    NOT NULL,
                    model         TEXT,
                    problem       TEXT    NOT NULL,
                    action_taken  TEXT    NOT NULL,
                    decision      TEXT    NOT NULL,
                    approved_by   TEXT,
                    slack_user_id TEXT,
                    notes         TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_audit_date
                    ON action_audit_log(date);

                CREATE INDEX IF NOT EXISTS idx_audit_miner
                    ON action_audit_log(miner_id);

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

                CREATE TABLE IF NOT EXISTS hvac_readings (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at     TEXT    NOT NULL,
                    supply_temp_f   REAL,
                    return_temp_f   REAL,
                    delta_t_f       REAL,
                    diff_pressure   REAL,
                    spray_pump_on   INTEGER,
                    cwp1_vfd_pct    REAL,
                    cwp2_vfd_pct    REAL,
                    ct1_vfd_pct     REAL,
                    ct2_vfd_pct     REAL,
                    leak_alarm      INTEGER DEFAULT 0,
                    ct1_fault       INTEGER DEFAULT 0,
                    ct2_fault       INTEGER DEFAULT 0,
                    pump_fault      INTEGER DEFAULT 0
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

                CREATE TABLE IF NOT EXISTS known_dead_boards (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    miner_id        TEXT    NOT NULL,
                    ip              TEXT,
                    model           TEXT,
                    board_indices   TEXT    NOT NULL,
                    first_seen      TEXT    NOT NULL,
                    restart_attempted TEXT,
                    restart_result  TEXT,
                    ticket_created  TEXT,
                    resolved_at     TEXT,
                    notes           TEXT
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_dead_boards_miner
                    ON known_dead_boards(miner_id)
                    WHERE resolved_at IS NULL;
            """)
        logger.info("Database ready at %s", self.db_path)

    def save_pending_approvals(self, thread_ts: str, scan_id: int,
                               issues: List[Dict]) -> None:
        """Save actionable issues as pending approvals linked to a Slack thread."""
        now  = datetime.now().isoformat()
        rows = []
        for i in issues:
            if i["action"] not in ("PDU_CYCLE", "RESTART", "RESTART_CHECK_BOARDS"):
                continue  # PHYSICAL_CYCLE requires manual visit, MONITOR needs no approval
            rows.append((
                now, scan_id, thread_ts,
                i["id"], i["ip"], i["model"],
                i["action"], " | ".join(i.get("issues", [])),
                i.get("pdu_id"), i.get("outlet"),
            ))
        if not rows:
            return
        with self._connect() as conn:
            conn.executemany("""
                INSERT INTO pending_approvals
                (created_at, scan_id, thread_ts, miner_id, ip, model,
                 action_type, problem, pdu_id, outlet)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, rows)
        logger.info("Saved %s pending approvals for thread %s", len(rows), thread_ts)

    def log_action(self, miner_id: str, ip: str, model: str,
                   problem: str, action_taken: str, decision: str,
                   approved_by: str = None, slack_user_id: str = None,
                   scan_id: int = None, notes: str = None) -> None:
        """Log every approval or denial to the permanent action audit log.

        Never expires. Grouped by date for easy review.
        approved_by should be the Slack display name of the person who responded.
        decision should be 'APPROVED' or 'DENIED'.
        """
        now  = datetime.now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO action_audit_log "
                "(timestamp, date, scan_id, miner_id, ip, model, "
                " problem, action_taken, decision, approved_by, "
                " slack_user_id, notes) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (now.isoformat(), now.strftime("%Y-%m-%d"), scan_id,
                 miner_id, ip, model, problem, action_taken,
                 decision, approved_by, slack_user_id, notes)
            )
        logger.info("Audit log: %s %s on %s (%s) by %s",
                    decision, action_taken, ip, model, approved_by or "unknown")

    def get_audit_log(self, days: int = None, miner_id: str = None,
                      limit: int = 100) -> List[Dict]:
        """Retrieve audit log entries, optionally filtered by date range or miner."""
        query  = "SELECT * FROM action_audit_log WHERE 1=1"
        params = []
        if days:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            query += " AND date >= ?"
            params.append(cutoff)
        if miner_id:
            query += " AND miner_id = ?"
            params.append(miner_id)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

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

    def save_hvac(self, hvac) -> None:
        """Store an HVAC snapshot alongside scan data."""
        if hvac is None:
            return
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO hvac_readings "
                "(recorded_at, supply_temp_f, return_temp_f, delta_t_f, "
                " diff_pressure, spray_pump_on, cwp1_vfd_pct, cwp2_vfd_pct, "
                " ct1_vfd_pct, ct2_vfd_pct, leak_alarm, ct1_fault, ct2_fault, pump_fault) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (now,
                 hvac.supply_temp_f,
                 hvac.return_temp_f,
                 hvac.delta_t_f,
                 hvac.diff_pressure_psi,
                 1 if hvac.spray_pump_on else 0,
                 hvac.cwp1_vfd_pct,
                 hvac.cwp2_vfd_pct,
                 hvac.ct1_vfd_pct,
                 hvac.ct2_vfd_pct,
                 1 if hvac.leak_alarm else 0,
                 1 if hvac.ct1_fault else 0,
                 1 if hvac.ct2_fault else 0,
                 1 if hvac.pump_fault else 0)
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
                temp_board = m.get("tempBoard") or 0
                pdu_power  = (m.get("pduOutlet") or {}).get("power") or 0
                map_loc   = (m.get("mapLocation") or {}).get("title") or None
                err_codes = str(m.get("errorCodes") or []) if m.get("errorCodes") else None
                issue     = issue_map.get(miner_id)

                # Use 'name' when profile confirms BiXBiT firmware and shortModel is wrong
                raw_model = m.get("shortModel", m.get("name", "unknown"))
                profile_str = m.get("currentProfile", "")
                if "TH/s" in profile_str and m.get("name") and m.get("name") != raw_model:
                    raw_model = m["name"]
                rows.append((
                    scan_id,
                    now,
                    miner_id,
                    m.get("ip"),
                    m.get("mac"),
                    raw_model,
                    m.get("status"),
                    hashrate,
                    max_hr,
                    pct,
                    temp,
                    temp_board if temp_board >= 0 else None,
                    m.get("coolingMode"),
                    m.get("currentProfile"),
                    m.get("firmwareManufacturer"),
                    m.get("firmwareVersion"),
                    m.get("uptime"),
                    m.get("consumption") or 0,
                    m.get("maxConsumption") or 0,
                    round(pdu_power / 1000, 2) if pdu_power else 0,
                    map_loc,
                    err_codes,
                    " | ".join(issue["issues"]) if issue else None,
                    issue["action"] if issue else None,
                    issue.get("pdu_id") if issue else None,
                    issue.get("outlet") if issue else None,
                ))

            conn.executemany(
                "INSERT INTO miner_readings "
                "(scan_id, scanned_at, miner_id, ip, mac, model, status, hashrate, "
                " max_hashrate, hashrate_pct, temp_chip, temp_board, cooling_mode, "
                " current_profile, firmware_manufacturer, firmware_version, uptime, "
                " consumption, max_consumption, pdu_power, map_location, error_codes, "
                " issue, action, pdu_id, outlet) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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

    def has_known_dead_boards(self, miner_id: str) -> bool:
        """Check if this miner has unresolved known dead boards (already attempted restart)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM known_dead_boards WHERE miner_id = ? AND resolved_at IS NULL AND restart_attempted IS NOT NULL",
                (miner_id,)
            ).fetchone()
            return row is not None

    def register_dead_boards(self, miner_id: str, ip: str, model: str,
                             board_indices: list, restart_result: str = None):
        """Register or update known dead boards for a miner."""
        now = datetime.now().isoformat()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM known_dead_boards WHERE miner_id = ? AND resolved_at IS NULL",
                (miner_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE known_dead_boards SET board_indices = ?, restart_attempted = ?, restart_result = ? WHERE id = ?",
                    (str(board_indices), now, restart_result, existing[0])
                )
            else:
                conn.execute(
                    "INSERT INTO known_dead_boards (miner_id, ip, model, board_indices, first_seen, restart_attempted, restart_result) VALUES (?,?,?,?,?,?,?)",
                    (miner_id, ip, model, str(board_indices), now, now if restart_result else None, restart_result)
                )
        logger.info("[%s] Registered known dead boards %s — result: %s", miner_id, board_indices, restart_result)

    def resolve_dead_boards(self, miner_id: str):
        """Mark dead boards as resolved (boards recovered after restart or repair)."""
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE known_dead_boards SET resolved_at = ? WHERE miner_id = ? AND resolved_at IS NULL",
                (now, miner_id)
            )

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

    CHANNEL_ID = "C0AQ8SE1448"  # #mining-guardian

    def __init__(self, webhook_url: Optional[str], channel_id: Optional[str] = None,
                 bot_token: Optional[str] = None):
        self.webhook_url = webhook_url
        self.channel_id  = channel_id or self.CHANNEL_ID
        self.bot_token   = bot_token

    def get_user_display_name(self, slack_user_id: str) -> Optional[str]:
        """Look up a Slack user's display name from their user ID.

        Requires a Slack bot token with users:read scope.
        Used to log the real name of whoever approved or denied an action.
        """
        if not self.bot_token:
            logger.warning("No Slack bot token configured — cannot look up user name")
            return None
        try:
            resp = requests.get(
                "https://slack.com/api/users.info",
                headers={"Authorization": f"Bearer {self.bot_token}"},
                params={"user": slack_user_id},
                timeout=5,
            )
            data = resp.json()
            if data.get("ok"):
                profile = data["user"].get("profile", {})
                return profile.get("display_name") or profile.get("real_name")
        except Exception as e:
            logger.warning("Slack user lookup failed: %s", e)
        return None

    def send_scan(self, miners: List[Dict], issues: List[Dict],
                  wx: Optional[Dict] = None,
                  ams_notifs: Optional[List[Dict]] = None,
                  hvac=None) -> None:
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

        # HVAC / warehouse mechanical section
        if hvac is not None:
            sup = f"{hvac.supply_temp_f:.1f}°F" if hvac.supply_temp_f is not None else "N/A"
            ret = f"{hvac.return_temp_f:.1f}°F" if hvac.return_temp_f is not None else "N/A"
            dlt = f"{hvac.delta_t_f:+.1f}°F"   if hvac.delta_t_f     is not None else "N/A"
            dp  = f"{hvac.diff_pressure_psi:.1f} PSI" if hvac.diff_pressure_psi is not None else "N/A"
            pump = "🟢 ON" if hvac.spray_pump_on else "🔴 OFF"
            cwp1 = f"{hvac.cwp1_vfd_pct:.0f}%" if hvac.cwp1_vfd_pct is not None else "?"
            cwp2 = f"{hvac.cwp2_vfd_pct:.0f}%" if hvac.cwp2_vfd_pct is not None else "?"
            ct1  = f"{hvac.ct1_vfd_pct:.0f}%"  if hvac.ct1_vfd_pct  is not None else "?"
            ct2  = f"{hvac.ct2_vfd_pct:.0f}%"  if hvac.ct2_vfd_pct  is not None else "?"

            hvac_lines = [
                f"\n*🏭 Warehouse Mechanical*",
                f"  Supply: *{sup}* | Return: *{ret}* | ΔT: *{dlt}* | Diff Press: *{dp}*",
                f"  Spray Pump: {pump} | CW Pump 1: {cwp1} | CW Pump 2: {cwp2}",
                f"  CT Fan 1: {ct1} | CT Fan 2: {ct2}",
            ]

            # Alarms
            alarms = []
            if hvac.leak_alarm:       alarms.append("🔴 LEAK DETECTED")
            if hvac.tower_vibration:  alarms.append("🔴 TOWER VIBRATION")
            if hvac.ct1_fault:        alarms.append("🔴 CT Fan 1 FAULT")
            if hvac.ct2_fault:        alarms.append("🔴 CT Fan 2 FAULT")
            if hvac.pump_fault:       alarms.append("🔴 Spray Pump FAULT")

            if alarms:
                hvac_lines.append(f"  ⚠️ *ALARMS:* {' | '.join(alarms)}")
            else:
                hvac_lines.append("  ✅ All alarms clear")

            lines.extend(hvac_lines)

        lines.append(status_line)

        if pdu_cycles:
            lines.append(f"\n*🔴 PDU Power Cycle Recommended ({len(pdu_cycles)} miners)*")
            for i in pdu_cycles:
                location = i.get("map_location", "—")
                lines.append(f"  • `{i['ip']}` {i['model']} — {i.get('pdu_action', 'No PDU info')} | Location: {location}")
            lines.append("  _After power cycle: logs collected on boot, elevated monitoring for 3hrs._")

        if fw_restarts:
            # Group by model
            from collections import defaultdict
            by_model: dict = defaultdict(list)
            for i in fw_restarts:
                by_model[i["model"]].append(i)
            lines.append(f"\n*🔴 Firmware Restart Recommended ({len(fw_restarts)} miners)*")
            for model, group in by_model.items():
                if len(group) == 1:
                    i = group[0]
                    lines.append(f"  • `{i['ip']}` {model} — Hashrate: {i['hashrate_pct']} | Temp: {i['temp_chip']}")
                else:
                    # Show all IPs with a shared issue summary
                    ips = ", ".join(f"`{i['ip']}`" for i in group)
                    issue_str = " | ".join(set(" | ".join(i["issues"]) for i in group))
                    lines.append(f"  • *{len(group)}x {model}:* {ips}")
                    lines.append(f"    _{issue_str}_")

        if phys_cycles:
            from collections import defaultdict
            by_model2: dict = defaultdict(list)
            for i in phys_cycles:
                by_model2[i["model"]].append(i)
            lines.append(f"\n*🔴 Physical Power Cycle Required ({len(phys_cycles)} miners)*")
            lines.append("  ⚠️ No PDU assigned — must be done manually at the facility.")
            for model, group in by_model2.items():
                ips = ", ".join(f"`{i['ip']}`" for i in group)
                lines.append(f"  • *{len(group)}x {model}:* {ips}")

        if temp_action:
            lines.append(f"\n*🔴 High Temp — Action Required ({len(temp_action)} miners)*")
            for i in temp_action:
                lines.append(f"  • `{i['ip']}` {i['model']} — {i['temp_chip']}")
            lines.append("  Options: [1] Restart  [2] Lower power  [3] Raise cooling")

        if monitors:
            lines.append(f"\n*🟡 Running Warm — {len(monitors)} miners in yellow zone (76–85°C)*")

        if issues:
            lines.append("\n_Reply *APPROVE* or *DENY* in this thread to execute._")

        # AMS notifications section — exclude miners already flagged in main report
        if ams_notifs:
            from collections import defaultdict
            # Human-readable names for AMS notification keys
            key_labels = {
                "consumptionChangeLevel": "Power consumption change",
                "hotBoard":               "Hashboard overheating",
                "workerOffline":          "Miner went offline",
                "workerOnline":           "Miner came back online",
                "hashrateDropped":        "Hashrate dropped",
                "highTemp":               "High temperature",
                "lowHashrate":            "Low hashrate",
            }
            # IPs already covered in the main report
            flagged_ips = {i["ip"] for i in issues}

            critical = [n for n in ams_notifs
                        if n.get("params", {}).get("alertLevel") == "Critical"
                        and n.get("params", {}).get("minerIp") not in flagged_ips]
            warnings = [n for n in ams_notifs
                        if n.get("params", {}).get("alertLevel") == "Warning"
                        and n.get("params", {}).get("minerIp") not in flagged_ips]

            if critical or warnings:
                lines.append(f"\n*⚠️ Additional AMS Alerts*")
                if critical:
                    by_key: dict = defaultdict(list)
                    for n in critical:
                        by_key[n.get("key", "unknown")].append(n.get("params", {}).get("minerIp", "unknown"))
                    lines.append(f"  🔴 Critical ({len(critical)})")
                    for key, ips in by_key.items():
                        label = key_labels.get(key, key)
                        ip_list = ", ".join(f"`{ip}`" for ip in ips)
                        lines.append(f"    • *{label}:* {ip_list}")
                if warnings:
                    by_key2: dict = defaultdict(list)
                    for n in warnings:
                        by_key2[n.get("key", "unknown")].append(n.get("params", {}).get("minerIp", "unknown"))
                    lines.append(f"  🟡 Warning ({len(warnings)})")
                    for key, ips in by_key2.items():
                        label = key_labels.get(key, key)
                        # Just show count for noisy alerts, IPs for actionable ones
                        if key in ("workerOnline", "workerOffline", "consumptionChangeLevel"):
                            lines.append(f"    • *{label}:* {len(ips)} miners")
                        else:
                            ip_list = ", ".join(f"`{ip}`" for ip in ips)
                            lines.append(f"    • *{label}:* {ip_list}")

        payload = {"text": "\n".join(lines)}

        thread_ts = None
        try:
            # Prefer bot token (returns message ts for threading)
            if self.bot_token:
                from slack_sdk import WebClient
                client = WebClient(token=self.bot_token)
                resp   = client.chat_postMessage(
                    channel=self.channel_id,
                    text="\n".join(lines)
                )
                thread_ts = resp["ts"]
                logger.info("Slack notified — scan posted (ts=%s)", thread_ts)
            else:
                resp = requests.post(self.webhook_url, json=payload, timeout=10)
                if resp.status_code == 200:
                    logger.info("Slack notified — scan summary posted to #mining-guardian")
                else:
                    logger.warning("Slack webhook returned %s: %s",
                                   resp.status_code, resp.text)
        except Exception as exc:
            logger.warning("Slack notification failed: %s", exc)

        return thread_ts


class MiningGuardian:
    HASHRATE_THRESHOLD = 0.90   # flag if below 90% of rated TH/s

    def __init__(self, config: GuardianConfig):
        self.config   = config
        self.ams      = AMSClient(config)
        self.notifier = OpenClawNotifier(config.openclaw_webhook_url)
        self.slack    = SlackNotifier(
            webhook_url=GuardianConfig._resolve(config.slack_webhook_url) if config.slack_webhook_url else None,
            bot_token=GuardianConfig._resolve(config.slack_bot_token) if hasattr(config, "slack_bot_token") and config.slack_bot_token else None
        )
        self.db       = GuardianDB()
        self._last_slack_post = 0  # timestamp of last Slack post
        self._reported_notif_ids = set()  # AMS notification IDs already reported to Slack
        self.weather  = WeatherCollector()

        # ── Three-tier hashrate evaluation ───────────────────────────────
        self.specs    = MinerSpecsLoader("miner_specs.json")
        self.baseline = BaselineManager(
            db_path              = self.db.db_path,
            learning_window_hours= self.specs.learning_window_hours,
            minimum_samples      = self.specs.minimum_samples,
            tolerance_pct        = self.specs.baseline_tolerance_pct,
            notify_callback      = self._on_baseline_locked,
        )
        self.tier_resolver = HashrateTierResolver(self.specs, self.baseline)

        # ── Facility infrastructure monitor ──────────────────────────────
        # Polls PDUs and immersion tank each scan cycle.
        # S19JPros (outside container) have no PDU — not polled here.
        self.facility = FacilityMonitor()
        self.hvac     = HVACClient()

    def _on_baseline_locked(self, miner_id: str, model: str,
                             ip: str, baseline_ths: float, samples: int) -> None:
        """Called when a Tier 3 miner's baseline is locked — post to Slack."""
        msg = (
            f"📊 *Baseline locked for miner {miner_id}* ({model} @ {ip})\n"
            f"Learned hashrate: *{baseline_ths:.1f} TH/s* from {samples} samples over "
            f"{self.specs.learning_window_hours}h. Now actively monitoring."
        )
        logger.info("Baseline locked: %s → %.1f TH/s", miner_id, baseline_ths)
        try:
            if self.slack and hasattr(self.slack, "post_message"):
                self.slack.post_message(msg)
        except Exception as e:
            logger.warning("Failed to post baseline lock notification: %s", e)

    # ── Per-miner analysis ────────────────────────────────────

    @staticmethod
    def _analyze_chains(chains: list) -> dict:
        """
        Analyse per-hashboard chain data from AMS.
        Returns a dict with:
          total_boards      — how many boards reported
          active_boards     — boards with rate > 1000 MH/s (1 TH/s floor)
          dead_boards       — boards with rate == 0 or None
          dead_indices      — list of dead board index numbers
          chain_rates_ths   — list of per-board rates in TH/s
          expected_boards   — estimated expected board count
          pct_capacity      — hashrate as % of full-board capacity
        """
        if not chains:
            return {"total_boards": 0, "active_boards": 0, "dead_boards": 0,
                    "dead_indices": [], "chain_rates_ths": [], "pct_capacity": None,
                    "expected_boards": 0}

        rates_mhs    = [c.get("rate", 0) or 0 for c in chains]
        dead_indices = [chains[i].get("index", i) for i, r in enumerate(rates_mhs) if r < 1000]
        active       = [r for r in rates_mhs if r >= 1000]
        rates_ths    = [round(r / 1000, 1) for r in rates_mhs]

        # Expected board count — standard miners have 3 boards
        expected     = 3
        avg_active   = (sum(active) / len(active)) if active else 0
        pct_capacity = round((len(active) / expected) * 100, 1) if expected > 0 else None

        return {
            "total_boards":    len(chains),
            "active_boards":   len(active),
            "dead_boards":     len(dead_indices),
            "dead_indices":    dead_indices,
            "chain_rates_ths": rates_ths,
            "avg_active_ths":  round(avg_active / 1000, 1),
            "expected_boards": expected,
            "pct_capacity":    pct_capacity,
        }

    def _analyze_miner(self, miner: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Return an issue dict if the miner has a problem, else None.

        Hashrate evaluation uses three tiers:
          Tier 1 — BiXBiT firmware:  parse currentProfile string (live)
          Tier 2 — Known model spec: look up default_rated_ths in miner_specs.json
          Tier 3 — Unknown model:    use 3-day running average baseline
        During Tier 3 learning window, hashrate is NOT flagged — only hard faults.
        """
        miner_id   = str(miner.get("id", "unknown"))
        ip         = miner.get("ip", "unknown")
        name       = miner.get("shortModel", miner.get("name", "unknown"))
        model_code = miner.get("model", "")
        status     = miner.get("status", "unknown")
        hashrate   = miner.get("hashrate", 0) or 0     # MH/s from AMS
        firmware   = miner.get("firmwareManufacturer", "") or ""

        temp_chip_raw = miner.get("tempChip", 0) or 0
        temp_chip     = temp_chip_raw if temp_chip_raw >= 0 else None

        # Power — PDU reading is authoritative, fall back to miner-reported
        pdu_power    = miner.get("pduOutlet", {}).get("power", 0) or 0
        miner_power  = miner.get("consumption", 0) or 0
        power_watts  = pdu_power if pdu_power > 0 else miner_power
        power_source = "PDU" if pdu_power > 0 else "miner"
        power_kw     = round(power_watts / 1000, 3) if power_watts else None

        pdu_id       = miner.get("pduOutlet", {}).get("pduID") or 0
        outlet_index = miner.get("pduOutlet", {}).get("outletIndex") or 0
        has_pdu      = pdu_id > 0 and outlet_index > 0

        issues    = []
        action    = None
        pdu_action = None

        # ── OFFLINE check ────────────────────────────────────────────────
        if status == "offline":
            # AMS can report false-offline after a restart or WebSocket sync lag.
            # Verify directly before taking any action.
            verify = verify_miner_online(ip)
            if verify["actually_online"]:
                logger.info(
                    "[%s] AMS reports offline but miner is reachable — %s. "
                    "Skipping this scan (AMS sync lag).",
                    miner_id, verify["status_detail"]
                )
                # Miner is alive — skip all evaluation this cycle.
                # AMS will catch up on the next scan.
                return None
            else:
                logger.debug(
                    "[%s] AMS offline confirmed by direct check — %s",
                    miner_id, verify["status_detail"]
                )
                issues.append("OFFLINE")
                if has_pdu:
                    action     = "PDU_CYCLE"
                    pdu_action = f"PDU {pdu_id} → Outlet {outlet_index}"
                else:
                    action = "PHYSICAL_CYCLE"

                return self._build_issue(
                    miner, issues, action, pdu_action, power_watts,
                    power_source, power_kw, pdu_id, outlet_index,
                    hashrate_pct="0%", tier="offline",
                    tier_note="Miner offline — confirmed by direct check",
                    chain_info=None,
                )

        # ── HASHBOARD check (always evaluated when online) ───────────────
        chains     = miner.get("chains", []) or []
        chain_info = self._analyze_chains(chains)

        if chain_info["dead_boards"] > 0:
            # Check if this miner already has known dead boards — skip reflagging
            if self.db.has_known_dead_boards(miner_id):
                logger.debug("[%s] Known dead boards — suppressed (ticket already created)", miner_id)
            else:
                dead_idx   = chain_info["dead_indices"]
                dead_count = chain_info["dead_boards"]
                issues.append(
                    f"🔴 DEAD HASHBOARD{'S' if dead_count > 1 else ''}: "
                    f"Board{'s' if dead_count > 1 else ''} {dead_idx} offline "
                    f"({chain_info['active_boards']}/{chain_info['expected_boards']} boards active, "
                    f"~{chain_info['pct_capacity']:.0f}% capacity)"
                )
                # Restart is the first-line fix — logs collected before and after
                action = "RESTART_CHECK_BOARDS"

        # ── Record baseline sample for Tier 3 learning ───────────────────
        # AMS hashrate field is in GH/s — divide by 1000 to get TH/s
        hashrate_ths = hashrate / 1_000 if hashrate > 0 else 0
        just_locked  = self.baseline.record_sample(
            miner_id, hashrate_ths, power_kw
        )
        if just_locked:
            logger.info("Baseline just locked for miner %s during this scan", miner_id)

        # ── Resolve rated TH/s (the three-tier lookup) ───────────────────
        rated_ths, tier, tier_note = self.tier_resolver.resolve(miner)

        # ── HASHRATE check ───────────────────────────────────────────────
        hashrate_pct_str = "N/A"
        if tier == "3_learning" or rated_ths is None:
            # In learning window — skip hashrate evaluation
            pass
        elif rated_ths > 0:
            pct = (hashrate_ths / rated_ths) * 100
            hashrate_pct_str = f"{pct:.1f}%"
            if pct < self.HASHRATE_THRESHOLD * 100:
                issues.append(
                    f"Hashrate {pct:.1f}% of rated "
                    f"({hashrate_ths:.1f} / {rated_ths:.0f} TH/s) "
                    f"[{tier}]"
                )
                # Only set RESTART if a dead board hasn't already claimed the action
                # Dead board takes priority — its flow includes a restart anyway
                if action != "RESTART_CHECK_BOARDS":
                    action = "RESTART"

        # ── TEMP check ───────────────────────────────────────────────────
        # Same thresholds regardless of cooling type.
        # Immersion miners are overclocked and run hotter than stock —
        # the same 76/86 limits apply across air, immersion, and hydro.
        if temp_chip is None:
            issues.append("⚠️ Sensor error — temp reading invalid")
        elif temp_chip >= 86:
            issues.append(f"🔴 RED — chip {temp_chip}°C (86°C+ threshold)")
            action = "TEMP_ACTION_REQUIRED"
        elif temp_chip >= 76:
            issues.append(f"🟡 YELLOW — chip {temp_chip}°C (76–85°C range)")
            if not action:
                action = "MONITOR"

        # ── Learning window advisory (non-blocking) ──────────────────────
        if tier == "3_learning":
            # Don't add as an "issue" — just annotate in the return dict
            pass

        if not issues:
            return None

        return self._build_issue(
            miner, issues, action, pdu_action, power_watts,
            power_source, power_kw, pdu_id, outlet_index,
            hashrate_pct=hashrate_pct_str, tier=tier,
            tier_note=tier_note,
            chain_info=chain_info,
        )

    def _build_issue(self, miner: Dict[str, Any], issues: list,
                     action: Optional[str], pdu_action: Optional[str],
                     power_watts: float, power_source: str,
                     power_kw: Optional[float], pdu_id: int, outlet_index: int,
                     hashrate_pct: str = "N/A", tier: str = "unknown",
                     tier_note: str = "",
                     chain_info: Optional[dict] = None) -> Dict[str, Any]:
        """Build the standardised issue dict returned by _analyze_miner."""
        temp_chip  = miner.get("tempChip", None)
        model_code = miner.get("model", "")
        profile    = miner.get("currentProfile", "") or ""

        # Use name (e.g. "Antminer S19JPro") as display model when AMS model
        # code is misregistered but name/profile reveal the real hardware.
        # A parseable BiXBiT profile string is the most reliable identity signal.
        short_model = miner.get("shortModel", miner.get("name", "unknown"))
        full_name   = miner.get("name", "")
        if parse_bixbit_profile(profile) and full_name:
            # Profile confirms BiXBiT firmware — trust name over shortModel
            display_model = full_name
        else:
            display_model = short_model

        return {
            "id":           str(miner.get("id", "unknown")),
            "ip":           miner.get("ip", "unknown"),
            "model":        display_model,
            "model_code":   model_code,
            "firmware":     miner.get("firmwareManufacturer", "") or "",
            "status":       miner.get("status", "unknown"),
            "hashrate_pct": hashrate_pct,
            "tier":         tier,
            "tier_note":    tier_note,
            "temp_chip":    f"{temp_chip}°C" if temp_chip is not None else "sensor error",
            "issues":       issues,
            "action":       action,
            "pdu_id":       pdu_id,
            "outlet":       outlet_index,
            "pdu_action":   pdu_action,
            "power_watts":  power_watts,
            "power_source": power_source,
            "pdu_power_kw": power_kw,
            "map_location": miner.get("mapLocation", {}).get("title") or "not mapped",
            "active_profile": miner.get("currentProfile", "") or "N/A",
            "chain_info":   chain_info,
        }

    # ── Hashboard restart + verification flow ─────────────────

    # Phase 1: wait for status == online
    PHASE1_MAX_WAIT    = 600    # 10 minutes max for miner to come back online
    # Phase 2: wait for hashrate stable + minerStatus == 0
    PHASE2_MAX_WAIT    = 2700   # 45 minutes max for full stability
    REBOOT_POLL_FAST   = 15     # poll interval during phase 1 (seconds)
    REBOOT_POLL_SLOW   = 30     # poll interval during phase 2 (seconds)
    STABLE_CONFIRM     = 2      # consecutive stable polls required before collecting logs
    LOG_COLLECT_TIMEOUT = 30    # seconds to attempt log collection before giving up
    BOARD_DEAD_THRESHOLD = 1000  # MH/s — below this a board is considered dead

    def _get_common_status_direct(self, ip: str, timeout: float = 5.0) -> Optional[str]:
        """Query common_status directly from the device via TCP port 4029.

        This is the authoritative post-restart state signal from BiXBiT firmware.
        AMS is always the primary command path — this is used only during the
        post-restart stability wait where device-level status is more reliable
        than AMS polling lag.

        Returns the common_status string (e.g. "mining", "auto-tuning",
        "starting") or None if the device is unreachable or the response
        cannot be parsed.
        """
        import socket, base64, json as _json
        try:
            cmd = _json.dumps({"command": "common_status"})
            payload = _json.dumps({"enc": False, "data": base64.b64encode(cmd.encode()).decode()}) + "\n"
            with socket.create_connection((ip, 4029), timeout=timeout) as sock:
                sock.sendall(payload.encode())
                chunks = []
                sock.settimeout(timeout)
                while True:
                    try:
                        chunk = sock.recv(4096)
                        if not chunk:
                            break
                        chunks.append(chunk)
                    except socket.timeout:
                        break
                raw = b"".join(chunks).decode(errors="replace").strip()
                resp = _json.loads(raw)
                status_val = resp.get("COMMON_STATUS", [{}])[0].get("common_status")
                return status_val
        except Exception:
            return None

    def _collect_logs_nonblocking(self, miner_id: str, model: str,
                                   label: str) -> dict:
        """
        Attempt log collection with a hard timeout.
        Returns log dict (possibly empty) — never raises, never hangs.
        If miner is offline or logs unavailable, returns {} immediately.
        """
        import signal

        def _timeout_handler(signum, frame):
            raise TimeoutError("log collection timed out")

        try:
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(self.LOG_COLLECT_TIMEOUT)
            logs = self.ams.collect_miner_logs(int(miner_id))
            signal.alarm(0)  # cancel alarm
            if logs:
                self.db.save_logs(miner_id, model, label, logs)
                logger.info("[%s] Logs collected (%s): %s files", miner_id, label, len(logs))
            else:
                logger.info("[%s] No logs available for %s — skipping", miner_id, label)
            return logs or {}
        except TimeoutError:
            signal.alarm(0)
            logger.warning("[%s] Log collection timed out after %ss (%s) — continuing",
                           miner_id, self.LOG_COLLECT_TIMEOUT, label)
            return {}
        except Exception as e:
            signal.alarm(0)
            logger.warning("[%s] Log collection failed (%s): %s — continuing", miner_id, label, e)
            return {}

    def _wait_for_stable(self, miner_id: str) -> Optional[Dict]:
        """
        Two-phase wait after a restart.

        Phase 1 — wait for status == 'online' (up to PHASE1_MAX_WAIT seconds).
        Phase 2 — wait for full stability: hashrate > 0 AND minerStatus == 0
                  on STABLE_CONFIRM consecutive polls (up to PHASE2_MAX_WAIT seconds).

        Returns the stable miner dict, or None if timed out.
        """
        # ── Phase 1: wait for online ──────────────────────────────────────
        waited  = 0
        current = None
        logger.info("[%s] Phase 1 — waiting for status=online (max %ss)",
                    miner_id, self.PHASE1_MAX_WAIT)

        while waited < self.PHASE1_MAX_WAIT:
            time.sleep(self.REBOOT_POLL_FAST)
            waited += self.REBOOT_POLL_FAST
            try:
                all_miners = self.ams.get_miners()
                current    = next(
                    (m for m in all_miners if str(m.get("id")) == str(miner_id)),
                    None
                )
                if current and current.get("status") == "online":
                    logger.info("[%s] Phase 1 complete — online after %ss", miner_id, waited)
                    break
                logger.debug("[%s] Phase 1: still offline at %ss", miner_id, waited)
            except Exception as e:
                logger.warning("[%s] Phase 1 poll error at %ss: %s", miner_id, waited, e)
        else:
            logger.warning("[%s] Phase 1 timed out — miner did not come online in %ss",
                           miner_id, self.PHASE1_MAX_WAIT)
            return None

        # ── Phase 2: wait for stable mining state ────────────────────────
        # Primary signal: common_status == "mining" via TCP port 4029
        #   This is the authoritative device state from BiXBiT firmware.
        #   States like "starting", "auto-tuning", "initializing" mean not ready.
        #   "emergency" means escalate immediately.
        # Fallback signal: AMS minerStatus == 0 AND hashrate > 0
        #   Used when direct TCP is not available (e.g. different network segment).
        # We require STABLE_CONFIRM consecutive passing polls either way.
        stable_count = 0
        waited2      = 0
        logger.info("[%s] Phase 2 — waiting for stable mining state (max %ss, need %s consecutive)",
                    miner_id, self.PHASE2_MAX_WAIT, self.STABLE_CONFIRM)

        while waited2 < self.PHASE2_MAX_WAIT:
            time.sleep(self.REBOOT_POLL_SLOW)
            waited2 += self.REBOOT_POLL_SLOW
            try:
                # --- Primary: direct common_status via TCP 4029 ---
                device_status = None
                try:
                    device_status = self._get_common_status_direct(ip)
                except Exception:
                    pass  # fallback to AMS below

                if device_status == "emergency":
                    logger.error(
                        "[%s] Phase 2: device entered EMERGENCY mode at %ss — escalating",
                        miner_id, waited2
                    )
                    break  # exit loop, board comparison will escalate to ticket

                if device_status is not None:
                    # We have a direct device answer — trust it over AMS
                    is_stable = (device_status == "mining")
                    status_source = f"direct({device_status})"
                else:
                    # --- Fallback: AMS minerStatus + hashrate ---
                    all_miners = self.ams.get_miners()
                    current    = next(
                        (m for m in all_miners if str(m.get("id")) == str(miner_id)),
                        None
                    )
                    if not current:
                        stable_count = 0
                        continue
                    hashrate     = current.get("hashrate", 0) or 0
                    miner_status = current.get("minerStatus", -1)
                    is_stable    = (hashrate > 0 and miner_status == 0)
                    status_source = f"ams(hr={hashrate:.0f} ms={miner_status})"

                if is_stable:
                    stable_count += 1
                    logger.info(
                        "[%s] Phase 2: stable poll %s/%s — %s",
                        miner_id, stable_count, self.STABLE_CONFIRM, status_source
                    )
                    if stable_count >= self.STABLE_CONFIRM:
                        total = waited + waited2
                        logger.info(
                            "[%s] Phase 2 complete — stable after %ss total (%ss + %ss)",
                            miner_id, total, waited, waited2
                        )
                        # Refresh AMS data one final time before returning
                        try:
                            all_miners = self.ams.get_miners()
                            current = next(
                                (m for m in all_miners if str(m.get("id")) == str(miner_id)),
                                current
                            )
                        except Exception:
                            pass
                        return current
                else:
                    if stable_count > 0:
                        logger.debug(
                            "[%s] Phase 2: stability reset at %ss — %s",
                            miner_id, waited2, status_source
                        )
                    stable_count = 0
            except Exception as e:
                logger.warning("[%s] Phase 2 poll error at %ss: %s", miner_id, waited2, e)
                stable_count = 0

        logger.warning(
            "[%s] Phase 2 timed out — miner online but did not stabilise in %ss",
            miner_id, self.PHASE2_MAX_WAIT
        )
        return current  # return what we have — better than nothing

    def execute_board_restart(self, issue: Dict[str, Any]) -> None:
        """
        Full dead-hashboard remediation sequence:

          1. Attempt pre-restart log collection (non-blocking, 30s timeout)
             — if miner is offline or logs unavailable, skip and continue
          2. Restart miner via AMS
          3. Phase 1 wait: poll for status=online (up to 10 min)
          4. Phase 2 wait: poll for stable hashrate + minerStatus=0 (up to 45 min)
          5. Collect post-restart logs (non-blocking)
          6. Compare board states before vs after
          7a. All boards recovered → log success + Slack
          7b. Partial recovery → Slack + escalate remaining dead boards
          7c. Still dead → AMS ticket + Slack escalation

        Called after operator approves RESTART_CHECK_BOARDS action.
        """
        miner_id   = issue["id"]
        ip         = issue["ip"]
        model      = issue["model"]
        chain_info = issue.get("chain_info") or {}
        dead_before = chain_info.get("dead_boards", 0)
        dead_idx    = chain_info.get("dead_indices", [])

        logger.info(
            "Board restart flow — miner %s (%s @ %s) dead boards: %s",
            miner_id, model, ip, dead_idx
        )

        # ── Step 1: Pre-restart logs (best-effort, never blocks) ─────────
        logger.info("[%s] Step 1 — pre-restart log collection (best-effort)", miner_id)
        self._collect_logs_nonblocking(miner_id, model, "pre-restart-board-check")

        # ── Step 2: Restart via AMS ───────────────────────────────────────
        logger.info("[%s] Step 2 — sending restart via AMS", miner_id)
        try:
            self.ams.reboot_miner([miner_id])
            self.db.record_restart(
                miner_id, ip, model,
                f"Dead board restart — boards {dead_idx} offline before restart"
            )
            logger.info("[%s] Restart command sent", miner_id)
        except Exception as e:
            logger.error("[%s] Restart command failed: %s", miner_id, e)
            self.db.log_action(
                miner_id, ip, model,
                problem=f"Dead boards {dead_idx}",
                action_taken="RESTART_CHECK_BOARDS",
                decision="ERROR",
                notes=f"Restart command failed: {e}"
            )
            return

        # ── Steps 3+4: Wait for stable (two-phase) ───────────────────────
        logger.info("[%s] Step 3+4 — waiting for stable operation", miner_id)
        post_miner = self._wait_for_stable(miner_id)

        if post_miner is None:
            self._escalate_board_issue(
                miner_id, ip, model, dead_idx,
                reason="Miner did not come back online within 10 minutes after restart"
            )
            return

        # ── Step 5: Post-restart logs (best-effort) ───────────────────────
        logger.info("[%s] Step 5 — post-restart log collection (best-effort)", miner_id)
        self._collect_logs_nonblocking(miner_id, model, "post-restart-board-check")

        # ── Step 6: Compare board states ─────────────────────────────────
        logger.info("[%s] Step 6 — comparing board states", miner_id)
        post_chains    = post_miner.get("chains", []) or []
        post_info      = self._analyze_chains(post_chains)
        still_dead     = post_info.get("dead_boards", 0)
        still_dead_idx = post_info.get("dead_indices", [])
        recovered_idx  = [i for i in dead_idx if i not in still_dead_idx]

        logger.info(
            "[%s] Board comparison — before: %s dead %s | after: %s dead %s | recovered: %s",
            miner_id, dead_before, dead_idx, still_dead, still_dead_idx, recovered_idx
        )

        # ── Step 7: Outcome ───────────────────────────────────────────────
        if still_dead == 0:
            # Full recovery
            msg = (
                f"✅ *Board restart successful* — Miner {miner_id} ({model} @ {ip})\n"
                f"Dead board(s) {dead_idx} recovered after restart.\n"
                f"All {post_info.get('active_boards')}/{post_info.get('expected_boards')} "
                f"boards now active."
            )
            logger.info("[%s] All boards recovered", miner_id)
            self.db.log_action(
                miner_id, ip, model,
                problem=f"Dead boards {dead_idx}",
                action_taken="RESTART_CHECK_BOARDS",
                decision="RESOLVED",
                notes=f"All boards recovered. Pre/post logs saved. Recovered: {recovered_idx}"
            )
            try:
                self.slack.post_to_channel(msg)
            except Exception as e:
                logger.warning("[%s] Slack notification failed: %s", miner_id, e)

        elif still_dead < dead_before:
            # Partial recovery
            msg = (
                f"⚠️ *Partial board recovery* — Miner {miner_id} ({model} @ {ip})\n"
                f"Boards {recovered_idx} recovered. Boards {still_dead_idx} still dead.\n"
                f"Escalating to ticket for physical inspection."
            )
            logger.info("[%s] Partial recovery — escalating boards %s", miner_id, still_dead_idx)
            self.db.log_action(
                miner_id, ip, model,
                problem=f"Dead boards {dead_idx}",
                action_taken="RESTART_CHECK_BOARDS",
                decision="PARTIAL",
                notes=f"Partial recovery. Recovered: {recovered_idx}. Still dead: {still_dead_idx}"
            )
            try:
                self.slack.post_to_channel(msg)
            except Exception as e:
                logger.warning("[%s] Slack notification failed: %s", miner_id, e)
            self._escalate_board_issue(
                miner_id, ip, model, still_dead_idx,
                reason=f"Partial recovery — boards {still_dead_idx} still dead after restart"
            )

        else:
            # No recovery
            self._escalate_board_issue(
                miner_id, ip, model, still_dead_idx,
                reason=f"Board(s) {still_dead_idx} still dead after restart"
            )

    def _escalate_board_issue(self, miner_id: str, ip: str, model: str,
                               dead_idx: list, reason: str) -> None:
        """
        Escalate a persistent dead hashboard to AMS ticket + Slack alert.
        Called when restart did not resolve the board issue.
        """
        title = (
            f"Dead hashboard — {model} @ {ip} "
            f"(Miner {miner_id}, board(s) {dead_idx})"
        )
        description = (
            f"Miner: {miner_id} ({model})\n"
            f"IP: {ip}\n"
            f"Dead board(s): {dead_idx}\n"
            f"Reason: {reason}\n"
            f"Action taken: Restart attempted — board(s) did not recover.\n"
            f"Pre and post-restart logs have been collected and saved to guardian.db.\n"
            f"Physical inspection and board replacement required."
        )

        # Create AMS ticket
        try:
            ticket = self.ams.create_ticket(
                title=title,
                description=description,
                priority="high"
            )
            ticket_id = ticket.get("id", "unknown")
            logger.info("[%s] AMS ticket created: %s", miner_id, ticket_id)
        except Exception as e:
            ticket_id = "failed"
            logger.error("[%s] AMS ticket creation failed: %s", miner_id, e)

        # Log to audit
        self.db.log_action(
            miner_id, ip, model,
            problem=f"Dead boards {dead_idx}",
            action_taken="RESTART_CHECK_BOARDS",
            decision="ESCALATED",
            notes=f"{reason}. AMS ticket #{ticket_id} created. Physical inspection required."
        )

        # Enable elevated monitoring so next scans watch it closely
        self.db.record_restart(miner_id, ip, model, reason)

        # Slack alert
        slack_msg = (
            f"🔴 *Dead hashboard — physical inspection required*\n"
            f"*Miner:* {miner_id} | {model} @ {ip}\n"
            f"*Dead board(s):* {dead_idx}\n"
            f"*Reason:* {reason}\n"
            f"*AMS Ticket:* #{ticket_id}\n"
            f"*Action:* Pre and post-restart logs saved. Board did not recover after restart.\n"
            f"Physical inspection and board replacement needed."
        )
        try:
            self.slack.post_to_channel(slack_msg)
        except Exception as e:
            logger.warning("[%s] Slack escalation alert failed: %s", miner_id, e)

        logger.info(
            "[%s] Escalated — dead boards %s, ticket #%s, Slack notified",
            miner_id, dead_idx, ticket_id
        )

    # ── Execute approved actions ──────────────────────────────

    def execute_restart(self, issue: Dict[str, Any]) -> None:
        """
        Execute an approved firmware restart with pre-restart log collection.

        Flow:
          1. Attempt pre-restart log collection (non-blocking, 30s timeout)
          2. Restart miner via AMS
          3. Log the action to audit log

        Called when operator approves a RESTART action.
        """
        miner_id = issue["id"]
        ip       = issue["ip"]
        model    = issue["model"]

        logger.info("[%s] Executing approved firmware restart for %s @ %s", miner_id, model, ip)

        # Step 1 — collect pre-restart logs (skip silently if offline/unavailable)
        self._collect_logs_nonblocking(miner_id, model, "pre-restart")

        # Step 2 — restart via AMS
        try:
            self.ams.reboot_miner([miner_id])
            logger.info("[%s] Firmware restart sent via AMS", miner_id)
        except Exception as e:
            logger.error("[%s] Firmware restart failed: %s", miner_id, e)

    def execute_pdu_cycle(self, issue: Dict[str, Any]) -> None:
        """
        Execute an approved PDU power cycle with pre-restart log collection.

        Flow:
          1. Attempt pre-restart log collection (non-blocking, 30s timeout)
          2. Turn PDU outlet OFF via AMS
          3. Wait 10 seconds
          4. Turn PDU outlet ON via AMS
          5. Log the action to audit log

        Called when operator approves a PDU_CYCLE action.
        """
        miner_id  = issue["id"]
        ip        = issue["ip"]
        model     = issue["model"]
        pdu_id    = issue.get("pdu_id")
        outlet    = issue.get("outlet")

        if not pdu_id or not outlet:
            logger.error("[%s] PDU cycle approved but no PDU/outlet info — skipping", miner_id)
            return

        logger.info("[%s] Executing approved PDU power cycle — PDU %s outlet %s",
                    miner_id, pdu_id, outlet)

        # Step 1 — collect pre-restart logs (skip silently if offline/unavailable)
        self._collect_logs_nonblocking(miner_id, model, "pre-pdu-cycle")

        # Step 2 — power cycle via AMS
        import time
        try:
            self.ams.pdu_cycle(pdu_id, outlet)
            logger.info("[%s] PDU %s outlet %s — power cycled", miner_id, pdu_id, outlet)
        except Exception as e:
            logger.error("[%s] PDU cycle failed: %s", miner_id, e)

    # ── Report printer ────────────────────────────────────────

    @staticmethod
    def _print_report(miners: List[Dict], issues: List[Dict],
                      wx: Optional[Dict] = None,
                      ams_notifs: Optional[List[Dict]] = None,
                      facility=None,
                      hvac=None) -> None:
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

        # HVAC / warehouse mechanical section
        if hvac is not None:
            print(format_hvac_report(hvac))
            print(divider)

        if not issues:
            print("  ✅ All miners operating within normal parameters.")
        else:
            # Group by action
            pdu_cycles    = [i for i in issues if i["action"] == "PDU_CYCLE"]
            fw_restarts   = [i for i in issues if i["action"] == "RESTART"]
            board_restarts = [i for i in issues if i["action"] == "RESTART_CHECK_BOARDS"]
            phys_cycles   = [i for i in issues if i["action"] == "PHYSICAL_CYCLE"]
            monitors      = [i for i in issues if i["action"] == "MONITOR"]
            restarts      = pdu_cycles + fw_restarts + phys_cycles + board_restarts

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

                if board_restarts:
                    print(f"\n  🔴 DEAD HASHBOARD — RESTART + LOG COMPARISON REQUIRED ({len(board_restarts)} miners)\n")
                    print(f"  {'ID':<8} {'IP':<18} {'Model':<14} {'Dead Boards':<14} {'Active':<10} {'Hashrate':<10} Location")
                    print(f"  {'-'*8} {'-'*18} {'-'*14} {'-'*14} {'-'*10} {'-'*10} {'-'*20}")
                    for i in board_restarts:
                        ci = i.get("chain_info") or {}
                        dead_str   = str(ci.get("dead_indices", []))
                        active_str = f"{ci.get('active_boards',0)}/{ci.get('expected_boards',3)}"
                        print(f"  {i['id']:<8} {i['ip']:<18} {i['model']:<14} {dead_str:<14} {active_str:<10} {i['hashrate_pct']:<10} {i.get('map_location','not mapped')}")
                    print(f"\n  Flow: collect logs → restart → wait → collect logs → compare → ticket if still dead")

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

        # ── Facility infrastructure section ──────────────────────────────
        if facility is not None:
            try:
                from facility_monitor import format_facility_report
                print(format_facility_report(facility))
            except Exception as e:
                logger.warning("Facility report section failed: %s", e)

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
        """Download logs once per day for ALL miners (good or bad) for LLM learning."""
        if not self.config.collect_logs:
            logger.debug("Log collection disabled — set collect_logs: true in config to enable")
            return

        now = datetime.now()
        collected = 0
        daily_seconds = 86400  # 24 hours

        for miner in miners:
            miner_id  = str(miner.get("id", ""))
            model     = miner.get("shortModel", miner.get("name", "unknown"))
            profile_s = miner.get("currentProfile", "")
            if "TH/s" in profile_s and miner.get("name") and miner.get("name") != model:
                model = miner["name"]
            status    = miner.get("status", "unknown")

            # Skip offline miners — no connection means no logs available
            if status == "offline":
                continue

            # Once per day for ALL miners — no duplicates
            last = self.db.last_log_collected(miner_id)
            if last is not None and (now - last).total_seconds() < daily_seconds:
                continue  # Already collected today

            flagged = miner_id in {i["id"] for i in issues}
            health_status = "flagged" if flagged else "healthy"

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
        # ── Poll facility infrastructure first ───────────────────────────
        facility_snapshot = self.facility.poll()

        # Fetch weather and AMS notifications
        wx = self.weather.fetch()
        if wx:
            self.db.save_weather(wx)

        hvac_snapshot = self.hvac.poll()
        if hvac_snapshot:
            self.db.save_hvac(hvac_snapshot)

        ams_notifs = self.ams.get_notifications("miner")
        if ams_notifs:
            self.db.save_notifications(ams_notifs)
            logger.info("Pulled %s AMS notifications", len(ams_notifs))

        # Filter out already-reported notifications for Slack
        new_notifs = []
        if ams_notifs:
            for n in ams_notifs:
                nid = n.get("id")
                if nid and nid not in self._reported_notif_ids:
                    new_notifs.append(n)
                    self._reported_notif_ids.add(nid)
            if len(new_notifs) < len(ams_notifs):
                logger.info("AMS notifications: %d new, %d already reported",
                            len(new_notifs), len(ams_notifs) - len(new_notifs))

        miners   = self.ams.get_miners(self.config.miner_filters)
        issues   = [r for r in (self._analyze_miner(m) for m in miners) if r]
        self._print_report(miners, issues, wx, ams_notifs, facility_snapshot, hvac_snapshot)
        scan_id   = self.db.save_scan(miners, issues)
        self.db.purge_old_logs(days=7)
        self.collect_logs(miners, issues)
        self.notifier.send_scan(miners, issues)

        # Slack throttle — only post at most once per slack_interval_seconds
        import time as _time
        now_ts = _time.time()
        if now_ts - self._last_slack_post >= self.config.slack_interval_seconds:
            thread_ts = self.slack.send_scan(miners, issues, wx, new_notifs, hvac_snapshot)
            self._last_slack_post = now_ts
            if thread_ts and issues:
                self.db.save_pending_approvals(thread_ts, scan_id, issues)
        else:
            logger.info("Slack throttled — next post in %ds",
                        int(self.config.slack_interval_seconds - (now_ts - self._last_slack_post)))

        # LLM analysis — feed scan data to local Ollama model
        if issues:
            try:
                from llm_analyzer import LLMAnalyzer
                analyzer = LLMAnalyzer()
                wx_data = {"temp_f": wx.get("temp_f"), "humidity_pct": wx.get("humidity_pct")} if wx else None
                hvac_data = None
                if hvac_snapshot:
                    hvac_data = {"supply_temp_f": hvac_snapshot.supply_temp_f,
                                 "return_temp_f": hvac_snapshot.return_temp_f,
                                 "delta_t_f": hvac_snapshot.delta_t_f}
                analysis = analyzer.analyze_issues(scan_id, issues, wx_data, hvac_data)
                if analysis:
                    logger.info("LLM analysis: %s", analysis[:200])
                    # Save LLM insight to persistent knowledge
                    try:
                        from knowledge_manager import KnowledgeManager
                        km = KnowledgeManager()
                        km.add_llm_insight(analysis)
                    except Exception:
                        pass
            except Exception as e:
                logger.warning("LLM analysis skipped: %s", e)

        # Update persistent knowledge with scan results
        try:
            from knowledge_manager import KnowledgeManager
            km = KnowledgeManager()
            km.update_from_scan(miners, issues, wx, hvac_snapshot)
        except Exception as e:
            logger.warning("Knowledge update skipped: %s", e)

        return {
            "scanned": len(miners),
            "issues":  len(issues),
            "pdu_cycle":         [i["id"] for i in issues if i["action"] == "PDU_CYCLE"],
            "firmware_restart":  [i["id"] for i in issues if i["action"] == "RESTART"],
            "board_restart":     [i["id"] for i in issues if i["action"] == "RESTART_CHECK_BOARDS"],
            "physical_cycle":    [i["id"] for i in issues if i["action"] == "PHYSICAL_CYCLE"],
            "monitor":           [i["id"] for i in issues if i["action"] == "MONITOR"],
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
    "openclaw_webhook_url": "http://127.0.0.1:18789/hooks",
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
