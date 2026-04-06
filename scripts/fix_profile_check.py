#!/usr/bin/env python3
"""
Fix action_diversity.py:
- _is_reduced_profile should check if current profile TH/s < max available TH/s
- Use config.json profile_map for max TH/s lookup
"""
import os

repo = "/Users/BigBobby/Documents/GitHub/Mining Gaurdian"
path = os.path.join(repo, "ai/action_diversity.py")

with open(path) as f:
    c = f.read()

# Replace _is_reduced_profile with a proper check
old = '''def _is_reduced_profile(profile: str) -> bool:
    """Check if miner is running a reduced (stepped-down) profile."""
    if not profile:
        return False
    profile_lower = profile.lower()
    return "eco" in profile_lower or "133" in profile or "134" in profile or "138" in profile'''

new = '''def _is_reduced_profile(profile: str) -> bool:
    """Check if miner is running below its max available profile.
    
    Reads config.json profile_map for max_ths per model type.
    If current profile TH/s < max available, miner has room to go up.
    If no config data or already at max, returns False.
    """
    if not profile:
        return False
    # Parse current profile TH/s
    from hashrate_evaluation import parse_bixbit_profile
    current_ths = parse_bixbit_profile(profile)
    if not current_ths:
        return False
    
    # Load max TH/s from config.json profile_map
    try:
        import json
        from pathlib import Path
        _root = Path(__file__).resolve().parent.parent
        for cfg_path in [_root / "config.json", _root / "config" / "config.json"]:
            if cfg_path.exists():
                cfg = json.loads(cfg_path.read_text())
                profile_map = cfg.get("profile_map", {})
                # Find the max TH/s across all model types
                for model_key, model_data in profile_map.items():
                    max_ths = model_data.get("max_ths", model_data.get("max", 0))
                    if isinstance(max_ths, (int, float)) and max_ths > 0:
                        # Check if current miner matches this model range
                        stock_ths = model_data.get("stock_ths", model_data.get("stock", 0))
                        min_ths = model_data.get("min_ths", model_data.get("min", 0))
                        if min_ths <= current_ths <= max_ths:
                            # This miner matches this model — check if below max
                            return current_ths < max_ths
                break
    except Exception:
        pass
    
    # Fallback: if current profile has "eco" or is obviously low
    profile_lower = profile.lower()
    if "eco" in profile_lower:
        return True
    return False'''

if old in c:
    c = c.replace(old, new)
    with open(path, "w") as f:
        f.write(c)
    print("FIXED: _is_reduced_profile now checks config.json max TH/s")
else:
    print("ERROR: Could not find _is_reduced_profile")
