import React from "react";
import { Box, Text, useInput } from "ink";
import { SYMBOLS } from "../../theme/index.js";

interface HelpModalProps {
  onClose: () => void;
}

interface ShortcutItem {
  key: string;
  description: string;
}

const SHORTCUTS: ShortcutItem[] = [
  { key: "H", description: "Toggle this help" },
  { key: "R", description: "Refresh data" },
  { key: "Q", description: "Quit application" },
  { key: "L", description: "Switch to legacy view" },
  { key: "O", description: "Switch to orchestrator view" },
  { key: "P", description: "Pause autonomous loop" },
  { key: "Esc", description: "Close modal / Go back" },
];

/**
 * Help modal showing keyboard shortcuts
 */
export function HelpModal({ onClose }: HelpModalProps) {
  useInput((input, key) => {
    if (
      key.escape ||
      input.toLowerCase() === "h" ||
      input.toLowerCase() === "q"
    ) {
      onClose();
    }
  });

  const boxWidth = 40;
  const innerWidth = boxWidth - 2;
  const doubleLine = SYMBOLS.box.doubleHorizontal.repeat(innerWidth);

  return (
    <Box flexDirection="column" padding={1}>
      {/* Top border */}
      <Box>
        <Text color="cyan">{SYMBOLS.box.doubleTopLeft}</Text>
        <Text color="cyan">{doubleLine}</Text>
        <Text color="cyan">{SYMBOLS.box.doubleTopRight}</Text>
      </Box>

      {/* Title */}
      <Box>
        <Text color="cyan">{SYMBOLS.box.doubleVertical}</Text>
        <Box width={innerWidth} justifyContent="center">
          <Text bold color="white">
            Keyboard Shortcuts
          </Text>
        </Box>
        <Text color="cyan">{SYMBOLS.box.doubleVertical}</Text>
      </Box>

      {/* Divider */}
      <Box>
        <Text color="cyan">{SYMBOLS.box.teeLeft}</Text>
        <Text color="gray">{SYMBOLS.box.horizontal.repeat(innerWidth)}</Text>
        <Text color="cyan">{SYMBOLS.box.teeRight}</Text>
      </Box>

      {/* Shortcuts */}
      {SHORTCUTS.map((shortcut, index) => (
        <Box key={index}>
          <Text color="cyan">{SYMBOLS.box.doubleVertical}</Text>
          <Box width={innerWidth} paddingLeft={2}>
            <Box width={6}>
              <Text color="yellow">{shortcut.key}</Text>
            </Box>
            <Text>{shortcut.description}</Text>
          </Box>
          <Text color="cyan">{SYMBOLS.box.doubleVertical}</Text>
        </Box>
      ))}

      {/* Empty line */}
      <Box>
        <Text color="cyan">{SYMBOLS.box.doubleVertical}</Text>
        <Box width={innerWidth}>
          <Text> </Text>
        </Box>
        <Text color="cyan">{SYMBOLS.box.doubleVertical}</Text>
      </Box>

      {/* Footer */}
      <Box>
        <Text color="cyan">{SYMBOLS.box.doubleVertical}</Text>
        <Box width={innerWidth} justifyContent="center">
          <Text dimColor>Press Esc or H to close</Text>
        </Box>
        <Text color="cyan">{SYMBOLS.box.doubleVertical}</Text>
      </Box>

      {/* Bottom border */}
      <Box>
        <Text color="cyan">{SYMBOLS.box.doubleBottomLeft}</Text>
        <Text color="cyan">{doubleLine}</Text>
        <Text color="cyan">{SYMBOLS.box.doubleBottomRight}</Text>
      </Box>
    </Box>
  );
}
