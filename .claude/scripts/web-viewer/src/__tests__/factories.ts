/**
 * Shared mock data factories for web-viewer tests.
 * Each factory returns a valid default object; pass Partial<T> to override fields.
 */

import type {
  Agent,
  AgentMetrics,
  AgentContext,
  AgentSummary,
  CostSummary,
  OrchestratorState,
  SessionState,
  PlanDefinition,
  PlanInfo,
  ProgressInfo,
  SessionAgent,
  GitInfo,
  ExecutionInfo,
  ActivityLogEntry,
  Story,
  MultitaskInstance,
} from '../../src/types.js';

export function createMockMetrics(overrides: Partial<AgentMetrics> = {}): AgentMetrics {
  return {
    tokensIn: 12000,
    tokensOut: 4500,
    totalTokens: 16500,
    cost: 0.15,
    startTime: '2026-02-05T10:00:00Z',
    ...overrides,
  };
}

export function createMockContext(overrides: Partial<AgentContext> = {}): AgentContext {
  return {
    used: 50000,
    total: 200000,
    percentage: 25,
    ...overrides,
  };
}

export function createMockAgent(overrides: Partial<Agent> = {}): Agent {
  const { metrics: _m, context: _c, ...rest } = overrides;
  return {
    id: 'agent-1',
    name: 'Test Worker',
    type: 'worker',
    status: 'active',
    plan: 'test-plan',
    metrics: createMockMetrics(overrides.metrics),
    context: createMockContext(overrides.context),
    tasks: ['task-1'],
    currentCommand: 'Running tests',
    ...rest,
  };
}

export function createMockCosts(overrides: Partial<CostSummary> = {}): CostSummary {
  return {
    today: 5.25,
    sessions: 12,
    sevenDay: 32.50,
    thirtyDay: 120.00,
    ...overrides,
  };
}

export function createMockAgentSummary(overrides: Partial<AgentSummary> = {}): AgentSummary {
  return {
    agents: overrides.agents ?? [createMockAgent()],
    activeCount: 1,
    pendingCount: 0,
    completedCount: 0,
    errorCount: 0,
    ...overrides,
  };
}

export function createMockOrchestratorState(overrides: Partial<OrchestratorState> = {}): OrchestratorState {
  const { agents: _a, costs: _c, ...rest } = overrides;
  return {
    version: '1.0',
    updated_at: '2026-02-05T10:00:00Z',
    agents: createMockAgentSummary(overrides.agents),
    costs: createMockCosts(overrides.costs),
    ...rest,
  };
}

export function createMockPlanInfo(overrides: Partial<PlanInfo> = {}): PlanInfo {
  return {
    path: 'docs/plans/test-plan.json',
    name: 'test-plan',
    branch: 'feature/test-plan',
    ...overrides,
  };
}

export function createMockProgressInfo(overrides: Partial<ProgressInfo> = {}): ProgressInfo {
  return {
    total_stories: 8,
    completed: 3,
    current_story: 'S4',
    current_iteration: 4,
    ...overrides,
  };
}

export function createMockSessionAgent(overrides: Partial<SessionAgent> = {}): SessionAgent {
  return {
    id: 'worker-1',
    joined_at: '2026-02-05T10:00:00Z',
    role: 'worker',
    ...overrides,
  };
}

export function createMockGitInfo(overrides: Partial<GitInfo> = {}): GitInfo {
  return {
    branch: 'feature/test-plan',
    head_commit: 'abc123',
    modified_files: ['src/index.ts'],
    ...overrides,
  };
}

export function createMockExecutionInfo(overrides: Partial<ExecutionInfo> = {}): ExecutionInfo {
  return {
    mode: 'autonomous',
    pid: 12345,
    start_time: '2026-02-05T10:00:00Z',
    ...overrides,
  };
}

export function createMockActivityLogEntry(overrides: Partial<ActivityLogEntry> = {}): ActivityLogEntry {
  return {
    timestamp: '2026-02-05T10:05:00Z',
    type: 'story_completed',
    story: 'S3',
    message: 'Story S3 completed successfully',
    ...overrides,
  };
}

export function createMockSessionState(overrides: Partial<SessionState> = {}): SessionState {
  const {
    plan: _p,
    progress: _pr,
    agents: _a,
    git: _g,
    execution: _e,
    activity_log: _al,
    ...rest
  } = overrides;
  return {
    version: '1.0',
    plan_id: 'test-plan',
    created_at: '2026-02-05T10:00:00Z',
    updated_at: '2026-02-05T10:05:00Z',
    status: 'running',
    plan: createMockPlanInfo(overrides.plan),
    progress: createMockProgressInfo(overrides.progress),
    agents: overrides.agents ?? [createMockSessionAgent()],
    file_claims: ['src/index.ts'],
    git: createMockGitInfo(overrides.git),
    execution: createMockExecutionInfo(overrides.execution),
    activity_log: overrides.activity_log ?? [createMockActivityLogEntry()],
    ...rest,
  };
}

export function createMockStory(overrides: Partial<Story> = {}): Story {
  return {
    id: 'S1',
    title: 'Setup project scaffolding',
    type: 'Setup',
    priority: 1,
    passes: false,
    files: ['src/index.ts'],
    acceptance: 'Project builds successfully',
    ...overrides,
  };
}

export function createMockPlanDefinition(overrides: Partial<PlanDefinition> = {}): PlanDefinition {
  return {
    feature: 'test-feature',
    branch: 'feature/test-plan',
    status: 'in-progress',
    created: '2026-02-05T10:00:00Z',
    stories: overrides.stories ?? [
      createMockStory({ id: 'S1', title: 'Setup scaffolding', type: 'Setup', priority: 1, passes: true }),
      createMockStory({ id: 'S2', title: 'Implement data models', type: 'Core', priority: 2 }),
      createMockStory({ id: 'S3', title: 'Add API endpoints', type: 'API', priority: 3 }),
    ],
    ...overrides,
  };
}

export function createMockMultitaskInstance(overrides: Partial<MultitaskInstance> = {}): MultitaskInstance {
  return {
    id: 1,
    worktree: '/tmp/test-worktree',
    branch: 'feature/test-plan',
    plan: 'test-plan',
    status: 'active',
    pid: 12345,
    logFile: '/tmp/test-worktree/.claude/logs/instance-1.log',
    name: 'instance-1',
    ...overrides,
  };
}

/**
 * Create a raw orchestrator JSON object (simulating what's read from disk).
 * Useful for testing parsers with realistic JSON input.
 */
export function createRawOrchestratorJson(overrides: Partial<OrchestratorState> = {}): Record<string, unknown> {
  const state = createMockOrchestratorState(overrides);
  return JSON.parse(JSON.stringify(state));
}

/**
 * Create a raw session JSON object (simulating what's read from disk).
 */
export function createRawSessionJson(overrides: Partial<SessionState> = {}): Record<string, unknown> {
  const state = createMockSessionState(overrides);
  return JSON.parse(JSON.stringify(state));
}
