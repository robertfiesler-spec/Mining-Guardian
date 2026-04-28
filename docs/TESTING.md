# Mining Guardian — Testing Guide

**Last Updated:** 2026-04-21

---

## Overview

Mining Guardian uses **pytest** for automated testing. Tests run automatically on every commit via a pre-commit hook.

## Quick Start

```bash
cd /root/Mining-Guardian
source venv/bin/activate
PYTHONPATH=/root/Mining-Guardian pytest tests/ -v
```

## Test Suite Summary

| Module | Tests | What It Tests |
|--------|-------|---------------|
| test_database.py | 8 | SQLite layer, WAL mode, table creation, audit logging |
| test_models.py | 9 | Dataclasses, rule evaluation, cooldown logic |
| test_ams_client.py | 3 | BiXBiT AMS API client initialization |
| test_hvac_client.py | 6 | HVAC systems (warehouse + S19JPro container) |
| test_slack_notifier.py | 5 | Slack messaging configuration |
| test_openclaw_notifier.py | 4 | OpenClaw webhook client |
| test_weather_collector.py | 4 | Open-Meteo API, Fort Worth coordinates |
| test_approval_interface.py | 3 | Manual approval flow |
| test_dashboard_api.py | 6 | FastAPI routes, rate limiting |
| **Total** | **48** | **~1 second runtime** |

## Running Tests

### Run All Tests
```bash
pytest tests/ -v
```

### Run Specific Test File
```bash
pytest tests/test_database.py -v
```

### Run with Coverage Report
```bash
pytest tests/ --cov=core --cov=clients --cov=notifiers --cov-report=term-missing
```

### Run Single Test
```bash
pytest tests/test_hvac_client.py::TestHVACClientInit::test_init_warehouse_default -v
```

## Pre-Commit Hook

Every `git commit` automatically:
1. Runs all 48 tests
2. Scans for secrets (API keys, tokens)
3. Blocks commit if either fails

Location: `.git/hooks/pre-commit`

## Test Fixtures (conftest.py)

| Fixture | Purpose |
|---------|---------|
| `temp_db` | Creates temporary SQLite database for testing |
| `mock_config` | Returns GuardianConfig with test credentials |
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
4. **Pre-commit guardrail** — Broken code cant be pushed

---

## Dependencies

- pytest >= 9.0
- pytest-cov >= 7.0

Install: `pip install pytest pytest-cov`
