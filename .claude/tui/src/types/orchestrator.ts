/**
 * Orchestrator state type definitions
 */

import type { AgentRegistry } from "./agent.js";

export type DataMode = "mock" | "real";
export type ConnectionStatus = "connected" | "disconnected" | "reconnecting";

export interface CostMetrics {
  today: number;
  todayDelta?: number;
  sessions: number;
  sessionsDelta?: number;
  sevenDay: number;
  sevenDayDelta?: number;
  thirtyDay: number;
  thirtyDayDelta?: number;
}

export interface SystemMetrics {
  memoryUsedGB: number;
  memoryTotalGB: number;
  cpuPercent: number;
  uptime: number;
}

export interface OrchestratorConfig {
  version: string;
  dataMode: DataMode;
  refreshInterval: number;
  maxAgentsDisplayed: number;
}

export interface OrchestratorState {
  config: OrchestratorConfig;
  connection: ConnectionStatus;
  costs: CostMetrics;
  system: SystemMetrics;
  registry: AgentRegistry;
  lastUpdated: string;
}

export interface OrchestratorViewState {
  mode: DataMode;
  showHelp: boolean;
  selectedAgentId?: string;
  scrollOffset: number;
}
