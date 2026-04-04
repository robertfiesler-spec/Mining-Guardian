import React from "react";
import { Box, Text } from "ink";
import { SectionHeader } from "./SectionHeader.js";
import { getActivityIcon, getActivityColor } from "../theme.js";

interface ActivityLogEntry {
  timestamp: string;
  type: string;
  message: string;
}

interface ActivityLogProps {
  activityLog: ActivityLogEntry[];
}

export function ActivityLog({ activityLog }: ActivityLogProps) {
  if (activityLog.length === 0) {
    return null;
  }

  return (
    <Box marginTop={1} flexDirection="column">
      <SectionHeader title="Activity" />

      <Box marginTop={1} flexDirection="column">
        {activityLog
          .slice(-5)
          .reverse()
          .map((activity, idx) => (
            <Box key={idx}>
              <Text dimColor>{formatTime(activity.timestamp)}</Text>
              <Text>{"  "}</Text>
              <Text color={getActivityColor(activity.type)}>
                {getActivityIcon(activity.type)}
              </Text>
              <Text> </Text>
              <Text>
                {activity.type === "story_started" ? "Started: " : ""}
                {activity.type === "story_completed" ? "Completed: " : ""}
                {activity.message}
              </Text>
            </Box>
          ))}
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
