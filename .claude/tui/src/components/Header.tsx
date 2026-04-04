import React from "react";
import { Box, Text } from "ink";
import { Divider } from "./Divider.js";
import { getModeColor, type ExecutionMode } from "../theme.js";

interface HeaderProps {
  mode: ExecutionMode;
  startTime: string;
}

export function Header({ mode, startTime }: HeaderProps) {
  const elapsed = getElapsedTime(startTime);
  const modeLabel = mode === "autonomous" ? "AUTONOMOUS" : "ATTENDED";
  const modeColor = getModeColor(mode);

  return (
    <Box flexDirection="column">
      <Box flexDirection="row" justifyContent="space-between">
        <Text bold>AI TOOLKIT</Text>
        <Box>
          <Text color={modeColor}>{modeLabel}</Text>
          <Text>{"  "}</Text>
          <Text dimColor>{elapsed}</Text>
        </Box>
      </Box>
      <Divider />
    </Box>
  );
}

function getElapsedTime(startTime: string): string {
  const start = new Date(startTime);
  const now = new Date();
  const diffMs = now.getTime() - start.getTime();

  const hours = Math.floor(diffMs / (1000 * 60 * 60));
  const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
  const seconds = Math.floor((diffMs % (1000 * 60)) / 1000);

  return `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
}
