import React from "react";
import { Box, Text } from "ink";
import { SYMBOLS, COLORS } from "../../theme/index.js";
import { getCardBorderColor, getAgentStatusColor } from "../../theme/colors.js";
import { formatCurrency, truncate } from "../../utils/format.js";
import type { AgentState } from "../../types/index.js";

interface AgentCardProps {
  agent: AgentState;
  width?: number;
  selected?: boolean;
}

/**
 * Full agent card with all metrics - redesigned to match mockup
 */
export function AgentCard({
  agent,
  width = 38,
  selected = false,
}: AgentCardProps) {
  const innerWidth = width - 2;
  const horizontalLine = SYMBOLS.box.horizontal.repeat(innerWidth);
  const borderColor = getCardBorderColor(agent.status, selected);
  const statusColor = getAgentStatusColor(agent.status);

  // Status label mapping
  const statusLabel =
    agent.status === "pending" ? "PENDING INPUT" : agent.status.toUpperCase();

  // Context bar calculations (clamp to prevent negative repeat)
  const contextRatio =
    agent.context.total > 0
      ? Math.min(agent.context.used / agent.context.total, 1)
      : 0;
  const contextPercent = Math.round(contextRatio * 100);
  const barWidth = innerWidth - 4;
  const filledWidth = Math.round(contextRatio * barWidth);
  const emptyWidth = Math.max(0, barWidth - filledWidth);
  const contextBarColor =
    contextPercent >= 90 ? "red" : COLORS.orchestrator.contextFilled;

  // Task count and visible tasks
  const taskCount = agent.tasks.length;
  const maxVisibleTasks = 3;
  const visibleTasks = agent.tasks.slice(0, maxVisibleTasks);
  const hiddenTaskCount = taskCount - maxVisibleTasks;

  return (
    <Box flexDirection="column" marginRight={1} marginBottom={1}>
      {/* Top border */}
      <Box>
        <Text color={borderColor}>{SYMBOLS.box.topLeft}</Text>
        <Text color={borderColor}>{horizontalLine}</Text>
        <Text color={borderColor}>{SYMBOLS.box.topRight}</Text>
      </Box>

      {/* Header: Icon + Name + Status Badge */}
      <Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
        <Box width={innerWidth} paddingLeft={1} justifyContent="space-between">
          <Box>
            <Text color={COLORS.orchestrator.agentIcon}>
              {SYMBOLS.icons.agent}
            </Text>
            <Text> </Text>
            <Text bold color={COLORS.orchestrator.agentName}>
              {truncate(agent.name.toUpperCase(), innerWidth - 18)}
            </Text>
          </Box>
          <Box paddingRight={1}>
            <Text color={statusColor}>{SYMBOLS.statusDot}</Text>
            <Text> </Text>
            <Text color={statusColor}>{statusLabel}</Text>
          </Box>
        </Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
      </Box>

      {/* Separator line */}
      <Box>
        <Text color={borderColor}>{SYMBOLS.box.teeLeft}</Text>
        <Text color={borderColor}>{horizontalLine}</Text>
        <Text color={borderColor}>{SYMBOLS.box.teeRight}</Text>
      </Box>

      {/* Stats row: Context Remaining | Cost */}
      <Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
        <Box width={innerWidth} paddingLeft={1}>
          <Box width={Math.floor(innerWidth / 2)}>
            <Text color={COLORS.textSecondary}>{SYMBOLS.icons.context}</Text>
            <Text> </Text>
            <Text color={COLORS.textSecondary}>CTX LEFT</Text>
          </Box>
          <Box>
            <Text color={COLORS.orchestrator.costLabel}>
              {SYMBOLS.icons.cost}
            </Text>
            <Text> </Text>
            <Text color={COLORS.orchestrator.costLabel}>COST</Text>
          </Box>
        </Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
      </Box>

      {/* Stats values row */}
      <Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
        <Box width={innerWidth} paddingLeft={1}>
          <Box width={Math.floor(innerWidth / 2)}>
            <Text
              bold
              color={
                contextPercent >= 90
                  ? "red"
                  : contextPercent >= 75
                    ? "yellow"
                    : "green"
              }
            >
              {100 - contextPercent}%
            </Text>
          </Box>
          <Box>
            <Text bold color={COLORS.orchestrator.costValue}>
              {formatCurrency(agent.metrics.cost)}
            </Text>
          </Box>
        </Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
      </Box>

      {/* Context progress bar */}
      <Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
        <Box width={innerWidth} paddingLeft={1} paddingRight={1}>
          <Text color={contextBarColor}>
            {SYMBOLS.progressBar.filled.repeat(filledWidth)}
          </Text>
          <Text color={COLORS.orchestrator.contextEmpty}>
            {SYMBOLS.progressBar.empty.repeat(emptyWidth)}
          </Text>
        </Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
      </Box>

      {/* Tasks section header */}
      <Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
        <Box width={innerWidth} paddingLeft={1}>
          <Text color={COLORS.textSecondary}>{SYMBOLS.icons.tasks}</Text>
          <Text> </Text>
          <Text color={COLORS.textSecondary}>TASKS ({taskCount})</Text>
        </Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
      </Box>

      {/* Task tags */}
      <Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
        <Box width={innerWidth} paddingLeft={1} flexWrap="wrap">
          {visibleTasks.map((task, i) => (
            <Box key={task.id || i} marginRight={1}>
              <Text color={COLORS.orchestrator.taskBorder}>[</Text>
              <Text color={COLORS.orchestrator.taskText}>{task.label}</Text>
              <Text color={COLORS.orchestrator.taskBorder}>]</Text>
            </Box>
          ))}
          {hiddenTaskCount > 0 && (
            <Text color={COLORS.textSecondary}>+{hiddenTaskCount} more</Text>
          )}
          {taskCount === 0 && (
            <Text color={COLORS.textSecondary}>No tasks</Text>
          )}
        </Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
      </Box>

      {/* Active command section (if present) */}
      {agent.currentCommand && (
        <>
          <Box>
            <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
            <Box width={innerWidth} paddingLeft={1}>
              <Text color={COLORS.orchestrator.cmdPrompt}>
                {SYMBOLS.icons.command}
              </Text>
              <Text> </Text>
              <Text color={COLORS.textSecondary}>ACTIVE CMD</Text>
            </Box>
            <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
          </Box>
          <Box>
            <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
            <Box width={innerWidth} paddingLeft={1}>
              <Text color={COLORS.orchestrator.cmdPrompt}>&gt; </Text>
              <Text color={COLORS.orchestrator.cmdText}>
                {truncate(agent.currentCommand, innerWidth - 6)}
              </Text>
              <Text color={COLORS.orchestrator.cmdCursor}>
                {" "}
                {SYMBOLS.icons.cursor}
              </Text>
            </Box>
            <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
          </Box>
        </>
      )}

      {/* Error (if present) */}
      {agent.error && (
        <Box>
          <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
          <Box width={innerWidth} paddingLeft={1}>
            <Text color={COLORS.error}>{SYMBOLS.error} </Text>
            <Text color={COLORS.error}>
              {truncate(agent.error, innerWidth - 4)}
            </Text>
          </Box>
          <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
        </Box>
      )}

      {/* Bottom border */}
      <Box>
        <Text color={borderColor}>{SYMBOLS.box.bottomLeft}</Text>
        <Text color={borderColor}>{horizontalLine}</Text>
        <Text color={borderColor}>{SYMBOLS.box.bottomRight}</Text>
      </Box>
    </Box>
  );
}
