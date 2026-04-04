/**
 * State manager watches filesystem for changes to orchestrator.json, session.json, and plan.json
 * Emits events when state changes are detected.
 *
 * Supports two orchestrator sources:
 * 1. orchestrator.json (preferred, from a rich orchestrator)
 * 2. multitask-session.json (fallback, synthesized into OrchestratorState)
 */

import { EventEmitter } from "events";
import { watch, existsSync, FSWatcher } from "fs";
import { readFile } from "fs/promises";
import { join } from "path";
import type {
  OrchestratorState,
  SessionState,
  PlanDefinition,
  MultitaskInstanceRaw,
  PipelineState,
} from "./types.js";
import {
  parseOrchestratorState,
  parseSessionState,
  parseMultitaskSessionRaw,
  synthesizeOrchestratorFromMultitask,
  parsePipelineState,
} from "./parsers.js";

const POLL_INTERVAL_MS = 2000;

export interface StateManagerEvents {
  orchestrator_update: (state: OrchestratorState) => void;
  session_update: (state: SessionState) => void;
  plan_update: (plan: PlanDefinition) => void;
  plans_update: (plans: Record<string, PlanDefinition>) => void;
  pipeline_update: (pipelines: Record<string, PipelineState>) => void;
  error: (error: Error) => void;
}

export declare interface StateManager {
  on<E extends keyof StateManagerEvents>(
    event: E,
    listener: StateManagerEvents[E],
  ): this;
  emit<E extends keyof StateManagerEvents>(
    event: E,
    ...args: Parameters<StateManagerEvents[E]>
  ): boolean;
}

export class StateManager extends EventEmitter {
  private watchers: FSWatcher[] = [];
  private orchestratorPath: string;
  private multitaskSessionPath: string;
  private sessionPath: string;
  private planPath: string;
  private planName: string;
  private baseDir: string;
  private hasOrchestratorFile = false;
  private planWatchers: Map<string, FSWatcher> = new Map();
  private planDefinitions: Map<string, PlanDefinition> = new Map();
  private pipelineWatchers: Map<string, FSWatcher> = new Map();
  private pipelineStates: Map<string, PipelineState> = new Map();
  private stateDir: string;
  private debounceTimers: Map<string, NodeJS.Timeout> = new Map();
  private pollTimers: Set<NodeJS.Timeout> = new Set();
  private readonly debounceMs = 100;

  constructor(baseDir: string, planName: string = "web-viewer") {
    super();

    this.baseDir = baseDir;
    this.planName = planName;
    this.stateDir = join(baseDir, ".claude/state");
    this.orchestratorPath = join(baseDir, ".claude/state/orchestrator.json");
    this.multitaskSessionPath = join(
      baseDir,
      ".claude/state/multitask-session.json",
    );
    this.sessionPath = join(
      baseDir,
      `.claude/state/plans/${planName}/session.json`,
    );
    this.planPath = join(baseDir, `docs/plans/${planName}.json`);
  }

  /**
   * Start watching files for changes
   */
  async start(): Promise<void> {
    // Watch orchestrator.json
    this.watchFile(this.orchestratorPath, async () => {
      this.hasOrchestratorFile = true;
      const state = await this.readOrchestratorState();
      if (state) {
        this.emit("orchestrator_update", state);
      }
    });

    // Watch multitask-session.json (fallback orchestrator source)
    this.watchFile(this.multitaskSessionPath, async () => {
      await this.handleMultitaskSessionChange();
    });

    // Watch session.json (primary plan)
    this.watchFile(this.sessionPath, async () => {
      const state = await this.readSessionState();
      if (state) {
        this.emit("session_update", state);
      }
    });

    // Watch plan.json (primary plan)
    this.watchFile(this.planPath, async () => {
      const plan = await this.readPlanDefinition();
      if (plan) {
        this.emit("plan_update", plan);
      }
    });

    // Discover and watch plans from multitask instances
    await this.syncMultitaskPlans();

    // Discover and watch pipeline state files
    await this.syncPipelines();

    // Load initial state
    await this.loadInitialState();

    console.log("[StateManager] Started watching files");
    console.log(`  - Orchestrator: ${this.orchestratorPath}`);
    console.log(`  - Multitask session: ${this.multitaskSessionPath}`);
    console.log(`  - Session: ${this.sessionPath}`);
    console.log(`  - Plan: ${this.planPath}`);
  }

  /**
   * Stop watching files
   */
  stop(): void {
    for (const watcher of this.watchers) {
      watcher.close();
    }
    this.watchers = [];

    for (const watcher of this.planWatchers.values()) {
      watcher.close();
    }
    this.planWatchers.clear();
    this.planDefinitions.clear();

    for (const watcher of this.pipelineWatchers.values()) {
      watcher.close();
    }
    this.pipelineWatchers.clear();
    this.pipelineStates.clear();

    for (const timer of this.debounceTimers.values()) {
      clearTimeout(timer);
    }
    this.debounceTimers.clear();

    for (const timer of this.pollTimers) {
      clearInterval(timer);
    }
    this.pollTimers.clear();

    console.log("[StateManager] Stopped watching files");
  }

  /**
   * Get current state snapshot
   */
  async getState(): Promise<{
    orchestrator: OrchestratorState | null;
    session: SessionState | null;
    plan: PlanDefinition | null;
    plans: Record<string, PlanDefinition>;
    pipelines: Record<string, PipelineState>;
  }> {
    const [orchestrator, session, plan] = await Promise.all([
      this.readOrchestratorState(),
      this.readSessionState(),
      this.readPlanDefinition(),
    ]);

    // Prefer orchestrator.json; fall back to synthesized from multitask-session.json
    let effectiveOrchestrator = orchestrator;
    if (effectiveOrchestrator) {
      this.hasOrchestratorFile = true;
    } else {
      effectiveOrchestrator = await this.readSynthesizedOrchestratorState();
    }

    // Collect plans: use cached definitions if available, else discover from multitask session
    const plans: Record<string, PlanDefinition> = {};
    if (this.planDefinitions.size > 0) {
      for (const [name, def] of this.planDefinitions) {
        plans[name] = def;
      }
    } else {
      // Discover plans directly from multitask-session.json (cold start without start())
      const discovered = await this.discoverPlansFromMultitask();
      Object.assign(plans, discovered);
    }
    if (plan && !plans[this.planName]) {
      plans[this.planName] = plan;
    }

    // Collect pipeline states: use cached if available, else discover from state dir
    const pipelines: Record<string, PipelineState> = {};
    if (this.pipelineStates.size > 0) {
      for (const [id, state] of this.pipelineStates) {
        pipelines[id] = state;
      }
    } else {
      const discovered = await this.discoverPipelines();
      Object.assign(pipelines, discovered);
    }

    return { orchestrator: effectiveOrchestrator, session, plan, plans, pipelines };
  }

  /**
   * Load initial state and emit events
   */
  private async loadInitialState(): Promise<void> {
    const state = await this.getState();

    if (state.orchestrator) {
      this.emit("orchestrator_update", state.orchestrator);
    }
    if (state.session) {
      this.emit("session_update", state.session);
    }
    if (state.plan) {
      this.emit("plan_update", state.plan);
    }
    if (Object.keys(state.plans).length > 0) {
      this.emit("plans_update", state.plans);
    }
    if (Object.keys(state.pipelines).length > 0) {
      this.emit("pipeline_update", state.pipelines);
    }
  }

  /**
   * Handle changes to multitask-session.json
   */
  private async handleMultitaskSessionChange(): Promise<void> {
    // Use as orchestrator source only if orchestrator.json doesn't exist
    if (!this.hasOrchestratorFile) {
      const synthesized = await this.readSynthesizedOrchestratorState();
      if (synthesized) {
        this.emit("orchestrator_update", synthesized);
      }
    }

    // Discover and watch plan files referenced by instances
    await this.syncMultitaskPlans();
  }

  /**
   * Synthesize OrchestratorState from multitask-session.json
   */
  private async readSynthesizedOrchestratorState(): Promise<OrchestratorState | null> {
    try {
      const content = await readFile(this.multitaskSessionPath, "utf-8");
      const raw = JSON.parse(content);
      const session = parseMultitaskSessionRaw(raw);
      if (!session) return null;
      return synthesizeOrchestratorFromMultitask(session);
    } catch {
      return null;
    }
  }

  /**
   * Discover plan files from multitask instances and set up watchers
   */
  private async syncMultitaskPlans(): Promise<void> {
    try {
      const content = await readFile(this.multitaskSessionPath, "utf-8");
      const raw = JSON.parse(content);
      const session = parseMultitaskSessionRaw(raw);
      if (!session) return;

      const planPaths = new Set<string>();

      for (const instance of session.instances) {
        const planPath = this.resolveInstancePlanPath(instance);
        if (planPath) planPaths.add(planPath);
      }

      // Add watchers for new plan files
      for (const planPath of planPaths) {
        if (!this.planWatchers.has(planPath)) {
          this.watchPlanFile(planPath);
        }
      }

      // Remove watchers for plans no longer in the session
      for (const [path, watcher] of this.planWatchers) {
        if (!planPaths.has(path)) {
          watcher.close();
          this.planWatchers.delete(path);
          this.planDefinitions.delete(this.extractPlanName(path));
        }
      }

      await this.readAndEmitAllPlans();
    } catch {
      // multitask-session.json may not exist yet
    }
  }

  /**
   * Watch a plan file and re-emit all plans on change
   */
  private watchPlanFile(planPath: string): void {
    try {
      if (!existsSync(planPath)) return;

      const watcher = watch(planPath, (eventType) => {
        if (eventType === "change") {
          const existingTimer = this.debounceTimers.get(planPath);
          if (existingTimer) clearTimeout(existingTimer);

          const timer = setTimeout(async () => {
            this.debounceTimers.delete(planPath);
            try {
              await this.readAndEmitAllPlans();
            } catch (error) {
              this.emit("error", error as Error);
            }
          }, this.debounceMs);

          this.debounceTimers.set(planPath, timer);
        }
      });

      watcher.on("error", () => {
        // File may have been removed
      });

      this.planWatchers.set(planPath, watcher);
    } catch {
      // File doesn't exist yet
    }
  }

  /**
   * Read all watched plan definitions and emit plans_update
   */
  private async readAndEmitAllPlans(): Promise<void> {
    const plans: Record<string, PlanDefinition> = {};

    for (const planPath of this.planWatchers.keys()) {
      try {
        const content = await readFile(planPath, "utf-8");
        const parsed = JSON.parse(content) as PlanDefinition;
        const planName = this.extractPlanName(planPath);
        plans[planName] = parsed;
        this.planDefinitions.set(planName, parsed);
      } catch {
        // Skip unreadable plans
      }
    }

    // Include the primary plan if not already in the map
    const primaryPlan = await this.readPlanDefinition();
    if (primaryPlan && !plans[this.planName]) {
      plans[this.planName] = primaryPlan;
    }

    if (Object.keys(plans).length > 0) {
      this.emit("plans_update", plans);
    }
  }

  /**
   * Discover plan definitions from multitask-session.json without setting up watchers.
   * Used by getState() when called before start().
   */
  private async discoverPlansFromMultitask(): Promise<Record<string, PlanDefinition>> {
    const plans: Record<string, PlanDefinition> = {};
    try {
      const content = await readFile(this.multitaskSessionPath, "utf-8");
      const raw = JSON.parse(content);
      const session = parseMultitaskSessionRaw(raw);
      if (!session) return plans;

      for (const instance of session.instances) {
        const planPath = this.resolveInstancePlanPath(instance);
        if (!planPath) continue;
        try {
          const planContent = await readFile(planPath, "utf-8");
          const parsed = JSON.parse(planContent) as PlanDefinition;
          const name = this.extractPlanName(planPath);
          plans[name] = parsed;
        } catch {
          // Plan file may not exist yet
        }
      }
    } catch {
      // multitask-session.json may not exist
    }
    return plans;
  }

  /**
   * Resolve a plan file path for a multitask instance.
   * Prefers the worktree copy (where stories get marked passes:true)
   * over the main repo copy (which stays stale during execution).
   */
  private resolveInstancePlanPath(instance: MultitaskInstanceRaw): string | null {
    if (!instance.plan) return null;
    const relativePlan = instance.plan.endsWith(".json")
      ? instance.plan
      : `docs/plans/${instance.plan}.json`;

    // Prefer worktree path — that's where the running instance updates passes
    if (instance.worktree) {
      const worktreePlan = join(instance.worktree, relativePlan);
      if (existsSync(worktreePlan)) return worktreePlan;
    }

    // Fall back to base dir
    return join(this.baseDir, relativePlan);
  }

  /**
   * Extract plan name from file path (e.g., "auth" from "/path/docs/plans/auth.json")
   */
  private extractPlanName(planPath: string): string {
    const basename = planPath.split("/").pop() ?? "";
    return basename.replace(/\.json$/, "");
  }

  /**
   * Watch a file for changes with debouncing.
   * Handles ENOENT gracefully by polling until the file appears.
   */
  private watchFile(filePath: string, onChange: () => Promise<void>): void {
    try {
      if (!existsSync(filePath)) {
        this.pollForFile(filePath, onChange);
        return;
      }

      const watcher = watch(filePath, (eventType) => {
        if (eventType === "change") {
          const existingTimer = this.debounceTimers.get(filePath);
          if (existingTimer) {
            clearTimeout(existingTimer);
          }

          const timer = setTimeout(async () => {
            this.debounceTimers.delete(filePath);
            try {
              await onChange();
            } catch (error) {
              this.emit("error", error as Error);
            }
          }, this.debounceMs);

          this.debounceTimers.set(filePath, timer);
        }
      });

      watcher.on("error", () => {
        // Silently handle - file may have been removed
      });

      this.watchers.push(watcher);
    } catch {
      // Fall back to polling if watch() itself throws
      this.pollForFile(filePath, onChange);
    }
  }

  /**
   * Poll for a file to appear, then set up a real watcher
   */
  private pollForFile(
    filePath: string,
    onChange: () => Promise<void>,
  ): void {
    const timer = setInterval(() => {
      if (existsSync(filePath)) {
        this.pollTimers.delete(timer);
        clearInterval(timer);
        // File appeared - set up real watcher and trigger initial read
        this.watchFile(filePath, onChange);
        onChange().catch(() => {});
      }
    }, POLL_INTERVAL_MS);

    this.pollTimers.add(timer);
  }

  /**
   * Discover pipeline-*.json files in .claude/state/ and set up watchers
   */
  private async syncPipelines(): Promise<void> {
    try {
      if (!existsSync(this.stateDir)) return;

      const { readdir } = await import("fs/promises");
      const files = await readdir(this.stateDir);
      const pipelineFiles = files.filter(
        (f) => f.startsWith("pipeline-") && f.endsWith(".json") && !f.includes(".events."),
      );

      for (const file of pipelineFiles) {
        const filePath = join(this.stateDir, file);
        if (!this.pipelineWatchers.has(filePath)) {
          this.watchPipelineFile(filePath);
        }
      }

      // Also poll for new pipeline files appearing
      const timer = setInterval(async () => {
        try {
          if (!existsSync(this.stateDir)) return;
          const currentFiles = await readdir(this.stateDir);
          const currentPipelines = currentFiles.filter(
            (f) => f.startsWith("pipeline-") && f.endsWith(".json") && !f.includes(".events."),
          );
          for (const file of currentPipelines) {
            const filePath = join(this.stateDir, file);
            if (!this.pipelineWatchers.has(filePath)) {
              this.watchPipelineFile(filePath);
              await this.readAndEmitAllPipelines();
            }
          }
        } catch {
          // Ignore polling errors
        }
      }, POLL_INTERVAL_MS);

      this.pollTimers.add(timer);

      await this.readAndEmitAllPipelines();
    } catch {
      // State dir may not exist yet
    }
  }

  /**
   * Watch a single pipeline state file and re-emit all pipelines on change
   */
  private watchPipelineFile(filePath: string): void {
    try {
      if (!existsSync(filePath)) return;

      const watcher = watch(filePath, (eventType) => {
        if (eventType === "change") {
          const existingTimer = this.debounceTimers.get(filePath);
          if (existingTimer) clearTimeout(existingTimer);

          const timer = setTimeout(async () => {
            this.debounceTimers.delete(filePath);
            try {
              await this.readAndEmitAllPipelines();
            } catch (error) {
              this.emit("error", error as Error);
            }
          }, this.debounceMs);

          this.debounceTimers.set(filePath, timer);
        }
      });

      watcher.on("error", () => {
        // File may have been removed
      });

      this.pipelineWatchers.set(filePath, watcher);
    } catch {
      // File doesn't exist yet
    }
  }

  /**
   * Read all watched pipeline state files and emit pipeline_update
   */
  private async readAndEmitAllPipelines(): Promise<void> {
    const pipelines: Record<string, PipelineState> = {};

    for (const filePath of this.pipelineWatchers.keys()) {
      try {
        const content = await readFile(filePath, "utf-8");
        const raw = JSON.parse(content);
        const parsed = parsePipelineState(raw);
        if (parsed) {
          pipelines[parsed.pipelineId] = parsed;
          this.pipelineStates.set(parsed.pipelineId, parsed);
        }
      } catch {
        // Skip unreadable pipeline files
      }
    }

    if (Object.keys(pipelines).length > 0) {
      this.emit("pipeline_update", pipelines);
    }
  }

  /**
   * Discover pipeline states from .claude/state/ without setting up watchers.
   * Used by getState() when called before start().
   */
  private async discoverPipelines(): Promise<Record<string, PipelineState>> {
    const pipelines: Record<string, PipelineState> = {};
    try {
      if (!existsSync(this.stateDir)) return pipelines;

      const { readdir } = await import("fs/promises");
      const files = await readdir(this.stateDir);
      const pipelineFiles = files.filter(
        (f) => f.startsWith("pipeline-") && f.endsWith(".json") && !f.includes(".events."),
      );

      for (const file of pipelineFiles) {
        try {
          const content = await readFile(join(this.stateDir, file), "utf-8");
          const raw = JSON.parse(content);
          const parsed = parsePipelineState(raw);
          if (parsed) {
            pipelines[parsed.pipelineId] = parsed;
          }
        } catch {
          // Skip unreadable files
        }
      }
    } catch {
      // State dir may not exist
    }
    return pipelines;
  }

  /**
   * Read and parse orchestrator.json
   */
  private async readOrchestratorState(): Promise<OrchestratorState | null> {
    try {
      const content = await readFile(this.orchestratorPath, "utf-8");
      const raw = JSON.parse(content);
      return parseOrchestratorState(raw);
    } catch {
      return null;
    }
  }

  /**
   * Read and parse session.json
   */
  private async readSessionState(): Promise<SessionState | null> {
    try {
      const content = await readFile(this.sessionPath, "utf-8");
      const raw = JSON.parse(content);
      return parseSessionState(raw);
    } catch {
      return null;
    }
  }

  /**
   * Read and parse plan definition
   */
  private async readPlanDefinition(): Promise<PlanDefinition | null> {
    try {
      const content = await readFile(this.planPath, "utf-8");
      return JSON.parse(content) as PlanDefinition;
    } catch {
      return null;
    }
  }
}
