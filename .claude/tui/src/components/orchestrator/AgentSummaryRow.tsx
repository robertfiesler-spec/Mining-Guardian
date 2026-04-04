import React from "react";
import { Box } from "ink";
import { SummaryCard } from "./SummaryCard.js";
import { SectionHeader } from "../primitives/SectionHeader.js";
import { COLORS } from "../../theme/index.js";
import type { AgentRegistry } from "../../types/index.js";

interface AgentSummaryRowProps {
  registry: AgentRegistry;
}

/**
 * Row showing active/pending/completed agent counts
 */
export function AgentSummaryRow({ registry }: AgentSummaryRowProps) {
  return (
    <Box flexDirection="column">
      <SectionHeader title="ACTIVE AGENTS" />
      <Box flexDirection="row" marginTop={1}>
        <SummaryCard
          title="Active"
          count={registry.activeCount}
          color={COLORS.orchestrator.active}
        />
        <SummaryCard
          title="Pending"
          count={registry.pendingCount}
          color={COLORS.orchestrator.pending}
        />
        <SummaryCard
          title="Completed"
          count={registry.completedCount}
          color={COLORS.orchestrator.completed}
        />
        {registry.errorCount > 0 && (
          <SummaryCard
            title="Error"
            count={registry.errorCount}
            color={COLORS.orchestrator.error}
          />
        )}
      </Box>
    </Box>
  );
}
