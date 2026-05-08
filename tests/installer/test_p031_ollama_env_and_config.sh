#!/usr/bin/env bash
# tests/installer/test_p031_ollama_env_and_config.sh
#
# P-031 (2026-05-08) — installer-side regression tests for the Ollama
# URL + model wiring fix.
#
# Background: pre-P-031 the customer Mac Mini scanner logged
#     Qwen scan analysis failed: HTTP Error 404: Not Found
# every scan. Root cause: every Python call site fell back to
# `qwen2.5:32b-instruct-q4_K_M` when no explicit value was supplied,
# but D-13 only ever pulls `llama3.2:3b` (16 GB tier) or
# `qwen2.5:14b-instruct-q4_K_M` (24 GB+ tier). The .env written by
# postinstall did not carry `OLLAMA_MODEL`, so the env-direct lookup
# missed; config.json did not surface `ollama_model`/`ollama_url`, so
# the GuardianConfig getattr branch missed; the only remaining branch
# was the 32B literal, and Ollama returned 404.
#
# This test asserts:
#   §1  — postinstall.sh parses cleanly (regression guard).
#   §2  — `step_drop_dotenv` writes OLLAMA_URL to .env.
#   §3  — `step_drop_dotenv` writes OLLAMA_MODEL=${MG_INSTALL_LLM_MODEL_Q}
#        to .env (i.e. the value detect_ram.sh / install_ollama.sh
#        actually pulled per D-13).
#   §4  — `step_drop_config_json` injects `ollama_url` as `env:OLLAMA_URL`
#        in the materialized config.json.
#   §5  — `step_drop_config_json` injects `ollama_model` as
#        `env:OLLAMA_MODEL` in the materialized config.json.
#   §6  — No call site uses the literal `qwen2.5:32b-instruct-q4_K_M`
#        as a string-value fallback (commentary references are fine).
#   §7  — `core/ollama_config.py` exists and contains the canonical
#        D-13 16 GB default `llama3.2:3b`.
#
# Run from repo root:
#     bash tests/installer/test_p031_ollama_env_and_config.sh

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

POSTINSTALL="installer/macos-pkg/scripts/postinstall.sh"
OLLAMA_HELPER="core/ollama_config.py"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }
section() { echo; echo "## $*"; }

# ---------------------------------------------------------------------
section "1. postinstall.sh exists and parses cleanly"
# ---------------------------------------------------------------------
if [[ -r "$POSTINSTALL" ]]; then
    ok "$POSTINSTALL present"
else
    fail "$POSTINSTALL missing"
    echo "  Cannot continue." >&2
    exit 2
fi

if bash -n "$POSTINSTALL" 2>/dev/null; then
    ok "postinstall.sh parses cleanly"
else
    fail "postinstall.sh has bash syntax errors"
    exit 2
fi

# ---------------------------------------------------------------------
section "2. step_drop_dotenv writes OLLAMA_URL to .env"
# ---------------------------------------------------------------------
drop_body="$(awk '/^step_drop_dotenv\(\)/,/^}$/' "$POSTINSTALL")"

if grep -qE 'OLLAMA_URL=http://127\.0\.0\.1:11434/api/generate' <<<"$drop_body"; then
    ok ".env writer carries OLLAMA_URL on the local /api/generate endpoint"
else
    fail ".env writer is missing OLLAMA_URL — Python callers will fall through to the helper default but the documentation contract is the explicit line"
fi

# ---------------------------------------------------------------------
section "3. step_drop_dotenv writes OLLAMA_MODEL from MG_INSTALL_LLM_MODEL"
# ---------------------------------------------------------------------
if grep -qE 'OLLAMA_MODEL=\$\{MG_INSTALL_LLM_MODEL_Q\}' <<<"$drop_body"; then
    ok ".env writer sources OLLAMA_MODEL from the installer-chosen MG_INSTALL_LLM_MODEL"
else
    fail ".env writer does not interpolate MG_INSTALL_LLM_MODEL into OLLAMA_MODEL — root cause of the 404 is unfixed"
fi

# ---------------------------------------------------------------------
section "4. step_drop_config_json injects ollama_url as env: placeholder"
# ---------------------------------------------------------------------
config_body="$(awk '/^step_drop_config_json\(\)/,/^}$/' "$POSTINSTALL")"

if grep -qE 'cfg\["ollama_url"\][[:space:]]*=[[:space:]]*"env:OLLAMA_URL"' <<<"$config_body"; then
    ok "config.json materializer injects ollama_url=env:OLLAMA_URL"
else
    fail "config.json materializer does not inject ollama_url — GuardianConfig.from_file will leave the field unset"
fi

# ---------------------------------------------------------------------
section "5. step_drop_config_json injects ollama_model as env: placeholder"
# ---------------------------------------------------------------------
if grep -qE 'cfg\["ollama_model"\][[:space:]]*=[[:space:]]*"env:OLLAMA_MODEL"' <<<"$config_body"; then
    ok "config.json materializer injects ollama_model=env:OLLAMA_MODEL"
else
    fail "config.json materializer does not inject ollama_model — root cause of the 404 will resurface"
fi

# ---------------------------------------------------------------------
section "6. No call site uses qwen2.5:32b as a string-value fallback"
# ---------------------------------------------------------------------
# We search for the literal inside *quoted* string contexts only; bare
# mentions in module docstrings or commit/repair-log commentary are
# legitimate forensic markers and must remain readable.
call_sites=(
    "core/mining_guardian.py"
    "ai/local_llm_analyzer.py"
    "ai/daily_deep_dive.py"
    "ai/refinement_chain.py"
    "ai/combine_knowledge.py"
)

bad=0
for f in "${call_sites[@]}"; do
    if grep -E '"qwen2\.5:32b|'"'"'qwen2\.5:32b' "$f" >/dev/null 2>&1; then
        fail "$f still has a quoted qwen2.5:32b literal — see core/ollama_config.py for the env-first replacement"
        bad=1
    fi
done
if [[ $bad -eq 0 ]]; then
    ok "no call site retains a quoted qwen2.5:32b string literal"
fi

# ---------------------------------------------------------------------
section "7. core/ollama_config.py is the single source of truth"
# ---------------------------------------------------------------------
if [[ -r "$OLLAMA_HELPER" ]]; then
    ok "$OLLAMA_HELPER present"
else
    fail "$OLLAMA_HELPER missing — P-031 helper module not in tree"
fi

if grep -q "llama3.2:3b" "$OLLAMA_HELPER"; then
    ok "helper carries the D-13 16 GB default llama3.2:3b"
else
    fail "helper does not pin llama3.2:3b as the D-13 small-tier default"
fi

if grep -q "MG_INSTALL_LLM_MODEL" "$OLLAMA_HELPER"; then
    ok "helper consults MG_INSTALL_LLM_MODEL (the installer-written value)"
else
    fail "helper ignores MG_INSTALL_LLM_MODEL — the installer chain is broken"
fi

# ---------------------------------------------------------------------
echo
echo "================================================================"
echo "Summary: pass=${pass_count} fail=${fail_count}"
echo "================================================================"

if [[ $fail_count -gt 0 ]]; then
    exit 1
fi
exit 0
