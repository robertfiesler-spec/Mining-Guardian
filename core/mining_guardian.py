import os
import sys
import json
import time
import sqlite3
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Path setup — works whether run from repo root or core/ directory ──────────
_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT), str(_ROOT / "core"), str(_ROOT / "clients"), str(_ROOT / "monitoring")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

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

        Bug fix (Apr 8 2026): long-running processes (overnight-automation,
        alert-listener) were getting HTTP 400 from select_workspace when the
        token expired. Root cause: stale session cookies were colliding with
        the new Bearer header during re-auth. Fix: clear the cookie jar before
        every re-auth, and on failure, reset _ws_token so the next call retries
        from scratch instead of returning the stale cached value.
        """
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
        # Yellow zone miners omitted from summary — stored in DB for learning only
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
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=30000')
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
                    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                    restarted_at          TEXT    NOT NULL,
                    miner_id              TEXT    NOT NULL,
                    ip                    TEXT,
                    model                 TEXT,
                    restart_type          TEXT,
                    elevated_until        TEXT,
                    -- Outcome feedback columns (Feature 1)
                    outcome               TEXT,    -- SUCCESS / FAILURE / PARTIAL / PENDING
                    outcome_checked_at    TEXT,    -- when outcome was evaluated
                    hashrate_before       REAL,    -- hashrate_pct at time of restart
                    hashrate_after        REAL,    -- hashrate_pct 2-3 scans after restart
                    recovery_time_scans   INTEGER  -- how many scans until recovery
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
                    ticket_noticed_at TEXT,
                    resolved_at     TEXT,
                    notes           TEXT
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_dead_boards_miner
                    ON known_dead_boards(miner_id)
                    WHERE resolved_at IS NULL;

                -- ── Per-board chain readings (one row per board per miner per scan) ──
                -- Captures every field AMS exposes at the board level:
                -- HW errors, voltage, frequency, per-board consumption, per-board temps
                CREATE TABLE IF NOT EXISTS chain_readings (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id         INTEGER NOT NULL REFERENCES scans(id),
                    scanned_at      TEXT    NOT NULL,
                    miner_id        TEXT    NOT NULL,
                    ip              TEXT,
                    board_index     INTEGER NOT NULL,
                    rate_mhs        REAL,
                    voltage         REAL,
                    freq_mhz        REAL,
                    consumption_w   REAL,
                    hw_errors       INTEGER,
                    temp_board      REAL,
                    temp_chip       REAL
                );

                CREATE INDEX IF NOT EXISTS idx_chain_miner
                    ON chain_readings(miner_id, scanned_at);

                -- ── Per-pool readings (one row per pool per miner per scan) ──
                -- Captures accepted/rejected shares, difficulty, pool status
                -- This is the data that drives profitability and pool health analysis
                CREATE TABLE IF NOT EXISTS pool_readings (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id         INTEGER NOT NULL REFERENCES scans(id),
                    scanned_at      TEXT    NOT NULL,
                    miner_id        TEXT    NOT NULL,
                    ip              TEXT,
                    pool_priority   INTEGER,
                    pool_url        TEXT,
                    pool_user       TEXT,
                    pool_type       TEXT,
                    status          TEXT,
                    accepted        INTEGER,
                    rejected        INTEGER,
                    accepted_diff   REAL,
                    rejected_diff   REAL,                    difficulty      TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_pool_miner
                    ON pool_readings(miner_id, scanned_at);

                -- ── Per-chip readings stub (for future direct miner API integration) ──
                -- chips_ws from AMS returns all zeros for hydro/immersion (no per-chip sensors)
                -- Future: populated via direct miner API (port 4028/4029 on BiXBiT firmware)
                -- Structure ready — data collection requires direct device access
                CREATE TABLE IF NOT EXISTS chip_readings (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id         INTEGER NOT NULL REFERENCES scans(id),
                    scanned_at      TEXT    NOT NULL,
                    miner_id        TEXT    NOT NULL,
                    ip              TEXT,
                    board_index     INTEGER NOT NULL,
                    chip_index      INTEGER NOT NULL,
                    freq_mhz        REAL,
                    voltage_mv      REAL,
                    temp_c          REAL,
                    source          TEXT    DEFAULT 'direct_api'
                );

                CREATE INDEX IF NOT EXISTS idx_chip_miner
                    ON chip_readings(miner_id, scanned_at);

                -- ── Extended miner state per scan ──
                -- Fields available in AMS miner list that we weren't storing
                CREATE TABLE IF NOT EXISTS miner_state_readings (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id         INTEGER NOT NULL REFERENCES scans(id),
                    scanned_at      TEXT    NOT NULL,
                    miner_id        TEXT    NOT NULL,
                    ip              TEXT,
                    hashrate_medium REAL,
                    hashrate_low    REAL,
                    max_hashrate    REAL,
                    max_consumption REAL,
                    max_temp_board  REAL,
                    max_temp_chip   REAL,
                    temp_chip_low   REAL,
                    temp_chip_medium REAL,
                    miner_status    INTEGER,
                    cooling_mode    INTEGER,
                    worker_version  TEXT,
                    active_pool_user TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_state_miner
                    ON miner_state_readings(miner_id, scanned_at);

                -- ── Miner hardware identity table ──────────────────────────────────
                -- Populated by parsing CGMiner/BixMiner logs at boot or log collection time.
                -- One row per board per miner — updated when new data is found.
                -- This is the permanent hardware identity record for the fleet.
                -- Fields sourced from miner.log EEPROM lines:
                --   board_name, serial_number, chip_die, chip_marking, chip_technology
                --   pcb_version, bom_version, chip_bin, chip_ft_ver
                -- Fields sourced from miner.log device detection:
                --   control_board, psu_version, bixminer_version, topol_machine
                --   device_name, asic_count, bad_chips_count
                -- This data never changes unless a board is physically replaced.
                -- When repair shop data arrives, cross-reference by board serial number.
                CREATE TABLE IF NOT EXISTS miner_hardware (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    miner_id            TEXT    NOT NULL,
                    ip                  TEXT,
                    mac                 TEXT,
                    board_index         INTEGER NOT NULL,
                    board_name          TEXT,
                    serial_number       TEXT,
                    chip_die            TEXT,
                    chip_marking        TEXT,
                    chip_technology     TEXT,
                    pcb_version         TEXT,
                    bom_version         TEXT,
                    chip_bin            TEXT,
                    chip_ft_ver         TEXT,
                    ideal_hashrate      INTEGER,
                    control_board       TEXT,
                    psu_version         TEXT,
                    bixminer_version    TEXT,
                    topol_machine       TEXT,
                    device_name         TEXT,
                    asic_count          INTEGER,
                    bad_chips_count     INTEGER,
                    pic_version         TEXT,
                    first_seen          TEXT    NOT NULL,
                    last_updated        TEXT    NOT NULL,
                    log_source          TEXT
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_hardware_miner_board
                    ON miner_hardware(miner_id, board_index);

                -- ── AMS miner_readings extended fields ─────────────────────────────
                -- Stores fields from AMS that belong in miner_readings but weren't there:
                -- timestamp (AMS reading time), map coordinates, stratum URL, pdu counter
                CREATE TABLE IF NOT EXISTS miner_ams_extended (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id             INTEGER NOT NULL REFERENCES scans(id),
                    scanned_at          TEXT    NOT NULL,
                    miner_id            TEXT    NOT NULL,
                    ip                  TEXT,
                    ams_timestamp       TEXT,
                    map_location_id     INTEGER,
                    map_x               REAL,
                    map_y               REAL,
                    pdu_counter         REAL,
                    stratum_url         TEXT,
                    favorite            INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_ams_ext_miner
                    ON miner_ams_extended(miner_id, scanned_at);
            """)

            # ── Schema migrations for existing databases ──────────────────────
            # Add outcome feedback columns to miner_restarts if not present
            existing = [r[1] for r in conn.execute(
                "PRAGMA table_info(miner_restarts)").fetchall()]
            for col, typedef in [
                ("outcome",             "TEXT"),
                ("outcome_checked_at",  "TEXT"),
                ("hashrate_before",     "REAL"),
                ("hashrate_after",      "REAL"),
                ("recovery_time_scans", "INTEGER"),
            ]:
                if col not in existing:
                    conn.execute(
                        f"ALTER TABLE miner_restarts ADD COLUMN {col} {typedef}")
                    logger.info("Migration: added miner_restarts.%s", col)
            conn.commit()

        logger.info("Database ready at %s", self.db_path)

    def save_pending_approvals(self, thread_ts: str, scan_id: int,
                               issues: List[Dict]) -> None:
        """Save actionable issues as pending approvals linked to a Slack thread.

        Rules:
          - Only RESTART / PDU_CYCLE / RESTART_CHECK_BOARDS ever need approval
          - Known dead boards are skipped (need physical inspection)
          - One pending approval per miner — if one already exists, update it
            so the thread_ts and problem stay current without creating duplicates
        """
        now  = datetime.now().isoformat()
        with self._connect() as conn:
            for i in issues:
                if i["action"] not in ("PDU_CYCLE", "RESTART", "RESTART_CHECK_BOARDS", "POWER_PROFILE_UP", "PREEMPTIVE_RESTART", "ECO_MODE", "MONITOR_CLOSE"):
                    continue
                if self.has_known_dead_boards(str(i["id"])):
                    logger.info("Skipping pending approval for miner %s (%s) — known dead boards",
                                i["id"], i.get("ip"))
                    continue

                problem = " | ".join(i.get("issues", []))

                # Check if a PENDING approval already exists for this miner
                existing = conn.execute(
                    "SELECT id FROM pending_approvals "
                    "WHERE miner_id=? AND status='PENDING' LIMIT 1",
                    (str(i["id"]),)
                ).fetchone()

                if existing:
                    # Update existing row — keep it current without spamming new rows
                    conn.execute("""
                        UPDATE pending_approvals
                        SET thread_ts=?, scan_id=?, action_type=?,
                            problem=?, pdu_id=?, outlet=?, created_at=?
                        WHERE id=?
                    """, (thread_ts, scan_id, i["action"],
                          problem, i.get("pdu_id"), i.get("outlet"),
                          now, existing["id"]))
                    logger.debug("Updated existing pending approval for miner %s", i["id"])
                else:
                    # New pending approval
                    conn.execute("""
                        INSERT INTO pending_approvals
                        (created_at, scan_id, thread_ts, miner_id, ip, model,
                         action_type, problem, pdu_id, outlet)
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                    """, (now, scan_id, thread_ts,
                          i["id"], i["ip"], i["model"],
                          i["action"], problem,
                          i.get("pdu_id"), i.get("outlet")))
                    logger.info("New pending approval for miner %s (%s) → %s",
                                i["id"], i["ip"], i["action"])

    def expire_old_pending_approvals(self, max_age_minutes: int = 30) -> int:
        """Auto-deny pending approvals older than max_age_minutes.

        Called at the start of each scan cycle. If you didn't respond in
        30 minutes, the approval is auto-denied and cleared from the queue.
        This prevents the queue from growing unboundedly across scans.
        """
        cutoff = (datetime.now() - timedelta(minutes=max_age_minutes)).isoformat()
        with self._connect() as conn:
            expired = conn.execute(
                "SELECT id, miner_id, ip, action_type FROM pending_approvals "
                "WHERE status='PENDING' AND created_at < ?",
                (cutoff,)
            ).fetchall()

            if expired:
                conn.execute("""
                    UPDATE pending_approvals
                    SET status='DENIED', responded_at=?
                    WHERE status='PENDING' AND created_at < ?
                """, (datetime.now().isoformat(), cutoff))

                # Log each expiry to audit trail
                for row in expired:
                    conn.execute("""
                        INSERT INTO action_audit_log
                        (timestamp, date, miner_id, ip, model, problem,
                         action_taken, decision, approved_by, notes)
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                    """, (datetime.now().isoformat(),
                          datetime.now().strftime("%Y-%m-%d"),
                          row["miner_id"], row["ip"], "", "",
                          row["action_type"], "DENIED",
                          "Mining Guardian (Auto-Expired)",
                          f"No response within {max_age_minutes} minutes — auto-denied"))

                logger.info("Auto-expired %d pending approvals older than %d min",
                            len(expired), max_age_minutes)
        return len(expired) if expired else 0

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
                # Use BiXBiT profile parser for accurate rated TH/s, fall back to AMS maxHashrate
                _profile_str = m.get("currentProfile", "") or ""
                _profile_rated = parse_bixbit_profile(_profile_str)
                if _profile_rated:
                    # Profile gives us TH/s, hashrate from AMS is MH/s
                    pct = round((hashrate / 1000.0 / _profile_rated) * 100, 1) if _profile_rated > 0 else 0.0
                elif max_hr > 0:
                    pct = round((hashrate / max_hr) * 100, 1)
                else:
                    pct = 0.0
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
        """Store extracted log file contents and parse all structured data from miner.log.

        Deduplicates by (miner_id, log_file) — same file is never stored twice.
        Hardware identity is parsed and upserted permanently.
        Per-chip hashrate, PSU voltage, system health parsed into structured tables.
        """
        now = datetime.now().isoformat()
        saved = 0
        with self._connect() as conn:
            for filename, content in log_files.items():
                # Dedup check — skip if this exact file was already stored
                # under the SAME health_status label. The same physical log file
                # may legitimately be stored under multiple labels (e.g. once as
                # 'healthy' from a routine scan and again as 'pre-restart' when
                # the operator approves a restart action) — those are distinct
                # observations of the system state and both have value.
                # Bug fix (Apr 8 2026): previously dedup was on (miner_id,
                # log_file) only, which silently dropped pre/post-restart saves
                # of files already captured under 'healthy'.
                existing = conn.execute(
                    "SELECT id FROM miner_logs WHERE miner_id=? AND log_file=? AND health_status=?",
                    (miner_id, filename, health_status)
                ).fetchone()
                if existing:
                    logger.debug("[%s] Log already stored under %s: %s — skipping",
                                 miner_id, health_status, filename)
                    continue
                conn.execute(
                    "INSERT INTO miner_logs "
                    "(collected_at, miner_id, model, health_status, log_file, content) "
                    "VALUES (?,?,?,?,?,?)",
                    (now, miner_id, model, health_status, filename, content)
                )
                saved += 1

        if saved:
            logger.info("Saved %s new log files for miner %s (%s)", saved, miner_id, health_status)

        # Parse hardware identity and structured data from miner.log automatically
        for filename, content in log_files.items():
            if "miner.log" in filename and content:
                try:
                    with self._connect() as conn:
                        row = conn.execute(
                            "SELECT ip, mac FROM miner_readings WHERE miner_id=? ORDER BY id DESC LIMIT 1",
                            (miner_id,)
                        ).fetchone()
                    ip  = row["ip"] if row else ""
                    mac = row["mac"] if row else ""
                    # Hardware identity — parse once, upsert permanently
                    self.parse_and_save_hardware(miner_id, ip, mac, content, filename)
                    # Parse per-chip data and other structured log data
                    self.parse_log_metrics(miner_id, ip, content, filename)
                except Exception as e:
                    logger.warning("[%s] Log parse failed: %s", miner_id, e)

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

    def last_log_collected(self, miner_id: str):
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
        """Register or update known dead boards for a miner.
        Sets ticket_created=None so the next scan knows to create an AMS ticket.
        """
        now = datetime.now().isoformat()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM known_dead_boards WHERE miner_id = ? AND resolved_at IS NULL",
                (miner_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE known_dead_boards SET board_indices=?, restart_attempted=?, restart_result=? WHERE id=?",
                    (str(board_indices), now, restart_result, existing[0])
                )
            else:
                conn.execute(
                    "INSERT INTO known_dead_boards "
                    "(miner_id, ip, model, board_indices, first_seen, restart_attempted, restart_result, ticket_created) "
                    "VALUES (?,?,?,?,?,?,?,NULL)",
                    (miner_id, ip, model, str(board_indices), now,
                     now if restart_result else None, restart_result)
                )
        logger.info("[%s] Registered known dead boards %s — result: %s", miner_id, board_indices, restart_result)

    def needs_ticket(self, miner_id: str) -> Optional[dict]:
        """Return dead board record if it needs an AMS ticket created (ticket_created IS NULL)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT miner_id, ip, model, board_indices, first_seen, restart_result "
                "FROM known_dead_boards "
                "WHERE miner_id=? AND resolved_at IS NULL AND ticket_created IS NULL "
                "AND restart_attempted IS NOT NULL",
                (miner_id,)
            ).fetchone()
        return dict(row) if row else None

    def mark_ticket_created(self, miner_id: str, ticket_id: str = None) -> None:
        """Record that an AMS ticket has been created for this dead board miner."""
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE known_dead_boards SET ticket_created=? "
                "WHERE miner_id=? AND resolved_at IS NULL",
                (ticket_id or now, miner_id)
            )
        conn.commit() if hasattr(conn, 'commit') else None
        logger.info("[%s] AMS ticket recorded: %s", miner_id, ticket_id or now)

    def get_newly_ticketed(self) -> list:
        """Return dead board miners whose ticket was created but not yet noticed in Slack.

        Bug fix: ticket_created stores the ticket ID string (e.g. '2661'), not a
        timestamp — comparing it against a datetime cutoff always matched because
        '2661' > '2026-...' alphabetically, so the notice showed every scan forever.
        Now we track ticket_noticed_at separately. Only rows where ticket_noticed_at
        IS NULL are returned — marking them noticed happens immediately after posting.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT miner_id, ip, model, board_indices, ticket_created "
                "FROM known_dead_boards "
                "WHERE resolved_at IS NULL AND ticket_created IS NOT NULL "
                "AND ticket_noticed_at IS NULL"
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_ticket_noticed(self, miner_ids: list) -> None:
        """Mark tickets as noticed in Slack — won't appear in future reports."""
        if not miner_ids:
            return
        now = datetime.now().isoformat()
        with self._connect() as conn:
            for miner_id in miner_ids:
                conn.execute(
                    "UPDATE known_dead_boards SET ticket_noticed_at=? "
                    "WHERE miner_id=? AND resolved_at IS NULL",
                    (now, miner_id)
                )

    def resolve_dead_boards(self, miner_id: str):
        """Mark dead boards as resolved (boards recovered after restart or repair)."""
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE known_dead_boards SET resolved_at = ? WHERE miner_id = ? AND resolved_at IS NULL",
                (now, miner_id)
            )

    def save_chain_readings(self, scan_id: int, scanned_at: str, miners: List[Dict]) -> None:
        """Store per-board chain data every scan: rate, voltage, freq, consumption, HW errors, temps."""
        rows = []
        for m in miners:
            miner_id = str(m.get("id", ""))
            ip = m.get("ip", "")
            for chain in (m.get("chains", []) or []):
                rows.append((
                    scan_id, scanned_at, miner_id, ip,
                    chain.get("index", 0), chain.get("rate", 0),
                    chain.get("voltage"), chain.get("freq"),
                    chain.get("consumption"), chain.get("HWErrors", 0),
                    chain.get("tempBoard"), chain.get("tempChip"),
                ))
        if not rows:
            return
        with self._connect() as conn:
            conn.executemany("""
                INSERT INTO chain_readings
                (scan_id, scanned_at, miner_id, ip, board_index,
                 rate_mhs, voltage, freq_mhz, consumption_w,
                 hw_errors, temp_board, temp_chip)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, rows)

    def save_pool_readings(self, scan_id: int, scanned_at: str, miners: List[Dict]) -> None:
        """Store per-pool stats every scan: accepted/rejected shares, diff, pool status."""
        rows = []
        for m in miners:
            miner_id = str(m.get("id", ""))
            ip = m.get("ip", "")
            for pool in (m.get("pools", []) or []):
                rows.append((
                    scan_id, scanned_at, miner_id, ip,
                    pool.get("priority", 0), pool.get("url", ""),
                    pool.get("user", ""), pool.get("poolType", ""),
                    pool.get("status", ""),
                    int(pool.get("accepted", 0) or 0),
                    int(pool.get("rejected", 0) or 0),
                    float(pool.get("acceptedDiff", 0) or 0),
                    float(pool.get("rejectedDiff", 0) or 0),
                    pool.get("diff", ""),
                ))
        if not rows:
            return
        with self._connect() as conn:
            conn.executemany("""
                INSERT INTO pool_readings
                (scan_id, scanned_at, miner_id, ip, pool_priority,
                 pool_url, pool_user, pool_type, status,
                 accepted, rejected, accepted_diff, rejected_diff, difficulty)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, rows)

    def save_miner_state_readings(self, scan_id: int, scanned_at: str, miners: List[Dict]) -> None:
        """Store extended state fields from AMS miner list: hashrate tiers, limits, status codes."""
        rows = []
        for m in miners:
            rows.append((
                scan_id, scanned_at, str(m.get("id", "")), m.get("ip", ""),
                m.get("hashrateMedium"), m.get("hashrateLow"),
                m.get("maxHashrate"), m.get("maxConsumption"),
                m.get("maxTempBoard"), m.get("maxTempChip"),
                m.get("tempChipLow"), m.get("tempChipMedium"),
                m.get("minerStatus"), m.get("coolingMode"),
                m.get("workerVersion", ""), m.get("activePoolUser", ""),
            ))
        if not rows:
            return
        with self._connect() as conn:
            conn.executemany("""
                INSERT INTO miner_state_readings
                (scan_id, scanned_at, miner_id, ip,
                 hashrate_medium, hashrate_low, max_hashrate, max_consumption,
                 max_temp_board, max_temp_chip, temp_chip_low, temp_chip_medium,
                 miner_status, cooling_mode, worker_version, active_pool_user)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, rows)

    def save_ams_extended(self, scan_id: int, scanned_at: str, miners: List[Dict]) -> None:
        """Store AMS fields not captured elsewhere: timestamp, map coords, pdu counter, stratum URL."""
        rows = []
        for m in miners:
            map_loc = m.get("mapLocation") or {}
            pdu_out = m.get("pduOutlet") or {}
            # Get stratum URL from primary pool
            pools = m.get("pools") or []
            stratum_url = pools[0].get("stratumURL", "") if pools else ""
            rows.append((
                scan_id, scanned_at, str(m.get("id", "")), m.get("ip", ""),
                m.get("timestamp", ""),
                map_loc.get("id"),
                map_loc.get("x"),
                map_loc.get("y"),
                pdu_out.get("counter"),
                stratum_url,
                1 if m.get("favorite") else 0,
            ))
        if not rows:
            return
        with self._connect() as conn:
            conn.executemany("""
                INSERT INTO miner_ams_extended
                (scan_id, scanned_at, miner_id, ip,
                 ams_timestamp, map_location_id, map_x, map_y,
                 pdu_counter, stratum_url, favorite)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, rows)

    def parse_and_save_hardware(self, miner_id: str, ip: str, mac: str,
                                 log_content: str, log_source: str) -> int:
        """Parse CGMiner/BixMiner miner.log and extract hardware identity.

        Extracts from EEPROM lines per board:
          board_name, serial_number, chip_die, chip_marking, chip_technology,
          pcb_version, bom_version, chip_bin, chip_ft_ver, ideal_hashrate

        Extracts from device detection lines:
          control_board, psu_version, bixminer_version, topol_machine,
          device_name, asic_count, bad_chips_count, pic_version

        Returns count of boards parsed.
        """
        import re
        now = datetime.now().isoformat()

        # Per-board EEPROM data
        eeprom_pattern = re.compile(
            r'Eeprom chain \[(\d+)\] '
            r'board_name: (\S+), '
            r'sn_oom: (\S+), '
            r'chip_die_oom: (\S+), '
            r'chip_marking_oom: (\S+), '
            r'chip_technology_oom: (\S+).*?'
            r'chip_bin (\S+).*?'
            r'chip_ft_ver (\S+).*?'
            r'pcb_version (\S+).*?'
            r'bom_version (\S+).*?'
            r'voltage \d+.*?'
            r'freq \d+.*?'
            r'ideal_hashrate (\d+)',
            re.MULTILINE
        )

        # Device-level fields
        control_board  = re.search(r'Control board: (\S+)', log_content)
        psu_version    = re.search(r'Detected psu version: (\S+)', log_content)
        bixminer_ver   = re.search(r'BixMiner ver: ([\S]+),', log_content)
        topol_machine  = re.search(r'Topol machine: (\S+)', log_content)
        device_name    = re.search(r'Device name: (.+)', log_content)

        ctrl_board_val  = control_board.group(1) if control_board else None
        psu_ver_val     = psu_version.group(1) if psu_version else None
        bixminer_val    = bixminer_ver.group(1) if bixminer_ver else None
        topol_val       = topol_machine.group(1) if topol_machine else None
        device_val      = device_name.group(1).strip() if device_name else None

        # Per-board asic counts
        asic_pattern = re.compile(r'Chain\[(\d+)\]: found (\d+) asic, bad chips (\d+)')
        asic_map = {}
        for match in asic_pattern.finditer(log_content):
            idx = int(match.group(1))
            asic_map[idx] = {"asic_count": int(match.group(2)), "bad_chips": int(match.group(3))}

        # PIC versions (one per board)
        pic_pattern = re.compile(r'Pic \[(\d+)\] version (\d+)')
        pic_map = {}
        for match in pic_pattern.finditer(log_content):
            pic_map[int(match.group(1))] = match.group(2)

        boards_parsed = 0
        with self._connect() as conn:
            for match in eeprom_pattern.finditer(log_content):
                board_idx = int(match.group(1))
                asic_info = asic_map.get(board_idx, {})
                pic_ver   = pic_map.get(board_idx)

                conn.execute("""
                    INSERT INTO miner_hardware
                    (miner_id, ip, mac, board_index, board_name, serial_number,
                     chip_die, chip_marking, chip_technology,
                     pcb_version, bom_version, chip_bin, chip_ft_ver, ideal_hashrate,
                     control_board, psu_version, bixminer_version, topol_machine,
                     device_name, asic_count, bad_chips_count, pic_version,
                     first_seen, last_updated, log_source)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(miner_id, board_index) DO UPDATE SET
                        board_name=excluded.board_name,
                        serial_number=excluded.serial_number,
                        chip_die=excluded.chip_die,
                        chip_marking=excluded.chip_marking,
                        chip_technology=excluded.chip_technology,
                        pcb_version=excluded.pcb_version,
                        bom_version=excluded.bom_version,
                        chip_bin=excluded.chip_bin,
                        chip_ft_ver=excluded.chip_ft_ver,
                        ideal_hashrate=excluded.ideal_hashrate,
                        control_board=excluded.control_board,
                        psu_version=excluded.psu_version,
                        bixminer_version=excluded.bixminer_version,
                        topol_machine=excluded.topol_machine,
                        device_name=excluded.device_name,
                        asic_count=excluded.asic_count,
                        bad_chips_count=excluded.bad_chips_count,
                        pic_version=excluded.pic_version,
                        last_updated=excluded.last_updated,
                        log_source=excluded.log_source
                """, (
                    miner_id, ip, mac, board_idx,
                    match.group(2),   # board_name
                    match.group(3),   # serial_number
                    match.group(4),   # chip_die
                    match.group(5),   # chip_marking
                    match.group(6),   # chip_technology
                    match.group(9),   # pcb_version
                    match.group(10),  # bom_version
                    match.group(7),   # chip_bin
                    match.group(8),   # chip_ft_ver
                    int(match.group(11)),  # ideal_hashrate
                    ctrl_board_val, psu_ver_val, bixminer_val,
                    topol_val, device_val,
                    asic_info.get("asic_count"),
                    asic_info.get("bad_chips"),
                    pic_ver,
                    now, now, log_source
                ))
                boards_parsed += 1

        if boards_parsed:
            logger.info("[%s] Hardware identity parsed: %s boards from %s",
                        miner_id, boards_parsed, log_source)
        return boards_parsed

    def get_hardware_identity(self, miner_id: str) -> List[Dict]:
        """Return hardware identity records for a miner (one per board)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM miner_hardware WHERE miner_id=? ORDER BY board_index",
                (miner_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def parse_log_metrics(self, miner_id: str, ip: str,
                          log_content: str, log_source: str) -> None:
        """Parse structured metrics from miner.log that aren't available via AMS.

        Extracts and stores:
        1. Per-chip hashrate vs target (the [chip_idx  actual  target] lines)
           - 126 chips per miner, logged every ~30 seconds
           - Key for detecting individual failing chips before board dies
        2. PSU voltage and estimated power over time
        3. CPU/memory system health over time
        4. Chain attach/detach events with timestamps

        All data is stored in log_metrics table for trending and AI analysis.
        """
        import re

        now = datetime.now().isoformat()
        rows = []

        # Per-chip hashrate lines: [chip_idx  actual  target] format
        # Example: [  0  97.69 121.47][  1  98.62 121.47]...
        chip_line_pattern = re.compile(
            r'\[(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\] INFO: '
            r'((?:\[\s*\d+\s+[\d.]+\s+[\d.]+\]\s*)+)'
        )

        # PSU voltage line: "Psu current voltage 14.70V, sample voltage 14.57V, power estimated 4632W"
        psu_pattern = re.compile(
            r'\[(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\] INFO: '
            r'Psu current voltage ([\d.]+)V, sample voltage ([\d.]+)V, power estimated (\d+)W'
        )

        # System health: "Total cpu: 79.65%, miner cpu: 44.16%, free mem: 158 MB, miner mem: 30 MB"
        sys_pattern = re.compile(
            r'\[(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\] INFO: '
            r'Total cpu: ([\d.]+)%, miner cpu: ([\d.]+)%, free mem: (\d+) MB, miner mem: (\d+) MB'
        )

        # Chain attach/detach events
        chain_event_pattern = re.compile(
            r'\[(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\] '
            r'(INFO|WARN): Chain\[(\d+)\] (attached|detached)'
        )

        # Ensure log_metrics table exists
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS log_metrics (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    miner_id        TEXT    NOT NULL,
                    ip              TEXT,
                    log_timestamp   TEXT,
                    metric_type     TEXT    NOT NULL,
                    board_index     INTEGER,
                    chip_index      INTEGER,
                    value_1         REAL,
                    value_2         REAL,
                    value_3         REAL,
                    value_4         REAL,
                    text_value      TEXT,
                    log_source      TEXT,
                    recorded_at     TEXT    NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_log_metrics_miner
                    ON log_metrics(miner_id, log_timestamp)
            """)

        # Parse PSU readings
        psu_rows = []
        for m in psu_pattern.finditer(log_content):
            psu_rows.append((
                miner_id, ip, m.group(1), "psu_voltage",
                None, None,
                float(m.group(2)),   # current voltage
                float(m.group(3)),   # sample voltage
                float(m.group(4)),   # power watts
                None, None,
                log_source, now
            ))

        # Parse system health readings
        sys_rows = []
        for m in sys_pattern.finditer(log_content):
            sys_rows.append((
                miner_id, ip, m.group(1), "system_health",
                None, None,
                float(m.group(2)),   # total cpu %
                float(m.group(3)),   # miner cpu %
                float(m.group(4)),   # free mem MB
                float(m.group(5)),   # miner mem MB
                None,
                log_source, now
            ))

        # Parse chain events
        event_rows = []
        for m in chain_event_pattern.finditer(log_content):
            event_rows.append((
                miner_id, ip, m.group(1), "chain_event",
                int(m.group(3)), None,
                None, None, None, None,
                m.group(4),  # "attached" or "detached"
                log_source, now
            ))

        # Parse per-chip hashrate (sample every 10th occurrence to avoid DB explosion)
        # Full 5MB log has thousands of these — we sample to keep DB manageable
        chip_rows = []
        chip_line_count = 0
        chip_entry_pattern = re.compile(r'\[\s*(\d+)\s+([\d.]+)\s+([\d.]+)\]')

        for m in chip_line_pattern.finditer(log_content):
            chip_line_count += 1
            if chip_line_count % 10 != 0:  # sample every 10th timestamp
                continue
            timestamp = m.group(1)
            line_data = m.group(2)
            for chip_m in chip_entry_pattern.finditer(line_data):
                chip_rows.append((
                    miner_id, ip, timestamp, "chip_hashrate",
                    None, int(chip_m.group(1)),
                    float(chip_m.group(2)),   # actual TH/s
                    float(chip_m.group(3)),   # target TH/s
                    None, None, None,
                    log_source, now
                ))

        all_rows = psu_rows + sys_rows + event_rows + chip_rows
        if not all_rows:
            return

        with self._connect() as conn:
            conn.executemany("""
                INSERT INTO log_metrics
                (miner_id, ip, log_timestamp, metric_type,
                 board_index, chip_index,
                 value_1, value_2, value_3, value_4, text_value,
                 log_source, recorded_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, all_rows)

        logger.info("[%s] Log metrics parsed: %d PSU + %d sys + %d events + %d chip samples",
                    miner_id, len(psu_rows), len(sys_rows),
                    len(event_rows), len(chip_rows))

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
                       restart_type: str, elevated_hours: int = 3,
                       hashrate_before: float = None) -> None:
        """Record a restart event, set elevated monitoring window, and mark outcome as PENDING.
        hashrate_before captures the miner's hashrate_pct at time of restart so the
        outcome checker knows what 'before' looked like without a separate lookup.
        """
        now            = datetime.now()
        elevated_until = (now + timedelta(hours=elevated_hours)).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO miner_restarts "
                "(restarted_at, miner_id, ip, model, restart_type, elevated_until, "
                " outcome, hashrate_before) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (now.isoformat(), miner_id, ip, model, restart_type,
                 elevated_until, "PENDING", hashrate_before)
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

    def get_failed_restart_count(self, miner_id: str, days: int = 7) -> int:
        """Count restarts in the last N days where the miner did not recover."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with self._connect() as conn:
            row = conn.execute("""
                SELECT COUNT(*) as cnt FROM miner_restarts
                WHERE miner_id=? AND restarted_at >= ?
            """, (miner_id, cutoff)).fetchone()
        return row["cnt"] if row else 0

    def count_outcome_failures(self, miner_id: str) -> int:
        """Count restarts labeled FAILURE by the outcome feedback loop (Feature 1)."""
        with self._connect() as conn:
            row = conn.execute("""
                SELECT COUNT(*) as cnt FROM miner_restarts
                WHERE miner_id=? AND outcome='FAILURE'
            """, (miner_id,)).fetchone()
        return row["cnt"] if row else 0

    def _count_pdu_cycles(self, miner_id: str, days: int = 1) -> int:
        """Count PDU power cycles attempted for this miner in the last N days."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with self._connect() as conn:
            row = conn.execute("""
                SELECT COUNT(*) as cnt FROM action_audit_log
                WHERE miner_id=? AND action_taken='PDU_CYCLE'
                  AND timestamp >= ?
            """, (miner_id, cutoff)).fetchone()
        return row["cnt"] if row else 0

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
        return scan_id


# ------------------------------------------------------------
# Slack notifier — direct fleet alerts to #mining-guardian
# ------------------------------------------------------------

class SlackNotifier:

    # ── Channel routing (Apr 8 2026) ──────────────────────────────────────
    # The fleet operator (Bobby) split #mining-guardian into 6 dedicated
    # channels so each message type lives in its own stream. This makes
    # the AI report channel a clean historical journal of LLM thinking,
    # the approvals channel an at-a-glance pending queue, etc.
    #
    # Each constant can be overridden via environment variable for ops
    # flexibility. Defaults are the production channel IDs in the
    # bixbitusa workspace.

    # Main channel — operator chat, natural language queries, manual ops
    CHANNEL_ID         = "C0AQ8SE1448"  # #mining-guardian
    # Hourly fleet scan posts — the routine operational stream
    SCANS_CHANNEL_ID   = "C0ARLJUJ3BQ"  # #mg-scans
    # Mining Guardian AI Analysis output — LLM interpretations
    AI_CHANNEL_ID      = "C0ARSB1U604"  # #mg-ai-reports
    # Pending approval requests + approve/deny threads
    APPROVALS_CHANNEL_ID = "C0AR79YRZ9V"  # #mg-approvals
    # Critical alerts — firmware regressions, ticket creation, dead boards
    ALERTS_CHANNEL_ID  = "C0ARJP300J0"  # #mining-guardian-alerts (existing)
    # Pre/post log comparisons + dual-model verdicts + manual upload analyses
    LOGS_CHANNEL_ID    = "C0ASH2CPHBJ"  # #mg-logs

    def __init__(self, webhook_url: Optional[str], channel_id: Optional[str] = None,
                 bot_token: Optional[str] = None,
                 alerts_channel_id: Optional[str] = None):
        self.webhook_url   = webhook_url
        self.bot_token     = bot_token

        # Each channel can be overridden via env var for ops flexibility.
        # Falls back to hardcoded constants if env var is not set.
        self.channel_id           = (channel_id
                                     or os.getenv("MG_CHANNEL_MAIN")
                                     or self.CHANNEL_ID)
        self.scans_channel_id     = os.getenv("MG_CHANNEL_SCANS")     or self.SCANS_CHANNEL_ID
        self.ai_channel_id        = os.getenv("MG_CHANNEL_AI")        or self.AI_CHANNEL_ID
        self.approvals_channel_id = os.getenv("MG_CHANNEL_APPROVALS") or self.APPROVALS_CHANNEL_ID
        self.alerts_channel_id    = (alerts_channel_id
                                     or os.getenv("MG_CHANNEL_ALERTS")
                                     or self.ALERTS_CHANNEL_ID)
        self.logs_channel_id      = os.getenv("MG_CHANNEL_LOGS")      or self.LOGS_CHANNEL_ID

    def post_to_channel(self, message: str, channel_id: Optional[str] = None) -> str:
        """Post a plain message to a channel. Defaults to the main channel.

        Pass channel_id to override (e.g. self.alerts_channel_id for feed posts).
        Webhook fallback only sends to whatever channel the webhook is configured
        for — bot token path is required for routing.
        """
        target = channel_id or self.channel_id
        try:
            if self.bot_token:
                from slack_sdk import WebClient
                resp = WebClient(token=self.bot_token).chat_postMessage(
                    channel=target, text=message
                )
                return resp.get("ts", "")
            elif self.webhook_url:
                requests.post(self.webhook_url, json={"text": message}, timeout=10)
                return ""
        except Exception as e:
            logger.warning("post_to_channel failed: %s", e)
        return ""

    def post_to_alerts_channel(self, message: str) -> str:
        """Post to the #mining-guardian-alerts channel.

        Critical alerts only — firmware regressions, ticket creation, dead
        board escalations, fleet emergencies. Anything operators need to see
        ASAP and that warrants a notification ping.
        """
        return self.post_to_channel(message, channel_id=self.alerts_channel_id)

    # ── New category-specific helpers (Apr 8 2026 channel split) ──────────

    def post_to_scans(self, message: str) -> str:
        """Post to #mg-scans — hourly fleet scan summaries (the routine feed)."""
        return self.post_to_channel(message, channel_id=self.scans_channel_id)

    def post_to_ai_reports(self, message: str) -> str:
        """Post to #mg-ai-reports — LLM analysis output, post-scan AI interpretations."""
        return self.post_to_channel(message, channel_id=self.ai_channel_id)

    def post_to_approvals(self, message: str) -> str:
        """Post to #mg-approvals — pending approval requests requiring operator decision."""
        return self.post_to_channel(message, channel_id=self.approvals_channel_id)

    def post_to_logs(self, message: str) -> str:
        """Post to #mg-logs — pre/post log comparisons, dual-model verdicts, manual upload analyses."""
        return self.post_to_channel(message, channel_id=self.logs_channel_id)

    def post_blocks_to_channel(self, blocks: list, fallback_text: str = "Mining Guardian update",
                                channel_id: Optional[str] = None) -> str:
        """Post a Block Kit message. Defaults to the main channel.

        Pass channel_id to override (e.g. self.alerts_channel_id for feed posts).
        Outbound-only (chat.postMessage). Works on the VPS today and on the
        production Mac Mini after May 5 — no public ingress required.

        Block Kit messages need a bot token (webhooks do not reliably render
        rich blocks). Falls back to plain text via post_to_channel if bot
        token is not configured. Interactive button click handling is routed
        through OpenClaw socket → localhost approval API, NOT through any URL
        handler that would require public ingress. See docs/CLOUDFLARE_MIGRATION.md.
        """
        target = channel_id or self.channel_id
        if not self.bot_token:
            logger.warning("post_blocks_to_channel: no bot token, falling back to plain text")
            return self.post_to_channel(fallback_text, channel_id=target)
        try:
            from slack_sdk import WebClient
            resp = WebClient(token=self.bot_token).chat_postMessage(
                channel=target,
                blocks=blocks,
                text=fallback_text,  # required for notifications and accessibility
            )
            return resp.get("ts", "")
        except Exception as e:
            logger.warning("post_blocks_to_channel failed: %s", e)
            return ""

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

    def send_ams_down(self, miners: List[Dict], wx: Optional[Dict] = None,
                      hvac=None) -> None:
        """Send a simple AMS-is-down message with just weather and mechanical data."""
        if not self.webhook_url:
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [
            f"*🤖 Mining Guardian — {now}*",
            f"🔴 *AMS is offline* — all {len(miners)} miners reporting offline.",
            "Miner analysis suspended until AMS comes back online.",
        ]

        if wx:
            lines.append(
                f"\n🌡️ Outside: *{wx['temp_f']}°F* | Humidity: *{wx['humidity_pct']}%* | "
                f"Feels like: {wx['feels_like_f']}°F | Today: {wx['temp_low_f']}–{wx['temp_high_f']}°F"
            )

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

            lines.append(f"\n*🏭 Warehouse Mechanical*")
            lines.append(f"  Supply: *{sup}* | Return: *{ret}* | ΔT: *{dlt}* | Diff Press: *{dp}*")
            lines.append(f"  Spray Pump: {pump} | CW Pump 1: {cwp1} | CW Pump 2: {cwp2}")
            lines.append(f"  CT Fan 1: {ct1} | CT Fan 2: {ct2}")

            alarms = []
            if hvac.leak_alarm:       alarms.append("🔴 LEAK DETECTED")
            if hvac.tower_vibration:  alarms.append("🔴 TOWER VIBRATION")
            if hvac.ct1_fault:        alarms.append("🔴 CT Fan 1 FAULT")
            if hvac.ct2_fault:        alarms.append("🔴 CT Fan 2 FAULT")
            if hvac.pump_fault:       alarms.append("🔴 Spray Pump FAULT")

            if alarms:
                lines.append(f"  ⚠️ *ALARMS:* {' | '.join(alarms)}")
            else:
                lines.append("  ✅ All alarms clear")

        payload = {"text": "\n".join(lines)}
        try:
            if self.bot_token:
                from slack_sdk import WebClient
                client = WebClient(token=self.bot_token)
                # AMS-down notifications go to the #mining-guardian-alerts feed
                # channel, NOT the main channel. They are read-only status alerts
                # that don't require operator interaction (no approval, no
                # button click, no thread reply needed).
                client.chat_postMessage(channel=self.alerts_channel_id, text=payload["text"])
            else:
                requests.post(self.webhook_url, json=payload, timeout=10)
            logger.info("AMS-down notification sent to #mining-guardian-alerts")
        except Exception as e:
            logger.warning("Slack AMS-down notification failed: %s", e)

    def send_scan(self, miners: List[Dict], issues: List[Dict],
                  wx: Optional[Dict] = None,
                  ams_notifs: Optional[List[Dict]] = None,
                  hvac=None) -> None:
        """POST a formatted scan summary to Slack via incoming webhook."""
        if not self.webhook_url:
            logger.debug("Slack webhook not configured — skipping Slack notification")
            return

        # Quiet hours — no Slack messages 10pm–5am
        # Overnight automation handles that window; Slack noise at night is unwanted
        current_hour = datetime.now().hour
        if current_hour >= 22 or current_hour < 5:
            logger.debug("Quiet hours (10pm–5am) — suppressing Slack scan report")
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

            # Feature 5: Add facility stress level to HVAC section
            try:
                from hvac_correlator import get_facility_stress_level
                stress, stress_reasons = get_facility_stress_level()
                if stress >= 51:
                    hvac_lines.append(
                        f"  🏭 *FACILITY STRESS: {stress}%* — "
                        f"{', '.join(stress_reasons[:2])}. "
                        f"Fleet flags may be facility-caused."
                    )
                elif stress >= 26:
                    hvac_lines.append(
                        f"  🏭 Facility watch: {stress}% — {', '.join(stress_reasons[:1])}"
                    )
            except Exception:
                pass

            lines.extend(hvac_lines)

        lines.append(status_line)

        if pdu_cycles:
            lines.append(f"\n*🔴 PDU Power Cycle Recommended ({len(pdu_cycles)} miners)*")
            for i in pdu_cycles:
                location = i.get("map_location", "—")
                lines.append(f"  • `{i['ip']}` {i['model']} — {i.get('pdu_action', 'No PDU info')} | Location: {location}")
            lines.append("  _After power cycle: logs collected on boot, elevated monitoring for 3hrs._")

        if fw_restarts:
            # Split into: has known dead boards (info only) vs approvable
            dead_board_miners = set()
            try:
                db_tmp = GuardianDB()
                with db_tmp._connect() as conn:
                    rows = conn.execute(
                        "SELECT miner_id FROM known_dead_boards WHERE resolved_at IS NULL"
                    ).fetchall()
                    dead_board_miners = {str(r["miner_id"]) for r in rows}
            except Exception:
                pass

            approvable = [i for i in fw_restarts if str(i["id"]) not in dead_board_miners]
            dead_mixed = [i for i in fw_restarts if str(i["id"]) in dead_board_miners]

            from collections import defaultdict
            # Load confidence scorer once for the whole report
            try:
                from ai.confidence_scorer import get_confidence, get_gate
                _has_confidence = True
            except ImportError:
                _has_confidence = False

            if approvable:
                by_model: dict = defaultdict(list)
                for i in approvable:
                    by_model[i["model"]].append(i)
                lines.append(f"\n*🔴 Firmware Restart Recommended ({len(approvable)} miners)*")
                for model, group in by_model.items():
                    if len(group) == 1:
                        i = group[0]
                        conf_str = ""
                        if _has_confidence:
                            try:
                                score, _ = get_confidence(str(i["id"]), i["ip"], "RESTART",
                                                          hashrate_pct=i.get("hashrate_pct"))
                                gate = get_gate(score)
                                gate_emoji = "🟢" if gate == "AUTO" else "🟡" if gate == "ASK" else "🔴"
                                conf_str = f" {gate_emoji} Conf: {score}%"
                            except Exception:
                                pass
                        lines.append(f"  • `{i['ip']}` {model} — HR: {i['hashrate_pct']} | Temp: {i['temp_chip']}{conf_str}")
                    else:
                        ips = ", ".join(f"`{i['ip']}`" for i in group)
                        issue_str = " | ".join(set(" | ".join(i["issues"]) for i in group))
                        lines.append(f"  • *{len(group)}x {model}:* {ips}")
                        lines.append(f"    _{issue_str}_")

            if dead_mixed:
                lines.append(f"\n*🔴 Known Dead Boards — Physical Inspection Required ({len(dead_mixed)} miners)*")
                lines.append("  ⚠️ Restart already attempted — software cannot fix this.")
                for i in dead_mixed:
                    lines.append(f"  • `{i['ip']}` {i['model']} — needs physical board inspection")

        # One-time notice for miners whose AMS ticket was just created this cycle
        try:
            db = GuardianDB()
            newly_ticketed = db.get_newly_ticketed()
            if newly_ticketed:
                lines.append(f"\n*🎫 AMS Tickets Created ({len(newly_ticketed)})*")
                for t in newly_ticketed:
                    lines.append(f"  • `{t['ip']}` ({t['model']}) — ticket #{t['ticket_created']} created, removed from future reports")
                lines.append("  _These miners will no longer appear in scan reports until resolved._")
                # Mark as noticed so this block never shows again for these miners
                db.mark_ticket_noticed([t['miner_id'] for t in newly_ticketed])
        except Exception:
            pass

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
            pass  # Yellow temp miners logged to DB for learning — not shown in Slack

        if issues:
            actionable_count = sum(1 for i in issues if i["action"] in ("PDU_CYCLE","RESTART","RESTART_CHECK_BOARDS"))
            if actionable_count > 0:
                lines.append(f"\n_⬇️ *{actionable_count} action(s) pending* — reply in thread to approve._")

        # AMS notifications section — exclude miners already flagged in main report
        if ams_notifs:
            from collections import defaultdict
            key_labels = {
                "consumptionChangeLevel": "Power consumption change",
                "hotBoard":               "Hashboard overheating",
                "workerOffline":          "Miner went offline",
                "workerOnline":           "Miner came back online",
                "hashrateDropped":        "Hashrate dropped",
                "highTemp":               "High temperature",
                "lowHashrate":            "Low hashrate",
            }
            # Suppress ticketed miners from AMS alerts section too
            ticketed_ips = set()
            try:
                with self.db._connect() as _conn:
                    ticketed_ips = {
                        r["ip"] for r in _conn.execute(
                            "SELECT ip FROM known_dead_boards WHERE resolved_at IS NULL"
                        ).fetchall()
                    }
            except Exception:
                pass

            # IPs already covered in the main report or ticketed
            flagged_ips = {i["ip"] for i in issues} | ticketed_ips

            critical = [n for n in ams_notifs
                        if n.get("params", {}).get("alertLevel") == "Critical"
                        and n.get("params", {}).get("minerIp") not in flagged_ips]
            warnings = [n for n in ams_notifs
                        if n.get("params", {}).get("alertLevel") == "Warning"
                        and n.get("params", {}).get("minerIp") not in flagged_ips]

            if False and (critical or warnings):  # AMS alerts stored in DB, suppressed from Slack
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
            if self.bot_token:
                from slack_sdk import WebClient
                client = WebClient(token=self.bot_token)
                resp   = client.chat_postMessage(
                    channel=self.scans_channel_id,
                    text="\n".join(lines)
                )
                thread_ts = resp["ts"]
                logger.info("Slack notified — scan posted (ts=%s)", thread_ts)

                # Post per-miner interactive Block Kit selection message in thread
                actionable = [i for i in issues if i["action"] in ("PDU_CYCLE","RESTART","RESTART_CHECK_BOARDS")]
                if actionable:
                    self._post_miner_selection(client, thread_ts, actionable)
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

    def _post_miner_selection(self, client, thread_ts: str, actionable: list) -> None:
        """Post a rich Block Kit approval card in the thread.

        Uses display-only blocks (no buttons/checkboxes that need Socket Mode).
        OpenClaw owns Socket Mode so interactive elements would be intercepted.
        Instead: visual Block Kit card with ☐ checkboxes + text-reply approval.
        """
        ACTION_ICONS  = {"RESTART": "🔄", "PDU_CYCLE": "🔌", "RESTART_CHECK_BOARDS": "🔴"}
        ACTION_LABELS = {"RESTART": "Firmware Restart", "PDU_CYCLE": "PDU Power Cycle",
                         "RESTART_CHECK_BOARDS": "Dead Board Restart"}

        blocks = []

        # ── Header ────────────────────────────────────────────────────────
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"⬇️  {len(actionable)} Action{'s' if len(actionable) > 1 else ''} Pending Approval",
                "emoji": True
            }
        })
        blocks.append({"type": "divider"})

        # ── One section block per miner ───────────────────────────────────
        for idx, issue in enumerate(actionable, 1):
            icon  = ACTION_ICONS.get(issue["action"], "⚡")
            label = ACTION_LABELS.get(issue["action"], issue["action"])
            loc   = issue.get("map_location") or "—"
            hr    = issue.get("hashrate_pct", "?")
            temp  = issue.get("temp_chip", "?")
            model = issue.get("model", "?")
            ip    = issue["ip"]

            # Determine temp color indicator
            try:
                t = float(temp)
                temp_icon = "🔴" if t >= 84 else "🟢"
            except (TypeError, ValueError):
                temp_icon = "⚪"

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{idx}.* ☐  {icon} `{ip}` — *{label}*\n"
                        f"      {model}  |  📍 {loc}  |  ⚡ HR: *{hr}%*  |  {temp_icon} Temp: *{temp}°C*"
                    )
                }
            })

        # ── Divider + approval instructions ──────────────────────────────
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Reply in this thread to approve:*\n"
                    "`APPROVE` — approve all  •  `DENY` — deny all\n"
                    "`approve 1,3` — by number  •  `approve .36,.46` — by IP"
                )
            }
        })
        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": "☑ = approved  •  Approved actions execute immediately via AMS"
            }]
        })

        try:
            client.chat_postMessage(
                channel=self.channel_id,
                thread_ts=thread_ts,
                text=f"{len(actionable)} action(s) pending — reply to approve",  # fallback
                blocks=blocks
            )
            logger.info("Posted Block Kit approval card (%d miners) thread=%s",
                        len(actionable), thread_ts)
        except Exception as e:
            logger.warning("Block Kit card failed, falling back to plain text: %s", e)
            # Plain text fallback
            lines = [f"*{len(actionable)} action(s) pending — reply to approve:*",
                     "_`APPROVE` all | `DENY` all | `approve 1,3` | `approve .36,.46`_", ""]
            for idx, issue in enumerate(actionable, 1):
                icon  = ACTION_ICONS.get(issue["action"], "⚡")
                label = ACTION_LABELS.get(issue["action"], issue["action"])
                lines.append(
                    f"*{idx}.* {icon} `{issue['ip']}` — {issue['model']}\n"
                    f"    {label} | {issue.get('map_location','—')} | HR: {issue.get('hashrate_pct','?')}% | {issue.get('temp_chip','?')}°C"
                )
            try:
                client.chat_postMessage(
                    channel=self.channel_id,
                    thread_ts=thread_ts,
                    text="\n".join(lines)
                )
            except Exception as e2:
                logger.warning("Fallback plain text also failed: %s", e2)


class MiningGuardian:
    HASHRATE_THRESHOLD = 0.80   # flag if below 80% of rated TH/s

    def __init__(self, config: GuardianConfig):
        self.config   = config
        self.ams      = AMSClient(config)
        self.notifier = OpenClawNotifier(config.openclaw_webhook_url)
        self.slack    = SlackNotifier(
            webhook_url=GuardianConfig._resolve(config.slack_webhook_url) if config.slack_webhook_url else None,
            bot_token=GuardianConfig._resolve(config.slack_bot_token) if hasattr(config, "slack_bot_token") and config.slack_bot_token else None,
            channel_id=getattr(config, "slack_channel_id", None),
            alerts_channel_id=getattr(config, "slack_alerts_channel_id", None),
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
    def _analyze_chains(chains: list, expected_boards: int = 3) -> dict:
        """
        Analyse per-hashboard chain data from AMS.
        Returns a dict with:
          total_boards      — how many boards reported
          active_boards     — boards with rate > 1000 MH/s (1 TH/s floor)
          dead_boards       — boards with rate == 0 or None
          dead_indices      — list of dead board index numbers
          chain_rates_ths   — list of per-board rates in TH/s
          expected_boards   — expected board count for this model (2 or 3)
          pct_capacity      — hashrate as % of full-board capacity

        Bug fix: expected_boards is now a parameter so 2-board models like
        the AH3880 are reported correctly. Callers should pass the value from
        miner_specs.json; defaults to 3 for backward compatibility.
        """
        if not chains:
            return {"total_boards": 0, "active_boards": 0, "dead_boards": 0,
                    "dead_indices": [], "chain_rates_ths": [], "pct_capacity": None,
                    "expected_boards": expected_boards}

        rates_mhs    = [c.get("rate", 0) or 0 for c in chains]
        dead_indices = [chains[i].get("index", i) for i, r in enumerate(rates_mhs) if r < 1000]
        active       = [r for r in rates_mhs if r >= 1000]
        rates_ths    = [round(r / 1000, 1) for r in rates_mhs]

        avg_active   = (sum(active) / len(active)) if active else 0
        pct_capacity = round((len(active) / expected_boards) * 100, 1) if expected_boards > 0 else None

        return {
            "total_boards":    len(chains),
            "active_boards":   len(active),
            "dead_boards":     len(dead_indices),
            "dead_indices":    dead_indices,
            "chain_rates_ths": rates_ths,
            "avg_active_ths":  round(avg_active / 1000, 1),
            "expected_boards": expected_boards,
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

        # ── Post-restart grace period ─────────────────────────────────
        # Skip action recommendations for miners that aren't fully stable.
        # Check 1: MG-tracked restarts via elevated_until (3hr window)
        # Check 2: AMS minerStatus != 0 (initializing/starting/auto-tuning)
        #   minerStatus 0 = mining (stable, ready for actions)
        #   minerStatus 3 = auto-tuning (still calibrating, don't touch)
        #   minerStatus 6 = initializing (just booted, too early)
        #   Any non-zero = not ready for actions
        # Check 3: Uptime < 20 min as fallback if minerStatus unavailable
        if self.db.is_elevated_monitoring(miner_id):
            logger.debug("[%s] Post-restart grace — elevated monitoring active", miner_id)
            return None
        miner_status = miner.get("minerStatus")
        if miner_status is not None and miner_status != 0 and status == "online":
            logger.info("[%s] minerStatus=%s (not mining) — skipping actions", miner_id, miner_status)
            return None
        uptime_str = str(miner.get("uptime", "") or "")
        if uptime_str and status == "online":
            try:
                import re as _re
                uptime_secs = 0
                if uptime_str.isdigit():
                    uptime_secs = int(uptime_str)
                if 0 < uptime_secs < 1200:  # < 20 minutes fallback
                    logger.debug("[%s] Uptime %ss < 20min — skipping actions", miner_id, uptime_secs)
                    return None
            except Exception:
                pass
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
                # Count how many consecutive scans this miner has been in AMS SYNC state
                ams_sync_count = 0
                try:
                    with self.db._connect() as conn:
                        rows = conn.execute("""
                            SELECT issue FROM miner_readings
                            WHERE miner_id=? ORDER BY id DESC LIMIT 20
                        """, (miner_id,)).fetchall()
                        for row in rows:
                            if row["issue"] and "AMS SYNC" in str(row["issue"]):
                                ams_sync_count += 1
                            else:
                                break  # stop at first non-AMS-SYNC scan
                except Exception:
                    pass

                if ams_sync_count >= 10:
                    # Been in AMS SYNC state for 10+ scans — suppress from report
                    # This miner is reachable but AMS is persistently out of sync.
                    # Don't flood reports with it — let it resolve itself.
                    logger.debug(
                        "[%s] AMS SYNC suppressed — %d consecutive scans, miner is reachable",
                        miner_id, ams_sync_count
                    )
                    return None  # exclude from issues entirely

                logger.info(
                    "[%s] AMS reports offline but miner is reachable — %s (scan %d).",
                    miner_id, verify["status_detail"], ams_sync_count + 1
                )
                issues.append(
                    f"⚠️ AMS SYNC ({ams_sync_count+1} scans): Miner is ONLINE (verified) "
                    f"but AMS reports offline — check AMS"
                )
                action = "MONITOR"
                return self._build_issue(
                    miner, issues, action, pdu_action, power_watts,
                    power_source, power_kw, pdu_id, outlet_index,
                    hashrate_pct="N/A", tier="ams_sync",
                    tier_note="AMS offline but miner reachable",
                    chain_info=None,
                )
            else:
                logger.debug(
                    "[%s] AMS offline confirmed by direct check — %s",
                    miner_id, verify["status_detail"]
                )
                issues.append("OFFLINE")

                # ── Offline remediation decision tree ─────────────────────
                # Domain rules from operator:
                #   S19JPros have NO PDU access — restart → still offline → bad PSU ticket
                #   S21 Hydro/Imm MAY have PDU via AMS — restart → PDU cycle → ticket
                #   has_pdu = AMS reports a PDU outlet for this miner
                #
                offline_restarts   = self.db.get_failed_restart_count(miner_id, days=1)
                offline_pdu_cycles = self.db._count_pdu_cycles(miner_id, days=1)

                # OPERATOR RULE: Firmware restart requires network connectivity.
                # If miner is truly offline (unreachable), restart command can't reach it.
                # Go straight to PDU cycle (if available) or physical inspection.
                
                if has_pdu and offline_pdu_cycles == 0:
                    # Has PDU → power cycle is the correct first action for offline miner
                    action     = "PDU_CYCLE"
                    pdu_action = f"PDU {pdu_id} → Outlet {outlet_index}"
                    issues[-1] = (
                        "OFFLINE — miner unreachable. PDU power cycle recommended "
                        "(firmware restart won't work without power)"
                    )

                elif has_pdu and offline_pdu_cycles > 0:
                    # PDU cycle already tried → needs physical inspection
                    action = "PHYSICAL_INSPECTION"
                    issues[-1] = (
                        "OFFLINE — PDU cycle attempted but miner still offline. "
                        "Bad PSU, bad control board, or blown fuse — physical inspection required"
                    )

                else:
                    # No PDU access (S19JPros etc.) → can't recover remotely
                    action = "PHYSICAL_INSPECTION"
                    issues[-1] = (
                        "OFFLINE — no PDU access, cannot recover remotely. "
                        "Physical inspection required — likely bad PSU or control board"
                    )

                return self._build_issue(
                    miner, issues, action, pdu_action, power_watts,
                    power_source, power_kw, pdu_id, outlet_index,
                    hashrate_pct="0%", tier="offline",
                    tier_note="Miner offline — confirmed by direct check",
                    chain_info=None,
                )

        # ── HASHBOARD check (always evaluated when online) ───────────────
        chains     = miner.get("chains", []) or []
        # Bug fix: look up correct board count from specs — AH3880 has 2, not 3
        model_code = miner.get("model", "")
        expected_boards = self.specs.get_boards(model_code, fallback=3)
        chain_info = self._analyze_chains(chains, expected_boards=expected_boards)

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
                # ── Ticketed miners — never re-queue ─────────────────────
                # If this miner already has a ticket (known dead boards with
                # ticket_created set), suppress entirely. Don't add to issues,
                # don't set action, don't show in Slack. Ticket handles it.
                if self.db.has_known_dead_boards(miner_id):
                    logger.debug(
                        "[%s] Low hashrate suppressed — known dead board ticket already open",
                        miner_id
                    )
                    return None  # fully suppress — don't appear in report at all

                issues.append(
                    f"Hashrate {pct:.1f}% of rated "
                    f"({hashrate_ths:.1f} / {rated_ths:.0f} TH/s) "
                    f"[{tier}]"
                )
                # Only set RESTART if a dead board hasn't already claimed the action
                if action != "RESTART_CHECK_BOARDS":
                    # Escalation: 2+ failed restarts → ticket flow
                    # Also check outcome-labeled failures from Feature 1
                    failed_restarts = self.db.get_failed_restart_count(miner_id, days=7)
                    outcome_failures = self.db.count_outcome_failures(miner_id)
                    if failed_restarts >= 2 or outcome_failures >= 2:
                        action = "RESTART_CHECK_BOARDS"
                        issues.append(
                            f"⚠️ Escalated: {failed_restarts} restarts, "
                            f"{outcome_failures} FAILURE outcomes — ticket required"
                        )
                        logger.info(
                            "[%s] Escalating to RESTART_CHECK_BOARDS — restarts=%d outcomes=%d",
                            miner_id, failed_restarts, outcome_failures
                        )
                    else:
                        action = "RESTART"

        # ── TEMP check ───────────────────────────────────────────────────
        # Same thresholds regardless of cooling type.
        # Immersion miners are overclocked and run hotter than stock —
        # the same 76/86 limits apply across air, immersion, and hydro.
        if temp_chip is None:
            issues.append("⚠️ Sensor error — temp reading invalid")
        elif temp_chip >= 84:
            issues.append(f"🔴 RED — chip {temp_chip}°C (≥84°C, action required)")
            action = "TEMP_ACTION_REQUIRED"
        # OPERATOR RULE: No yellow tier. Liquid-cooled fleet runs 67-73°C normally.
        # Do not flag any miner below 84°C as warm/yellow/monitor.

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
    # NO TIME CAPS on the restart wait — logs are too important to miss
    # due to arbitrary timeouts. The only exits from _wait_for_stable are:
    # stable mining, emergency state, or miner removed from AMS by the
    # ticketing flow (after 5 consecutive polls where the miner disappears).

    REBOOT_POLL_FAST   = 15     # poll interval during phase 1 (seconds)
    REBOOT_POLL_SLOW   = 60     # poll interval during phase 2 (seconds) — per operator spec
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

        Bug fix (Apr 8 2026): signal.SIGALRM only works on the main thread of
        the main interpreter. When this function is called from a background
        thread (e.g. the post-restart capture spawned by execute_restart),
        signal.signal() raises ValueError immediately and we lose the entire
        capture. Fix: detect whether we are on the main thread and only use
        signal-based timeout in that case. Background threads rely on the
        underlying HTTP timeouts and collect_fresh_miner_logs's own
        max_wait_seconds parameter for bounded duration.
        """
        import signal
        import threading

        def _timeout_handler(signum, frame):
            raise TimeoutError("log collection timed out")

        wants_fresh = label.startswith("pre-") or label.startswith("post-")
        # Fresh-log path needs more time than cached collection
        timeout = 120 if wants_fresh else self.LOG_COLLECT_TIMEOUT

        on_main_thread = threading.current_thread() is threading.main_thread()
        signal_armed = False

        try:
            if on_main_thread and not wants_fresh:
                signal.signal(signal.SIGALRM, _timeout_handler)
                signal.alarm(timeout)
                signal_armed = True

            if wants_fresh:
                logger.info("[%s] Triggering FRESH log export for %s", miner_id, label)
                logs = self.ams.collect_fresh_miner_logs(int(miner_id))
            else:
                logs = self.ams.collect_miner_logs(int(miner_id))

            if signal_armed:
                signal.alarm(0)  # cancel alarm

            if logs:
                self.db.save_logs(miner_id, model, label, logs)
                logger.info("[%s] Logs collected (%s): %s files", miner_id, label, len(logs))
            else:
                logger.info("[%s] No logs available for %s — skipping", miner_id, label)
            return logs or {}
        except TimeoutError:
            if signal_armed:
                signal.alarm(0)
            logger.warning("[%s] Log collection timed out after %ss (%s) — continuing",
                           miner_id, timeout, label)
            return {}
        except Exception as e:
            if signal_armed:
                signal.alarm(0)
            logger.warning("[%s] Log collection failed (%s): %s — continuing", miner_id, label, e)
            return {}

    def _wait_for_stable(self, miner_id: str, ip: str) -> Optional[Dict]:
        """
        Two-phase state-based wait after a restart. NO TIME CAPS.

        Phase 1 — wait for AMS status == 'online'. Poll every REBOOT_POLL_FAST
                  seconds, forever, until the miner reports online OR
                  disappears from AMS entirely (sent to ticketing).

        Phase 2 — wait for stable mining state: common_status == 'mining' via
                  direct TCP port 4029 (primary) or AMS minerStatus == 0 AND
                  hashrate > 0 (fallback), on STABLE_CONFIRM consecutive polls.
                  Poll every REBOOT_POLL_SLOW seconds, forever, until stable,
                  emergency, or miner disappears from AMS.

        Rationale: logs are too important to miss due to arbitrary timeouts.
        Some miners take 45+ minutes to reach mining state after a restart
        and that is normal. We wait as long as it takes. The only ways out
        are: success (stable), emergency (escalate to ticket), or the miner
        is removed from AMS (handled upstream by the ticketing flow).

        Returns the stable miner dict on success, or None if the miner
        disappeared from AMS or entered emergency mode.
        """
        # ── Phase 1: wait for online ──────────────────────────────────────
        waited  = 0
        current = None
        logger.info("[%s] Phase 1 — waiting for status=online (no cap, polling every %ss)",
                    miner_id, self.REBOOT_POLL_FAST)
        consecutive_missing = 0
        while True:
            time.sleep(self.REBOOT_POLL_FAST)
            waited += self.REBOOT_POLL_FAST
            try:
                all_miners = self.ams.get_miners()
                current    = next(
                    (m for m in all_miners if str(m.get("id")) == str(miner_id)),
                    None
                )
                if current is None:
                    # Miner not in AMS list — could be momentary, could be
                    # that ticketing flow pulled it. Allow a few consecutive
                    # misses before giving up.
                    consecutive_missing += 1
                    if consecutive_missing >= 5:
                        logger.warning(
                            "[%s] Phase 1: miner not in AMS for %s consecutive polls — "
                            "likely pulled by ticketing flow, aborting wait",
                            miner_id, consecutive_missing
                        )
                        return None
                    logger.debug("[%s] Phase 1: miner missing from AMS (%s/5) at %ss",
                                 miner_id, consecutive_missing, waited)
                    continue
                consecutive_missing = 0
                if current.get("status") == "online":
                    logger.info("[%s] Phase 1 complete — online after %ss", miner_id, waited)
                    break
                logger.debug("[%s] Phase 1: still offline at %ss", miner_id, waited)
                # Periodic heartbeat at 10-minute marks so operators can see
                # the wait is still progressing on long-running restarts.
                if waited % 600 == 0:
                    logger.info("[%s] Phase 1: still waiting for online at %ss (no cap)",
                                miner_id, waited)
            except Exception as e:
                logger.warning("[%s] Phase 1 poll error at %ss: %s", miner_id, waited, e)

        # ── Phase 2: wait for stable mining state ────────────────────────
        # Primary signal: common_status == "mining" via TCP port 4029
        #   This is the authoritative device state from BiXBiT firmware.
        #   States like "starting", "auto-tuning", "initializing" mean not ready.
        #   "emergency" means escalate immediately.
        # Fallback signal: AMS minerStatus == 0 AND hashrate > 0
        #   Used when direct TCP is not available (e.g. different network segment).
        # We require STABLE_CONFIRM consecutive passing polls either way.
        # NO TIME CAP — wait as long as it takes.
        stable_count = 0
        waited2      = 0
        logger.info("[%s] Phase 2 — waiting for stable mining state (no cap, polling every %ss, need %s consecutive)",
                    miner_id, self.REBOOT_POLL_SLOW, self.STABLE_CONFIRM)
        consecutive_missing = 0
        while True:
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
                    return current  # exit, board comparison will escalate to ticket

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
                        # Miner disappeared from AMS — could be momentary,
                        # could be ticketing flow. Allow a few consecutive
                        # misses before giving up.
                        consecutive_missing += 1
                        if consecutive_missing >= 5:
                            logger.warning(
                                "[%s] Phase 2: miner not in AMS for %s consecutive polls — "
                                "likely pulled by ticketing flow, aborting wait",
                                miner_id, consecutive_missing
                            )
                            return None
                        stable_count = 0
                        continue
                    consecutive_missing = 0
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
                    # Periodic heartbeat at 10-minute marks so operators can
                    # see the wait is still progressing on long-running tunes.
                    if waited2 % 600 == 0:
                        logger.info("[%s] Phase 2: still waiting for stable mining at %ss (%s)",
                                    miner_id, waited2, status_source)
            except Exception as e:
                logger.warning("[%s] Phase 2 poll error at %ss: %s", miner_id, waited2, e)
                stable_count = 0

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

        # Bug fix: respect dry_run in the dead-board path too
        if self.config.dry_run:
            logger.info("[%s] DRY RUN — dead-board restart skipped (set dry_run: false to enable)", miner_id)
            return

        try:
            self.ams.reboot_miner([miner_id])
            self.db.record_restart(
                miner_id, ip, model,
                f"Dead board restart — boards {dead_idx} offline before restart",
                hashrate_before=float(issue.get("hashrate_pct") or 0)
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
        post_miner = self._wait_for_stable(miner_id, ip)

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
        post_info      = self._analyze_chains(post_chains, expected_boards=chain_info.get("expected_boards", 3))
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
                self.slack.post_to_alerts_channel(msg)
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
                self.slack.post_to_alerts_channel(msg)
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

    def _auto_create_missing_tickets(self, miners: list) -> None:
        """
        Scan-level ticket creation for miners that have accumulated 3+ FAILURE
        outcomes but never had an AMS ticket created — this handles the case where
        miners kept getting plain RESTART approvals instead of RESTART_CHECK_BOARDS,
        bypassing the normal ticket creation flow in execute_board_restart().

        Runs every scan. Only creates a ticket once — marks ticket_created so it
        won't repeat. Suppresses the miner from future reports automatically.
        """
        # Trigger on 3+ FAILURE outcomes OR 2+ restarts that escalated to RESTART_CHECK_BOARDS
        FAILURE_THRESHOLD = 3
        ESCALATION_THRESHOLD = 1  # even 1 dead board restart = needs inspection

        with self.db._connect() as conn:
            # Find miners with enough failures and no ticket
            # Two paths:
            # 1. 3+ FAILURE outcomes (confirmed bad)
            # 2. 2+ total restarts escalated to RESTART_CHECK_BOARDS (oscillating pattern)
            # Don't count failures from restarts in the last 30 minutes (miner may still be booting)
            candidates_failures = conn.execute("""
                SELECT miner_id, ip, model,
                       COUNT(*) as failure_count, 'failure_outcomes' as reason
                FROM miner_restarts
                WHERE outcome = 'FAILURE'
                  AND restarted_at < datetime('now', '-30 minutes')
                GROUP BY miner_id
                HAVING failure_count >= ?
            """, (FAILURE_THRESHOLD,)).fetchall()

            candidates_escalated = conn.execute("""
                SELECT miner_id, ip, model,
                       COUNT(*) as failure_count, 'escalated_restarts' as reason
                FROM miner_restarts
                WHERE restart_type LIKE '%Dead board%'
                   OR restart_type LIKE '%board%'
                GROUP BY miner_id
                HAVING failure_count >= ?
            """, (ESCALATION_THRESHOLD,)).fetchall()

            # Path 3: miners currently pending RESTART_CHECK_BOARDS approval
            candidates_pending = conn.execute("""
                SELECT DISTINCT miner_id, ip, model,
                       1 as failure_count, 'pending_board_check' as reason
                FROM pending_approvals
                WHERE action_type = 'RESTART_CHECK_BOARDS'
                  AND status = 'PENDING'
            """).fetchall()

            # Path 4: offline miners stuck in PHYSICAL_CYCLE for 3+ consecutive scans
            # These are miners where restart was tried, no PDU, needs bad PSU ticket
            candidates_offline = conn.execute("""
                SELECT miner_id, ip, model,
                       COUNT(*) as failure_count, 'offline_no_pdu' as reason
                FROM miner_readings
                WHERE action = 'PHYSICAL_CYCLE'
                  AND status = 'offline'
                  AND scan_id IN (SELECT id FROM scans ORDER BY id DESC LIMIT 10)
                GROUP BY miner_id
                HAVING failure_count >= 3
            """).fetchall()

            # Merge all paths, dedup by miner_id
            seen = set()
            candidates = []
            for c in (list(candidates_failures) + list(candidates_escalated) +
                      list(candidates_pending) + list(candidates_offline)):
                if c["miner_id"] not in seen:
                    seen.add(c["miner_id"])
                    candidates.append(c)

        logger.info(
            "Auto-ticket check: %d candidates (%d failure + %d escalated + %d pending board check + %d offline no-pdu)",
            len(candidates), len(candidates_failures),
            len(candidates_escalated), len(candidates_pending), len(candidates_offline)
        )
        for c in candidates:
            miner_id = str(c["miner_id"])
            ip       = c["ip"]
            model    = c["model"]
            failures = c["failure_count"]

            # Skip if already in known_dead_boards with a ticket
            with self.db._connect() as conn:
                existing = conn.execute("""
                    SELECT ticket_created FROM known_dead_boards
                    WHERE miner_id=? AND resolved_at IS NULL
                """, (miner_id,)).fetchone()

            if existing and existing["ticket_created"]:
                continue  # already has a ticket

            # Create the AMS ticket with diagnostic context
            reason_str = c["reason"] if "reason" in c.keys() else "persistent_failure"
            if reason_str == "offline_no_pdu":
                title = f"Offline — bad PSU suspected — {model} @ {ip}"
                description = (
                    f"Miner: {miner_id} ({model})\nIP: {ip}\n"
                    f"Issue: Miner offline, firmware restart attempted, no PDU access to power cycle.\n"
                    f"Likely cause: Bad PSU — miner cannot restart itself.\n"
                    f"Action: Physical inspection — check PSU, power connections, fuses.\n"
                    f"Note: S19JPros have no PDU outlet; PSU replacement most common fix."
                )
            elif reason_str == "pending_board_check":
                title = f"Dead hashboards — {model} @ {ip} (physical inspection required)"
                description = (
                    f"Miner: {miner_id} ({model})\nIP: {ip}\n"
                    f"Issue: Hashboards not recovering after restart attempts.\n"
                    f"Likely cause: Dead hashboard(s) — needs physical inspection and board replacement.\n"
                    f"Action: Check each board, test with known-good board if available."
                )
            elif reason_str == "escalated_restarts":
                title = f"Persistent hashrate failure — {model} @ {ip} (dead boards)"
                description = (
                    f"Miner: {miner_id} ({model})\nIP: {ip}\n"
                    f"Board check restarts: {failures}\n"
                    f"Likely cause: Dead hashboard(s) that restart cannot fix.\n"
                    f"Action: Physical board inspection and replacement required."
                )
            else:
                title = f"Persistent FAILURE outcomes — {model} @ {ip} ({failures} restarts)"
                description = (
                    f"Miner: {miner_id} ({model})\nIP: {ip}\n"
                    f"Failed restarts: {failures}\n"
                    f"Outcome: Every restart attempt returned FAILURE — miner not recovering.\n"
                    f"Possible causes: Dead hashboard, bad PSU, bad control board.\n"
                    f"Action: Physical inspection required."
                )
            try:
                ticket = self.ams.create_ticket(
                    title=title,
                    description=description,
                    priority="high",
                    miner_ids=[int(miner_id)]
                )
                ticket_id = str(ticket.get("id", "unknown"))
                logger.info(
                    "[%s] Auto-ticket created: #%s (%d failures)",
                    ip, ticket_id, failures
                )
                # Register in known_dead_boards so miner is suppressed
                if not existing:
                    self.db.register_dead_boards(
                        miner_id, ip, model,
                        board_indices=[], restart_result="failed"
                    )
                self.db.mark_ticket_created(miner_id, ticket_id)

                # Slack notification
                try:
                    self.slack.post_to_alerts_channel(
                        f"🎫 *Auto-ticket created: #{ticket_id}*\n"
                        f"  `{ip}` ({model}) — {failures} FAILURE outcomes, "
                        f"no recovery after repeated restarts.\n"
                        f"  Miner removed from reports. Physical inspection required."
                    )
                except Exception:
                    pass

            except Exception as e:
                logger.error("[%s] Auto-ticket creation failed: %s", ip, e)

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
                priority="high",
                miner_ids=[int(miner_id)]
            )
            ticket_id = ticket.get("id", "unknown")
            logger.info("[%s] AMS ticket created: %s", miner_id, ticket_id)
            # Mark ticket created so this miner is suppressed from future Slack reports
            self.db.register_dead_boards(miner_id, ip, model, dead_idx, restart_result="failed")
            self.db.mark_ticket_created(miner_id, str(ticket_id))
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
        self.db.record_restart(miner_id, ip, model, reason,
                               hashrate_before=float(issue.get("hashrate_pct") or 0))

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
            self.slack.post_to_alerts_channel(slack_msg)
        except Exception as e:
            logger.warning("[%s] Slack escalation alert failed: %s", miner_id, e)

        logger.info(
            "[%s] Escalated — dead boards %s, ticket #%s, Slack notified",
            miner_id, dead_idx, ticket_id
        )

    # ── Execute approved actions ──────────────────────────────

    def execute_restart(self, issue: Dict[str, Any]) -> None:
        """
        Execute an approved firmware restart with pre AND post log collection.

        Flow:
          1. Capture FRESH pre-restart logs (blocks up to 120s)
          2. Restart miner via AMS
          3. Spawn background thread that waits ~75s for the miner to come
             back online, then captures FRESH post-restart logs
          4. Record action to audit log

        Both pre and post logs are stored with distinct labels in miner_logs
        so the LLM can compare them when learning whether the restart actually
        helped. The background thread is fire-and-forget — failures there do
        not block this method or affect the main daemon loop.

        Called when operator approves a RESTART action OR overnight automation
        auto-approves it.
        """
        miner_id = issue["id"]
        ip       = issue["ip"]
        model    = issue["model"]

        logger.info("[%s] Executing approved firmware restart for %s @ %s", miner_id, model, ip)

        # Bug fix: respect dry_run — log intent but do not touch AMS
        if self.config.dry_run:
            logger.info("[%s] DRY RUN — firmware restart skipped (set dry_run: false to enable)", miner_id)
            return

        # Step 1 — collect FRESH pre-restart logs
        self._collect_logs_nonblocking(miner_id, model, "pre-restart")

        # Step 2 — restart via AMS
        try:
            self.ams.reboot_miner([miner_id])
            logger.info("[%s] Firmware restart sent via AMS", miner_id)
            self.db.record_restart(miner_id, ip, model, restart_type="MANUAL_APPROVED",
                                   hashrate_before=float(issue.get("hashrate_pct") or 0))
        except Exception as e:
            logger.error("[%s] Firmware restart failed: %s", miner_id, e)
            return

        # Step 3 — spawn background thread for post-restart log capture.
        # OPERATOR RULE (Bobby, Apr 8 2026): NO maximum wait time. Bobby has
        # seen miners take 5-6 HOURS to reach fully-mining-with-settled-hashrate
        # state. The number one goal is capturing the log AT THE RIGHT MOMENT
        # (not capturing it quickly). Settled hashrate detection: track the
        # last 4 hashrate readings; the miner is "settled" when the standard
        # deviation of those 4 readings is within 5% of their mean.
        # Fire-and-forget daemon thread; failures are logged but do not raise.
        # If the parent process exits before the capture completes, the daemon
        # thread is killed and we accept the post-capture gap for that one
        # action (the action itself is already in the audit log).
        def _post_restart_capture():
            import time as _time
            from collections import deque
            try:
                # Wait 60s before first poll — even reaching AMS takes time
                _time.sleep(60)

                poll_interval_seconds = 60
                history_size = 4
                settled_tolerance_pct = 5.0
                hashrate_history = deque(maxlen=history_size)
                poll_num = 0
                start_time = _time.time()

                while True:  # NO maximum — wait as long as it takes
                    poll_num += 1
                    try:
                        all_miners = self.ams.get_miners()
                        current = next(
                            (m for m in all_miners if str(m.get("id")) == str(miner_id)),
                            None
                        )
                        if current is None:
                            logger.info("[%s] Post-restart poll %d: miner not in fleet list yet",
                                        miner_id, poll_num)
                            hashrate_history.clear()
                        else:
                            status        = current.get("status", "?")
                            miner_status  = current.get("minerStatus", -1)
                            hashrate      = current.get("hashrate", 0) or 0
                            is_mining = (status == "online" and miner_status == 0 and hashrate > 0)

                            if is_mining:
                                hashrate_history.append(float(hashrate))
                                if len(hashrate_history) == history_size:
                                    mean_hr = sum(hashrate_history) / len(hashrate_history)
                                    if mean_hr > 0:
                                        variance = sum((h - mean_hr) ** 2 for h in hashrate_history) / len(hashrate_history)
                                        stddev = variance ** 0.5
                                        stddev_pct = (stddev / mean_hr) * 100
                                        is_settled = stddev_pct < settled_tolerance_pct
                                        elapsed_min = (_time.time() - start_time) / 60
                                        logger.info("[%s] Post-restart poll %d (%.1f min): mining=True hashrate=%.1f mean=%.1f stddev=%.2f%% settled=%s",
                                                    miner_id, poll_num, elapsed_min, hashrate, mean_hr, stddev_pct, is_settled)
                                        if is_settled:
                                            logger.info("[%s] Miner is fully mining with SETTLED hashrate after %.1f min — capturing post-restart logs",
                                                        miner_id, elapsed_min)
                                            self._collect_logs_nonblocking(miner_id, model, "post-restart")
                                            # Wire LLM pre/post comparison — runs against local Qwen,
                                            # stores result in knowledge.json, posts to Slack
                                            self._run_post_action_log_comparison(
                                                miner_id, ip, model, "restart"
                                            )
                                            return
                                    else:
                                        hashrate_history.clear()
                                else:
                                    elapsed_min = (_time.time() - start_time) / 60
                                    logger.info("[%s] Post-restart poll %d (%.1f min): mining=True hashrate=%.1f (building history %d/%d)",
                                                miner_id, poll_num, elapsed_min, hashrate, len(hashrate_history), history_size)
                            else:
                                elapsed_min = (_time.time() - start_time) / 60
                                logger.info("[%s] Post-restart poll %d (%.1f min): status=%s minerStatus=%s hashrate=%s — not yet mining",
                                            miner_id, poll_num, elapsed_min, status, miner_status, hashrate)
                                hashrate_history.clear()
                    except Exception as poll_e:
                        logger.warning("[%s] Post-restart poll %d failed: %s", miner_id, poll_num, poll_e)
                        hashrate_history.clear()

                    _time.sleep(poll_interval_seconds)
            except Exception as e:
                logger.warning("[%s] Post-restart log capture thread failed: %s", miner_id, e)

        t = threading.Thread(target=_post_restart_capture, daemon=True,
                             name=f"post-restart-{miner_id}")
        t.start()
        logger.info("[%s] Post-restart log capture scheduled (background, polls until hashrate is fully settled — NO max wait)",
                    miner_id)

    def _run_post_action_log_comparison(self, miner_id: str, ip: str,
                                         model: str, action_label: str) -> None:
        """Compare the most recent pre/post log pair for a miner via local LLM.

        Called from the background polling thread after a successful
        post-action fresh log capture lands in the DB. Fetches the most
        recent pre and post miner.log content for the given action_label
        ('restart' or 'pdu-cycle'), passes them to the local LLM analyzer,
        stores the analysis in knowledge.json, and posts a summary to Slack.

        action_label maps to health_status:
            'restart'    -> ('pre-restart',    'post-restart')
            'pdu-cycle'  -> ('pre-pdu-cycle',  'post-pdu-cycle')

        NEVER raises. All errors logged and swallowed because this is a
        non-critical analysis step that runs in a background thread and
        must not affect the main remediation flow.
        """
        pre_label, post_label = {
            'restart':   ('pre-restart',   'post-restart'),
            'pdu-cycle': ('pre-pdu-cycle', 'post-pdu-cycle'),
        }.get(action_label, (None, None))
        if not pre_label:
            logger.warning("[%s] Unknown action_label %r — skipping LLM comparison",
                           miner_id, action_label)
            return

        try:
            # Fetch the most recent pre and post miner.log content. We only
            # care about miner.log here because it has the structured DVFS,
            # PSU, chip, and event data the LLM uses. power.log and
            # autotune.log are usually empty in our captures anyway.
            with self.db._connect() as conn:
                pre_row = conn.execute(
                    "SELECT content, datetime(collected_at) FROM miner_logs "
                    "WHERE miner_id=? AND health_status=? AND log_file LIKE ?"
                    " ORDER BY collected_at DESC LIMIT 1",
                    (miner_id, pre_label, '%miner.log')
                ).fetchone()
                post_row = conn.execute(
                    "SELECT content, datetime(collected_at) FROM miner_logs "
                    "WHERE miner_id=? AND health_status=? AND log_file LIKE ?"
                    " ORDER BY collected_at DESC LIMIT 1",
                    (miner_id, post_label, '%miner.log')
                ).fetchone()

            if not pre_row or not post_row:
                logger.info("[%s] Skipping LLM log comparison — pre or post miner.log missing (pre=%s post=%s)",
                            miner_id, bool(pre_row), bool(post_row))
                return

            pre_log  = pre_row['content'] or ""
            post_log = post_row['content'] or ""
            if not pre_log or not post_log:
                logger.info("[%s] Skipping LLM log comparison — pre or post log content empty",
                            miner_id)
                return

            logger.info("[%s] Running DUAL-MODEL log comparison: pre=%s bytes, post=%s bytes",
                        miner_id, len(pre_log), len(post_log))

            # Import both models. Either may be missing — handle each
            # independently so a single import error doesn't lose the other
            # model's analysis.
            import sys as _sys
            from pathlib import Path as _Path
            _ai = str(_Path(__file__).resolve().parent.parent / "ai")
            if _ai not in _sys.path:
                _sys.path.insert(0, _ai)

            qwen_available = False
            claude_available = False
            try:
                from llm_scan_hook import run_log_comparison_llm
                qwen_available = True
            except ImportError as ie:
                logger.warning("[%s] Qwen log comparison module unavailable: %s", miner_id, ie)
            try:
                import claude_log_comparison
                claude_available = claude_log_comparison.is_available()
                if not claude_available:
                    logger.warning("[%s] Claude API key not configured — Claude comparison disabled", miner_id)
            except ImportError as ie:
                logger.warning("[%s] Claude log comparison module unavailable: %s", miner_id, ie)

            if not qwen_available and not claude_available:
                logger.warning("[%s] Neither Qwen nor Claude log comparison available — skipping", miner_id)
                return

            miner_info = {
                "ip":     ip,
                "model":  model,
                "action": action_label,
                "pre_collected_at":  pre_row[1],
                "post_collected_at": post_row[1],
                "pre_log_size":      len(pre_log),
                "post_log_size":     len(post_log),
            }

            qwen_analysis = None
            claude_analysis = None

            # Run Qwen first (fast, free, local — usually returns in 25-90s)
            if qwen_available:
                try:
                    logger.info("[%s] Running Qwen 2.5 32B comparison...", miner_id)
                    qwen_analysis = run_log_comparison_llm(
                        miner_id=miner_id,
                        pre_log=pre_log,
                        post_log=post_log,
                        miner_info=miner_info,
                        slack_client=None,  # we'll post a unified message below
                    )
                    if qwen_analysis:
                        logger.info("[%s] Qwen comparison complete (%s chars)", miner_id, len(qwen_analysis))
                    else:
                        logger.info("[%s] Qwen comparison returned no analysis", miner_id)
                except Exception as qe:
                    logger.warning("[%s] Qwen comparison failed: %s", miner_id, qe)

            # Run Claude in parallel-ish (sequential because we want to compare
            # outputs side by side, and Claude is faster anyway — usually 8-15s)
            if claude_available:
                try:
                    logger.info("[%s] Running Claude Sonnet 4.6 comparison...", miner_id)
                    claude_analysis = claude_log_comparison.compare_logs_via_claude(
                        miner_id=miner_id,
                        pre_log=pre_log,
                        post_log=post_log,
                        miner_info=miner_info,
                    )
                    if claude_analysis:
                        logger.info("[%s] Claude comparison complete (%s chars)", miner_id, len(claude_analysis))
                    else:
                        logger.info("[%s] Claude comparison returned no analysis", miner_id)
                except Exception as ce:
                    logger.warning("[%s] Claude comparison failed: %s", miner_id, ce)

            if not qwen_analysis and not claude_analysis:
                logger.info("[%s] Both models returned no analysis", miner_id)
                return

            # Store BOTH analyses in knowledge.json with distinct miner_ids so
            # they can be retrieved separately and compared.
            try:
                from knowledge_manager import KnowledgeManager
                km = KnowledgeManager()
                if qwen_analysis:
                    km.add_llm_insight(
                        qwen_analysis,
                        miner_id=f"compare:{action_label}:qwen:{miner_id}",
                    )
                if claude_analysis:
                    km.add_llm_insight(
                        claude_analysis,
                        miner_id=f"compare:{action_label}:claude:{miner_id}",
                    )
                logger.info("[%s] Dual-model comparisons stored in knowledge.json", miner_id)
            except Exception as ke:
                logger.warning("[%s] Failed to store comparisons in knowledge.json: %s",
                               miner_id, ke)

            # Post a unified side-by-side message to Slack alerts channel.
            # Operator can see both models' verdicts and learn the differences.
            try:
                if hasattr(self, "slack") and self.slack:
                    NL = chr(10)
                    msg_parts = [
                        f"🔍 *Pre/Post Log Comparison — `{ip}` ({model})*",
                        f"Action: {action_label} | id: {miner_id}",
                        f"Pre: {len(pre_log):,} bytes  |  Post: {len(post_log):,} bytes",
                        "",
                    ]
                    if qwen_analysis:
                        q = qwen_analysis[:1500]
                        msg_parts.append(f"*🧠 Local Qwen 2.5 32B:*{NL}```{NL}{q}{NL}```")
                    else:
                        msg_parts.append("*🧠 Local Qwen 2.5 32B:* _(no analysis returned)_")
                    msg_parts.append("")
                    if claude_analysis:
                        c = claude_analysis[:1500]
                        msg_parts.append(f"*🤖 Claude Sonnet 4.6:*{NL}```{NL}{c}{NL}```")
                    else:
                        msg_parts.append("*🤖 Claude Sonnet 4.6:* _(no analysis returned)_")
                    full_msg = NL.join(msg_parts)
                    self.slack.post_to_logs(full_msg)
                    logger.info("[%s] Dual-model comparison posted to #mg-logs", miner_id)
            except Exception as se:
                logger.warning("[%s] Failed to post dual-model comparison to Slack: %s",
                               miner_id, se)

        except Exception as e:
            logger.warning("[%s] Post-action dual-model comparison failed (non-fatal): %s",
                           miner_id, e)

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

        # Bug fix: respect dry_run — log intent but do not touch AMS or PDU
        if self.config.dry_run:
            logger.info("[%s] DRY RUN — PDU cycle skipped (set dry_run: false to enable)", miner_id)
            return

        # Step 1 — collect FRESH pre-pdu-cycle logs
        self._collect_logs_nonblocking(miner_id, model, "pre-pdu-cycle")

        # Step 2 — power cycle via AMS
        import time
        try:
            self.ams.pdu_power_cycle(pdu_id, outlet)
            logger.info("[%s] PDU %s outlet %s — power cycled", miner_id, pdu_id, outlet)
        except Exception as e:
            logger.error("[%s] PDU cycle failed: %s", miner_id, e)
            return

        # Step 3 — wait 90 seconds for the miner to come back online enough
        # to do basic TCP-level verification. The fresh post-pdu-cycle log
        # capture happens in the background once the miner is fully mining
        # with settled hashrate (see step 5).
        logger.info("[%s] Waiting 90s for miner to recover after PDU cycle...", miner_id)
        time.sleep(90)

        # Step 4 — re-verify miner status (TCP-level check)
        from miner_verify import verify_miner_online
        result = verify_miner_online(ip)

        # Step 5 — spawn background thread for FRESH post-pdu-cycle log capture.
        # OPERATOR RULE (Bobby, Apr 8 2026): NO maximum wait. Wait as long as
        # it takes for the miner to be fully mining with settled hashrate.
        # Bobby has seen this take 5-6 hours.
        if result.get("actually_online"):
            def _post_pdu_capture():
                import time as _time
                from collections import deque
                try:
                    _time.sleep(60)  # extra cushion before first poll

                    poll_interval_seconds = 60
                    history_size = 4
                    settled_tolerance_pct = 5.0
                    hashrate_history = deque(maxlen=history_size)
                    poll_num = 0
                    start_time = _time.time()

                    while True:  # NO maximum
                        poll_num += 1
                        try:
                            all_miners = self.ams.get_miners()
                            current = next(
                                (m for m in all_miners if str(m.get("id")) == str(miner_id)),
                                None
                            )
                            if current is None:
                                logger.info("[%s] Post-PDU poll %d: miner not in fleet list yet",
                                            miner_id, poll_num)
                                hashrate_history.clear()
                            else:
                                status        = current.get("status", "?")
                                miner_status  = current.get("minerStatus", -1)
                                hashrate      = current.get("hashrate", 0) or 0
                                is_mining = (status == "online" and miner_status == 0 and hashrate > 0)

                                if is_mining:
                                    hashrate_history.append(float(hashrate))
                                    if len(hashrate_history) == history_size:
                                        mean_hr = sum(hashrate_history) / len(hashrate_history)
                                        if mean_hr > 0:
                                            variance = sum((h - mean_hr) ** 2 for h in hashrate_history) / len(hashrate_history)
                                            stddev = variance ** 0.5
                                            stddev_pct = (stddev / mean_hr) * 100
                                            is_settled = stddev_pct < settled_tolerance_pct
                                            elapsed_min = (_time.time() - start_time) / 60
                                            logger.info("[%s] Post-PDU poll %d (%.1f min): mining=True hashrate=%.1f mean=%.1f stddev=%.2f%% settled=%s",
                                                        miner_id, poll_num, elapsed_min, hashrate, mean_hr, stddev_pct, is_settled)
                                            if is_settled:
                                                logger.info("[%s] Miner is fully mining with SETTLED hashrate after %.1f min — capturing post-pdu-cycle logs",
                                                            miner_id, elapsed_min)
                                                self._collect_logs_nonblocking(miner_id, model, "post-pdu-cycle")
                                                # Wire LLM pre/post comparison
                                                self._run_post_action_log_comparison(
                                                    miner_id, ip, model, "pdu-cycle"
                                                )
                                                return
                                        else:
                                            hashrate_history.clear()
                                    else:
                                        elapsed_min = (_time.time() - start_time) / 60
                                        logger.info("[%s] Post-PDU poll %d (%.1f min): mining=True hashrate=%.1f (building history %d/%d)",
                                                    miner_id, poll_num, elapsed_min, hashrate, len(hashrate_history), history_size)
                                else:
                                    elapsed_min = (_time.time() - start_time) / 60
                                    logger.info("[%s] Post-PDU poll %d (%.1f min): status=%s minerStatus=%s hashrate=%s — not yet mining",
                                                miner_id, poll_num, elapsed_min, status, miner_status, hashrate)
                                    hashrate_history.clear()
                        except Exception as poll_e:
                            logger.warning("[%s] Post-PDU poll %d failed: %s", miner_id, poll_num, poll_e)
                            hashrate_history.clear()

                        _time.sleep(poll_interval_seconds)
                except Exception as e:
                    logger.warning("[%s] Post-PDU log capture thread failed: %s", miner_id, e)

            t = threading.Thread(target=_post_pdu_capture, daemon=True,
                                 name=f"post-pdu-{miner_id}")
            t.start()
            logger.info("[%s] Post-PDU log capture scheduled (background, polls until settled — NO max wait)",
                        miner_id)
        else:
            logger.info("[%s] Skipping post-PDU log capture — miner did not come back online", miner_id)
        self.db.log_action(
            miner_id, ip, model,
            problem="Offline — PDU cycle executed",
            action_taken="PDU_CYCLE",
            decision="APPROVED",
            notes=f"Post-cycle check: {'ONLINE' if result['actually_online'] else 'STILL OFFLINE'}"
        )

        if not result["actually_online"]:
            # Still offline after PDU cycle — bad PSU or control board
            logger.warning(
                "[%s] Still offline after PDU cycle — likely bad PSU or control board",
                miner_id
            )
            # Create AMS ticket
            try:
                ticket = self.ams.create_ticket(
                    title=f"Offline after PDU cycle — {model} @ {ip} (bad PSU / control board)",
                    description=(
                        f"Miner: {miner_id} ({model})\n"
                        f"IP: {ip}\n"
                        f"Steps taken: Firmware restart attempted → PDU power cycle (off 10s, on)\n"
                        f"Result: Miner still offline after PDU cycle.\n"
                        f"Likely cause: Bad PSU, bad control board, blown fuse, or physical fault.\n"
                        f"Action required: Physical inspection — check PSU, control board, fuses."
                    ),
                    priority="high",
                    miner_ids=[int(miner_id)]
                )
                ticket_id = str(ticket.get("id", "unknown"))
                logger.info("[%s] Auto-ticket created after PDU failure: #%s", ip, ticket_id)

                # Register in known_dead_boards to suppress from future reports
                self.db.register_dead_boards(miner_id, ip, model, [], restart_result="pdu_failed")
                self.db.mark_ticket_created(miner_id, ticket_id)

                # Slack alert
                try:
                    self.slack.post_to_alerts_channel(
                        f"🔴 *Offline after PDU cycle — physical inspection required*\n"
                        f"  `{ip}` ({model})\n"
                        f"  Ticket #{ticket_id} created.\n"
                        f"  Likely: bad PSU, bad control board, or blown fuse.\n"
                        f"  Miner removed from reports until ticket resolved."
                    )
                except Exception:
                    pass
            except Exception as e:
                logger.error("[%s] Failed to create post-PDU ticket: %s", ip, e)
        else:
            logger.info("[%s] Back online after PDU cycle — power issue resolved", miner_id)

    # ── Report printer ────────────────────────────────────────

    @staticmethod
    def _print_report(miners: List[Dict], issues: List[Dict],
                      wx: Optional[Dict] = None,
                      ams_notifs: Optional[List[Dict]] = None,
                      facility=None,
                      hvac=None,
                      dry_run: bool = False) -> None:
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
        print(f"  {'[DRY RUN — no actions taken]' if dry_run else '[LIVE — actions will execute]'}")

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
        """Daily baseline log collection for every online miner.

        Design (per operator spec):
          * Every online miner gets ONE fresh log export per 24 hours.
          * No flagged-vs-healthy split — everyone gets the same treatment.
          * Uses collect_fresh_miner_logs (trigger + wait + download), not
            the existing-only path, so miners whose AMS export queue is
            empty still get a fresh log pulled.
          * No time cap on the fresh export wait — logs are too important
            to miss due to timing ("as long as it takes").
          * Runs in a background thread so the scan loop never blocks
            waiting for slow exports.
          * Pre/post restart logs are collected separately by the
            execute_board_restart() / execute_restart() flows — this
            function only handles the daily baseline.

        Log content is kept for 30 days then purged. Hardware identity
        parsed from miner.log is permanent and never purged.
        """
        if not self.config.collect_logs:
            logger.debug("Log collection disabled — set collect_logs: true in config to enable")
            return

        # Guard: if a previous background collection is still running, don't
        # spawn another one on top of it. The per-miner dedup (24h interval
        # check inside the thread) would handle it safely, but skipping the
        # whole thread avoids log spam and double AMS sessions.
        existing = getattr(self, '_daily_log_thread', None)
        if existing is not None and existing.is_alive():
            logger.info("Daily log collection: previous background thread still running, skipping this scan cycle")
            return

        # Snapshot the miner list — the thread runs in the background while
        # the main scan loop continues, so we hand it a copy of the data
        # it needs rather than sharing mutable state.
        eligible = []
        for miner in miners:
            status = miner.get("status", "unknown")
            if status == "offline":
                continue
            # Skip miners that aren't fully mining yet — don't download during
            # initializing (6), starting, or auto-tuning (3). Wait for mining (0).
            miner_status_val = miner.get("minerStatus")
            if miner_status_val is not None and miner_status_val != 0:
                continue

            # Resolve display model name the same way the old code did —
            # prefer shortModel, fall back to name, override with name if the
            # currentProfile string contains TH/s (BiXBiT firmware convention).
            model     = miner.get("shortModel", miner.get("name", "unknown"))
            profile_s = miner.get("currentProfile", "")
            if "TH/s" in profile_s and miner.get("name") and miner.get("name") != model:
                model = miner["name"]

            eligible.append({
                "id":    str(miner.get("id", "")),
                "model": model,
            })

        if not eligible:
            logger.debug("Daily log collection: no eligible miners this scan")
            return

        logger.info("Daily log collection: spawning background thread for %d eligible miners", len(eligible))

        def _daily_baseline_worker(miner_list):
            """Background worker — pull one fresh log per miner, PARALLEL (15 workers).

            Concurrency rationale (per operator April 9 2026):
              - BiXBiT owns AMS so rate limiting is not a concern
              - The constraint is the REST connection pool and socket capacity
              - 15 concurrent is a conservative starting point, tune from there
              - Each worker still has its own 10-minute per-miner cap inside
                collect_fresh_miner_logs, so one stuck miner cannot starve
                any other miner — it just burns its own 10 minutes while
                everyone else finishes normally

            Thread safety:
              - AMS REST calls use requests.Session (thread-safe for concurrent POSTs)
              - Database writes use per-call sqlite3 connections with WAL mode
                (thread-safe; see _connect at line 1396)
              - Token is refreshed ONCE before spawning the pool (below) to
                avoid a potential race inside _ensure_token if the token
                expires mid-run. After that all threads read the cached
                token without mutation.
            """
            import concurrent.futures
            # DAILY_INTERVAL_SECONDS removed — every miner gets fresh logs every day
            DAILY_PARALLEL_WORKERS = 15

            # Force a fresh token BEFORE spawning parallel workers to avoid
            # a race on _ensure_token if the current token is near expiry.
            try:
                self.ams._ensure_token()
                logger.info("Daily log: token refreshed before parallel sweep")
            except Exception as e:
                logger.warning("Daily log: pre-sweep token refresh failed: %s — workers will retry", e)

            # Counters — mutated by worker callbacks, guarded by a lock
            # because Python threading with CPython GIL is NOT guaranteed
            # to make += on integers atomic in all interpreter versions.
            counter_lock = _threading.Lock()
            counters = {"collected": 0, "skipped_recent": 0, "failed": 0}
            failed_miners = []  # Track failed miners for retry pass

            def _collect_one(entry):
                """Collect logs for one miner — runs inside a pool worker thread."""
                miner_id = entry["id"]
                model    = entry["model"]
                if not miner_id:
                    return

                # OPERATOR RULE (April 11 2026): Every miner gets fresh logs EVERY day.
                # No 24h dedup — fresh logs are critical for AI learning.
                # Pre/post restart logs are separate; this is the daily baseline.

                # Trigger a fresh export and wait
                try:
                    logger.info("Daily log: pulling fresh export for miner %s (%s)", miner_id, model)
                    # 10-minute per-miner cap. Still applies in the parallel
                    # path because even with parallelism, we do not want a
                    # single truly-broken miner to hold any worker slot
                    # open indefinitely.
                    log_files = self.ams.collect_fresh_miner_logs(
                        int(miner_id),
                        max_wait_seconds=600,  # 10 minutes
                    )
                    if log_files:
                        self.db.save_logs(miner_id, model, "daily_baseline", log_files)
                        with counter_lock:
                            counters["collected"] += 1
                        logger.info("Daily log: miner %s collected, %d files saved",
                                    miner_id, len(log_files))
                    else:
                        # Fresh export failed — try to download most recent EXISTING ready log
                        logger.info("Daily log: fresh export failed for %s, trying existing logs", miner_id)
                        try:
                            existing_logs = self.ams.collect_miner_logs(int(miner_id))
                            if existing_logs:
                                self.db.save_logs(miner_id, model, "daily_baseline_fallback", existing_logs)
                                with counter_lock:
                                    counters["collected"] += 1
                                logger.info("Daily log: miner %s collected via fallback (existing log)",
                                            miner_id)
                            else:
                                with counter_lock:
                                    counters["failed"] += 1
                                    failed_miners.append(entry)
                                logger.warning("Daily log: miner %s no fresh or existing logs available",
                                               miner_id)
                        except Exception as fallback_err:
                            with counter_lock:
                                counters["failed"] += 1
                                failed_miners.append(entry)
                            logger.warning("Daily log: miner %s fallback also failed: %s",
                                           miner_id, fallback_err)
                except Exception as e:
                    with counter_lock:
                        counters["failed"] += 1
                        failed_miners.append(entry)
                    logger.warning("Daily log: miner %s fresh export raised: %s", miner_id, e)

            # Spawn the pool and wait for all miners to complete
            logger.info("Daily log: starting %d-way parallel sweep across %d miners",
                        DAILY_PARALLEL_WORKERS, len(miner_list))
            sweep_start = time.time()
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=DAILY_PARALLEL_WORKERS,
                thread_name_prefix="daily-log-baseline",
            ) as executor:
                futures = [executor.submit(_collect_one, entry) for entry in miner_list]
                for fut in concurrent.futures.as_completed(futures):
                    # as_completed just blocks until each future finishes.
                    # Exceptions are already logged inside _collect_one so
                    # we do not re-raise here.
                    try:
                        fut.result()
                    except Exception as fe:
                        logger.warning("Daily log: worker future raised: %s", fe)

            sweep_elapsed = time.time() - sweep_start
            logger.info(
                "Daily log collection pass 1 complete: %d collected, %d skipped, %d failed, %.1fs",
                counters["collected"], counters["skipped_recent"], counters["failed"], sweep_elapsed,
            )

            # ── RETRY PASS for failed miners ────────────────────────────────
            # Miners that timed out or failed get a second chance with a longer
            # timeout. These simple machines sometimes just need another try.
            # Added April 10 2026 per operator request — log collection is THE
            # most important step, we cannot afford to lose logs.
            if failed_miners:
                logger.info("Daily log RETRY: attempting %d failed miners with 20-min timeout",
                            len(failed_miners))
                retry_counters = {"collected": 0, "failed": 0}
                retry_start = time.time()
                
                def _retry_one(entry):
                    miner_id = entry["id"]
                    model = entry["model"]
                    try:
                        logger.info("Daily log RETRY: pulling miner %s (%s)", miner_id, model)
                        # Longer timeout on retry — 20 minutes instead of 10
                        log_files = self.ams.collect_fresh_miner_logs(
                            int(miner_id),
                            max_wait_seconds=1200,  # 20 minutes
                        )
                        if log_files:
                            self.db.save_logs(miner_id, model, "daily_baseline_retry", log_files)
                            with counter_lock:
                                retry_counters["collected"] += 1
                            logger.info("Daily log RETRY: miner %s SUCCESS, %d files",
                                        miner_id, len(log_files))
                        else:
                            with counter_lock:
                                retry_counters["failed"] += 1
                            logger.warning("Daily log RETRY: miner %s still no files", miner_id)
                    except Exception as e:
                        with counter_lock:
                            retry_counters["failed"] += 1
                        logger.warning("Daily log RETRY: miner %s failed: %s", miner_id, e)

                # Run retries with fewer workers to be gentler
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=5,  # Fewer workers for retry
                    thread_name_prefix="daily-log-retry",
                ) as executor:
                    futures = [executor.submit(_retry_one, entry) for entry in failed_miners]
                    for fut in concurrent.futures.as_completed(futures):
                        try:
                            fut.result()
                        except Exception as fe:
                            logger.warning("Daily log RETRY: worker raised: %s", fe)

                retry_elapsed = time.time() - retry_start
                logger.info(
                    "Daily log RETRY complete: %d recovered, %d still failed, %.1fs",
                    retry_counters["collected"], retry_counters["failed"], retry_elapsed,
                )
                # Update main counters
                counters["collected"] += retry_counters["collected"]
                counters["failed"] = retry_counters["failed"]  # Only count final failures

            total_elapsed = time.time() - sweep_start
            logger.info(
                "Daily log collection FINAL: %d collected, %d skipped, %d failed, %.1fs total",
                counters["collected"], counters["skipped_recent"], counters["failed"], total_elapsed,
            )

        import threading as _threading
        t = _threading.Thread(
            target=_daily_baseline_worker,
            args=(eligible,),
            name="daily-log-baseline",
            daemon=True,
        )
        t.start()
        self._daily_log_thread = t

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

        # AMS-down detection — if ALL miners are offline, AMS is likely down
        online_count = sum(1 for m in miners if m.get("status") == "online")
        ams_is_down = len(miners) > 0 and online_count == 0

        if ams_is_down:
            logger.warning("AMS appears down — all %d miners reporting offline", len(miners))
            # Only post once per hour, just weather + mechanical
            import time as _time
            now_ts = _time.time()
            if now_ts - self._last_slack_post >= self.config.slack_interval_seconds:
                self._last_slack_post = now_ts
                self.slack.send_ams_down(miners, wx, hvac_snapshot)
            else:
                logger.info("AMS down — Slack throttled, next post in %ds",
                            int(self.config.slack_interval_seconds - (now_ts - self._last_slack_post)))
            # Still save scan to DB for tracking, but skip everything else
            self.db.save_scan(miners, [])
            # Update knowledge
            try:
                from knowledge_manager import KnowledgeManager
                km = KnowledgeManager()
                km.update_from_scan(miners, [], wx, hvac_snapshot)
            except Exception:
                pass
            return {"scanned": len(miners), "issues": 0, "ams_down": True}

        issues   = [r for r in (self._analyze_miner(m) for m in miners) if r]
        self._print_report(miners, issues, wx, ams_notifs, facility_snapshot, hvac_snapshot,
                           dry_run=self.config.dry_run)
        scan_id   = self.db.save_scan(miners, issues)

        # Expire unanswered approvals older than 1 hour before saving new ones
        # This keeps the queue clean — only the current scan's actions are ever pending
        expired = self.db.expire_old_pending_approvals(max_age_minutes=60)
        if expired:
            logger.info("Expired %d stale pending approvals", expired)

        # Cancel pending approvals for miners that now have tickets
        # Prevents stale RESTART_CHECK_BOARDS approvals from sitting in queue
        # after a ticket has been auto-created for that miner
        try:
            with self.db._connect() as conn:
                ticketed_ids = [r["miner_id"] for r in conn.execute(
                    "SELECT miner_id FROM known_dead_boards WHERE resolved_at IS NULL"
                ).fetchall()]
                if ticketed_ids:
                    placeholders = ",".join("?" for _ in ticketed_ids)
                    cancelled = conn.execute(f"""
                        UPDATE pending_approvals
                        SET status='CANCELLED', responded_at=datetime('now')
                        WHERE miner_id IN ({placeholders}) AND status='PENDING'
                    """, ticketed_ids).rowcount
                    if cancelled:
                        logger.info(
                            "Cancelled %d pending approvals for ticketed miners", cancelled
                        )
                    conn.commit()
        except Exception:
            logger.exception("Failed to cancel ticketed pending approvals (non-fatal)")

        # ── Auto-ticket: miners with 3+ FAILURE outcomes and no ticket yet ──
        # This handles miners that kept getting plain RESTART approvals but never
        # went through the RESTART_CHECK_BOARDS flow that normally creates tickets.
        try:
            self._auto_create_missing_tickets(miners)
        except Exception:
            logger.exception("Auto-ticket creation failed (non-fatal)")

        self.db.save_chain_readings(scan_id, datetime.now().isoformat(), miners)
        self.db.save_pool_readings(scan_id, datetime.now().isoformat(), miners)
        self.db.save_miner_state_readings(scan_id, datetime.now().isoformat(), miners)
        self.db.save_ams_extended(scan_id, datetime.now().isoformat(), miners)
        self.db.purge_old_logs(days=30)
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
        # Skip when scan data is clearly bad (AMS down = all offline)
        online = sum(1 for m in miners if m.get("status") == "online")
        actionable_issues = [i for i in issues if i["action"] not in ("MONITOR", "PHYSICAL_CYCLE")]
        # LLM analysis — Qwen on ROBS-PC via Tailscale (RTX 4090, ~4.6s per scan)
        # Restored 2026-04-10 after diagnosing frozen llm_scan_analyses stream.
        # Writes to knowledge['llm_scan_analyses'] which weekly_train.py reads.
        # Two-tier AI: Qwen on every scan here, Claude only in Sunday weekly trainer.
        if actionable_issues and online > 0 and len(actionable_issues) <= 20:
            try:
                import json as _json
                import urllib.request as _urlreq
                from datetime import datetime as _dt
                from pathlib import Path as _P
                wx_data = {"temp_f": wx.get("temp_f"), "humidity_pct": wx.get("humidity_pct")} if wx else None
                hvac_data = None
                if hvac_snapshot:
                    hvac_data = {"supply_temp_f": hvac_snapshot.supply_temp_f,
                                 "return_temp_f": hvac_snapshot.return_temp_f,
                                 "delta_t_f": hvac_snapshot.delta_t_f}
                qwen_prompt = (
                    "You are the local LLM for a 58-miner liquid-cooled Bitcoin mining facility. "
                    "Operator rules: do NOT flag chip temps below 84C (normal in liquid cooling), "
                    "do NOT recommend HVAC investigation (HVAC is confirmed correct), "
                    "2+ failed restarts in 7 days auto-escalates to board check.\n\n"
                    f"Scan #{scan_id} — {len(actionable_issues)} miners flagged:\n" +
                    "\n".join(f"- Miner {i['id']} ({i['model']}) @ {i['ip']}: {i.get('action','?')} — {' | '.join(i.get('issues',[]))[:150]}" for i in actionable_issues[:10]) +
                    f"\nWeather: {wx_data}\nHVAC: {hvac_data}\n\n"
                    "Provide: DIAGNOSIS (1 sentence), ACTION (bullet list with miner IPs), PATTERN (1 sentence or 'none')."
                )
                payload = {
                    "model": getattr(self.config, "ollama_model", "qwen2.5:32b-instruct-q4_K_M"),
                    "prompt": qwen_prompt,
                    "stream": False,
                    "options": {"temperature": 0.3, "num_ctx": 16384},
                }
                req = _urlreq.Request(
                    getattr(self.config, "ollama_url", "http://100.110.87.1:11434/api/generate"),
                    data=_json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with _urlreq.urlopen(req, timeout=60) as r:
                    resp = _json.loads(r.read().decode())
                analysis_text = resp.get("response", "").strip()
                if analysis_text:
                    logger.info("Qwen scan analysis: %s", analysis_text[:200])
                    # Write to llm_scan_analyses stream (the one weekly_train.py reads)
                    kpath = _P("/root/Mining-Gaurdian/knowledge.json")
                    knowledge = _json.loads(kpath.read_text()) if kpath.exists() else {}
                    if not isinstance(knowledge.get("llm_scan_analyses"), list):
                        knowledge["llm_scan_analyses"] = []
                    knowledge["llm_scan_analyses"].append({
                        "timestamp": _dt.now().isoformat(),
                        "analysis": analysis_text,
                        "model": payload["model"],
                        "scan_id": scan_id,
                        "source": "qwen_scan_loop",
                    })
                    # Keep last 500 entries to bound file size
                    knowledge["llm_scan_analyses"] = knowledge["llm_scan_analyses"][-500:]
                    tmp = str(kpath) + ".tmp"
                    with open(tmp, "w") as f:
                        _json.dump(knowledge, f, indent=2)
                    import os as _os
                    _os.replace(tmp, str(kpath))
                    logger.info("llm_scan_analyses written, now %d entries", len(knowledge["llm_scan_analyses"]))
                else:
                    logger.warning("Qwen returned empty response for scan #%d", scan_id)
            except Exception as e:
                logger.warning("Qwen scan analysis failed: %s", e)
        elif issues and online == 0:
            logger.info("LLM analysis skipped — all miners offline (AMS likely down)")
        elif len(actionable_issues) > 20:
            logger.info("LLM analysis skipped — too many issues (%d), likely systemic problem", len(actionable_issues))

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
        # Ensure ai/ directory is in sys.path for all feature imports
        import sys as _sys
        _ai_path = str(Path(__file__).resolve().parent.parent / "ai")
        if _ai_path not in _sys.path:
            _sys.path.insert(0, _ai_path)

        # Import outcome checker once at loop start
        try:
            from outcome_checker import check_outcomes
            _has_outcome_checker = True
        except ImportError:
            logger.warning("outcome_checker not found — outcome feedback disabled")
            _has_outcome_checker = False

        while True:
            try:
                self.run_once()

                # Feature 1: Outcome Feedback Loop
                # Runs after every scan to evaluate restart outcomes
                if _has_outcome_checker:
                    try:
                        check_outcomes()
                    except Exception:
                        logger.exception("Outcome checker error (non-fatal)")

                # Feature 5: HVAC/Environment Correlation
                # Check if fleet flags correlate with facility stress
                try:
                    from hvac_correlator import check_fleet_correlation, get_facility_stress_level
                    stress, reasons = get_facility_stress_level()
                    if stress >= 26:
                        logger.info("Facility stress %d%%: %s", stress, reasons)
                    # check_fleet_correlation uses the latest scan id
                    latest_scan = self.db._connect().execute(
                        "SELECT id FROM scans ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                    if latest_scan:
                        check_fleet_correlation(latest_scan["id"])
                except Exception:
                    logger.debug("HVAC correlator skipped (non-fatal)")

                # Feature 6: Pre-Failure Prediction
                # Detect miners showing pre-failure signals before they break
                try:
                    from predictor import run_predictions, format_prediction_alert
                    latest_scan = self.db._connect().execute(
                        "SELECT id FROM scans ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                    if latest_scan:
                        preds = run_predictions(latest_scan["id"])
                        for pred in preds:
                            # Only alert for high-confidence predictions (>= 75%)
                            if pred.get("confidence", 0) < 75:
                                logger.debug("Prediction skipped (low conf): %s conf=%d%%",
                                           pred.get("ip"), pred.get("confidence", 0))
                                continue
                            
                            logger.info("Prediction alert: %s %s conf=%d%%",
                                       pred.get("ip"), pred.get("action"), pred.get("confidence", 0))

                            # Skip ticketed miners — they already have a ticket open
                            if self.db.has_known_dead_boards(miner_id):
                                logger.debug(
                                    "Prediction suppressed for %s — dead board ticket open", ip
                                )
                                continue

                            # Skip Auradine voltage signal — 0.29V is their firmware format
                            firmware = ""
                            try:
                                with self.db._connect() as _c:
                                    _fw = _c.execute(
                                        "SELECT firmware_manufacturer FROM miner_readings "
                                        "WHERE miner_id=? ORDER BY id DESC LIMIT 1", (miner_id,)
                                    ).fetchone()
                                    firmware = (_fw["firmware_manufacturer"] or "").upper() if _fw else ""
                            except Exception:
                                pass
                            if "AURADINE" in firmware:
                                filtered = [s for s in pred.get("signals", [])
                                            if "voltage" not in s.lower()]
                                if not filtered:
                                    logger.debug("Prediction suppressed for %s — Auradine voltage false positive", ip)
                                    continue
                                pred["signals"] = filtered

                            if pred["action"] == "PREEMPTIVE_RESTART":
                                try:
                                    # Post as approval request so you can APPROVE or DENY
                                    msg = format_prediction_alert(pred)
                                    thread = self.slack.post_to_approvals(
                                        msg + "\n\n_Reply `APPROVE` to execute restart or `DENY` to skip._"
                                    )
                                    # Register as pending approval so listener picks it up
                                    if thread and isinstance(thread, str):
                                        self.db.save_pending_approvals(
                                            thread, latest_scan["id"],
                                            [{
                                                "id":          miner_id,
                                                "ip":          ip,
                                                "model":       pred.get("model", ""),
                                                "action":      "RESTART",
                                                "issues":      pred.get("signals", []),
                                                "hashrate_pct":f"{pred.get('current_hr', 0):.1f}%",
                                                "temp_chip":   pred.get("current_chip_temp", 0),
                                            }]
                                        )
                                except Exception:
                                    pass
                            logger.info("Prediction: %s %s conf=%d%%",
                                       ip, pred["action"], pred["confidence"])
                except Exception:
                    logger.debug("Predictor skipped (non-fatal)")

                # Feature 8: Action Diversity
                # Evaluate power tuning, eco mode, pool failover
                try:
                    from action_diversity import evaluate_all_actions
                    latest_scan = self.db._connect().execute(
                        "SELECT id FROM scans ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                    if latest_scan:
                        new_actions = evaluate_all_actions(latest_scan["id"])
                        for act in new_actions:
                            logger.info(
                                "Action diversity: %s for %s conf=%d%% reasons=%s",
                                act["action"], act["ip"],
                                act["confidence"], act.get("reasons", [])[:1]
                            )
                            # Log to audit trail for tracking
                            try:
                                self.db.log_action(
                                    act["miner_id"], act["ip"],
                                    act["model"],
                                    problem="; ".join(act.get("reasons", [])),
                                    action_taken=act["action"],
                                    decision="PENDING_APPROVAL",
                                    notes=f"confidence={act['confidence']}% data={act.get('data_used',[])}",
                                )
                            except Exception:
                                pass
                            # Post to Slack so operator can approve/deny
                            try:
                                reasons_str = ", ".join(act.get("reasons", []))[:100]
                                msg = (
                                    f":crystal_ball: *AI Recommendation — {act['action']}*\n"
                                    f"Miner: `{act['ip']}` ({act['model']})\n"
                                    f"Confidence: *{act['confidence']}%*\n"
                                    f"Reason: {reasons_str}\n\n"
                                    f"_Reply `APPROVE` to execute or `DENY` to skip._"
                                )
                                thread = self.slack.post_to_approvals(msg)
                                if thread and isinstance(thread, str) and thread:
                                    issue_entry = [{
                                        "id": act["miner_id"],
                                        "ip": act["ip"],
                                        "model": act["model"],
                                        "action": act["action"],
                                        "issues": act.get("reasons", []),
                                    }]
                                    self.db.save_pending_approvals(
                                        thread, latest_scan["id"], issue_entry
                                    )
                            except Exception as ex:
                                logger.debug("Action diversity Slack post failed: %s", ex)
                            
                except Exception:
                    logger.debug("Action diversity skipped (non-fatal)")

                # ── Local LLM scan analysis (background thread) ──────────
                # Sends fleet data to Qwen 32B on RTX 4090 for real-time analysis.
                # Runs in background thread — never blocks the next scan.
                try:
                    import threading
                    from llm_scan_hook import run_post_scan_llm
                    # scan_id is local to run_once() — fetch latest from DB instead
                    _latest = self.db._connect().execute(
                        "SELECT id FROM scans ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                    if _latest:
                        _scan_id = _latest["id"]
                        logger.info("Local LLM analysis scheduled for scan #%s", _scan_id)
                        def _llm_analysis():
                            try:
                                run_post_scan_llm(_scan_id, self.slack)
                                logger.info("Local LLM analysis complete for scan #%s", _scan_id)
                            except Exception as ex:
                                logger.warning("Local LLM analysis thread error: %s", ex)
                        threading.Thread(target=_llm_analysis, daemon=True).start()
                    else:
                        logger.debug("Local LLM analysis skipped — no scans yet")
                except Exception as ex:
                    logger.warning("Local LLM analysis setup failed: %s", ex)

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
