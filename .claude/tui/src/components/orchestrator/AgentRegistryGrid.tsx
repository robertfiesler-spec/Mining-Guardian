import React from "react";
import { Box, Text } from "ink";
import { AgentCard } from "./AgentCard.js";
import { Grid } from "../primitives/Grid.js";
import { SectionHeader } from "../primitives/SectionHeader.js";
import { COLORS } from "../../theme/index.js";
import type { AgentRegistry } from "../../types/index.js";

interface AgentRegistryGridProps {
  registry: AgentRegistry;
  columns?: number;
  maxVisible?: number;
  selectedAgentId?: string;
}

/**
 * Grid of agent cards with section header
 */
export function AgentRegistryGrid({
  registry,
  columns = 3,
  maxVisible = 8,
  selectedAgentId,
}: AgentRegistryGridProps) {
  const { agents } = registry;

  if (agents.length === 0) {
    return (
      <Box flexDirection="column">
        <SectionHeader title="AGENT REGISTRY" count={0} />
        <Box marginTop={1} paddingLeft={2}>
          <Text color={COLORS.textSecondary}>
            No agents registered. Start a task to see agents here.
          </Text>
        </Box>
      </Box>
    );
  }

  // Sort agents: active first, then pending, then completed, then error
  const sortOrder = { active: 0, pending: 1, completed: 2, idle: 3, error: 4 };
  const sortedAgents = [...agents].sort(
    (a, b) => sortOrder[a.status] - sortOrder[b.status],
  );

  const visibleAgents = sortedAgents.slice(0, maxVisible);
  const hiddenCount = agents.length - maxVisible;

  return (
    <Box flexDirection="column">
      <SectionHeader title="AGENT REGISTRY" count={agents.length} />
      <Box marginTop={1}>
        <Grid columns={columns} gap={0} rowGap={0}>
          {visibleAgents.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              selected={agent.id === selectedAgentId}
            />
          ))}
        </Grid>
      </Box>
      {hiddenCount > 0 && (
        <Box paddingLeft={2}>
          <Text color={COLORS.textSecondary}>+{hiddenCount} more agents</Text>
        </Box>
      )}
    </Box>
  );
}
