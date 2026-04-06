#!/usr/bin/env python3
"""Run just the cross-miner correlation step — skips per-miner analysis."""
import sys, sqlite3
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "ai"))
sys.path.insert(0, str(_ROOT / "core"))

from train_comprehensive import get_cross_miner_correlations, DB_PATH
from llm_analyzer import LLMAnalyzer
from knowledge_manager import KnowledgeManager

conn = sqlite3.connect(DB_PATH, timeout=30)
conn.row_factory = sqlite3.Row
print("Running cross-miner correlation...")
prompt = get_cross_miner_correlations(conn)
print(f"Correlation prompt built: {len(prompt)} chars")

analyzer = LLMAnalyzer()
print("Sending to Claude for analysis...")
response = analyzer.deep_analyze(prompt)
print(f"Claude response: {len(response)} chars")

km = KnowledgeManager()
if response:
    km.knowledge.setdefault("cross_miner_analysis", [])
    km.knowledge["cross_miner_analysis"] = [{
        "analyzed_at": "2026-04-06",
        "summary": response[:2000]
    }]
    km.save()
    print("Knowledge updated with cross-miner analysis")
else:
    print("Empty response - skipped")

conn.close()
d = km.knowledge
print(f"\nFinal knowledge: {len(d.get('known_issues',[]))} issues, "
      f"{len(d.get('patterns',[]))} patterns, "
      f"{len(d.get('miner_profiles',{}))} profiles")
print("DONE")
