#!/usr/bin/env python3
"""
train_cohort.py — Mining Guardian Cohort-Based Weekly Training

This is the SCALE-FIRST replacement for train_comprehensive.py.

WHY THIS EXISTS
===============
The original train_comprehensive.py made one Claude API call per miner. At our
49-miner test mine that was 49 calls, each carrying ~25-30K tokens of context
because we removed the cap on local LLM analyses. We hit the Tier 1 rate limit
on miner #3.

At production scale (5,000 miners per site), one-call-per-miner is fundamentally
broken — it would take hours of pure rate-limit waiting and cost $5,000+ per run.

THE COHORT APPROACH
===================
Miners are grouped into cohorts by their hardware identity:
    (model, firmware_manufacturer, chip_bin, pcb_version, cooling_mode)

Most miners in a fleet are essentially identical at the hardware level. A cohort
of 30 miners with the same chip_bin and pcb_version will all behave the same way
under the same conditions. Analyzing them as a group is BOTH faster AND more
accurate than analyzing them individually — Claude sees the fleet-wide pattern
instead of 30 disconnected per-miner stories.

OUTLIERS get individual attention. A miner whose hashrate is >2σ below its
cohort mean, or whose temperature is >2σ above, gets analyzed alone because
something specific is wrong with THAT unit.

SCALE COMPARISON
================
  49 miners (test):    49 calls -> ~10-15 cohorts + ~5-10 outliers + 1 fleet =  16-26 calls
  500 miners:          500 calls -> ~15-25 cohorts + ~20-40 outliers + 1 fleet = 36-66 calls
  5,000 miners:        5000 calls -> ~30-80 cohorts + ~50-100 outliers + 1 fleet = 81-181 calls
  50,000 miners:       50000 calls -> ~50-150 cohorts + ~200-500 outliers + 1 fleet = 251-651 calls

The cohort count grows sub-linearly with fleet size (more miners just deepens
the cohorts that already exist), so this stays under any reasonable rate limit
and keeps weekly training cost flat across mine sizes.

WHAT CLAUDE PRODUCES PER LAYER
==============================
  Cohort pass:    Per-cohort behavioral baseline, common failure modes,
                  recommended action bias for THIS cohort
  Outlier pass:   Per-miner deep dive (only for flagged outliers)
  Fleet pass:     Cross-cohort patterns, procurement recommendations,
                  validates the local LLM's weekly conclusions, refines
                  operator rules

This is the SAME code path that production sites will use with their local LLM
(Qwen 32B) instead of Claude. Cohort-based grouping reduces local LLM workload
just as much as it reduces Claude workload — each container only needs to run
~30 cohort analyses per training cycle instead of 240.
"""

import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / 'ai'))
sys.path.insert(0, str(_ROOT / 'core'))

from llm_analyzer import LLMAnalyzer
from knowledge_manager import KnowledgeManager
from insight_manager import process_refined_insights, migrate_legacy_insight
from train_comprehensive import (
    get_miner_full_profile,
    build_miner_prompt,
    get_hvac_weather_context,
    get_cross_miner_correlations,
)

try:
    from ai.catalog_context import get_miner_catalog_context
except ImportError:
    def get_miner_catalog_context(model_name):
        return ""

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger('train_cohort')

DB_PATH = str(_ROOT / 'guardian.db')
KNOWLEDGE_PATH = _ROOT / 'knowledge.json'

# Tunables — keep these conservative for Tier 1 safety
MAX_LOCAL_LLM_ANALYSES_PER_COHORT = 25   # how many recent local LLM analyses to include in each cohort prompt
MAX_LOCAL_LLM_ANALYSES_PER_OUTLIER = 15  # how many for an outlier prompt
OUTLIER_HASHRATE_SIGMA = 2.0            # miners >2σ below cohort mean HR
OUTLIER_TEMP_SIGMA = 2.0                # miners >2σ above cohort mean temp
MAX_OUTLIERS_PER_RUN = 30               # hard cap to prevent runaway
INTER_REQUEST_PAUSE_SECONDS = 1         # gap between Claude calls (gentle pacing)


# ──────────────────────────────────────────────────────────────────────
# Cohort building
# ──────────────────────────────────────────────────────────────────────

def _normalize_model(model: str) -> str:
    """Collapse cosmetic model variants into a single canonical form.

    Examples:
      'Antminer S19JPro'  -> 's19jpro'
      'Antminer S19j Pro' -> 's19jpro'
      'S19JPro'           -> 's19jpro'
      'Antminer S21Imm'   -> 's21imm'
      'AH3880'            -> 'ah3880'
    """
    if not model:
        return 'unknown'
    s = str(model).strip().lower()
    s = s.replace('antminer', '').strip()
    s = s.replace(' ', '').replace('-', '').replace('.', '')
    return s or 'unknown'


def _normalize_field(value: str) -> str:
    """Strip noise (trailing commas, whitespace) from hardware fingerprint fields."""
    if not value:
        return ''
    return str(value).strip().strip(',').strip()


def build_cohorts(conn: sqlite3.Connection) -> Dict[Tuple, List[Dict]]:
    """Group miners by hardware identity into cohorts.

    Returns a dict keyed by cohort tuple, with values being lists of miner
    summary dicts (one per miner in the cohort).

    Cohort key: (model, firmware_manufacturer, chip_bin, pcb_version, cooling_mode)

    A miner with missing hardware fingerprint data falls into the
    'unknown_hardware' cohort for that field — we still group them but flag
    them so the prompt can mention the data gap.
    """
    # Pull the most recent reading per miner with hardware fingerprint joined in
    rows = conn.execute('''
        SELECT
            mr.miner_id,
            mr.ip,
            mr.model,
            COALESCE(mr.firmware_manufacturer, '') as firmware,
            COALESCE(mr.cooling_mode, '') as cooling,
            mr.hashrate_pct,
            mr.temp_chip,
            mr.status,
            mr.action,
            COALESCE(
                (SELECT chip_bin FROM miner_hardware
                 WHERE miner_id = mr.miner_id AND chip_bin IS NOT NULL
                 LIMIT 1),
                ''
            ) as chip_bin,
            COALESCE(
                (SELECT pcb_version FROM miner_hardware
                 WHERE miner_id = mr.miner_id AND pcb_version IS NOT NULL
                 LIMIT 1),
                ''
            ) as pcb_version
        FROM miner_readings mr
        WHERE mr.id IN (
            SELECT MAX(id) FROM miner_readings GROUP BY miner_id
        )
        ORDER BY mr.miner_id
    ''').fetchall()

    cohorts: Dict[Tuple, List[Dict]] = {}
    for r in rows:
        # Normalize each field to collapse cosmetic variants
        norm_model = _normalize_model(r['model'])
        norm_firmware = _normalize_field(r['firmware']).upper() or 'unknown_fw'
        norm_chip_bin = _normalize_field(r['chip_bin']) or 'unknown_chip'
        norm_pcb = _normalize_field(r['pcb_version']) or 'unknown_pcb'
        norm_cooling = _normalize_field(r['cooling']) or 'unknown_cool'
        key = (norm_model, norm_firmware, norm_chip_bin, norm_pcb, norm_cooling)
        cohorts.setdefault(key, []).append(dict(r))

    logger.info('Built %d cohorts from %d miners', len(cohorts), len(rows))
    for key, members in sorted(cohorts.items(), key=lambda x: -len(x[1])):
        logger.info('  %2d miners: %s', len(members), '/'.join(str(k) for k in key))
    return cohorts


def summarize_cohort(conn: sqlite3.Connection, cohort_key: Tuple,
                      members: List[Dict]) -> Dict:
    """Compute SQL aggregates for a cohort. No LLM, no API calls.

    Returns the data Claude needs to understand this cohort's behavior:
    averages, ranges, restart success rates, common issues, outlier list.
    """
    miner_ids = [m['miner_id'] for m in members]
    if not miner_ids:
        return {}

    placeholders = ','.join('?' for _ in miner_ids)

    # Fleet-wide aggregates for these miners
    agg = conn.execute(f'''
        SELECT
            COUNT(DISTINCT miner_id) as miner_count,
            ROUND(AVG(hashrate_pct), 1) as avg_hr,
            ROUND(MIN(hashrate_pct), 1) as min_hr,
            ROUND(MAX(hashrate_pct), 1) as max_hr,
            ROUND(AVG(CASE WHEN temp_chip > 0 THEN temp_chip END), 1) as avg_temp,
            MAX(temp_chip) as max_temp,
            COUNT(*) as total_readings,
            SUM(CASE WHEN status='offline' THEN 1 ELSE 0 END) as offline_count,
            SUM(CASE WHEN action NOT IN ('MONITOR','') AND action IS NOT NULL THEN 1 ELSE 0 END) as flag_count
        FROM miner_readings
        WHERE miner_id IN ({placeholders})
          AND scanned_at >= datetime('now', '-7 days')
    ''', miner_ids).fetchone()

    # Restart outcomes for this cohort over the week
    outcomes = conn.execute(f'''
        SELECT outcome, COUNT(*) as cnt
        FROM miner_restarts
        WHERE miner_id IN ({placeholders})
          AND restarted_at >= datetime('now', '-7 days')
          AND outcome IS NOT NULL
        GROUP BY outcome
    ''', miner_ids).fetchall()

    # Common failure patterns (from action_audit_log problems)
    problems = conn.execute(f'''
        SELECT problem, COUNT(*) as cnt
        FROM action_audit_log
        WHERE miner_id IN ({placeholders})
          AND timestamp >= datetime('now', '-7 days')
          AND problem IS NOT NULL AND problem != ''
        GROUP BY problem
        ORDER BY cnt DESC
        LIMIT 5
    ''', miner_ids).fetchall()

    # Outliers: miners >OUTLIER_HASHRATE_SIGMA below the cohort mean HR
    # or >OUTLIER_TEMP_SIGMA above cohort mean temp
    outliers = []
    if len(members) >= 3:  # need at least 3 to compute meaningful sigma
        # Compute per-miner average HR over the week
        hr_rows = conn.execute(f'''
            SELECT miner_id, ip,
                   ROUND(AVG(hashrate_pct), 1) as avg_hr,
                   ROUND(AVG(CASE WHEN temp_chip > 0 THEN temp_chip END), 1) as avg_temp
            FROM miner_readings
            WHERE miner_id IN ({placeholders})
              AND scanned_at >= datetime('now', '-7 days')
            GROUP BY miner_id
        ''', miner_ids).fetchall()

        hrs = [r['avg_hr'] for r in hr_rows if r['avg_hr'] is not None]
        temps = [r['avg_temp'] for r in hr_rows if r['avg_temp'] is not None]
        if hrs:
            mean_hr = sum(hrs) / len(hrs)
            var_hr = sum((h - mean_hr) ** 2 for h in hrs) / len(hrs)
            std_hr = var_hr ** 0.5
            hr_threshold = mean_hr - OUTLIER_HASHRATE_SIGMA * std_hr
        else:
            mean_hr = std_hr = hr_threshold = 0
        if temps:
            mean_temp = sum(temps) / len(temps)
            var_temp = sum((t - mean_temp) ** 2 for t in temps) / len(temps)
            std_temp = var_temp ** 0.5
            temp_threshold = mean_temp + OUTLIER_TEMP_SIGMA * std_temp
        else:
            mean_temp = std_temp = temp_threshold = 0

        for r in hr_rows:
            reasons = []
            if r['avg_hr'] is not None and std_hr > 0 and r['avg_hr'] < hr_threshold:
                reasons.append(f"HR {r['avg_hr']}% < cohort threshold {hr_threshold:.1f}%")
            if r['avg_temp'] is not None and std_temp > 0 and r['avg_temp'] > temp_threshold:
                reasons.append(f"temp {r['avg_temp']}°C > cohort threshold {temp_threshold:.1f}°C")
            if reasons:
                outliers.append({
                    'miner_id': r['miner_id'],
                    'ip': r['ip'],
                    'avg_hr': r['avg_hr'],
                    'avg_temp': r['avg_temp'],
                    'reasons': reasons,
                })

    return {
        'cohort_key': cohort_key,
        'member_count': len(members),
        'aggregates': dict(agg) if agg else {},
        'restart_outcomes': [dict(o) for o in outcomes],
        'top_problems': [dict(p) for p in problems],
        'outliers': outliers,
        'all_member_ips': [m['ip'] for m in members],
    }


# ──────────────────────────────────────────────────────────────────────
# Prompt builders
# ──────────────────────────────────────────────────────────────────────

def _filter_local_llm_for_ips(all_analyses: List[Dict], ips: List[str],
                                limit: int) -> List[Dict]:
    """Pick the most recent local LLM analyses that mention any of the given IPs."""
    if not all_analyses or not ips:
        return []
    ip_set = set(ips)
    matched = []
    for a in all_analyses:  # already in newest-first order
        text = (a.get('analysis') or '')
        if any(ip in text for ip in ip_set):
            matched.append(a)
            if len(matched) >= limit:
                break
    return matched


def build_cohort_prompt(summary: Dict, env_context: str,
                         local_llm_analyses: List[Dict],
                         catalog_context: str = "") -> str:
    """Build the Claude prompt for a single cohort. Designed to stay <8K tokens."""
    key = summary['cohort_key']
    agg = summary.get('aggregates') or {}
    outcomes = summary.get('restart_outcomes') or []
    problems = summary.get('top_problems') or []
    outliers = summary.get('outliers') or []

    lines = [
        '=' * 60,
        f"COHORT: {' / '.join(str(k) for k in key)}",
        '=' * 60,
        f"Members: {summary['member_count']} miners",
        '',
        '--- Aggregates (last 7 days) ---',
        f"  Avg hashrate: {agg.get('avg_hr', '?')}%   range: [{agg.get('min_hr','?')}, {agg.get('max_hr','?')}]",
        f"  Avg chip temp: {agg.get('avg_temp', '?')}°C   max: {agg.get('max_temp', '?')}°C",
        f"  Total readings: {agg.get('total_readings', 0)}",
        f"  Offline events: {agg.get('offline_count', 0)}",
        f"  Times flagged for action: {agg.get('flag_count', 0)}",
    ]

    if outcomes:
        lines.append('')
        lines.append('--- Restart outcomes (last 7 days) ---')
        for o in outcomes:
            lines.append(f"  {o['outcome']}: {o['cnt']}")

    if problems:
        lines.append('')
        lines.append('--- Top problems triggered ---')
        for p in problems:
            lines.append(f"  ({p['cnt']}x) {p['problem'][:100]}")

    if outliers:
        lines.append('')
        lines.append(f'--- Within-cohort outliers ({len(outliers)}) ---')
        for o in outliers:
            lines.append(f"  {o['ip']}: {'; '.join(o['reasons'])}")

    if local_llm_analyses:
        lines.append('')
        lines.append(f'--- Local LLM analyses for this cohort (most recent {len(local_llm_analyses)}) ---')
        for a in local_llm_analyses:
            ts = (a.get('timestamp') or '?')[:16]
            text = (a.get('analysis') or '')[:400]
            lines.append(f"  [{ts}] {text}")
            lines.append('')

    if catalog_context:
        lines.append('')
        lines.append('=== INTELLIGENCE CATALOG (manufacturer specs for this cohort model) ===')
        lines.append(catalog_context)

    lines.extend([
        '',
        '=== ENVIRONMENT CONTEXT ===',
        env_context[:1500],
        '',
                '=== OPERATOR RULES (MUST FOLLOW) ===',
        'These rules are set by the fleet operator and override any default heuristics:',
        '',
        '1. TEMPERATURE: This is a LIQUID-COOLED fleet. Chip temps of 67-73°C are NORMAL',
        '   and require NO action. Do NOT flag, warn about, or recommend action for any',
        '   miner running below 84°C. Do NOT describe miners under 84°C as "running hot",',
        '   "overheating", or "thermally stressed". Only chip temps >=84°C warrant action.',
        '',
        '2. HVAC: The USA 188 HVAC system is performing CORRECTLY. The supply/return',
        '   water delta-T is intentionally LOW right now and will rise as outside temps',
        '   climb (seasonal behavior). Do NOT recommend "check the HVAC because delta-T',
        '   is low". Do NOT describe low delta-T as "minimal headroom" or "thermal stress".',
        '   Assume the HVAC is fine unless multiple miners simultaneously exceed 84°C.',
        '',
        '3. ACTION RECOMMENDATIONS: Bias toward documenting hardware patterns over',
        '   recommending environmental changes. The cooling system is rarely the problem.',
        '',
        '=== YOUR TASK ===',
        f'You are Claude — an expert Bitcoin mining fleet analyst. Analyze this cohort of {summary["member_count"]} miners as a GROUP, not individually.',
        '',
        'Your audience is the fleet operator and the on-site local LLM (Qwen 32B) that runs',
        'between your weekly visits. The on-site LLM will read your analysis next week and use',
        'it to make per-scan decisions, so be SPECIFIC and PRESCRIPTIVE — generic advice helps',
        'no one. Reference actual miner IPs, actual hashrate numbers, actual temperatures.',
        '',
        '1. BEHAVIORAL BASELINE (3-5 sentences): What is normal for this hardware cohort?',
        '   Use the aggregates as ground truth. Note any unusual baseline characteristics',
        '   (e.g., these miners run hot, these miners restart often, these miners drift HR).',
        '',
        '2. COMMON FAILURE MODES (detailed bullet list, 4-8 items): What problems repeat',
        '   across this cohort? Distinguish hardware-pattern issues (chip degradation, PSU',
        '   failures, board death) from environmental triggers (HVAC stress, ambient temp,',
        '   water flow). For each mode, cite the data evidence (e.g., "39 occurrences in',
        '   action_audit_log over 7 days").',
        '',
        '3. RESTART EFFECTIVENESS (2-3 sentences): Calculate the SUCCESS RATE from the',
        '   restart_outcomes data. Are restarts actually fixing root causes, or just',
        '   resetting symptoms? Does this cohort show "restart fatigue" (multiple restarts',
        '   without lasting improvement)?',
        '',
        '4. RECOMMENDED ACTION BIAS (4-6 specific recommendations): For THIS cohort',
        '   specifically, what action thresholds should the on-site LLM use? Be numeric:',
        '   - HR threshold for flagging restart: ___% (vs fleet default 80%)',
        '   - Restart attempts before ticketing: ___ (vs fleet default 3)',
        '   - Temp threshold for action: ___°C (vs fleet default 86°C)',
        '   - Cooldown after restart: ___ min (vs fleet default 20)',
        '   - Special handling rules unique to this cohort',
        '',
        '5. WHICH OUTLIERS NEED INDIVIDUAL ATTENTION: For each listed outlier, decide',
        '   whether it needs a deeper individual deep-dive (will be done in the next pass)',
        '   or if its issue is already explained by cohort-wide patterns. Justify each.',
        '',
        '6. HARDWARE QUALITY ASSESSMENT (2-3 sentences): Based on this weeks data, is',
        '   this cohort a candidate for procurement review? Are the units holding up to',
        '   spec, or is there a hardware quality concern that warrants ordering replacements?',
        '',
        '7. CROSS-COHORT INSIGHTS (1-2 sentences): Anything notable about how this cohort',
        '   compares to the rest of the fleet? Higher/lower restart rates? More/less',
        '   thermal headroom? This will feed into the fleet-wide synthesis pass.',
        '',
        'Format with markdown headers. Cite specific evidence. Aim for 600-1200 words of',
        'genuine analysis — no filler, no executive summary fluff.',
    ])
    return '\n'.join(lines)


def build_outlier_prompt(miner_id: str, profile: dict, cohort_key: Tuple,
                          env_context: str, local_llm_analyses: List[Dict]) -> str:
    """Build a focused prompt for one outlier miner. Reuses the existing
    build_miner_prompt for the deep miner data, then adds cohort context."""
    base = build_miner_prompt(miner_id, profile)

    extras = [
        '',
        '=== COHORT CONTEXT ===',
        f"This miner belongs to cohort: {' / '.join(str(k) for k in cohort_key)}",
        f'It was flagged as an outlier within its own cohort because something',
        f'specific is wrong with THIS unit, not the hardware family.',
    ]

    if local_llm_analyses:
        extras.append('')
        extras.append(f'--- Local LLM observations mentioning this miner ({len(local_llm_analyses)}) ---')
        for a in local_llm_analyses:
            ts = (a.get('timestamp') or '?')[:16]
            text = (a.get('analysis') or '')[:300]
            extras.append(f'  [{ts}] {text}')
            extras.append('')

    extras.extend([
        '',
        '=== ENVIRONMENT CONTEXT ===',
        env_context[:1000],
        '',
                '=== OPERATOR RULES (MUST FOLLOW) ===',
        'These rules are set by the fleet operator and override any default heuristics:',
        '',
        '1. TEMPERATURE: This is a LIQUID-COOLED fleet. Chip temps of 67-73°C are NORMAL',
        '   and require NO action. Do NOT flag, warn about, or recommend action for any',
        '   miner running below 84°C. Do NOT describe miners under 84°C as "running hot",',
        '   "overheating", or "thermally stressed". Only chip temps >=84°C warrant action.',
        '',
        '2. HVAC: The USA 188 HVAC system is performing CORRECTLY. The supply/return',
        '   water delta-T is intentionally LOW right now and will rise as outside temps',
        '   climb (seasonal behavior). Do NOT recommend "check the HVAC because delta-T',
        '   is low". Do NOT describe low delta-T as "minimal headroom" or "thermal stress".',
        '   Assume the HVAC is fine unless multiple miners simultaneously exceed 84°C.',
        '',
        '3. ACTION RECOMMENDATIONS: Bias toward documenting hardware patterns over',
        '   recommending environmental changes. The cooling system is rarely the problem.',
        '',
        '=== YOUR TASK ===',
        'This miner is an OUTLIER within its hardware cohort. Something specific is wrong',
        'with THIS unit, distinct from the cohort-wide patterns. The fleet operator needs',
        'to know whether this is a repair candidate, a replacement candidate, or a tuning',
        'opportunity.',
        '',
        '1. ROOT CAUSE HYPOTHESIS (3-5 sentences): What is most likely wrong with this',
        '   miner? Be specific — name the suspected component (PSU, hashboard, chip die,',
        '   chip bin, control board, fan, network, AMS sync, etc.). Reference the chip',
        '   bin or PCB version if hardware fingerprint data is available.',
        '',
        '2. EVIDENCE FROM DATA (5-10 bullet points): Cite specific numbers from the',
        '   profile and from the local LLM observations above. Examples: "Hashrate has',
        '   dropped from 145 TH/s to 35 TH/s over the past 4 days while temp climbed',
        '   from 68°C to 79°C — classic thermal throttling pattern". Be quantitative.',
        '',
        '3. CONFIDENCE LEVEL (1 sentence): How confident are you in the diagnosis (high/',
        '   medium/low) and what data would increase confidence?',
        '',
        '4. RECOMMENDED ACTION (2-4 specific steps): What should the operator do? Order',
        '   matters — what to try first, what to escalate to. Include thresholds for',
        '   when to give up and ticket. Examples:',
        '   - First: PDU cycle, wait 20 min, check if HR recovers above X%',
        '   - Second: collect logs, look for chain disconnect events',
        '   - Third: ticket as bad PSU, swap to spare',
        '',
        '5. PARALLEL INDICATORS (1-2 sentences): Are there other miners in the fleet',
        '   showing similar early warning signs that we should preemptively check?',
        '',
        'Format with markdown headers. 400-800 words.',
    ])
    return base + '\n' + '\n'.join(extras)


def build_fleet_prompt(cohort_results: List[Dict], outlier_results: List[Dict],
                       all_local_llm_analyses: List[Dict],
                       operator_rules: List[str],
                       cross_miner_text: str) -> str:
    """Build the final fleet-wide synthesis prompt. Gets EVERYTHING."""
    lines = [
        '=' * 60,
        'FLEET-WIDE WEEKLY SYNTHESIS',
        '=' * 60,
        f'Cohorts analyzed: {len(cohort_results)}',
        f'Outlier miners analyzed: {len(outlier_results)}',
        f'Local LLM scan analyses available: {len(all_local_llm_analyses)}',
        f'Operator rules captured this week: {len(operator_rules)}',
        '',
        '=== COHORT ANALYSIS RESULTS ===',
    ]
    for cr in cohort_results:
        lines.append('')
        lines.append(f"--- {' / '.join(str(k) for k in cr['cohort_key'])} ({cr['member_count']} miners) ---")
        lines.append(cr.get('claude_response', '')[:1500])

    if outlier_results:
        lines.append('')
        lines.append('=== OUTLIER ANALYSIS RESULTS ===')
        for o in outlier_results:
            lines.append('')
            lines.append(f"--- Miner {o['miner_id']} ({o.get('ip', '?')}) ---")
            lines.append(o.get('claude_response', '')[:800])

    if operator_rules:
        lines.append('')
        lines.append('=== OPERATOR RULES (extracted by local LLM from denials) ===')
        for r in operator_rules:
            lines.append(f'  - {r}')

    if cross_miner_text:
        lines.append('')
        lines.append('=== CROSS-MINER CORRELATIONS (from SQL) ===')
        lines.append(cross_miner_text[:5000])

    if all_local_llm_analyses:
        lines.append('')
        lines.append(f'=== ALL LOCAL LLM SCAN ANALYSES THIS WEEK ({len(all_local_llm_analyses)}) ===')
        lines.append('Below are all the analyses the on-site LLM (Qwen 32B) produced.')
        lines.append('Validate its conclusions, correct mistakes, identify patterns it missed.')
        for a in all_local_llm_analyses:
            ts = (a.get('timestamp') or '?')[:16]
            text = (a.get('analysis') or '')[:300]
            lines.append('')
            lines.append(f'[{ts}] {text}')

    lines.extend([
        '',
                '=== OPERATOR RULES (MUST FOLLOW) ===',
        'These rules are set by the fleet operator and override any default heuristics:',
        '',
        '1. TEMPERATURE: This is a LIQUID-COOLED fleet. Chip temps of 67-73°C are NORMAL',
        '   and require NO action. Do NOT flag, warn about, or recommend action for any',
        '   miner running below 84°C. Do NOT describe miners under 84°C as "running hot",',
        '   "overheating", or "thermally stressed". Only chip temps >=84°C warrant action.',
        '',
        '2. HVAC: The USA 188 HVAC system is performing CORRECTLY. The supply/return',
        '   water delta-T is intentionally LOW right now and will rise as outside temps',
        '   climb (seasonal behavior). Do NOT recommend "check the HVAC because delta-T',
        '   is low". Do NOT describe low delta-T as "minimal headroom" or "thermal stress".',
        '   Assume the HVAC is fine unless multiple miners simultaneously exceed 84°C.',
        '',
        '3. ACTION RECOMMENDATIONS: Bias toward documenting hardware patterns over',
        '   recommending environmental changes. The cooling system is rarely the problem.',
        '',
        '=== YOUR TASK ===',
        'You are Claude — the weekly fleet analyst for BiXBiT USAs Mining Guardian system.',
        'You have just read the full weekly state of the fleet: 16 cohort analyses, 3 outlier',
        'analyses, every local LLM observation from the past week (130+ entries), every',
        'operator decision and denial reason, and the cross-miner correlation data.',
        '',
        'Your job is to produce the WEEKLY FLEET REPORT that the on-site LLM will read next',
        'week and the operator will act on. This report becomes part of the systems long-term',
        'memory — it is the highest-leverage moment in the entire learning cycle.',
        '',
        '1. EXECUTIVE SUMMARY (3-5 sentences): What is the headline of this week? What is',
        '   the single most important thing the operator should know? What changed from',
        '   previous weeks (if cross_miner_analysis history is available)?',
        '',
        '2. TOP 5 SYSTEMIC ISSUES (numbered list with detail): What patterns repeat across',
        '   multiple cohorts? Distinguish:',
        '   a) Hardware quality patterns (specific chip bins / PCB versions failing)',
        '   b) Firmware bugs (BiXBiT vs Stock vs Auradine differences)',
        '   c) Environmental stressors (HVAC correlation, weather, time-of-day)',
        '   d) Operator behavior patterns (what gets denied vs approved and why)',
        '   e) AMS data quality issues (false offlines, alert noise, ticket gaps)',
        '   For each, cite specific cohorts and miners affected, and propose one concrete',
        '   action the operator could take in the next week.',
        '',
        '3. PROCUREMENT REVIEW (per-cohort recommendation): For each of the 16 cohorts,',
        '   give a one-line verdict: KEEP / WATCH / REPLACE. Justify any REPLACE call with',
        '   the data. KEEP is the default — only flag REPLACE if hardware quality is genuinely',
        '   suspect. WATCH means "monitor closely for one more week".',
        '',
        '4. LOCAL LLM PERFORMANCE REVIEW (bullet list, 5-10 items): The on-site LLM (Qwen',
        '   32B) made 130+ scan analyses this week. Sample several at random (cite their',
        '   timestamps) and:',
        '   - Was its diagnosis correct? What did it get right?',
        '   - What did it miss that you can see now with fleet-wide context?',
        '   - Where was it overconfident? Underconfident?',
        '   - What pattern recognition could it learn from your analysis?',
        '   This is critical — your job is to TRAIN the local LLM, not replace it.',
        '',
        '5. OPERATOR RULE REFINEMENT (bullet list): Look at the 3 captured operator rules',
        '   from denial reasons. For each:',
        '   - Is the rule correctly stated, or should it be generalized/narrowed?',
        '   - Should any rules be merged into one?',
        '   - Are there NEW rules implied by patterns you see in the data that the system',
        '     hasnt captured yet? Propose them.',
        '',
        '6. PREDICTIVE WARNINGS (bullet list, 3-7 items): Based on the trends in the data,',
        '   what miners are likely to fail or need attention in the NEXT 7 days? Be specific:',
        '   miner IP, expected failure mode, expected timeframe, what to do preemptively.',
        '   This is where you earn your weekly run — predict the future with the data you have.',
        '',
        '7. NEXT-WEEK FOCUS AREAS (numbered list, 3-5 items): What should the on-site LLM',
        '   pay closest attention to in the next 7 days? What signals matter most? What',
        '   should it ignore that it has been over-flagging?',
        '',
        '8. METRICS TO ADD (bullet list, optional): Are there metrics or data points the',
        '   system isnt currently capturing that would help future analysis? This goes to',
        '   Bobby for the next sprint.',
        '',
        '9. REFINED INSIGHTS (CRITICAL — JSON OUTPUT REQUIRED):',
        '   After your narrative analysis, you MUST output a ```json block containing',
        '   permanent, data-backed insights for the Fleet Intelligence dashboard.',
        '   These are NOT weekly summaries — they persist and accumulate.',
        '',
        '   GOLD STANDARD EXAMPLE: "PCB=0110/BOM=0020 boards averaging 13.6% hashrate',
        '   while PCB=0130/BOM=0010 hit 73.5%. Reject all 0110/0020 combinations."',
        '',
        '   Output format (after your narrative):',
        '   ```json',
        '   {',
        '     "refined_insights": {',
        '       "descriptive_key": {',
        '         "category": "PCB/BOM Failure",',
        '         "topic": "0110_0020_boards",',
        '         "insight": "One crisp sentence with specific numbers.",',
        '         "action": "REJECT",',
        '         "confidence": "HIGH",',
        '         "cooling_type": "HYDRO",',
        '         "miner_type": "Antminer S19J Pro",',
        '         "data_source": "847 chip readings over 14 days",',
        '         "miners_affected": ["53482", "64407"],',
        '         "data_points": 847',
        '       }',
        '     }',
        '   }',
        '   ```',
        '',
        '   CATEGORIES: Chip Quality, PCB/BOM Failure, Serial Batch Pattern, PSU Reliability,',
        '   Hashboard Reliability, Firmware Insight, Restart Effectiveness, Parts Donor,',
        '   Golden Miner, Procurement Action',
        '',
        '   CONFIDENCE: HIGH (100+ points, 7+ days, >20% gap), MEDIUM (25-99 points),',
        '   LOW (<25 points)',
        '',
        '   ACTION VALUES: REJECT, WATCH, KEEP, REPLACE, INVESTIGATE, TUNE, NONE',
        '',
        '   RULES: Only output insights backed by data. Be SPECIFIC with numbers.',
        '   Quality over quantity — 1-3 strong insights beats 10 weak ones.',
        '   If no clear insight, output empty: "refined_insights": {}',
        '',
        'Format with markdown headers. Cite cohorts and miners by name throughout. This',
        'is the most important document the system produces all week — aim for 1500-3000',
        'words of dense, evidence-backed analysis. No filler, no hedging, no executive',
        'summary fluff. Be opinionated where the data supports an opinion.',
    ])
    return '\n'.join(lines)


# ──────────────────────────────────────────────────────────────────────
# Main loop
# ──────────────────────────────────────────────────────────────────────

def run_cohort_training():
    """Main entry point — cohort-based weekly training run."""
    analyzer = LLMAnalyzer()
    km = KnowledgeManager()

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    logger.info('=' * 60)
    logger.info('COHORT-BASED WEEKLY TRAINING')
    logger.info('=' * 60)

    # Migrate legacy April 6 insight if not already done (runs once)
    migrate_legacy_insight()

    # Step 0: load context
    env_context = get_hvac_weather_context(conn)
    logger.info('Environment context built')

    knowledge = {}
    if KNOWLEDGE_PATH.exists():
        knowledge = json.loads(KNOWLEDGE_PATH.read_text())
    all_local_llm_analyses = knowledge.get('llm_scan_analyses', [])

    # TEMP_MAY_REMOVE: pre/post restart comparison merge for Claude weekly training.
    # _run_post_action_log_comparison writes dual-model Qwen+Claude verdicts of
    # each restart's before-vs-after into knowledge['known_issues'] with miner_id
    # prefix 'compare:restart:*' or 'compare:pdu-cycle:*'. Those entries are the
    # richest per-restart analysis the system produces, but the weekly trainer
    # historically only read llm_scan_analyses, so Claude never saw them in the
    # Sunday synthesis pass. Merge them into the analyses stream here.
    #
    # On Mac mini ('May') arrival, remove this entire block. Claude will still get
    # the llm_scan_analyses, daily logs, and cohort/outlier/fleet synthesis — this
    # ONLY removes the comparison summary layer, nothing else about the Sunday
    # training changes.
    compare_entries = []
    for ki in knowledge.get('known_issues', []):
        mid = ki.get('miner_id', '')
        if not isinstance(mid, str) or not mid.startswith('compare:'):
            continue
        # miner_id shapes:
        #   compare:restart:53487                 (legacy, model unknown)
        #   compare:restart:qwen:53487            (dual-model qwen half)
        #   compare:restart:claude:53487          (dual-model claude half)
        #   compare:pdu-cycle:qwen:<id>
        #   compare:diagnostic:qwen:auradine_28   (one-off diagnostic runs)
        parts = mid.split(':')
        action_label = parts[1] if len(parts) > 1 else 'unknown'
        if len(parts) >= 4 and parts[2] in ('qwen', 'claude'):
            model_tag = parts[2]
            real_miner_id = ':'.join(parts[3:])
        else:
            model_tag = 'unspecified'
            real_miner_id = ':'.join(parts[2:]) if len(parts) > 2 else 'unknown'

        insight_text = ki.get('insight', '') or ''
        if not insight_text:
            continue

        # Prepend a clear tag so Claude knows what it is reading in the
        # fleet prompt. Format matches the existing llm_scan_analyses
        # convention used by build_fleet_prompt at lines ~563-567.
        tag = f'[PRE/POST COMPARE | {action_label} | miner {real_miner_id} | {model_tag}]'
        tagged_analysis = f'{tag}\n{insight_text}'

        # Convert known_issues schema {date, insight, miner_id} into the
        # llm_scan_analyses schema {timestamp, analysis, model, scan_id, source}
        # so the existing fleet prompt loop handles it with zero changes.
        date_str = ki.get('date', '')
        timestamp = f'{date_str}T00:00:00' if date_str else ''
        compare_entries.append({
            'timestamp': timestamp,
            'analysis': tagged_analysis,
            'model': model_tag,
            'scan_id': None,
            'source': 'restart_comparison',
        })

    if compare_entries:
        logger.info('Merging %d pre/post restart comparison entries into analyses stream', len(compare_entries))
        all_local_llm_analyses = list(all_local_llm_analyses) + compare_entries
    # END TEMP_MAY_REMOVE

    # Daily deep dive merge — PERMANENT, not TEMP_MAY_REMOVE.
    # ai/daily_deep_dive.py runs once a day and produces a long Qwen 32B
    # synthesis of the entire fleet (per-miner analyses + fleet synthesis pass).
    # Each day's entry is stored in knowledge['daily_deep_analyses']. We want
    # every Sunday Claude run to see the week's daily deep dives so Claude can
    # build on the local LLM's daily learning. Unlike the restart comparison
    # merge above, this one is permanent — the daily deep dive IS the local
    # LLM analysis stream at its richest, and that stream stays on forever
    # per operator rule (see CLAUDE.md 'May Migration Changes' section).
    daily_entries = []
    for dd in knowledge.get('daily_deep_analyses', []):
        date_str = dd.get('date', '')
        timestamp = dd.get('timestamp') or (f'{date_str}T00:00:00' if date_str else '')
        fleet_synth = dd.get('fleet_synthesis', '') or ''
        if fleet_synth:
            # The fleet synthesis is the big picture — always include it.
            tag = f'[DAILY DEEP DIVE FLEET SYNTHESIS | {date_str}]'
            daily_entries.append({
                'timestamp': timestamp,
                'analysis': f'{tag}\n{fleet_synth}',
                'model': 'qwen_daily_deep_dive',
                'scan_id': None,
                'source': 'daily_deep_dive_fleet',
            })
        # Include per-miner analyses too so Claude can see miner-level detail.
        # Each per-miner analysis gets its own entry tagged with the miner id.
        per_miner = dd.get('per_miner', {}) or {}
        if isinstance(per_miner, dict):
            for mid, analysis_text in per_miner.items():
                if not analysis_text:
                    continue
                tag = f'[DAILY DEEP DIVE PER-MINER | {date_str} | miner {mid}]'
                daily_entries.append({
                    'timestamp': timestamp,
                    'analysis': f'{tag}\n{analysis_text}',
                    'model': 'qwen_daily_deep_dive',
                    'scan_id': None,
                    'source': 'daily_deep_dive_per_miner',
                })

    if daily_entries:
        logger.info('Merging %d daily deep dive entries into analyses stream', len(daily_entries))
        all_local_llm_analyses = list(all_local_llm_analyses) + daily_entries

    operator_rules = knowledge.get('operator_rules', [])
    logger.info('Loaded %d local LLM analyses and %d operator rules from knowledge.json',
                len(all_local_llm_analyses), len(operator_rules))

    # Step 1: build cohorts
    cohorts = build_cohorts(conn)

    # Step 2: summarize each cohort (SQL only, no API calls)
    summaries = {}
    all_outliers = []
    for key, members in cohorts.items():
        summary = summarize_cohort(conn, key, members)
        summaries[key] = summary
        for o in summary.get('outliers', []):
            o['cohort_key'] = key
            all_outliers.append(o)
    logger.info('Cohort summaries built. Total outliers across all cohorts: %d', len(all_outliers))

    # Cap outliers to prevent runaway cost
    all_outliers.sort(key=lambda o: -len(o.get('reasons', [])))
    if len(all_outliers) > MAX_OUTLIERS_PER_RUN:
        logger.warning('Capping outliers from %d to %d', len(all_outliers), MAX_OUTLIERS_PER_RUN)
        all_outliers = all_outliers[:MAX_OUTLIERS_PER_RUN]

    # Step 3: cohort pass — one Claude call per cohort
    cohort_results = []
    logger.info('--- COHORT PASS: %d cohorts ---', len(cohorts))
    for i, (key, summary) in enumerate(summaries.items(), 1):
        logger.info('[%d/%d] Cohort %s (%d miners)',
                    i, len(summaries), '/'.join(str(k) for k in key), summary['member_count'])
        cohort_local_llm = _filter_local_llm_for_ips(
            all_local_llm_analyses,
            summary.get('all_member_ips', []),
            MAX_LOCAL_LLM_ANALYSES_PER_COHORT,
        )
        # Look up catalog context for this cohort's model
        cohort_catalog = ""
        try:
            # First element of cohort_key is the normalized model name
            model_name = str(key[0]) if key else ""
            if model_name and model_name != "unknown":
                cohort_catalog = get_miner_catalog_context(model_name)
        except Exception as e:
            logger.debug("Catalog lookup for cohort %s skipped: %s", key, e)
        prompt = build_cohort_prompt(summary, env_context, cohort_local_llm, cohort_catalog)
        logger.info('  Prompt size: %d chars', len(prompt))

        response = ''
        for attempt in range(3):
            response = analyzer.deep_analyze(prompt)
            if response and len(response) > 100:
                break
            wait = 30 * (attempt + 1)
            logger.warning('  Attempt %d failed or empty — waiting %ds', attempt + 1, wait)
            time.sleep(wait)

        if response:
            logger.info('  ✓ %d chars returned', len(response))
            km.add_llm_insight(response[:50000], miner_id=f"cohort:{'/'.join(str(k) for k in key)[:80]}")
            cohort_results.append({
                'cohort_key': key,
                'member_count': summary['member_count'],
                'claude_response': response,
            })
        else:
            logger.error('  All attempts failed for this cohort')

        time.sleep(INTER_REQUEST_PAUSE_SECONDS)

    # Step 4: outlier pass — one Claude call per flagged outlier
    outlier_results = []
    logger.info('--- OUTLIER PASS: %d outliers ---', len(all_outliers))
    for i, outlier in enumerate(all_outliers, 1):
        miner_id = outlier['miner_id']
        logger.info('[%d/%d] Outlier miner %s (%s)', i, len(all_outliers),
                    miner_id, outlier.get('ip', '?'))
        try:
            profile = get_miner_full_profile(conn, miner_id)
            if not profile['scan'] or not profile['scan'].get('scan_count'):
                logger.info('  Skipping — no scan data')
                continue
        except Exception as e:
            logger.warning('  Profile fetch failed: %s', e)
            continue

        outlier_local_llm = _filter_local_llm_for_ips(
            all_local_llm_analyses,
            [outlier.get('ip', '')],
            MAX_LOCAL_LLM_ANALYSES_PER_OUTLIER,
        )
        prompt = build_outlier_prompt(miner_id, profile, outlier['cohort_key'],
                                       env_context, outlier_local_llm)
        logger.info('  Prompt size: %d chars', len(prompt))

        response = ''
        for attempt in range(3):
            response = analyzer.deep_analyze(prompt)
            if response and len(response) > 100:
                break
            wait = 30 * (attempt + 1)
            logger.warning('  Attempt %d failed or empty — waiting %ds', attempt + 1, wait)
            time.sleep(wait)

        if response:
            logger.info('  ✓ %d chars returned', len(response))
            km.add_llm_insight(response[:50000], miner_id=miner_id)
            outlier_results.append({
                'miner_id': miner_id,
                'ip': outlier.get('ip'),
                'claude_response': response,
            })

        time.sleep(INTER_REQUEST_PAUSE_SECONDS)

    # Step 5: fleet-wide synthesis pass — ONE Claude call with everything
    logger.info('--- FLEET PASS ---')
    cross_miner_text = ''
    try:
        cross_miner_text = get_cross_miner_correlations(conn)
    except Exception as e:
        logger.warning('cross_miner_correlations failed: %s', e)

    fleet_prompt = build_fleet_prompt(
        cohort_results, outlier_results, all_local_llm_analyses,
        operator_rules, cross_miner_text,
    )
    logger.info('Fleet prompt size: %d chars', len(fleet_prompt))

    fleet_response = ''
    for attempt in range(3):
        fleet_response = analyzer.deep_analyze(fleet_prompt)
        if fleet_response and len(fleet_response) > 100:
            break
        wait = 60 * (attempt + 1)
        logger.warning('Fleet attempt %d failed — waiting %ds', attempt + 1, wait)
        time.sleep(wait)

    # CRITICAL ORDERING: km.save() writes KnowledgeManager's in-memory state to disk,
    # which does NOT include the cross_miner_analysis direct-write below. If km.save()
    # runs AFTER the direct write, it clobbers the fleet synthesis. Fixed 2026-04-10:
    # km.save() now fires FIRST, then the direct write lands last and survives.
    # See REPAIR_LOG.md "Weekly training fleet synthesis silently clobbered" (2026-04-10).
    km.save()
    conn.close()

    if fleet_response:
        logger.info('Fleet synthesis complete: %d chars', len(fleet_response))
        km.add_llm_insight(fleet_response[:50000], miner_id='fleet')
        # Store in cross_miner_analysis for the local LLM to read next week.
        # This MUST be the last write to knowledge.json in this function.
        knowledge = json.loads(KNOWLEDGE_PATH.read_text())
        if not isinstance(knowledge.get('cross_miner_analysis'), list):
            knowledge['cross_miner_analysis'] = []
        knowledge['cross_miner_analysis'].insert(0, {
            'timestamp': datetime.now().isoformat(),
            'analysis': fleet_response,
            'cohort_count': len(cohort_results),
            'outlier_count': len(outlier_results),
            'source': 'claude_weekly_cohort',
        })
        knowledge['cross_miner_analysis'] = knowledge['cross_miner_analysis'][:10]  # keep last 10 weeks
        tmp_path = str(KNOWLEDGE_PATH) + '.tmp'
        with open(tmp_path, 'w') as f:
            json.dump(knowledge, f, indent=2)
        os.replace(tmp_path, str(KNOWLEDGE_PATH))

        # Extract and store refined insights from Claude's response
        logger.info('Processing refined insights from fleet response...')
        insight_result = process_refined_insights(fleet_response, site_id='R&D Home')
        logger.info('Refined insights: %d added, %d updated, %d errors',
                    insight_result['added'], insight_result['updated'], insight_result['errors'])

    total_calls = len(cohort_results) + len(outlier_results) + (1 if fleet_response else 0)
    logger.info('=' * 60)
    logger.info('TRAINING COMPLETE')
    logger.info('  Cohorts:  %d', len(cohort_results))
    logger.info('  Outliers: %d', len(outlier_results))
    logger.info('  Fleet:    %s', 'yes' if fleet_response else 'no')
    logger.info('  Total Claude API calls: %d', total_calls)
    logger.info('=' * 60)


if __name__ == '__main__':
    run_cohort_training()
