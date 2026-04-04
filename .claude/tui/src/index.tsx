#!/usr/bin/env node
import React from "react";
import { render } from "ink";
import { App } from "./App.js";
import { ErrorBoundary } from "./components/ErrorBoundary.js";

// Global error handlers for graceful fallback
// Clear screen before logging to prevent overlap with Ink rendering
process.on("uncaughtException", (error: Error) => {
  process.stdout.write("\x1B[2J\x1B[H"); // Clear screen first
  process.stderr.write(`\n[TUI] Uncaught exception: ${error.message}\n`);
  process.stderr.write(
    "The loop continues running. Monitor with: tail -f .claude/state/progress.txt\n",
  );
  process.exit(1);
});

process.on("unhandledRejection", (reason: unknown) => {
  // Don't clear screen for unhandled rejections - try to keep TUI running
  // The rejection will be handled by React's error boundary if it's a render error
});

// Handle graceful exit
const handleExit = () => {
  // Clear screen and restore terminal state before exiting
  process.stdout.write("\x1B[2J\x1B[H");
  if (process.stdin.isTTY) {
    process.stdin.setRawMode(false);
  }
  process.stdout.write("[TUI] Exiting...\n");
  process.exit(0);
};

process.on("SIGINT", handleExit);
process.on("SIGTERM", handleExit);

// Error handler callback for ErrorBoundary
// NOTE: Don't use console.error here as it interferes with Ink's rendering
const handleError = (error: Error) => {
  // Errors are displayed via the ErrorBoundary's render method
  // Only log to file if needed for debugging
};

// Ensure stdin is in raw mode for keyboard input
// This is especially important for terminals like Warp
if (process.stdin.isTTY) {
  process.stdin.setRawMode(true);
}
process.stdin.resume();

// Clear screen before rendering to prevent duplicate rendering artifacts
// Uses ANSI escape codes: \x1B[2J clears screen, \x1B[H moves cursor to home
process.stdout.write("\x1B[2J\x1B[H");

// Render the app with error boundary
const { unmount, waitUntilExit, clear } = render(
  <ErrorBoundary
    fallbackMessage="The TUI encountered an error. The loop continues running in the background."
    onError={handleError}
  >
    <App />
  </ErrorBoundary>,
);

// Handle cleanup on exit
waitUntilExit().then(() => {
  if (process.stdin.isTTY) {
    process.stdin.setRawMode(false);
  }
});
