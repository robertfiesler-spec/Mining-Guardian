"""
Mining Guardian Data Models and Utilities
Extracted from mining_guardian.py on April 21, 2026

Contains dataclasses, config loading, and small utility classes.
"""

import os
import json
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class ParameterRule:
    # P-029 (2026-05-06): @dataclass decorator restored. Without it, the bare
    # class lacked an __init__ accepting these annotations as kwargs, so
    # GuardianConfig.from_file's `ParameterRule(**item)` raised
    # TypeError: ParameterRule() takes no arguments — crashing scanner and
    # ams_alert_listener on first config load. Defaults stay None/empty so
    # legacy tests that mutate fields after `ParameterRule()` still pass.
    key: Optional[str] = None
    operator: Optional[str] = None
    expected: Any = None
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
    slack_webhook_url: Optional[str] = None
    slack_bot_token:   Optional[str] = None
    dry_run: bool = True
    collect_logs: bool = False  # enable log collection independently of dry_run
    scan_interval_seconds: int = 300
    slack_interval_seconds: int = 3600  # post to Slack at most once per hour
    approval_mode: str = "manual"
    miner_filters: Dict[str, Any] = field(default_factory=dict)
    rules: List[ParameterRule] = field(default_factory=list)
    # P-031 (2026-05-08): Ollama endpoint + model surfaced on the config so
    # callers stop falling back to the never-installed
    # `qwen2.5:32b-instruct-q4_K_M`. Resolution order is env-first via
    # core.ollama_config — see that module's docstring for the rationale.
    ollama_url: Optional[str] = None
    ollama_model: Optional[str] = None

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
        # P-031: resolve Ollama URL + model with env-first precedence so the
        # scanner never falls back to the un-installed 32B model. config.json
        # values (if any) are resolved through `_resolve` so `env:OLLAMA_URL`
        # / `env:OLLAMA_MODEL` placeholders work. When the key is absent OR
        # the env var the placeholder points to is unset, the helper falls
        # back to env-direct → D-13 default — the placeholder must NOT
        # raise on the OLLAMA path because the env file legitimately may
        # not carry one (helper has its own defaults).
        from core.ollama_config import resolve_ollama_url, resolve_ollama_model

        def _try_resolve(value):
            if not value:
                return None
            try:
                return GuardianConfig._resolve(value)
            except EnvironmentError:
                return None

        cfg_ollama_url = _try_resolve(raw.get("ollama_url"))
        cfg_ollama_model = _try_resolve(raw.get("ollama_model"))
        return GuardianConfig(
            ams_base_url=raw["ams_base_url"],
            ams_email=GuardianConfig._resolve(raw["ams_email"]),
            ams_password=GuardianConfig._resolve(raw["ams_password"]),
            ams_workspace_id=int(GuardianConfig._resolve(raw["ams_workspace_id"])),
            slack_webhook_url=raw.get("slack_webhook_url"),
            slack_bot_token=raw.get("slack_bot_token"),
            dry_run=raw.get("dry_run", True),
            collect_logs=raw.get("collect_logs", False),
            scan_interval_seconds=raw.get("scan_interval_seconds", 300),
            slack_interval_seconds=raw.get("slack_interval_seconds", 3600),
            approval_mode=raw.get("approval_mode", "manual"),
            miner_filters=raw.get("miner_filters", {}),
            rules=rules,
            ollama_url=resolve_ollama_url(cfg_ollama_url),
            ollama_model=resolve_ollama_model(cfg_ollama_model),
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


# RemediationCooldown - manages cooldown periods between actions
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
