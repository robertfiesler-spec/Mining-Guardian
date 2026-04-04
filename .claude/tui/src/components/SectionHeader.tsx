import React from "react";
import { Box, Text } from "ink";
import { Divider } from "./Divider.js";

interface SectionHeaderProps {
  title: string;
  showDivider?: boolean;
}

export function SectionHeader({
  title,
  showDivider = true,
}: SectionHeaderProps) {
  return (
    <Box flexDirection="column">
      <Text bold>{title.toUpperCase()}</Text>
      {showDivider && <Divider />}
    </Box>
  );
}
