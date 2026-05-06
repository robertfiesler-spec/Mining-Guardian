"""
Tests for the models module (dataclasses and utilities).
Created April 21, 2026 as part of Phase 4 testing infrastructure.

P-029 (2026-05-06): Added ParameterRule kwarg-construction tests and
GuardianConfig.from_file roundtrip tests against the exact rule dicts
emitted by write_example_config(), to lock in the fix for the
"TypeError: ParameterRule() takes no arguments" crash that hit scanner
and ams_alert_listener on the customer Mac mini after copying
config.example.json -> config.json.
"""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import (
    ParameterRule,
    MinerFinding,
    GuardianConfig,
    PolicyEngine,
    RemediationPlanner,
    RemediationCooldown,
)


# Mirror of the canonical example config emitted by
# core.mining_guardian.write_example_config (and persisted to
# config.example.json on the customer Mac mini at install time).
# Kept in-sync via test_example_config_shape_matches_source below
# so we don't have to import the full guardian module (heavy deps).
EXAMPLE_CONFIG_RULES = [
    {
        "key": "telemetry.hashrate_ths",
        "operator": "gte",
        "expected": 85,
        "severity": "critical",
        "recommended_fix": None,
        "note": "Hashrate below model minimum — requires operator review",
    },
    {
        "key": "telemetry.chip_temp_c",
        "operator": "between",
        "expected": [40, 80],
        "severity": "critical",
        "recommended_fix": "efficiency",
        "note": "Chip temp outside safe envelope — drop to efficiency profile",
    },
]

EXAMPLE_CONFIG = {
    "ams_base_url": "https://api-staging.dev.bixbit.io/api/v1",
    "ams_email": "env:AMS_EMAIL",
    "ams_password": "env:AMS_PASSWORD",
    "ams_workspace_id": "env:AMS_WORKSPACE_ID",
    "dry_run": True,
    "scan_interval_seconds": 300,
    "approval_mode": "manual",
    "miner_filters": {},
    "rules": EXAMPLE_CONFIG_RULES,
}


class TestParameterRule:
    """Tests for ParameterRule class."""

    def test_evaluate_eq_true(self):
        """Test equality operator returns True when values match."""
        rule = ParameterRule()
        rule.key = "status"
        rule.operator = "eq"
        rule.expected = "ONLINE"
        assert rule.evaluate("ONLINE") is True

    def test_evaluate_eq_false(self):
        """Test equality operator returns False when values differ."""
        rule = ParameterRule()
        rule.key = "status"
        rule.operator = "eq"
        rule.expected = "ONLINE"
        assert rule.evaluate("OFFLINE") is False

    def test_evaluate_gt(self):
        """Test greater than operator."""
        rule = ParameterRule()
        rule.key = "temp"
        rule.operator = "gt"
        rule.expected = 80
        assert rule.evaluate(85) is True
        assert rule.evaluate(75) is False

    def test_evaluate_between(self):
        """Test between operator."""
        rule = ParameterRule()
        rule.key = "temp"
        rule.operator = "between"
        rule.expected = (60, 80)
        assert rule.evaluate(70) is True
        assert rule.evaluate(85) is False

    def test_evaluate_in(self):
        """Test in operator."""
        rule = ParameterRule()
        rule.key = "status"
        rule.operator = "in"
        rule.expected = ["ONLINE", "STARTING"]
        assert rule.evaluate("ONLINE") is True
        assert rule.evaluate("OFFLINE") is False


class TestRemediationCooldown:
    """Tests for RemediationCooldown class."""

    def test_not_cooling_down_initially(self):
        """Test that a new miner is not in cooldown."""
        cooldown = RemediationCooldown(cooldown_minutes=30)
        assert cooldown.is_cooling_down("12345", "RESTART") is False

    def test_cooling_down_after_record(self):
        """Test that a miner is in cooldown after recording."""
        cooldown = RemediationCooldown(cooldown_minutes=30)
        cooldown.record("12345", "RESTART")
        assert cooldown.is_cooling_down("12345", "RESTART") is True

    def test_different_keys_not_cooling_down(self):
        """Test that different action keys have separate cooldowns."""
        cooldown = RemediationCooldown(cooldown_minutes=30)
        cooldown.record("12345", "RESTART")
        # Different key should not be in cooldown
        assert cooldown.is_cooling_down("12345", "PDU_CYCLE") is False


class TestMinerFinding:
    """Tests for MinerFinding dataclass."""

    def test_create_finding(self):
        """Test creating a MinerFinding."""
        finding = MinerFinding(
            miner_id="12345",
            ip="192.168.188.10",
            key="temp_check",
            operator="gt",
            note="Temperature too high",
            recommended_fix=None,
            severity="warning",
            actual=85,
            expected=80,
        )
        assert finding.miner_id == "12345"
        assert finding.severity == "warning"


class TestParameterRuleConstruction:
    """P-029 regression: ParameterRule must accept the keys emitted by
    write_example_config() as kwargs. Before the @dataclass decorator was
    restored, ``ParameterRule(**item)`` raised TypeError on the customer
    Mac mini after copying config.example.json -> config.json."""

    def test_construct_with_full_kwargs(self):
        item = EXAMPLE_CONFIG_RULES[0]
        rule = ParameterRule(**item)
        assert rule.key == "telemetry.hashrate_ths"
        assert rule.operator == "gte"
        assert rule.expected == 85
        assert rule.severity == "critical"
        assert rule.recommended_fix is None
        assert rule.note.startswith("Hashrate below")

    def test_construct_between_with_list_expected(self):
        # `expected: [40, 80]` is JSON-decoded to a list, not a tuple —
        # evaluate() relies on tuple-style unpacking, which works on lists.
        rule = ParameterRule(**EXAMPLE_CONFIG_RULES[1])
        assert rule.operator == "between"
        assert rule.expected == [40, 80]
        assert rule.evaluate(70) is True
        assert rule.evaluate(85) is False

    def test_construct_with_recommended_fix_string(self):
        rule = ParameterRule(**EXAMPLE_CONFIG_RULES[1])
        assert rule.recommended_fix == "efficiency"

    def test_construct_no_args_still_works(self):
        # Legacy tests in this file mutate fields after `ParameterRule()`.
        # Defaults must keep that path working.
        rule = ParameterRule()
        rule.key = "x"
        rule.operator = "eq"
        rule.expected = "ONLINE"
        assert rule.evaluate("ONLINE") is True


class TestGuardianConfigFromFile:
    """P-029 regression: GuardianConfig.from_file must successfully parse
    the file emitted by write_example_config() once the operator fills in
    AMS_EMAIL / AMS_PASSWORD / AMS_WORKSPACE_ID via env."""

    def setup_method(self):
        self._saved_env = {
            k: os.environ.get(k)
            for k in ("AMS_EMAIL", "AMS_PASSWORD", "AMS_WORKSPACE_ID")
        }
        os.environ["AMS_EMAIL"] = "operator@example.com"
        os.environ["AMS_PASSWORD"] = "test-password"
        os.environ["AMS_WORKSPACE_ID"] = "119"

    def teardown_method(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _write_config(self, payload):
        fd, path = tempfile.mkstemp(suffix=".json", prefix="mg-test-config-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return path

    def test_loads_example_config_shape(self):
        path = self._write_config(EXAMPLE_CONFIG)
        try:
            cfg = GuardianConfig.from_file(path)
            assert cfg.ams_base_url == EXAMPLE_CONFIG["ams_base_url"]
            assert cfg.ams_email == "operator@example.com"
            assert cfg.ams_password == "test-password"
            assert cfg.ams_workspace_id == 119
            assert len(cfg.rules) == 2
            # Each loaded rule must be a real ParameterRule instance with
            # working evaluate(), not a dict or a stub.
            assert all(isinstance(r, ParameterRule) for r in cfg.rules)
            assert cfg.rules[0].evaluate(90) is True   # 90 >= 85
            assert cfg.rules[0].evaluate(80) is False  # 80 < 85
            assert cfg.rules[1].evaluate(70) is True   # 40 <= 70 <= 80
            assert cfg.rules[1].evaluate(85) is False  # 85 > 80
        finally:
            os.unlink(path)

    def test_loads_when_rules_empty(self):
        payload = {**EXAMPLE_CONFIG, "rules": []}
        path = self._write_config(payload)
        try:
            cfg = GuardianConfig.from_file(path)
            assert cfg.rules == []
        finally:
            os.unlink(path)

    def test_loads_when_rules_missing(self):
        payload = {k: v for k, v in EXAMPLE_CONFIG.items() if k != "rules"}
        path = self._write_config(payload)
        try:
            cfg = GuardianConfig.from_file(path)
            assert cfg.rules == []
        finally:
            os.unlink(path)


class TestExampleConfigShapeDrift:
    """P-029: keep the test fixture in lockstep with the canonical
    EXAMPLE_CONFIG dict in core/mining_guardian.py without importing the
    module (which pulls heavy deps like websocket). If the source-of-truth
    rule shape changes, this test fails and points to both files to fix."""

    def test_fixture_keys_match_source(self):
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src_path = os.path.join(repo_root, "core", "mining_guardian.py")
        with open(src_path, "r", encoding="utf-8") as f:
            src = f.read()

        # The set of keys ParameterRule(**item) must accept, derived from
        # the canonical EXAMPLE_CONFIG rule dicts.
        expected_rule_keys = {"key", "operator", "expected", "severity",
                              "recommended_fix", "note"}
        for k in expected_rule_keys:
            assert f'"{k}":' in src, (
                f"EXAMPLE_CONFIG in core/mining_guardian.py no longer emits "
                f"the '{k}' rule key. Update tests/test_models.py "
                f"EXAMPLE_CONFIG_RULES to match, then re-run."
            )

        # Any rule key our fixture declares must also exist in the source,
        # so a future trim of EXAMPLE_CONFIG keys doesn't silently leave
        # the test asserting against a stale shape.
        for item in EXAMPLE_CONFIG_RULES:
            for k in item:
                assert f'"{k}":' in src, (
                    f"Test fixture key '{k}' not present in "
                    f"core/mining_guardian.py EXAMPLE_CONFIG."
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
