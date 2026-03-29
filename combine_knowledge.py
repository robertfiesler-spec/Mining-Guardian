#!/usr/bin/env python3
"""
combine_knowledge.py
Mining Guardian — Central Knowledge Combiner

Run this at your office after collecting knowledge.json files
from all customer Mac Minis (via USB or manual transfer).

Merges all customer knowledge files into a single
master_knowledge.json weighted by confidence (observation count).

Usage:
    # Combine all knowledge files in a folder
    python combine_knowledge.py --input /path/to/collected/

    # Combine specific files
    python combine_knowledge.py customer1.json customer2.json customer3.json

    # Specify output path
    python combine_knowledge.py --input ./collected/ --output master_knowledge.json
"""

import json
import os
import argparse
from datetime import datetime
from collections import defaultdict
from pathlib import Path


def load_knowledge_files(paths: list) -> list:
    """Load and validate knowledge JSON files."""
    knowledge_list = []
    for path in paths:
        try:
            with open(path) as f:
                data = json.load(f)
            if "model_statistics" not in data:
                print(f"⚠️  Skipping {path} — not a valid knowledge file")
                continue
            data["_source_file"] = str(path)
            knowledge_list.append(data)
            print(f"✅ Loaded {path} (exported {data.get('exported_at', 'unknown')})")
        except Exception as e:
            print(f"❌ Failed to load {path}: {e}")
    return knowledge_list


def combine_model_statistics(all_knowledge: list) -> list:
    """Merge model statistics across all customers, weighted by observation count."""
    model_data = defaultdict(lambda: {
        "total_readings": 0,
        "hashrate_sum": 0.0,
        "hashrate_count": 0,
        "temp_sum": 0.0,
        "temp_count": 0,
        "max_temp_seen": 0.0,
        "restart_count": 0,
        "pdu_cycle_count": 0,
        "physical_cycle_count": 0,
        "offline_count": 0,
    })

    for k in all_knowledge:
        for stat in k.get("model_statistics", []):
            model = stat.get("model")
            if not model:
                continue
            d = model_data[model]
            d["total_readings"]      += stat.get("total_readings", 0) or 0
            d["restart_count"]       += stat.get("restart_count", 0) or 0
            d["pdu_cycle_count"]     += stat.get("pdu_cycle_count", 0) or 0
            d["physical_cycle_count"]+= stat.get("physical_cycle_count", 0) or 0
            d["offline_count"]       += stat.get("offline_count", 0) or 0
            d["max_temp_seen"]        = max(d["max_temp_seen"],
                                           stat.get("max_temp_seen") or 0)
            if stat.get("avg_healthy_hashrate"):
                d["hashrate_sum"]   += stat["avg_healthy_hashrate"] * (stat.get("total_readings") or 1)
                d["hashrate_count"] += stat.get("total_readings", 1) or 1
            if stat.get("avg_temp"):
                d["temp_sum"]   += stat["avg_temp"] * (stat.get("total_readings") or 1)
                d["temp_count"] += stat.get("total_readings", 1) or 1

    results = []
    for model, d in sorted(model_data.items(), key=lambda x: -x[1]["total_readings"]):
        results.append({
            "model":                 model,
            "total_readings":        d["total_readings"],
            "avg_healthy_hashrate":  round(d["hashrate_sum"] / d["hashrate_count"], 2)
                                     if d["hashrate_count"] else None,
            "avg_temp":              round(d["temp_sum"] / d["temp_count"], 2)
                                     if d["temp_count"] else None,
            "max_temp_seen":         d["max_temp_seen"],
            "restart_count":         d["restart_count"],
            "pdu_cycle_count":       d["pdu_cycle_count"],
            "physical_cycle_count":  d["physical_cycle_count"],
            "offline_count":         d["offline_count"],
            "failure_rate_pct":      round(
                (d["restart_count"] + d["pdu_cycle_count"] + d["physical_cycle_count"])
                / max(d["total_readings"], 1) * 100, 2),
        })
    return results


def combine_notification_patterns(all_knowledge: list) -> list:
    """Merge AMS notification patterns across all customers."""
    patterns = defaultdict(lambda: defaultdict(int))
    for k in all_knowledge:
        for p in k.get("notification_patterns", []):
            patterns[p.get("key")][p.get("alert_level")] += p.get("count", 0)

    results = []
    for key, levels in sorted(patterns.items()):
        for level, count in sorted(levels.items()):
            results.append({"key": key, "alert_level": level, "count": count})
    return sorted(results, key=lambda x: -x["count"])


def combine_audit_logs(all_knowledge: list) -> list:
    """Combine all audit log entries from all customers."""
    all_entries = []
    for k in all_knowledge:
        source = k.get("_source_file", "unknown")
        for entry in k.get("action_audit_log", []):
            entry["_source"] = source
            all_entries.append(entry)
    return sorted(all_entries, key=lambda x: x.get("date", ""), reverse=True)


def combine_knowledge(input_paths: list, output_path: str = "master_knowledge.json"):
    """Main combiner — merges all knowledge files into one master file."""
    print(f"\n{'='*60}")
    print(f"  Mining Guardian — Knowledge Combiner")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    all_knowledge = load_knowledge_files(input_paths)
    if not all_knowledge:
        print("❌ No valid knowledge files found. Exiting.")
        return

    print(f"\nCombining {len(all_knowledge)} knowledge files...\n")

    master = {
        "combined_at":    datetime.now().isoformat(),
        "combine_version":"1.0",
        "source_count":   len(all_knowledge),
        "sources":        [k.get("_source_file") for k in all_knowledge],
        "model_statistics":       combine_model_statistics(all_knowledge),
        "notification_patterns":  combine_notification_patterns(all_knowledge),
        "action_audit_log":       combine_audit_logs(all_knowledge),
    }

    with open(output_path, "w") as f:
        json.dump(master, f, indent=2, default=str)

    print(f"✅ Master knowledge written to {output_path}")
    print(f"   Sources combined:   {len(all_knowledge)}")
    print(f"   Models tracked:     {len(master['model_statistics'])}")
    print(f"   Alert patterns:     {len(master['notification_patterns'])}")
    print(f"   Audit entries:      {len(master['action_audit_log'])}")
    print(f"\nDistribute {output_path} to all customer Mac Minis.")
    print("Drop it in the Mining Guardian repo folder as master_knowledge.json.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Combine Mining Guardian knowledge files")
    parser.add_argument("files", nargs="*", help="Knowledge JSON files to combine")
    parser.add_argument("--input", help="Folder containing knowledge JSON files")
    parser.add_argument("--output", default="master_knowledge.json",
                        help="Output file (default: master_knowledge.json)")
    args = parser.parse_args()

    paths = []
    if args.input:
        folder = Path(args.input)
        paths = list(folder.glob("*.json"))
        if not paths:
            print(f"No JSON files found in {args.input}")
            exit(1)
    elif args.files:
        paths = [Path(f) for f in args.files]
    else:
        print("Usage: python combine_knowledge.py --input /folder/  OR  file1.json file2.json")
        exit(1)

    combine_knowledge(paths, args.output)
