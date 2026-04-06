"""
combine_knowledge.py
Mining Guardian — Federated Knowledge Merger

Takes multiple knowledge.json files from different Mining Guardian deployments,
feeds them to the LLM for intelligent synthesis, and produces a master_knowledge.json
that contains combined insights, cross-site patterns, and weighted confidence scores.

This is NOT a simple merge — it's a LEARNING EVENT. The LLM reads all knowledge bases
and produces NEW insights that no single site had individually.

Usage:
  python3 combine_knowledge.py site_a.json site_b.json [site_c.json ...]
  python3 combine_knowledge.py /path/to/exports/*.json

Output:
  master_knowledge.json — combined knowledge for all sites
"""

import os
import json
import sys
import logging
import requests
from datetime import datetime, timezone
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("combine_knowledge")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://100.110.87.1:11434/api/generate")
MODEL      = os.getenv("OLLAMA_MODEL", "qwen2.5:32b-instruct-q4_K_M")
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "master_knowledge.json")

# Use Claude API if available, fall back to Ollama
CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


def load_knowledge_files(paths: List[str]) -> List[Dict]:
    """Load and validate multiple knowledge.json files."""
    sites = []
    for path in paths:
        try:
            with open(path) as f:
                data = json.load(f)
            site_name = path.replace("/", "_").replace(".json", "")
            sites.append({"name": site_name, "data": data, "path": path})
            miners = len(data.get("miner_profiles", {}))
            insights = len(data.get("known_issues", []))
            patterns = len(data.get("patterns", []))
            logger.info("Loaded %s: %d miners, %d insights, %d patterns",
                        path, miners, insights, patterns)
        except Exception as e:
            logger.error("Failed to load %s: %s", path, e)
    return sites


def build_merge_prompt(sites: List[Dict]) -> str:
    """Build a prompt that asks the LLM to synthesize knowledge from multiple sites."""
    parts = [
        "You are Mining Guardian AI performing a KNOWLEDGE MERGE across multiple mining sites.",
        "Each site has been independently monitoring miners and learning patterns.",
        "Your job: synthesize ALL knowledge into unified insights that make every site smarter.",
        "",
        "INSTRUCTIONS:",
        "1. Identify patterns that appear at MULTIPLE sites — these are high-confidence universal patterns.",
        "2. Flag patterns unique to one site — these may be site-specific or early warnings for other sites.",
        "3. Combine miner model insights — if Site A learned about S19JPro issues and Site B learned about AH3880, both benefit.",
        "4. Weight confidence by how many sites confirm the same pattern.",
        "5. Generate NEW insights by cross-referencing: e.g., if Site A sees chain detachment in heat and Site B in cold, it's likely hardware not environmental.",
        "",
        f"DATA FROM {len(sites)} SITES:",
        ""
    ]

    for site in sites:
        d = site["data"]
        parts.append(f"=== SITE: {site['name']} ===")
        parts.append(f"Miners tracked: {len(d.get('miner_profiles', {}))}")

        # Patterns
        patterns = d.get("patterns", [])
        if patterns:
            parts.append(f"Patterns ({len(patterns)}):")
            for p in patterns:
                parts.append(f"  - {str(p)[:200]}")

        # Recent insights
        insights = d.get("known_issues", [])[-10:]
        if insights:
            parts.append(f"Recent insights ({len(insights)}):")
            for i in insights:
                parts.append(f"  [{i.get('date','')}] {i.get('insight','')[:200]}")

        # Fleet summary
        fs = d.get("fleet_summary", {})
        if fs:
            parts.append(f"Fleet: {fs.get('total_miners','?')} miners")
            if fs.get("models"):
                parts.append(f"Models: {', '.join(fs['models'])}")
        parts.append("")

    parts.append("RESPOND IN JSON FORMAT ONLY (no markdown, no backticks):")
    parts.append('{')
    parts.append('  "universal_patterns": ["pattern confirmed across multiple sites"],')
    parts.append('  "site_specific_patterns": [{"site": "name", "pattern": "...", "may_apply_to": "all/specific"}],')
    parts.append('  "new_cross_site_insights": ["NEW insight derived from combining data across sites"],')
    parts.append('  "model_insights": {"S19JPro": ["insight about this model"], "AH3880": ["insight"]},')
    parts.append('  "confidence_rankings": [{"pattern": "...", "confidence": "high/medium/low", "sites_confirming": 2}]')
    parts.append('}')

    return "\n".join(parts)


def query_llm(prompt: str) -> str:
    """Send the merge prompt to Claude API (preferred) or Ollama (fallback)."""
    if CLAUDE_API_KEY:
        logger.info("Using Claude API for knowledge merge (%d chars)...", len(prompt))
        try:
            resp = requests.post("https://api.anthropic.com/v1/messages", json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}]
            }, headers={
                "x-api-key": CLAUDE_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            text = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")
            if not text:
                logger.warning("Claude returned empty content — falling back to Ollama")
                raise ValueError("empty response")
            logger.info("Claude merge complete (%d chars)", len(text))
            return text
        except Exception as e:
            logger.error("Claude API failed: %s — falling back to Ollama", e)

    logger.info("Using Ollama for knowledge merge (%d chars)...", len(prompt))
    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False
        }, timeout=600)
        resp.raise_for_status()
        result = resp.json().get("response", "")
        if not result:
            logger.error("Ollama returned empty response")
        return result
    except requests.exceptions.HTTPError as e:
        logger.error("Ollama HTTP error %s: %s", e.response.status_code, e.response.text[:200])
        return ""
    except Exception as e:
        logger.error("LLM query failed: %s", e)
        return ""


def build_master_knowledge(sites: List[Dict], llm_synthesis: str) -> Dict:
    """Combine raw knowledge from all sites with LLM synthesis into master."""
    master = {
        "version": 1,
        "last_merged": datetime.now(timezone.utc).isoformat(),
        "sites_merged": [s["name"] for s in sites],
        "site_count": len(sites),
        "fleet_summary": {},
        "miner_profiles": {},
        "known_issues": [],
        "patterns": [],
        "llm_synthesis": {},
    }

    # Merge miner profiles — keep the one with the most flags (most data)
    for site in sites:
        for mid, profile in site["data"].get("miner_profiles", {}).items():
            key = f"{site['name']}_{mid}"
            existing = master["miner_profiles"].get(key)
            if not existing or profile.get("total_flags", 0) > existing.get("total_flags", 0):
                master["miner_profiles"][key] = profile

    # Merge patterns — deduplicate by similarity
    all_patterns = set()
    for site in sites:
        for p in site["data"].get("patterns", []):
            # Coerce to string — patterns may be dicts/lists in some knowledge files
            all_patterns.add(str(p) if not isinstance(p, str) else p)
    master["patterns"] = list(all_patterns)

    # Merge insights — keep all, sorted by date
    all_insights = []
    for site in sites:
        for i in site["data"].get("known_issues", []):
            # Copy before mutating — don't modify caller's data
            insight = dict(i)
            insight["source_site"] = site["name"]
            all_insights.append(insight)
    all_insights.sort(key=lambda x: x.get("date", ""), reverse=True)
    master["known_issues"] = all_insights[:100]  # keep top 100

    # Add LLM synthesis — skip entirely if LLM returned nothing
    if not llm_synthesis:
        logger.warning("LLM synthesis was empty — skipping synthesis block")
        return master

    try:
        synthesis = json.loads(llm_synthesis)
        master["llm_synthesis"] = synthesis

        # Add universal patterns from LLM to the main patterns list
        for p in synthesis.get("universal_patterns", []):
            if p not in master["patterns"]:
                master["patterns"].append(p)

        # Add cross-site insights as known issues
        for insight in synthesis.get("new_cross_site_insights", []):
            master["known_issues"].insert(0, {
                "date": datetime.now(timezone.utc).isoformat()[:10],
                "miner_id": "cross-site",
                "insight": insight,
                "source_site": "llm_merge"
            })
    except json.JSONDecodeError:
        logger.warning("LLM response was not valid JSON — saving raw text")
        master["llm_synthesis"] = {"raw_response": llm_synthesis[:2000]}

    # Fleet summary
    total_miners = sum(len(s["data"].get("miner_profiles", {})) for s in sites)
    all_models = set()
    for s in sites:
        fs = s["data"].get("fleet_summary", {})
        if fs.get("models"):
            all_models.update(fs["models"])
    master["fleet_summary"] = {
        "total_miners_across_sites": total_miners,
        "models": list(all_models),
        "sites": len(sites)
    }

    return master


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 combine_knowledge.py site_a.json site_b.json [site_c.json ...]")
        print("  Merges multiple knowledge.json files with LLM-powered synthesis.")
        print("  Output: master_knowledge.json")
        sys.exit(1)

    paths = sys.argv[1:]
    logger.info("=" * 60)
    logger.info("FEDERATED KNOWLEDGE MERGE — %d sites", len(paths))
    logger.info("=" * 60)

    # Load all knowledge files
    sites = load_knowledge_files(paths)
    if len(sites) < 2:
        logger.error("Need at least 2 knowledge files to merge")
        sys.exit(1)

    # Build merge prompt and send to LLM
    prompt = build_merge_prompt(sites)
    llm_response = query_llm(prompt)
    if llm_response:
        logger.info("LLM synthesis received (%d chars)", len(llm_response))
    else:
        logger.warning("LLM synthesis failed — merging without AI insights")

    # Build master knowledge
    master = build_master_knowledge(sites, llm_response)

    # Save
    tmp = OUTPUT_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(master, f, indent=2)
    os.replace(tmp, OUTPUT_PATH)

    logger.info("=" * 60)
    logger.info("MERGE COMPLETE — master_knowledge.json")
    logger.info("  Sites merged: %d", master["site_count"])
    logger.info("  Total miners: %d", len(master["miner_profiles"]))
    logger.info("  Patterns: %d", len(master["patterns"]))
    logger.info("  Insights: %d", len(master["known_issues"]))
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
