"""
Prompt Builder — formats Intelligence Catalog bundles into LLM prompt text.

Backup formatter for the VPS side. The Catalog API returns pre-formatted
prompt_text, but if that field is missing or empty this module can build it
from the raw context_bundle.

Priority-ranked sections (token budget ~2300 tokens / ~9200 chars):
1. Active issue failure patterns (800 tokens max)
2. Model specs + baselines (400 tokens)
3. Firmware guidance (200 tokens)
4. Environmental context (200 tokens)
5. Repair notes (300 tokens)
6. General background (400 tokens)
"""

import json
import logging
from typing import Any

logger = logging.getLogger("catalog-bridge.prompt_builder")

# Approximate: 1 token ≈ 4 chars
MAX_CHARS = 9200


class PromptBuilder:
    """Formats a context_bundle dict into LLM-ready prompt text."""

    def __init__(self, char_budget: int = MAX_CHARS):
        self.char_budget = char_budget

    def build(self, bundle: dict[str, Any], prompt_text_from_api: str = "") -> str:
        """
        Return prompt text for LLM injection.

        If the API already provided prompt_text and it's non-empty, use that.
        Otherwise, build from the raw context_bundle.
        """
        if prompt_text_from_api and len(prompt_text_from_api) > 50:
            logger.info("Using pre-formatted prompt text from API (%d chars)", len(prompt_text_from_api))
            return prompt_text_from_api

        logger.info("Building prompt text from raw bundle")
        return self._build_from_bundle(bundle)

    def _build_from_bundle(self, bundle: dict[str, Any]) -> str:
        """Build prompt text from a raw context bundle."""
        sections: list[str] = []
        used = 0

        def add(title: str, content: str, max_chars: int) -> None:
            nonlocal used
            remaining = self.char_budget - used
            allowed = min(max_chars, remaining)
            if allowed <= 0 or not content.strip():
                return
            text = f"\n### {title}\n{content[:allowed]}"
            sections.append(text)
            used += len(text)

        # 1. Failure patterns (~3200 chars)
        add("Known Failure Patterns",
            self._format_failure_patterns(bundle.get("failure_patterns", [])),
            3200)

        # 2. Model specs + baselines (~1600 chars)
        add("Model Specs & Baselines",
            self._format_model_specs(bundle),
            1600)

        # 3. Firmware guidance (~800 chars)
        add("Firmware Intelligence",
            self._format_firmware(bundle.get("firmware", {})),
            800)

        # 4. Environmental context (~800 chars)
        add("Environmental Context",
            self._format_environmental(bundle),
            800)

        # 5. Repair notes (~1200 chars)
        add("Repair Procedures",
            self._format_repair(bundle.get("repair", {})),
            1200)

        # 6. Chip specs (remaining)
        add("Chip Specifications",
            self._format_chips(bundle.get("chip_specs", [])),
            800)

        if not sections:
            return ""

        header = ("## Intelligence Catalog Context\n"
                  "The following knowledge is from the Mining Intelligence Catalog "
                  "and should inform your analysis:\n")
        return header + "".join(sections)

    def _format_failure_patterns(self, patterns: list[dict]) -> str:
        """Format failure pattern entries."""
        lines = []
        for fp in patterns[:15]:
            name = fp.get("failure_mode") or fp.get("name") or fp.get("signature_type") or "Unknown"
            desc = fp.get("description") or fp.get("root_cause") or ""
            severity = fp.get("severity") or fp.get("risk_level") or ""
            line = f"- **{name}**"
            if severity:
                line += f" [{severity}]"
            if desc:
                line += f": {self._safe_str(desc)}"
            lines.append(line)
        return "\n".join(lines)

    def _format_model_specs(self, bundle: dict) -> str:
        """Format model specs and baselines."""
        parts = []

        models = bundle.get("matched_models", [])
        if models:
            model_lines = []
            for m in models[:5]:
                name = m.get("model_name") or m.get("name") or "Unknown"
                hashrate = m.get("hashrate_th") or m.get("hashrate") or "?"
                power = m.get("power_consumption_w") or m.get("power_w") or "?"
                chip = m.get("chip_name") or m.get("asic_chip") or "?"
                model_lines.append(f"- **{name}**: {hashrate} TH/s, {power}W, chip: {chip}")
            parts.append("**Models:**\n" + "\n".join(model_lines))

        baselines = bundle.get("thresholds", {}).get("baselines", [])
        if baselines:
            bl_lines = []
            for b in baselines[:5]:
                metric = b.get("metric_name") or b.get("parameter") or "metric"
                expected = b.get("expected_value") or b.get("baseline_value") or "?"
                bl_lines.append(f"- {metric}: {expected}")
            parts.append("**Baselines:**\n" + "\n".join(bl_lines))

        return "\n".join(parts)

    def _format_firmware(self, fw_data: dict) -> str:
        """Format firmware data."""
        lines = []
        for v in fw_data.get("versions", [])[:5]:
            ver = v.get("version") or v.get("firmware_version") or "?"
            status = v.get("status") or v.get("stability_rating") or ""
            lines.append(f"- v{ver}" + (f" ({status})" if status else ""))
        for bug in fw_data.get("bugs", [])[:3]:
            desc = bug.get("description") or bug.get("bug_description") or "bug"
            lines.append(f"- BUG: {self._safe_str(desc)[:150]}")
        return "\n".join(lines)

    def _format_environmental(self, bundle: dict) -> str:
        """Format environmental and threshold data."""
        lines = []
        env = bundle.get("environmental", {})
        for s in env.get("safety_systems", [])[:3]:
            name = s.get("system_name") or s.get("name") or "system"
            lines.append(f"- {name}")
        for c in env.get("cooling_specs", [])[:3]:
            name = c.get("cooling_type") or c.get("name") or "cooling"
            lines.append(f"- Cooling: {name}")
        for t in bundle.get("thresholds", {}).get("env_matrix", [])[:3]:
            param = t.get("parameter") or t.get("metric") or "param"
            val = t.get("threshold_value") or t.get("max_value") or "?"
            lines.append(f"- {param}: {val}")
        return "\n".join(lines)

    def _format_repair(self, repair_data: dict) -> str:
        """Format repair procedures."""
        lines = []
        for proc in repair_data.get("procedures", [])[:5]:
            title = proc.get("procedure_name") or proc.get("title") or "Procedure"
            steps = proc.get("steps") or proc.get("procedure_steps") or ""
            line = f"- **{title}**"
            if steps:
                line += f": {self._safe_str(steps)[:200]}"
            lines.append(line)
        return "\n".join(lines)

    def _format_chips(self, chips: list[dict]) -> str:
        """Format chip specification entries."""
        lines = []
        for c in chips[:5]:
            name = c.get("chip_name") or c.get("name") or "chip"
            process = c.get("process_node") or c.get("process_nm") or "?"
            lines.append(f"- {name}: {process}nm process")
        return "\n".join(lines)

    @staticmethod
    def _safe_str(val: Any) -> str:
        """Safely convert a value to string."""
        if val is None:
            return "N/A"
        if isinstance(val, (dict, list)):
            return json.dumps(val, default=str)
        return str(val)
