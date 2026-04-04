import { describe, it, expect } from 'vitest';
import {
  createMockAgent,
  createMockMetrics,
  createMockOrchestratorState,
  createMockSessionState,
} from './factories.js';

describe('factories', () => {
  describe('createMockAgent', () => {
    it('merges nested metrics overrides into full AgentMetrics', () => {
      const agent = createMockAgent({ metrics: { cost: 999 } });
      expect(agent.metrics.cost).toBe(999);
      expect(agent.metrics.tokensIn).toBe(12000);
      expect(agent.metrics.tokensOut).toBe(4500);
      expect(agent.metrics.totalTokens).toBe(16500);
      expect(agent.metrics.startTime).toBe('2026-02-05T10:00:00Z');
    });

    it('merges nested context overrides into full AgentContext', () => {
      const agent = createMockAgent({ context: { percentage: 50 } });
      expect(agent.context.percentage).toBe(50);
      expect(agent.context.used).toBe(50000);
      expect(agent.context.total).toBe(200000);
    });
  });

  describe('createMockOrchestratorState', () => {
    it('merges nested costs overrides into full CostSummary', () => {
      const state = createMockOrchestratorState({ costs: { today: 100 } });
      expect(state.costs.today).toBe(100);
      expect(state.costs.sessions).toBe(12);
      expect(state.costs.sevenDay).toBe(32.5);
      expect(state.costs.thirtyDay).toBe(120);
    });

    it('merges nested agents overrides via createMockAgentSummary', () => {
      const state = createMockOrchestratorState({ agents: { activeCount: 3 } });
      expect(state.agents.activeCount).toBe(3);
      expect(state.agents.agents).toHaveLength(1);
      expect(state.agents.pendingCount).toBe(0);
    });
  });

  describe('createMockSessionState', () => {
    it('merges nested plan overrides into full PlanInfo', () => {
      const state = createMockSessionState({ plan: { branch: 'fix/foo' } });
      expect(state.plan.branch).toBe('fix/foo');
      expect(state.plan.path).toBe('docs/plans/test-plan.json');
      expect(state.plan.name).toBe('test-plan');
    });

    it('merges nested git overrides into full GitInfo', () => {
      const state = createMockSessionState({ git: { head_commit: 'deadbeef' } });
      expect(state.git.head_commit).toBe('deadbeef');
      expect(state.git.branch).toBe('feature/test-plan');
      expect(state.git.modified_files).toEqual(['src/index.ts']);
    });
  });

  describe('createMockMetrics', () => {
    it('returns full AgentMetrics with overrides applied', () => {
      const metrics = createMockMetrics({ cost: 999 });
      expect(metrics.cost).toBe(999);
      expect(metrics.tokensIn).toBe(12000);
      expect(metrics.tokensOut).toBe(4500);
    });
  });
});
