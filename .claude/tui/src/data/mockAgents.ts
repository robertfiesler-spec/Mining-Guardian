import type { AgentState, AgentRegistry } from "../types/index.js";

/**
 * Mock agent data for demo/development mode
 */

export const MOCK_AGENTS: AgentState[] = [
  {
    id: "agent-001",
    name: "Orchestrator-Prime",
    type: "orchestrator",
    status: "active",
    metrics: {
      tokensIn: 180000,
      tokensOut: 65700,
      totalTokens: 245700,
      cost: 0.4913,
      startTime: new Date(Date.now() - 3600000).toISOString(),
      duration: 3600,
    },
    context: {
      used: 95000,
      total: 128000,
      percentage: 74,
    },
    tasks: [
      { id: "t1", label: "coordinate", status: "completed" },
      { id: "t2", label: "delegate", status: "in_progress" },
      { id: "t3", label: "monitor", status: "pending" },
      { id: "t4", label: "report", status: "pending" },
    ],
    currentCommand: "analyzing task dependencies...",
  },
  {
    id: "agent-002",
    name: "Perf-Analyzer",
    type: "performance",
    status: "active",
    metrics: {
      tokensIn: 130000,
      tokensOut: 48900,
      totalTokens: 178900,
      cost: 0.3578,
      startTime: new Date(Date.now() - 1800000).toISOString(),
      duration: 1800,
    },
    context: {
      used: 56000,
      total: 128000,
      percentage: 44,
    },
    tasks: [
      { id: "t1", label: "benchmark", status: "completed" },
      { id: "t2", label: "profile", status: "in_progress" },
      { id: "t3", label: "optimize", status: "pending" },
    ],
    currentCommand: "running lighthouse audit...",
  },
  {
    id: "agent-003",
    name: "Code-Executor-A1",
    type: "executor",
    status: "active",
    metrics: {
      tokensIn: 140000,
      tokensOut: 49400,
      totalTokens: 189400,
      cost: 0.3788,
      startTime: new Date(Date.now() - 2400000).toISOString(),
      duration: 2400,
    },
    context: {
      used: 72000,
      total: 128000,
      percentage: 56,
    },
    tasks: [
      { id: "t1", label: "compile", status: "completed" },
      { id: "t2", label: "execute", status: "in_progress" },
      { id: "t3", label: "test", status: "pending" },
    ],
    currentCommand: "npm run build --production",
  },
  {
    id: "agent-004",
    name: "Doc-Writer-V2",
    type: "docs-writer",
    status: "active",
    metrics: {
      tokensIn: 72000,
      tokensOut: 26300,
      totalTokens: 98300,
      cost: 0.1967,
      startTime: new Date(Date.now() - 1200000).toISOString(),
      duration: 1200,
    },
    context: {
      used: 110000,
      total: 128000,
      percentage: 86,
    },
    tasks: [
      { id: "t1", label: "document", status: "in_progress" },
      { id: "t2", label: "format", status: "pending" },
    ],
    currentCommand: "generating API documentation...",
  },
  {
    id: "agent-005",
    name: "Research-Scout",
    type: "research",
    status: "pending",
    metrics: {
      tokensIn: 115000,
      tokensOut: 41200,
      totalTokens: 156200,
      cost: 0.3124,
      startTime: new Date(Date.now() - 600000).toISOString(),
      duration: 600,
    },
    context: {
      used: 45000,
      total: 128000,
      percentage: 35,
    },
    tasks: [
      { id: "t1", label: "search", status: "completed" },
      { id: "t2", label: "analyze", status: "in_progress" },
      { id: "t3", label: "summarize", status: "pending" },
    ],
    currentCommand: "awaiting user confirmation...",
  },
  {
    id: "agent-006",
    name: "Test-Runner-01",
    type: "test-runner",
    status: "pending",
    metrics: {
      tokensIn: 50000,
      tokensOut: 17900,
      totalTokens: 67900,
      cost: 0.1358,
      startTime: new Date(Date.now() - 300000).toISOString(),
      duration: 300,
    },
    context: {
      used: 89000,
      total: 128000,
      percentage: 70,
    },
    tasks: [
      { id: "t1", label: "unit-test", status: "completed" },
      { id: "t2", label: "integration-test", status: "in_progress" },
      { id: "t3", label: "coverage", status: "pending" },
    ],
    currentCommand: "waiting for build completion...",
  },
  {
    id: "agent-007",
    name: "Deploy-Agent",
    type: "deployer",
    status: "completed",
    metrics: {
      tokensIn: 172000,
      tokensOut: 62500,
      totalTokens: 234500,
      cost: 0.469,
      startTime: new Date(Date.now() - 7200000).toISOString(),
      endTime: new Date(Date.now() - 3600000).toISOString(),
      duration: 3600,
    },
    context: {
      used: 128000,
      total: 128000,
      percentage: 100,
    },
    tasks: [
      { id: "t1", label: "deploy", status: "completed" },
      { id: "t2", label: "verify", status: "completed" },
      { id: "t3", label: "rollback", status: "completed" },
    ],
    currentCommand: "deployment successful ✓",
  },
  {
    id: "agent-008",
    name: "Security-Scan",
    type: "security",
    status: "completed",
    metrics: {
      tokensIn: 34000,
      tokensOut: 11600,
      totalTokens: 45600,
      cost: 0.0912,
      startTime: new Date(Date.now() - 5400000).toISOString(),
      endTime: new Date(Date.now() - 3600000).toISOString(),
      duration: 1800,
    },
    context: {
      used: 128000,
      total: 128000,
      percentage: 100,
    },
    tasks: [
      { id: "t1", label: "scan", status: "completed" },
      { id: "t2", label: "audit", status: "completed" },
    ],
    currentCommand: "no vulnerabilities found ✓",
  },
];

export function getMockAgentRegistry(): AgentRegistry {
  const agents = MOCK_AGENTS;

  return {
    agents,
    activeCount: agents.filter((a) => a.status === "active").length,
    pendingCount: agents.filter((a) => a.status === "pending").length,
    completedCount: agents.filter((a) => a.status === "completed").length,
    errorCount: agents.filter((a) => a.status === "error").length,
  };
}

export function getMockAgents(): AgentState[] {
  return MOCK_AGENTS;
}
