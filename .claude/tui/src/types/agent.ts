/**
 * Agent type definitions for the Orchestrator Dashboard
 */

export type AgentStatus = "active" | "pending" | "completed" | "error" | "idle";

export interface AgentTask {
  id: string;
  label: string;
  status: "pending" | "in_progress" | "completed";
}

export interface AgentMetrics {
  tokensIn: number;
  tokensOut: number;
  totalTokens: number;
  cost: number;
  startTime: string;
  endTime?: string;
  duration?: number;
}

export interface AgentContext {
  used: number;
  total: number;
  percentage: number;
}

export interface AgentState {
  id: string;
  name: string;
  type: string;
  status: AgentStatus;
  metrics: AgentMetrics;
  context: AgentContext;
  tasks: AgentTask[];
  currentCommand?: string;
  error?: string;
  parentId?: string;
  children?: string[];
}

export interface AgentRegistry {
  agents: AgentState[];
  activeCount: number;
  pendingCount: number;
  completedCount: number;
  errorCount: number;
}
