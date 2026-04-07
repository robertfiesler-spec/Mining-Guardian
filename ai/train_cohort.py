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
from train_comprehensive import (
    get_miner_full_profile,
    build_miner_prompt,
    get_hvac_weather_context,
    get_cross_miner_correlations,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger('train_cohort')

DB_PATH = str(_ROOT / 'guardian.db')
KNOWLEDGE_PATH = _ROOT / 'knowledge.json'

# Tunables — keep these conservative for Tier 1 safety
MAX_LOCAL_LLM_ANALYSES_PER_COHORT = 8   # how many recent local LLM analyses to include in each cohort prompt
MAX_LOCAL_LLM_ANALYSES_PER_OUTLIER = 5  # how many for an outlier prompt
OUTLIER_HASHRATE_SIGMA = 2.0            # miners >2σ below cohort mean HR
OUTLIER_TEMP_SIGMA = 2.0                # miners >2σ above cohort mean temp
MAX_OUTLIERS_PER_RUN = 30               # hard cap to prevent runaway
INTER_REQUEST_PAUSE_SECONDS = 3         # gap between Claude calls (gentle pacing)


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
                         local_llm_analyses: List[Dict]) -> str:
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

    lines.extend([
        '',
        '=== ENVIRONMENT CONTEXT ===',
        env_context[:1500],
        '',
        '=== YOUR TASK ===',
        f'Analyze this cohort of {summary["member_count"]} miners as a GROUP, not individually.',
        '',
        '1. BEHAVIORAL BASELINE (2-3 sentences): What is normal for this hardware cohort?',
        '   Use the aggregates as ground truth.',
        '',
        '2. COMMON FAILURE MODES (bullet list): What problems repeat across this cohort?',
        '   Distinguish hardware-pattern issues from environmental triggers.',
        '',
        '3. RESTART EFFECTIVENESS (1-2 sentences): Are restarts actually fixing problems',
        '   for this cohort, or masking them?',
        '',
        '4. RECOMMENDED ACTION BIAS (1-2 sentences): For this cohort specifically, what',
        '   action thresholds make sense? Should they be more or less aggressive than fleet default?',
        '',
        '5. OUTLIERS NEEDING INDIVIDUAL ATTENTION: Which of the listed outliers (if any)',
        '   need a deeper individual analysis?',
        '',
        'Keep your response under 600 words. Be specific. No filler.',
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
        '=== YOUR TASK ===',
        'This miner is an OUTLIER within its hardware cohort. Something specific is wrong with THIS unit.',
        '',
        '1. ROOT CAUSE HYPOTHESIS (2-3 sentences): What is most likely wrong?',
        '2. EVIDENCE FROM DATA (bullet list): cite specific numbers from the profile',
        '3. RECOMMENDED ACTION (1 sentence): one concrete next step',
        '',
        'Under 400 words. Be specific.',
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
        '=== YOUR TASK ===',
        'You have just read the full weekly state of the fleet — by cohort, by outlier,',
        'by local LLM observation, and by operator rule.',
        '',
        '1. TOP 3 SYSTEMIC ISSUES (numbered list): What patterns repeat across cohorts?',
        '   What hardware quality issues are emerging?',
        '',
        '2. WHICH COHORTS NEED PROCUREMENT REVIEW (1-2 sentences each):',
        '   Are any cohorts showing systemic underperformance that suggests buying alternatives?',
        '',
        '3. LOCAL LLM VALIDATION (bullet list):',
        '   Was the local LLM\'s diagnosis correct? What did it miss that you can see fleet-wide?',
        '',
        '4. OPERATOR RULE REFINEMENT (bullet list):',
        '   Should any of the captured operator rules be generalized, narrowed, or merged?',
        '',
        '5. NEXT-WEEK FOCUS AREAS (bullet list):',
        '   What should the system pay closest attention to in the next 7 days?',
        '',
        'Be specific. Reference cohorts and miners by name. Under 1500 words.',
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

    # Step 0: load context
    env_context = get_hvac_weather_context(conn)
    logger.info('Environment context built')

    knowledge = {}
    if KNOWLEDGE_PATH.exists():
        knowledge = json.loads(KNOWLEDGE_PATH.read_text())
    all_local_llm_analyses = knowledge.get('llm_scan_analyses', [])
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
        prompt = build_cohort_prompt(summary, env_context, cohort_local_llm)
        logger.info('  Prompt size: %d chars', len(prompt))

        response = ''
        for attempt in range(3):
            response = analyzer.deep_analyze(prompt)
            if response and 'error' not in response.lower():
                break
            wait = 30 * (attempt + 1)
            logger.warning('  Attempt %d failed or empty — waiting %ds', attempt + 1, wait)
            time.sleep(wait)

        if response:
            logger.info('  ✓ %d chars returned', len(response))
            km.add_llm_insight(response[:600], miner_id=f"cohort:{'/'.join(str(k) for k in key)[:80]}")
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
            if response and 'error' not in response.lower():
                break
            wait = 30 * (attempt + 1)
            logger.warning('  Attempt %d failed or empty — waiting %ds', attempt + 1, wait)
            time.sleep(wait)

        if response:
            logger.info('  ✓ %d chars returned', len(response))
            km.add_llm_insight(response[:500], miner_id=miner_id)
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
        if fleet_response and 'error' not in fleet_response.lower():
            break
        wait = 60 * (attempt + 1)
        logger.warning('Fleet attempt %d failed — waiting %ds', attempt + 1, wait)
        time.sleep(wait)

    if fleet_response:
        logger.info('Fleet synthesis complete: %d chars', len(fleet_response))
        km.add_llm_insight(fleet_response[:800], miner_id='fleet')
        # Also store in cross_miner_analysis for the local LLM to read next week
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

    km.save()
    conn.close()

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
