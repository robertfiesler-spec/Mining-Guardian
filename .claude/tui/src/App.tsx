import React, { useState, useCallback } from "react";
import { Box, Text, useApp, useStdout } from "ink";
import { useSessionWithError } from "./hooks/useSession.js";
import { useKeyboard } from "./hooks/useKeyboard.js";
import { useClock } from "./hooks/useClock.js";
import { useSystemMetrics } from "./hooks/useSystemMetrics.js";
import { useOrchestrator } from "./hooks/useOrchestrator.js";
import { Header } from "./components/Header.js";
import { ProgressSection } from "./components/ProgressSection.js";
import { StatusPanel } from "./components/StatusPanel.js";
import { ActivityLog } from "./components/ActivityLog.js";
import { LogViewer } from "./components/LogViewer.js";
import { StatusViewer } from "./components/StatusViewer.js";
import { Divider } from "./components/Divider.js";
import { ModeSelector } from "./components/ModeSelector.js";
import { HelpModal } from "./components/modals/HelpModal.js";
import {
  OrchestratorDashboard,
  OrchestratorLoading,
  OrchestratorError,
} from "./components/orchestrator/index.js";
import { COLORS, SYMBOLS, getStatusColor } from "./theme.js";
import type { DataMode } from "./types/index.js";

type ViewMode =
  | "mode_select"
  | "orchestrator"
  | "legacy"
  | "logs"
  | "status"
  | "help";

export function App() {
  const { exit } = useApp();
  const { stdout } = useStdout();
  const { session, error, isLoading } = useSessionWithError();
  const [isPaused, setIsPaused] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("mode_select");
  const [previousViewMode, setPreviousViewMode] = useState<
    "orchestrator" | "legacy"
  >("orchestrator");
  const [dataMode, setDataMode] = useState<DataMode>("mock");

  // Clear screen utility - clears terminal and resets cursor position
  const clearScreen = useCallback(() => {
    // ANSI escape codes:
    // \x1B[2J - Clear entire screen
    // \x1B[H - Move cursor to home position (top-left)
    stdout.write("\x1B[2J\x1B[H");
  }, [stdout]);

  // Hooks for orchestrator
  const { time } = useClock();
  const systemMetrics = useSystemMetrics();
  const {
    state: orchestratorState,
    error: orchestratorError,
    isLoading: orchestratorLoading,
    refresh,
  } = useOrchestrator(dataMode, systemMetrics);

  // Disable keyboard handling during mode selection (ModeSelector has its own handlers)
  useKeyboard({
    isActive: viewMode !== "mode_select",
    onPause: () => {
      setIsPaused(true);
      setMessage("Pause requested - loop will stop after current story");
      setTimeout(() => setMessage(null), 3000);
    },
    onResume: () => {
      setIsPaused(false);
      setMessage("Resuming loop...");
      setTimeout(() => setMessage(null), 3000);
    },
    onQuit: () => {
      // Show message briefly then exit
      setMessage("Quit requested - exiting TUI...");
      setTimeout(() => exit(), 500);
    },
    onLogs: () => {
      clearScreen();
      if (viewMode === "orchestrator" || viewMode === "legacy") {
        setPreviousViewMode(viewMode);
        setViewMode("logs");
      } else if (viewMode === "logs") {
        setViewMode(previousViewMode);
      }
    },
    onStatus: () => {
      clearScreen();
      if (viewMode === "orchestrator" || viewMode === "legacy") {
        setPreviousViewMode(viewMode);
        setViewMode("status");
      } else if (viewMode === "status") {
        setViewMode(previousViewMode);
      }
    },
    onHelp: () => {
      clearScreen();
      if (viewMode === "orchestrator" || viewMode === "legacy") {
        setPreviousViewMode(viewMode);
        setViewMode("help");
      } else if (viewMode === "help") {
        setViewMode(previousViewMode);
      }
    },
    onOrchestrator: () => {
      clearScreen();
      if (viewMode === "legacy") {
        setPreviousViewMode("orchestrator");
        setViewMode("orchestrator");
      } else if (viewMode === "orchestrator") {
        setPreviousViewMode("legacy");
        setViewMode("legacy");
      } else if (
        viewMode === "logs" ||
        viewMode === "status" ||
        viewMode === "help"
      ) {
        // From overlay views, toggle the underlying view
        const newView =
          previousViewMode === "orchestrator" ? "legacy" : "orchestrator";
        setPreviousViewMode(newView);
        setViewMode(newView);
      }
    },
  });

  // Handle mode selection - clears screen to prevent duplicate rendering
  const handleModeSelect = useCallback(
    (mode: DataMode) => {
      clearScreen();
      setDataMode(mode);
      setPreviousViewMode("orchestrator");
      setViewMode("orchestrator");
    },
    [clearScreen],
  );

  // Render mode selector
  if (viewMode === "mode_select") {
    return <ModeSelector onSelect={handleModeSelect} />;
  }

  // Render help modal
  if (viewMode === "help") {
    return <HelpModal onClose={() => setViewMode(previousViewMode)} />;
  }

  // Render orchestrator dashboard
  if (viewMode === "orchestrator") {
    if (orchestratorLoading) {
      return <OrchestratorLoading />;
    }

    if (orchestratorError) {
      return <OrchestratorError error={orchestratorError} />;
    }

    if (orchestratorState) {
      return (
        <OrchestratorDashboard
          state={orchestratorState}
          time={time}
          mode={dataMode}
          isPaused={isPaused}
        />
      );
    }

    return <OrchestratorLoading message="Initializing..." />;
  }

  // ---- Legacy views below (require session) ----

  // Show loading state
  if (isLoading) {
    return (
      <Box flexDirection="column" padding={1}>
        <Text bold>AI TOOLKIT</Text>
        <Divider />
        <Box marginTop={1}>
          <Text color={COLORS.primary}>
            {SYMBOLS.bullet} Loading session...
          </Text>
        </Box>
      </Box>
    );
  }

  // Show error state
  if (error) {
    return (
      <Box flexDirection="column" padding={1}>
        <Text bold>AI TOOLKIT</Text>
        <Divider />
        <Box marginTop={1} flexDirection="column">
          <Text color={COLORS.error}>
            {SYMBOLS.error} Session Error: {error.message}
          </Text>
          {error.details && (
            <Box marginTop={1}>
              <Text dimColor>{error.details}</Text>
            </Box>
          )}
        </Box>
        <Box marginTop={1} flexDirection="column">
          <Text dimColor>The loop may still be running in the background.</Text>
          <Text dimColor>
            Monitor progress: tail -f .claude/state/progress.txt
          </Text>
        </Box>
        <Box marginTop={1}>
          <Text dimColor>Press Q to quit, O for orchestrator view</Text>
        </Box>
      </Box>
    );
  }

  // Show waiting state when no session exists
  if (!session) {
    return (
      <Box flexDirection="column" padding={1}>
        <Text bold>AI TOOLKIT</Text>
        <Divider />
        <Box marginTop={1}>
          <Text color={COLORS.primary}>
            {SYMBOLS.bullet} No active session found
          </Text>
        </Box>
        <Text dimColor>
          Press O for orchestrator view, or wait for session...
        </Text>
      </Box>
    );
  }

  // Render log viewer
  if (viewMode === "logs") {
    return (
      <LogViewer
        activityLog={session.activity_log}
        onClose={() => setViewMode(previousViewMode)}
      />
    );
  }

  // Render status viewer
  if (viewMode === "status") {
    return (
      <StatusViewer
        session={session}
        onClose={() => setViewMode(previousViewMode)}
      />
    );
  }

  // Render legacy dashboard
  return (
    <Box flexDirection="column" padding={1}>
      <Header
        mode={session.execution.mode}
        startTime={session.execution.start_time}
      />

      <ProgressSection
        totalStories={session.progress.total_stories}
        completed={session.progress.completed}
        currentStory={session.progress.current_story}
        currentIteration={session.progress.current_iteration}
        mode={session.execution.mode}
      />

      <StatusPanel
        status={session.status}
        planName={session.plan.name}
        branch={session.plan.branch}
        modifiedFiles={session.git.modified_files}
      />

      <ActivityLog activityLog={session.activity_log} />

      {message && (
        <Box marginTop={1}>
          <Text color={COLORS.primary}>
            {SYMBOLS.bullet} {message}
          </Text>
        </Box>
      )}

      <Box marginTop={1} flexDirection="column">
        <Divider />
        <Box flexDirection="row" justifyContent="space-between">
          <Text dimColor>
            {session.execution.mode === "autonomous"
              ? "P Pause R Resume Q Quit L Logs S Status O Orchestrator"
              : "Q Quit L Logs S Status O Orchestrator"}
          </Text>
          <Text>
            <Text color={getStatusColor(session.status)}>
              {SYMBOLS.statusDot}
            </Text>
            <Text> </Text>
            <Text color={getStatusColor(session.status)}>
              {session.status.toUpperCase()}
            </Text>
            {isPaused && session.execution.mode === "autonomous" && (
              <Text color={COLORS.primary}> (PAUSING)</Text>
            )}
          </Text>
        </Box>
      </Box>
    </Box>
  );
}
