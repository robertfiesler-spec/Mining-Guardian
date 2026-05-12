#!/usr/bin/env python3
"""
Extended W14a import test — tests not just the launchd entry points,
but ALSO the 5 PR #188 files (which are imported by parent callers)
AND the scanner entry point (which imports through the AI files).

Exit 0 if all pass, 1 if any fail.
"""
import sys
import importlib.util
import traceback
from pathlib import Path

TEST_ROOT = "/tmp/w14a-fix-staging-test"

FILES_TO_TEST = [
    # Layer 1 — direct entry points (PR #187)
    ("ams_alert_listener",      f"{TEST_ROOT}/api/ams_alert_listener.py",     "entry point"),
    ("approval_api",            f"{TEST_ROOT}/api/approval_api.py",           "entry point"),
    ("dashboard_api",           f"{TEST_ROOT}/api/dashboard_api.py",          "entry point"),
    ("intelligence_report_api", f"{TEST_ROOT}/api/intelligence_report_api.py","entry point"),
    ("slack_approval_listener", f"{TEST_ROOT}/api/slack_approval_listener.py","entry point"),
    ("slack_command_handler",   f"{TEST_ROOT}/api/slack_command_handler.py",  "entry point"),
    ("overnight_automation",    f"{TEST_ROOT}/core/overnight_automation.py",  "entry point"),

    # Layer 2 — PR #188 files (could also be entry points)
    ("ai_dashboard_api",        f"{TEST_ROOT}/api/ai_dashboard_api.py",       "PR #188 fix"),
    ("confidence_scorer",       f"{TEST_ROOT}/ai/confidence_scorer.py",       "PR #188 fix"),
    ("fingerprint_builder",     f"{TEST_ROOT}/ai/fingerprint_builder.py",     "PR #188 fix"),
    ("hvac_correlator",         f"{TEST_ROOT}/ai/hvac_correlator.py",         "PR #188 fix"),
    ("train_cohort",            f"{TEST_ROOT}/ai/train_cohort.py",            "PR #188 fix"),

    # Layer 3 — scanner (mining_guardian) — imports the full graph
    ("mining_guardian",         f"{TEST_ROOT}/core/mining_guardian.py",       "scanner entry point"),
]

print(f"Testing {len(FILES_TO_TEST)} files at {TEST_ROOT}")
print()

results = []
for module_name, file_path, kind in FILES_TO_TEST:
    if not Path(file_path).exists():
        print(f"  ❌ {module_name} ({kind}): FILE NOT FOUND at {file_path}")
        results.append(False)
        continue

    saved_path = sys.path[:]
    saved_modules = set(sys.modules.keys())
    try:
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            print(f"  ❌ {module_name} ({kind}): spec_from_file_location returned None")
            results.append(False)
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        print(f"  ✅ {module_name} ({kind}): imports cleanly")
        results.append(True)
    except Exception:
        print(f"  ❌ {module_name} ({kind}): FAILED")
        print("     Traceback:")
        tb_lines = traceback.format_exc().splitlines()
        for line in tb_lines:
            print(f"     {line}")
        results.append(False)
    finally:
        sys.path[:] = saved_path
        for mod_name in list(sys.modules.keys()):
            if mod_name not in saved_modules:
                del sys.modules[mod_name]

print()
print("=" * 60)
passed = sum(results)
total = len(results)
if passed == total:
    print(f"✅ ALL {total}/{total} import tests PASSED")
    sys.exit(0)
else:
    print(f"❌ {passed}/{total} passed, {total - passed} FAILED")
    sys.exit(1)
