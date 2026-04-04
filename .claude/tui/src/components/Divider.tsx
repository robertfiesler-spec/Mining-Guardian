import React from "react";
import { Text } from "ink";
import { SYMBOLS, COLORS } from "../theme.js";

interface DividerProps {
  width?: number;
}

export function Divider({ width = 68 }: DividerProps) {
  return <Text color={COLORS.divider}>{SYMBOLS.divider.repeat(width)}</Text>;
}
