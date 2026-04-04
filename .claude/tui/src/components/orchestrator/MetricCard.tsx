import React from "react";
import { Box, Text } from "ink";
import { SYMBOLS, COLORS } from "../../theme/index.js";
import { getCostDeltaColor } from "../../theme/colors.js";

interface MetricCardProps {
  title: string;
  value: string;
  delta?: number;
  deltaPrefix?: string;
  width?: number;
  icon?: string;
}

/**
 * Metric card for cost/session displays
 * Design: icon + label on top, value + delta below
 */
export function MetricCard({
  title,
  value,
  delta,
  deltaPrefix = "",
  width = 20,
  icon,
}: MetricCardProps) {
  const innerWidth = width - 2;
  const horizontalLine = SYMBOLS.box.horizontal.repeat(innerWidth);
  const borderColor = COLORS.orchestrator.cardBorder;

  // Format delta
  let deltaDisplay = "";
  let deltaColor: string = COLORS.orchestrator.costNeutral;

  if (delta !== undefined && delta !== 0) {
    const sign = delta > 0 ? "+" : "";
    const formattedDelta = Math.abs(delta).toFixed(delta < 10 ? 2 : 0);
    deltaDisplay = `${sign}${deltaPrefix}${formattedDelta}`;
    deltaColor = getCostDeltaColor(delta);
  }

  // Default icons based on title
  const displayIcon =
    icon ??
    (title.toLowerCase().includes("session")
      ? SYMBOLS.icons.sessions
      : title.toLowerCase().includes("day")
        ? SYMBOLS.icons.calendar
        : SYMBOLS.icons.dollar);

  return (
    <Box flexDirection="column" marginRight={1}>
      {/* Top border */}
      <Box>
        <Text color={borderColor}>{SYMBOLS.box.topLeft}</Text>
        <Text color={borderColor}>{horizontalLine}</Text>
        <Text color={borderColor}>{SYMBOLS.box.topRight}</Text>
      </Box>

      {/* Icon + Title row */}
      <Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
        <Box width={innerWidth} paddingLeft={1}>
          <Text color={COLORS.orchestrator.metricIcon}>{displayIcon}</Text>
          <Text> </Text>
          <Text color={COLORS.orchestrator.metricLabel}>
            {title.toUpperCase()}
          </Text>
        </Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
      </Box>

      {/* Value + Delta row */}
      <Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
        <Box width={innerWidth} paddingLeft={1}>
          <Text bold color={COLORS.orchestrator.metricValue}>
            {value}
          </Text>
          {deltaDisplay && (
            <>
              <Text> </Text>
              <Text color={deltaColor}>{deltaDisplay}</Text>
            </>
          )}
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
