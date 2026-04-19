#!/usr/bin/env python3
"""
Fast Miner Analysis - Optimized for Speed
Uses pre-processed log summaries and a persistent system prompt.
Target: 2-5 minutes per miner instead of 135 minutes.
"""

import json
import re
import urllib.request
import time
from pathlib import Path
from typing import Dict, Optional, List
from collections import Counter

# Config
LLM_URL = "http://100.110.87.1:11434"
LLM_MODEL = "qwen2.5:32b-instruct-q4_K_M"

# The SYSTEM PROMPT - loaded once, stays in memory
MINING_GUARDIAN_SYSTEM = """You are Mining Guardian, an expert Bitcoin mining fleet analyst.

YOUR KNOWLEDGE (permanent - do not need to be told again):
- You monitor Antminer S19J Pro, S21 variants, and Auradine AH3880 miners
- All miners are liquid-cooled (hydro or immersion)
- Normal chip temps: 65-80°C. ONLY flag temps >= 84°C as concerning
- Hashrate is measured in TH/s. S19J Pro stock = 104 TH/s
- Each miner has 3 hashboards with ~126 ASICs each
- PSUs have dual circuits: control board circuit + hashboard circuit
- If control board works but all hashboards dead = PSU hashboard circuit failure

PATTERN RECOGNITION:
- Zero hashrate + no temps + unreachable = miner is OFF, needs power cycle
- Control board on + all boards dead = PSU partial failure, create ticket
- Voltage fluctuation + hashrate volatility = PSU degradation, 3-5 days to failure
- PCB=0110/BOM=0020 hardware = higher failure rate, monitor closely

RULES:
- Wait for status=MINING before taking action after restart
- Same problem = one notification per day max
- Once AMS ticket exists, stop alerting
- Each miner model variant needs its own baseline (S21 != S21 XP != S21 Imm)

OUTPUT FORMAT:
Respond with a brief JSON object:
{
  "status": "healthy|degraded|failing|offline",
  "confidence": 0.0-1.0,
  "issues": ["list of current issues"],
  "action": "none|monitor|restart|power_cycle|create_ticket",
  "reason": "brief explanation",
  "prediction_24h": "stable|degrading|at_risk"
}
"""


def summarize_log(raw_log: str) -> str:
    """Convert a huge raw log into a compact summary (~500-1000 chars)."""
    if not raw_log:
        return "NO LOG AVAILABLE"
    
    lines = raw_log.split("\n")
    
    # Count error types
    errors = Counter()
    warnings = Counter()
    
    # Extract key metrics
    voltages = []
    temps = []
    hashrates = []
    
    for line in lines:
        lower = line.lower()
        
        # Count errors/warnings
        if "error" in lower or "fail" in lower:
            # Extract error type
            if "voltage" in lower:
                errors["voltage_error"] += 1
            elif "temp" in lower or "thermal" in lower:
                errors["thermal_error"] += 1
            elif "chain" in lower or "board" in lower:
                errors["board_error"] += 1
            elif "chip" in lower or "asic" in lower:
                errors["chip_error"] += 1
            else:
                errors["other_error"] += 1
                
        if "warn" in lower:
            warnings["warning"] += 1
            
        # Extract voltages (pattern: voltage=14.5 or 14.5V)
        volt_match = re.findall(r"voltage[=:\s]*(\d+\.?\d*)", lower)
        voltages.extend([float(v) for v in volt_match if 10 < float(v) < 20])
        
        # Extract temps
        temp_match = re.findall(r"temp[=:\s]*(\d+)", lower)
        temps.extend([int(t) for t in temp_match if 20 < int(t) < 120])
        
    # Build summary
    summary_parts = [
        f"LOG_LINES: {len(lines)}",
    ]
    
    if errors:
        summary_parts.append(f"ERRORS: {dict(errors)}")
    else:
        summary_parts.append("ERRORS: none")
        
    if warnings:
        summary_parts.append(f"WARNINGS: {sum(warnings.values())}")
        
    if voltages:
        summary_parts.append(f"VOLTAGE: min={min(voltages):.2f}V max={max(voltages):.2f}V avg={sum(voltages)/len(voltages):.2f}V")
        
    if temps:
        summary_parts.append(f"TEMPS: min={min(temps)}C max={max(temps)}C avg={sum(temps)//len(temps)}C")
    
    return " | ".join(summary_parts)


def build_fast_prompt(miner: Dict, log_summary: str, trends: Dict) -> str:
    """Build a minimal prompt - just the data, no instructions."""
    
    prompt = f"""MINER: {miner.get("miner_id")} | IP: {miner.get("ip")} | MODEL: {miner.get("model")}
STATUS: {miner.get("status")} | HASHRATE: {miner.get("hashrate_pct", "?")}% | UPTIME: {miner.get("uptime", "?")}

LOG SUMMARY: {log_summary}

TRENDS 24H: hashrate_avg={trends.get("hr_avg", "?")}% temps_avg={trends.get("temp_avg", "?")}C restarts={trends.get("restart_count", 0)}

Analyze this miner and respond with JSON."""
    
    return prompt


def query_qwen_fast(prompt: str, keep_alive: str = "5m") -> Optional[Dict]:
    """Query Qwen with system prompt and keep_alive for speed."""
    
    api_url = f"{LLM_URL}/api/generate"
    payload = {
        "model": LLM_MODEL,
        "system": MINING_GUARDIAN_SYSTEM,
        "prompt": prompt,
        "stream": False,
        "keep_alive": keep_alive,  # Keep model loaded
        "options": {
            "num_ctx": 8192,  # Much smaller context needed
            "num_predict": 500,  # Short JSON response
            "temperature": 0.3,  # More deterministic
        },
    }
    
    start = time.time()
    try:
        req = urllib.request.Request(
            api_url,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = resp.read().decode()
        d = json.loads(body)
        
        elapsed = time.time() - start
        response = d.get("response", "")
        
        print(f"Qwen responded in {elapsed:.1f}s ({len(prompt)} chars prompt -> {len(response)} chars response)")
        
        # Try to parse JSON from response
        try:
            # Find JSON in response
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass
            
        return {"raw_response": response}
        
    except Exception as e:
        print(f"Error: {e}")
        return None


# Quick test
if __name__ == "__main__":
    print("Testing fast analysis...")
    
    # Mock miner data
    test_miner = {
        "miner_id": "53499",
        "ip": "192.168.188.125",
        "model": "Antminer S19JPro",
        "status": "mining",
        "hashrate_pct": 85,
        "uptime": "3d2h",
    }
    
    test_log = "voltage=14.5V temp=72C chain0=OK chain1=OK chain2=OK"
    test_trends = {"hr_avg": 87, "temp_avg": 71, "restart_count": 0}
    
    log_summary = summarize_log(test_log)
    prompt = build_fast_prompt(test_miner, log_summary, test_trends)
    
    print(f"Prompt size: {len(prompt)} chars")
    print(f"System prompt size: {len(MINING_GUARDIAN_SYSTEM)} chars")
    print()
    
    result = query_qwen_fast(prompt)
    print(f"Result: {json.dumps(result, indent=2)}")
