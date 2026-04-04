/**
 * Type definitions for the web-viewer dashboard
 * Adapted from orchestrator.json and session.json structures
 */

// ===== Agent Types =====

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

export type AgentStatus = 'active' | 'pending' | 'completed' | 'error';
export type AgentType = 'explorer' | 'orchestrator' | 'worker' | 'debugger';

export interface Agent {
  id: string;
  name: string;
  type: AgentType;
  status: AgentStatus;
  plan: string;
  metrics: AgentMetrics;
  context: AgentContext;
  tasks: string[];
  currentCommand: string;
}

export interface AgentSummary {
  agents: Agent[];
  activeCount: number;
  pendingCount: number;
  completedCount: number;
  errorCount: number;
}

// ===== Cost Types =====

export interface CostSummary {
  today: number;
  sessions: number;
  sevenDay: number;
  thirtyDay: number;
}

// ===== Instance Types (for multitask support) =====

export interface MultitaskInstance {
  id: number;
  worktree: string;
  branch: string;
  plan: string;
  /**
   * Multitask instance lifecycle status.
   *
   * Note: This mirrors `.claude/state/multitask-session.json` and recovery logic
   * in `scripts/multitask.sh`.
   */
  status: 'running' | 'paused' | 'completed' | 'crashed' | 'stopped' | 'active';
  pid?: number;
  logFile?: string;
  name?: string;
  /** ISO timestamp of last health check by the orchestrator */
  lastHeartbeat?: string;
  /** Process exit code (null while running) */
  exitCode?: number | null;
  /** ISO timestamp when the process exited */
  exitedAt?: string;
  /** Elapsed seconds since instance started */
  runtimeSeconds?: number;
  /** Number of times this instance has crashed */
  crashCount?: number;
  /** Structured crash event log */
  crashLog?: CrashEvent[];
}

export interface CrashEvent {
  timestamp: string;
  exitCode: number;
  pid: number;
  runtimeSeconds: number;
  message: string;
}

// ===== Process Types (generic for multitask + future pipeline runner) =====

export interface ProcessEntry extends MultitaskInstance {
  /** Discriminator for source system */
  source?: 'multitask' | 'pipeline';
}

export type ProcessMap = Record<string, ProcessEntry>;

// ===== Orchestrator Types =====

export interface OrchestratorState {
  version: string;
  updated_at: string;
  agents: AgentSummary;
  costs: CostSummary;
  instances?: ProcessMap;
}

// ===== Session Types =====

export interface PlanInfo {
  path: string;
  name: string;
  branch: string;
}

export interface ProgressInfo {
  total_stories: number;
  completed: number;
  current_story: string;
  current_iteration: number;
}

export interface SessionAgent {
  id: string;
  joined_at: string;
  role: 'worker' | 'orchestrator';
  departed_at?: string;
}

export interface GitInfo {
  branch: string;
  head_commit: string;
  modified_files: string[];
}

export interface ExecutionInfo {
  mode: 'autonomous' | 'manual' | 'interactive';
  pid?: number;
  start_time: string;
}

export type ActivityType = 'story_started' | 'story_completed' | 'error' | 'checkpoint';

export interface ActivityLogEntry {
  timestamp: string;
  type: ActivityType;
  story?: string;
  message: string;
}

export interface SessionState {
  version: string;
  plan_id: string;
  created_at: string;
  updated_at: string;
  status: 'running' | 'paused' | 'completed' | 'failed';
  plan: PlanInfo;
  progress: ProgressInfo;
  agents: SessionAgent[];
  file_claims: string[];
  git: GitInfo;
  execution: ExecutionInfo;
  activity_log: ActivityLogEntry[];
}

// ===== Plan Types =====

export type StoryType = 'Setup' | 'Core' | 'UI' | 'API' | 'Data' | 'Test' | 'Docs';

export interface Story {
  id: string;
  title: string;
  type: StoryType;
  priority: number;
  passes: boolean;
  depends?: string[];
  files: string[];
  acceptance: string;
}

export interface PlanDefinition {
  feature: string;
  branch: string;
  status: 'planned' | 'in-progress' | 'completed';
  created: string;
  stories: Story[];
}

// ===== WebSocket Message Types =====

export interface StateUpdateMessage {
  type: 'state_update';
  orchestrator?: OrchestratorState;
  session?: SessionState;
  plan?: PlanDefinition;
  plans?: Record<string, PlanDefinition>;
  pipelines?: Record<string, PipelineState>;
}

export interface LogMessage {
  type: 'log';
  instanceId: string;
  lines: string[];
}

export interface ErrorMessage {
  type: 'error';
  message: string;
}

export type WebSocketMessage = StateUpdateMessage | LogMessage | ErrorMessage;

// ===== Pipeline Types =====

export type PipelineStatus = 'pending' | 'running' | 'completed' | 'failed' | 'paused';
export type PipelineNodeStatus = 'pending' | 'queued' | 'running' | 'completed' | 'failed' | 'skipped';
export type PipelineNodeType = 'task' | 'plan' | 'gate' | 'shell';
export type PipelineBackend = 'claude-code' | 'cursor' | 'shell' | 'manual';

export interface PipelineNode {
  id: string;
  type: PipelineNodeType;
  name: string;
  status: PipelineNodeStatus;
  backend: PipelineBackend;
  command?: string | null;
  depends: string[];
  startedAt?: string | null;
  completedAt?: string | null;
  exitCode?: number | null;
  pid?: number | null;
  attempt: number;
  logFile?: string | null;
  runtimeSeconds: number;
  error?: string | null;
}

export interface PipelineCheckpoint {
  savedAt: string;
  completedNodes: string[];
  failedNodes: string[];
  skippedNodes: string[];
}

export interface PipelineState {
  version: string;
  pipelineId: string;
  definitionPath: string;
  status: PipelineStatus;
  createdAt: string;
  updatedAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
  executionOrder: string[];
  parallelGroups: string[][];
  nodes: Record<string, PipelineNode>;
  checkpoint: PipelineCheckpoint;
}

/** Raw on-disk format written by pipeline.sh (snake_case) */
export interface PipelineStateRaw {
  version: string;
  pipeline_id: string;
  definition_path: string;
  status: string;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  execution_order: string[];
  parallel_groups: string[][];
  nodes: Record<string, PipelineNodeRaw>;
  checkpoint: PipelineCheckpointRaw;
}

export interface PipelineNodeRaw {
  id: string;
  type: string;
  name?: string;
  status: string;
  backend?: string;
  command?: string | null;
  depends?: string[];
  started_at?: string | null;
  completed_at?: string | null;
  exit_code?: number | null;
  pid?: number | null;
  attempt?: number;
  log_file?: string | null;
  runtime_seconds?: number;
  error?: string | null;
}

export interface PipelineCheckpointRaw {
  saved_at: string;
  completed_nodes?: string[];
  failed_nodes?: string[];
  skipped_nodes?: string[];
}

// ===== Multitask Session =====

export interface MultitaskSession {
  version: string;
  created_at: string;
  instances: MultitaskInstance[];
}

// ===== Raw Multitask Session (on-disk format from multitask.sh) =====

/**
 * Shape written by multitask.sh to .claude/state/multitask-session.json.
 * The adapter translates this into OrchestratorState for the dashboard.
 */
export interface MultitaskSessionRaw {
  session_id: string;
  started: string;
  tui_enabled: boolean;
  use_happy_cli: boolean;
  max_iterations: number;
  instances: MultitaskInstanceRaw[];
  web_viewer_pid?: number;
  tui_pid?: string;
}

export interface CrashEventRaw {
  timestamp: string;
  exit_code: number;
  pid: number;
  runtime_seconds: number;
  message: string;
}

export interface MultitaskInstanceRaw {
  instance_num: number;
  worktree: string;
  branch: string;
  plan: string;
  pid: number;
  status: string;
  started: string;
  log_file: string;
  /** ISO timestamp of last health check by the orchestrator */
  last_heartbeat?: string;
  /** Process exit code (null while running) */
  exit_code?: number | null;
  /** ISO timestamp when the process exited */
  exited_at?: string;
  /** Elapsed seconds since instance started */
  runtime_seconds?: number;
  /** Number of times this instance has crashed */
  crash_count?: number;
  /** Structured crash event log */
  crash_log?: CrashEventRaw[];
}
