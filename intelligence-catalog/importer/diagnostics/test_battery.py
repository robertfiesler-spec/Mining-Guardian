"""Diagnostic test battery — runs all applicable tests against parsed data."""

import logging
from typing import Optional

from models import DetectedMiner, ParsedData, TestResult
from .universal_tests import UNIVERSAL_TESTS
from .brand_tests import BRAND_TESTS

logger = logging.getLogger("importer.diagnostics")


class DiagnosticBattery:
    """Runs diagnostic tests against parsed miner data."""

    def run(
        self,
        data: ParsedData,
        detected: DetectedMiner,
    ) -> list[TestResult]:
        """Run all applicable tests and return results.

        Runs universal tests first, then brand-specific tests if brand is known.
        """
        results: list[TestResult] = []

        # Run universal tests
        for test_fn in UNIVERSAL_TESTS:
            try:
                result = test_fn(data, detected)
                results.append(result)
            except Exception as e:
                logger.warning("Test %s failed with error: %s", test_fn.__name__, e)
                results.append(TestResult(
                    test_id=f"ERR-{test_fn.__name__}",
                    test_name=test_fn.__name__,
                    category="universal",
                    result="ERROR",
                    evidence=str(e),
                ))

        # Run brand-specific tests
        brand = detected.brand
        if brand and brand in BRAND_TESTS:
            for test_fn in BRAND_TESTS[brand]:
                try:
                    result = test_fn(data, detected)
                    results.append(result)
                except Exception as e:
                    logger.warning(
                        "Brand test %s failed with error: %s", test_fn.__name__, e
                    )
                    results.append(TestResult(
                        test_id=f"ERR-{test_fn.__name__}",
                        test_name=test_fn.__name__,
                        category="brand_specific",
                        result="ERROR",
                        evidence=str(e),
                    ))

        return results

    @staticmethod
    def summarize(results: list[TestResult]) -> dict[str, int]:
        """Count results by outcome."""
        summary = {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIP": 0, "ERROR": 0}
        for r in results:
            summary[r.result] = summary.get(r.result, 0) + 1
        return summary

    @staticmethod
    def format_summary(results: list[TestResult]) -> str:
        """Format results into a one-line summary string."""
        summary = DiagnosticBattery.summarize(results)
        parts = []
        if summary["PASS"]:
            parts.append(f"{summary['PASS']} PASS")
        if summary["WARN"]:
            parts.append(f"{summary['WARN']} WARN")
        if summary["FAIL"]:
            parts.append(f"{summary['FAIL']} FAIL")
        if summary["SKIP"]:
            parts.append(f"{summary['SKIP']} SKIP")
        if summary["ERROR"]:
            parts.append(f"{summary['ERROR']} ERROR")
        return ", ".join(parts)
