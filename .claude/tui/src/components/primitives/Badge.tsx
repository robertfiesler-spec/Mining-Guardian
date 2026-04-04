import React from "react";
import { Box, Text } from "ink";
import { COLORS, SYMBOLS } from "../../theme/index.js";
import type { AgentStatus } from "../../types/index.js";

interface BadgeProps {
  variant: AgentStatus;
  label?: string;
  showDot?: boolean;
}

const BADGE_COLORS: Record<AgentStatus, string> = {
  active: COLORS.orchestrator.active,
  pending: COLORS.orchestrator.pending,
  completed: COLORS.orchestrator.completed,
  error: COLORS.orchestrator.error,
  idle: COLORS.orchestrator.idle,
};

const BADGE_LABELS: Record<AgentStatus, string> = {
  active: "ACTIVE",
  pending: "PENDING INPUT",
  completed: "COMPLETED",
  error: "ERROR",
  idle: "IDLE",
};

/**
 * Badge component for status indicators
 * New design: "● STATUS" with colored dot and label
 */
export function Badge({ variant, label, showDot = true }: BadgeProps) {
  const color = BADGE_COLORS[variant];
  const displayLabel = label ?? BADGE_LABELS[variant];

  return (
    <Box>
      {showDot && (
        <>
          <Text color={color}>{SYMBOLS.statusDot}</Text>
          <Text> </Text>
        </>
      )}
      <Text color={color}>{displayLabel}</Text>
    </Box>
  );
}

interface StatusDotProps {
  status: AgentStatus;
  showLabel?: boolean;
}

/**
 * Simple status dot indicator
 */
export function StatusDot({ status, showLabel = false }: StatusDotProps) {
  const color = BADGE_COLORS[status];

  return (
    <Box>
      <Text color={color}>●</Text>
      {showLabel && (
        <Text color={color}>
          {" "}
          {status.charAt(0).toUpperCase() + status.slice(1)}
        </Text>
      )}
    </Box>
  );
}

interface ConnectionBadgeProps {
  connected: boolean;
}

/**
 * Connection status badge with dot indicator
 */
export function ConnectionBadge({ connected }: ConnectionBadgeProps) {
  return (
    <Box>
      <Text color={connected ? "green" : "red"}>●</Text>
      <Text color={connected ? "green" : "red"}>
        {" "}
        {connected ? "Connected" : "Disconnected"}
      </Text>
    </Box>
  );
}
