import React from "react";
import { Box, Text } from "ink";
import { SYMBOLS, COLORS } from "../../theme/index.js";
import { formatMemory, formatCPU } from "../../utils/format.js";
import type { SystemMetrics } from "../../types/index.js";

interface OrchestratorFooterProps {
  system: SystemMetrics;
  isPaused?: boolean;
}

/**
 * Footer with keyboard shortcuts and system metrics
 * Format: "> Press [H] for help | [R] to refresh | [Q] to quit" on left
 *         "SYS: OK | MEM: 2.4GB | CPU: 34%" on right
 */
export function OrchestratorFooter({
  system,
  isPaused = false,
}: OrchestratorFooterProps) {
  return (
    <Box flexDirection="column" marginTop={1}>
      {/* Divider */}
      <Box>
        <Text color={COLORS.orchestrator.sectionBorder}>
          {SYMBOLS.divider.repeat(80)}
        </Text>
      </Box>

      {/* Shortcuts and system stats */}
      <Box flexDirection="row" justifyContent="space-between" marginTop={1}>
        <Box>
          <Text color={COLORS.textSecondary}>&gt; Press </Text>
          <Text color={COLORS.textSecondary}>[</Text>
          <Text color={COLORS.textPrimary}>H</Text>
          <Text color={COLORS.textSecondary}>] for help</Text>
          <Text color={COLORS.textSecondary}> | </Text>
          <Text color={COLORS.textSecondary}>[</Text>
          <Text color={COLORS.textPrimary}>R</Text>
          <Text color={COLORS.textSecondary}>] to refresh</Text>
          <Text color={COLORS.textSecondary}> | </Text>
          <Text color={COLORS.textSecondary}>[</Text>
          <Text color={COLORS.textPrimary}>Q</Text>
          <Text color={COLORS.textSecondary}>] to quit</Text>
          {isPaused && (
            <>
              <Text color={COLORS.textSecondary}> | </Text>
              <Text color={COLORS.warning}>[PAUSED]</Text>
            </>
          )}
        </Box>
        <Box>
          <Text color={COLORS.orchestrator.sysLabel}>SYS:</Text>
          <Text> </Text>
          <Text color={COLORS.orchestrator.sysOk}>OK</Text>
          <Text color={COLORS.textSecondary}> | </Text>
          <Text color={COLORS.orchestrator.memLabel}>MEM:</Text>
          <Text> </Text>
          <Text color={COLORS.textPrimary}>
            {formatMemory(system.memoryUsedGB)}
          </Text>
          <Text color={COLORS.textSecondary}> | </Text>
          <Text color={COLORS.orchestrator.cpuLabel}>CPU:</Text>
          <Text> </Text>
          <Text color={COLORS.textPrimary}>{formatCPU(system.cpuPercent)}</Text>
        </Box>
      </Box>
    </Box>
  );
}
