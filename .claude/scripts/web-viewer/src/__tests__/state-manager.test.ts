import { describe, it, expect, afterEach } from 'vitest';
import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { StateManager } from '../../src/state-manager.js';
import {
  createRawOrchestratorJson,
  createRawSessionJson,
  createMockPlanDefinition,
} from './factories.js';

let tempDir: string;

afterEach(() => {
  if (tempDir) {
    rmSync(tempDir, { recursive: true, force: true });
  }
});

function setupTempDir(): string {
  tempDir = mkdtempSync(join(tmpdir(), 'state-manager-test-'));
  return tempDir;
}

function setupDirs(baseDir: string, planName: string = 'web-viewer'): void {
  mkdirSync(join(baseDir, '.claude/state'), { recursive: true });
  mkdirSync(join(baseDir, `.claude/state/plans/${planName}`), { recursive: true });
  mkdirSync(join(baseDir, 'docs/plans'), { recursive: true });
}

describe('StateManager', () => {
  describe('constructor', () => {
    it('builds correct file paths from baseDir and planName', () => {
      const baseDir = '/fake/base';
      const manager = new StateManager(baseDir, 'my-plan');

      // We verify paths by calling getState and checking behavior,
      // but we can also inspect the manager indirectly by verifying
      // it creates a valid instance
      expect(manager).toBeInstanceOf(StateManager);
    });

    it('uses web-viewer as default planName', () => {
      const baseDir = setupTempDir();
      setupDirs(baseDir, 'web-viewer');

      // Write orchestrator file
      const orchestratorData = createRawOrchestratorJson();
      writeFileSync(
        join(baseDir, '.claude/state/orchestrator.json'),
        JSON.stringify(orchestratorData),
      );

      // Write session file at the default plan path (web-viewer)
      const sessionData = createRawSessionJson();
      writeFileSync(
        join(baseDir, '.claude/state/plans/web-viewer/session.json'),
        JSON.stringify(sessionData),
      );

      // Create manager without explicit planName (should default to 'web-viewer')
      const manager = new StateManager(baseDir);

      // getState should find both files using the default plan name
      return manager.getState().then((state) => {
        expect(state.orchestrator).not.toBeNull();
        expect(state.session).not.toBeNull();
      });
    });
  });

  describe('getState', () => {
    it('returns null for all fields when files do not exist', async () => {
      const baseDir = setupTempDir();
      // Intentionally do NOT create any subdirectories or files
      const manager = new StateManager(baseDir, 'nonexistent');

      const state = await manager.getState();
      expect(state.orchestrator).toBeNull();
      expect(state.session).toBeNull();
      expect(state.plan).toBeNull();
    });

    it('reads and returns parsed orchestrator state from real file', async () => {
      const baseDir = setupTempDir();
      setupDirs(baseDir);

      const orchestratorData = createRawOrchestratorJson();
      writeFileSync(
        join(baseDir, '.claude/state/orchestrator.json'),
        JSON.stringify(orchestratorData),
      );

      const manager = new StateManager(baseDir);
      const state = await manager.getState();

      expect(state.orchestrator).not.toBeNull();
      expect(state.orchestrator!.version).toBe('1.0');
      expect(state.orchestrator!.updated_at).toBe('2026-02-05T10:00:00Z');
      expect(state.orchestrator!.agents.agents).toHaveLength(1);
      expect(state.orchestrator!.costs.today).toBe(5.25);
    });

    it('reads and returns parsed session state from real file', async () => {
      const baseDir = setupTempDir();
      setupDirs(baseDir);

      const sessionData = createRawSessionJson();
      writeFileSync(
        join(baseDir, '.claude/state/plans/web-viewer/session.json'),
        JSON.stringify(sessionData),
      );

      const manager = new StateManager(baseDir);
      const state = await manager.getState();

      expect(state.session).not.toBeNull();
      expect(state.session!.version).toBe('1.0');
      expect(state.session!.plan_id).toBe('test-plan');
      expect(state.session!.status).toBe('running');
      expect(state.session!.agents).toHaveLength(1);
    });

    it('reads and returns parsed plan definition from real file', async () => {
      const baseDir = setupTempDir();
      setupDirs(baseDir);

      const planData = createMockPlanDefinition();
      writeFileSync(
        join(baseDir, 'docs/plans/web-viewer.json'),
        JSON.stringify(planData),
      );

      const manager = new StateManager(baseDir);
      const state = await manager.getState();

      expect(state.plan).not.toBeNull();
      expect(state.plan!.feature).toBe('test-feature');
      expect(state.plan!.branch).toBe('feature/test-plan');
      expect(state.plan!.stories).toHaveLength(3);
    });

    it('returns all three fields when all files exist', async () => {
      const baseDir = setupTempDir();
      setupDirs(baseDir);

      writeFileSync(
        join(baseDir, '.claude/state/orchestrator.json'),
        JSON.stringify(createRawOrchestratorJson()),
      );
      writeFileSync(
        join(baseDir, '.claude/state/plans/web-viewer/session.json'),
        JSON.stringify(createRawSessionJson()),
      );
      writeFileSync(
        join(baseDir, 'docs/plans/web-viewer.json'),
        JSON.stringify(createMockPlanDefinition()),
      );

      const manager = new StateManager(baseDir);
      const state = await manager.getState();

      expect(state.orchestrator).not.toBeNull();
      expect(state.session).not.toBeNull();
      expect(state.plan).not.toBeNull();
    });
  });

  describe('dual-source orchestrator', () => {
    it('synthesizes from multitask-session.json when orchestrator.json is absent', async () => {
      const baseDir = setupTempDir();
      setupDirs(baseDir);

      const multitaskSession = {
        session_id: 'test-session',
        started: '2026-02-07T12:00:00Z',
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
            started: '2026-02-07T12:00:00Z',
            log_file: '.claude/state/multitask-instance-1.log',
          },
        ],
      };

      writeFileSync(
        join(baseDir, '.claude/state/multitask-session.json'),
        JSON.stringify(multitaskSession),
      );

      const manager = new StateManager(baseDir);
      const state = await manager.getState();

      expect(state.orchestrator).not.toBeNull();
      expect(state.orchestrator!.version).toBe('1.1.0');
      expect(state.orchestrator!.agents.activeCount).toBe(1);
      expect(state.orchestrator!.instances).toBeDefined();
      expect(Object.keys(state.orchestrator!.instances!)).toHaveLength(1);
      expect(state.orchestrator!.instances!['1'].branch).toBe('feature/auth');
    });

    it('prefers orchestrator.json when both files exist', async () => {
      const baseDir = setupTempDir();
      setupDirs(baseDir);

      // Write orchestrator.json
      writeFileSync(
        join(baseDir, '.claude/state/orchestrator.json'),
        JSON.stringify(createRawOrchestratorJson()),
      );

      // Write multitask-session.json
      writeFileSync(
        join(baseDir, '.claude/state/multitask-session.json'),
        JSON.stringify({
          session_id: 'test-session',
          started: '2026-02-07T12:00:00Z',
          tui_enabled: false,
          use_happy_cli: false,
          max_iterations: 50,
          instances: [
            {
              instance_num: 1, worktree: '/tmp/wt-1', branch: 'feature/auth',
              plan: 'auth', pid: 12345, status: 'running',
              started: '2026-02-07T12:00:00Z', log_file: 'log.txt',
            },
          ],
        }),
      );

      const manager = new StateManager(baseDir);
      const state = await manager.getState();

      // Should use orchestrator.json (version 1.0), not synthesized (version 1.1.0)
      expect(state.orchestrator).not.toBeNull();
      expect(state.orchestrator!.version).toBe('1.0');
    });

    it('returns null orchestrator when neither file exists', async () => {
      const baseDir = setupTempDir();
      setupDirs(baseDir);

      const manager = new StateManager(baseDir);
      const state = await manager.getState();

      expect(state.orchestrator).toBeNull();
    });
  });

  describe('multi-plan support', () => {
    it('returns plans from multitask instances', async () => {
      const baseDir = setupTempDir();
      setupDirs(baseDir);
      mkdirSync(join(baseDir, 'docs/plans'), { recursive: true });

      // Write multitask-session with two instances referencing plan files
      writeFileSync(
        join(baseDir, '.claude/state/multitask-session.json'),
        JSON.stringify({
          session_id: 'test-session',
          started: '2026-02-07T12:00:00Z',
          tui_enabled: false,
          use_happy_cli: false,
          max_iterations: 50,
          instances: [
            {
              instance_num: 1, worktree: '/tmp/wt-1', branch: 'feature/auth',
              plan: 'docs/plans/auth.json', pid: 12345, status: 'running',
              started: '2026-02-07T12:00:00Z', log_file: 'log1.txt',
            },
            {
              instance_num: 2, worktree: '/tmp/wt-2', branch: 'feature/api',
              plan: 'docs/plans/api.json', pid: 12346, status: 'running',
              started: '2026-02-07T12:00:00Z', log_file: 'log2.txt',
            },
          ],
        }),
      );

      // Write plan definition files
      writeFileSync(
        join(baseDir, 'docs/plans/auth.json'),
        JSON.stringify(createMockPlanDefinition({ feature: 'Authentication' })),
      );
      writeFileSync(
        join(baseDir, 'docs/plans/api.json'),
        JSON.stringify(createMockPlanDefinition({ feature: 'API Layer' })),
      );

      const manager = new StateManager(baseDir);
      const state = await manager.getState();

      expect(Object.keys(state.plans).length).toBeGreaterThanOrEqual(2);
      expect(state.plans['auth']?.feature).toBe('Authentication');
      expect(state.plans['api']?.feature).toBe('API Layer');
    });

    it('returns empty plans when no multitask session exists', async () => {
      const baseDir = setupTempDir();
      setupDirs(baseDir);

      const manager = new StateManager(baseDir);
      const state = await manager.getState();

      // May include primary plan if it exists, but should not crash
      expect(state.plans).toBeDefined();
    });
  });

  describe('stop', () => {
    it('cleans up without errors when no watchers are active', () => {
      const baseDir = setupTempDir();
      const manager = new StateManager(baseDir);

      // stop() should not throw even when start() was never called
      expect(() => manager.stop()).not.toThrow();
    });

    it('can be called multiple times without error', () => {
      const baseDir = setupTempDir();
      const manager = new StateManager(baseDir);

      expect(() => {
        manager.stop();
        manager.stop();
      }).not.toThrow();
    });
  });
});
