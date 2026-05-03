"""
tests/console/conftest.py — pytest fixtures for the D-19 console tests.

Forces eager import of api.system_settings so unittest.mock.patch can
locate `api.system_settings.X` regardless of import order. Also adds the
project root to sys.path (already done in tests/conftest.py for the
top-level suite, but conftest under tests/console/ is loaded by pytest
before the parent in some contexts).
"""

import os
import sys

# Add project root to path even if pytest is invoked from a subdirectory.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Eagerly import api.system_settings so `unittest.mock.patch("api.system_settings.X")`
# resolves cleanly even if no test has imported it yet.
import api.system_settings  # noqa: F401,E402

# Mock launchctl by default; opt out per-test.
os.environ.setdefault("MG_CONSOLE_LAUNCHCTL", "mock")
