"""
Tests for the models module (dataclasses and utilities).
Created April 21, 2026 as part of Phase 4 testing infrastructure.
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import (
    ParameterRule,
    MinerFinding,
    GuardianConfig,
    PolicyEngine,
    RemediationPlanner,
    RemediationCooldown,
)


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
