/**
 * ACS Client - Agent Cognition System Integration
 *
 * Defines the interface contract for integrating with ACS, the cross-project
 * memory layer. ACS is OPTIONAL — all methods degrade gracefully when unavailable.
 *
 * Architecture:
 * - This TypeScript file defines types and serves as a reference implementation
 * - Shell scripts source scripts/lib/acs-client.sh for actual execution
 * - Commands (markdown) instruct Claude to use the shell bridge
 * - Claude reads this file for type context when generating API calls
 *
 * Detection priority:
 * 1. ACS_URL environment variable
 * 2. config.json acs.url setting
 * 3. Health check GET /api/health (cached 60s)
 * 4. acs.enabled: false = kill switch
 *
 * Usage:
 * - createACSClient(): Factory that returns Live or Noop client
 * - NoopACSClient: Safe defaults when ACS is unavailable
 * - formatACSContext(): Render query results as markdown for command injection
 *
 * @module acs-client
 */

// ============================================================================
// Configuration
// ============================================================================

/**
 * ACS connection configuration.
 * Resolved from environment variables and config.json.
 */
export interface ACSConfig {
  /** Base URL of the ACS instance (e.g., "http://localhost:3000") */
  baseUrl: string;
  /** Tenant ID for multi-tenant isolation */
  tenantId: string;
  /** Request timeout in milliseconds */
  timeoutMs: number;
  /** Whether to log ACS operations for debugging */
  debug: boolean;
}

/** Default configuration values */
export const ACS_DEFAULTS = {
  tenantId: "default",
  timeoutMs: 5000,
  debug: false,
} as const;

// ============================================================================
// Health Check Types
// ============================================================================

/**
 * ACS health check response.
 * Maps to GET /api/health response.
 */
export interface ACSHealthStatus {
  status: "healthy" | "degraded" | "unhealthy";
  timestamp: string;
  version: string;
  environment: string;
  checks: {
    database: {
      status: "up" | "down";
      latencyMs: number;
      error?: string;
    };
  };
}

// ============================================================================
// Retrieval Types (POST /api/retrieve)
// ============================================================================

/** Memory categories supported by ACS */
export type ACSMemoryCategory =
  | "conversation"
  | "document"
  | "insight"
  | "task"
  | "preference"
  | "fact";

/** Memory storage tiers */
export type ACSMemoryTier = "HOT" | "WARM" | "COLD" | "STALE";

/**
 * Options for querying ACS hybrid retrieval.
 * Maps to the RetrieveRequestSchema in ACS (POST /api/retrieve).
 */
export interface ACSQueryOptions {
  /** Filter by memory categories */
  categories?: ACSMemoryCategory[];
  /** Filter by memory tiers */
  tiers?: Exclude<ACSMemoryTier, "STALE">[];
  /** Time range filter (ISO 8601 datetime strings) */
  timeRange?: {
    start?: string;
    end?: string;
  };
  /** Filter by linked entity IDs (UUIDs) */
  entityIds?: string[];
  /** Minimum confidence score (0-1) */
  minConfidence?: number;
  /** Maximum number of results (1-100) */
  maxResults?: number;
  /** Whether to include graph traversal (default true) */
  includeGraph?: boolean;
  /** Graph traversal depth (1-3, default 2) */
  graphHops?: number;
  /** Token budget for synthesized response (100-16000, default 4000) */
  tokenBudget?: number;
  /** Output format for synthesized context */
  outputFormat?: "markdown" | "structured" | "plain";
}

/**
 * A single retrieved memory from ACS.
 * Subset of the full Memory type, focused on retrieval results.
 */
export interface ACSRetrievedMemory {
  id: string;
  content: string;
  contentSnippet: string;
  category: string;
  tier: string;
  relevanceScore: number;
  priorityScore: number;
  source: "vector" | "graph" | "both";
  createdAt: string;
}

/** Entity discovered through retrieval */
export interface ACSRetrievedEntity {
  id: string;
  name: string;
  type: string;
  memoryCount: number;
}

/** Relationship between entities */
export interface ACSRelationship {
  source: string;
  target: string;
  label: string;
  weight: number;
}

/**
 * Full retrieval response from ACS.
 * Maps to the RetrieveResponse in ACS POST /api/retrieve.
 */
export interface ACSQueryResult {
  /** Synthesized context string (markdown, structured, or plain text) */
  context: string;
  /** Individual memories that contributed to the context */
  memories: ACSRetrievedMemory[];
  /** Entities discovered through retrieval */
  entities: ACSRetrievedEntity[];
  /** Relationships between entities */
  relationships: ACSRelationship[];
  /** Performance and usage metadata */
  metadata: {
    latencyMs: number;
    memoriesScanned: number;
    vectorResults: number;
    graphResults: number;
    tokensUsed: number;
    tokenBudget: number;
  };
}

// ============================================================================
// Memory Storage Types (POST /api/memories)
// ============================================================================

/**
 * A learning to store in ACS.
 * Maps to the CreateMemorySchema in ACS.
 */
export interface ACSLearning {
  /** The learning content (rule text, pattern, correction, insight) */
  content: string;
  /** Short summary for display (auto-truncated to 200 chars if omitted) */
  contentSnippet?: string;
  /** Memory category — learnings are typically 'insight' or 'fact' */
  category: "insight" | "fact" | "preference" | "task";
  /** Storage tier — learnings default to WARM */
  tier?: "HOT" | "WARM" | "COLD";
  /** Confidence score (0-1), defaults to 1.0 */
  confidenceScore?: number;
  /** Whether to pin this memory (prevents archival/consolidation) */
  isPinned?: boolean;
  /** Metadata for provenance tracking */
  metadata?: {
    /** Source command that generated this learning (e.g., "/learn") */
    source?: string;
    /** Project where the learning originated */
    project?: string;
    /** Git commit hash associated with the learning */
    commit?: string;
    /** The mistake or correction that led to this learning */
    mistake?: string;
    /** Category of the rule (typescript, security, accessibility, etc.) */
    ruleCategory?: string;
    /** Agent ID that generated the learning */
    agentId?: string;
  };
}

/**
 * Response from storing a learning in ACS.
 * Subset of the full Memory type — what the toolkit needs after storing.
 */
export interface ACSStoredMemory {
  id: string;
  tenantId: string;
  content: string;
  contentSnippet: string;
  category: string;
  tier: string;
  confidenceScore: number;
  createdAt: string;
}

// ============================================================================
// Memory Search Types (GET /api/memories)
// ============================================================================

/**
 * Filters for searching memories in ACS.
 * Maps to query parameters on GET /api/memories.
 */
export interface ACSSearchFilters {
  /** Full-text search query */
  search?: string;
  /** Filter by tiers */
  tier?: ACSMemoryTier[];
  /** Filter by categories */
  category?: ACSMemoryCategory[];
  /** Filter by linked entity ID */
  entityId?: string;
  /** Date range start (ISO 8601) */
  dateFrom?: string;
  /** Date range end (ISO 8601) */
  dateTo?: string;
  /** Only pinned memories */
  isPinned?: boolean;
  /** Only flagged memories */
  isFlagged?: boolean;
  /** Page number (1-based, default 1) */
  page?: number;
  /** Results per page (max 100, default 20) */
  pageSize?: number;
  /** Sort field */
  sort?: "createdAt" | "updatedAt" | "accessCount" | "lastAccessedAt";
  /** Sort direction */
  order?: "asc" | "desc";
}

/**
 * Paginated search results from ACS.
 * Maps to MemoryListResponse from ACS types.
 */
export interface ACSSearchResult {
  memories: ACSStoredMemory[];
  total: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
}

// ============================================================================
// Consolidation Types (POST /api/consolidation/trigger)
// ============================================================================

/** Consolidation job types */
export type ACSConsolidationType = "nightly" | "weekly" | "monthly" | "manual";

/**
 * Response from triggering a consolidation job.
 * Subset of ConsolidationJob from ACS types.
 */
export interface ACSConsolidationResult {
  id: string;
  type: ACSConsolidationType;
  status: "pending" | "running";
  isDryRun: boolean;
}

// ============================================================================
// Client Interface
// ============================================================================

/**
 * The ACS Client interface.
 *
 * All methods return Promises and handle errors gracefully.
 * When ACS is unavailable, the NoopACSClient returns safe empty defaults.
 * When ACS is available but a call fails, the wrapped client catches
 * errors and falls back to noop behavior.
 */
export interface ACSClient {
  /**
   * Check if ACS is available and healthy.
   * Makes a GET request to /api/health and checks the status field.
   *
   * @returns true if ACS responds with status "healthy" or "degraded"
   */
  isAvailable(): Promise<boolean>;

  /**
   * Query ACS for relevant context using hybrid vector + graph search.
   * Makes a POST request to /api/retrieve.
   *
   * Use this for cross-project knowledge retrieval — finding patterns,
   * learnings, and decisions from past work across all projects.
   *
   * @param query - Natural language query describing what context is needed
   * @param options - Search filters, limits, and output preferences
   * @returns Retrieved context with memories, entities, and relationships
   *
   * @example
   * const result = await client.query(
   *   "TypeScript patterns for error handling in API routes",
   *   { categories: ['insight', 'fact'], maxResults: 10, tokenBudget: 2000 }
   * );
   * // result.context contains synthesized markdown
   */
  query(query: string, options?: ACSQueryOptions): Promise<ACSQueryResult>;

  /**
   * Store a new learning in ACS as a persistent memory.
   * Makes a POST request to /api/memories.
   *
   * Use this to persist learnings, patterns, corrections, and insights
   * so they can be retrieved in future sessions across any project.
   *
   * @param learning - The learning to persist (content, category, metadata)
   * @returns The stored memory record with generated ID
   *
   * @example
   * await client.store({
   *   content: "NEVER use outline-none without providing focus-visible replacement",
   *   category: 'insight',
   *   metadata: { source: '/learn', project: 'my-app', ruleCategory: 'accessibility' }
   * });
   */
  store(learning: ACSLearning): Promise<ACSStoredMemory>;

  /**
   * Search for specific memories in ACS with filters.
   * Makes a GET request to /api/memories with query parameters.
   *
   * Use this for targeted lookups — finding specific memories by category,
   * tier, date range, or full-text search.
   *
   * @param filters - Search criteria (text, tier, category, date range, pagination)
   * @returns Paginated list of matching memories
   *
   * @example
   * const results = await client.search({
   *   search: "authentication patterns",
   *   category: ['insight'],
   *   tier: ['HOT', 'WARM'],
   *   pageSize: 10,
   * });
   */
  search(filters: ACSSearchFilters): Promise<ACSSearchResult>;

  /**
   * Trigger a memory consolidation job in ACS.
   * Makes a POST request to /api/consolidation/trigger.
   *
   * Consolidation reconciles conflicting information, merges redundant memories,
   * and updates memory tiers based on access patterns.
   *
   * @param type - Type of consolidation to run
   * @param dryRun - If true, simulates consolidation without making changes
   * @returns The created consolidation job with ID and status
   */
  triggerConsolidation(
    type: ACSConsolidationType,
    dryRun?: boolean
  ): Promise<ACSConsolidationResult>;

  /**
   * Get project-specific context from ACS.
   * Convenience method that calls query() with project-scoped parameters.
   *
   * Retrieves learnings, patterns, and decisions from past work on the
   * specified project, optionally focused on a specific area.
   *
   * @param projectName - The project to get context for
   * @param focus - Optional focus area (e.g., "authentication", "testing patterns")
   * @returns Synthesized context relevant to the project and focus area
   *
   * @example
   * const context = await client.getContext("my-app", "database patterns");
   */
  getContext(projectName: string, focus?: string): Promise<ACSQueryResult>;
}

// ============================================================================
// Empty Results (used by NoopACSClient and error fallbacks)
// ============================================================================

/** Empty query result returned when ACS is unavailable */
const EMPTY_QUERY_RESULT: ACSQueryResult = {
  context: "",
  memories: [],
  entities: [],
  relationships: [],
  metadata: {
    latencyMs: 0,
    memoriesScanned: 0,
    vectorResults: 0,
    graphResults: 0,
    tokensUsed: 0,
    tokenBudget: 0,
  },
};

/** Empty search result returned when ACS is unavailable */
const EMPTY_SEARCH_RESULT: ACSSearchResult = {
  memories: [],
  total: 0,
  page: 1,
  pageSize: 20,
  hasMore: false,
};

// ============================================================================
// Noop Implementation
// ============================================================================

/**
 * No-op ACS client that returns safe defaults.
 * Used when ACS_URL is not configured or ACS is unreachable.
 * Never throws errors. All methods return immediately with empty results.
 */
export const NoopACSClient: ACSClient = {
  async isAvailable(): Promise<boolean> {
    return false;
  },

  async query(): Promise<ACSQueryResult> {
    return EMPTY_QUERY_RESULT;
  },

  async store(learning: ACSLearning): Promise<ACSStoredMemory> {
    return {
      id: "noop",
      tenantId: "noop",
      content: learning.content,
      contentSnippet:
        learning.contentSnippet ?? learning.content.slice(0, 200),
      category: learning.category,
      tier: learning.tier ?? "WARM",
      confidenceScore: learning.confidenceScore ?? 1.0,
      createdAt: new Date().toISOString(),
    };
  },

  async search(): Promise<ACSSearchResult> {
    return EMPTY_SEARCH_RESULT;
  },

  async triggerConsolidation(
    type: ACSConsolidationType
  ): Promise<ACSConsolidationResult> {
    return { id: "noop", type, status: "pending", isDryRun: true };
  },

  async getContext(): Promise<ACSQueryResult> {
    return EMPTY_QUERY_RESULT;
  },
};

// ============================================================================
// Live Implementation
// ============================================================================

/**
 * Create a live ACS client that makes real HTTP calls to the ACS API.
 * Uses native fetch (Node 18+) with no external dependencies.
 * Each method includes a timeout via AbortController.
 *
 * @param config - ACS connection configuration
 * @returns Live ACS client instance
 */
export function createLiveACSClient(config: ACSConfig): ACSClient {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "x-tenant-id": config.tenantId,
  };

  /** Internal fetch wrapper with timeout and error handling */
  async function fetchACS<T>(
    path: string,
    options: RequestInit = {}
  ): Promise<T> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), config.timeoutMs);

    try {
      const response = await fetch(`${config.baseUrl}${path}`, {
        ...options,
        headers: {
          ...headers,
          ...(options.headers as Record<string, string> | undefined),
        },
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(
          `ACS API error: ${response.status} ${response.statusText}`
        );
      }

      return (await response.json()) as T;
    } finally {
      clearTimeout(timeoutId);
    }
  }

  return {
    async isAvailable(): Promise<boolean> {
      try {
        const health = await fetchACS<ACSHealthStatus>("/api/health");
        return health.status === "healthy" || health.status === "degraded";
      } catch {
        return false;
      }
    },

    async query(
      query: string,
      options: ACSQueryOptions = {}
    ): Promise<ACSQueryResult> {
      return fetchACS<ACSQueryResult>("/api/retrieve", {
        method: "POST",
        body: JSON.stringify({
          query,
          filters: {
            categories: options.categories,
            tiers: options.tiers,
            timeRange: options.timeRange,
            entityIds: options.entityIds,
            minConfidence: options.minConfidence,
          },
          options: {
            maxResults: options.maxResults,
            includeGraph: options.includeGraph,
            graphHops: options.graphHops,
            tokenBudget: options.tokenBudget,
            outputFormat: options.outputFormat,
          },
        }),
      });
    },

    async store(learning: ACSLearning): Promise<ACSStoredMemory> {
      return fetchACS<ACSStoredMemory>("/api/memories", {
        method: "POST",
        body: JSON.stringify({
          content: learning.content,
          contentSnippet:
            learning.contentSnippet ?? learning.content.slice(0, 200),
          category: learning.category,
          tier: learning.tier ?? "WARM",
          confidenceScore: learning.confidenceScore ?? 1.0,
          isPinned: learning.isPinned ?? false,
          metadata: learning.metadata,
        }),
      });
    },

    async search(filters: ACSSearchFilters): Promise<ACSSearchResult> {
      const params = new URLSearchParams();
      if (filters.search) params.set("search", filters.search);
      if (filters.tier?.length) params.set("tier", filters.tier.join(","));
      if (filters.category?.length)
        params.set("category", filters.category.join(","));
      if (filters.entityId) params.set("entityId", filters.entityId);
      if (filters.dateFrom) params.set("dateFrom", filters.dateFrom);
      if (filters.dateTo) params.set("dateTo", filters.dateTo);
      if (filters.isPinned !== undefined)
        params.set("isPinned", String(filters.isPinned));
      if (filters.isFlagged !== undefined)
        params.set("isFlagged", String(filters.isFlagged));
      if (filters.page) params.set("page", String(filters.page));
      if (filters.pageSize) params.set("pageSize", String(filters.pageSize));
      if (filters.sort) params.set("sort", filters.sort);
      if (filters.order) params.set("order", filters.order);

      return fetchACS<ACSSearchResult>(
        `/api/memories?${params.toString()}`
      );
    },

    async triggerConsolidation(
      type: ACSConsolidationType,
      dryRun = false
    ): Promise<ACSConsolidationResult> {
      return fetchACS<ACSConsolidationResult>("/api/consolidation/trigger", {
        method: "POST",
        body: JSON.stringify({ type, isDryRun: dryRun }),
      });
    },

    async getContext(
      projectName: string,
      focus?: string
    ): Promise<ACSQueryResult> {
      const query = focus
        ? `Project "${projectName}": ${focus}`
        : `Project context and learnings for "${projectName}"`;

      return this.query(query, {
        categories: ["insight", "fact", "preference"],
        tiers: ["HOT", "WARM"],
        maxResults: 20,
        tokenBudget: 3000,
        outputFormat: "markdown",
        includeGraph: true,
      });
    },
  };
}

// ============================================================================
// Factory with Detection and Caching
// ============================================================================

/** Cached client instance (singleton per process) */
let cachedClient: ACSClient | null = null;

/** Cached availability with TTL */
let availabilityCache: { available: boolean; checkedAt: number } | null = null;
const AVAILABILITY_CACHE_TTL_MS = 60_000;

/**
 * Create or return the cached ACS client.
 *
 * Detection strategy:
 * 1. Check ACS_URL (or ACS_BASE_URL) environment variable
 * 2. If no URL configured, return NoopACSClient immediately (zero overhead)
 * 3. If URL is set, create a wrapped live client that:
 *    - Checks availability before each call (cached 60s)
 *    - Falls back to noop behavior on any error
 *    - Never throws or blocks the calling command
 *
 * @returns ACS client — live if ACS is configured, noop otherwise
 */
export function createACSClient(): ACSClient {
  if (cachedClient) return cachedClient;

  const acsUrl =
    typeof process !== "undefined"
      ? (process.env.ACS_URL ?? process.env.ACS_BASE_URL)
      : undefined;

  if (!acsUrl) {
    cachedClient = NoopACSClient;
    return cachedClient;
  }

  const config: ACSConfig = {
    baseUrl: acsUrl.replace(/\/$/, ""),
    tenantId: process.env.ACS_TENANT_ID ?? ACS_DEFAULTS.tenantId,
    timeoutMs: Number(process.env.ACS_TIMEOUT_MS) || ACS_DEFAULTS.timeoutMs,
    debug: process.env.ACS_DEBUG === "true",
  };

  const liveClient = createLiveACSClient(config);

  /** Wrapped client with availability caching and error recovery */
  const wrappedClient: ACSClient = {
    async isAvailable(): Promise<boolean> {
      const now = Date.now();
      if (
        availabilityCache &&
        now - availabilityCache.checkedAt < AVAILABILITY_CACHE_TTL_MS
      ) {
        return availabilityCache.available;
      }
      const available = await liveClient.isAvailable();
      availabilityCache = { available, checkedAt: now };
      return available;
    },

    async query(
      query: string,
      options?: ACSQueryOptions
    ): Promise<ACSQueryResult> {
      if (!(await this.isAvailable())) return EMPTY_QUERY_RESULT;
      try {
        return await liveClient.query(query, options);
      } catch {
        return EMPTY_QUERY_RESULT;
      }
    },

    async store(learning: ACSLearning): Promise<ACSStoredMemory> {
      if (!(await this.isAvailable())) return NoopACSClient.store(learning);
      try {
        return await liveClient.store(learning);
      } catch {
        return NoopACSClient.store(learning);
      }
    },

    async search(filters: ACSSearchFilters): Promise<ACSSearchResult> {
      if (!(await this.isAvailable())) return EMPTY_SEARCH_RESULT;
      try {
        return await liveClient.search(filters);
      } catch {
        return EMPTY_SEARCH_RESULT;
      }
    },

    async triggerConsolidation(
      type: ACSConsolidationType,
      dryRun?: boolean
    ): Promise<ACSConsolidationResult> {
      if (!(await this.isAvailable()))
        return NoopACSClient.triggerConsolidation(type, dryRun);
      try {
        return await liveClient.triggerConsolidation(type, dryRun);
      } catch {
        return NoopACSClient.triggerConsolidation(type, dryRun);
      }
    },

    async getContext(
      projectName: string,
      focus?: string
    ): Promise<ACSQueryResult> {
      if (!(await this.isAvailable())) return EMPTY_QUERY_RESULT;
      try {
        return await liveClient.getContext(projectName, focus);
      } catch {
        return EMPTY_QUERY_RESULT;
      }
    },
  };

  cachedClient = wrappedClient;
  return cachedClient;
}

/**
 * Reset the cached client and availability state.
 * Useful for testing or when ACS configuration changes.
 */
export function resetACSClient(): void {
  cachedClient = null;
  availabilityCache = null;
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Format an ACS query result as markdown for injection into command context.
 * Used by /iterate, /loop, /kickoff when they retrieve ACS context.
 *
 * @param result - The query result from ACS
 * @param maxMemories - Maximum number of individual memories to include
 * @returns Formatted markdown string, or empty string if no results
 */
export function formatACSContext(
  result: ACSQueryResult,
  maxMemories = 5
): string {
  if (!result.context && result.memories.length === 0) {
    return "";
  }

  const lines: string[] = ["## ACS Context (Cross-Project Learnings)", ""];

  if (result.context) {
    lines.push(result.context);
    lines.push("");
  }

  if (result.memories.length > 0) {
    const showing = Math.min(maxMemories, result.memories.length);
    lines.push(
      `*${result.memories.length} relevant memories found (showing top ${showing})*`
    );
    lines.push("");

    for (const memory of result.memories.slice(0, maxMemories)) {
      const pct = (memory.relevanceScore * 100).toFixed(0);
      lines.push(
        `- **[${memory.category}/${memory.tier}]** ${memory.contentSnippet} *(relevance: ${pct}%)*`
      );
    }
  }

  if (result.entities.length > 0) {
    lines.push("");
    lines.push(
      `**Related entities:** ${result.entities.map((e) => e.name).join(", ")}`
    );
  }

  return lines.join("\n");
}
