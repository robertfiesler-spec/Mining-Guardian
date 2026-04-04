import React from "react";
import { Box, Text, useInput } from "ink";
import type { SessionState } from "../hooks/useSession.js";
import { SectionHeader } from "./SectionHeader.js";
import { Divider } from "./Divider.js";
import { getStatusColor, COLORS } from "../theme.js";

interface StatusViewerProps {
  session: SessionState;
  onClose: () => void;
}

export function StatusViewer({ session, onClose }: StatusViewerProps) {
  useInput((input, key) => {
    if (input === "s" || key.escape) {
      onClose();
    }
  });

  const elapsedTime = getElapsedTime(session.execution.start_time);
  const progressPercent =
    session.progress.total_stories > 0
      ? Math.round(
          (session.progress.completed / session.progress.total_stories) * 100,
        )
      : 0;

  return (
    <Box flexDirection="column" padding={1}>
      <Text bold>SESSION STATUS</Text>
      <Divider />

      {/* Session Info */}
      <Box marginTop={1} flexDirection="column">
        <SectionHeader title="Session" />
        <Box marginTop={1} flexDirection="row" justifyContent="space-between">
          <Text>
            Version: <Text color={COLORS.primary}>{session.version}</Text>
          </Text>
          <Text>
            Status:{" "}
            <Text color={getStatusColor(session.status)}>
              {session.status.toUpperCase()}
            </Text>
          </Text>
        </Box>
        <Box flexDirection="row" justifyContent="space-between">
          <Text dimColor>Created: {formatDateTime(session.created_at)}</Text>
          <Text dimColor>Updated: {formatDateTime(session.updated_at)}</Text>
        </Box>
      </Box>

      {/* Plan Info */}
      <Box marginTop={1} flexDirection="column">
        <SectionHeader title="Plan" />
        <Box marginTop={1} flexDirection="row" justifyContent="space-between">
          <Text>
            Name: <Text color={COLORS.primary}>{session.plan.name}</Text>
          </Text>
          <Text>
            Branch: <Text color={COLORS.primary}>{session.plan.branch}</Text>
          </Text>
        </Box>
        <Text dimColor>Path: {session.plan.path}</Text>
      </Box>

      {/* Progress */}
      <Box marginTop={1} flexDirection="column">
        <SectionHeader title="Progress" />
        <Box marginTop={1} flexDirection="row" justifyContent="space-between">
          <Text>
            Stories:{" "}
            <Text color={COLORS.success}>{session.progress.completed}</Text>
            <Text>/</Text>
            <Text>{session.progress.total_stories}</Text>
            <Text dimColor> ({progressPercent}%)</Text>
          </Text>
          <Text>
            Iteration:{" "}
            <Text color={COLORS.primary}>
              {session.progress.current_iteration}
            </Text>
          </Text>
        </Box>
        <Text>
          Current:{" "}
          <Text color={COLORS.current}>
            {session.progress.current_story || "None"}
          </Text>
        </Text>
      </Box>

      {/* Git Info */}
      <Box marginTop={1} flexDirection="column">
        <SectionHeader title="Git" />
        <Box marginTop={1} flexDirection="row" justifyContent="space-between">
          <Text>
            Branch: <Text color={COLORS.primary}>{session.git.branch}</Text>
          </Text>
          <Text>
            Modified:{" "}
            <Text color={COLORS.primary}>
              {session.git.modified_files.length}
            </Text>{" "}
            files
          </Text>
        </Box>
        <Text dimColor>HEAD: {session.git.head_commit || "N/A"}</Text>
        {session.git.modified_files.slice(0, 3).map((file) => (
          <Text key={file} dimColor>
            {"  "}
            {file}
          </Text>
        ))}
        {session.git.modified_files.length > 3 && (
          <Text dimColor>
            {"  "}... and {session.git.modified_files.length - 3} more
          </Text>
        )}
      </Box>

      {/* Execution */}
      <Box marginTop={1} flexDirection="column">
        <SectionHeader title="Execution" />
        <Box marginTop={1} flexDirection="row" justifyContent="space-between">
          <Text>
            Mode:{" "}
            <Text color={COLORS.primary}>
              {session.execution.mode.toUpperCase()}
            </Text>
          </Text>
          <Text>
            Elapsed: <Text color={COLORS.primary}>{elapsedTime}</Text>
          </Text>
        </Box>
        <Box flexDirection="row" justifyContent="space-between">
          <Text dimColor>PID: {session.execution.pid}</Text>
          <Text dimColor>
            Started: {formatDateTime(session.execution.start_time)}
          </Text>
        </Box>
      </Box>

      <Box marginTop={1} flexDirection="column">
        <Divider />
        <Text dimColor>[s/Esc] Close</Text>
      </Box>
    </Box>
  );
}

function formatDateTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function getElapsedTime(startTime: string): string {
  const start = new Date(startTime).getTime();
  const now = Date.now();
  const diffMs = now - start;

  const hours = Math.floor(diffMs / (1000 * 60 * 60));
  const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
  const seconds = Math.floor((diffMs % (1000 * 60)) / 1000);

  return `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
}
