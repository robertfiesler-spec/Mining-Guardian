"""
tests/test_p035_knowledge_persistence_hardening.py

P-034 + P-035 (2026-05-08) — consolidated knowledge / LLM persistence
hardening regression suite.

Two related issues surfaced together on the customer Mac Mini after
installing package eecde3a:

  P-034 — `core/mining_guardian.py` post-Qwen-scan persistence block
          hard-coded `/root/Mining-Guardian/knowledge.json` (a Linux/
          legacy dev path that does not exist in the install tree).
          Every scan logged
          `[Errno 2] No such file or directory:
           '/root/Mining-Guardian/knowledge.json.tmp'`
          even though the Qwen call itself succeeded. The
          `llm_scan_analyses` stream that `weekly_train.py` reads
          (Vision Anchor 1 — the LLM IS the product) therefore
          stopped accumulating.

  P-035 — `ai/knowledge_manager.py::update_from_scan` did
          `profile["total_flags"] += 1` against an existing entry in
          `knowledge["miner_profiles"]`. If a pre-existing profile
          (e.g. one carried in from the seed payload, a hand-written
          ops dump, or a partially-merged federated update) lacked
          the `total_flags` key, the line raised
          `KeyError: 'total_flags'`. Live evidence on the same Mini
          install logged
          `WARNING Knowledge update skipped: 'total_flags'`
          immediately after the (now-fixed) Qwen persistence error.

This module locks in:

  §1. P-034 path/locked-write fix in the Qwen post-scan block
       (regression — copied from PR #167's test surface).
  §2. P-035 KnowledgeManager defensive backfill on legacy seed-shaped
       miner_profiles entries that lack `total_flags`,
       `last_flagged`, or `issue_history`.
  §3. P-035 writer hardening — every active scheduled writer of
       knowledge.json under `core/` and `ai/` uses the canonical
       `core.file_lock` helpers (locked_knowledge_update or
       atomic_write_json), and no module hand-rolls a tmp + os.replace
       on the knowledge path.
"""

import ast
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER_PATH = REPO_ROOT / "core" / "mining_guardian.py"
KM_PATH = REPO_ROOT / "ai" / "knowledge_manager.py"

# Make the repo root importable so we can import KnowledgeManager + core.file_lock
# in unit-test mode without sys.path scaffolding leaking elsewhere.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _scanner_src() -> str:
    return SCANNER_PATH.read_text()


def _qwen_block(src: str) -> str:
    """Slice mining_guardian.py covering the Qwen post-scan persistence block.

    Pinned by stable sentinels: the analysis_text assignment that follows
    the Ollama HTTP call, and the `Qwen scan analysis failed` warning that
    closes the surrounding try/except.
    """
    start_token = 'analysis_text = resp.get("response"'
    end_token = "Qwen scan analysis failed"
    i = src.index(start_token)
    j = src.index(end_token, i)
    return src[i:j]


# ─────────────────────────────────────────────────────────────────────────
# §1. P-034 — Qwen post-scan persistence block uses _ROOT + locked helper
# ─────────────────────────────────────────────────────────────────────────


def test_p034_qwen_block_no_root_mining_guardian_path():
    block = _qwen_block(_scanner_src())
    for quote in (
        '"/root/Mining-Guardian/knowledge.json"',
        "'/root/Mining-Guardian/knowledge.json'",
    ):
        assert quote not in block, (
            f"core/mining_guardian.py Qwen block still contains {quote} — "
            "use `_ROOT / 'knowledge.json'` and "
            "`core.file_lock.locked_knowledge_update` instead. P-034."
        )


def test_p034_qwen_block_uses_root_relative_knowledge_path():
    block = _qwen_block(_scanner_src())
    assert '_ROOT / "knowledge.json"' in block, (
        "Qwen block must resolve the knowledge path via the module-level "
        "`_ROOT` so it works under the dev clone and the Mac Mini install "
        "tree alike. P-034."
    )


def test_p034_qwen_block_uses_locked_knowledge_update():
    block = _qwen_block(_scanner_src())
    assert "locked_knowledge_update" in block, (
        "Qwen block must route the read-modify-write through "
        "`core.file_lock.locked_knowledge_update`. P-034."
    )


def test_p034_qwen_block_imports_file_lock_helper():
    src = _scanner_src()
    assert "from core.file_lock import locked_knowledge_update" in src, (
        "core/mining_guardian.py must import `locked_knowledge_update` "
        "from `core.file_lock`. P-034."
    )


def test_p034_no_hot_path_module_hardcodes_root_knowledge_json():
    """Sweep `core/` + `ai/` (the scanner hot path) and confirm no .py file
    hard-codes `/root/Mining-Guardian/knowledge.json` as a writable target.
    `archive/`, `installer/`, `migrations/`, `intelligence-catalog/`, and
    `tests/` are excluded by design.
    """
    forbidden = "/root/Mining-Guardian/knowledge.json"
    offenders = []
    for sub in ("core", "ai"):
        for py in (REPO_ROOT / sub).rglob("*.py"):
            text = py.read_text()
            for line in text.splitlines():
                # Skip P-034 explanatory comments that mention the legacy
                # path solely to document why the fix exists.
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if forbidden in line and ('"' in line or "'" in line):
                    # only flag actual quoted literals (writable targets)
                    if (f'"{forbidden}"' in line) or (f"'{forbidden}'" in line):
                        offenders.append(f"{py}: {line.strip()}")
    assert not offenders, (
        "Hot-path Python files must not hard-code "
        f"{forbidden!r} as a writable target. Offenders:\n  "
        + "\n  ".join(offenders)
    )


# ─────────────────────────────────────────────────────────────────────────
# §2. P-035 — KnowledgeManager defensive backfill on seed-shaped profiles
# ─────────────────────────────────────────────────────────────────────────


def _seed_knowledge_path() -> Path:
    """Return the installer-payload seed knowledge.json (the live seed
    customers receive)."""
    return (
        REPO_ROOT / "installer" / "macos-pkg" / "resources"
        / "knowledge" / "knowledge.json"
    )


def test_p035_seed_payload_has_profiles_missing_total_flags():
    """Sanity: the live seed actually exhibits the bug shape we're fixing.

    If this assertion ever fails because a future seed regen adds
    `total_flags` to every profile, the rest of P-035 is still a
    defensive measure — but the test should be updated to construct the
    bug shape synthetically rather than dropped.
    """
    seed_path = _seed_knowledge_path()
    if not seed_path.exists():
        pytest.skip("seed payload not present in this checkout")
    seed = json.loads(seed_path.read_text())
    profiles = seed.get("miner_profiles", {})
    assert profiles, "seed payload should ship with miner_profiles"
    missing = [mid for mid, p in profiles.items() if "total_flags" not in p]
    # Live seed at v1.0.2 build had 3 of 96 profiles missing total_flags;
    # any ≥1 is enough to validate the fix path matters.
    assert len(missing) >= 1, (
        "expected at least one seeded profile missing `total_flags` so "
        "the P-035 backfill path is actually exercised in production"
    )


_HAS_PSYCOPG2 = True
try:  # pragma: no cover - environment-dependent
    import psycopg2  # noqa: F401
except ImportError:
    _HAS_PSYCOPG2 = False


@pytest.mark.skipif(not _HAS_PSYCOPG2, reason="psycopg2 not installed in test env")
def test_p035_knowledge_manager_loads_real_seed_without_keyerror(tmp_path):
    """KnowledgeManager constructed against the real seed loads cleanly."""
    seed_path = _seed_knowledge_path()
    if not seed_path.exists():
        pytest.skip("seed payload not present in this checkout")
    # Copy the seed into a tmp_path so the test never mutates the repo seed.
    work = tmp_path / "knowledge.json"
    work.write_text(seed_path.read_text())

    from ai.knowledge_manager import KnowledgeManager

    km = KnowledgeManager(db_path="unused", knowledge_path=str(work))
    # Loading should not raise. A profile missing total_flags is fine.
    assert isinstance(km.knowledge, dict)
    profiles = km.knowledge.get("miner_profiles", {})
    assert profiles, "loaded seed should expose miner_profiles"


@pytest.mark.skipif(not _HAS_PSYCOPG2, reason="psycopg2 not installed in test env")
def test_p035_update_from_scan_backfills_seed_profile_missing_total_flags(tmp_path):
    """Reproducer for B-35: legacy profile lacks `total_flags` → no KeyError."""
    # Hand-build a knowledge.json with a profile missing the three keys
    # update_from_scan reads. This is the exact shape the live seed has.
    legacy = {
        "version": 1,
        "fleet_summary": {},
        "miner_profiles": {
            "65891": {
                "model": "Antminer S19J Pro",
                "ip": "192.168.188.50",
                # no total_flags, no last_flagged, no issue_history
            },
        },
        "known_issues": [],
        "patterns": [],
        "baselines": {},
    }
    work = tmp_path / "knowledge.json"
    work.write_text(json.dumps(legacy))

    from ai.knowledge_manager import KnowledgeManager

    km = KnowledgeManager(db_path="unused", knowledge_path=str(work))

    # Drive the failing scan path that pre-P-035 raised KeyError.
    miners = [{"id": "65891", "status": "online"}]
    issues = [{
        "id": "65891",
        "model": "Antminer S19J Pro",
        "ip": "192.168.188.50",
        "action": "RESTART",
        "issues": ["chip temp 71C"],
    }]

    km.update_from_scan(miners, issues, weather=None, hvac=None)

    profile = km.knowledge["miner_profiles"]["65891"]
    assert profile["total_flags"] == 1, (
        "P-035: update_from_scan must backfill total_flags=0 then "
        "increment to 1, not raise KeyError on a seeded profile."
    )
    assert profile["last_flagged"] is not None
    assert isinstance(profile["issue_history"], list)
    assert len(profile["issue_history"]) == 1
    assert profile["issue_history"][0]["action"] == "RESTART"


def test_p035_update_from_scan_backfill_logic_static_check():
    """Static-source check for the P-035 backfill: even without psycopg2
    available to drive a real KnowledgeManager, the source-level guarantee
    that `update_from_scan` setdefaults the three legacy-prone keys before
    incrementing must hold.
    """
    src = KM_PATH.read_text()
    # Locate update_from_scan body
    idx = src.index("def update_from_scan(")
    next_def = src.index("\n    def ", idx + 5)
    body = src[idx:next_def]
    # All three setdefault calls must precede the += on total_flags.
    plus_eq_idx = body.index('profile["total_flags"] += 1')
    pre_increment = body[:plus_eq_idx]
    for key in ('total_flags', 'last_flagged', 'issue_history'):
        assert f'profile.setdefault("{key}"' in pre_increment, (
            f"P-035: update_from_scan must setdefault('{key}', ...) "
            "before incrementing total_flags so legacy seed profiles "
            "missing the key cannot raise KeyError."
        )


def test_p035_knowledge_manager_save_is_locked():
    """KnowledgeManager.save() must route through locked_knowledge_update."""
    src = KM_PATH.read_text()
    assert "from core.file_lock import locked_knowledge_update" in src
    # The save body must call the helper, not write_text() / json.dump
    # against the path directly.
    save_idx = src.index("def save(self):")
    next_def = src.index("def ", save_idx + 5)
    save_body = src[save_idx:next_def]
    assert "locked_knowledge_update" in save_body, (
        "KnowledgeManager.save() must route the write through "
        "`locked_knowledge_update`."
    )


# ─────────────────────────────────────────────────────────────────────────
# §3. P-035 — every active scheduled knowledge writer uses file_lock
# ─────────────────────────────────────────────────────────────────────────

# Active scheduled writers of knowledge.json. These are the modules cron /
# launchd fires regularly that read-modify-write knowledge.json.
ACTIVE_KNOWLEDGE_WRITERS = [
    "ai/daily_deep_dive.py",
    "ai/train_cohort.py",
    "ai/refinement_chain.py",
    "ai/outcome_checker.py",
    "ai/local_llm_analyzer.py",
    "ai/knowledge_manager.py",
    "core/mining_guardian.py",
]


@pytest.mark.parametrize("rel_path", ACTIVE_KNOWLEDGE_WRITERS)
def test_p035_active_writer_imports_locked_helper(rel_path):
    """Every active scheduled writer must import a file_lock helper.

    The helper may be imported lazily inside the writer function (so the
    module is still importable in environments that don't have the
    package on sys.path), but the import statement must exist somewhere
    in the source.
    """
    text = (REPO_ROOT / rel_path).read_text()
    assert "core.file_lock" in text and "locked_knowledge_update" in text, (
        f"{rel_path} must import `locked_knowledge_update` from "
        "`core.file_lock` to write knowledge.json safely. P-035."
    )


@pytest.mark.parametrize("rel_path", ACTIVE_KNOWLEDGE_WRITERS)
def test_p035_no_hand_rolled_tmp_replace_on_knowledge_path(rel_path):
    """No active writer may hand-roll a `tmp + os.replace` against
    `KNOWLEDGE_PATH` / `knowledge.json` — it must use the locked helper.

    We walk the AST looking for any `os.replace(<x>, <y>)` call whose
    second argument string-form references `KNOWLEDGE_PATH` or
    `knowledge.json`. Any hit is a regression.
    """
    text = (REPO_ROOT / rel_path).read_text()
    tree = ast.parse(text)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_os_replace = (
            isinstance(func, ast.Attribute)
            and func.attr == "replace"
            and isinstance(func.value, ast.Name)
            and func.value.id == "os"
        )
        if not is_os_replace:
            continue
        # Inspect the destination (second positional arg)
        if len(node.args) < 2:
            continue
        dest_src = ast.unparse(node.args[1]) if hasattr(ast, "unparse") else ""
        if "KNOWLEDGE_PATH" in dest_src or "knowledge.json" in dest_src:
            offenders.append(
                f"{rel_path}:{node.lineno}: os.replace(... , {dest_src})"
            )
    assert not offenders, (
        "Active knowledge writers must use "
        "`core.file_lock.locked_knowledge_update` instead of hand-rolling "
        "`os.replace(tmp, knowledge_path)`. Offenders:\n  "
        + "\n  ".join(offenders)
    )


def test_p035_no_writer_uses_path_write_text_for_knowledge():
    """No active writer may call `KNOWLEDGE_PATH.write_text(...)` directly.

    This is the non-atomic write daily_deep_dive used pre-P-035. Walks
    the AST so explanatory mentions in docstrings or comments are not
    counted as offenses.
    """
    offenders = []
    for rel_path in ACTIVE_KNOWLEDGE_WRITERS:
        text = (REPO_ROOT / rel_path).read_text()
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr != "write_text":
                continue
            value_src = (
                ast.unparse(func.value) if hasattr(ast, "unparse") else ""
            )
            if "KNOWLEDGE_PATH" in value_src:
                offenders.append(f"{rel_path}:{node.lineno}: {value_src}.write_text(...)")
    assert not offenders, (
        "Active writers must not call `KNOWLEDGE_PATH.write_text(...)` "
        "(non-atomic, no lock). Use `core.file_lock.locked_knowledge_update`. "
        f"Offenders: {offenders}"
    )


# ─────────────────────────────────────────────────────────────────────────
# §4. combine_knowledge.py federated mastering uses atomic_write_json
# ─────────────────────────────────────────────────────────────────────────


def test_p035_combine_knowledge_uses_atomic_write_helper():
    """combine_knowledge.py federated-master writer routes through
    `core.file_lock.atomic_write_json` (single-writer scenario, no flock
    required, but the temp-file-then-rename guarantee belongs in one
    place)."""
    text = (REPO_ROOT / "ai" / "combine_knowledge.py").read_text()
    assert "atomic_write_json" in text, (
        "ai/combine_knowledge.py must reference "
        "`core.file_lock.atomic_write_json` for the master_knowledge.json "
        "write. P-035."
    )
