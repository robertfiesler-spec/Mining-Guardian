#!/usr/bin/env python3
"""Add prediction awareness to confidence_scorer"""

with open("/root/Mining-Gaurdian/ai/confidence_scorer.py", "r") as f:
    content = f.read()

# 1. Add helper function to get prediction risk after get_db
old_get_db = '''def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn'''

new_get_db = '''def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _get_prediction_penalty(ip: str) -> float:
    """
    Check if this miner has pre-failure predictions.
    Returns a penalty (negative adjustment) if so.
    
    Miners with pre-failure signals should have LOWER confidence
    for restart actions because the issue may be hardware, not software.
    """
    try:
        knowledge = json.loads(Path(KNOWLEDGE_PATH).read_text())
        predictions = knowledge.get("predictions", [])
        
        for p in predictions:
            if p.get("ip") == ip:
                conf = p.get("confidence", 0)
                signals = p.get("signals", [])
                
                # The more signals and higher confidence, the bigger the penalty
                if conf >= 80:
                    return -15.0  # Strong pre-failure signal = significant penalty
                elif conf >= 70:
                    return -10.0
                elif conf >= 60:
                    return -5.0
        
        return 0.0  # No prediction = no penalty
    except Exception:
        return 0.0'''

if old_get_db in content:
    content = content.replace(old_get_db, new_get_db)
    print("Step 1: Added _get_prediction_penalty function")
else:
    print("ERROR: Could not find get_db function")

# 2. Apply prediction penalty in get_confidence
old_fingerprint = '''    # Feature 4: Apply per-miner fingerprint confidence modifier
    try:
        from fingerprint_builder import get_confidence_modifier
        modifier = get_confidence_modifier(miner_id)
        # Modifier is -0.5 to +0.5, scale to point adjustment
        fingerprint_adjustment = modifier * 30  # max +/-15 points
    except Exception:
        fingerprint_adjustment = 0.0'''

new_fingerprint = '''    # Feature 4: Apply per-miner fingerprint confidence modifier
    try:
        from fingerprint_builder import get_confidence_modifier
        modifier = get_confidence_modifier(miner_id)
        # Modifier is -0.5 to +0.5, scale to point adjustment
        fingerprint_adjustment = modifier * 30  # max +/-15 points
    except Exception:
        fingerprint_adjustment = 0.0
    
    # Feature: Apply prediction penalty (pre-failure signals = lower confidence)
    prediction_penalty = _get_prediction_penalty(ip)'''

if old_fingerprint in content:
    content = content.replace(old_fingerprint, new_fingerprint)
    print("Step 2: Added prediction penalty call")
else:
    print("ERROR: Could not find fingerprint block")

# 3. Apply penalty to final score
old_final = '''    # Final weighted score with fingerprint modifier
    raw_confidence = (
        history_score   * (WEIGHT_MINER_HISTORY + WEIGHT_FLEET_HISTORY) +
        stability_score * WEIGHT_STABILITY
    )
    confidence = max(0, min(100, round(raw_confidence + fingerprint_adjustment)))'''

new_final = '''    # Final weighted score with fingerprint modifier and prediction penalty
    raw_confidence = (
        history_score   * (WEIGHT_MINER_HISTORY + WEIGHT_FLEET_HISTORY) +
        stability_score * WEIGHT_STABILITY
    )
    confidence = max(0, min(100, round(raw_confidence + fingerprint_adjustment + prediction_penalty)))'''

if old_final in content:
    content = content.replace(old_final, new_final)
    print("Step 3: Applied prediction penalty to final score")
else:
    print("ERROR: Could not find final score calculation")

with open("/root/Mining-Gaurdian/ai/confidence_scorer.py", "w") as f:
    f.write(content)

print("SUCCESS: Confidence scorer now factors in predictions")
