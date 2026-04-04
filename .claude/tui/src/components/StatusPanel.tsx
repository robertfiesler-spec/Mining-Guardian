import React from "react";
import { Box, Text } from "ink";
import { SectionHeader } from "./SectionHeader.js";
import { getStatusColor } from "../theme.js";

interface StatusPanelProps {
  status: "running" | "paused" | "complete" | "crashed";
  planName: string;
  branch: string;
  modifiedFiles: string[];
}

export function StatusPanel({
  status,
  planName,
  branch,
  modifiedFiles,
}: StatusPanelProps) {
  return (
    <Box marginTop={1} flexDirection="column">
      <SectionHeader title="Status" />

      <Box marginTop={1} flexDirection="row" justifyContent="space-between">
        <Text>
          State:{" "}
          <Text color={getStatusColor(status)}>{status.toUpperCase()}</Text>
        </Text>
        <Text>Plan: {planName}</Text>
      </Box>

      <Box flexDirection="row" justifyContent="space-between">
        <Text>Branch: {branch}</Text>
        <Text>Modified: {modifiedFiles.length} files</Text>
      </Box>
    </Box>
  );
}
