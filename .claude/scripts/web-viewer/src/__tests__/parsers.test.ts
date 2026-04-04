import { describe, it, expect } from 'vitest';
import {
  parseOrchestratorState,
  parseAgent,
  parseSessionState,
  parseSessionAgent,
  parseActivityLogEntry,
  parseMultitaskSessionRaw,
  synthesizeOrchestratorFromMultitask,
  parsePipelineState,
  parsePipelineNode,
  parsePipelineCheckpoint,
  normalizePipelineStatus,
  normalizePipelineNodeStatus,
  normalizePipelineNodeType,
  normalizePipelineBackend,
} from '../../src/parsers.js';
import { createRawOrchestratorJson, createRawSessionJson } from './factories.js';

describe('parseOrchestratorState', () => {
  it('parses valid complete input into typed structure', () => {
    const raw = createRawOrchestratorJson();
    const result = parseOrchestratorState(raw);

    expect(result.version).toBe('1.0');
    expect(result.updated_at).toBe('2026-02-05T10:00:00Z');
    expect(result.agents.agents).toHaveLength(1);
    expect(result.agents.activeCount).toBe(1);
    expect(result.agents.pendingCount).toBe(0);
    expect(result.agents.completedCount).toBe(0);
    expect(result.agents.errorCount).toBe(0);
    expect(result.costs.today).toBe(5.25);
    expect(result.costs.sessions).toBe(12);
    expect(result.costs.sevenDay).toBe(32.50);
    expect(result.costs.thirtyDay).toBe(120.00);
  });

  it('throws on missing version field', () => {
    const raw = createRawOrchestratorJson();
    delete (raw as Record<string, unknown>).version;

    expect(() => parseOrchestratorState(raw)).toThrow('Invalid orchestrator.json structure');
  });

  it('throws on missing updated_at field', () => {
    const raw = createRawOrchestratorJson();
    delete (raw as Record<string, unknown>).updated_at;

    expect(() => parseOrchestratorState(raw)).toThrow('Invalid orchestrator.json structure');
  });

  it('throws on missing agents field', () => {
    const raw = createRawOrchestratorJson();
    delete (raw as Record<string, unknown>).agents;

    expect(() => parseOrchestratorState(raw)).toThrow('Invalid orchestrator.json structure');
  });

  it('throws on missing costs field', () => {
    const raw = createRawOrchestratorJson();
    delete (raw as Record<string, unknown>).costs;

    expect(() => parseOrchestratorState(raw)).toThrow('Invalid orchestrator.json structure');
  });

  it('coerces string numbers to numbers in costs', () => {
    const raw = createRawOrchestratorJson();
    (raw as Record<string, unknown>).costs = {
      today: '5.25',
      sessions: '12',
      sevenDay: '32.5',
      thirtyDay: '120',
    };

    const result = parseOrchestratorState(raw);
    expect(result.costs.today).toBe(5.25);
    expect(result.costs.sessions).toBe(12);
    expect(result.costs.sevenDay).toBe(32.5);
    expect(result.costs.thirtyDay).toBe(120);
  });

  it('coerces string numbers to numbers in agent counts', () => {
    const raw = createRawOrchestratorJson();
    const agents = raw.agents as Record<string, unknown>;
    agents.activeCount = '3';
    agents.pendingCount = '1';

    const result = parseOrchestratorState(raw);
    expect(result.agents.activeCount).toBe(3);
    expect(result.agents.pendingCount).toBe(1);
  });

  it('defaults agents array to empty when not an array', () => {
    const raw = createRawOrchestratorJson();
    (raw.agents as Record<string, unknown>).agents = 'not-an-array';

    const result = parseOrchestratorState(raw);
    expect(result.agents.agents).toEqual([]);
  });

  it('defaults agents array to empty when missing', () => {
    const raw = createRawOrchestratorJson();
    delete (raw.agents as Record<string, unknown>).agents;

    const result = parseOrchestratorState(raw);
    expect(result.agents.agents).toEqual([]);
  });
});

describe('parseAgent', () => {
  it('parses valid complete agent input', () => {
    const raw = {
      id: 'agent-42',
      name: 'My Worker',
      type: 'orchestrator',
      status: 'active',
      plan: 'feature-x',
      metrics: {
        tokensIn: 1000,
        tokensOut: 500,
        totalTokens: 1500,
        cost: 0.05,
        startTime: '2026-02-05T10:00:00Z',
        endTime: '2026-02-05T10:30:00Z',
        duration: 1800,
      },
      context: {
        used: 80000,
        total: 200000,
        percentage: 40,
      },
      tasks: ['task-a', 'task-b'],
      currentCommand: 'npm test',
    };

    const result = parseAgent(raw);
    expect(result.id).toBe('agent-42');
    expect(result.name).toBe('My Worker');
    expect(result.type).toBe('orchestrator');
    expect(result.status).toBe('active');
    expect(result.plan).toBe('feature-x');
    expect(result.metrics.tokensIn).toBe(1000);
    expect(result.metrics.tokensOut).toBe(500);
    expect(result.metrics.totalTokens).toBe(1500);
    expect(result.metrics.cost).toBe(0.05);
    expect(result.metrics.startTime).toBe('2026-02-05T10:00:00Z');
    expect(result.metrics.endTime).toBe('2026-02-05T10:30:00Z');
    expect(result.metrics.duration).toBe(1800);
    expect(result.context.used).toBe(80000);
    expect(result.context.total).toBe(200000);
    expect(result.context.percentage).toBe(40);
    expect(result.tasks).toEqual(['task-a', 'task-b']);
    expect(result.currentCommand).toBe('npm test');
  });

  it('defaults name to Unknown when missing', () => {
    const result = parseAgent({});
    expect(result.name).toBe('Unknown');
  });

  it('defaults type to worker when missing', () => {
    const result = parseAgent({});
    expect(result.type).toBe('worker');
  });

  it('defaults status to pending when missing', () => {
    const result = parseAgent({});
    expect(result.status).toBe('pending');
  });

  it('defaults context.total to 200000 when missing', () => {
    const result = parseAgent({});
    expect(result.context.total).toBe(200000);
  });

  it('defaults context.total to 200000 when context is empty', () => {
    const result = parseAgent({ context: {} });
    expect(result.context.total).toBe(200000);
  });

  it('defaults tasks to empty array when missing', () => {
    const result = parseAgent({});
    expect(result.tasks).toEqual([]);
  });

  it('defaults tasks to empty array when not an array', () => {
    const result = parseAgent({ tasks: 'not-array' });
    expect(result.tasks).toEqual([]);
  });

  it('defaults metrics fields to 0 when metrics is missing', () => {
    const result = parseAgent({});
    expect(result.metrics.tokensIn).toBe(0);
    expect(result.metrics.tokensOut).toBe(0);
    expect(result.metrics.totalTokens).toBe(0);
    expect(result.metrics.cost).toBe(0);
  });

  it('coerces string metric values to numbers', () => {
    const result = parseAgent({
      metrics: {
        tokensIn: '1000',
        tokensOut: '500',
        totalTokens: '1500',
        cost: '0.05',
        startTime: '2026-02-05T10:00:00Z',
      },
    });
    expect(result.metrics.tokensIn).toBe(1000);
    expect(result.metrics.tokensOut).toBe(500);
    expect(result.metrics.totalTokens).toBe(1500);
    expect(result.metrics.cost).toBe(0.05);
  });

  it('sets endTime to undefined when not present', () => {
    const result = parseAgent({ metrics: { startTime: 'now' } });
    expect(result.metrics.endTime).toBeUndefined();
  });

  it('sets duration to undefined when not present', () => {
    const result = parseAgent({ metrics: { startTime: 'now' } });
    expect(result.metrics.duration).toBeUndefined();
  });

  it('converts id to string', () => {
    const result = parseAgent({ id: 123 });
    expect(result.id).toBe('123');
  });
});

describe('parseSessionState', () => {
  it('parses valid complete session input', () => {
    const raw = createRawSessionJson();
    const result = parseSessionState(raw);

    expect(result.version).toBe('1.0');
    expect(result.plan_id).toBe('test-plan');
    expect(result.created_at).toBe('2026-02-05T10:00:00Z');
    expect(result.updated_at).toBe('2026-02-05T10:05:00Z');
    expect(result.status).toBe('running');
    expect(result.plan.path).toBe('docs/plans/test-plan.json');
    expect(result.plan.name).toBe('test-plan');
    expect(result.plan.branch).toBe('feature/test-plan');
    expect(result.progress.total_stories).toBe(8);
    expect(result.progress.completed).toBe(3);
    expect(result.agents).toHaveLength(1);
    expect(result.file_claims).toEqual(['src/index.ts']);
    expect(result.git.branch).toBe('feature/test-plan');
    expect(result.execution.mode).toBe('autonomous');
    expect(result.activity_log).toHaveLength(1);
  });

  it('throws on missing version field', () => {
    const raw = createRawSessionJson();
    delete (raw as Record<string, unknown>).version;

    expect(() => parseSessionState(raw)).toThrow('Invalid session.json structure');
  });

  it('throws on missing plan_id field', () => {
    const raw = createRawSessionJson();
    delete (raw as Record<string, unknown>).plan_id;

    expect(() => parseSessionState(raw)).toThrow('Invalid session.json structure');
  });

  it('throws on missing created_at field', () => {
    const raw = createRawSessionJson();
    delete (raw as Record<string, unknown>).created_at;

    expect(() => parseSessionState(raw)).toThrow('Invalid session.json structure');
  });

  it('defaults status to running when missing', () => {
    const raw = createRawSessionJson();
    delete (raw as Record<string, unknown>).status;

    const result = parseSessionState(raw);
    expect(result.status).toBe('running');
  });

  it('defaults execution.mode to manual when missing', () => {
    const raw = createRawSessionJson();
    delete (raw as Record<string, unknown>).execution;

    const result = parseSessionState(raw);
    expect(result.execution.mode).toBe('manual');
  });

  it('defaults agents to empty array when not an array', () => {
    const raw = createRawSessionJson();
    (raw as Record<string, unknown>).agents = 'not-array';

    const result = parseSessionState(raw);
    expect(result.agents).toEqual([]);
  });

  it('defaults activity_log to empty array when missing', () => {
    const raw = createRawSessionJson();
    delete (raw as Record<string, unknown>).activity_log;

    const result = parseSessionState(raw);
    expect(result.activity_log).toEqual([]);
  });

  it('defaults file_claims to empty array when not an array', () => {
    const raw = createRawSessionJson();
    (raw as Record<string, unknown>).file_claims = null;

    const result = parseSessionState(raw);
    expect(result.file_claims).toEqual([]);
  });

  it('defaults git.modified_files to empty array when missing', () => {
    const raw = createRawSessionJson();
    (raw as Record<string, unknown>).git = {};

    const result = parseSessionState(raw);
    expect(result.git.modified_files).toEqual([]);
  });

  it('uses created_at as fallback for updated_at', () => {
    const raw = createRawSessionJson();
    delete (raw as Record<string, unknown>).updated_at;

    const result = parseSessionState(raw);
    expect(result.updated_at).toBe(result.created_at);
  });
});

describe('parseSessionAgent', () => {
  it('parses valid session agent', () => {
    const raw = {
      id: 'worker-5',
      joined_at: '2026-02-05T10:00:00Z',
      role: 'orchestrator',
      departed_at: '2026-02-05T11:00:00Z',
    };

    const result = parseSessionAgent(raw);
    expect(result.id).toBe('worker-5');
    expect(result.joined_at).toBe('2026-02-05T10:00:00Z');
    expect(result.role).toBe('orchestrator');
    expect(result.departed_at).toBe('2026-02-05T11:00:00Z');
  });

  it('defaults role to worker when missing', () => {
    const result = parseSessionAgent({ id: 'w1', joined_at: 'now' });
    expect(result.role).toBe('worker');
  });

  it('sets departed_at to undefined when missing', () => {
    const result = parseSessionAgent({ id: 'w1', joined_at: 'now' });
    expect(result.departed_at).toBeUndefined();
  });

  it('defaults id to empty string when missing', () => {
    const result = parseSessionAgent({});
    expect(result.id).toBe('');
  });

  it('defaults joined_at to empty string when missing', () => {
    const result = parseSessionAgent({});
    expect(result.joined_at).toBe('');
  });
});

describe('parseActivityLogEntry', () => {
  it('parses valid activity log entry', () => {
    const raw = {
      timestamp: '2026-02-05T10:00:00Z',
      type: 'story_completed',
      story: 'S3',
      message: 'Story completed',
    };

    const result = parseActivityLogEntry(raw);
    expect(result.timestamp).toBe('2026-02-05T10:00:00Z');
    expect(result.type).toBe('story_completed');
    expect(result.story).toBe('S3');
    expect(result.message).toBe('Story completed');
  });

  it('defaults type to checkpoint when missing', () => {
    const result = parseActivityLogEntry({ timestamp: 'now', message: 'test' });
    expect(result.type).toBe('checkpoint');
  });

  it('sets story to undefined when missing', () => {
    const result = parseActivityLogEntry({ timestamp: 'now', message: 'test' });
    expect(result.story).toBeUndefined();
  });

  it('defaults timestamp to empty string when missing', () => {
    const result = parseActivityLogEntry({});
    expect(result.timestamp).toBe('');
  });

  it('defaults message to empty string when missing', () => {
    const result = parseActivityLogEntry({});
    expect(result.message).toBe('');
  });
});

describe('parseMultitaskSessionRaw', () => {
  const validSession = {
    session_id: 'multitask-2026-02-07-123456',
    started: '2026-02-07T12:34:56Z',
    tui_enabled: true,
    use_happy_cli: false,
    max_iterations: 50,
    instances: [
      {
        instance_num: 1,
        worktree: '../repo-wt-feat-auth',
        branch: 'feature/auth',
        plan: 'docs/plans/auth.json',
        pid: 12345,
        status: 'running',
        started: '2026-02-07T12:34:56Z',
        log_file: '.claude/state/multitask-instance-1.log',
      },
    ],
  };

  it('parses valid multitask session', () => {
    const result = parseMultitaskSessionRaw(validSession);
    expect(result).not.toBeNull();
    expect(result!.session_id).toBe('multitask-2026-02-07-123456');
    expect(result!.instances).toHaveLength(1);
    expect(result!.instances[0].branch).toBe('feature/auth');
    expect(result!.instances[0].log_file).toBe('.claude/state/multitask-instance-1.log');
  });

  it('returns null for non-object input', () => {
    expect(parseMultitaskSessionRaw('not an object')).toBeNull();
    expect(parseMultitaskSessionRaw(null)).toBeNull();
    expect(parseMultitaskSessionRaw(42)).toBeNull();
  });

  it('returns null for missing session_id', () => {
    expect(parseMultitaskSessionRaw({ instances: [] })).toBeNull();
  });

  it('returns null for missing instances array', () => {
    expect(parseMultitaskSessionRaw({ session_id: 'test' })).toBeNull();
  });

  it('handles optional web_viewer_pid', () => {
    const result = parseMultitaskSessionRaw({ ...validSession, web_viewer_pid: 54321 });
    expect(result!.web_viewer_pid).toBe(54321);
  });

  it('defaults max_iterations to 50 when missing', () => {
    const { max_iterations: _, ...withoutMax } = validSession;
    const result = parseMultitaskSessionRaw({ ...withoutMax, max_iterations: undefined });
    expect(result!.max_iterations).toBe(50);
  });
});

describe('parseMultitaskSessionRaw health fields', () => {
  it('parses session with health fields present', () => {
    const result = parseMultitaskSessionRaw({
      session_id: 'test-health',
      started: '2026-02-08T10:00:00Z',
      tui_enabled: false,
      use_happy_cli: false,
      max_iterations: 50,
      instances: [
        {
          instance_num: 1,
          worktree: '/tmp/wt-1',
          branch: 'feature/auth',
          plan: 'docs/plans/auth.json',
          pid: 12345,
          status: 'crashed',
          started: '2026-02-08T10:00:00Z',
          log_file: '.claude/state/multitask-instance-1.log',
          last_heartbeat: '2026-02-08T10:05:00Z',
          exit_code: 137,
          exited_at: '2026-02-08T10:05:30Z',
          runtime_seconds: 330,
          crash_count: 2,
          crash_log: [
            {
              timestamp: '2026-02-08T10:03:00Z',
              exit_code: 1,
              pid: 12340,
              runtime_seconds: 180,
              message: 'Instance #1 crashed with exit code 1',
            },
            {
              timestamp: '2026-02-08T10:05:30Z',
              exit_code: 137,
              pid: 12345,
              runtime_seconds: 150,
              message: 'Instance #1 crashed with exit code 137',
            },
          ],
        },
      ],
    });

    expect(result).not.toBeNull();
    const inst = result!.instances[0];
    expect(inst.last_heartbeat).toBe('2026-02-08T10:05:00Z');
    expect(inst.exit_code).toBe(137);
    expect(inst.exited_at).toBe('2026-02-08T10:05:30Z');
    expect(inst.runtime_seconds).toBe(330);
    expect(inst.crash_count).toBe(2);
    expect(inst.crash_log).toHaveLength(2);
    expect(inst.crash_log![0].exit_code).toBe(1);
    expect(inst.crash_log![1].exit_code).toBe(137);
  });

  it('parses session without health fields (backward compat)', () => {
    const result = parseMultitaskSessionRaw({
      session_id: 'test-old',
      started: '2026-02-07T12:00:00Z',
      tui_enabled: true,
      use_happy_cli: false,
      max_iterations: 50,
      instances: [
        {
          instance_num: 1,
          worktree: '/tmp/wt-1',
          branch: 'feature/auth',
          plan: 'docs/plans/auth.json',
          pid: 12345,
          status: 'running',
          started: '2026-02-07T12:00:00Z',
          log_file: '.claude/state/multitask-instance-1.log',
        },
      ],
    });

    expect(result).not.toBeNull();
    const inst = result!.instances[0];
    expect(inst.last_heartbeat).toBeUndefined();
    expect(inst.exit_code).toBeUndefined();
    expect(inst.exited_at).toBeUndefined();
    expect(inst.runtime_seconds).toBeUndefined();
    expect(inst.crash_count).toBeUndefined();
    expect(inst.crash_log).toBeUndefined();
  });

  it('handles exit_code of null (still running)', () => {
    const result = parseMultitaskSessionRaw({
      session_id: 'test-null-exit',
      started: '2026-02-08T10:00:00Z',
      tui_enabled: false,
      use_happy_cli: false,
      max_iterations: 50,
      instances: [
        {
          instance_num: 1,
          worktree: '/tmp/wt-1',
          branch: 'feature/auth',
          plan: 'docs/plans/auth.json',
          pid: 12345,
          status: 'running',
          started: '2026-02-08T10:00:00Z',
          log_file: '.claude/state/multitask-instance-1.log',
          exit_code: null,
        },
      ],
    });

    expect(result).not.toBeNull();
    expect(result!.instances[0].exit_code).toBeNull();
  });

  it('handles exit_code of 0 (clean exit)', () => {
    const result = parseMultitaskSessionRaw({
      session_id: 'test-zero-exit',
      started: '2026-02-08T10:00:00Z',
      tui_enabled: false,
      use_happy_cli: false,
      max_iterations: 50,
      instances: [
        {
          instance_num: 1,
          worktree: '/tmp/wt-1',
          branch: 'feature/auth',
          plan: 'docs/plans/auth.json',
          pid: 12345,
          status: 'completed',
          started: '2026-02-08T10:00:00Z',
          log_file: '.claude/state/multitask-instance-1.log',
          exit_code: 0,
        },
      ],
    });

    expect(result).not.toBeNull();
    expect(result!.instances[0].exit_code).toBe(0);
  });
});

describe('synthesizeOrchestratorFromMultitask', () => {
  it('synthesizes valid OrchestratorState with running instances', () => {
    const session = parseMultitaskSessionRaw({
      session_id: 'test',
      started: '2026-02-07T12:00:00Z',
      tui_enabled: false,
      use_happy_cli: false,
      max_iterations: 50,
      instances: [
        {
          instance_num: 1, worktree: '/tmp/wt-1', branch: 'feature/auth',
          plan: 'docs/plans/auth.json', pid: 12345, status: 'running',
          started: '2026-02-07T12:00:00Z', log_file: '.claude/state/multitask-instance-1.log',
        },
        {
          instance_num: 2, worktree: '/tmp/wt-2', branch: 'feature/api',
          plan: 'docs/plans/api.json', pid: 12346, status: 'completed',
          started: '2026-02-07T12:00:00Z', log_file: '.claude/state/multitask-instance-2.log',
        },
        {
          instance_num: 3, worktree: '/tmp/wt-3', branch: 'feature/ui',
          plan: 'docs/plans/ui.json', pid: 12347, status: 'crashed',
          started: '2026-02-07T12:00:00Z', log_file: '.claude/state/multitask-instance-3.log',
        },
      ],
    })!;

    const result = synthesizeOrchestratorFromMultitask(session);

    expect(result.version).toBe('1.1.0');
    expect(result.agents.activeCount).toBe(1);
    expect(result.agents.completedCount).toBe(1);
    expect(result.agents.errorCount).toBe(1);
    expect(result.agents.agents).toEqual([]);
    expect(result.costs.today).toBe(0);
    expect(result.instances).toBeDefined();
    expect(Object.keys(result.instances!)).toHaveLength(3);
    expect(result.instances!['1'].branch).toBe('feature/auth');
    expect(result.instances!['1'].logFile).toBe('.claude/state/multitask-instance-1.log');
    expect(result.instances!['2'].status).toBe('completed');
    expect(result.instances!['3'].status).toBe('crashed');
  });

  it('preserves health fields through synthesis pipeline', () => {
    const session = parseMultitaskSessionRaw({
      session_id: 'test-health-synth',
      started: '2026-02-08T10:00:00Z',
      tui_enabled: false,
      use_happy_cli: false,
      max_iterations: 50,
      instances: [
        {
          instance_num: 1,
          worktree: '/tmp/wt-1',
          branch: 'feature/auth',
          plan: 'docs/plans/auth.json',
          pid: 12345,
          status: 'crashed',
          started: '2026-02-08T10:00:00Z',
          log_file: '.claude/state/multitask-instance-1.log',
          last_heartbeat: '2026-02-08T10:04:50Z',
          exit_code: 1,
          exited_at: '2026-02-08T10:05:00Z',
          runtime_seconds: 300,
          crash_count: 1,
          crash_log: [
            {
              timestamp: '2026-02-08T10:05:00Z',
              exit_code: 1,
              pid: 12345,
              runtime_seconds: 300,
              message: 'Instance #1 crashed with exit code 1',
            },
          ],
        },
      ],
    })!;

    const result = synthesizeOrchestratorFromMultitask(session);
    const inst = result.instances!['1'];

    expect(inst.lastHeartbeat).toBe('2026-02-08T10:04:50Z');
    expect(inst.exitCode).toBe(1);
    expect(inst.exitedAt).toBe('2026-02-08T10:05:00Z');
    expect(inst.runtimeSeconds).toBe(300);
    expect(inst.crashCount).toBe(1);
    expect(inst.crashLog).toHaveLength(1);
    expect(inst.crashLog![0].exitCode).toBe(1);
  });

  it('handles empty instances array', () => {
    const session = parseMultitaskSessionRaw({
      session_id: 'test',
      started: '2026-02-07T12:00:00Z',
      tui_enabled: false,
      use_happy_cli: false,
      max_iterations: 50,
      instances: [],
    })!;

    const result = synthesizeOrchestratorFromMultitask(session);
    expect(result.agents.activeCount).toBe(0);
    expect(result.agents.completedCount).toBe(0);
    expect(result.agents.errorCount).toBe(0);
  });
});

// ===== Pipeline Parser Tests =====

describe('parsePipelineState', () => {
  const validRaw = {
    version: '1.0',
    pipeline_id: 'deploy-feature',
    definition_path: 'docs/plans/examples/deploy-pipeline.json',
    status: 'running',
    created_at: '2026-02-08T15:00:00Z',
    updated_at: '2026-02-08T15:05:00Z',
    started_at: '2026-02-08T15:00:05Z',
    completed_at: null,
    execution_order: ['lint', 'test', 'build'],
    parallel_groups: [['lint', 'test'], ['build']],
    nodes: {
      lint: {
        id: 'lint',
        type: 'shell',
        name: 'Lint',
        status: 'completed',
        backend: 'shell',
        command: 'npm run lint',
        depends: [],
        started_at: '2026-02-08T15:00:05Z',
        completed_at: '2026-02-08T15:00:15Z',
        exit_code: 0,
        pid: 12345,
        attempt: 1,
        log_file: '.claude/state/pipeline-deploy-feature-node-lint.log',
        runtime_seconds: 10,
        error: null,
      },
      test: {
        id: 'test',
        type: 'shell',
        name: 'Test',
        status: 'running',
        backend: 'shell',
        command: 'npm test',
        depends: [],
        started_at: '2026-02-08T15:00:05Z',
        completed_at: null,
        exit_code: null,
        pid: 12346,
        attempt: 1,
        log_file: '.claude/state/pipeline-deploy-feature-node-test.log',
        runtime_seconds: 55,
        error: null,
      },
      build: {
        id: 'build',
        type: 'shell',
        name: 'Build',
        status: 'pending',
        backend: 'shell',
        command: 'npm run build',
        depends: ['lint', 'test'],
        started_at: null,
        completed_at: null,
        exit_code: null,
        pid: null,
        attempt: 0,
        log_file: null,
        runtime_seconds: 0,
        error: null,
      },
    },
    checkpoint: {
      saved_at: '2026-02-08T15:00:15Z',
      completed_nodes: ['lint'],
      failed_nodes: [],
      skipped_nodes: [],
    },
  };

  it('parses valid complete pipeline state', () => {
    const result = parsePipelineState(validRaw);
    expect(result).not.toBeNull();
    expect(result!.pipelineId).toBe('deploy-feature');
    expect(result!.definitionPath).toBe('docs/plans/examples/deploy-pipeline.json');
    expect(result!.status).toBe('running');
    expect(result!.createdAt).toBe('2026-02-08T15:00:00Z');
    expect(result!.startedAt).toBe('2026-02-08T15:00:05Z');
    expect(result!.completedAt).toBeNull();
    expect(result!.executionOrder).toEqual(['lint', 'test', 'build']);
    expect(result!.parallelGroups).toEqual([['lint', 'test'], ['build']]);
  });

  it('parses nodes correctly', () => {
    const result = parsePipelineState(validRaw)!;
    expect(Object.keys(result.nodes)).toHaveLength(3);
    expect(result.nodes.lint.status).toBe('completed');
    expect(result.nodes.lint.exitCode).toBe(0);
    expect(result.nodes.test.status).toBe('running');
    expect(result.nodes.test.pid).toBe(12346);
    expect(result.nodes.build.status).toBe('pending');
    expect(result.nodes.build.depends).toEqual(['lint', 'test']);
  });

  it('parses checkpoint correctly', () => {
    const result = parsePipelineState(validRaw)!;
    expect(result.checkpoint.savedAt).toBe('2026-02-08T15:00:15Z');
    expect(result.checkpoint.completedNodes).toEqual(['lint']);
    expect(result.checkpoint.failedNodes).toEqual([]);
    expect(result.checkpoint.skippedNodes).toEqual([]);
  });

  it('returns null for non-object input', () => {
    expect(parsePipelineState('not an object')).toBeNull();
    expect(parsePipelineState(null)).toBeNull();
    expect(parsePipelineState(42)).toBeNull();
    expect(parsePipelineState([])).toBeNull();
  });

  it('returns null for missing pipeline_id', () => {
    const { pipeline_id: _, ...noId } = validRaw;
    expect(parsePipelineState(noId)).toBeNull();
  });

  it('returns null for missing nodes', () => {
    const { nodes: _, ...noNodes } = validRaw;
    expect(parsePipelineState(noNodes)).toBeNull();
  });

  it('returns null when nodes is not an object', () => {
    expect(parsePipelineState({ ...validRaw, nodes: 'bad' })).toBeNull();
    expect(parsePipelineState({ ...validRaw, nodes: [] })).toBeNull();
  });

  it('defaults version to 1.0 when missing', () => {
    const { version: _, ...noVersion } = validRaw;
    const result = parsePipelineState({ ...noVersion, pipeline_id: 'test', nodes: {} });
    expect(result!.version).toBe('1.0');
  });

  it('defaults status to pending for unknown value', () => {
    const result = parsePipelineState({ ...validRaw, status: 'bogus' });
    expect(result!.status).toBe('pending');
  });

  it('defaults execution_order to empty array when missing', () => {
    const { execution_order: _, ...noExec } = validRaw;
    const result = parsePipelineState(noExec);
    expect(result!.executionOrder).toEqual([]);
  });

  it('defaults parallel_groups to empty array when missing', () => {
    const { parallel_groups: _, ...noGroups } = validRaw;
    const result = parsePipelineState(noGroups);
    expect(result!.parallelGroups).toEqual([]);
  });

  it('handles started_at and completed_at as null', () => {
    const result = parsePipelineState({ ...validRaw, started_at: null, completed_at: null });
    expect(result!.startedAt).toBeNull();
    expect(result!.completedAt).toBeNull();
  });
});

describe('parsePipelineNode', () => {
  it('parses valid complete node', () => {
    const raw = {
      id: 'lint',
      type: 'shell',
      name: 'Run Linter',
      status: 'completed',
      backend: 'shell',
      command: 'npm run lint',
      depends: ['setup'],
      started_at: '2026-02-08T15:00:00Z',
      completed_at: '2026-02-08T15:00:10Z',
      exit_code: 0,
      pid: 12345,
      attempt: 1,
      log_file: '/tmp/lint.log',
      runtime_seconds: 10,
      error: null,
    };

    const result = parsePipelineNode(raw, 'fallback');
    expect(result.id).toBe('lint');
    expect(result.type).toBe('shell');
    expect(result.name).toBe('Run Linter');
    expect(result.status).toBe('completed');
    expect(result.backend).toBe('shell');
    expect(result.command).toBe('npm run lint');
    expect(result.depends).toEqual(['setup']);
    expect(result.startedAt).toBe('2026-02-08T15:00:00Z');
    expect(result.completedAt).toBe('2026-02-08T15:00:10Z');
    expect(result.exitCode).toBe(0);
    expect(result.pid).toBe(12345);
    expect(result.attempt).toBe(1);
    expect(result.logFile).toBe('/tmp/lint.log');
    expect(result.runtimeSeconds).toBe(10);
    expect(result.error).toBeNull();
  });

  it('uses fallbackId when id is missing', () => {
    const result = parsePipelineNode({}, 'my-fallback');
    expect(result.id).toBe('my-fallback');
  });

  it('uses fallbackId for name when name is missing', () => {
    const result = parsePipelineNode({}, 'node-1');
    expect(result.name).toBe('node-1');
  });

  it('defaults type to shell for unknown value', () => {
    const result = parsePipelineNode({ type: 'unknown' }, 'n');
    expect(result.type).toBe('shell');
  });

  it('defaults status to pending for unknown value', () => {
    const result = parsePipelineNode({ status: 'bogus' }, 'n');
    expect(result.status).toBe('pending');
  });

  it('defaults backend to shell for unknown value', () => {
    const result = parsePipelineNode({ backend: 'docker' }, 'n');
    expect(result.backend).toBe('shell');
  });

  it('defaults command to null when missing', () => {
    const result = parsePipelineNode({}, 'n');
    expect(result.command).toBeNull();
  });

  it('defaults depends to empty array when missing', () => {
    const result = parsePipelineNode({}, 'n');
    expect(result.depends).toEqual([]);
  });

  it('defaults exit_code to null when missing', () => {
    const result = parsePipelineNode({}, 'n');
    expect(result.exitCode).toBeNull();
  });

  it('handles exit_code of 0', () => {
    const result = parsePipelineNode({ exit_code: 0 }, 'n');
    expect(result.exitCode).toBe(0);
  });

  it('handles exit_code of null (still running)', () => {
    const result = parsePipelineNode({ exit_code: null }, 'n');
    expect(result.exitCode).toBeNull();
  });

  it('defaults attempt to 0 when missing', () => {
    const result = parsePipelineNode({}, 'n');
    expect(result.attempt).toBe(0);
  });

  it('defaults runtimeSeconds to 0 when missing', () => {
    const result = parsePipelineNode({}, 'n');
    expect(result.runtimeSeconds).toBe(0);
  });

  it('handles non-object input gracefully', () => {
    const result = parsePipelineNode('bad', 'fallback');
    expect(result.id).toBe('fallback');
    expect(result.type).toBe('shell');
    expect(result.status).toBe('pending');
  });

  it('recognizes claude-code backend', () => {
    const result = parsePipelineNode({ backend: 'claude-code' }, 'n');
    expect(result.backend).toBe('claude-code');
  });

  it('recognizes gate node type', () => {
    const result = parsePipelineNode({ type: 'gate' }, 'n');
    expect(result.type).toBe('gate');
  });

  it('preserves error string', () => {
    const result = parsePipelineNode({ error: 'Something failed' }, 'n');
    expect(result.error).toBe('Something failed');
  });
});

describe('parsePipelineCheckpoint', () => {
  it('parses valid checkpoint', () => {
    const result = parsePipelineCheckpoint({
      saved_at: '2026-02-08T15:00:15Z',
      completed_nodes: ['lint', 'test'],
      failed_nodes: ['build'],
      skipped_nodes: ['deploy'],
    });
    expect(result.savedAt).toBe('2026-02-08T15:00:15Z');
    expect(result.completedNodes).toEqual(['lint', 'test']);
    expect(result.failedNodes).toEqual(['build']);
    expect(result.skippedNodes).toEqual(['deploy']);
  });

  it('defaults all fields when input is empty', () => {
    const result = parsePipelineCheckpoint({});
    expect(result.savedAt).toBe('');
    expect(result.completedNodes).toEqual([]);
    expect(result.failedNodes).toEqual([]);
    expect(result.skippedNodes).toEqual([]);
  });

  it('handles non-object input gracefully', () => {
    const result = parsePipelineCheckpoint(null);
    expect(result.savedAt).toBe('');
    expect(result.completedNodes).toEqual([]);
  });
});

describe('normalizePipelineStatus', () => {
  it('returns valid statuses as-is', () => {
    expect(normalizePipelineStatus('pending')).toBe('pending');
    expect(normalizePipelineStatus('running')).toBe('running');
    expect(normalizePipelineStatus('completed')).toBe('completed');
    expect(normalizePipelineStatus('failed')).toBe('failed');
    expect(normalizePipelineStatus('paused')).toBe('paused');
  });

  it('defaults to pending for unknown string', () => {
    expect(normalizePipelineStatus('bogus')).toBe('pending');
  });

  it('defaults to pending for non-string', () => {
    expect(normalizePipelineStatus(42)).toBe('pending');
    expect(normalizePipelineStatus(null)).toBe('pending');
    expect(normalizePipelineStatus(undefined)).toBe('pending');
  });
});

describe('normalizePipelineNodeStatus', () => {
  it('returns valid statuses as-is', () => {
    expect(normalizePipelineNodeStatus('pending')).toBe('pending');
    expect(normalizePipelineNodeStatus('queued')).toBe('queued');
    expect(normalizePipelineNodeStatus('running')).toBe('running');
    expect(normalizePipelineNodeStatus('completed')).toBe('completed');
    expect(normalizePipelineNodeStatus('failed')).toBe('failed');
    expect(normalizePipelineNodeStatus('skipped')).toBe('skipped');
  });

  it('defaults to pending for unknown string', () => {
    expect(normalizePipelineNodeStatus('bogus')).toBe('pending');
  });

  it('defaults to pending for non-string', () => {
    expect(normalizePipelineNodeStatus(null)).toBe('pending');
  });
});

describe('normalizePipelineNodeType', () => {
  it('returns valid types as-is', () => {
    expect(normalizePipelineNodeType('task')).toBe('task');
    expect(normalizePipelineNodeType('plan')).toBe('plan');
    expect(normalizePipelineNodeType('gate')).toBe('gate');
    expect(normalizePipelineNodeType('shell')).toBe('shell');
  });

  it('defaults to shell for unknown string', () => {
    expect(normalizePipelineNodeType('docker')).toBe('shell');
  });

  it('defaults to shell for non-string', () => {
    expect(normalizePipelineNodeType(123)).toBe('shell');
  });
});

describe('normalizePipelineBackend', () => {
  it('returns valid backends as-is', () => {
    expect(normalizePipelineBackend('claude-code')).toBe('claude-code');
    expect(normalizePipelineBackend('cursor')).toBe('cursor');
    expect(normalizePipelineBackend('shell')).toBe('shell');
    expect(normalizePipelineBackend('manual')).toBe('manual');
  });

  it('defaults to shell for unknown string', () => {
    expect(normalizePipelineBackend('docker')).toBe('shell');
  });

  it('defaults to shell for non-string', () => {
    expect(normalizePipelineBackend(null)).toBe('shell');
  });
});
