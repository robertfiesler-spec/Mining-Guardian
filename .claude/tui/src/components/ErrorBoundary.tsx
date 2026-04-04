import React, { Component, ReactNode } from "react";
import { Box, Text } from "ink";
import { COLORS, SYMBOLS } from "../theme.js";

interface ErrorBoundaryProps {
  children: ReactNode;
  fallbackMessage?: string;
  onError?: (error: Error, errorInfo: React.ErrorInfo) => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

/**
 * Error boundary component for graceful error handling in TUI
 * Catches React errors and displays a user-friendly message
 */
export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    // NOTE: Avoid console.error here as it interferes with Ink's rendering
    // and can cause duplicate content to appear on screen.
    // The error is displayed in the render method instead.

    // Call optional error handler which can log if needed
    this.props.onError?.(error, errorInfo);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      const message =
        this.props.fallbackMessage || "An error occurred in the TUI";

      return (
        <Box flexDirection="column" padding={1}>
          <Box marginBottom={1}>
            <Text bold color={COLORS.error}>
              {SYMBOLS.error} TUI Error
            </Text>
          </Box>

          <Box marginBottom={1}>
            <Text color={COLORS.warning}>{message}</Text>
          </Box>

          {this.state.error && (
            <Box flexDirection="column" marginBottom={1}>
              <Text dimColor>Error: {this.state.error.message}</Text>
            </Box>
          )}

          <Box flexDirection="column">
            <Text dimColor>The loop continues running in the background.</Text>
            <Text dimColor>
              Monitor progress with: tail -f .claude/state/progress.txt
            </Text>
          </Box>

          <Box marginTop={1}>
            <Text dimColor>Press Ctrl+C to exit</Text>
          </Box>
        </Box>
      );
    }

    return this.props.children;
  }
}
