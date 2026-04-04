import React from "react";
import { Box, Text, useInput, useApp } from "ink";
import { SYMBOLS } from "../theme/index.js";
import { getCachedVersion } from "../utils/version.js";
import type { DataMode } from "../types/index.js";

interface ModeSelectorProps {
  onSelect: (mode: DataMode) => void;
}

/**
 * Startup mode selector screen
 * User chooses Mock or Real agent tracking mode
 */
export function ModeSelector({ onSelect }: ModeSelectorProps) {
  const { exit } = useApp();
  const version = getCachedVersion();

  useInput((input, key) => {
    const lowerInput = input.toLowerCase();

    if (lowerInput === "m") {
      onSelect("mock");
    } else if (lowerInput === "r") {
      onSelect("real");
    } else if (key.escape || lowerInput === "q") {
      exit();
    }
  });

  const boxWidth = 44;
  const innerWidth = boxWidth - 2;
  const doubleLine = SYMBOLS.box.doubleHorizontal.repeat(innerWidth);
  const singleLine = SYMBOLS.box.horizontal.repeat(innerWidth);

  return (
    <Box flexDirection="column" padding={1}>
      {/* Top border */}
      <Box>
        <Text color="cyan">{SYMBOLS.box.doubleTopLeft}</Text>
        <Text color="cyan">{doubleLine}</Text>
        <Text color="cyan">{SYMBOLS.box.doubleTopRight}</Text>
      </Box>

      {/* Robot Logo */}
      {SYMBOLS.robot.lines.map((line, idx) => (
        <Box key={idx}>
          <Text color="cyan">{SYMBOLS.box.doubleVertical}</Text>
          <Box width={innerWidth} justifyContent="center">
            <Text color="yellow">{line}</Text>
          </Box>
          <Text color="cyan">{SYMBOLS.box.doubleVertical}</Text>
        </Box>
      ))}

      {/* Title */}
      <Box>
        <Text color="cyan">{SYMBOLS.box.doubleVertical}</Text>
        <Box width={innerWidth} justifyContent="center">
          <Text bold color="white">
            AGENT ORCHESTRATOR v{version}
          </Text>
        </Box>
        <Text color="cyan">{SYMBOLS.box.doubleVertical}</Text>
      </Box>

      {/* Divider */}
      <Box>
        <Text color="cyan">{SYMBOLS.box.teeLeft}</Text>
        <Text color="gray">{singleLine}</Text>
        <Text color="cyan">{SYMBOLS.box.teeRight}</Text>
      </Box>

      {/* Instructions */}
      <Box>
        <Text color="cyan">{SYMBOLS.box.doubleVertical}</Text>
        <Box width={innerWidth} justifyContent="center">
          <Text>Select data mode:</Text>
        </Box>
        <Text color="cyan">{SYMBOLS.box.doubleVertical}</Text>
      </Box>

      {/* Empty line */}
      <Box>
        <Text color="cyan">{SYMBOLS.box.doubleVertical}</Text>
        <Box width={innerWidth}>
          <Text> </Text>
        </Box>
        <Text color="cyan">{SYMBOLS.box.doubleVertical}</Text>
      </Box>

      {/* Mock option */}
      <Box>
        <Text color="cyan">{SYMBOLS.box.doubleVertical}</Text>
        <Box width={innerWidth} paddingLeft={2}>
          <Text color="yellow">[M]</Text>
          <Text> Mock Data - Demo with sample agents</Text>
        </Box>
        <Text color="cyan">{SYMBOLS.box.doubleVertical}</Text>
      </Box>

      {/* Real option */}
      <Box>
        <Text color="cyan">{SYMBOLS.box.doubleVertical}</Text>
        <Box width={innerWidth} paddingLeft={2}>
          <Text color="green">[R]</Text>
          <Text> Real Tracking - Live agent data</Text>
        </Box>
        <Text color="cyan">{SYMBOLS.box.doubleVertical}</Text>
      </Box>

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
          <Text dimColor>Press key to continue, Q to quit</Text>
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
