#!/usr/bin/env python3
"""
insight_manager.py — Mining Guardian Refined Insights System

Manages the accumulating "Fleet Intelligence" insights that Claude generates.
Unlike weekly summaries that get replaced, refined insights persist and
get updated as new data refines the numbers.

DESIGN PRINCIPLES:
1. Insights are keyed by topic+cooling_type (e.g., "0110_0020_boards_hydro")
2. Small changes (<5%) update in place with history logged
3. Significant changes (>5%) or conclusion changes add new insight
4. Claude generates both narrative summary AND JSON insights block
5. JSON block is parsed and merged into knowledge.json["refined_insights"]

See docs/REFINED_INSIGHTS_DESIGN.md for full specification.
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('insight_manager')

_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_PATH = _ROOT / 'knowledge.json'

# Confidence thresholds (can be moved to config.json later)
CONFIDENCE_THRESHOLDS = {
    'HIGH': {'min_data_points': 100, 'min_days': 7, 'min_separation': 0.20},
    'MEDIUM': {'min_data_points': 25, 'min_days': 3, 'min_separation': 0.10},
    'LOW': {'min_data_points': 0, 'min_days': 0, 'min_separation': 0.0},
}

# Update threshold — changes above this % trigger new insight vs in-place update
SIGNIFICANT_CHANGE_THRESHOLD = 0.05  # 5%


def load_knowledge() -> Dict:
    """Load knowledge.json, initializing refined_insights if missing."""
    if not KNOWLEDGE_PATH.exists():
        return {'refined_insights': {}}
    try:
        with open(KNOWLEDGE_PATH) as f:
            k = json.load(f)
        if 'refined_insights' not in k:
            k['refined_insights'] = {}
        return k
    except Exception as e:
        logger.error('Failed to load knowledge.json: %s', e)
        return {'refined_insights': {}}


def save_knowledge(knowledge: Dict) -> bool:
    """Atomically save knowledge.json with file locking."""
    try:
        from core.file_lock import locked_knowledge_update
        with locked_knowledge_update(str(KNOWLEDGE_PATH)) as on_disk:
            on_disk.update(knowledge)
        return True
    except Exception as e:
        logger.error('Failed to save knowledge.json: %s', e)
        return False


def extract_json_from_response(response: str) -> Optional[Dict]:
    """Extract JSON block from Claude's response.
    
    Claude is instructed to output a ```json block containing refined_insights.
    This function finds and parses that block.
    """
    # Look for ```json ... ``` block
    json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError as e:
            logger.warning('JSON parse error in ```json block: %s', e)
    
    # Fallback: look for { "refined_insights": ... } pattern
    brace_match = re.search(r'\{\s*"refined_insights"\s*:\s*\{.*?\}\s*\}', response, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError as e:
            logger.warning('JSON parse error in brace match: %s', e)
    
    logger.warning('No valid JSON block found in Claude response')
    return None


def generate_insight_key(insight: Dict) -> str:
    """Generate a unique key for an insight based on topic + cooling_type.
    
    Key format: {topic}_{cooling_type}
    Example: "0110_0020_boards_hydro"
    """
    topic = insight.get('topic', 'unknown').lower().replace(' ', '_').replace('/', '_')
    cooling = insight.get('cooling_type', 'unknown').lower()
    return f"{topic}_{cooling}"


def should_update_in_place(existing: Dict, new: Dict) -> bool:
    """Determine if an insight should be updated in place vs added as new.
    
    Returns True for in-place update when:
    - Same conclusion (action field)
    - Change in numeric values < SIGNIFICANT_CHANGE_THRESHOLD
    
    Returns False (add as new) when:
    - Conclusion changed (e.g., REJECT -> WATCH)
    - Numeric change >= SIGNIFICANT_CHANGE_THRESHOLD
    """
    # Different conclusions = new insight
    if existing.get('action') != new.get('action'):
        logger.info('Conclusion changed: %s -> %s', existing.get('action'), new.get('action'))
        return False
    
    # Try to compare numeric values in the insight text
    # This is heuristic — look for percentage patterns
    old_pcts = re.findall(r'(\d+\.?\d*)%', existing.get('insight', ''))
    new_pcts = re.findall(r'(\d+\.?\d*)%', new.get('insight', ''))
    
    if old_pcts and new_pcts:
        try:
            old_val = float(old_pcts[0])
            new_val = float(new_pcts[0])
            if old_val > 0:
                change = abs(new_val - old_val) / old_val
                if change >= SIGNIFICANT_CHANGE_THRESHOLD:
                    logger.info('Significant change detected: %.1f%% -> %.1f%% (%.1f%% change)',
                               old_val, new_val, change * 100)
                    return False
        except (ValueError, ZeroDivisionError):
            pass
    
    return True


def merge_insight(existing: Dict, new: Dict) -> Dict:
    """Merge a new insight into an existing one (in-place update).
    
    - Updates numeric fields
    - Logs old values to update_history
    - Preserves first_seen
    - Updates last_updated
    """
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Build history entry for the old state
    history_entry = {
        'date': existing.get('last_updated', today),
        'insight': existing.get('insight'),
        'data_points': existing.get('data_points'),
        'confidence': existing.get('confidence'),
    }
    
    # Update fields from new insight
    merged = existing.copy()
    merged['insight'] = new.get('insight', existing.get('insight'))
    merged['confidence'] = new.get('confidence', existing.get('confidence'))
    merged['data_source'] = new.get('data_source', existing.get('data_source'))
    merged['data_points'] = new.get('data_points', existing.get('data_points'))
    merged['miners_affected'] = new.get('miners_affected', existing.get('miners_affected'))
    merged['last_updated'] = today
    
    # Append to history
    if 'update_history' not in merged:
        merged['update_history'] = []
    merged['update_history'].append(history_entry)
    
    # Keep history manageable (last 10 updates)
    merged['update_history'] = merged['update_history'][-10:]
    
    return merged


def process_refined_insights(claude_response: str, site_id: str = 'R&D Home') -> Dict:
    """Main entry point: extract and merge refined insights from Claude response.
    
    Args:
        claude_response: Full text of Claude's fleet synthesis response
        site_id: Identifier for this mining site
        
    Returns:
        Dict with 'added', 'updated', 'errors' counts
    """
    result = {'added': 0, 'updated': 0, 'errors': 0, 'insights': []}
    
    # Extract JSON from response
    extracted = extract_json_from_response(claude_response)
    if not extracted:
        logger.warning('No refined insights JSON found in response')
        return result
    
    new_insights = extracted.get('refined_insights', {})
    if not new_insights:
        logger.info('Empty refined_insights dict in response')
        return result
    
    # Load current knowledge
    knowledge = load_knowledge()
    existing = knowledge.get('refined_insights', {})
    today = datetime.now().strftime('%Y-%m-%d')
    
    for key, insight in new_insights.items():
        try:
            # Validate required fields
            if not insight.get('category') or not insight.get('insight'):
                logger.warning('Skipping insight %s: missing required fields', key)
                result['errors'] += 1
                continue
            
            # Generate canonical key
            canonical_key = generate_insight_key(insight)
            
            # Add metadata
            insight['site_id'] = site_id
            insight['last_updated'] = today
            
            if canonical_key in existing:
                # Existing insight — check if update in place or add new
                if should_update_in_place(existing[canonical_key], insight):
                    existing[canonical_key] = merge_insight(existing[canonical_key], insight)
                    logger.info('Updated in place: %s', canonical_key)
                    result['updated'] += 1
                else:
                    # Significant change — add with timestamp suffix
                    new_key = f"{canonical_key}_{today.replace('-', '')}"
                    insight['first_seen'] = today
                    insight['update_history'] = []
                    existing[new_key] = insight
                    logger.info('Added new (significant change): %s', new_key)
                    result['added'] += 1
            else:
                # New insight
                insight['first_seen'] = today
                insight['update_history'] = []
                existing[canonical_key] = insight
                logger.info('Added new: %s', canonical_key)
                result['added'] += 1
            
            result['insights'].append(canonical_key)
            
        except Exception as e:
            logger.error('Error processing insight %s: %s', key, e)
            result['errors'] += 1
    
    # Save updated knowledge
    knowledge['refined_insights'] = existing
    if save_knowledge(knowledge):
        logger.info('Saved %d refined insights to knowledge.json', len(existing))
    
    return result


def get_all_insights() -> Dict:
    """Get all refined insights for dashboard display."""
    knowledge = load_knowledge()
    return knowledge.get('refined_insights', {})


def get_insights_by_category(category: str) -> List[Dict]:
    """Get insights filtered by category."""
    all_insights = get_all_insights()
    return [
        {'key': k, **v}
        for k, v in all_insights.items()
        if v.get('category', '').lower() == category.lower()
    ]


def migrate_legacy_insight():
    """Migrate the gold-standard April 6 insight to new format.
    
    Run this once to seed the refined_insights dict with the legacy insight
    that Bobby identified as the gold standard example.
    """
    knowledge = load_knowledge()
    existing = knowledge.get('refined_insights', {})
    
    # Check if already migrated
    if '0110_0020_boards_immersion' in existing or '0110_0020_boards_hydro' in existing:
        logger.info('Legacy insight already migrated')
        return False
    
    # The gold standard insight from April 6
    legacy_insight = {
        'category': 'PCB/BOM Failure',
        'topic': '0110_0020_boards',
        'insight': 'PCB=0110/BOM=0020 boards averaging 13.6% hashrate while PCB=0130/BOM=0010 hit 73.5%. Reject all 0110/0020 combinations.',
        'action': 'REJECT',
        'confidence': 'HIGH',
        'cooling_type': 'IMMERSION',
        'miner_type': 'Antminer S19J Pro',
        'data_source': '847 chip readings over 14 days',
        'miners_affected': ['53482', '53493'],
        'data_points': 847,
        'site_id': 'R&D Home',
        'first_seen': '2026-04-06',
        'last_updated': '2026-04-06',
        'update_history': [],
    }
    
    # Migration key changed from 0110_0020_boards_hydro to 0110_0020_boards_immersion
    # to reflect the corrected cooling type. Old key kept here so the migration check
    # below still detects already-migrated knowledge bases.
    existing['0110_0020_boards_immersion'] = legacy_insight
    knowledge['refined_insights'] = existing
    
    if save_knowledge(knowledge):
        logger.info('Migrated legacy April 6 insight to refined_insights')
        return True
    return False


# ──────────────────────────────────────────────────────────────────────
# Prompt section for Claude
# ──────────────────────────────────────────────────────────────────────

REFINED_INSIGHTS_PROMPT_SECTION = '''
=== REFINED INSIGHTS (CRITICAL — FLAGSHIP FEATURE) ===

In addition to your narrative analysis, you MUST output a JSON block containing
permanent, data-backed insights that will accumulate on the Fleet Intelligence
dashboard. These are NOT weekly summaries — they are persistent findings that
get updated as data refines the numbers.

GOLD STANDARD EXAMPLE (from April 6):
**PCB/BOM Failure:** PCB=0110/BOM=0020 boards averaging 13.6% hashrate while
PCB=0130/BOM=0010 hit 73.5%. Reject all 0110/0020 combinations.

YOUR OUTPUT FORMAT:
After your narrative analysis, include a ```json block like this:

```json
{
  "refined_insights": {
    "descriptive_key_here": {
      "category": "PCB/BOM Failure",
      "topic": "0110_0020_boards",
      "insight": "One crisp sentence with specific numbers. Example: PCB=0110/BOM=0020 boards averaging 13.6% hashrate vs 73.5% for 0130/0010.",
      "action": "REJECT",
      "confidence": "HIGH",
      "cooling_type": "IMMERSION",
      "miner_type": "Antminer S19J Pro",
      "data_source": "847 chip readings over 14 days",
      "miners_affected": ["53482", "53493"],
      "data_points": 847
    }
  }
}

COOLING TYPE RULES — MUST FOLLOW:
- Antminer S19J Pro at this facility = IMMERSION (operator converted from air to immersion)
- Antminer S21Imm = IMMERSION (B100 Fog Hashing tank)
- Antminer S21e XP Hyd = HYDRO (water-cooled by design)
- Auradine AH3880 = HYDRO (water-cooled by design)
- All container miners (non-S19) = IMMERSION (same container)
- NO miner at this facility is air-cooled in operation
- Never mix cooling types in a single insight. If a pattern spans multiple cooling
  types, generate separate insights, one per cooling_type.

MINERS_AFFECTED RULES — MUST FOLLOW:
- Always a JSON array of MINER ID STRINGS, e.g. ["53476", "53477", "53480"]
- Never a label, category name, or descriptive string like "cohort_bin_3_miners"
- If you cannot enumerate the specific miner IDs, output an empty array []
```

CATEGORIES TO CONSIDER:
- Hardware: Chip Quality, PCB/BOM Failure, Serial Batch Pattern, PSU Reliability,
  Hashboard Reliability, Control Board Reliability, Firmware Insight
- Environmental: HVAC Correlation, Weather Correlation, Fluid Flow Correlation,
  Cooling Type Comparison, Time Pattern
- Operational: Restart Effectiveness, PDU Cycle Effectiveness, Network Performance
- Fleet-Level: Parts Donor, Golden Miner, AMS Alert Noise
- Procurement: Procurement Action (stop buying / buy more)

CONFIDENCE LEVELS:
- HIGH: 100+ data points, 7+ days, >20% separation between groups
- MEDIUM: 25-99 data points, 3-7 days, 10-20% separation
- LOW: <25 data points, <3 days, <10% separation

ACTION VALUES: REJECT, WATCH, KEEP, REPLACE, INVESTIGATE, TUNE, NONE

RULES:
1. Only output insights backed by data in this prompt
2. Be SPECIFIC — include actual percentages, miner IDs, component identifiers
3. If no clear insight emerges from the data, output an empty refined_insights: {}
4. Quality over quantity — 1-3 strong insights beats 10 weak ones
5. These insights train the on-site LLM and inform procurement decisions
'''


if __name__ == '__main__':
    # Run migration when executed directly
    migrate_legacy_insight()
    print('Current insights:', json.dumps(get_all_insights(), indent=2))
