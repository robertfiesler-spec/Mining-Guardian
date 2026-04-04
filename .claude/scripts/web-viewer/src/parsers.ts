/**
 * Pure parsing functions for converting raw JSON into typed structures.
 * Extracted from StateManager for independent testability.
 */

import type {
  Agent,
  OrchestratorState,
  SessionState,
  SessionAgent,
  ActivityLogEntry,
  MultitaskInstance,
  MultitaskSessionRaw,
  MultitaskInstanceRaw,
  CrashEvent,
  CrashEventRaw,
  PipelineState,
  PipelineNode,
  PipelineCheckpoint,
  PipelineStatus,
  PipelineNodeStatus,
  PipelineNodeType,
  PipelineBackend,
} from './types.js';

/**
 * Type guard to check if a value is a plain object (record)
 */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Parse orchestrator.json data into typed structure
 */
export function parseOrchestratorState(raw: unknown): OrchestratorState {
  if (!isRecord(raw)) {
    throw new Error('Invalid orchestrator.json structure: expected object');
  }

  if (!raw.version || !raw.updated_at || !raw.agents || !raw.costs) {
    throw new Error('Invalid orchestrator.json structure');
  }

  const rawAgents = isRecord(raw.agents) ? raw.agents : {};
  const agents = Array.isArray(rawAgents.agents)
    ? rawAgents.agents.map(parseAgent)
    : [];

  const rawCosts = isRecord(raw.costs) ? raw.costs : {};
  const instances = parseMultitaskInstances(raw.instances);

  return {
    version: String(raw.version),
    updated_at: String(raw.updated_at),
    agents: {
      agents,
      activeCount: Number(rawAgents.activeCount) || 0,
      pendingCount: Number(rawAgents.pendingCount) || 0,
      completedCount: Number(rawAgents.completedCount) || 0,
      errorCount: Number(rawAgents.errorCount) || 0,
    },
    costs: {
      today: Number(rawCosts.today) || 0,
      sessions: Number(rawCosts.sessions) || 0,
      sevenDay: Number(rawCosts.sevenDay) || 0,
      thirtyDay: Number(rawCosts.thirtyDay) || 0,
    },
    ...(instances ? { instances } : {}),
  };
}

/**
 * Parse multitask instances (if present) into a normalized record.
 *
 * Accepts either:
 * - A record keyed by instance id: `{ "1": { ... }, "2": { ... } }`
 * - An array of instances (e.g. `.claude/state/multitask-session.json`): `[ { instance_num, ... }, ... ]`
 */
export function parseMultitaskInstances(
  rawInstances: unknown,
): Record<string, MultitaskInstance> | undefined {
  if (!rawInstances) return undefined;

  if (Array.isArray(rawInstances)) {
    const entries = rawInstances
      .map((rawInstance, index) => {
        const parsed = parseMultitaskInstance(rawInstance, index);
        const key = getMultitaskInstanceKey(rawInstance, parsed, index);
        return [key, parsed] as const;
      })
      .filter(([key]) => key.length > 0);

    const record = Object.fromEntries(entries) as Record<
      string,
      MultitaskInstance
    >;
    return Object.keys(record).length > 0 ? record : undefined;
  }

  if (isRecord(rawInstances)) {
    const entries = Object.entries(rawInstances)
      .map(([key, rawInstance], index) => {
        const parsed = parseMultitaskInstance(rawInstance, index);
        const normalizedKey =
          key || getMultitaskInstanceKey(rawInstance, parsed, index);
        return [String(normalizedKey), parsed] as const;
      })
      .filter(([key]) => key.length > 0);

    const record = Object.fromEntries(entries) as Record<
      string,
      MultitaskInstance
    >;
    return Object.keys(record).length > 0 ? record : undefined;
  }

  return undefined;
}

/**
 * Get a key for a multitask instance based on available identifiers
 */
export function getMultitaskInstanceKey(
  rawInstance: unknown,
  parsed: MultitaskInstance,
  index: number,
): string {
  if (isRecord(rawInstance)) {
    const instanceNum = rawInstance.instance_num;
    if (typeof instanceNum === 'number' && Number.isFinite(instanceNum))
      return String(instanceNum);

    const id = rawInstance.id;
    if (typeof id === 'number' && Number.isFinite(id)) return String(id);
  }

  if (Number.isFinite(parsed.id)) return String(parsed.id);
  return String(index + 1);
}

/**
 * Parse a single multitask instance
 */
export function parseMultitaskInstance(
  rawInstance: unknown,
  index: number,
): MultitaskInstance {
  if (!isRecord(rawInstance)) {
    return {
      id: index + 1,
      worktree: '',
      branch: '',
      plan: '',
      status: 'running',
      name: String(index + 1),
    };
  }

  const id = parseInstanceId(rawInstance, index);
  const status = normalizeInstanceStatus(rawInstance.status);

  const branch =
    typeof rawInstance.branch === 'string' ? rawInstance.branch : '';
  const plan = typeof rawInstance.plan === 'string' ? rawInstance.plan : '';

  const logFile =
    typeof rawInstance.logFile === 'string'
      ? rawInstance.logFile
      : typeof rawInstance.log_file === 'string'
        ? rawInstance.log_file
        : undefined;

  const name =
    typeof rawInstance.name === 'string' && rawInstance.name.trim().length > 0
      ? rawInstance.name
      : branch || `Instance ${id}`;

  return {
    id,
    worktree:
      typeof rawInstance.worktree === 'string' ? rawInstance.worktree : '',
    branch,
    plan,
    status,
    pid: typeof rawInstance.pid === 'number' ? rawInstance.pid : undefined,
    logFile,
    name,
    lastHeartbeat:
      typeof rawInstance.last_heartbeat === 'string'
        ? rawInstance.last_heartbeat
        : undefined,
    exitCode:
      rawInstance.exit_code === null
        ? null
        : typeof rawInstance.exit_code === 'number'
          ? rawInstance.exit_code
          : undefined,
    exitedAt:
      typeof rawInstance.exited_at === 'string'
        ? rawInstance.exited_at
        : undefined,
    runtimeSeconds:
      typeof rawInstance.runtime_seconds === 'number'
        ? rawInstance.runtime_seconds
        : undefined,
    crashCount:
      typeof rawInstance.crash_count === 'number'
        ? rawInstance.crash_count
        : undefined,
    crashLog: Array.isArray(rawInstance.crash_log)
      ? rawInstance.crash_log.map(parseCrashEvent)
      : undefined,
  };
}

/**
 * Parse the instance ID from raw data
 */
export function parseInstanceId(
  rawInstance: Record<string, unknown>,
  index: number,
): number {
  const instanceNum = rawInstance.instance_num;
  if (typeof instanceNum === 'number' && Number.isFinite(instanceNum))
    return instanceNum;

  const id = rawInstance.id;
  if (typeof id === 'number' && Number.isFinite(id)) return id;

  return index + 1;
}

/**
 * Normalize instance status to valid enum values
 */
export function normalizeInstanceStatus(
  rawStatus: unknown,
): MultitaskInstance['status'] {
  if (typeof rawStatus !== 'string') return 'running';

  switch (rawStatus) {
    case 'running':
    case 'paused':
    case 'completed':
    case 'crashed':
    case 'stopped':
    case 'active':
      return rawStatus;
    default:
      // Back-compat / unknown values: treat as running so instances still show up.
      return 'running';
  }
}

/**
 * Parse a single agent object
 */
export function parseAgent(raw: unknown): Agent {
  const r = isRecord(raw) ? raw : {};
  const metrics = isRecord(r.metrics) ? r.metrics : {};
  const context = isRecord(r.context) ? r.context : {};

  return {
    id: String(r.id || ''),
    name: String(r.name || 'Unknown'),
    type: (r.type as Agent['type']) || 'worker',
    status: (r.status as Agent['status']) || 'pending',
    plan: String(r.plan || ''),
    metrics: {
      tokensIn: Number(metrics.tokensIn) || 0,
      tokensOut: Number(metrics.tokensOut) || 0,
      totalTokens: Number(metrics.totalTokens) || 0,
      cost: Number(metrics.cost) || 0,
      startTime: String(metrics.startTime || ''),
      endTime: metrics.endTime ? String(metrics.endTime) : undefined,
      duration: metrics.duration ? Number(metrics.duration) : undefined,
    },
    context: {
      used: Number(context.used) || 0,
      total: Number(context.total) || 200000,
      percentage: Number(context.percentage) || 0,
    },
    tasks: Array.isArray(r.tasks) ? r.tasks.map(String) : [],
    currentCommand: String(r.currentCommand || ''),
  };
}

/**
 * Parse session.json data into typed structure
 */
export function parseSessionState(raw: unknown): SessionState {
  if (!isRecord(raw)) {
    throw new Error('Invalid session.json structure: expected object');
  }

  if (!raw.version || !raw.plan_id || !raw.created_at) {
    throw new Error('Invalid session.json structure');
  }

  const agents = Array.isArray(raw.agents)
    ? raw.agents.map(parseSessionAgent)
    : [];

  const activity_log = Array.isArray(raw.activity_log)
    ? raw.activity_log.map(parseActivityLogEntry)
    : [];

  const plan = isRecord(raw.plan) ? raw.plan : {};
  const progress = isRecord(raw.progress) ? raw.progress : {};
  const git = isRecord(raw.git) ? raw.git : {};
  const execution = isRecord(raw.execution) ? raw.execution : {};

  return {
    version: String(raw.version),
    plan_id: String(raw.plan_id),
    created_at: String(raw.created_at),
    updated_at: String(raw.updated_at || raw.created_at),
    status: (raw.status as SessionState['status']) || 'running',
    plan: {
      path: String(plan.path || ''),
      name: String(plan.name || ''),
      branch: String(plan.branch || ''),
    },
    progress: {
      total_stories: Number(progress.total_stories) || 0,
      completed: Number(progress.completed) || 0,
      current_story: String(progress.current_story || ''),
      current_iteration: Number(progress.current_iteration) || 0,
    },
    agents,
    file_claims: Array.isArray(raw.file_claims)
      ? raw.file_claims.map(String)
      : [],
    git: {
      branch: String(git.branch || ''),
      head_commit: String(git.head_commit || ''),
      modified_files: Array.isArray(git.modified_files)
        ? git.modified_files.map(String)
        : [],
    },
    execution: {
      mode: (execution.mode as 'autonomous' | 'manual' | 'interactive') || 'manual',
      pid: execution.pid ? Number(execution.pid) : undefined,
      start_time: String(execution.start_time || raw.created_at),
    },
    activity_log,
  };
}

/**
 * Parse a session agent entry
 */
export function parseSessionAgent(raw: unknown): SessionAgent {
  const r = isRecord(raw) ? raw : {};
  return {
    id: String(r.id || ''),
    joined_at: String(r.joined_at || ''),
    role: (r.role as SessionAgent['role']) || 'worker',
    departed_at: r.departed_at ? String(r.departed_at) : undefined,
  };
}

/**
 * Parse an activity log entry
 */
export function parseActivityLogEntry(raw: unknown): ActivityLogEntry {
  const r = isRecord(raw) ? raw : {};
  return {
    timestamp: String(r.timestamp || ''),
    type: (r.type as ActivityLogEntry['type']) || 'checkpoint',
    story: r.story ? String(r.story) : undefined,
    message: String(r.message || ''),
  };
}

/**
 * Parse raw JSON from multitask-session.json into MultitaskSessionRaw.
 * Returns null if the input is not a valid multitask session.
 */
export function parseMultitaskSessionRaw(raw: unknown): MultitaskSessionRaw | null {
  if (!isRecord(raw)) return null;
  if (typeof raw.session_id !== 'string') return null;
  if (!Array.isArray(raw.instances)) return null;

  return {
    session_id: raw.session_id,
    started: typeof raw.started === 'string' ? raw.started : new Date().toISOString(),
    tui_enabled: raw.tui_enabled === true,
    use_happy_cli: raw.use_happy_cli === true,
    max_iterations: typeof raw.max_iterations === 'number' ? raw.max_iterations : 50,
    instances: raw.instances.map(parseMultitaskInstanceRaw),
    web_viewer_pid: typeof raw.web_viewer_pid === 'number' ? raw.web_viewer_pid : undefined,
    tui_pid: typeof raw.tui_pid === 'string' ? raw.tui_pid : undefined,
  };
}

/**
 * Parse a single raw multitask instance from multitask-session.json.
 */
function parseMultitaskInstanceRaw(raw: unknown): MultitaskInstanceRaw {
  const r = isRecord(raw) ? raw : {};
  return {
    instance_num: typeof r.instance_num === 'number' ? r.instance_num : 0,
    worktree: typeof r.worktree === 'string' ? r.worktree : '',
    branch: typeof r.branch === 'string' ? r.branch : '',
    plan: typeof r.plan === 'string' ? r.plan : '',
    pid: typeof r.pid === 'number' ? r.pid : 0,
    status: typeof r.status === 'string' ? r.status : 'running',
    started: typeof r.started === 'string' ? r.started : '',
    log_file: typeof r.log_file === 'string' ? r.log_file : '',
    last_heartbeat: typeof r.last_heartbeat === 'string' ? r.last_heartbeat : undefined,
    exit_code: r.exit_code === null ? null : (typeof r.exit_code === 'number' ? r.exit_code : undefined),
    exited_at: typeof r.exited_at === 'string' ? r.exited_at : undefined,
    runtime_seconds: typeof r.runtime_seconds === 'number' ? r.runtime_seconds : undefined,
    crash_count: typeof r.crash_count === 'number' ? r.crash_count : undefined,
    crash_log: Array.isArray(r.crash_log) ? r.crash_log.map(parseCrashEventRaw) : undefined,
  };
}

/**
 * Parse a raw crash event from the crash_log array.
 */
function parseCrashEventRaw(raw: unknown): CrashEventRaw {
  const r = isRecord(raw) ? raw : {};
  return {
    timestamp: typeof r.timestamp === 'string' ? r.timestamp : '',
    exit_code: typeof r.exit_code === 'number' ? r.exit_code : 0,
    pid: typeof r.pid === 'number' ? r.pid : 0,
    runtime_seconds: typeof r.runtime_seconds === 'number' ? r.runtime_seconds : 0,
    message: typeof r.message === 'string' ? r.message : '',
  };
}

/**
 * Parse a crash event from raw instance data into the normalized CrashEvent type.
 */
function parseCrashEvent(raw: unknown): CrashEvent {
  const r = isRecord(raw) ? raw : {};
  return {
    timestamp: typeof r.timestamp === 'string' ? r.timestamp : '',
    exitCode: typeof r.exit_code === 'number' ? r.exit_code : (typeof r.exitCode === 'number' ? r.exitCode : 0),
    pid: typeof r.pid === 'number' ? r.pid : 0,
    runtimeSeconds: typeof r.runtime_seconds === 'number' ? r.runtime_seconds : (typeof r.runtimeSeconds === 'number' ? r.runtimeSeconds : 0),
    message: typeof r.message === 'string' ? r.message : '',
  };
}

/**
 * Parse a pipeline state file (pipeline-{id}.json) into typed PipelineState.
 * Returns null if the input is not a valid pipeline state.
 */
export function parsePipelineState(raw: unknown): PipelineState | null {
  if (!isRecord(raw)) return null;
  if (typeof raw.pipeline_id !== 'string') return null;
  if (!isRecord(raw.nodes)) return null;

  const nodes: Record<string, PipelineNode> = {};
  for (const [id, rawNode] of Object.entries(raw.nodes as Record<string, unknown>)) {
    nodes[id] = parsePipelineNode(rawNode, id);
  }

  return {
    version: typeof raw.version === 'string' ? raw.version : '1.0',
    pipelineId: raw.pipeline_id,
    definitionPath: typeof raw.definition_path === 'string' ? raw.definition_path : '',
    status: normalizePipelineStatus(raw.status),
    createdAt: typeof raw.created_at === 'string' ? raw.created_at : '',
    updatedAt: typeof raw.updated_at === 'string' ? raw.updated_at : '',
    startedAt: typeof raw.started_at === 'string' ? raw.started_at : null,
    completedAt: typeof raw.completed_at === 'string' ? raw.completed_at : null,
    executionOrder: Array.isArray(raw.execution_order)
      ? raw.execution_order.map(String)
      : [],
    parallelGroups: Array.isArray(raw.parallel_groups)
      ? raw.parallel_groups.map((g: unknown) => Array.isArray(g) ? g.map(String) : [])
      : [],
    nodes,
    checkpoint: parsePipelineCheckpoint(raw.checkpoint),
  };
}

/**
 * Parse a single pipeline node from raw state data.
 */
export function parsePipelineNode(raw: unknown, fallbackId: string): PipelineNode {
  const r = isRecord(raw) ? raw : {};
  return {
    id: typeof r.id === 'string' ? r.id : fallbackId,
    type: normalizePipelineNodeType(r.type),
    name: typeof r.name === 'string' ? r.name : fallbackId,
    status: normalizePipelineNodeStatus(r.status),
    backend: normalizePipelineBackend(r.backend),
    command: typeof r.command === 'string' ? r.command : null,
    depends: Array.isArray(r.depends) ? r.depends.map(String) : [],
    startedAt: typeof r.started_at === 'string' ? r.started_at : null,
    completedAt: typeof r.completed_at === 'string' ? r.completed_at : null,
    exitCode: r.exit_code === null ? null : (typeof r.exit_code === 'number' ? r.exit_code : null),
    pid: r.pid === null ? null : (typeof r.pid === 'number' ? r.pid : null),
    attempt: typeof r.attempt === 'number' ? r.attempt : 0,
    logFile: typeof r.log_file === 'string' ? r.log_file : null,
    runtimeSeconds: typeof r.runtime_seconds === 'number' ? r.runtime_seconds : 0,
    error: typeof r.error === 'string' ? r.error : null,
  };
}

/**
 * Parse pipeline checkpoint data.
 */
export function parsePipelineCheckpoint(raw: unknown): PipelineCheckpoint {
  const r = isRecord(raw) ? raw : {};
  return {
    savedAt: typeof r.saved_at === 'string' ? r.saved_at : '',
    completedNodes: Array.isArray(r.completed_nodes) ? r.completed_nodes.map(String) : [],
    failedNodes: Array.isArray(r.failed_nodes) ? r.failed_nodes.map(String) : [],
    skippedNodes: Array.isArray(r.skipped_nodes) ? r.skipped_nodes.map(String) : [],
  };
}

/**
 * Normalize pipeline status to valid enum value.
 */
export function normalizePipelineStatus(raw: unknown): PipelineStatus {
  if (typeof raw !== 'string') return 'pending';
  switch (raw) {
    case 'pending':
    case 'running':
    case 'completed':
    case 'failed':
    case 'paused':
      return raw;
    default:
      return 'pending';
  }
}

/**
 * Normalize pipeline node status to valid enum value.
 */
export function normalizePipelineNodeStatus(raw: unknown): PipelineNodeStatus {
  if (typeof raw !== 'string') return 'pending';
  switch (raw) {
    case 'pending':
    case 'queued':
    case 'running':
    case 'completed':
    case 'failed':
    case 'skipped':
      return raw;
    default:
      return 'pending';
  }
}

/**
 * Normalize pipeline node type to valid enum value.
 */
export function normalizePipelineNodeType(raw: unknown): PipelineNodeType {
  if (typeof raw !== 'string') return 'shell';
  switch (raw) {
    case 'task':
    case 'plan':
    case 'gate':
    case 'shell':
      return raw;
    default:
      return 'shell';
  }
}

/**
 * Normalize pipeline backend to valid enum value.
 */
export function normalizePipelineBackend(raw: unknown): PipelineBackend {
  if (typeof raw !== 'string') return 'shell';
  switch (raw) {
    case 'claude-code':
    case 'cursor':
    case 'shell':
    case 'manual':
      return raw;
    default:
      return 'shell';
  }
}

/**
 * Synthesize an OrchestratorState from a MultitaskSessionRaw.
 * Bridges multitask.sh output to the web-viewer's expected format.
 */
export function synthesizeOrchestratorFromMultitask(
  session: MultitaskSessionRaw,
): OrchestratorState {
  const instances = parseMultitaskInstances(session.instances);

  let activeCount = 0;
  let completedCount = 0;
  let errorCount = 0;

  if (instances) {
    for (const inst of Object.values(instances)) {
      if (inst.status === 'running' || inst.status === 'active') activeCount++;
      else if (inst.status === 'completed') completedCount++;
      else if (inst.status === 'crashed') errorCount++;
    }
  }

  return {
    version: '1.1.0',
    updated_at: new Date().toISOString(),
    agents: {
      agents: [],
      activeCount,
      pendingCount: 0,
      completedCount,
      errorCount,
    },
    costs: {
      today: 0,
      sessions: 0,
      sevenDay: 0,
      thirtyDay: 0,
    },
    ...(instances ? { instances } : {}),
  };
}
