import React from "react";
import { Box, Text } from "ink";
import { SYMBOLS, COLORS } from "../../theme/index.js";

interface SummaryCardProps {
  title: string;
  count: number;
  color: string;
  width?: number;
  maxDots?: number;
}

/**
 * Summary card for agent counts with dot indicators
 */
export function SummaryCard({
  title,
  count,
  color,
  width = 22,
  maxDots = 10,
}: SummaryCardProps) {
  const innerWidth = width - 2;
  const horizontalLine = SYMBOLS.box.horizontal.repeat(innerWidth);
  const borderColor = COLORS.orchestrator.cardBorder;

  // Generate dot indicators (max 10 dots)
  const dotCount = Math.min(count, maxDots);
  const dots = SYMBOLS.dotFilled.repeat(dotCount);

  return (
    <Box flexDirection="column" marginRight={1}>
      {/* Top border */}
      <Box>
        <Text color={borderColor}>{SYMBOLS.box.topLeft}</Text>
        <Text color={borderColor}>{horizontalLine}</Text>
        <Text color={borderColor}>{SYMBOLS.box.topRight}</Text>
      </Box>

      {/* Status dot and title */}
      <Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
        <Box width={innerWidth} paddingLeft={1}>
          <Text color={color}>{SYMBOLS.statusDot}</Text>
          <Text> </Text>
          <Text color={COLORS.textSecondary}>{title.toUpperCase()}</Text>
        </Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
      </Box>

      {/* Count + Dot indicators */}
      <Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
        <Box width={innerWidth} paddingLeft={1} justifyContent="space-between">
          <Text bold color={COLORS.textPrimary}>
            {count}
          </Text>
          <Box paddingRight={1}>
            <Text color={color}>{dots}</Text>
          </Box>
        </Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
      </Box>

      {/* Bottom border */}
      <Box>
        <Text color={borderColor}>{SYMBOLS.box.bottomLeft}</Text>
        <Text color={borderColor}>{horizontalLine}</Text>
        <Text color={borderColor}>{SYMBOLS.box.bottomRight}</Text>
      </Box>
    </Box>
  );
}
