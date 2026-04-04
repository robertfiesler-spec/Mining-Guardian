import React from "react";
import { Box, Text } from "ink";
import { SYMBOLS, COLORS } from "../../theme/index.js";
import type { ConnectionStatus, DataMode } from "../../types/index.js";

interface OrchestratorHeaderProps {
  version: string;
  connection: ConnectionStatus;
  time: string;
  mode: DataMode;
}

/**
 * Header component with title, version, connection status, and clock
 * Simple single-line design matching mockup
 */
export function OrchestratorHeader({
  version,
  connection,
  time,
  mode,
}: OrchestratorHeaderProps) {
  const isConnected = connection === "connected";
  const connectionColor = isConnected
    ? COLORS.orchestrator.connectionOk
    : connection === "reconnecting"
      ? "yellow"
      : COLORS.orchestrator.connectionError;

  const connectionLabel = connection.toUpperCase();

  return (
    <Box flexDirection="row" justifyContent="space-between">
      {/* Left side: Icon + Title + Version */}
      <Box>
        <Text color={COLORS.orchestrator.headerTitle}>{SYMBOLS.icons.app}</Text>
        <Text> </Text>
        <Text bold color={COLORS.orchestrator.headerTitle}>
          AGENT ORCHESTRATOR
        </Text>
        <Text> </Text>
        <Text color={COLORS.orchestrator.headerVersion}>v{version}</Text>
        {mode === "mock" && (
          <>
            <Text> </Text>
            <Text color="yellow">[MOCK]</Text>
          </>
        )}
      </Box>

      {/* Right side: Connection status + Time */}
      <Box>
        <Text color={connectionColor}>{SYMBOLS.icons.connection}</Text>
        <Text> </Text>
        <Text color={connectionColor}>{connectionLabel}</Text>
        <Text> </Text>
        <Text color={COLORS.orchestrator.timestamp}>{time}</Text>
      </Box>
    </Box>
  );
}
