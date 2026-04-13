"""Brand-specific diagnostic tests.

These tests only run when the detected brand matches.
"""

from config import MIN_HITRATE
from models import DetectedMiner, ParsedData, TestResult


# ═══════════════════════════════════════════════════════════════════════════════
# BITMAIN (BiXBiT) TESTS
# ═══════════════════════════════════════════════════════════════════════════════

def test_bitmain_chain_detach(data: ParsedData, detected: DetectedMiner) -> TestResult:
    """Detect chain detach — a chain with 0 hashrate while others are active."""
    test = TestResult(
        test_id="BIT-001",
        test_name="Chain detach detection",
        category="brand_specific",
        result="SKIP",
    )

    if not data.chains:
        test.evidence = "No chain data available"
        return test

    active = [c for c in data.chains if c.get("hashrate", 0) > 0]
    dead = [c for c in data.chains if c.get("hashrate", 0) == 0]

    test.evidence = f"Active chains: {len(active)}, Dead chains: {len(dead)}"

    if not dead:
        test.result = "PASS"
        test.diagnosis = "All chains operational"
        test.confidence = 0.90
    elif active:
        test.result = "FAIL"
        test.severity = "CRITICAL"
        dead_ids = [str(c.get("chain_id", "?")) for c in dead]
        test.diagnosis = f"Chain detach: chain(s) {', '.join(dead_ids)} reporting 0 hashrate"
        test.recommended_action = "Reseat hashboard cables, check chain ribbon connectors"
        test.confidence = 0.95
    else:
        test.result = "FAIL"
        test.severity = "CRITICAL"
        test.diagnosis = "All chains reporting 0 hashrate — miner down"
        test.recommended_action = "Check PSU, control board, and all chain connections"
        test.confidence = 0.95

    return test


def test_bitmain_autotune_missing(data: ParsedData, detected: DetectedMiner) -> TestResult:
    """Check if BiXBiT autotune data is present (should be for BiXBiT firmware)."""
    test = TestResult(
        test_id="BIT-002",
        test_name="Autotune configuration",
        category="brand_specific",
        result="SKIP",
    )

    has_bixbit = detected.firmware and "bixbit" in detected.firmware.lower()
    autotune = data.raw_fields.get("autotune")

    if not has_bixbit:
        test.evidence = "Not BiXBiT firmware — autotune check not applicable"
        return test

    if autotune:
        test.result = "PASS"
        test.evidence = f"Autotune setting: {autotune}"
        test.diagnosis = "Autotune is configured"
        test.confidence = 0.85
    else:
        test.result = "WARN"
        test.severity = "MEDIUM"
        test.evidence = "BiXBiT firmware detected but no autotune configuration found"
        test.diagnosis = "Autotune may not be enabled"
        test.recommended_action = "Enable autotune for optimal performance"
        test.confidence = 0.70

    return test


def test_bitmain_inter_chain_voltage_delta(
    data: ParsedData, detected: DetectedMiner
) -> TestResult:
    """Check voltage delta between chains — large delta indicates board issues."""
    test = TestResult(
        test_id="BIT-003",
        test_name="Inter-chain voltage delta",
        category="brand_specific",
        result="SKIP",
    )

    chain_voltages = [
        c.get("voltage") for c in data.chains if c.get("voltage") is not None
    ]

    if len(chain_voltages) < 2:
        test.evidence = "Need at least 2 chain voltages to compare"
        return test

    delta = max(chain_voltages) - min(chain_voltages)
    avg = sum(chain_voltages) / len(chain_voltages)
    test.evidence = (
        f"Chain voltages: {[f'{v:.1f}' for v in chain_voltages]}, "
        f"Delta: {delta:.1f}, Avg: {avg:.1f}"
    )

    if delta < 20:
        test.result = "PASS"
        test.diagnosis = "Chain voltages well balanced"
        test.confidence = 0.85
    elif delta < 50:
        test.result = "WARN"
        test.severity = "MEDIUM"
        test.diagnosis = f"Voltage delta {delta:.1f} between chains — monitor closely"
        test.recommended_action = "Check for aging hashboard or connector issues"
        test.confidence = 0.80
    else:
        test.result = "FAIL"
        test.severity = "HIGH"
        test.diagnosis = f"Large voltage delta {delta:.1f} — possible hashboard degradation"
        test.recommended_action = "Inspect hashboard with lowest voltage for damage"
        test.confidence = 0.85

    return test


def test_bitmain_power_calibration(
    data: ParsedData, detected: DetectedMiner
) -> TestResult:
    """Check if observed power matches expected range for the model."""
    test = TestResult(
        test_id="BIT-004",
        test_name="Power calibration check",
        category="brand_specific",
        result="SKIP",
    )

    if not data.power_w or not detected.stock_power_w:
        test.evidence = "Missing power data or stock power spec"
        return test

    ratio = data.power_w / detected.stock_power_w
    test.evidence = (
        f"Observed: {data.power_w:.0f}W, Stock: {detected.stock_power_w:.0f}W, "
        f"Ratio: {ratio:.2%}"
    )

    if 0.85 <= ratio <= 1.15:
        test.result = "PASS"
        test.diagnosis = "Power within expected range"
        test.confidence = 0.85
    elif 0.70 <= ratio <= 1.30:
        test.result = "WARN"
        test.severity = "MEDIUM"
        test.diagnosis = f"Power {(ratio - 1) * 100:+.1f}% from stock spec"
        test.recommended_action = "Check PSU calibration and miner tune profile"
        test.confidence = 0.80
    else:
        test.result = "FAIL"
        test.severity = "HIGH"
        test.diagnosis = f"Power significantly off: {ratio:.0%} of stock spec"
        test.recommended_action = "PSU inspection or firmware power reporting issue"
        test.confidence = 0.75

    return test


# ═══════════════════════════════════════════════════════════════════════════════
# AURADINE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

def test_auradine_dvfs_voltage_range(
    data: ParsedData, detected: DetectedMiner
) -> TestResult:
    """Check if DVFS voltages are within acceptable range."""
    test = TestResult(
        test_id="AUR-001",
        test_name="DVFS voltage range",
        category="brand_specific",
        result="SKIP",
    )

    if not data.voltages:
        test.evidence = "No voltage data available"
        return test

    min_v = min(data.voltages)
    max_v = max(data.voltages)
    avg_v = sum(data.voltages) / len(data.voltages)

    # Typical Auradine DVFS voltage range: 250-450 mV
    test.evidence = (
        f"Min: {min_v:.0f}mV, Max: {max_v:.0f}mV, "
        f"Avg: {avg_v:.0f}mV, Count: {len(data.voltages)}"
    )

    out_of_range = [v for v in data.voltages if v < 200 or v > 500]

    if not out_of_range:
        test.result = "PASS"
        test.diagnosis = "All DVFS voltages within normal range"
        test.confidence = 0.85
    elif len(out_of_range) <= len(data.voltages) * 0.05:
        test.result = "WARN"
        test.severity = "MEDIUM"
        test.diagnosis = f"{len(out_of_range)} voltage readings out of range"
        test.recommended_action = "Monitor for voltage regulator degradation"
        test.confidence = 0.80
    else:
        test.result = "FAIL"
        test.severity = "HIGH"
        test.diagnosis = f"{len(out_of_range)} voltage readings significantly out of range"
        test.recommended_action = "Inspect voltage regulators and DVFS configuration"
        test.confidence = 0.85

    return test


def test_auradine_power_reduction(
    data: ParsedData, detected: DetectedMiner
) -> TestResult:
    """Check for power reduction events indicating throttling."""
    test = TestResult(
        test_id="AUR-002",
        test_name="Power reduction events",
        category="brand_specific",
        result="SKIP",
    )

    reductions = data.raw_fields.get("power_reduction_events", 0)
    clips = data.raw_fields.get("power_state_clips", 0)

    if reductions == 0 and clips == 0:
        test.result = "PASS"
        test.evidence = "No power reduction events detected"
        test.diagnosis = "Running at full power"
        test.confidence = 0.85
        return test

    test.evidence = f"Power reductions: {reductions}, PowerState clips: {clips}"

    total = reductions + clips
    if total <= 3:
        test.result = "WARN"
        test.severity = "LOW"
        test.diagnosis = f"{total} power limiting events — may be transient"
        test.recommended_action = "Check ambient temperature and power supply capacity"
    elif total <= 10:
        test.result = "WARN"
        test.severity = "MEDIUM"
        test.diagnosis = f"{total} power limiting events — frequent throttling"
        test.recommended_action = "Improve cooling or reduce power target"
    else:
        test.result = "FAIL"
        test.severity = "HIGH"
        test.diagnosis = f"{total} power limiting events — persistent throttling"
        test.recommended_action = "Address root cause: cooling, PSU, or ambient temp"

    test.confidence = 0.85
    return test


def test_auradine_dead_board(data: ParsedData, detected: DetectedMiner) -> TestResult:
    """Detect dead boards via avg_volt = 0."""
    test = TestResult(
        test_id="AUR-003",
        test_name="Dead board detection (avg_volt 0)",
        category="brand_specific",
        result="SKIP",
    )

    if not data.boards:
        test.evidence = "No board data available"
        return test

    dead_boards = [b for b in data.boards if b.get("avg_volt") == 0 or b.get("dead")]
    live_boards = [b for b in data.boards if b.get("avg_volt", 0) > 0 and not b.get("dead")]

    test.evidence = f"Total boards: {len(data.boards)}, Dead: {len(dead_boards)}, Live: {len(live_boards)}"

    if not dead_boards:
        test.result = "PASS"
        test.diagnosis = "All boards reporting voltage"
        test.confidence = 0.90
    else:
        dead_ids = [str(b.get("board_id", "?")) for b in dead_boards]
        test.result = "FAIL"
        test.severity = "CRITICAL"
        test.diagnosis = f"Dead board(s): {', '.join(dead_ids)} (avg_volt = 0)"
        test.recommended_action = "Inspect dead board(s) — check power connectors and board health"
        test.confidence = 0.95

    return test


def test_auradine_hitrate(data: ParsedData, detected: DetectedMiner) -> TestResult:
    """Check hitrate — below 0.90 indicates issues."""
    test = TestResult(
        test_id="AUR-004",
        test_name="Hitrate check",
        category="brand_specific",
        result="SKIP",
    )

    hitrate = data.raw_fields.get("hitrate")
    if hitrate is None:
        test.evidence = "No hitrate data available"
        return test

    test.evidence = f"Hitrate: {hitrate:.4f} (threshold: {MIN_HITRATE})"

    if hitrate >= MIN_HITRATE:
        test.result = "PASS"
        test.diagnosis = f"Hitrate {hitrate:.4f} above threshold"
        test.confidence = 0.90
    elif hitrate >= 0.80:
        test.result = "WARN"
        test.severity = "MEDIUM"
        test.diagnosis = f"Hitrate {hitrate:.4f} below {MIN_HITRATE} threshold"
        test.recommended_action = "Check for noisy chips or DVFS misconfiguration"
        test.confidence = 0.85
    else:
        test.result = "FAIL"
        test.severity = "HIGH"
        test.diagnosis = f"Hitrate {hitrate:.4f} critically low"
        test.recommended_action = "Investigate chip health and voltage settings"
        test.confidence = 0.90

    return test


# ═══════════════════════════════════════════════════════════════════════════════
# MICROBT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

def test_microbt_fan_failure(data: ParsedData, detected: DetectedMiner) -> TestResult:
    """Check for fan failure patterns in WhatsMiner logs."""
    test = TestResult(
        test_id="MCB-001",
        test_name="Fan failure detection",
        category="brand_specific",
        result="SKIP",
    )

    fan_fails = data.raw_fields.get("fan_failures", 0)

    if not data.fan_speeds and fan_fails == 0:
        test.evidence = "No fan data available"
        return test

    # Check for fans at 0 RPM
    zero_fans = [s for s in data.fan_speeds if s == 0]

    test.evidence = (
        f"Fan speeds: {data.fan_speeds}, "
        f"Zero RPM fans: {len(zero_fans)}, "
        f"Fan failure events: {fan_fails}"
    )

    if fan_fails > 0 or zero_fans:
        test.result = "FAIL"
        test.severity = "CRITICAL"
        test.diagnosis = f"Fan failure detected: {fan_fails} events, {len(zero_fans)} fans at 0 RPM"
        test.recommended_action = "Replace failed fans immediately — thermal shutdown risk"
        test.confidence = 0.95
    elif data.fan_speeds and min(data.fan_speeds) < 1000:
        test.result = "WARN"
        test.severity = "MEDIUM"
        test.diagnosis = f"Fan running slow: {min(data.fan_speeds)} RPM"
        test.recommended_action = "Check fan bearings and dust buildup"
        test.confidence = 0.80
    else:
        test.result = "PASS"
        test.diagnosis = "Fan operation normal"
        test.confidence = 0.85

    return test


def test_microbt_temp_sensor_error(
    data: ParsedData, detected: DetectedMiner
) -> TestResult:
    """Check for temperature sensor errors."""
    test = TestResult(
        test_id="MCB-002",
        test_name="Temp sensor error detection",
        category="brand_specific",
        result="SKIP",
    )

    temp_errs = data.raw_fields.get("temp_sensor_errors", 0)

    if temp_errs == 0:
        test.result = "PASS"
        test.evidence = "No temperature sensor errors detected"
        test.diagnosis = "Temp sensors operational"
        test.confidence = 0.85
        return test

    test.evidence = f"Temperature sensor errors: {temp_errs}"
    test.result = "FAIL"
    test.severity = "HIGH"
    test.diagnosis = f"{temp_errs} temp sensor error(s) — thermal protection compromised"
    test.recommended_action = "Replace temp sensor or affected hashboard"
    test.confidence = 0.90

    return test


# ═══════════════════════════════════════════════════════════════════════════════
# CANAAN TESTS
# ═══════════════════════════════════════════════════════════════════════════════

def test_canaan_nonce_rate_degradation(
    data: ParsedData, detected: DetectedMiner
) -> TestResult:
    """Check for nonce rate degradation in Avalon miners."""
    test = TestResult(
        test_id="CAN-001",
        test_name="Nonce rate degradation",
        category="brand_specific",
        result="SKIP",
    )

    nonce_rate = data.raw_fields.get("nonce_rate")
    nonce_errors = data.raw_fields.get("nonce_errors", 0)

    if nonce_rate is None:
        test.evidence = "No nonce rate data available"
        return test

    test.evidence = f"Nonce rate: {nonce_rate}, Nonce errors: {nonce_errors}"

    if nonce_errors > 100:
        test.result = "FAIL"
        test.severity = "HIGH"
        test.diagnosis = f"High nonce error count ({nonce_errors}) — chip degradation"
        test.recommended_action = "Inspect hashboard for degraded ASIC chips"
        test.confidence = 0.80
    elif nonce_errors > 20:
        test.result = "WARN"
        test.severity = "MEDIUM"
        test.diagnosis = f"Moderate nonce errors ({nonce_errors})"
        test.recommended_action = "Monitor for progression"
        test.confidence = 0.75
    else:
        test.result = "PASS"
        test.diagnosis = "Nonce rate within normal range"
        test.confidence = 0.80

    return test


def test_canaan_vreg_issues(data: ParsedData, detected: DetectedMiner) -> TestResult:
    """Check for voltage regulator issues in Avalon miners."""
    test = TestResult(
        test_id="CAN-002",
        test_name="Voltage regulator issues",
        category="brand_specific",
        result="SKIP",
    )

    vreg_errors = data.raw_fields.get("vreg_errors", 0)

    if vreg_errors == 0:
        test.result = "PASS"
        test.evidence = "No voltage regulator errors detected"
        test.diagnosis = "VReg operation normal"
        test.confidence = 0.85
        return test

    test.evidence = f"Voltage regulator errors: {vreg_errors}"
    test.result = "FAIL"
    test.severity = "CRITICAL"
    test.diagnosis = f"{vreg_errors} VReg error(s) — board power delivery compromised"
    test.recommended_action = "Inspect voltage regulators on affected hashboard(s)"
    test.confidence = 0.90

    return test


# ─── Brand test registry ─────────────────────────────────────────────────────

BRAND_TESTS = {
    "bitmain": [
        test_bitmain_chain_detach,
        test_bitmain_autotune_missing,
        test_bitmain_inter_chain_voltage_delta,
        test_bitmain_power_calibration,
    ],
    "auradine": [
        test_auradine_dvfs_voltage_range,
        test_auradine_power_reduction,
        test_auradine_dead_board,
        test_auradine_hitrate,
    ],
    "microbt": [
        test_microbt_fan_failure,
        test_microbt_temp_sensor_error,
    ],
    "canaan": [
        test_canaan_nonce_rate_degradation,
        test_canaan_vreg_issues,
    ],
}
