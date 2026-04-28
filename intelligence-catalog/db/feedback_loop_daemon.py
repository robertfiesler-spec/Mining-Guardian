#!/usr/bin/env python3
"""
intelligence-catalog/db/feedback_loop_daemon.py — D-14 PR 4a

C5 operational→catalog feedback DAEMON.

Cron-driven feedback (the original PR #22 wiring) is replaced by an
event-driven LISTEN loop:

    Postgres NOTIFY 'catalog_feedback'  ──►  this daemon  ──►  run_full_feedback_loop()

Per D-14 sub-lock 3:
  - Latency from operational write → catalog refresh ≤ ~100ms.
  - No cron. No polling on the operational tables.
  - The aggregation itself is the existing run_full_feedback_loop()
    orchestrator in feedback_loop.py — we do NOT re-implement it.

Behaviour
---------
1. Open a psycopg2 connection in autocommit mode and `LISTEN catalog_feedback`.
2. Block on `select.select([conn], [], [], idle_timeout)`. When the socket
   becomes readable, drain ALL queued notifications via `conn.poll()` +
   `conn.notifies.pop(0)`.
3. Debounce: once the FIRST notification of a batch is observed, wait an
   additional `debounce_ms` window so a burst of related writes coalesces
   into one feedback-loop invocation. Default 100ms (sub-lock 3 budget).
4. Call `run_full_feedback_loop()` exactly once per debounced batch.
5. On any psycopg2 OperationalError (db restart, network blip, etc.) the
   daemon closes the connection and reconnects with exponential backoff
   capped at `max_backoff_s`. We never lose the daemon.
6. Clean shutdown on SIGTERM/SIGINT — the LISTEN connection is closed and
   the process exits 0.

This file is intentionally dependency-light: it imports ONLY from the
existing feedback_loop module + stdlib + psycopg2 (already a project
dependency). No async runtime, no new deps.

CLI
---
    python -m intelligence-catalog.db.feedback_loop_daemon          # run forever
    python -m intelligence-catalog.db.feedback_loop_daemon --once   # single debounce cycle, then exit
    python -m intelligence-catalog.db.feedback_loop_daemon --verbose
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import select
import signal
import sys
import time
from typing import Any, Optional

# Reuse the existing connection helper + orchestrator. The two modules live
# in the same package (intelligence-catalog/db/), so a relative import is the
# right shape — but because this file is also runnable as a script via the
# launchd/systemd unit, we fall back to a path-based import when __package__
# is None.
try:                                  # pragma: no cover - import-mode dependent
    from .feedback_loop import _get_connection, run_full_feedback_loop  # type: ignore
except ImportError:                   # pragma: no cover - script-mode fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    if _here not in sys.path:
        sys.path.insert(0, _here)
    from feedback_loop import _get_connection, run_full_feedback_loop  # type: ignore


LOG = logging.getLogger("mg.feedback_loop_daemon")

# Channel name MUST match migrations/003_c5_notify_triggers.sql
CHANNEL = "catalog_feedback"

# Debounce window for coalescing a NOTIFY burst into one orchestrator call.
# Sub-lock 3 budgets ~100ms end-to-end; we use 100ms by default.
DEFAULT_DEBOUNCE_MS = 100

# How long select.select blocks when no NOTIFY is pending. Keeping this
# short (1s) means SIGTERM is honoured promptly.
DEFAULT_IDLE_TIMEOUT_S = 1.0

# Reconnect backoff schedule.
INITIAL_BACKOFF_S = 1.0
MAX_BACKOFF_S = 30.0


# ──────────────────────────────────────────────────────────────────────────
# Daemon
# ──────────────────────────────────────────────────────────────────────────

class FeedbackLoopDaemon:
    """LISTEN-driven runner for run_full_feedback_loop().

    Not thread-safe — one daemon per process.
    """

    def __init__(
        self,
        *,
        debounce_ms: int = DEFAULT_DEBOUNCE_MS,
        idle_timeout_s: float = DEFAULT_IDLE_TIMEOUT_S,
        run_once: bool = False,
    ) -> None:
        self.debounce_s = max(0, debounce_ms) / 1000.0
        self.idle_timeout_s = max(0.05, idle_timeout_s)
        self.run_once = run_once
        self._stop = False
        self._conn = None  # psycopg2 connection
        self._backoff_s = INITIAL_BACKOFF_S
        # counters for observability (printed on shutdown / --once)
        self.batches_processed = 0
        self.notifications_seen = 0

    # -- signals --------------------------------------------------------
    def install_signal_handlers(self) -> None:
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, self._on_signal)
            except (ValueError, OSError):
                # Some environments (e.g. embedded test harnesses) disallow
                # signal handler installation. Daemon still works there if
                # the caller drives _stop manually.
                pass

    def _on_signal(self, signum: int, _frame: Any) -> None:
        LOG.info("signal %s received — stopping daemon", signum)
        self._stop = True

    def stop(self) -> None:
        """Programmatic shutdown (used by tests)."""
        self._stop = True

    # -- connection -----------------------------------------------------
    def _connect_and_listen(self) -> bool:
        """Open a connection, set autocommit, and LISTEN. Returns True on success."""
        conn = _get_connection()
        if conn is None:
            LOG.error("cannot open Postgres connection (psycopg2 missing or MG_DB_PASSWORD unset?)")
            return False
        try:
            conn.set_isolation_level(0)  # ISOLATION_LEVEL_AUTOCOMMIT
            with conn.cursor() as cur:
                cur.execute(f"LISTEN {CHANNEL};")
            self._conn = conn
            self._backoff_s = INITIAL_BACKOFF_S  # reset on success
            LOG.info("LISTEN %s established (fd=%s)", CHANNEL, conn.fileno())
            return True
        except Exception as exc:
            LOG.error("LISTEN setup failed: %s", exc)
            try:
                conn.close()
            except Exception:
                pass
            self._conn = None
            return False

    def _close_conn(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _backoff(self) -> None:
        sleep_s = self._backoff_s
        LOG.warning("reconnecting in %.1fs", sleep_s)
        # Sleep in small chunks so SIGTERM is honoured promptly.
        deadline = time.monotonic() + sleep_s
        while not self._stop and time.monotonic() < deadline:
            time.sleep(min(0.25, deadline - time.monotonic()))
        self._backoff_s = min(self._backoff_s * 2.0, MAX_BACKOFF_S)

    # -- loop -----------------------------------------------------------
    def run(self) -> int:
        """Main loop. Returns process exit code."""
        self.install_signal_handlers()
        LOG.info(
            "feedback_loop_daemon starting — debounce=%dms idle_timeout=%.1fs run_once=%s",
            int(self.debounce_s * 1000), self.idle_timeout_s, self.run_once,
        )

        while not self._stop:
            if self._conn is None:
                if not self._connect_and_listen():
                    if self.run_once:
                        return 1
                    self._backoff()
                    continue

            try:
                processed = self._wait_and_process_one_batch()
            except Exception as exc:
                # psycopg2.OperationalError, InterfaceError, network drop …
                LOG.error("daemon loop error: %s — closing connection", exc)
                self._close_conn()
                if self.run_once:
                    return 1
                self._backoff()
                continue

            if self.run_once and processed:
                LOG.info("--once: processed one batch — exiting")
                break

        self._close_conn()
        LOG.info(
            "feedback_loop_daemon stopped — batches=%d notifications=%d",
            self.batches_processed, self.notifications_seen,
        )
        return 0

    def _wait_and_process_one_batch(self) -> bool:
        """Block on select; if NOTIFY arrives, debounce, then run the loop.

        Returns True iff a batch was processed.
        """
        assert self._conn is not None

        # Block until the connection socket becomes readable OR idle timeout.
        readable, _, _ = select.select([self._conn], [], [], self.idle_timeout_s)
        if not readable:
            return False

        # Drain notifications and apply debounce window.
        first_notify_ts = time.monotonic()
        first_payload = self._drain_notifies()
        if not first_payload:
            return False

        # While we are inside the debounce window, keep draining anything
        # else that arrives so a burst of related INSERTs collapses into one
        # call to run_full_feedback_loop().
        deadline = first_notify_ts + self.debounce_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or self._stop:
                break
            r2, _, _ = select.select([self._conn], [], [], remaining)
            if not r2:
                break
            self._drain_notifies()

        self.batches_processed += 1
        return self._invoke_orchestrator(first_payload)

    def _drain_notifies(self) -> Optional[dict]:
        """Pull every queued NOTIFY off the connection.

        Returns the FIRST notification payload (parsed) seen this drain,
        or None if there were no notifications. The remaining payloads are
        intentionally discarded — the orchestrator re-aggregates from SQL,
        so we only need to know that *something* changed.
        """
        assert self._conn is not None
        first: Optional[dict] = None
        self._conn.poll()
        while self._conn.notifies:
            n = self._conn.notifies.pop(0)
            self.notifications_seen += 1
            if first is None:
                try:
                    first = json.loads(n.payload) if n.payload else {}
                except Exception:
                    first = {"raw": n.payload}
                LOG.info("NOTIFY %s pid=%s payload=%s", n.channel, n.pid, n.payload)
            else:
                LOG.debug("coalesced NOTIFY pid=%s payload=%s", n.pid, n.payload)
        return first

    def _invoke_orchestrator(self, trigger_payload: dict) -> bool:
        """Run the existing C5 feedback orchestrator. Always logs the result."""
        LOG.info("running run_full_feedback_loop (trigger=%s)", trigger_payload)
        t0 = time.monotonic()
        try:
            stats = run_full_feedback_loop()
        except Exception as exc:
            LOG.error("run_full_feedback_loop crashed: %s", exc, exc_info=True)
            return True  # batch was 'processed' even if it errored
        dt_ms = int((time.monotonic() - t0) * 1000)
        LOG.info("feedback loop OK in %dms — stats=%s", dt_ms, json.dumps(stats, default=str))
        return True


# ──────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="C5 NOTIFY/LISTEN daemon — runs run_full_feedback_loop on every operational write.",
    )
    p.add_argument("--once", action="store_true",
                   help="Process exactly one debounced batch then exit (smoke test mode).")
    p.add_argument("--debounce-ms", type=int, default=DEFAULT_DEBOUNCE_MS,
                   help=f"Coalescence window in ms (default {DEFAULT_DEBOUNCE_MS}).")
    p.add_argument("--idle-timeout-s", type=float, default=DEFAULT_IDLE_TIMEOUT_S,
                   help="select() blocking timeout when idle (default 1.0).")
    p.add_argument("--verbose", "-v", action="store_true")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_argparser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    daemon = FeedbackLoopDaemon(
        debounce_ms=args.debounce_ms,
        idle_timeout_s=args.idle_timeout_s,
        run_once=args.once,
    )
    return daemon.run()


if __name__ == "__main__":
    sys.exit(main())
