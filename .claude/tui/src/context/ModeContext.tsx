import React, { createContext, useContext, useState, useCallback } from "react";
import type { DataMode, OrchestratorViewState } from "../types/index.js";

interface ModeContextValue {
  mode: DataMode;
  setMode: (mode: DataMode) => void;
  viewState: OrchestratorViewState;
  setShowHelp: (show: boolean) => void;
  setSelectedAgent: (agentId: string | undefined) => void;
  setScrollOffset: (offset: number) => void;
}

const ModeContext = createContext<ModeContextValue | null>(null);

interface ModeProviderProps {
  children: React.ReactNode;
  initialMode?: DataMode;
}

/**
 * Context provider for orchestrator mode and view state
 */
export function ModeProvider({ children, initialMode }: ModeProviderProps) {
  const [mode, setMode] = useState<DataMode>(initialMode ?? "mock");
  const [viewState, setViewState] = useState<OrchestratorViewState>({
    mode: initialMode ?? "mock",
    showHelp: false,
    selectedAgentId: undefined,
    scrollOffset: 0,
  });

  const handleSetMode = useCallback((newMode: DataMode) => {
    setMode(newMode);
    setViewState((prev) => ({ ...prev, mode: newMode }));
  }, []);

  const setShowHelp = useCallback((show: boolean) => {
    setViewState((prev) => ({ ...prev, showHelp: show }));
  }, []);

  const setSelectedAgent = useCallback((agentId: string | undefined) => {
    setViewState((prev) => ({ ...prev, selectedAgentId: agentId }));
  }, []);

  const setScrollOffset = useCallback((offset: number) => {
    setViewState((prev) => ({ ...prev, scrollOffset: offset }));
  }, []);

  return (
    <ModeContext.Provider
      value={{
        mode,
        setMode: handleSetMode,
        viewState,
        setShowHelp,
        setSelectedAgent,
        setScrollOffset,
      }}
    >
      {children}
    </ModeContext.Provider>
  );
}

/**
 * Hook to access mode context
 */
export function useMode(): ModeContextValue {
  const context = useContext(ModeContext);

  if (!context) {
    throw new Error("useMode must be used within a ModeProvider");
  }

  return context;
}

/**
 * Hook for just the data mode
 */
export function useDataMode(): DataMode {
  const { mode } = useMode();
  return mode;
}
