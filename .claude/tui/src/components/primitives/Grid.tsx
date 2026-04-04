import React from "react";
import { Box } from "ink";

interface GridProps {
  columns: number;
  children: React.ReactNode;
  gap?: number;
  rowGap?: number;
}

/**
 * Grid layout helper component
 * Arranges children in a specified number of columns
 */
export function Grid({ columns, children, gap = 1, rowGap = 0 }: GridProps) {
  const childArray = React.Children.toArray(children);
  const rows: React.ReactNode[][] = [];

  // Group children into rows
  for (let i = 0; i < childArray.length; i += columns) {
    rows.push(childArray.slice(i, i + columns));
  }

  return (
    <Box flexDirection="column">
      {rows.map((row, rowIndex) => (
        <Box
          key={rowIndex}
          flexDirection="row"
          marginBottom={rowIndex < rows.length - 1 ? rowGap : 0}
        >
          {row.map((child, colIndex) => (
            <Box key={colIndex} marginRight={colIndex < columns - 1 ? gap : 0}>
              {child}
            </Box>
          ))}
        </Box>
      ))}
    </Box>
  );
}

interface FlexRowProps {
  children: React.ReactNode;
  gap?: number;
  justify?:
    | "flex-start"
    | "flex-end"
    | "center"
    | "space-between"
    | "space-around";
  align?: "flex-start" | "flex-end" | "center" | "stretch";
}

/**
 * Flexible row layout helper
 */
export function FlexRow({
  children,
  gap = 1,
  justify = "flex-start",
  align = "flex-start",
}: FlexRowProps) {
  const childArray = React.Children.toArray(children);

  return (
    <Box flexDirection="row" justifyContent={justify} alignItems={align}>
      {childArray.map((child, index) => (
        <Box key={index} marginRight={index < childArray.length - 1 ? gap : 0}>
          {child}
        </Box>
      ))}
    </Box>
  );
}

interface FlexColumnProps {
  children: React.ReactNode;
  gap?: number;
  align?: "flex-start" | "flex-end" | "center" | "stretch";
}

/**
 * Flexible column layout helper
 */
export function FlexColumn({
  children,
  gap = 0,
  align = "stretch",
}: FlexColumnProps) {
  const childArray = React.Children.toArray(children);

  return (
    <Box flexDirection="column" alignItems={align}>
      {childArray.map((child, index) => (
        <Box key={index} marginBottom={index < childArray.length - 1 ? gap : 0}>
          {child}
        </Box>
      ))}
    </Box>
  );
}
