/**
 * Agent panel component for displaying agent cards
 * Renders agent status, metrics, and context usage in grid layout
 */

/**
 * Update agent grid with current agents
 * @param {Array} agents - Array of agent objects from orchestrator state
 */
function updateAgentGrid(agents) {
  const agentsGrid = document.getElementById("agents-grid");
  const emptyState = document.getElementById("agents-empty");

  if (!agentsGrid) return;

  // Show empty state if no agents
  if (!agents || agents.length === 0) {
    agentsGrid.innerHTML = "";
    if (emptyState) {
      agentsGrid.appendChild(emptyState);
    } else {
      agentsGrid.innerHTML =
        '<div class="empty-state"><p>No active agents</p></div>';
    }
    return;
  }

  // Hide empty state
  if (emptyState) {
    emptyState.remove();
  }

  // Build agent cards HTML
  const cardsHTML = agents.map((agent) => createAgentCard(agent)).join("");
  agentsGrid.innerHTML = cardsHTML;
}

/**
 * Create HTML for a single agent card
 * @param {Object} agent - Agent object with id, name, status, metrics, etc.
 * @returns {string} HTML string for agent card
 */
function createAgentCard(agent) {
  const statusClass = `agent-status-${agent.status}`;
  const contextPercentage = agent.context?.percentage || 0;
  const contextClass = getContextClass(contextPercentage);

  // Format metrics
  const tokensIn = formatTokens(agent.metrics?.tokensIn || 0);
  const tokensOut = formatTokens(agent.metrics?.tokensOut || 0);
  const cost = formatCost(agent.metrics?.cost || 0);
  const duration = agent.metrics?.duration
    ? formatDuration(agent.metrics.duration)
    : "In Progress";

  // Format context usage
  const contextUsed = formatTokens(agent.context?.used || 0);
  const contextTotal = formatTokens(agent.context?.total || 0);
  const contextPct = formatPercentage(contextPercentage, 0);

  // Get status badge
  const statusBadge = getStatusBadge(agent.status);

  // Get type badge
  const typeBadge = getTypeBadge(agent.type);

  // Current command or task
  const currentActivity = agent.currentCommand || agent.tasks?.[0] || "Idle";
  const truncatedActivity = truncateText(currentActivity, 60);

  return `
    <article class="agent-card ${statusClass}">
      <header class="agent-card-header">
        <div class="agent-card-title-row">
          <h3 class="agent-card-title">${escapeHtml(agent.name || agent.id)}</h3>
          ${statusBadge}
        </div>
        <div class="agent-card-meta">
          ${typeBadge}
          <span class="agent-plan" title="${escapeHtml(agent.plan || "No plan")}">
            ${escapeHtml(truncateText(agent.plan || "No plan", 30))}
          </span>
        </div>
      </header>

      <div class="agent-card-body">
        <!-- Current Activity -->
        <div class="agent-activity">
          <span class="activity-label">Activity:</span>
          <span class="activity-text" title="${escapeHtml(currentActivity)}">
            ${escapeHtml(truncatedActivity)}
          </span>
        </div>

        <!-- Metrics Grid -->
        <div class="agent-metrics">
          <div class="metric-item">
            <span class="metric-label">In</span>
            <span class="metric-value">${tokensIn}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Out</span>
            <span class="metric-value">${tokensOut}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Cost</span>
            <span class="metric-value">${cost}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Duration</span>
            <span class="metric-value">${duration}</span>
          </div>
        </div>

        <!-- Context Usage Bar -->
        <div class="context-usage">
          <div class="context-header">
            <span class="context-label">Context</span>
            <span class="context-text">${contextUsed} / ${contextTotal} (${contextPct})</span>
          </div>
          <div class="progress-bar">
            <div class="progress-fill ${contextClass}" style="width: ${contextPercentage}%"></div>
          </div>
        </div>
      </div>
    </article>
  `;
}

/**
 * Get CSS class for context usage based on percentage
 * @param {number} percentage - Context usage percentage (0-100)
 * @returns {string} CSS class name
 */
function getContextClass(percentage) {
  if (percentage >= 90) return "context-critical";
  if (percentage >= 75) return "context-warning";
  return "context-normal";
}

/**
 * Get status badge HTML
 * @param {string} status - Agent status (active, pending, completed, error)
 * @returns {string} HTML for status badge
 */
function getStatusBadge(status) {
  const badges = {
    active: '<span class="badge badge-success">Active</span>',
    pending: '<span class="badge badge-warning">Pending</span>',
    completed: '<span class="badge badge-info">Completed</span>',
    error: '<span class="badge badge-error">Error</span>',
  };

  return badges[status] || '<span class="badge badge-secondary">Unknown</span>';
}

/**
 * Get type badge HTML
 * @param {string} type - Agent type (explorer, orchestrator, worker, debugger)
 * @returns {string} HTML for type badge
 */
function getTypeBadge(type) {
  const typeIcons = {
    explorer: "🔍",
    orchestrator: "🎯",
    worker: "⚙️",
    debugger: "🐛",
  };

  const icon = typeIcons[type] || "🤖";
  const displayType = type
    ? type.charAt(0).toUpperCase() + type.slice(1)
    : "Unknown";

  return `<span class="agent-type-badge" title="${escapeHtml(displayType)}">${icon} ${escapeHtml(displayType)}</span>`;
}

// Note: `escapeHtml` is provided by `formatters.js` (loaded before this file).

// Enable module imports for testing
if (typeof module !== "undefined" && module.exports) {
  module.exports = { getContextClass, getStatusBadge, getTypeBadge };
}
