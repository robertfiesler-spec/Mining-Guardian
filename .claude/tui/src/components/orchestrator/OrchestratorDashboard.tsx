import React from "react";
import { Box, Text } from "ink";
import { OrchestratorHeader } from "./OrchestratorHeader.js";
import { MetricsRow } from "./MetricsRow.js";
import { AgentSummaryRow } from "./AgentSummaryRow.js";
import { AgentRegistryGrid } from "./AgentRegistryGrid.js";
import { OrchestratorFooter } from "./OrchestratorFooter.js";
import { SYMBOLS } from "../../theme/index.js";
import type { OrchestratorState, DataMode } from "../../types/index.js";

interface OrchestratorDashboardProps {
  state: OrchestratorState;
  time: string;
  mode: DataMode;
  selectedAgentId?: string;
  isPaused?: boolean;
}

/**
 * Main orchestrator dashboard container
 * Composes all orchestrator sections
 */
export function OrchestratorDashboard({
  state,
  time,
  mode,
  selectedAgentId,
  isPaused = false,
}: OrchestratorDashboardProps) {
  return (
    <Box flexDirection="column" padding={1}>
      {/* Header */}
      <OrchestratorHeader
        version={state.config.version}
        connection={state.connection}
        time={time}
        mode={mode}
      />

      {/* Cost Metrics Row */}
      <MetricsRow costs={state.costs} />

      {/* Agent Summary Row */}
      <AgentSummaryRow registry={state.registry} />

      {/* Agent Registry Grid */}
      <AgentRegistryGrid
        registry={state.registry}
        columns={2}
        maxVisible={6}
        selectedAgentId={selectedAgentId}
      />

      {/* Footer */}
      <OrchestratorFooter system={state.system} isPaused={isPaused} />
    </Box>
  );
}

interface LoadingStateProps {
  message?: string;
}

/**
 * Loading state for orchestrator dashboard
 */
export function OrchestratorLoading({
  message = "Loading...",
}: LoadingStateProps) {
  return (
    <Box flexDirection="column" padding={1}>
      <Text bold color="cyan">
        AGENT ORCHESTRATOR
      </Text>
      <Box marginTop={1}>
        <Text color="yellow">
          {SYMBOLS.bullet} {message}
        </Text>
      </Box>
    </Box>
  );
}

interface ErrorStateProps {
  error: string;
  onRetry?: () => void;
}

/**
 * Error state for orchestrator dashboard
 */
export function OrchestratorError({ error }: ErrorStateProps) {
  return (
    <Box flexDirection="column" padding={1}>
      <Text bold color="cyan">
        AGENT ORCHESTRATOR
      </Text>
      <Box marginTop={1} flexDirection="column">
        <Text color="red">
          {SYMBOLS.error} Error: {error}
        </Text>
      </Box>
      <Box marginTop={1}>
        <Text dimColor>Press R to retry, Q to quit</Text>
      </Box>
    </Box>
  );
}
