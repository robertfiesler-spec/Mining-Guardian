import React from "react";
import { Box, Text } from "ink";
import { SYMBOLS, COLORS } from "../theme.js";

interface DotProgressProps {
  completed: number;
  total: number;
  width?: number;
}

export function DotProgress({
  completed,
  total,
  width = 12,
}: DotProgressProps) {
  const ratio = total > 0 ? Math.min(completed / total, 1) : 0;
  const filled = Math.round(ratio * width);
  const empty = Math.max(0, width - filled);
  const percentage = total > 0 ? Math.round((completed / total) * 100) : 0;

  return (
    <Box flexDirection="row" justifyContent="space-between">
      <Text>
        <Text color={COLORS.success}>{SYMBOLS.dotFilled.repeat(filled)}</Text>
        <Text color={COLORS.dimmed}>{SYMBOLS.dotEmpty.repeat(empty)}</Text>
      </Text>
      <Text>
        {completed}/{total} ({percentage}%)
      </Text>
    </Box>
  );
}
