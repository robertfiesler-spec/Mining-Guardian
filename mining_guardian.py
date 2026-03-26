import os
import json
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("mining_guardian")


# ------------------------------------------------------------
# Configuration models
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
            if self.operator == "eq":
                return actual == self.expected
            if self.operator == "neq":
                return actual != self.expected
            if self.operator == "lt":
                return actual < self.expected
            if self.operator == "lte":
                return actual <= self.expected
            if self.operator == "gt":
                return actual > self.expected
            if self.operator == "gte":
                return actual >= self.expected
            if self.operator == "between":
                low, high = self.expected
                return low <= actual <= high
            if self.operator == "in":
                return actual in self.expected
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
    ams_base_url: str
    ams_api_key: str
    openclaw_webhook_url: Optional[str] = None
    dry_run: bool = True
    scan_interval_seconds: int = 300
    approval_mode: str = "manual"  # manual | auto-low-risk
    miner_filters: Dict[str, Any] = field(default_factory=dict)
    rules: List[ParameterRule] = field(default_factory=list)

    @staticmethod
    def _resolve_secret(value: str) -> str:
        """If value starts with 'env:', resolve it from the environment.

        Example in config.json:
            "ams_api_key": "env:AMS_API_KEY"

        This keeps secrets out of config files on disk.
        """
        if isinstance(value, str) and value.startswith("env:"):
            env_var = value[4:]
            resolved = os.environ.get(env_var)
            if not resolved:
                raise EnvironmentError(
                    f"Secret '{env_var}' referenced in config but not set in environment."
                )
            return resolved
        return value

    @staticmethod
    def from_file(path: str) -> "GuardianConfig":
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        rules = [ParameterRule(**item) for item in raw.get("rules", [])]
        return GuardianConfig(
            ams_base_url=raw["ams_base_url"],
            ams_api_key=GuardianConfig._resolve_secret(raw["ams_api_key"]),
            openclaw_webhook_url=raw.get("openclaw_webhook_url"),
            dry_run=raw.get("dry_run", True),
            scan_interval_seconds=raw.get("scan_interval_seconds", 300),
            approval_mode=raw.get("approval_mode", "manual"),
            miner_filters=raw.get("miner_filters", {}),
            rules=rules,
        )


# ------------------------------------------------------------
# AMS client
# Replace endpoint paths with your actual AMS API routes.
# ------------------------------------------------------------

class AMSClient:
    # Retry on transient server errors and network timeouts.
    # total=3 means up to 3 retries (4 attempts total).
    # backoff_factor=1 gives delays of 1s, 2s, 4s between retries.
    # status_forcelist retries on 429 (rate limit), 500, 502, 503, 504.
    _RETRY_POLICY = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist={429, 500, 502, 503, 504},
        allowed_methods={"GET", "POST", "PATCH"},
        raise_on_status=False,
    )

    def __init__(self, base_url: str, api_key: str, timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        adapter = HTTPAdapter(max_retries=self._RETRY_POLICY)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def get_miners(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        filters = filters or {}
        url = f"{self.base_url}/api/miners"
        response = self.session.get(url, params=filters, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        return data.get("items", data)

    def get_miner_state(self, miner_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/miners/{miner_id}"
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def patch_miner_settings(self, miner_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/api/miners/{miner_id}/settings"
        response = self.session.patch(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def restart_miner(self, miner_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/miners/{miner_id}/restart"
        response = self.session.post(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()


# ------------------------------------------------------------
# Policy engine
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
            passed = rule.evaluate(actual)
            if not passed:
                findings.append(
                    MinerFinding(
                        miner_id=miner_id,
                        ip=ip,
                        key=rule.key,
                        actual=actual,
                        expected=rule.expected,
                        operator=rule.operator,
                        severity=rule.severity,
                        note=rule.note,
                        recommended_fix=rule.recommended_fix,
                    )
                )
        return findings


# ------------------------------------------------------------
# Recommendation + approval flow
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


class ApprovalInterface:
    def __init__(self, config: GuardianConfig):
        self.config = config

    def request_approval(self, finding: MinerFinding) -> bool:
        """Request approval for a remediation action.

        Approval flow by mode
        ---------------------
        auto-low-risk : Low-risk findings are approved automatically by the
                        caller (MiningGuardian.remediate) before this method
                        is invoked.  Only high-severity or non-whitelisted
                        keys reach here — fall through to interactive prompt.

        manual        : Always prompts interactively.  In a headless/daemon
                        context swap this out for the OpenClaw webhook flow
                        described below.

        OpenClaw integration (TODO)
        ---------------------------
        1. POST finding summary to config.openclaw_webhook_url with an
           action_id (e.g. UUID).
        2. Poll or receive a callback at an /approve endpoint.
        3. Return True if the operator replied APPROVE within a timeout,
           False otherwise.
        """
        summary = (
            f"  Miner : {finding.miner_id} ({finding.ip})\n"
            f"  Key   : {finding.key}\n"
            f"  Actual: {finding.actual}  →  Fix: {finding.recommended_fix}\n"
            f"  Note  : {finding.note or '—'}"
        )
        logger.info("Approval required:\n%s", summary)

        # ── Interactive CLI prompt (interim until OpenClaw is wired) ──────
        # If stdin is not a TTY (e.g. running as a systemd service) this
        # safely returns False so the finding is logged but not applied.
        if not os.isatty(0):
            logger.warning(
                "Non-interactive environment — auto-denying approval for miner=%s key=%s",
                finding.miner_id,
                finding.key,
            )
            return False

        try:
            answer = input(f"\nApprove patch for {finding.miner_id} [{finding.key}]? [y/N]: ")
            return answer.strip().lower() == "y"
        except (EOFError, KeyboardInterrupt):
            logger.warning("Approval prompt interrupted — denying.")
            return False


# ------------------------------------------------------------
# OpenClaw notifier (webhook placeholder)
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
                {
                    "miner_id": f.miner_id,
                    "ip": f.ip,
                    "key": f.key,
                    "actual": f.actual,
                    "expected": f.expected,
                    "severity": f.severity,
                    "recommended_fix": f.recommended_fix,
                    "note": f.note,
                }
                for f in findings
            ],
        }
        try:
            requests.post(self.webhook_url, json=payload, timeout=10)
        except Exception as exc:
            logger.warning("Failed to send OpenClaw notification: %s", exc)


# ------------------------------------------------------------
# Remediation cooldown cache
# ------------------------------------------------------------

class RemediationCooldown:
    """Prevents hammering the same (miner, key) pair on every scan cycle.

    How it works
    ------------
    After a successful patch (or dry-run), we record a timestamp for the
    (miner_id, key) pair.  Subsequent calls to is_cooling_down() return True
    until cooldown_minutes has elapsed, causing the orchestrator to skip that
    finding.

    Why this matters
    ----------------
    Without it, a persistently non-compliant miner generates a finding every
    scan cycle and triggers repeated patch attempts or repeated approval
    prompts — noisy and potentially harmful to miner stability.
    """

    def __init__(self, cooldown_minutes: int = 30):
        self.cooldown = timedelta(minutes=cooldown_minutes)
        self._last_remediated: Dict[Tuple[str, str], datetime] = {}

    def is_cooling_down(self, miner_id: str, key: str) -> bool:
        last = self._last_remediated.get((miner_id, key))
        if last is None:
            return False
        return datetime.utcnow() - last < self.cooldown

    def record(self, miner_id: str, key: str) -> None:
        self._last_remediated[(miner_id, key)] = datetime.utcnow()


# ------------------------------------------------------------
# Orchestrator
# ------------------------------------------------------------

class MiningGuardian:
    def __init__(self, config: GuardianConfig):
        self.config = config
        self.ams = AMSClient(config.ams_base_url, config.ams_api_key)
        self.engine = PolicyEngine(config.rules)
        self.planner = RemediationPlanner()
        self.approval = ApprovalInterface(config)
        self.notifier = OpenClawNotifier(config.openclaw_webhook_url)
        self.cooldown = RemediationCooldown(cooldown_minutes=30)

    def scan(self) -> List[MinerFinding]:
        """Fetch miner list, then re-fetch fresh per-miner state before evaluating rules.

        Why re-fetch per miner?
        -----------------------
        The list endpoint (/api/miners) typically returns a summary snapshot —
        often cached or aggregated.  The individual state endpoint returns live
        telemetry.  Evaluating rules against stale list data produces false
        positives and missed violations.  We degrade gracefully: if the
        per-miner fetch fails, we fall back to the list snapshot with a warning.
        """
        miners = self.ams.get_miners(self.config.miner_filters)
        findings: List[MinerFinding] = []

        for miner in miners:
            miner_id = str(miner.get("id", "unknown"))
            try:
                fresh_state = self.ams.get_miner_state(miner_id)
            except Exception:
                logger.warning(
                    "Could not fetch fresh state for miner %s — using list snapshot",
                    miner_id,
                )
                fresh_state = miner
            findings.extend(self.engine.evaluate_miner(fresh_state))

        return findings

    def remediate(self, findings: List[MinerFinding]) -> List[Tuple[MinerFinding, str]]:
        results: List[Tuple[MinerFinding, str]] = []

        for finding in findings:
            if self.cooldown.is_cooling_down(finding.miner_id, finding.key):
                logger.debug(
                    "Cooldown active — skipping miner=%s key=%s",
                    finding.miner_id,
                    finding.key,
                )
                results.append((finding, "cooldown"))
                continue

            try:
                auto_ok = (
                    self.config.approval_mode == "auto-low-risk"
                    and self.planner.is_low_risk(finding)
                )
                approved = auto_ok or self.approval.request_approval(finding)

                if not approved:
                    results.append((finding, "not approved"))
                    continue

                patch = self.planner.build_patch(finding)
                if self.config.dry_run:
                    logger.info("DRY RUN patch for miner %s: %s", finding.miner_id, patch)
                    self.cooldown.record(finding.miner_id, finding.key)
                    results.append((finding, "dry-run only"))
                    continue

                self.ams.patch_miner_settings(finding.miner_id, patch)
                self.cooldown.record(finding.miner_id, finding.key)
                results.append((finding, "patched"))
            except Exception as exc:
                logger.exception("Failed remediation for miner %s", finding.miner_id)
                results.append((finding, f"error: {exc}"))

        return results

    def run_once(self) -> Dict[str, Any]:
        findings = self.scan()
        self.notifier.send_findings(findings)
        remediation = self.remediate(findings)
        summary = {
            "finding_count": len(findings),
            "remediation_count": len(remediation),
            "results": [
                {
                    "miner_id": finding.miner_id,
                    "ip": finding.ip,
                    "key": finding.key,
                    "status": status,
                }
                for finding, status in remediation
            ],
        }
        return summary

    def loop(self) -> None:
        while True:
            try:
                summary = self.run_once()
                logger.info("Scan summary: %s", json.dumps(summary))
            except Exception:
                logger.exception("Guardian loop failed")
            time.sleep(self.config.scan_interval_seconds)


# ------------------------------------------------------------
# Example config.json
# ------------------------------------------------------------
EXAMPLE_CONFIG = {
    "ams_base_url": "https://ams.internal.example",
    # Use "env:VAR_NAME" to source secrets from the environment instead of
    # storing them in this file.  Example: set AMS_API_KEY in your shell or
    # systemd service unit, then reference it as "env:AMS_API_KEY" here.
    "ams_api_key": "env:AMS_API_KEY",
    "openclaw_webhook_url": "https://openclaw.internal/webhook/mining-guardian",
    "dry_run": True,
    "scan_interval_seconds": 300,
    "approval_mode": "manual",
    "miner_filters": {
        "site": "warehouse-a"
    },
    "rules": [
        {
            "key": "telemetry.hashrate_ths",
            "operator": "gte",
            "expected": 130,
            "severity": "critical",
            "recommended_fix": None,
            "note": "Hashrate below expected floor — no automatic fix; requires operator review"
        },
        {
            "key": "telemetry.chip_temp_c",
            "operator": "between",
            "expected": [40, 75],
            "severity": "critical",
            "recommended_fix": "efficiency",
            "note": "Temperature outside normal envelope — drop to efficiency power profile"
        },
        {
            "key": "config.power.profile",
            "operator": "in",
            "expected": ["balanced", "efficiency", "immersion-140th"],
            "severity": "warning",
            "recommended_fix": "balanced",
            "note": "Unexpected power profile detected"
        }
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
        raise SystemExit("Create config.json from config.example.json and adjust endpoints.")

    config = GuardianConfig.from_file(config_path)
    guardian = MiningGuardian(config)
    result = guardian.run_once()
    print(json.dumps(result, indent=2))
