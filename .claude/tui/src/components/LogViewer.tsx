import React, { useState, useEffect } from "react";
import { Box, Text, useInput } from "ink";
import { Divider } from "./Divider.js";
import { getActivityIcon, getActivityColor, COLORS } from "../theme.js";

interface ActivityLogEntry {
  timestamp: string;
  type: string;
  story: string;
  message: string;
}

interface LogViewerProps {
  activityLog: ActivityLogEntry[];
  onClose: () => void;
}

const VISIBLE_LINES = 15;

export function LogViewer({ activityLog, onClose }: LogViewerProps) {
  const [scrollOffset, setScrollOffset] = useState(0);

  // Start at bottom (most recent)
  useEffect(() => {
    const maxOffset = Math.max(0, activityLog.length - VISIBLE_LINES);
    setScrollOffset(maxOffset);
  }, [activityLog.length]);

  useInput((input, key) => {
    if (input === "l" || key.escape) {
      onClose();
      return;
    }

    if (key.upArrow) {
      setScrollOffset((prev) => Math.max(0, prev - 1));
    } else if (key.downArrow) {
      setScrollOffset((prev) =>
        Math.min(Math.max(0, activityLog.length - VISIBLE_LINES), prev + 1),
      );
    } else if (key.pageUp) {
      setScrollOffset((prev) => Math.max(0, prev - VISIBLE_LINES));
    } else if (key.pageDown) {
      setScrollOffset((prev) =>
        Math.min(
          Math.max(0, activityLog.length - VISIBLE_LINES),
          prev + VISIBLE_LINES,
        ),
      );
    }
  });

  const visibleLogs = activityLog.slice(
    scrollOffset,
    scrollOffset + VISIBLE_LINES,
  );

  const totalLogs = activityLog.length;
  const currentPosition =
    totalLogs === 0
      ? "0/0"
      : `${scrollOffset + 1}-${Math.min(scrollOffset + VISIBLE_LINES, totalLogs)}/${totalLogs}`;

  return (
    <Box flexDirection="column" padding={1}>
      <Box flexDirection="row" justifyContent="space-between">
        <Text bold>ACTIVITY LOG</Text>
        <Text dimColor>({currentPosition})</Text>
      </Box>
      <Divider />

      <Box flexDirection="column" marginTop={1} height={VISIBLE_LINES}>
        {visibleLogs.length === 0 ? (
          <Text dimColor>No activity yet</Text>
        ) : (
          visibleLogs.map((entry, idx) => (
            <Box key={scrollOffset + idx}>
              <Text dimColor>{formatTime(entry.timestamp)}</Text>
              <Text>{"  "}</Text>
              <Text color={getActivityColor(entry.type)}>
                {getActivityIcon(entry.type)}
              </Text>
              <Text> </Text>
              {entry.story && (
                <>
                  <Text color={COLORS.primary}>[{entry.story}]</Text>
                  <Text> </Text>
                </>
              )}
              <Text>{entry.message}</Text>
            </Box>
          ))
        )}
      </Box>

      <Box marginTop={1} flexDirection="column">
        <Divider />
        <Text dimColor>[Up/Down] Scroll [PgUp/PgDn] Page [l/Esc] Close</Text>
      </Box>
    </Box>
  );
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}
