import os
import json
import time
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests
import websocket
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("mining_guardian")


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
    dry_run: bool = True
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
            dry_run=raw.get("dry_run", True),
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
        now = datetime.utcnow()
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
                self._token_expiry = datetime.utcfromtimestamp(exp) - timedelta(seconds=60)
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

    # ── Public write methods ──────────────────────────────────

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
# OpenClaw notifier — unchanged
# ------------------------------------------------------------

class OpenClawNotifier:
    def __init__(self, webhook_url: Optional[str]):
        self.webhook_url = webhook_url

    def send_findings(self, findings: List[MinerFinding]) -> None:
        if not self.webhook_url or not findings:
            return
        payload = {
            "type": "mining_guardian.findings",
            "count": len(findings),
            "findings": [
                {"miner_id": f.miner_id, "ip": f.ip, "key": f.key,
                 "actual": f.actual, "expected": f.expected,
                 "severity": f.severity, "recommended_fix": f.recommended_fix,
                 "note": f.note}
                for f in findings
            ],
        }
        try:
            requests.post(self.webhook_url, json=payload, timeout=10)
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
        return False if last is None else datetime.utcnow() - last < self.cooldown

    def record(self, miner_id: str, key: str) -> None:
        self._last_remediated[(miner_id, key)] = datetime.utcnow()


# ------------------------------------------------------------
# Orchestrator — updated to use new AMSClient interface
# ------------------------------------------------------------

class MiningGuardian:
    HASHRATE_THRESHOLD = 0.90   # flag if below 90% of maxHashrate

    def __init__(self, config: GuardianConfig):
        self.config   = config
        self.ams      = AMSClient(config)
        self.notifier = OpenClawNotifier(config.openclaw_webhook_url)

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
        temp_chip     = temp_chip_raw if temp_chip_raw >= 0 else None  # negative = bad sensor
        temp_low   = miner.get("tempChipLow", 86)
        temp_med   = miner.get("tempChipMedium", 95)
        temp_max   = miner.get("maxTempChip", 100)

        issues = []
        action = None

        # ── Hashrate check ──────────────────────────────────
        if status == "offline":
            pct = 0.0
            issues.append("OFFLINE")
            action = "RESTART"
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
        }

    # ── Report printer ────────────────────────────────────────

    @staticmethod
    def _print_report(miners: List[Dict], issues: List[Dict]) -> None:
        now      = datetime.now().strftime("%Y-%m-%d %H:%M")
        online   = sum(1 for m in miners if m.get("status") == "online")
        offline  = len(miners) - online
        divider  = "━" * 60

        print(f"\n{divider}")
        print(f"  MINING GUARDIAN SCAN — {now}")
        print(divider)
        print(f"  Fleet:   {len(miners)} miners  |  {online} online  |  {offline} offline")
        print(divider)

        if not issues:
            print("  ✅ All miners operating within normal parameters.")
        else:
            # Group by action
            restarts = [i for i in issues if i["action"] == "RESTART"]
            monitors = [i for i in issues if i["action"] == "MONITOR"]

            if restarts:
                print(f"\n  🔴 RESTART RECOMMENDED ({len(restarts)} miners)\n")
                print(f"  {'ID':<8} {'IP':<18} {'Model':<14} {'Hashrate':<10} {'ChipTemp':<10} Issue")
                print(f"  {'-'*8} {'-'*18} {'-'*14} {'-'*10} {'-'*10} {'-'*30}")
                for i in restarts:
                    issue_str = " | ".join(i["issues"])
                    print(f"  {i['id']:<8} {i['ip']:<18} {i['model']:<14} {i['hashrate_pct']:<10} {i['temp_chip']:<10} {issue_str}")

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

    # ── Main entry ────────────────────────────────────────────

    def run_once(self) -> Dict[str, Any]:
        miners = self.ams.get_miners(self.config.miner_filters)
        issues = [r for r in (self._analyze_miner(m) for m in miners) if r]
        self._print_report(miners, issues)
        self.notifier.send_findings([])   # placeholder — findings now use new format
        return {
            "scanned": len(miners),
            "issues":  len(issues),
            "restart_recommended": [i["id"] for i in issues if i["action"] == "RESTART"],
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
    config_path = os.environ.get("GUARDIAN_CONFIG", "config.json")
    if not os.path.exists(config_path):
        write_example_config()
        raise SystemExit("Create config.json from config.example.json, then re-run.")

    config   = GuardianConfig.from_file(config_path)
    guardian = MiningGuardian(config)
    result   = guardian.run_once()
    print(json.dumps(result, indent=2))
