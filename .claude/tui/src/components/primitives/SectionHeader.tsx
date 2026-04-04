import React from "react";
import { Box, Text } from "ink";
import { SYMBOLS, COLORS } from "../../theme/index.js";

interface SectionHeaderProps {
  title: string;
  count?: number;
  width?: number;
}

/**
 * Section header with "─ TITLE ─" style
 * Used for Cost Metrics, Active Agents, Agent Registry sections
 */
export function SectionHeader({
  title,
  count,
  width = 80,
}: SectionHeaderProps) {
  const displayTitle = count !== undefined ? `${title} (${count})` : title;
  // Calculate padding: "─ " + title + " " + remaining dashes
  const prefixLength = 2; // "─ "
  const suffixLength = 1; // " " before trailing dashes
  const titleLength = displayTitle.length;
  const remainingDashes = Math.max(
    0,
    width - prefixLength - titleLength - suffixLength - 1,
  );

  return (
    <Box marginTop={1} marginBottom={0}>
      <Text color={COLORS.orchestrator.sectionBorder}>{SYMBOLS.divider}</Text>
      <Text color={COLORS.orchestrator.sectionBorder}> </Text>
      <Text color={COLORS.orchestrator.sectionTitle} bold>
        {displayTitle}
      </Text>
      <Text color={COLORS.orchestrator.sectionBorder}> </Text>
      <Text color={COLORS.orchestrator.sectionBorder}>
        {SYMBOLS.divider.repeat(remainingDashes)}
      </Text>
    </Box>
  );
}
