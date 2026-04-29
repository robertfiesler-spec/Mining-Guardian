# Mining Guardian — Testing Guide

**Last Updated:** 2026-04-29

---

## Overview

Mining Guardian uses **pytest** for automated testing. Tests run automatically on every commit via a pre-commit hook.

The catalog DB lives in PostgreSQL 16 on the Mac Mini; tests do not require a live catalog connection — fixtures use temporary local databases or in-memory mocks.

## Quick Start

```bash
cd ~/Documents/GitHub/Mining-Guardian
source venv/bin/activate
PYTHONPATH=. pytest tests/ -v
```

## Test Suite Summary

| Module | Tests | What It Tests |
|--------|-------|---------------|
| test_database.py | 8 | Legacy `core/database.GuardianDB` layer (slated for removal post-install — see `docs/LATENT_BUGS.md`) |
| test_models.py | 9 | Dataclasses, rule evaluation, cooldown logic |
| test_ams_client.py | 3 | BiXBiT AMS API client initialization |
| test_hvac_client.py | 6 | HVAC systems (warehouse + S19JPro container) |
| test_slack_notifier.py | 5 | Slack messaging configuration |
| test_weather_collector.py | 4 | Open-Meteo API, Fort Worth coordinates |
| test_approval_interface.py | 3 | Manual approval flow |
| test_dashboard_api.py | 6 | FastAPI routes, rate limiting |
| test_system_schedules.py | 23 | Operator-controlled schedules (§10.7), DOW parsing, window evaluation |
| test_system_settings_and_mode_gating.py | 10 | Automation mode (full / semi / manual), setting persistence, action gating |
| **Total** | **77** | **~2 second runtime** |

## Running Tests

### Run All Tests
```bash
pytest tests/ -v
```

### Run Specific Test File
```bash
pytest tests/test_system_schedules.py -v
```

### Run with Coverage Report
```bash
pytest tests/ --cov=core --cov=clients --cov=notifiers --cov=approval_api --cov-report=term-missing
```

### Run Single Test
```bash
pytest tests/test_hvac_client.py::TestHVACClientInit::test_init_warehouse_default -v
```

## Pre-Commit Hook

Every `git commit` automatically:
1. Runs all 77 tests
2. Scans for secrets (API keys, tokens, password literals)
3. Blocks commit if either fails

Location: `.git/hooks/pre-commit`

## Test Fixtures (conftest.py)

| Fixture | Purpose |
|---------|---------|
| `temp_db` | Creates a temporary local DB file for `core.database.GuardianDB` legacy tests |
| `mock_config` | Returns `GuardianConfig` with test credentials |
| `sample_miner_data` | Returns realistic miner data structure |

## Adding New Tests

1. Create `tests/test_<module>.py`
2. Import the module being tested
3. Create test classes with `Test` prefix
4. Create test methods with `test_` prefix

Example:
```python
import pytest
from clients.my_client import MyClient

class TestMyClientInit:
    def test_init_with_defaults(self):
        client = MyClient()
        assert client is not None
```

## Why Tests Matter

1. **Catch bugs before production** — Refactoring is safe
2. **Living documentation** — Tests show how code should be used
3. **Confidence to change** — Run tests, see green, ship it
4. **Pre-commit guardrail** — Broken code can't be pushed

---

## Dependencies

- pytest >= 9.0
- pytest-cov >= 7.0

Install: `pip install pytest pytest-cov`
