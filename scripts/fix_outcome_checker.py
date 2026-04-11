#!/usr/bin/env python3
"""Add prediction validation to outcome_checker"""

import sys

with open("/root/Mining-Gaurdian/ai/outcome_checker.py", "r") as f:
    content = f.read()

# 1. Add helper function after _update_knowledge definition
old_update_knowledge_end = '''        logger.warning("Could not update knowledge.json with outcome: %s", e)'''

new_with_prediction_validation = '''        logger.warning("Could not update knowledge.json with outcome: %s", e)


def _validate_prediction(miner_id: str, ip: str, outcome: str) -> None:
    """
    Check if there was a prediction for this miner and validate it.
    Updates prediction_accuracy in knowledge.json.
    
    Prediction validation rules:
    - If we predicted failure (PREEMPTIVE_RESTART) and miner failed = TRUE POSITIVE
    - If we predicted failure but miner recovered = FALSE POSITIVE  
    - If we did not predict and miner failed = FALSE NEGATIVE (missed)
    - If we did not predict and miner recovered = TRUE NEGATIVE
    """
    try:
        knowledge = {}
        if Path(KNOWLEDGE_PATH).exists():
            knowledge = json.loads(Path(KNOWLEDGE_PATH).read_text())
        
        predictions = knowledge.get("predictions", [])
        
        # Find prediction for this miner (within last 48 hours)
        cutoff = (datetime.now() - timedelta(hours=48)).isoformat()
        relevant_pred = None
        for p in predictions:
            if (p.get("ip") == ip or p.get("miner_id") == str(miner_id)):
                pred_time = p.get("predicted_at", "")
                if pred_time >= cutoff:
                    relevant_pred = p
                    break  # Use most recent
        
        # Initialize prediction_accuracy if not present
        accuracy = knowledge.setdefault("prediction_accuracy", {
            "true_positives": 0,
            "false_positives": 0,
            "false_negatives": 0,
            "true_negatives": 0,
            "total_validations": 0
        })
        
        predicted_failure = (relevant_pred is not None and 
                            relevant_pred.get("action") == "PREEMPTIVE_RESTART")
        actual_failure = outcome == "FAILURE"
        
        accuracy["total_validations"] += 1
        
        if predicted_failure and actual_failure:
            accuracy["true_positives"] += 1
            logger.info("PREDICTION VALIDATED: TRUE POSITIVE for %s - predicted failure and it failed", ip)
        elif predicted_failure and not actual_failure:
            accuracy["false_positives"] += 1
            logger.info("PREDICTION VALIDATED: FALSE POSITIVE for %s - predicted failure but recovered", ip)
        elif not predicted_failure and actual_failure:
            accuracy["false_negatives"] += 1
            logger.info("PREDICTION VALIDATED: FALSE NEGATIVE for %s - missed the failure", ip)
        else:
            accuracy["true_negatives"] += 1
            # Do not log true negatives (too noisy)
        
        # Calculate accuracy rate
        tp = accuracy["true_positives"]
        tn = accuracy["true_negatives"]
        total = accuracy["total_validations"]
        if total > 0:
            accuracy["accuracy_rate"] = round((tp + tn) / total * 100, 1)
        
        # Atomic write
        tmp = str(KNOWLEDGE_PATH) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(knowledge, f, indent=2)
        import os
        os.replace(tmp, str(KNOWLEDGE_PATH))
        
    except Exception as e:
        logger.warning("Could not validate prediction: %s", e)'''

if old_update_knowledge_end in content:
    content = content.replace(old_update_knowledge_end, new_with_prediction_validation)
    print("Step 1: Added _validate_prediction function")
else:
    print("ERROR: Could not find _update_knowledge end")
    sys.exit(1)

# 2. Call _validate_prediction after _update_knowledge in _evaluate_restart
old_update_call = '''    # Update knowledge.json miner profile with outcome
    if outcome != "PENDING":
        _update_knowledge(miner_id, ip, restart["model"], outcome, recovery_scans)'''

new_update_call = '''    # Update knowledge.json miner profile with outcome
    if outcome != "PENDING":
        _update_knowledge(miner_id, ip, restart["model"], outcome, recovery_scans)
        # Validate any predictions we made for this miner
        _validate_prediction(miner_id, ip, outcome)'''

if old_update_call in content:
    content = content.replace(old_update_call, new_update_call)
    print("Step 2: Added _validate_prediction call")
else:
    print("ERROR: Could not find _update_knowledge call")
    sys.exit(1)

with open("/root/Mining-Gaurdian/ai/outcome_checker.py", "w") as f:
    f.write(content)

print("SUCCESS: Outcome checker now validates predictions")
