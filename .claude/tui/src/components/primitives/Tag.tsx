import React from "react";
import { Box, Text } from "ink";
import { COLORS } from "../../theme/index.js";

interface TagProps {
  label: string;
  color?: string;
  borderColor?: string;
}

/**
 * Single tag component for task labels
 * Design: [label] with gray brackets and gray text
 */
export function Tag({
  label,
  color = COLORS.orchestrator.taskText,
  borderColor = COLORS.orchestrator.taskBorder,
}: TagProps) {
  return (
    <Box marginRight={1}>
      <Text color={borderColor}>[</Text>
      <Text color={color}>{label}</Text>
      <Text color={borderColor}>]</Text>
    </Box>
  );
}

interface TagListProps {
  tags: string[];
  maxVisible?: number;
  color?: string;
}

/**
 * List of tags with overflow indicator
 * Shows "+N more" when tags exceed maxVisible
 */
export function TagList({
  tags,
  maxVisible = 3,
  color = "cyan",
}: TagListProps) {
  if (tags.length === 0) {
    return (
      <Box>
        <Text dimColor>No tasks</Text>
      </Box>
    );
  }

  const visibleTags = tags.slice(0, maxVisible);
  const hiddenCount = tags.length - maxVisible;

  return (
    <Box flexDirection="row" flexWrap="wrap">
      {visibleTags.map((tag, index) => (
        <Tag key={index} label={tag} color={color} />
      ))}
      {hiddenCount > 0 && (
        <Box>
          <Text dimColor>+{hiddenCount} more</Text>
        </Box>
      )}
    </Box>
  );
}

interface TaskTagProps {
  label: string;
  status: "pending" | "in_progress" | "completed";
}

const TASK_STATUS_COLORS: Record<string, string> = {
  pending: "gray",
  in_progress: "yellow",
  completed: "green",
};

const TASK_STATUS_SYMBOLS: Record<string, string> = {
  pending: "○",
  in_progress: "●",
  completed: "✓",
};

/**
 * Task tag with status indicator
 */
export function TaskTag({ label, status }: TaskTagProps) {
  const color = TASK_STATUS_COLORS[status];
  const symbol = TASK_STATUS_SYMBOLS[status];

  return (
    <Box marginRight={1}>
      <Text color={color}>
        {symbol} {label}
      </Text>
    </Box>
  );
}

interface TaskListProps {
  tasks: Array<{
    label: string;
    status: "pending" | "in_progress" | "completed";
  }>;
  maxVisible?: number;
}

/**
 * List of task tags with status indicators
 */
export function TaskList({ tasks, maxVisible = 3 }: TaskListProps) {
  if (tasks.length === 0) {
    return (
      <Box>
        <Text dimColor>No tasks</Text>
      </Box>
    );
  }

  const visibleTasks = tasks.slice(0, maxVisible);
  const hiddenCount = tasks.length - maxVisible;

  return (
    <Box flexDirection="row" flexWrap="wrap">
      {visibleTasks.map((task, index) => (
        <TaskTag key={index} label={task.label} status={task.status} />
      ))}
      {hiddenCount > 0 && (
        <Box>
          <Text dimColor>+{hiddenCount} more</Text>
        </Box>
      )}
    </Box>
  );
}
