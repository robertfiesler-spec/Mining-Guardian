"""
Integration Example — How to wire the CatalogAPIClient into an existing LLM flow.

This is a STANDALONE example showing the wiring pattern. It does NOT modify
any existing files. Bobby will integrate when ready.

Usage pattern:
    1. Before LLM inference, call get_scan_context_bundle() with scan data
    2. Append the returned prompt_text to the existing SYSTEM_PROMPT
    3. Pass the augmented prompt to Ollama/Qwen
    4. If the catalog is unreachable, the system degrades gracefully (empty prompt_text)
"""

import asyncio
import logging
import os

logger = logging.getLogger("catalog-bridge.integration")

# ---------------------------------------------------------------------------
# Example: augment a system prompt with Intelligence Catalog context
# ---------------------------------------------------------------------------

# Your existing system prompt (unchanged)
EXISTING_SYSTEM_PROMPT = """You are a mining operations AI assistant analyzing
Bitcoin SHA-256 miner fleet scan data. Analyze the scan results and provide
actionable recommendations."""


async def augment_prompt_with_catalog(
    miner_models: list[str],
    active_issues: list[str],
    chip_dies: list[str] | None = None,
    firmware_versions: list[str] | None = None,
) -> str:
    """
    Fetch catalog intelligence and append it to the system prompt.

    This function shows how to integrate the catalog bridge into an existing
    LLM inference pipeline. It:
    1. Creates a CatalogAPIClient
    2. Fetches the knowledge bundle for the current scan context
    3. Uses PromptBuilder to format the bundle into prompt text
    4. Appends the prompt text to the existing SYSTEM_PROMPT
    5. Returns the augmented prompt, ready for LLM inference

    If the catalog is unreachable, returns the original prompt unchanged.
    """
    from .client import CatalogAPIClient
    from .prompt_builder import PromptBuilder

    client = CatalogAPIClient(
        base_url=os.getenv("CATALOG_API_URL", "http://100.110.87.1:8420"),
        api_key=os.getenv("CATALOG_API_KEY", ""),
    )
    builder = PromptBuilder()

    try:
        # Fetch the knowledge bundle
        result = await client.get_scan_context_bundle(
            miner_models=miner_models,
            active_issues=active_issues,
            chip_dies=chip_dies or [],
            firmware_versions=firmware_versions or [],
        )

        # The API returns pre-formatted prompt_text; PromptBuilder is the fallback
        prompt_text = builder.build(
            bundle=result.get("context_bundle", {}),
            prompt_text_from_api=result.get("prompt_text", ""),
        )

        if prompt_text:
            augmented = f"{EXISTING_SYSTEM_PROMPT}\n\n{prompt_text}"
            logger.info(
                "Prompt augmented with catalog intelligence (%d chars added, %d sources)",
                len(prompt_text),
                len(result.get("sources", [])),
            )
            return augmented

        logger.info("No catalog intelligence available — using base prompt")
        return EXISTING_SYSTEM_PROMPT

    except Exception as exc:
        # Never let catalog failures break the LLM pipeline
        logger.warning("Catalog bridge error (non-fatal): %s", exc)
        return EXISTING_SYSTEM_PROMPT

    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Example: full scan → LLM flow
# ---------------------------------------------------------------------------

async def example_scan_to_llm_flow():
    """
    Complete example showing how the catalog bridge fits into
    the scan → LLM analysis pipeline.
    """
    # --- Step 1: Data from a real scan (these come from your scan pipeline) ---
    scan_data = {
        "miner_models": ["Antminer S19j Pro"],
        "active_issues": ["RESTART", "TEMP_ACTION_REQUIRED"],
        "chip_dies": ["BM1362AA"],
        "firmware_versions": ["22.08.30"],
    }

    # --- Step 2: Augment the system prompt with catalog intelligence ---
    system_prompt = await augment_prompt_with_catalog(
        miner_models=scan_data["miner_models"],
        active_issues=scan_data["active_issues"],
        chip_dies=scan_data["chip_dies"],
        firmware_versions=scan_data["firmware_versions"],
    )

    # --- Step 3: Call your LLM (Ollama/Qwen) with the augmented prompt ---
    # This is where you'd call your existing LLM inference function.
    # The system_prompt now contains Intelligence Catalog context.
    #
    # Example (pseudo-code — replace with your actual Ollama call):
    #
    # response = await ollama_client.generate(
    #     model="qwen2.5:32b",
    #     system=system_prompt,
    #     prompt=f"Analyze this scan data:\n{json.dumps(scan_data)}",
    # )

    print(f"System prompt length: {len(system_prompt)} chars")
    print(f"First 200 chars:\n{system_prompt[:200]}...")
    return system_prompt


# ---------------------------------------------------------------------------
# Run the example
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(example_scan_to_llm_flow())
