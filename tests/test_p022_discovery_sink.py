"""tests/test_p022_discovery_sink.py

P-022 (2026-05-08) — scanner discovery JSON sink regression guard.

Background
----------
Audit on 2026-05-08 found the daily catalog-import job had nothing to
import on customer Macs: ``cron_tracking/`` was empty, and the
scanner's discovery findings (``DISCOVERY: Unknown model detected:
S19JPro at 192.168.188.36`` etc.) were persisted only to the
``discovery_log`` Postgres table — never to the file-based intake
surface every other catalog-bound source uses. P-022 closes that gap
by adding ``core/discovery_sink.py``, called from both branches of
``mining_guardian.py::_track_discoveries``.

This test:
  * exercises the public API (``record_discovery``, ``read_latest``,
    ``resolve_sink_dir``)
  * proves the rolling JSON dedup logic
  * proves atomic-write safety (a torn previous write must not crash
    the next call)
  * proves a missing/unwritable sink dir is non-fatal
  * proves the JSONL audit trail captures every observation, not just
    the dedup'd snapshot
  * proves the wrapper script ``run_daily_catalog_import.sh``
    references the sink path so the daily job surfaces presence

It does NOT exercise the scanner's hot path end-to-end (psycopg2 isn't
in this sandbox); a separate scanner-integration test belongs in a
follow-up PR.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _import_sink():
    import importlib
    return importlib.import_module("core.discovery_sink")


class TestSinkResolveDir(unittest.TestCase):
    """``resolve_sink_dir`` resolution order matches the spec."""

    def setUp(self) -> None:
        self.sink = _import_sink()
        self._saved = {
            k: os.environ.pop(k, None)
            for k in ("MG_DISCOVERY_SINK_DIR", "MG_INSTALL_ROOT")
        }

    def tearDown(self) -> None:
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v

    def test_explicit_override_wins(self) -> None:
        # NOTE (P-022 portability fix, 2026-05-08): both sides go through
        # `os.path.realpath` because macOS canonicalises ``/tmp`` →
        # ``/private/tmp`` (it's a symlink), and the helper itself uses
        # ``Path(...).expanduser().resolve()`` which follows that
        # symlink. Compare canonicalised paths so the test passes on
        # both Darwin and Linux — sandbox dirs from ``tempfile`` may
        # also live under ``/var/folders/...`` on macOS, which the same
        # ``realpath`` normalisation handles.
        os.environ["MG_DISCOVERY_SINK_DIR"] = "/tmp/explicit-sink"
        os.environ["MG_INSTALL_ROOT"] = "/tmp/install-root"
        self.assertEqual(
            os.path.realpath(str(self.sink.resolve_sink_dir())),
            os.path.realpath("/tmp/explicit-sink"),
        )

    def test_install_root_used_when_no_override(self) -> None:
        os.environ["MG_INSTALL_ROOT"] = "/tmp/install-root"
        self.assertEqual(
            os.path.realpath(str(self.sink.resolve_sink_dir())),
            os.path.realpath(
                "/tmp/install-root/cron_tracking/scanner_discovery"
            ),
        )

    def test_falls_back_to_repo_root(self) -> None:
        # No envs — uses _ROOT (the repo root inferred from the module's
        # own location).
        sink_dir = self.sink.resolve_sink_dir()
        self.assertTrue(
            str(sink_dir).endswith(
                os.path.join("cron_tracking", "scanner_discovery")
            ),
            f"got {sink_dir!r}",
        )


class TestRecordDiscovery(unittest.TestCase):
    """End-to-end: ``record_discovery`` writes the rolling JSON +
    append-only JSONL."""

    def setUp(self) -> None:
        self.sink = _import_sink()
        self.tmp = tempfile.mkdtemp(prefix="p022-sink-test-")
        os.environ["MG_DISCOVERY_SINK_DIR"] = self.tmp

    def tearDown(self) -> None:
        os.environ.pop("MG_DISCOVERY_SINK_DIR", None)
        # Cheap cleanup — best-effort.
        for child in Path(self.tmp).rglob("*"):
            try:
                child.unlink()
            except (OSError, IsADirectoryError):
                pass
        try:
            Path(self.tmp).rmdir()
        except OSError:
            pass

    # ---- shape ----

    def test_unknown_model_event_landed(self) -> None:
        ok = self.sink.record_discovery(
            "unknown_model",
            {"model_name": "S19JPro", "ip": "192.168.188.36"},
        )
        self.assertTrue(ok)
        latest = self.sink.read_latest()
        self.assertIn("events", latest)
        self.assertEqual(len(latest["events"]), 1)
        evt = list(latest["events"].values())[0]
        self.assertEqual(evt["event_type"], "unknown_model")
        self.assertEqual(evt["model_name"], "S19JPro")
        self.assertEqual(evt["count"], 1)
        self.assertEqual(evt["ips"], ["192.168.188.36"])
        self.assertEqual(evt["source"], "scanner_discovery")
        self.assertIn("first_seen", evt)
        self.assertIn("last_seen", evt)
        self.assertEqual(evt["first_seen"], evt["last_seen"])

    def test_new_firmware_event_landed(self) -> None:
        ok = self.sink.record_discovery(
            "new_firmware",
            {
                "model_name": "S19JPro",
                "firmware_version": "0.9.9.3-stage29.2799",
                "ip": "192.168.188.36",
                "miner_id": 54504,
            },
        )
        self.assertTrue(ok)
        latest = self.sink.read_latest()
        evt = list(latest["events"].values())[0]
        self.assertEqual(evt["event_type"], "new_firmware")
        self.assertEqual(evt["firmware_version"], "0.9.9.3-stage29.2799")
        self.assertEqual(evt["miner_id_examples"], ["54504"])

    # ---- dedup ----

    def test_repeat_unknown_model_increments_count_not_keys(self) -> None:
        for _ in range(5):
            self.sink.record_discovery(
                "unknown_model",
                {"model_name": "AH3880", "ip": "192.168.188.51"},
            )
        latest = self.sink.read_latest()
        self.assertEqual(len(latest["events"]), 1)
        evt = list(latest["events"].values())[0]
        self.assertEqual(evt["count"], 5)
        # Same IP each time — should not duplicate in the ips list.
        self.assertEqual(evt["ips"], ["192.168.188.51"])

    def test_distinct_ips_accumulate(self) -> None:
        for ip in ("192.168.188.36", "192.168.188.37", "192.168.188.38"):
            self.sink.record_discovery(
                "unknown_model",
                {"model_name": "S19JPro", "ip": ip},
            )
        evt = list(self.sink.read_latest()["events"].values())[0]
        self.assertEqual(set(evt["ips"]), {
            "192.168.188.36", "192.168.188.37", "192.168.188.38",
        })
        self.assertEqual(evt["count"], 3)

    def test_ips_capped_at_max(self) -> None:
        # 32 distinct IPs — should be trimmed to the cap (16 per
        # _MAX_IPS_PER_KEY).
        for i in range(32):
            self.sink.record_discovery(
                "unknown_model",
                {"model_name": "BigFleet", "ip": f"10.0.0.{i}"},
            )
        evt = list(self.sink.read_latest()["events"].values())[0]
        self.assertEqual(evt["count"], 32)
        self.assertEqual(len(evt["ips"]), 16)

    def test_distinct_event_types_create_distinct_keys(self) -> None:
        self.sink.record_discovery(
            "unknown_model", {"model_name": "S19JPro"}
        )
        self.sink.record_discovery(
            "new_firmware",
            {"model_name": "S19JPro",
             "firmware_version": "0.9.9.3-stage29.2799"},
        )
        latest = self.sink.read_latest()
        self.assertEqual(len(latest["events"]), 2)

    def test_distinct_firmware_versions_create_distinct_keys(self) -> None:
        for fw in ("v1", "v2", "v3"):
            self.sink.record_discovery(
                "new_firmware",
                {"model_name": "S21Imm", "firmware_version": fw},
            )
        self.assertEqual(len(self.sink.read_latest()["events"]), 3)

    # ---- jsonl audit ----

    def test_jsonl_appends_every_event(self) -> None:
        for ip in ("a", "b", "a", "a", "b"):
            self.sink.record_discovery(
                "unknown_model",
                {"model_name": "S19JPro", "ip": ip},
            )
        files = list(Path(self.tmp).glob("events-*.jsonl"))
        self.assertEqual(len(files), 1)
        lines = files[0].read_text(encoding="utf-8").splitlines()
        # Every record_discovery call lands one line, regardless of dedup.
        self.assertEqual(len(lines), 5)
        # Each line is valid JSON with the expected keys.
        for line in lines:
            record = json.loads(line)
            for key in ("ts", "event_type", "model_name", "source"):
                self.assertIn(key, record)
            self.assertEqual(record["source"], "scanner_discovery")

    # ---- robustness ----

    def test_corrupted_latest_is_reset_in_place(self) -> None:
        # Pre-populate with junk.
        sink_dir = Path(self.tmp)
        sink_dir.mkdir(parents=True, exist_ok=True)
        (sink_dir / "latest_findings.json").write_text("not json{}{[")
        # Should not raise; the rolling file resets and the new event lands.
        ok = self.sink.record_discovery(
            "unknown_model",
            {"model_name": "S19JPro", "ip": "1.2.3.4"},
        )
        self.assertTrue(ok)
        latest = self.sink.read_latest()
        self.assertEqual(len(latest["events"]), 1)

    def test_unwritable_sink_dir_is_non_fatal(self) -> None:
        # Point at a path that exists as a file (so mkdir refuses).
        bogus = tempfile.NamedTemporaryFile(delete=False)
        bogus.write(b"x")
        bogus.close()
        try:
            os.environ["MG_DISCOVERY_SINK_DIR"] = bogus.name
            ok = self.sink.record_discovery(
                "unknown_model", {"model_name": "X"},
            )
            # Returns False, doesn't raise. Scanner hot path is safe.
            self.assertFalse(ok)
        finally:
            os.unlink(bogus.name)

    def test_payload_must_be_dict(self) -> None:
        # `None` is the documented default (helper substitutes {}), so
        # it's tolerated.
        self.assertTrue(self.sink.record_discovery("unknown_model", None))
        # Type-junk payloads (non-dict, non-None): helper logs WARNING
        # and returns False, never raises.
        self.assertFalse(self.sink.record_discovery("unknown_model", "string"))
        self.assertFalse(self.sink.record_discovery("unknown_model", [1, 2, 3]))

    def test_unfamiliar_event_type_still_recorded(self) -> None:
        # Forward-compat: a future caller emits a new event_type. Helper
        # logs INFO but stores it — it does NOT crash or skip.
        ok = self.sink.record_discovery(
            "control_board_observed",
            {"model_name": "S19JPro", "ip": "1.2.3.4"},
        )
        self.assertTrue(ok)
        latest = self.sink.read_latest()
        self.assertEqual(len(latest["events"]), 1)


class TestScannerWiring(unittest.TestCase):
    """The scanner's ``_track_discoveries`` calls ``record_discovery``
    in BOTH branches (unknown_model AND new_firmware)."""

    def test_scanner_imports_record_discovery_in_both_branches(self) -> None:
        src = (REPO_ROOT / "core" / "mining_guardian.py").read_text()
        # The discovery method's actual name is _check_discoveries (per
        # core/mining_guardian.py:192). Capture from its def to the next
        # def at the same indent level.
        import re
        m = re.search(
            r"def _check_discoveries\(.*?\n(.*?)\n    def [_A-Za-z]",
            src,
            re.S,
        )
        self.assertIsNotNone(m, "_check_discoveries not found")
        body = m.group(1)
        # Both branches should call record_discovery (one for
        # unknown_model, one for new_firmware).
        self.assertGreaterEqual(
            body.count("record_discovery"), 2,
            "_check_discoveries must call record_discovery in BOTH "
            "the unknown_model AND new_firmware branches",
        )
        for evt in ('"unknown_model"', '"new_firmware"'):
            self.assertIn(
                evt, body,
                f"_check_discoveries must record event_type={evt}",
            )


class TestDailyImportWrapperSurfaces(unittest.TestCase):
    """``run_daily_catalog_import.sh`` surfaces scanner_discovery
    presence + count in its INFO output, not silently."""

    def setUp(self) -> None:
        self.wrapper = REPO_ROOT / "intelligence-catalog/tools/run_daily_catalog_import.sh"
        self.assertTrue(self.wrapper.exists())
        self.body = self.wrapper.read_text()

    def test_wrapper_references_scanner_discovery_path(self) -> None:
        self.assertIn(
            "cron_tracking/scanner_discovery",
            self.body,
            "wrapper must reference the scanner_discovery sink dir",
        )

    def test_wrapper_logs_findings_count(self) -> None:
        self.assertIn(
            "scanner_discovery findings",
            self.body,
            "wrapper must surface scanner_discovery findings (presence + count)",
        )

    def test_wrapper_no_longer_aborts_when_only_sweep_dir_missing(self) -> None:
        # Pre-P-022 the wrapper exited 0 with INFO if SWEEP_DIR was
        # missing, BEFORE the scanner_discovery probe ever ran. After
        # P-022 the early-out must come AFTER the probe so the probe
        # executes regardless of SWEEP_DIR's presence.
        #
        # We strip comments first (a `# … exit 0 (not an error; …)`
        # comment up at line 26 is documentation, not control flow) and
        # then check that the *first executable* `exit 0` follows the
        # scanner_discovery probe.
        import re
        # Drop full-line shell comments so the matcher sees only code.
        non_comment_lines = []
        for raw in self.body.splitlines():
            stripped = raw.lstrip()
            if stripped.startswith("#"):
                continue
            # Trim trailing inline `# ...` comments without breaking
            # quoted strings — for this script the trailing-comment
            # pattern is only used after bare commands, so a simple
            # split on the literal '# ' suffix is sufficient.
            non_comment_lines.append(raw)
        code_only = "\n".join(non_comment_lines)
        idx_probe = code_only.find("scanner_discovery findings")
        idx_exit = code_only.rfind("exit 0", 0, idx_probe) if idx_probe > 0 else -1
        self.assertGreater(
            idx_probe, 0,
            "wrapper code (comments stripped) missing scanner_discovery "
            "probe text",
        )
        self.assertLess(
            idx_exit, 0,
            "wrapper still has an executable `exit 0` before the "
            "scanner_discovery probe — the probe will never run when "
            "SWEEP_DIR is empty (the common customer case)",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
