import React from "react";
import { Box, Text } from "ink";
import { SYMBOLS, COLORS } from "../../theme/index.js";
import { getContextBarColor } from "../../theme/colors.js";
import { formatPercent, formatContextSize } from "../../utils/format.js";

interface ContextBarProps {
  used: number;
  total: number;
  width?: number;
  showLabel?: boolean;
  showPercentage?: boolean;
  showValues?: boolean;
  label?: string;
}

/**
 * Context usage progress bar
 * Shows filled/empty segments based on usage percentage
 * Uses yellow/amber color scheme to match mockup
 */
export function ContextBar({
  used,
  total,
  width = 20,
  showLabel = false,
  showPercentage = true,
  showValues = false,
  label = "CONTEXT",
}: ContextBarProps) {
  const ratio = total > 0 ? Math.min(used / total, 1) : 0;
  const percentage = ratio * 100;
  const filledWidth = Math.round(ratio * width);
  const emptyWidth = Math.max(0, width - filledWidth);
  const color = getContextBarColor(percentage);

  const filledBar = SYMBOLS.progressBar.filled.repeat(filledWidth);
  const emptyBar = SYMBOLS.progressBar.empty.repeat(emptyWidth);

  return (
    <Box>
      {showLabel && (
        <>
          <Text color={COLORS.textSecondary}>{SYMBOLS.icons.context}</Text>
          <Text> </Text>
          <Text color={COLORS.textSecondary}>{label}</Text>
          <Text> </Text>
        </>
      )}
      <Text color={color}>{filledBar}</Text>
      <Text color={COLORS.orchestrator.contextEmpty}>{emptyBar}</Text>
      {showValues && (
        <Text color={COLORS.textSecondary}>
          {" "}
          {formatContextSize(used)} / {formatContextSize(total)}
        </Text>
      )}
      {showPercentage && (
        <Text color={COLORS.textSecondary}> {formatPercent(percentage)}</Text>
      )}
    </Box>
  );
}

interface MiniBarProps {
  value: number;
  max: number;
  width?: number;
  color?: string;
}

/**
 * Minimal progress bar without labels
 */
export function MiniBar({
  value,
  max,
  width = 10,
  color = "cyan",
}: MiniBarProps) {
  const ratio = max > 0 ? Math.min(value / max, 1) : 0;
  const filledWidth = Math.round(ratio * width);
  const emptyWidth = Math.max(0, width - filledWidth);

  return (
    <Box>
      <Text color={color}>
        {SYMBOLS.progressBar.filled.repeat(filledWidth)}
      </Text>
      <Text color="gray">{SYMBOLS.progressBar.empty.repeat(emptyWidth)}</Text>
    </Box>
  );
}

interface LabeledProgressProps {
  label: string;
  value: number;
  max: number;
  width?: number;
  valueLabel?: string;
}

/**
 * Progress bar with label and value display
 */
export function LabeledProgress({
  label,
  value,
  max,
  width = 15,
  valueLabel,
}: LabeledProgressProps) {
  const ratio = max > 0 ? Math.min(value / max, 1) : 0;
  const percentage = ratio * 100;
  const filledWidth = Math.round(ratio * width);
  const emptyWidth = Math.max(0, width - filledWidth);
  const color = getContextBarColor(percentage);

  return (
    <Box flexDirection="row">
      <Box width={8}>
        <Text dimColor>{label}</Text>
      </Box>
      <Text color={color}>
        {SYMBOLS.progressBar.filled.repeat(filledWidth)}
      </Text>
      <Text color="gray">{SYMBOLS.progressBar.empty.repeat(emptyWidth)}</Text>
      <Text dimColor> {valueLabel ?? formatPercent(percentage)}</Text>
    </Box>
  );
}
