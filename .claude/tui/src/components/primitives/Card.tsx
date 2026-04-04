import React from "react";
import { Box, Text } from "ink";
import { SYMBOLS } from "../../theme/index.js";

interface CardProps {
  title?: string;
  children: React.ReactNode;
  width?: number | string;
  borderColor?: string;
  padding?: number;
  marginRight?: number;
  marginBottom?: number;
}

/**
 * Card component with border support
 * Uses box-drawing characters for clean borders
 */
export function Card({
  title,
  children,
  width,
  borderColor = "gray",
  padding = 1,
  marginRight = 0,
  marginBottom = 0,
}: CardProps) {
  return (
    <Box
      flexDirection="column"
      width={width}
      marginRight={marginRight}
      marginBottom={marginBottom}
    >
      {/* Top border with optional title */}
      <Box>
        <Text color={borderColor}>{SYMBOLS.box.topLeft}</Text>
        {title ? (
          <>
            <Text color={borderColor}>{SYMBOLS.box.horizontal}</Text>
            <Text color={borderColor}> </Text>
            <Text bold color="white">
              {title}
            </Text>
            <Text color={borderColor}> </Text>
            <Text color={borderColor}>{SYMBOLS.box.horizontal.repeat(50)}</Text>
          </>
        ) : (
          <Text color={borderColor}>{SYMBOLS.box.horizontal.repeat(50)}</Text>
        )}
        <Text color={borderColor}>{SYMBOLS.box.topRight}</Text>
      </Box>

      {/* Content with side borders */}
      <Box flexDirection="row">
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
        <Box
          flexDirection="column"
          paddingLeft={padding}
          paddingRight={padding}
          flexGrow={1}
        >
          {children}
        </Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
      </Box>

      {/* Bottom border */}
      <Box>
        <Text color={borderColor}>{SYMBOLS.box.bottomLeft}</Text>
        <Text color={borderColor}>{SYMBOLS.box.horizontal.repeat(50)}</Text>
        <Text color={borderColor}>{SYMBOLS.box.bottomRight}</Text>
      </Box>
    </Box>
  );
}

interface CompactCardProps {
  title: string;
  value: string;
  subtitle?: string;
  borderColor?: string;
  width?: number;
}

/**
 * Compact card for metric displays
 * Shows title, large value, and optional subtitle
 */
export function CompactCard({
  title,
  value,
  subtitle,
  borderColor = "gray",
  width = 18,
}: CompactCardProps) {
  const innerWidth = width - 2;
  const horizontalLine = SYMBOLS.box.horizontal.repeat(innerWidth);

  return (
    <Box flexDirection="column" width={width}>
      {/* Top border */}
      <Box>
        <Text color={borderColor}>{SYMBOLS.box.topLeft}</Text>
        <Text color={borderColor}>{horizontalLine}</Text>
        <Text color={borderColor}>{SYMBOLS.box.topRight}</Text>
      </Box>

      {/* Title row */}
      <Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
        <Box width={innerWidth} justifyContent="center">
          <Text dimColor>{title}</Text>
        </Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
      </Box>

      {/* Value row */}
      <Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
        <Box width={innerWidth} justifyContent="center">
          <Text bold color="white">
            {value}
          </Text>
        </Box>
        <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
      </Box>

      {/* Subtitle row (optional) */}
      {subtitle && (
        <Box>
          <Text color={borderColor}>{SYMBOLS.box.vertical}</Text>
          <Box width={innerWidth} justifyContent="center">
            <Text color="cyan">{subtitle}</Text>
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
