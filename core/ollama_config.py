"""
core/ollama_config.py — P-031 (2026-05-08)

Single source of truth for the Ollama (local LLM) endpoint and model name
that Mining Guardian uses on the customer Mac Mini.

Why this module exists
----------------------
Pre-P-031 every caller — `core/mining_guardian.py`, `ai/local_llm_analyzer.py`,
`ai/daily_deep_dive.py`, `ai/refinement_chain.py`, `ai/combine_knowledge.py`
— resolved the model name on its own, and every one of those resolutions
fell back to a hard-coded `qwen2.5:32b-instruct-q4_K_M`. That model is NOT
pulled by the installer: D-13 says the installer pulls `llama3.2:3b` on
16 GB Minis or `qwen2.5:14b-instruct-q4_K_M` on 24 GB+ Minis based on
detected RAM, and writes the choice to `MG_INSTALL_LLM_MODEL` in the
.env. The fallback never matched what was on disk, so every scan logged:

    Qwen scan analysis failed: HTTP Error 404: Not Found

P-031 collapses the resolution into one helper that every call site uses.

Resolution order (env-first, D-13-aligned defaults)
---------------------------------------------------
Model:
  1. `OLLAMA_MODEL` env var (operator override)
  2. `MG_INSTALL_LLM_MODEL` env var (installer-chosen, written by
     postinstall.sh from detect_ram.sh per D-13)
  3. `llama3.2:3b` — D-13 16 GB default. Picked over the 24 GB pick because
     a wrong-too-small choice on a 24 GB box still resolves to a model that
     was pulled by SOME D-13 install path; a wrong-too-big choice (the old
     32b fallback) resolves to a model that NO D-13 install path pulls.

URL:
  1. `OLLAMA_URL` env var
  2. `http://127.0.0.1:11434/api/generate` — D-9 / S-13 (local-only).

`config.json` integration
-------------------------
`GuardianConfig.from_file` populates `ollama_url` / `ollama_model` from
config.json values when present (resolved through `_resolve` so `env:KEY`
placeholders are expanded). When the keys are absent, this module's
`resolve_*` helpers are used. This is the same env-first chain — config.json
is just a convenience layer for operators who want to pin a value without
editing the .env.
"""

from __future__ import annotations

import os
from typing import Optional

# D-9 / S-13 / P-018E — local Mini Ollama only, no off-host calls.
_DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

# D-13 — 16 GB default. Picked deliberately over the 24 GB pick: see module
# docstring for the rationale (a too-small fallback still hits a real model
# on the 24 GB tier; a too-big fallback hits nothing on the 16 GB tier).
_D13_DEFAULT_MODEL = "llama3.2:3b"


def resolve_ollama_url(explicit: Optional[str] = None) -> str:
    """Return the Ollama /api/generate URL the runtime should call.

    Order: explicit (config.json value) → OLLAMA_URL env → D-9 default.
    """
    if explicit:
        return explicit
    return os.getenv("OLLAMA_URL") or _DEFAULT_OLLAMA_URL


def resolve_ollama_model(explicit: Optional[str] = None) -> str:
    """Return the Ollama model name the runtime should call.

    Order: explicit (config.json value) → OLLAMA_MODEL env →
    MG_INSTALL_LLM_MODEL env → D-13 small-tier default.
    """
    if explicit:
        return explicit
    return (
        os.getenv("OLLAMA_MODEL")
        or os.getenv("MG_INSTALL_LLM_MODEL")
        or _D13_DEFAULT_MODEL
    )
