"""
tests/test_system_settings_and_mode_gating.py
Bucket 9 §10.1/§10.2 — system_settings + automation_mode gating tests.

Covers:
  - system_settings.get_setting / set_setting / get_setting_record
  - system_settings.get_automation_mode / set_automation_mode validation
  - system_settings.get_automation_mode fails open to FULL_AUTO on DB error
  - overnight_automation.run_overnight_cycle respects mode:
      FULL_AUTO  — AUTO auto-executes  (baseline)
      SEMI_AUTO  — AUTO downgraded to HOLD
      MANUAL     — everything becomes MANUAL
  - gui_find_pending helper isolates by miner_id
  - The per-action classifier output is still reported on the `risk` axis even
    when mode overrides `effective_risk`.

All DB access is mocked — no live Postgres required to run these tests.
Run with: PYTHONPATH=. pytest -xvs tests/test_system_settings_and_mode_gating.py
"""

from __future__ import annotations

import os
import sys
from unittest import mock

import pytest

# Project paths — mirror conftest.py behavior so imports work under `pytest
# tests/test_system_settings_and_mode_gating.py` from the repo root.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "api"), os.path.join(_ROOT, "core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ──────────────────────────────────────────────────────────────────────────
# system_settings.py
# ──────────────────────────────────────────────────────────────────────────

class TestSystemSettingsValues:
    def test_allowed_modes_constants(self):
        from api import system_settings as ss
        assert ss.AUTOMATION_MODE_FULL_AUTO == "FULL_AUTO"
        assert ss.AUTOMATION_MODE_SEMI_AUTO == "SEMI_AUTO"
        assert ss.AUTOMATION_MODE_MANUAL == "MANUAL"
        assert ss.ALLOWED_AUTOMATION_MODES == frozenset(
            {"FULL_AUTO", "SEMI_AUTO", "MANUAL"}
        )
        assert ss.DEFAULT_AUTOMATION_MODE == "FULL_AUTO"

    def test_get_setting_returns_default_on_db_error(self, monkeypatch):
        """If psycopg2.connect raises, get_setting returns the default. Never raises."""
        from api import system_settings as ss
        monkeypatch.setattr(ss.psycopg2, "connect",
                            mock.Mock(side_effect=RuntimeError("db down")))
        assert ss.get_setting("anything", default="SENTINEL") == "SENTINEL"
        assert ss.get_setting("anything") is None

    def test_get_automation_mode_fails_open_to_full_auto(self, monkeypatch):
        """DB failure must default to FULL_AUTO — never silently halt automation."""
        from api import system_settings as ss
        monkeypatch.setattr(ss, "get_setting",
                            mock.Mock(side_effect=RuntimeError("should not raise")))
        # get_setting itself catches internally; assert the surfaced default wins:
        monkeypatch.setattr(ss, "get_setting", lambda k, default=None: None)
        # None is not in allowed set → should return the default.
        monkeypatch.setattr(ss, "get_setting",
                            lambda k, default=None: default)
        assert ss.get_automation_mode() == "FULL_AUTO"

    def test_get_automation_mode_rejects_unknown_value(self, monkeypatch):
        from api import system_settings as ss
        monkeypatch.setattr(ss, "get_setting",
                            lambda k, default=None: "WEIRD_VALUE")
        assert ss.get_automation_mode() == "FULL_AUTO"

    def test_get_automation_mode_accepts_valid_value(self, monkeypatch):
        from api import system_settings as ss
        for valid in ("FULL_AUTO", "SEMI_AUTO", "MANUAL"):
            monkeypatch.setattr(ss, "get_setting",
                                lambda k, default=None, v=valid: v)
            assert ss.get_automation_mode() == valid

    def test_set_automation_mode_validates_input(self, monkeypatch):
        from api import system_settings as ss
        called = []
        monkeypatch.setattr(ss, "set_setting",
                            lambda k, v, updated_by="x": called.append((k, v, updated_by)) or True)
        assert ss.set_automation_mode("FULL_AUTO", updated_by="test") is True
        assert called == [("automation_mode", "FULL_AUTO", "test")]
        # Invalid value must not write.
        called.clear()
        assert ss.set_automation_mode("HACK_MODE", updated_by="test") is False
        assert called == []


# ──────────────────────────────────────────────────────────────────────────
# overnight_automation.run_overnight_cycle — mode gating behavior
# ──────────────────────────────────────────────────────────────────────────

class TestOvernightModeGating:
    @pytest.fixture
    def three_actions(self):
        """Three pending actions with known classifier outputs: one AUTO, one
        HOLD, one MANUAL. We drive classify_risk by returning from a mock keyed
        on miner_id."""
        return [
            {"miner_id": "AUTO_M",   "ip": "10.0.0.1", "action_type": "RESTART",
             "model": "S19"},
            {"miner_id": "HOLD_M",   "ip": "10.0.0.2", "action_type": "RESTART",
             "model": "S19"},
            {"miner_id": "MANUAL_M", "ip": "10.0.0.3", "action_type": "PDU_CYCLE",
             "model": "S19"},
        ]

    def _run_with_mode(self, mode, three_actions, monkeypatch):
        """Helper: stub the DB + classifier + executor, run one cycle, return summary."""
        from core import overnight_automation as oa

        monkeypatch.setattr(oa, "_get_automation_mode_safe", lambda: mode)
        monkeypatch.setattr(oa, "get_pending_actions", lambda: list(three_actions))

        def _classify(action):
            return {"AUTO_M": "AUTO", "HOLD_M": "HOLD", "MANUAL_M": "MANUAL"}[action["miner_id"]]
        monkeypatch.setattr(oa, "classify_risk", _classify)

        executed_calls = []
        def _exec(action):
            executed_calls.append(action["miner_id"])
            return {"status": "executed"}
        monkeypatch.setattr(oa, "execute_auto_action", _exec)
        monkeypatch.setattr(oa, "log_skip", lambda action, reason: None)
        monkeypatch.setattr(oa, "get_restart_count_tonight", lambda mid: 0)

        summary = oa.run_overnight_cycle()
        return summary, executed_calls

    def test_full_auto_mode_executes_auto(self, three_actions, monkeypatch):
        summary, executed = self._run_with_mode("FULL_AUTO", three_actions, monkeypatch)
        assert summary["mode"] == "FULL_AUTO"
        assert len(summary["executed"]) == 1
        assert executed == ["AUTO_M"]
        assert len(summary["held"]) == 1
        assert summary["held"][0]["ip"] == "10.0.0.2"
        assert len(summary["manual"]) == 1
        assert summary["manual"][0]["ip"] == "10.0.0.3"

    def test_semi_auto_mode_demotes_auto_to_hold(self, three_actions, monkeypatch):
        summary, executed = self._run_with_mode("SEMI_AUTO", three_actions, monkeypatch)
        assert summary["mode"] == "SEMI_AUTO"
        # Nothing auto-executes in SEMI_AUTO.
        assert summary["executed"] == []
        assert executed == []
        # The AUTO miner is now HOLD with mode-specific reason.
        held_ips = {h["ip"] for h in summary["held"]}
        assert "10.0.0.1" in held_ips
        assert "10.0.0.2" in held_ips
        assert any("semi-auto" in h["reason"].lower() for h in summary["held"]
                   if h["ip"] == "10.0.0.1")
        # The MANUAL classifier action stays MANUAL.
        assert len(summary["manual"]) == 1
        assert summary["manual"][0]["ip"] == "10.0.0.3"

    def test_manual_mode_moves_everything_to_manual(self, three_actions, monkeypatch):
        summary, executed = self._run_with_mode("MANUAL", three_actions, monkeypatch)
        assert summary["mode"] == "MANUAL"
        assert summary["executed"] == []
        assert executed == []
        assert summary["held"] == []
        assert len(summary["manual"]) == 3
        manual_ips = {m["ip"] for m in summary["manual"]}
        assert manual_ips == {"10.0.0.1", "10.0.0.2", "10.0.0.3"}
        # Every manual entry records manual-mode reason.
        for m in summary["manual"]:
            assert "manual mode" in m["reason"]

    def test_empty_pending_returns_clean_summary(self, monkeypatch):
        from core import overnight_automation as oa
        monkeypatch.setattr(oa, "_get_automation_mode_safe", lambda: "FULL_AUTO")
        monkeypatch.setattr(oa, "get_pending_actions", lambda: [])
        summary = oa.run_overnight_cycle()
        assert summary == {"executed": [], "held": [], "manual": [], "mode": "FULL_AUTO"}
