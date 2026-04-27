#!/usr/bin/env python3
"""Tests for intelligence-catalog/db/feedback_loop.py (C5 / PR #22).

These exercise the C5 feedback loop end-to-end against a live Postgres
sandbox: insert source rows in `public.*`, run the sync, and assert that
the catalog tables (`ops.failure_patterns`, `market.war_stories`,
`hardware.model_known_issues`) received the expected upserts.

Tests are isolated by a per-run UUID so they're safe to interleave with
other PRs.

Run:
    PGHOST=/tmp PGPORT=5433 MG_DB_PASSWORD=sandbox \
        python -m unittest intelligence_catalog.db.tests.test_feedback_loop
"""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "_feedback_loop",
    ROOT / "intelligence-catalog" / "db" / "feedback_loop.py",
)
fb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fb)


def _have_db() -> bool:
    conn = fb._get_connection()
    if conn is None:
        return False
    conn.close()
    return True


@unittest.skipUnless(_have_db(), "no Postgres reachable; skipping integration tests")
class TestFeedbackLoopHelpers(unittest.TestCase):
    """Pure-Python helpers that don't touch the DB."""

    def test_pattern_code_is_deterministic(self):
        a = fb._pattern_code("OP", "Antminer S19", "high temp")
        b = fb._pattern_code("OP", "Antminer S19", "high temp")
        self.assertEqual(a, b)

    def test_pattern_code_changes_with_input(self):
        a = fb._pattern_code("OP", "Antminer S19", "high temp")
        b = fb._pattern_code("OP", "Antminer S19", "low hashrate")
        self.assertNotEqual(a, b)

    def test_classify_severity_scales(self):
        self.assertEqual(fb._classify_severity(60, 0), "critical")
        self.assertEqual(fb._classify_severity(25, 0), "high")
        self.assertEqual(fb._classify_severity(10, 0), "medium")
        self.assertEqual(fb._classify_severity(2, 0), "low")
        # denied-heavy small sample → high
        self.assertEqual(fb._classify_severity(2, 2), "high")

    def test_classify_root_cause(self):
        self.assertEqual(fb._classify_root_cause("Board over temp warning"), "thermal")
        self.assertEqual(fb._classify_root_cause("hashrate dropped to 50%"), "performance")
        self.assertEqual(fb._classify_root_cause("Miner offline, network unreachable"), "network")
        self.assertEqual(fb._classify_root_cause("Random unknown thing"), "unknown")

    def test_classify_commonality(self):
        self.assertEqual(fb._classify_commonality(0.6, 100), "widespread")
        self.assertEqual(fb._classify_commonality(0.3, 50), "common")
        self.assertEqual(fb._classify_commonality(0.1, 50), "occasional")
        self.assertEqual(fb._classify_commonality(0.01, 50), "rare")
        self.assertEqual(fb._classify_commonality(0.5, 3), "isolated")

    def test_extract_topic_tags(self):
        tags = fb._extract_topic_tags("The miner overheated and the chip failed.")
        self.assertIn("thermal", tags)
        self.assertIn("hardware", tags)


@unittest.skipUnless(_have_db(), "no Postgres reachable; skipping integration tests")
class TestFeedbackLoopRoundTrip(unittest.TestCase):
    """End-to-end: source rows in public.* → catalog rows in ops/market/hardware."""

    @classmethod
    def setUpClass(cls):
        cls.run_id = uuid4().hex[:8]
        cls.miner_id = f"test-{cls.run_id}-miner"
        cls.model_text = f"TestModel-{cls.run_id}"
        cls.problem_text = f"test problem {cls.run_id}"
        cls.conn = fb._get_connection()
        assert cls.conn is not None

        with cls.conn.cursor() as cur:
            # Ensure source tables exist (test-only migration, idempotent)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.action_audit_log (
                    id           SERIAL PRIMARY KEY,
                    timestamp    TIMESTAMP WITH TIME ZONE NOT NULL,
                    date         DATE NOT NULL,
                    scan_id      INTEGER,
                    miner_id     TEXT NOT NULL,
                    ip           TEXT NOT NULL,
                    model        TEXT,
                    problem      TEXT NOT NULL,
                    action_taken TEXT NOT NULL,
                    decision     TEXT NOT NULL,
                    approved_by  TEXT,
                    notes        TEXT
                );
                CREATE TABLE IF NOT EXISTS public.miner_restarts (
                    id                  SERIAL PRIMARY KEY,
                    restarted_at        TIMESTAMP WITH TIME ZONE NOT NULL,
                    miner_id            TEXT NOT NULL,
                    ip                  TEXT,
                    model               TEXT,
                    restart_type        TEXT,
                    elevated_until      TEXT,
                    outcome             TEXT,
                    outcome_checked_at  TEXT,
                    hashrate_before     REAL,
                    hashrate_after      REAL,
                    recovery_time_scans INTEGER
                );
                CREATE TABLE IF NOT EXISTS public.llm_analysis (
                    id          SERIAL PRIMARY KEY,
                    scan_id     INTEGER,
                    analyzed_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    miner_id    TEXT,
                    ip          TEXT,
                    prompt      TEXT,
                    response    TEXT,
                    model_used  TEXT,
                    duration_ms INTEGER
                );
            """)

            # Seed action_audit_log: 6 occurrences of (model, problem)
            for i in range(6):
                cur.execute("""
                    INSERT INTO public.action_audit_log (
                        timestamp, date, miner_id, ip, model, problem,
                        action_taken, decision
                    ) VALUES (
                        now() - (%s || ' minutes')::interval,
                        current_date, %s, '10.0.0.1', %s, %s,
                        'restart', %s
                    )
                """, (i * 5, cls.miner_id, cls.model_text,
                      cls.problem_text, "APPROVED" if i % 2 == 0 else "DENIED"))

            # Seed miner_restarts: 5 'soft' restarts with mixed outcomes.
            # We pin the model text to a real catalog row so the lookup
            # succeeds (Antminer S19 Pro is in the seed).
            for i in range(5):
                cur.execute("""
                    INSERT INTO public.miner_restarts (
                        restarted_at, miner_id, ip, model, restart_type,
                        outcome, hashrate_before, hashrate_after,
                        recovery_time_scans
                    ) VALUES (
                        now() - (%s || ' minutes')::interval,
                        %s, '10.0.0.1', 'S19 Pro', 'soft',
                        %s, 100.0, 100.0, 2
                    )
                """, (i * 7, cls.miner_id,
                      "success" if i < 3 else "failure"))

            # Seed llm_analysis: one substantive (>= 200 chars) row
            cur.execute("""
                INSERT INTO public.llm_analysis (
                    scan_id, analyzed_at, miner_id, ip, prompt, response,
                    model_used, duration_ms
                ) VALUES (
                    %s, now(), %s, '10.0.0.1', 'why is hashrate low?',
                    %s, 'qwen-test', 1234
                )
                RETURNING id
            """, (
                999_000 + int(cls.run_id, 16) % 1000,
                cls.miner_id,
                ("Hashrate dropped due to thermal throttling. The chip "
                 "temperature exceeded the safe envelope. Recommend "
                 "cleaning the air filters and verifying inlet temp. "
                 "This is a common pattern on dusty deployments and "
                 "occurs roughly weekly without preventive maintenance."),
            ))
            cls.llm_id = cur.fetchone()[0]
            cls.conn.commit()

    @classmethod
    def tearDownClass(cls):
        with cls.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM public.action_audit_log WHERE miner_id=%s",
                (cls.miner_id,),
            )
            cur.execute(
                "DELETE FROM public.miner_restarts WHERE miner_id=%s",
                (cls.miner_id,),
            )
            cur.execute(
                "DELETE FROM public.llm_analysis WHERE id=%s",
                (cls.llm_id,),
            )
            # Catalog cleanup
            cur.execute(
                "DELETE FROM ops.failure_patterns "
                "WHERE primary_source_id::text=%s "
                "AND metadata->>'operational_model_text'=%s",
                (fb.SOURCE_ID_BOBBY_OPERATIONAL, cls.model_text),
            )
            cur.execute(
                "DELETE FROM market.war_stories "
                "WHERE primary_source_id::text=%s "
                "AND (metadata->>'llm_analysis_id')::int=%s",
                (fb.SOURCE_ID_BOBBY_OPERATIONAL, cls.llm_id),
            )
            cur.execute(
                "DELETE FROM hardware.model_known_issues "
                "WHERE primary_source_id::text=%s "
                "AND metadata->>'operational_model_text'='S19 Pro' "
                "AND metadata->>'feedback_loop_key'='restart::soft'",
                (fb.SOURCE_ID_BOBBY_OPERATIONAL,),
            )
            cls.conn.commit()
        cls.conn.close()

    def test_audit_log_sync_creates_failure_pattern(self):
        stats = fb.sync_action_audit_to_failure_patterns()
        self.assertIsNone(stats["error"], stats["error"])
        self.assertGreaterEqual(stats["rows_read"], 1)
        # Verify the row landed
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT pattern_code, severity, failure_category
                FROM ops.failure_patterns
                WHERE metadata->>'operational_model_text'=%s
            """, (self.model_text,))
            rows = cur.fetchall()
        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(rows[0][2], "operational")

    def test_audit_log_sync_is_idempotent(self):
        # Run twice; second should hit the UPDATE branch.
        fb.sync_action_audit_to_failure_patterns()
        stats2 = fb.sync_action_audit_to_failure_patterns()
        self.assertIsNone(stats2["error"])
        self.assertGreaterEqual(stats2["rows_updated"], 1)

    def test_llm_analysis_sync_creates_war_story(self):
        stats = fb.sync_llm_analysis_to_war_stories()
        self.assertIsNone(stats["error"], stats["error"])
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT title, lesson_learned, topic_tags
                FROM market.war_stories
                WHERE (metadata->>'llm_analysis_id')::int=%s
            """, (self.llm_id,))
            row = cur.fetchone()
        self.assertIsNotNone(row, "war story should have been inserted")
        title, lesson, tags = row
        self.assertIn(self.miner_id, title)
        self.assertTrue(lesson)
        self.assertTrue(any(t in tags for t in ("thermal", "performance", "maintenance")))

    def test_llm_analysis_sync_is_idempotent(self):
        fb.sync_llm_analysis_to_war_stories()
        stats2 = fb.sync_llm_analysis_to_war_stories()
        self.assertIsNone(stats2["error"])
        self.assertGreaterEqual(stats2["rows_updated"], 1)

    def test_miner_restarts_sync_creates_known_issue(self):
        stats = fb.sync_miner_restarts_to_known_issues()
        self.assertIsNone(stats["error"], stats["error"])
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT issue_type, commonality, report_count
                FROM hardware.model_known_issues
                WHERE primary_source_id::text=%s
                  AND metadata->>'feedback_loop_key'='restart::soft'
                  AND metadata->>'operational_model_text'='S19 Pro'
            """, (fb.SOURCE_ID_BOBBY_OPERATIONAL,))
            row = cur.fetchone()
        self.assertIsNotNone(row, "known_issue should have been inserted")
        issue_type, commonality, report_count = row
        self.assertEqual(issue_type, "soft")
        self.assertGreaterEqual(report_count, 5)
        self.assertIn(commonality, ("rare", "occasional", "common", "widespread", "isolated"))

    def test_run_full_feedback_loop(self):
        out = fb.run_full_feedback_loop()
        for key in ("audit_log", "llm_analysis", "miner_restarts"):
            self.assertIn(key, out)
            self.assertIsNone(out[key]["error"], f"{key}: {out[key]['error']}")


@unittest.skipUnless(_have_db(), "no Postgres reachable; skipping integration tests")
class TestFeedbackLoopMissingSources(unittest.TestCase):
    """Verify graceful skip when source tables don't exist."""

    def test_missing_table_skipped_with_error(self):
        # We can't easily DROP public.action_audit_log without breaking
        # other tests, so synthesize the path: call _table_exists with
        # a guaranteed-missing name and verify the helper returns False.
        conn = fb._get_connection()
        self.assertIsNotNone(conn)
        try:
            with conn.cursor() as cur:
                self.assertFalse(
                    fb._table_exists(cur, "public", "definitely_not_a_table")
                )
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
