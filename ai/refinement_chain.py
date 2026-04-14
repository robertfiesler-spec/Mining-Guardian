#!/usr/bin/env python3
"""
refinement_chain.py — Mining Guardian Weekly Refinement Chain (resume-safe v2)

Four-pass learning loop:
  Pass 1: Qwen daily deep dive (read from knowledge['daily_deep_analyses'][0])
  Pass 2: Claude weekly training (read from knowledge['cross_miner_analysis'][0])
  Pass 3: Qwen reflection on Claude's output (WRITTEN HERE)
  Pass 4: Claude merged final report (WRITTEN HERE)

Resume-safety guarantees (added 2026-04-10 after Pass 4 crashed and lost Pass 3):
  - Pre-flight checks validate ALL dependencies BEFORE firing any model call:
      Pass 1 exists, Pass 2 exists, anthropic SDK imports, API key present,
      Qwen endpoint reachable.
  - After Pass 3 completes, it is IMMEDIATELY written to
      /root/Mining-Gaurdian/refinement_chain_wip/pass3_YYYYMMDD_HHMMSS.json
      BEFORE Pass 4 is attempted. If Pass 4 crashes, Pass 3 is preserved
      and --resume-from 4 can re-run Pass 4 against the saved Pass 3.
  - --smoke-test runs the plumbing end-to-end with fake 500-char inputs
      in ~60 seconds to verify the pipeline before burning 20+ minutes.
  - --resume-from {3,4} skips earlier passes and uses the most recent WIP file.

Storage (on success):
  - Full chain in knowledge['weekly_refinement_chain'] (last 10 preserved)
  - Pass 4 ALSO overwrites knowledge['cross_miner_analysis'][0] so Sunday's
    train_cohort.py merge block picks up the refined version next week.

Usage:
  venv/bin/python3 ai/refinement_chain.py                # Full run
  venv/bin/python3 ai/refinement_chain.py --smoke-test   # Plumbing test
  venv/bin/python3 ai/refinement_chain.py --dry-run      # Show plan, no calls
  venv/bin/python3 ai/refinement_chain.py --resume-from 4  # Skip Pass 3
"""
import argparse
import json
import logging
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "ai"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("refinement_chain")

KNOWLEDGE_PATH = _ROOT / "knowledge.json"
CONFIG_PATH = _ROOT / "config.json"
WIP_DIR = _ROOT / "refinement_chain_wip"


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_knowledge():
    with open(KNOWLEDGE_PATH) as f:
        return json.load(f)


def save_knowledge(k):
    """Atomic write via tmp + os.replace."""
    tmp = str(KNOWLEDGE_PATH) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(k, f, indent=2)
    os.replace(tmp, str(KNOWLEDGE_PATH))


def save_pass_wip(pass_name, payload):
    """Immediately persist a completed pass to disk so it survives later failures."""
    WIP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = WIP_DIR / f"{pass_name}_{ts}.json"
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    logger.info("WIP saved: %s (%d bytes)", path, path.stat().st_size)
    return path


def load_latest_pass_wip(pass_name):
    """Find the most recent WIP file for a given pass."""
    if not WIP_DIR.exists():
        return None
    candidates = sorted(WIP_DIR.glob(f"{pass_name}_*.json"))
    if not candidates:
        return None
    latest = candidates[-1]
    logger.info("Resuming from WIP: %s", latest)
    with open(latest) as f:
        return json.load(f)


def get_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    env_path = _ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def preflight_checks(config, resume_from, smoke_test):
    """Validate EVERYTHING before firing any model call. Fail fast and loud."""
    logger.info("=== PRE-FLIGHT CHECKS ===")
    errors = []

    # Check 1: anthropic SDK (always needed, even in --resume-from 4)
    try:
        import anthropic  # noqa: F401
        logger.info("[OK] anthropic SDK importable")
    except ImportError:
        errors.append("anthropic SDK not installed — run: venv/bin/pip install anthropic")

    # Check 2: Claude API key
    if not get_api_key():
        errors.append("ANTHROPIC_API_KEY not found in env or .env file")
    else:
        logger.info("[OK] ANTHROPIC_API_KEY present")

    # Checks 3+4: Pass 1 and Pass 2 on disk (skip if smoke-testing with fakes)
    if not smoke_test:
        try:
            k = load_knowledge()
            dda = k.get("daily_deep_analyses", [])
            if not dda or not dda[0].get("fleet_synthesis"):
                errors.append("knowledge['daily_deep_analyses'][0] missing or empty — run daily_deep_dive.py first")
            else:
                logger.info("[OK] Pass 1 (Qwen deep dive): %d chars", len(dda[0]["fleet_synthesis"]))
            cma = k.get("cross_miner_analysis", [])
            pass_2_found = any(e.get("source") == "claude_weekly_cohort" for e in cma)
            if not pass_2_found and not cma:
                errors.append("knowledge['cross_miner_analysis'] missing — run weekly_train.py first")
            else:
                logger.info("[OK] Pass 2 (Claude weekly): found")
        except Exception as e:
            errors.append(f"Could not load knowledge.json: {e}")

    # Check 5: Qwen endpoint reachable (skip if resuming past Pass 3)
    if resume_from < 4:
        url = config.get("ollama_url", os.getenv("OLLAMA_URL", "http://100.110.87.1:11434/api/generate"))
        tags_url = url.replace("/api/generate", "/api/tags")
        try:
            with urllib.request.urlopen(tags_url, timeout=10) as r:
                data = json.loads(r.read().decode())
            models = [m["name"] for m in data.get("models", [])]
            target = config.get("ollama_model", "qwen2.5:32b-instruct-q4_K_M")
            if target not in models:
                errors.append(f"Qwen model '{target}' not loaded on ROBS-PC. Available: {models}")
            else:
                logger.info("[OK] Qwen endpoint reachable, model '%s' loaded", target)
        except Exception as e:
            errors.append(f"Qwen endpoint {tags_url} unreachable: {e}")

    # Check 6: WIP dir writable
    try:
        WIP_DIR.mkdir(parents=True, exist_ok=True)
        test = WIP_DIR / ".write_test"
        test.write_text("ok")
        test.unlink()
        logger.info("[OK] WIP directory writable: %s", WIP_DIR)
    except Exception as e:
        errors.append(f"WIP directory not writable: {e}")

    # Check 7: If resuming from Pass 4, make sure we have a Pass 3 WIP to resume from
    if resume_from >= 4 and not smoke_test:
        wip = load_latest_pass_wip("pass3")
        if not wip:
            errors.append("--resume-from 4 requested but no pass3_*.json file in refinement_chain_wip/")
        else:
            logger.info("[OK] Pass 3 WIP available for resume")

    if errors:
        logger.error("PRE-FLIGHT FAILED:")
        for e in errors:
            logger.error("  - %s", e)
        raise RuntimeError("Pre-flight checks failed — fix the above and retry")
    logger.info("=== ALL PRE-FLIGHT CHECKS PASSED ===")


def get_pass_1_and_2(k):
    pass_1 = k["daily_deep_analyses"][0]
    cma = k.get("cross_miner_analysis", [])
    pass_2 = None
    for entry in cma:
        if entry.get("source") == "claude_weekly_cohort":
            pass_2 = entry
            break
    if not pass_2:
        pass_2 = cma[0]
    return pass_1, pass_2


def build_pass_3_prompt(pass_1, pass_2):
    return f"""You are Qwen 2.5 32B, the local LLM for the BiXBiT USA Mining Guardian system at a 58-miner liquid-cooled Bitcoin mining facility in Fort Worth, TX.

This is a LEARNING REFLECTION task. Your goal is not to produce another fleet report — it is to LEARN from comparing your own recent work to Claude's.

LOCKED OPERATOR RULES (never violate):
1. Fleet is 58 miners, liquid-cooled.
2. Do NOT flag chip temps below 84 degrees C.
3. Do NOT recommend HVAC investigation for low delta-T.
4. 2+ failed restarts in 7 days auto-escalates to RESTART_CHECK_BOARDS.
5. 20-minute post-restart grace period.
6. Dead S19JPro boards suppressed after ticket creation.
7. Firmware regression rule: N+ identical faults after firmware update means ROLL BACK, not replace.
8. Auradine AH3880 April 8 firmware regression: verdict was ROLL BACK FIRMWARE, not replace.

=== YOUR OWN DAILY DEEP DIVE FROM LAST NIGHT (2026-04-09) ===

{pass_1.get('fleet_synthesis', '(no fleet synthesis)')}

=== CLAUDE'S WEEKLY SYNTHESIS FROM THIS MORNING ===

{pass_2.get('analysis', '(no analysis)')}

=== YOUR LEARNING REFLECTION TASK ===

Answer each section thoroughly. No length limit. Be honest and self-critical.

SECTION 1 — AGREEMENTS: Where did Claude agree with your deep dive? List specific findings and miner IPs. These are HIGH CONFIDENCE.

SECTION 2 — DISAGREEMENTS: For each disagreement: (a) what Claude said, (b) what you said, (c) who is right and why, (d) if Claude was right and you missed it, why did you miss it, (e) if you were right, what in Claude's context caused the error.

SECTION 3 — CLAUDE'S KNOWN ERRORS: Claude's report contained these errors. Identify each in your own words and explain why they violate the locked rules:
  - "47 of 49 miners online" (actual fleet is 58)
  - REPLACE recommendation for s21exphyd/BIXBIT (newest hardware)
  - REPLACE recommendation for ah3880/AURADINE (contradicts rule 8)
  - Claude re-proposed the 2-restart escalation rule and 84C threshold rule as "new" (both already locked)
  - Claude's predictive warnings omitted miner 53482 (canonical degrader) and 53476 (new pool code 1003 issue)

SECTION 4 — NEW TECHNIQUES TO INTERNALIZE: What analytical techniques from Claude's report should you add to your toolkit? List them as specific rules for your next deep dive.

SECTION 5 — SELF-ASSESSMENT: Where was your deep dive weakest? Where were you most confident and right? What is ONE concrete thing you will do differently tomorrow?

SECTION 6 — OPEN QUESTIONS: For disagreements you could not resolve, what additional data would you need?

Begin your reflection now. Be thorough."""


def fire_pass_3_qwen_reflection(pass_1, pass_2, config, smoke_test=False):
    if smoke_test:
        prompt = "Say 'SMOKE TEST PASS 3 OK' and nothing else."
    else:
        prompt = build_pass_3_prompt(pass_1, pass_2)
    payload = {
        "model": config.get("ollama_model", "qwen2.5:32b-instruct-q4_K_M"),
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.4, "num_ctx": 32768, "num_predict": -1},
    }
    url = config.get("ollama_url", os.getenv("OLLAMA_URL", "http://100.110.87.1:11434/api/generate"))
    logger.info("Pass 3: firing Qwen (prompt %d chars, unconstrained output)", len(prompt))
    t0 = time.time()
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=3600) as r:
        resp = json.loads(r.read().decode())
    elapsed = time.time() - t0
    reflection = resp.get("response", "").strip()
    logger.info("Pass 3: complete (%.1fs, %d chars)", elapsed, len(reflection))
    result = {
        "timestamp": datetime.now().isoformat(),
        "source": "qwen_learning_reflection",
        "model": payload["model"],
        "elapsed_s": round(elapsed, 1),
        "reflection": reflection,
        "prompt_chars": len(prompt),
        "eval_count": resp.get("eval_count"),
        "prompt_eval_count": resp.get("prompt_eval_count"),
    }
    # CHECKPOINT: save immediately before Pass 4 can possibly crash
    save_pass_wip("pass3", result)
    return result


def build_pass_4_prompt(pass_2, pass_3):
    return f"""You are Claude Sonnet, producing the FINAL MERGED weekly fleet report for Mining Guardian at BiXBiT USA (58 miners, liquid-cooled, Fort Worth TX).

You have two inputs: your own weekly synthesis from earlier today, and Qwen 2.5 32B's learning reflection on your work. Qwen identified agreements, disagreements, errors you made, and techniques it plans to internalize.

Your job: produce a FINAL MERGED report that keeps agreed findings (HIGH CONFIDENCE), resolves disagreements honestly (sometimes Qwen caught you making mistakes), corrects your original errors, notes any Qwen errors, and adds a META-LEARNING section.

=== YOUR ORIGINAL WEEKLY SYNTHESIS ===

{pass_2.get('analysis', '(no analysis)')}

=== QWEN'S LEARNING REFLECTION ===

{pass_3['reflection']}

=== YOUR TASK ===

Produce the FINAL MERGED WEEKLY REPORT with:
1. EXECUTIVE SUMMARY — corrected, confidence-scored headline
2. HIGH CONFIDENCE FINDINGS (both models agreed) — with specific miner IDs/IPs
3. MEDIUM CONFIDENCE FINDINGS (one model flagged, other did not)
4. CORRECTED ERRORS FROM YOUR ORIGINAL — acknowledge each error Qwen caught
5. QWEN ERRORS CAUGHT (if any) — places Qwen's reflection was wrong
6. PREDICTIVE WARNINGS — corrected merged list with timelines
7. OPERATOR RULES — only genuinely new rules not already locked
8. META-LEARNING — 3-5 bullets on what this comparison taught both models

Be direct and specific."""


def fire_pass_4_claude_merged(pass_2, pass_3, smoke_test=False):
    from anthropic import Anthropic
    client = Anthropic(api_key=get_api_key())
    if smoke_test:
        prompt = "Say 'SMOKE TEST PASS 4 OK' and nothing else."
    else:
        prompt = build_pass_4_prompt(pass_2, pass_3)
    logger.info("Pass 4: firing Claude (prompt %d chars)", len(prompt))
    t0 = time.time()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed = time.time() - t0
    final_text = "".join(b.text for b in response.content if hasattr(b, "text"))
    logger.info(
        "Pass 4: complete (%.1fs, %d chars, in=%d out=%d tokens)",
        elapsed, len(final_text),
        response.usage.input_tokens, response.usage.output_tokens,
    )
    result = {
        "timestamp": datetime.now().isoformat(),
        "source": "claude_refined_merged_v1",
        "model": "claude-sonnet-4-20250514",
        "elapsed_s": round(elapsed, 1),
        "analysis": final_text,
        "prompt_chars": len(prompt),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    save_pass_wip("pass4", result)
    return result


def write_final_state(pass_1, pass_2, pass_3, pass_4):
    """Re-read knowledge (minimize clobber window), write chain + overwrite cma[0]."""
    k = load_knowledge()
    chain_entry = {
        "chain_date": datetime.now().strftime("%Y-%m-%d"),
        "chain_timestamp": datetime.now().isoformat(),
        "pass_1_deep_dive_ref": {
            "date": pass_1.get("date"),
            "fleet_synthesis_chars": len(pass_1.get("fleet_synthesis", "")),
        },
        "pass_2_claude_weekly_ref": {
            "timestamp": pass_2.get("timestamp"),
            "analysis_chars": len(pass_2.get("analysis", "")),
            "analysis": pass_2.get("analysis"),
        },
        "pass_3_qwen_reflection": pass_3,
        "pass_4_claude_merged": pass_4,
    }
    if not isinstance(k.get("weekly_refinement_chain"), list):
        k["weekly_refinement_chain"] = []
    k["weekly_refinement_chain"].insert(0, chain_entry)
    k["weekly_refinement_chain"] = k["weekly_refinement_chain"][:10]

    if not isinstance(k.get("cross_miner_analysis"), list):
        k["cross_miner_analysis"] = []
    k["cross_miner_analysis"].insert(0, {
        "timestamp": pass_4["timestamp"],
        "analysis": pass_4["analysis"],
        "source": "claude_refined_merged_v1",
        "refinement_chain_date": datetime.now().strftime("%Y-%m-%d"),
    })
    k["cross_miner_analysis"] = k["cross_miner_analysis"][:10]
    save_knowledge(k)
    logger.info("Final state written to knowledge.json")


def run_chain(dry_run=False, smoke_test=False, resume_from=3):
    logger.info("=" * 60)
    logger.info("WEEKLY REFINEMENT CHAIN — resume_from=%d smoke_test=%s dry_run=%s",
                resume_from, smoke_test, dry_run)
    logger.info("=" * 60)

    config = load_config()
    preflight_checks(config, resume_from, smoke_test)

    if dry_run:
        logger.info("DRY RUN — pre-flight passed, exiting without firing passes")
        return

    # Load Pass 1 and Pass 2 (or fakes for smoke test)
    if smoke_test:
        pass_1 = {"date": "smoke", "fleet_synthesis": "x" * 500}
        pass_2 = {"timestamp": "smoke", "analysis": "y" * 500, "source": "claude_weekly_cohort"}
    else:
        k = load_knowledge()
        pass_1, pass_2 = get_pass_1_and_2(k)
        logger.info("Pass 1: %s, %d chars", pass_1.get("date", "?"), len(pass_1.get("fleet_synthesis", "")))
        logger.info("Pass 2: %s, %d chars", pass_2.get("timestamp", "?"), len(pass_2.get("analysis", "")))

    # Pass 3
    if resume_from <= 3:
        pass_3 = fire_pass_3_qwen_reflection(pass_1, pass_2, config, smoke_test=smoke_test)
    else:
        pass_3 = load_latest_pass_wip("pass3")
        logger.info("Pass 3: loaded from WIP (%d chars)", len(pass_3.get("reflection", "")))

    # Pass 4
    pass_4 = fire_pass_4_claude_merged(pass_2, pass_3, smoke_test=smoke_test)

    # Final write (skip in smoke test to avoid polluting real knowledge.json)
    if smoke_test:
        logger.info("SMOKE TEST: skipping final write to knowledge.json")
    else:
        write_final_state(pass_1, pass_2, pass_3, pass_4)

    logger.info("=" * 60)
    logger.info("REFINEMENT CHAIN COMPLETE")
    logger.info("  Pass 3: %d chars", len(pass_3.get("reflection", "")))
    logger.info("  Pass 4: %d chars", len(pass_4.get("analysis", "")))
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--resume-from", type=int, default=3, choices=[3, 4])
    args = parser.parse_args()
    try:
        run_chain(dry_run=args.dry_run, smoke_test=args.smoke_test, resume_from=args.resume_from)
    except Exception as e:
        logger.error("Refinement chain failed: %s", e, exc_info=True)
        sys.exit(1)
