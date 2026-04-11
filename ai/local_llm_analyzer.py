"""
local_llm_analyzer.py
Mining Guardian — Local LLM Analysis Engine

Runs after EVERY scan. Sends fleet data + miner logs to the local LLM
(Qwen 2.5 32B on RTX 4090 via Ollama) for real-time analysis.

This is NOT the weekly Claude training — this is continuous local learning.
The LLM sees every scan, every log download, every restart outcome,
and produces analysis that gets:
  1. Posted to Slack as the AI's interpretation of the scan
  2. Stored in knowledge.json for accumulating intelligence
  3. Used to improve recommendations over time

The local LLM runs on the Windows PC RTX 4090 via Tailscale.
On Mac Mini deployment, it runs locally via Ollama.
"""

import json
import logging
import sqlite3
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List

_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = str(_ROOT / "guardian.db")
KNOWLEDGE_PATH = _ROOT / "knowledge.json"

logger = logging.getLogger("mining_guardian")

# LLM endpoint — Ollama on Windows PC (Tailscale) or local Mac Mini
# Configurable via config.json "local_llm_url"
DEFAULT_LLM_URL = "http://100.110.87.1:11434"
DEFAULT_MODEL = "qwen2.5:32b-instruct-q4_K_M"


class LocalLLMAnalyzer:
    """Real-time fleet analysis via local LLM after every scan."""

    def __init__(self, llm_url: str = None, model: str = None):
        self.llm_url = llm_url or DEFAULT_LLM_URL
        self.model = model or DEFAULT_MODEL
        self.api_url = f"{self.llm_url}/api/generate"
        self._last_full_analysis = 0  # timestamp of last full analysis
        self.FULL_ANALYSIS_INTERVAL = 1800  # full analysis every 30 min
        self.QUICK_ANALYSIS_INTERVAL = 300  # quick check every scan

    def _query_llm(self, prompt: str, max_tokens: int = 1024,
                   timeout: int = 60) -> Optional[str]:
        """Send prompt to local Ollama LLM and return response."""
        try:
            resp = requests.post(
                self.api_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": 0.3,  # low temp for factual analysis
                    },
                },
                timeout=timeout,
            )
            if resp.status_code == 200:
                return resp.json().get("response", "")
            else:
                logger.warning("LLM returned %s: %s", resp.status_code, resp.text[:100])
                return None
        except requests.exceptions.Timeout:
            logger.warning("LLM request timed out after %ss", timeout)
            return None
        except Exception as e:
            logger.warning("LLM request failed: %s", e)
            return None

    def _get_scan_context(self, scan_id: int) -> Dict:
        """Build context from the latest scan data."""
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row

        # Current scan summary
        scan = conn.execute(
            "SELECT * FROM scans WHERE id=?", (scan_id,)
        ).fetchone()

        # Miners with issues this scan
        flagged = conn.execute("""
            SELECT ip, model, hashrate_pct, temp_chip, current_profile,
                   status, action, issue, uptime
            FROM miner_readings
            WHERE scan_id=? AND action IS NOT NULL AND action != 'MONITOR'
            ORDER BY hashrate_pct ASC
        """, (scan_id,)).fetchall()

        # Recent restart outcomes (last 24h)
        outcomes = conn.execute("""
            SELECT ip, model, outcome, hashrate_before, hashrate_after,
                   restarted_at, restart_type
            FROM miner_restarts
            WHERE restarted_at >= datetime('now', '-24 hours')
              AND outcome IS NOT NULL
            ORDER BY restarted_at DESC LIMIT 10
        """).fetchall()

        # Recent denial reasons (last 24h)
        denials = conn.execute("""
            SELECT ip, model, action_taken, notes, timestamp
            FROM action_audit_log
            WHERE notes LIKE '%DENIAL_REASON%'
              AND timestamp >= datetime('now', '-24 hours')
            ORDER BY timestamp DESC LIMIT 5
        """).fetchall()

        # New logs collected since last analysis
        recent_logs = conn.execute("""
            SELECT miner_id, collected_at, health_status, log_file,
                   LENGTH(content) as size_bytes
            FROM miner_logs
            WHERE collected_at >= datetime('now', '-30 minutes')
            ORDER BY collected_at DESC LIMIT 10
        """).fetchall()

        # Pre/post restart log pairs (last 24h)
        restart_logs = conn.execute("""
            SELECT miner_id, health_status, collected_at, log_file,
                   SUBSTR(content, 1, 2000) as content_preview
            FROM miner_logs
            WHERE health_status LIKE '%restart%'
              AND collected_at >= datetime('now', '-24 hours')
            ORDER BY miner_id, collected_at DESC
            LIMIT 20
        """).fetchall()

        # HVAC current state
        hvac = conn.execute("""
            SELECT supply_temp_f, return_temp_f, delta_t_f, diff_pressure,
                   spray_pump_on, cwp2_vfd_pct, ct1_vfd_pct, ct2_vfd_pct
            FROM hvac_readings ORDER BY id DESC LIMIT 1
        """).fetchone()

        # Weather
        weather = conn.execute("""
            SELECT temp_f, humidity_pct, feels_like_f
            FROM weather_readings ORDER BY id DESC LIMIT 1
        """).fetchone()

        # Knowledge patterns
        knowledge = {}
        if KNOWLEDGE_PATH.exists():
            try:
                knowledge = json.loads(KNOWLEDGE_PATH.read_text())
            except Exception:
                pass

        conn.close()

        # Get our OWN previous analyses to learn from
        prev_analyses = knowledge.get("llm_scan_analyses", [])[-3:]  # Last 3
        
        # Get flagged miner IDs for fingerprint lookup
        flagged_ids = []
        flagged_ips = []
        for r in flagged:
            rd = dict(r)
            if "miner_id" in rd:
                flagged_ids.append(rd["miner_id"])
            if "ip" in rd:
                flagged_ips.append(rd["ip"])
        
        # Get fingerprints for flagged miners only (keeps prompt focused)
        all_fingerprints = knowledge.get("miner_fingerprints", {})
        flagged_fingerprints = {}
        for mid in flagged_ids:
            if mid in all_fingerprints:
                flagged_fingerprints[mid] = all_fingerprints[mid]
        # Also try matching by IP
        for ip in flagged_ips:
            for fid, fp in all_fingerprints.items():
                if fp.get("ip") == ip and fid not in flagged_fingerprints:
                    flagged_fingerprints[fid] = fp
        
        # Get predictions for flagged miners
        all_predictions = knowledge.get("predictions", [])
        relevant_predictions = [p for p in all_predictions if p.get("ip") in flagged_ips][:10]
        
        return {
            "scan": dict(scan) if scan else {},
            "flagged": [dict(r) for r in flagged],
            "outcomes": [dict(r) for r in outcomes],
            "denials": [dict(r) for r in denials],
            "recent_logs": [dict(r) for r in recent_logs],
            "restart_logs": [dict(r) for r in restart_logs],
            "hvac": dict(hvac) if hvac else {},
            "weather": dict(weather) if weather else {},
            "patterns": knowledge.get("patterns", []),
            "known_issues": knowledge.get("known_issues", [])[-20:],
            "refined_insights": knowledge.get("refined_insights", {}),
            "previous_analyses": prev_analyses,
            # NEW: Full AI context
            "predictions": relevant_predictions,
            "operator_rules": knowledge.get("operator_rules", []),
            "fingerprints": flagged_fingerprints,
            "cross_miner_analysis": knowledge.get("cross_miner_analysis", [])[:3],
            "hvac_correlation": knowledge.get("hvac_correlation", {}),
        }

    def _build_scan_prompt(self, ctx: Dict) -> str:
        """Build LLM prompt from scan context."""
        scan = ctx["scan"]
        lines = [
            "You are Mining Guardian's AI analyst for a Bitcoin mining fleet.",
            "Analyze this scan data and provide actionable intelligence.",
            "",
            f"=== SCAN #{scan.get('id', '?')} — {scan.get('scanned_at', '?')} ===",
            f"Fleet: {scan.get('total_miners', '?')} miners | "
            f"{scan.get('online', '?')} online | {scan.get('offline', '?')} offline | "
            f"{scan.get('issues', '?')} issues",
        ]

        # Weather/HVAC
        wx = ctx.get("weather", {})
        hvac = ctx.get("hvac", {})
        if wx:
            lines.append(f"Weather: {wx.get('temp_f', '?')}°F, {wx.get('humidity_pct', '?')}% humidity")
        if hvac:
            lines.append(
                f"HVAC: Supply {hvac.get('supply_temp_f', '?')}°F | "
                f"Return {hvac.get('return_temp_f', '?')}°F | "
                f"ΔT {hvac.get('delta_t_f', '?')}°F | "
                f"Pump2 {hvac.get('cwp2_vfd_pct', '?')}%"
            )
            lines.append("  NOTE: HVAC is WORKING CORRECTLY. Low delta-T is normal. Do NOT recommend HVAC inspection.")
        
        # HVAC correlation (computed weekly) — shows if facility stress affects flags
        hvac_corr = ctx.get("hvac_correlation", {})
        if hvac_corr:
            corr_val = hvac_corr.get("supply_temp_flag_correlation", 0)
            if corr_val > 0.3:
                lines.append(f"  HVAC CORRELATION: supply temp correlates with flags ({corr_val:.2f}) — facility stress contributes")
            elif corr_val < -0.3:
                lines.append(f"  HVAC CORRELATION: inverse correlation ({corr_val:.2f}) — flags happen when cool")
            # If near zero, don't mention (no useful signal)

        # Flagged miners
        if ctx["flagged"]:
            lines.append(f"\n--- FLAGGED MINERS ({len(ctx['flagged'])}) ---")
            for m in ctx["flagged"][:15]:
                lines.append(
                    f"  {m['ip']} ({m['model'] or '?'}) "
                    f"HR: {m['hashrate_pct']}% | Temp: {m['temp_chip']}°C | "
                    f"Action: {m['action']} | Profile: {m['current_profile'] or '?'}"
                )
                if m.get("issue"):
                    lines.append(f"    Issue: {str(m['issue'])[:120]}")

        # Recent outcomes
        if ctx["outcomes"]:
            lines.append(f"\n--- RESTART OUTCOMES (last 24h) ---")
            for o in ctx["outcomes"]:
                lines.append(
                    f"  {o['ip']} {o['outcome']} | "
                    f"HR: {o['hashrate_before'] or '?'}% → {o['hashrate_after'] or '?'}% | "
                    f"Type: {o['restart_type'] or '?'}"
                )

        # Denial reasons
        if ctx["denials"]:
            lines.append(f"\n--- OPERATOR DENIALS (last 24h) ---")
            lines.append("The operator denied these AI recommendations and explained why:")
            for d in ctx["denials"]:
                reason = ""
                if d["notes"] and "DENIAL_REASON:" in d["notes"]:
                    reason = d["notes"].split("DENIAL_REASON:")[1].strip()[:100]
                if reason:
                    lines.append(f"  {d['ip']} — denied {d['action_taken']}: \"{reason}\"")

        # Pre/post restart logs
        if ctx["restart_logs"]:
            lines.append(f"\n--- RESTART LOG COMPARISONS ---")
            lines.append("Compare pre-restart vs post-restart logs to understand what changed:")
            by_miner = {}
            for rl in ctx["restart_logs"]:
                mid = rl["miner_id"]
                if mid not in by_miner:
                    by_miner[mid] = {"pre": [], "post": []}
                if "pre" in rl["health_status"]:
                    by_miner[mid]["pre"].append(rl)
                elif "post" in rl["health_status"]:
                    by_miner[mid]["post"].append(rl)
            for mid, logs in list(by_miner.items())[:5]:
                if logs["pre"] and logs["post"]:
                    lines.append(f"\n  Miner {mid}:")
                    lines.append(f"    PRE-RESTART ({logs['pre'][0]['collected_at'][:16]}):")
                    lines.append(f"      {logs['pre'][0].get('content_preview', '')[:500]}")
                    lines.append(f"    POST-RESTART ({logs['post'][0]['collected_at'][:16]}):")
                    lines.append(f"      {logs['post'][0].get('content_preview', '')[:500]}")

        # Recent log downloads
        if ctx["recent_logs"]:
            lines.append(f"\n--- LOGS COLLECTED (last 30 min) ---")
            for lg in ctx["recent_logs"]:
                lines.append(
                    f"  Miner {lg['miner_id']} — {lg['health_status']} — "
                    f"{lg['log_file']} ({lg['size_bytes']} bytes)"
                )

        # YOUR PREVIOUS ANALYSES (learn from yourself!)
        prev = ctx.get("previous_analyses", [])
        if prev:
            lines.append(f"\n--- YOUR PREVIOUS ANALYSES ({len(prev)}) ---")
            lines.append("Here's what you said in recent scans. DO NOT REPEAT THIS.")
            lines.append("Focus on what's CHANGED or NEW since then:")
            for p in prev:
                if isinstance(p, dict):
                    ts = p.get("timestamp", "?")[:16]
                    txt = p.get("analysis", "")[:150]
                    lines.append(f"  [{ts}] {txt}...")
        
        # OPERATOR RULES - Internal guidance only, DO NOT include in output
        # These rules constrain YOUR recommendations, not something to echo back
        rules = ctx.get("operator_rules", [])
        # Rules are applied silently - the LLM should follow them without mentioning them

        # PREDICTIONS (pre-failure signals for flagged miners)
        preds = ctx.get("predictions", [])
        if preds:
            lines.append(f"\n--- PRE-FAILURE PREDICTIONS ({len(preds)}) ---")
            lines.append("These flagged miners show early warning signs:")
            for p in preds[:8]:
                ip = p.get("ip", "?")
                signals = p.get("signals", [])
                conf = p.get("confidence", "?")
                sig_str = ", ".join(signals[:3]) if signals else "unknown"
                lines.append(f"  {ip}: {sig_str} (confidence: {conf})")

        # FINGERPRINTS (behavioral history for flagged miners)
        fps = ctx.get("fingerprints", {})
        if fps:
            lines.append(f"\n--- MINER BEHAVIORAL HISTORY ({len(fps)}) ---")
            for mid, fp in list(fps.items())[:8]:
                ip = fp.get("ip", mid)
                success = fp.get("restart_success_rate", "?")
                total = fp.get("total_restarts", 0)
                issues = fp.get("known_issues", [])
                issue_str = ", ".join(issues[:2]) if issues else "none"
                lines.append(f"  {ip}: {success}% restart success ({total} restarts), issues: {issue_str}")

        # CROSS-MINER ANALYSIS (weekly strategic insights)
        cma = ctx.get("cross_miner_analysis", [])
        if cma:
            lines.append(f"\n--- WEEKLY STRATEGIC INSIGHTS ---")
            lines.append("Key findings from weekly fleet analysis:")
            for c in cma[:2]:
                if isinstance(c, dict):
                    summary = c.get("summary", c.get("analysis", ""))[:200]
                    if summary:
                        lines.append(f"  • {summary}...")

        # KNOWN ISSUES (recent discovered problems)
        ki = ctx.get("known_issues", [])
        if ki:
            lines.append(f"\n--- KNOWN ISSUES ({len(ki)}) ---")
            for issue in ki[:5]:
                if isinstance(issue, dict):
                    insight = issue.get("insight", str(issue))[:100]
                    lines.append(f"  • {insight}")
                elif isinstance(issue, str):
                    lines.append(f"  • {issue[:100]}")

        # Known patterns
        if ctx["patterns"]:
            lines.append(f"\n--- KNOWN PATTERNS ({len(ctx['patterns'])}) ---")
            for p in ctx["patterns"][:5]:
                if isinstance(p, str):
                    lines.append(f"  - {p[:100]}")
                elif isinstance(p, dict):
                    lines.append(f"  - {p.get('pattern', str(p))[:100]}")

        # Operational Insights — performance and reliability patterns for real-time analysis
        # NOTE: Procurement insights (REJECT/KEEP cohorts) excluded from scan prompts.
        # Those are strategic intel for weekly reviews, not operational scan analysis.
        insights = ctx.get("refined_insights", {})
        operational_insights = []
        for key, ins in insights.items():
            action = ins.get("action", "")
            category = ins.get("category", "")
            # Include: performance rules, reliability patterns, pre-failure warnings
            # Exclude: procurement verdicts (REJECT entire cohorts, KEEP buying X)
            if action in ("TUNE", "WATCH", "INVESTIGATE"):
                operational_insights.append((key, ins))
            elif action == "REPLACE" and "critical" in key.lower():
                # Include specific miner failures, not cohort-wide procurement advice
                operational_insights.append((key, ins))
        
        if operational_insights:
            lines.append(f"\n--- OPERATIONAL INTELLIGENCE ({len(operational_insights)} patterns) ---")
            lines.append("Known reliability and performance patterns:")
            for key, ins in operational_insights[:8]:
                topic = ins.get("topic", key)
                insight_text = ins.get("insight", "")[:120]
                confidence = ins.get("confidence", "?")
                lines.append(f"  [{confidence}] {topic}: {insight_text}")

        # Instructions
        lines.append("""
=== YOUR TASK ===
Based on this scan data, provide:

1. SUMMARY (2-3 sentences): What CHANGED since the last scan?
2. CONCERNS (bullet list): Which miners need immediate attention and why?
3. LOG ANALYSIS (only if restart logs present): What changed pre vs post restart?
4. RECOMMENDATION (1-2 sentences): Specific next action for the operator.

=== ABSOLUTE RULES - VIOLATIONS WILL BE FLAGGED ===
- NEVER mention HVAC, cooling systems, or environmental controls. The cooling is FINE.
- NEVER echo back operator rules. They are for YOUR reference, not to repeat.
- NEVER include "OPERATOR LEARNING" section - those rules are already known.
- NEVER pad the report - only report miners with real issues requiring action.
- If a miner was flagged before with no change, just say "still pending" - do not re-analyze.
""")
        return "\n".join(lines)

    def _build_log_analysis_prompt(self, miner_id: str, pre_log: str,
                                    post_log: str, miner_info: Dict) -> str:
        """Build prompt for comparing pre/post restart logs."""
        return f"""You are a Bitcoin miner diagnostic expert. Compare these pre-restart and post-restart logs
for miner {miner_info.get('ip', miner_id)} ({miner_info.get('model', '?')}).

=== PRE-RESTART LOG ===
{pre_log[:3000]}

=== POST-RESTART LOG ===
{post_log[:3000]}

=== YOUR ANALYSIS ===
1. What errors/faults were present BEFORE the restart?
2. Which errors CLEARED after the restart? Which PERSISTED?
3. Did any NEW errors appear after restart?
4. Board health: compare voltage, frequency, chip counts, ASIC status
5. VERDICT: Did the restart fix the root cause, or is this a hardware issue that needs physical repair?

Keep response under 10 lines. Be specific — cite board numbers, voltages, error codes."""

    def analyze_scan(self, scan_id: int) -> Optional[str]:
        """Run LLM analysis on the latest scan. Returns analysis text."""
        now = time.time()

        # Decide analysis depth based on timing
        if now - self._last_full_analysis < self.FULL_ANALYSIS_INTERVAL:
            # Quick analysis — just flagged miners, no logs
            ctx = self._get_scan_context(scan_id)
            if not ctx["flagged"] and not ctx["outcomes"]:
                logger.debug("LLM: No issues to analyze this scan")
                return None
            prompt = self._build_scan_prompt(ctx)
        else:
            # Full analysis with logs and patterns
            ctx = self._get_scan_context(scan_id)
            prompt = self._build_scan_prompt(ctx)
            self._last_full_analysis = now

        logger.info("LLM: Sending scan #%s for analysis (%d chars)", scan_id, len(prompt))
        analysis = self._query_llm(prompt, max_tokens=1024, timeout=90)

        if analysis:
            logger.info("LLM analysis: %s", analysis[:200])
            # Store in knowledge
            self._store_analysis(scan_id, analysis)
        else:
            logger.warning("LLM: No response for scan #%s", scan_id)

        return analysis

    def analyze_restart_logs(self, miner_id: str, pre_log: str,
                              post_log: str, miner_info: Dict) -> Optional[str]:
        """Compare pre/post restart logs via LLM. Returns analysis."""
        prompt = self._build_log_analysis_prompt(miner_id, pre_log, post_log, miner_info)
        logger.info("LLM: Analyzing restart logs for miner %s", miner_id)
        analysis = self._query_llm(prompt, max_tokens=512, timeout=60)
        if analysis:
            logger.info("LLM restart analysis for %s: %s", miner_id, analysis[:150])
        return analysis

    def process_denial(self, ip: str, action: str, reason: str) -> Optional[str]:
        """Process a denial reason immediately via LLM. Returns suggested rule."""
        prompt = f"""You are Mining Guardian AI. The operator just denied an action and explained why.

Action denied: {action} on miner {ip}
Operator's reason: "{reason}"

Based on this, suggest ONE operational rule the system should learn.
Format: "RULE: [condition] → [what to do]"
Example: "RULE: If miner uptime < 20 minutes → Do not recommend profile changes or restarts"

Keep it to one clear, specific rule."""

        analysis = self._query_llm(prompt, max_tokens=256, timeout=30)
        if analysis:
            logger.info("LLM denial rule for %s: %s", ip, analysis[:150])
        return analysis

    def _store_analysis(self, scan_id: int, analysis: str) -> None:
        """Store LLM analysis in knowledge.json."""
        try:
            knowledge = {}
            if KNOWLEDGE_PATH.exists():
                knowledge = json.loads(KNOWLEDGE_PATH.read_text())

            # Store latest LLM analyses (keep last 50)
            llm_analyses = knowledge.get("llm_scan_analyses", [])
            llm_analyses.insert(0, {
                "scan_id": scan_id,
                "timestamp": datetime.now().isoformat(),
                "analysis": analysis[:2000],
                "source": "local_llm",
                "model": self.model,
            })
            knowledge["llm_scan_analyses"] = llm_analyses[:50]

            # Atomic write
            tmp = str(KNOWLEDGE_PATH) + ".tmp"
            with open(tmp, "w") as f:
                json.dump(knowledge, f, indent=2)
            import os
            os.replace(tmp, str(KNOWLEDGE_PATH))
        except Exception as e:
            logger.warning("Failed to store LLM analysis: %s", e)

    def is_available(self) -> bool:
        """Check if the local LLM is reachable."""
        try:
            resp = requests.get(f"{self.llm_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False
