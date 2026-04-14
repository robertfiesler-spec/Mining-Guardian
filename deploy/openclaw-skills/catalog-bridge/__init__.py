"""
OpenClaw Catalog Bridge — Phase 1 (READ path)

Async client for querying the Mining Intelligence Catalog API
and formatting knowledge bundles for LLM system prompt injection.
"""

from .client import CatalogAPIClient
from .prompt_builder import PromptBuilder

__all__ = ["CatalogAPIClient", "PromptBuilder"]
