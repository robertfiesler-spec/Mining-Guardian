import { useState, useEffect, useCallback } from "react";
import { readFileSync, watchFile, unwatchFile, existsSync } from "fs";
import { resolve } from "path";
import { STATE_DIR } from "../constants.js";
import { getMockAgentRegistry, getMockCosts } from "../data/index.js";
import { getCachedVersion } from "../utils/version.js";
import type {
  OrchestratorState,
  DataMode,
  CostMetrics,
  SystemMetrics,
} from "../types/index.js";
import type { AgentRegistry } from "../types/agent.js";

const ORCHESTRATOR_FILE = `${STATE_DIR}/orchestrator.json`;

interface OrchestratorFileState {
  version: string;
  updated_at: string;
  agents: AgentRegistry;
  costs: CostMetrics;
}

interface UseOrchestratorResult {
  state: OrchestratorState | null;
  error: string | null;
  isLoading: boolean;
  refresh: () => void;
}

/**
 * Hook for orchestrator state management
 * Supports both mock and real data modes
 */
export function useOrchestrator(
  mode: DataMode,
  systemMetrics: SystemMetrics,
  pollInterval = 1000,
): UseOrchestratorResult {
  const [state, setState] = useState<OrchestratorState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadState = useCallback(() => {
    if (mode === "mock") {
      // Use mock data
      const registry = getMockAgentRegistry();
      const costs = getMockCosts();

      setState({
        config: {
          version: getCachedVersion(),
          dataMode: "mock",
          refreshInterval: pollInterval,
          maxAgentsDisplayed: 12,
        },
        connection: "connected",
        costs,
        system: systemMetrics,
        registry,
        lastUpdated: new Date().toISOString(),
      });
      setError(null);
      setIsLoading(false);
      return;
    }

    // Real mode - read from orchestrator.json
    const orchestratorPath = resolve(process.cwd(), ORCHESTRATOR_FILE);

    try {
      if (!existsSync(orchestratorPath)) {
        // File doesn't exist yet - return empty state
        setState({
          config: {
            version: getCachedVersion(),
            dataMode: "real",
            refreshInterval: pollInterval,
            maxAgentsDisplayed: 12,
          },
          connection: "disconnected",
          costs: {
            today: 0,
            sessions: 0,
            sevenDay: 0,
            thirtyDay: 0,
          },
          system: systemMetrics,
          registry: {
            agents: [],
            activeCount: 0,
            pendingCount: 0,
            completedCount: 0,
            errorCount: 0,
          },
          lastUpdated: new Date().toISOString(),
        });
        setError(null);
        setIsLoading(false);
        return;
      }

      const data = readFileSync(orchestratorPath, "utf-8");

      if (!data.trim()) {
        setError("Orchestrator file is empty");
        setIsLoading(false);
        return;
      }

      const parsed = JSON.parse(data) as OrchestratorFileState;

      setState({
        config: {
          version: parsed.version || "1.0.0",
          dataMode: "real",
          refreshInterval: pollInterval,
          maxAgentsDisplayed: 12,
        },
        connection: "connected",
        costs: parsed.costs || {
          today: 0,
          sessions: 0,
          sevenDay: 0,
          thirtyDay: 0,
        },
        system: systemMetrics,
        registry: parsed.agents || {
          agents: [],
          activeCount: 0,
          pendingCount: 0,
          completedCount: 0,
          errorCount: 0,
        },
        lastUpdated: parsed.updated_at || new Date().toISOString(),
      });
      setError(null);
      setIsLoading(false);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : String(err);
      setError(`Failed to load orchestrator state: ${errorMessage}`);
      setIsLoading(false);
    }
  }, [mode, pollInterval, systemMetrics]);

  useEffect(() => {
    // Initial load
    loadState();

    if (mode === "mock") {
      // For mock mode, just update system metrics periodically
      const timer = setInterval(() => {
        setState((prev) =>
          prev
            ? {
                ...prev,
                system: systemMetrics,
                lastUpdated: new Date().toISOString(),
              }
            : null,
        );
      }, pollInterval);

      return () => clearInterval(timer);
    }

    // Real mode - watch file for changes
    const orchestratorPath = resolve(process.cwd(), ORCHESTRATOR_FILE);

    watchFile(orchestratorPath, { interval: pollInterval }, () => {
      loadState();
    });

    return () => {
      unwatchFile(orchestratorPath);
    };
  }, [loadState, mode, pollInterval, systemMetrics]);

  return {
    state,
    error,
    isLoading,
    refresh: loadState,
  };
}
