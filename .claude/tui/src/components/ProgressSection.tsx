import React from "react";
import { Box, Text } from "ink";
import { SectionHeader } from "./SectionHeader.js";
import { DotProgress } from "./DotProgress.js";
import { COLORS, type ExecutionMode } from "../theme.js";

interface ProgressSectionProps {
  totalStories: number;
  completed: number;
  currentStory: string | null;
  currentIteration: number;
  mode?: ExecutionMode;
}

export function ProgressSection({
  totalStories,
  completed,
  currentStory,
  currentIteration,
  mode = "autonomous",
}: ProgressSectionProps) {
  // Use mode-appropriate terminology
  const unitLabel = mode === "attended" ? "Items" : "Stories";
  const currentLabel = mode === "attended" ? "Current Item" : "Current";

  return (
    <Box marginTop={1} flexDirection="column">
      <SectionHeader title="Progress" />

      <Box marginTop={1}>
        <DotProgress completed={completed} total={totalStories} />
      </Box>

      <Box marginTop={1} flexDirection="row" justifyContent="space-between">
        <Text>
          {unitLabel}: {completed}/{totalStories}
        </Text>
        {mode === "autonomous" && <Text>Iteration: {currentIteration}</Text>}
        {mode === "attended" && currentIteration > 0 && (
          <Text>Batch: {currentIteration}</Text>
        )}
      </Box>

      {currentStory && (
        <Text>
          {currentLabel}: <Text color={COLORS.current}>{currentStory}</Text>
        </Text>
      )}
    </Box>
  );
}
