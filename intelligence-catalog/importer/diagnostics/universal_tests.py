"""Universal diagnostic tests — apply to any miner regardless of brand.

Each test is a function that takes (ParsedData, DetectedMiner) and returns TestResult.
"""

from config import MAX_CHIP_TEMP_C, POOL_REJECT_FAIL_PCT, POOL_REJECT_WARN_PCT
from models import DetectedMiner, ParsedData, TestResult


def test_hashrate_vs_spec(data: ParsedData, detected: DetectedMiner) -> TestResult:
    """Compare observed hashrate against catalog stock spec."""
    test = TestResult(
        test_id="UNIV-001",
        test_name="Hashrate vs stock spec",
        category="universal",
        result="SKIP",
    )

    if not data.hashrate_th or not detected.stock_hashrate_th:
        test.evidence = "Missing hashrate or stock spec data"
        return test

    ratio = data.hashrate_th / detected.stock_hashrate_th
    test.evidence = (
        f"Observed: {data.hashrate_th:.2f} TH/s, "
        f"Stock: {detected.stock_hashrate_th:.2f} TH/s, "
        f"Ratio: {ratio:.2%}"
    )

    if ratio >= 0.95:
        test.result = "PASS"
        test.diagnosis = "Hashrate within normal range"
    elif ratio >= 0.80:
        test.result = "WARN"
        test.severity = "MEDIUM"
        test.diagnosis = f"Hashrate {(1 - ratio) * 100:.1f}% below stock spec"
        test.recommended_action = "Check for thermal throttling or degraded hashboards"
    elif ratio >= 0.50:
        test.result = "FAIL"
        test.severity = "HIGH"
        test.diagnosis = f"Hashrate {(1 - ratio) * 100:.1f}% below stock spec — significant degradation"
        test.recommended_action = "Inspect hashboards for dead chips, check cooling, verify firmware"
    else:
        test.result = "FAIL"
        test.severity = "CRITICAL"
        test.diagnosis = f"Hashrate only {ratio:.0%} of stock spec — possible dead board or major failure"
        test.recommended_action = "Immediate inspection required — likely hardware failure"

    test.confidence = 0.90
    return test


def test_temperature_threshold(data: ParsedData, detected: DetectedMiner) -> TestResult:
    """Check chip temps against 84C operator threshold."""
    test = TestResult(
        test_id="UNIV-002",
        test_name="Temperature threshold (84C)",
        category="universal",
        result="SKIP",
    )

    all_temps = data.chip_temps + data.board_temps
    if not all_temps:
        test.evidence = "No temperature data available"
        return test

    max_temp = max(all_temps)
    avg_temp = sum(all_temps) / len(all_temps)
    test.evidence = (
        f"Max: {max_temp:.1f}C, Avg: {avg_temp:.1f}C, "
        f"Readings: {len(all_temps)}, Threshold: {MAX_CHIP_TEMP_C}C"
    )

    if max_temp <= MAX_CHIP_TEMP_C - 5:
        test.result = "PASS"
        test.diagnosis = "All temperatures within safe range"
    elif max_temp <= MAX_CHIP_TEMP_C:
        test.result = "WARN"
        test.severity = "MEDIUM"
        test.diagnosis = f"Max temp {max_temp:.1f}C approaching {MAX_CHIP_TEMP_C}C threshold"
        test.recommended_action = "Monitor closely — consider improving airflow"
    else:
        test.result = "FAIL"
        test.severity = "HIGH"
        test.diagnosis = f"Max temp {max_temp:.1f}C exceeds {MAX_CHIP_TEMP_C}C operator threshold"
        test.recommended_action = "Reduce ambient temp, clean fans, check thermal paste"

    test.confidence = 0.95
    return test


def test_dead_chips(data: ParsedData, detected: DetectedMiner) -> TestResult:
    """Check for dead chips (0V or null voltage)."""
    test = TestResult(
        test_id="UNIV-003",
        test_name="Dead chip detection",
        category="universal",
        result="SKIP",
    )

    if data.dead_chips == 0 and data.total_chips is None:
        test.evidence = "No chip-level data available"
        return test

    if data.dead_chips == 0:
        test.result = "PASS"
        test.evidence = f"0 dead chips out of {data.total_chips or 'unknown'} total"
        test.diagnosis = "All chips operational"
        test.confidence = 0.90
        return test

    pct = (data.dead_chips / data.total_chips * 100) if data.total_chips else 0
    test.evidence = (
        f"{data.dead_chips} dead chips out of {data.total_chips or 'unknown'} total "
        f"({pct:.1f}%)"
    )

    if pct <= 1:
        test.result = "WARN"
        test.severity = "LOW"
        test.diagnosis = f"{data.dead_chips} dead chip(s) — minor impact"
        test.recommended_action = "Monitor for progression"
    elif pct <= 5:
        test.result = "WARN"
        test.severity = "MEDIUM"
        test.diagnosis = f"{data.dead_chips} dead chips — noticeable hashrate impact"
        test.recommended_action = "Schedule hashboard inspection"
    else:
        test.result = "FAIL"
        test.severity = "HIGH"
        test.diagnosis = f"{data.dead_chips} dead chips ({pct:.1f}%) — significant performance loss"
        test.recommended_action = "Hashboard repair or replacement needed"

    test.confidence = 0.95
    return test


def test_error_keyword_count(data: ParsedData, detected: DetectedMiner) -> TestResult:
    """Count error/warn/fatal keywords in log."""
    test = TestResult(
        test_id="UNIV-004",
        test_name="Error keyword count",
        category="universal",
        result="SKIP",
    )

    total = data.error_count + data.warn_count + data.fatal_count
    if total == 0 and data.error_count == 0:
        test.result = "PASS"
        test.evidence = "No error/warn/fatal keywords found"
        test.diagnosis = "Clean log"
        test.confidence = 0.80
        return test

    test.evidence = (
        f"Errors: {data.error_count}, Warnings: {data.warn_count}, "
        f"Fatal: {data.fatal_count}"
    )

    if data.fatal_count > 0:
        test.result = "FAIL"
        test.severity = "CRITICAL"
        test.diagnosis = f"{data.fatal_count} FATAL events detected"
        test.recommended_action = "Investigate fatal errors immediately"
    elif data.error_count > 50:
        test.result = "FAIL"
        test.severity = "HIGH"
        test.diagnosis = f"High error rate: {data.error_count} errors"
        test.recommended_action = "Review error logs for recurring patterns"
    elif data.error_count > 10:
        test.result = "WARN"
        test.severity = "MEDIUM"
        test.diagnosis = f"Moderate error count: {data.error_count} errors"
        test.recommended_action = "Review for systemic issues"
    else:
        test.result = "PASS"
        test.evidence += " — within normal range"
        test.diagnosis = "Error counts within acceptable range"

    test.confidence = 0.85
    return test


def test_pool_rejection_rate(data: ParsedData, detected: DetectedMiner) -> TestResult:
    """Check pool share rejection rate."""
    test = TestResult(
        test_id="UNIV-005",
        test_name="Pool rejection rate",
        category="universal",
        result="SKIP",
    )

    if data.accepted_shares is None or data.rejected_shares is None:
        test.evidence = "No pool share data available"
        return test

    total = data.accepted_shares + data.rejected_shares
    if total == 0:
        test.evidence = "No shares submitted"
        return test

    reject_pct = (data.rejected_shares / total) * 100
    test.evidence = (
        f"Accepted: {data.accepted_shares:,}, Rejected: {data.rejected_shares:,}, "
        f"Rate: {reject_pct:.2f}%"
    )

    if reject_pct < POOL_REJECT_WARN_PCT:
        test.result = "PASS"
        test.diagnosis = "Rejection rate within normal range"
    elif reject_pct < POOL_REJECT_FAIL_PCT:
        test.result = "WARN"
        test.severity = "MEDIUM"
        test.diagnosis = f"Rejection rate {reject_pct:.2f}% above {POOL_REJECT_WARN_PCT}%"
        test.recommended_action = "Check network latency and pool configuration"
    else:
        test.result = "FAIL"
        test.severity = "HIGH"
        test.diagnosis = f"Rejection rate {reject_pct:.2f}% above {POOL_REJECT_FAIL_PCT}%"
        test.recommended_action = "Check for stale work, network issues, or misconfiguration"

    test.confidence = 0.90
    return test


def test_unexpected_reboots(data: ParsedData, detected: DetectedMiner) -> TestResult:
    """Check for unexpected reboots/restarts."""
    test = TestResult(
        test_id="UNIV-006",
        test_name="Unexpected reboots",
        category="universal",
        result="SKIP",
    )

    if data.reboot_count == 0:
        test.result = "PASS"
        test.evidence = "No reboot/restart events detected"
        test.diagnosis = "Stable operation"
        test.confidence = 0.80
        return test

    test.evidence = f"{data.reboot_count} reboot/restart events detected"

    if data.reboot_count <= 2:
        test.result = "WARN"
        test.severity = "LOW"
        test.diagnosis = f"{data.reboot_count} restart(s) — may be routine"
        test.recommended_action = "Verify if restarts were intentional"
    elif data.reboot_count <= 5:
        test.result = "WARN"
        test.severity = "MEDIUM"
        test.diagnosis = f"{data.reboot_count} restarts — concerning frequency"
        test.recommended_action = "Check for thermal shutdowns, power issues, or firmware bugs"
    else:
        test.result = "FAIL"
        test.severity = "HIGH"
        test.diagnosis = f"{data.reboot_count} restarts — unstable miner"
        test.recommended_action = "Investigate root cause: PSU, thermal, or firmware issue"

    test.confidence = 0.85
    return test


# All universal tests in execution order
UNIVERSAL_TESTS = [
    test_hashrate_vs_spec,
    test_temperature_threshold,
    test_dead_chips,
    test_error_keyword_count,
    test_pool_rejection_rate,
    test_unexpected_reboots,
]
