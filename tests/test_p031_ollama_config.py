"""
tests/test_p031_ollama_config.py

P-031 (2026-05-08) — regression tests for the Ollama URL + model
resolution fix.

Pre-P-031 the scanner and four sibling AI scripts each fell back to
the never-installed `qwen2.5:32b-instruct-q4_K_M`, producing:

    Qwen scan analysis failed: HTTP Error 404: Not Found

every scan, because D-13 only ever pulls `llama3.2:3b` (16 GB tier) or
`qwen2.5:14b-instruct-q4_K_M` (24 GB+ tier). These tests lock in:

  1. core/ollama_config.py never returns the 32B model from any
     fallback path.
  2. The env-first chain (OLLAMA_MODEL → MG_INSTALL_LLM_MODEL → D-13
     small-tier default) is honored in the documented order.
  3. GuardianConfig.from_file populates ollama_url / ollama_model
     correctly with config.json values, env vars, and absent keys.
  4. The installer postinstall.sh writes both OLLAMA_URL and
     OLLAMA_MODEL to .env, and the config.json materializer injects
     env: placeholders for both keys.
  5. Every Python call site has had its hard-coded 32B fallback
     removed.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import core.ollama_config as ollama_config  # noqa: E402
from core.models import GuardianConfig  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────
# §1. core.ollama_config — pure unit tests on the resolver
# ─────────────────────────────────────────────────────────────────────────


class TestResolveOllamaModel:
    def setup_method(self):
        # Clear any inherited env between tests.
        for k in ("OLLAMA_MODEL", "MG_INSTALL_LLM_MODEL"):
            os.environ.pop(k, None)

    def teardown_method(self):
        for k in ("OLLAMA_MODEL", "MG_INSTALL_LLM_MODEL"):
            os.environ.pop(k, None)

    def test_no_32b_string_literal_in_module(self):
        """The 32B model name must not appear as a string literal in
        core/ollama_config.py — i.e. must not be quoted, only referenced
        in comments describing what the P-031 fix removed.
        """
        src = (REPO_ROOT / "core" / "ollama_config.py").read_text()
        for quote in ('"qwen2.5:32b', "'qwen2.5:32b"):
            assert quote not in src, (
                f"core/ollama_config.py contains the string literal "
                f"{quote!r} — the 32B model is the never-pulled fallback "
                "that P-031 removed; commentary references are fine but "
                "the literal must not survive."
            )

    def test_default_when_nothing_set_is_d13_small_tier(self):
        assert ollama_config.resolve_ollama_model() == "llama3.2:3b"

    def test_default_is_never_qwen_32b(self):
        # Sweep every reachable empty-input path.
        assert "qwen2.5:32b" not in ollama_config.resolve_ollama_model()
        assert "qwen2.5:32b" not in ollama_config.resolve_ollama_model("")
        assert "qwen2.5:32b" not in ollama_config.resolve_ollama_model(None)

    def test_explicit_argument_wins_over_env(self):
        os.environ["OLLAMA_MODEL"] = "from-env"
        os.environ["MG_INSTALL_LLM_MODEL"] = "from-install"
        assert ollama_config.resolve_ollama_model("from-config") == "from-config"

    def test_ollama_model_env_wins_over_install_env(self):
        os.environ["OLLAMA_MODEL"] = "qwen2.5:14b-instruct-q4_K_M"
        os.environ["MG_INSTALL_LLM_MODEL"] = "llama3.2:3b"
        assert (
            ollama_config.resolve_ollama_model()
            == "qwen2.5:14b-instruct-q4_K_M"
        )

    def test_install_env_used_when_ollama_model_unset(self):
        # This is the actual D-13 production flow: detect_ram.sh writes
        # MG_INSTALL_LLM_MODEL, the launcher sources .env, the scanner
        # picks it up.
        os.environ["MG_INSTALL_LLM_MODEL"] = "qwen2.5:14b-instruct-q4_K_M"
        assert (
            ollama_config.resolve_ollama_model()
            == "qwen2.5:14b-instruct-q4_K_M"
        )

    def test_install_env_for_16gb_tier(self):
        os.environ["MG_INSTALL_LLM_MODEL"] = "llama3.2:3b"
        assert ollama_config.resolve_ollama_model() == "llama3.2:3b"


class TestResolveOllamaUrl:
    def setup_method(self):
        os.environ.pop("OLLAMA_URL", None)

    def teardown_method(self):
        os.environ.pop("OLLAMA_URL", None)

    def test_default_is_local_mini(self):
        # D-9 / S-13 — no Tailscale, no off-Mini calls.
        url = ollama_config.resolve_ollama_url()
        assert url.startswith("http://127.0.0.1:11434")
        assert url.endswith("/api/generate")

    def test_explicit_wins_over_env(self):
        os.environ["OLLAMA_URL"] = "http://from-env:11434/api/generate"
        assert (
            ollama_config.resolve_ollama_url("http://from-config:11434/api/generate")
            == "http://from-config:11434/api/generate"
        )

    def test_env_used_when_explicit_unset(self):
        os.environ["OLLAMA_URL"] = "http://from-env:11434/api/generate"
        assert (
            ollama_config.resolve_ollama_url()
            == "http://from-env:11434/api/generate"
        )

    def test_no_retired_robs_pc_in_default(self):
        # The retired ROBS-PC tailscale IP must never reappear as a
        # silent default (D-9, P-018E).
        assert "100.110" not in ollama_config.resolve_ollama_url()


# ─────────────────────────────────────────────────────────────────────────
# §2. GuardianConfig.from_file integration
# ─────────────────────────────────────────────────────────────────────────

_MIN_CONFIG = {
    "ams_base_url": "https://api-staging.dev.bixbit.io/api/v1",
    "ams_email": "test@example.com",
    "ams_password": "test-pw",
    "ams_workspace_id": 119,
    "rules": [],
}


def _write_cfg(payload):
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    Path(path).write_text(json.dumps(payload))
    return path


class TestGuardianConfigOllamaFields:
    def setup_method(self):
        for k in ("OLLAMA_MODEL", "MG_INSTALL_LLM_MODEL", "OLLAMA_URL"):
            os.environ.pop(k, None)

    def teardown_method(self):
        for k in ("OLLAMA_MODEL", "MG_INSTALL_LLM_MODEL", "OLLAMA_URL"):
            os.environ.pop(k, None)

    def test_absent_keys_use_d13_defaults(self):
        path = _write_cfg(_MIN_CONFIG)
        try:
            cfg = GuardianConfig.from_file(path)
        finally:
            os.unlink(path)
        assert cfg.ollama_model == "llama3.2:3b"
        assert cfg.ollama_url.endswith("/api/generate")

    def test_env_placeholder_resolves_to_install_model(self):
        os.environ["MG_INSTALL_LLM_MODEL"] = "qwen2.5:14b-instruct-q4_K_M"
        os.environ["OLLAMA_MODEL"] = "qwen2.5:14b-instruct-q4_K_M"
        os.environ["OLLAMA_URL"] = "http://127.0.0.1:11434/api/generate"
        payload = dict(_MIN_CONFIG)
        payload["ollama_model"] = "env:OLLAMA_MODEL"
        payload["ollama_url"] = "env:OLLAMA_URL"
        path = _write_cfg(payload)
        try:
            cfg = GuardianConfig.from_file(path)
        finally:
            os.unlink(path)
        assert cfg.ollama_model == "qwen2.5:14b-instruct-q4_K_M"
        assert cfg.ollama_url == "http://127.0.0.1:11434/api/generate"

    def test_unset_env_placeholder_falls_back_gracefully(self):
        # If the operator's config.json references env:OLLAMA_MODEL but
        # the .env doesn't actually export it, GuardianConfig must NOT
        # raise — it must fall back to the install/D-13 chain. Pre-P-031
        # _resolve raised EnvironmentError on missing env vars.
        payload = dict(_MIN_CONFIG)
        payload["ollama_model"] = "env:OLLAMA_MODEL"
        os.environ["MG_INSTALL_LLM_MODEL"] = "llama3.2:3b"
        path = _write_cfg(payload)
        try:
            cfg = GuardianConfig.from_file(path)
        finally:
            os.unlink(path)
        assert cfg.ollama_model == "llama3.2:3b"
        assert "qwen2.5:32b" not in cfg.ollama_model

    def test_literal_model_string_in_config_wins(self):
        payload = dict(_MIN_CONFIG)
        payload["ollama_model"] = "qwen2.5:14b-instruct-q4_K_M"
        path = _write_cfg(payload)
        try:
            cfg = GuardianConfig.from_file(path)
        finally:
            os.unlink(path)
        assert cfg.ollama_model == "qwen2.5:14b-instruct-q4_K_M"


# ─────────────────────────────────────────────────────────────────────────
# §3. No 32B fallback survives in any Python call site
# ─────────────────────────────────────────────────────────────────────────

_CALL_SITES = [
    "core/mining_guardian.py",
    "ai/local_llm_analyzer.py",
    "ai/daily_deep_dive.py",
    "ai/refinement_chain.py",
    "ai/combine_knowledge.py",
]


@pytest.mark.parametrize("relpath", _CALL_SITES)
def test_no_qwen_32b_string_literal_in_call_site(relpath):
    """The 32B model literal must not appear as a quoted string in any
    active call site.

    P-031 root cause: every one of these files used
    `qwen2.5:32b-instruct-q4_K_M` as a hard-coded fallback when neither
    config.json nor the env supplied a value. That model is not pulled
    by detect_ram.sh / install_ollama.sh on either D-13 RAM tier, so
    Ollama returned 404 for every scan.

    Comment references describing the bug are allowed (and useful for
    git-blame / future agent context); only quoted string literals
    indicate live fallback code.
    """
    src = (REPO_ROOT / relpath).read_text()
    for quote in ('"qwen2.5:32b', "'qwen2.5:32b"):
        assert quote not in src, (
            f"{relpath} contains the string literal {quote!r} — the 32B "
            "model is never pulled by the D-13 installer (16 GB → "
            "llama3.2:3b, 24 GB+ → qwen2.5:14b-instruct-q4_K_M). Resolve "
            "via core.ollama_config instead of hard-coding."
        )


# ─────────────────────────────────────────────────────────────────────────
# §4. Installer wiring — postinstall .env + config.json
# ─────────────────────────────────────────────────────────────────────────


def _read(p):
    return (REPO_ROOT / p).read_text()


class TestInstallerWiring:
    def test_postinstall_env_writes_ollama_url(self):
        src = _read("installer/macos-pkg/scripts/postinstall.sh")
        assert "OLLAMA_URL=http://127.0.0.1:11434/api/generate" in src, (
            "postinstall.sh step_drop_dotenv must write OLLAMA_URL to .env "
            "(P-031). Without it, Python callers that read the env directly "
            "fall through to the D-9 default — which is correct, but the "
            "explicit line is the documentation contract that operators "
            "and future agents grep for."
        )

    def test_postinstall_env_writes_ollama_model_from_install_pick(self):
        src = _read("installer/macos-pkg/scripts/postinstall.sh")
        assert "OLLAMA_MODEL=${MG_INSTALL_LLM_MODEL_Q}" in src, (
            "postinstall.sh step_drop_dotenv must write OLLAMA_MODEL to "
            ".env, sourced from MG_INSTALL_LLM_MODEL (the value detect_ram.sh "
            "/ install_ollama.sh actually pulled per D-13). P-031."
        )

    def test_postinstall_config_json_injects_ollama_url_placeholder(self):
        src = _read("installer/macos-pkg/scripts/postinstall.sh")
        assert 'cfg["ollama_url"]' in src, (
            "step_drop_config_json must inject ollama_url into config.json "
            "as an env: placeholder (P-031)."
        )
        assert '"env:OLLAMA_URL"' in src

    def test_postinstall_config_json_injects_ollama_model_placeholder(self):
        src = _read("installer/macos-pkg/scripts/postinstall.sh")
        assert 'cfg["ollama_model"]' in src, (
            "step_drop_config_json must inject ollama_model into config.json "
            "as an env: placeholder (P-031)."
        )
        assert '"env:OLLAMA_MODEL"' in src
