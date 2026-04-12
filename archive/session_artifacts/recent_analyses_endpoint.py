

# ── AI Recent Analyses with Confidence (for Grafana) ─────────────────────────

@app.get("/ai/recent_analyses")
def ai_recent_analyses(hours: int = 6):
    """Recent AI analyses with confidence scores.
    
    Returns LLM outputs from the last N hours, each with confidence %.
    Perfect for Grafana table display. 6-hour window keeps it fresh.
    
    Args:
        hours: How many hours back to include (default 6, max 24)
    """
    hours = min(hours, 24)
    cutoff = datetime.now() - timedelta(hours=hours)
    cutoff_str = cutoff.isoformat()
    
    try:
        with open(_ROOT / "knowledge.json", "r") as f:
            knowledge = json.load(f)
    except Exception as e:
        return {"error": f"Cannot read knowledge.json: {e}"}
    
    analyses = []
    conf_map = {"HIGH": 90, "MEDIUM": 70, "LOW": 40}
    
    # 1. Predictions (already have numeric confidence)
    for p in knowledge.get("predictions", []):
        predicted_at = p.get("predicted_at", "")
        if predicted_at >= cutoff_str:
            signals = p.get("signals", [])[:2]
            analyses.append({
                "type": "PREDICTION",
                "timestamp": predicted_at,
                "miner_ip": p.get("ip", "?"),
                "model": p.get("model", "?").replace("Antminer ", ""),
                "statement": f"{p.get('action', '?')}: {', '.join(signals)}",
                "confidence_pct": p.get("confidence", 0),
                "outcome": p.get("outcome")
            })

    # 2. Refined insights (convert HIGH/MEDIUM/LOW to numeric)
    for key, insight in knowledge.get("refined_insights", {}).items():
        last_updated = insight.get("last_updated", "")
        if last_updated >= cutoff_str[:10]:
            miners = insight.get("miners_affected", [])[:3]
            analyses.append({
                "type": "INSIGHT",
                "timestamp": last_updated,
                "miner_ip": ", ".join(miners) if miners else "fleet",
                "model": insight.get("miner_type", "Various").replace("Antminer ", ""),
                "statement": insight.get("insight", "")[:150],
                "confidence_pct": conf_map.get(insight.get("confidence", "MEDIUM"), 70),
                "outcome": insight.get("action")
            })
    
    # 3. Daily deep analysis fleet synthesis (most recent)
    deep_analyses = knowledge.get("daily_deep_analyses", [])
    if isinstance(deep_analyses, list):
        for da in deep_analyses:
            timestamp = da.get("timestamp", "")
            if timestamp >= cutoff_str:
                fleet_syn = da.get("fleet_synthesis", "")
                for line in fleet_syn.split("\n"):
                    line = line.strip()
                    if line and len(line) > 20:
                        conf = 75
                        if "(" in line and "%" in line:
                            try:
                                conf = int(line.split("(")[-1].split("%")[0])
                            except:
                                pass
                        analyses.append({
                            "type": "ANALYSIS",
                            "timestamp": timestamp,
                            "miner_ip": "fleet",
                            "model": "Fleet-wide",
                            "statement": line[:150],
                            "confidence_pct": conf,
                            "outcome": None
                        })

    # Sort by timestamp descending, limit to 50
    analyses.sort(key=lambda x: x["timestamp"], reverse=True)
    analyses = analyses[:50]
    
    # Summary stats
    if analyses:
        avg_conf = sum(a["confidence_pct"] for a in analyses) / len(analyses)
        high_conf = sum(1 for a in analyses if a["confidence_pct"] >= 80)
        med_conf = sum(1 for a in analyses if 50 <= a["confidence_pct"] < 80)
        low_conf = sum(1 for a in analyses if a["confidence_pct"] < 50)
    else:
        avg_conf = high_conf = med_conf = low_conf = 0
    
    return {
        "summary": {
            "total_analyses": len(analyses),
            "avg_confidence_pct": round(avg_conf, 1),
            "high_confidence": high_conf,
            "medium_confidence": med_conf,
            "low_confidence": low_conf,
            "time_window_hours": hours
        },
        "analyses": analyses,
        "generated_at": datetime.now().isoformat()
    }


