/**
 * Dashboard component for plan progress and story checklist
 * Displays current plan status, progress bar, and story completion
 */

/**
 * Update plan progress section with current session state
 * @param {Object} sessionState - Session state from multitask-session.json
 */
function updatePlanProgress(sessionState) {
  if (!sessionState) return;

  const planInfo = sessionState.plan;
  const progressInfo = sessionState.progress;

  // Update plan header
  updatePlanHeader(planInfo, sessionState.status);

  // Update progress bar
  updateProgressBar(progressInfo);

  // Update current story display
  updateCurrentStory(progressInfo, sessionState.activity_log);
}

/**
 * Update plan header with plan name and branch
 * @param {Object} planInfo - Plan information object
 * @param {string} status - Session status (running, paused, completed, failed)
 */
function updatePlanHeader(planInfo, status) {
  const planName = document.getElementById("plan-name");
  const planBranch = document.getElementById("plan-branch");

  if (planName && planInfo) {
    planName.textContent = planInfo.name || "Unnamed Plan";
  }

  if (planBranch && planInfo) {
    const statusBadge = getSessionStatusBadge(status);
    planBranch.innerHTML = `
      Branch: <code>${escapeHtml(planInfo.branch || "unknown")}</code>
      ${statusBadge}
    `;
  }
}

/**
 * Update progress bar and text
 * @param {Object} progressInfo - Progress information object
 */
function updateProgressBar(progressInfo) {
  const progressFill = document.getElementById("plan-progress-fill");
  const progressText = document.getElementById("plan-progress-text");

  if (!progressInfo) return;

  const completed = progressInfo.completed || 0;
  const total = progressInfo.total_stories || 0;
  const percentage = total > 0 ? (completed / total) * 100 : 0;

  if (progressFill) {
    progressFill.style.width = `${percentage}%`;

    // Add color class based on progress
    progressFill.className = "progress-fill";
    if (percentage === 100) {
      progressFill.classList.add("progress-complete");
    } else if (percentage >= 50) {
      progressFill.classList.add("progress-good");
    }
  }

  if (progressText) {
    progressText.textContent = `${completed} / ${total} stories`;
  }
}

/**
 * Update current story display
 * @param {Object} progressInfo - Progress information object
 * @param {Array} activityLog - Activity log entries
 */
function updateCurrentStory(progressInfo, activityLog) {
  const currentStoryContainer = document.getElementById("current-story");
  if (!currentStoryContainer) return;

  const currentStoryId = progressInfo?.current_story;
  const iteration = progressInfo?.current_iteration || 1;

  if (!currentStoryId) {
    currentStoryContainer.innerHTML =
      '<p class="text-muted">No active story</p>';
    return;
  }

  // Find the most recent activity for current story
  const recentActivity = activityLog
    ?.filter((entry) => entry.story === currentStoryId)
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))[0];

  const activityText = recentActivity?.message || "In progress...";
  const timestamp = recentActivity?.timestamp
    ? formatRelativeTime(recentActivity.timestamp)
    : "";

  currentStoryContainer.innerHTML = `
    <div class="current-story-content">
      <div class="story-header">
        <strong>Current Story:</strong>
        <code class="story-id">${escapeHtml(currentStoryId)}</code>
        <span class="iteration-badge">Iteration ${iteration}</span>
      </div>
      <p class="story-activity">${escapeHtml(activityText)}</p>
      ${timestamp ? `<p class="story-timestamp">${timestamp}</p>` : ""}
    </div>
  `;
}

/**
 * Update story checklist from plan definition
 * @param {Object} planDefinition - Plan definition with stories array
 */
function updateStoryChecklist(planDefinition) {
  const storyList = document.getElementById("story-list");
  if (!storyList || !planDefinition) return;

  const stories = planDefinition.stories || [];

  if (stories.length === 0) {
    storyList.innerHTML = '<li class="empty-state">No stories defined</li>';
    return;
  }

  // Group stories by type for better organization
  const groupedStories = groupStoriesByType(stories);

  // Build HTML for each type group
  const storyHTML = Object.entries(groupedStories)
    .map(([type, typeStories]) => {
      const storiesHTML = typeStories
        .map((story) => createStoryListItem(story))
        .join("");

      return `
        <li class="story-type-group">
          <div class="story-type-header">${escapeHtml(type)}</div>
          <ul class="story-type-list">
            ${storiesHTML}
          </ul>
        </li>
      `;
    })
    .join("");

  storyList.innerHTML = storyHTML;
}

/**
 * Group stories by type
 * @param {Array} stories - Array of story objects
 * @returns {Object} Stories grouped by type
 */
function groupStoriesByType(stories) {
  const grouped = {};

  stories.forEach((story) => {
    const type = story.type || "Other";
    if (!grouped[type]) {
      grouped[type] = [];
    }
    grouped[type].push(story);
  });

  // Sort each group by priority
  Object.keys(grouped).forEach((type) => {
    grouped[type].sort((a, b) => a.priority - b.priority);
  });

  return grouped;
}

/**
 * Create HTML for a single story list item
 * @param {Object} story - Story object
 * @returns {string} HTML string for story item
 */
function createStoryListItem(story) {
  const statusIcon = story.passes ? "✓" : "○";
  const statusClass = story.passes ? "story-completed" : "story-pending";
  const priorityBadge = `<span class="priority-badge priority-${story.priority}">${story.priority}</span>`;

  return `
    <li class="story-item ${statusClass}">
      <div class="story-checkbox">
        <span class="story-status-icon">${statusIcon}</span>
      </div>
      <div class="story-content">
        <div class="story-title-row">
          <code class="story-id">${escapeHtml(story.id)}</code>
          ${priorityBadge}
          <span class="story-title">${escapeHtml(story.title)}</span>
        </div>
        <div class="story-acceptance">${escapeHtml(story.acceptance)}</div>
        ${
          story.depends && story.depends.length > 0
            ? `
          <div class="story-depends">
            Depends on: ${story.depends.map((id) => `<code>${escapeHtml(id)}</code>`).join(", ")}
          </div>
        `
            : ""
        }
      </div>
    </li>
  `;
}

/**
 * Get session status badge HTML
 * @param {string} status - Session status
 * @returns {string} HTML for status badge
 */
function getSessionStatusBadge(status) {
  const badges = {
    running: '<span class="badge badge-success">Running</span>',
    paused: '<span class="badge badge-warning">Paused</span>',
    completed: '<span class="badge badge-info">Completed</span>',
    failed: '<span class="badge badge-error">Failed</span>',
  };

  return badges[status] || "";
}

/**
 * Note: `escapeHtml` is provided by `formatters.js` (loaded before this file).
 */

/**
 * Update display for multiple concurrent plans (multitask mode)
 * @param {Object} plans - Plans keyed by name
 */
function updateMultiPlanDisplay(plans) {
  const planContainer = document.getElementById("plan-container");
  if (!planContainer) return;

  const planNames = Object.keys(plans);
  if (planNames.length === 0) return;

  // Single plan: delegate to existing display
  if (planNames.length === 1) {
    const plan = plans[planNames[0]];
    updateStoryChecklist(plan);
    return;
  }

  // Multi-plan mode: render a compact card per plan
  const html = planNames
    .map((name) => {
      const plan = plans[name];
      const stories = plan.stories || [];
      const completed = stories.filter((s) => s.passes).length;
      const total = stories.length;
      const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

      const progressClass =
        pct === 100
          ? "progress-complete"
          : pct >= 50
            ? "progress-good"
            : "";

      const statusBadge = plan.status
        ? `<span class="badge badge-${plan.status === "completed" ? "info" : "success"}">${escapeHtml(plan.status)}</span>`
        : "";

      const storyChips = stories
        .map(
          (s) =>
            `<span class="story-chip ${s.passes ? "story-chip-done" : "story-chip-pending"}" title="${escapeHtml(s.title)}">` +
            `${s.passes ? "&#10003;" : "&#9675;"} ${escapeHtml(s.id)}</span>`,
        )
        .join("");

      return `
      <div class="multi-plan-card">
        <div class="multi-plan-header">
          <h4 class="multi-plan-name">${escapeHtml(plan.feature || name)}</h4>
          ${statusBadge}
        </div>
        <div class="multi-plan-branch">
          Branch: <code>${escapeHtml(plan.branch || "unknown")}</code>
        </div>
        <div class="plan-progress-bar-container">
          <div class="progress-bar">
            <div class="progress-fill ${progressClass}" style="width: ${pct}%"></div>
          </div>
          <span class="progress-text">${completed} / ${total} stories (${pct}%)</span>
        </div>
        <div class="multi-plan-stories">${storyChips}</div>
      </div>
    `;
    })
    .join("");

  planContainer.innerHTML = html;
}

// Enable module imports for testing
if (typeof module !== "undefined" && module.exports) {
  // Node-compatible escapeHtml (browser version uses DOM via formatters.js)
  const _escapeHtml = (str) => {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  };
  module.exports = {
    groupStoriesByType,
    getSessionStatusBadge,
    updateMultiPlanDisplay,
    escapeHtml: _escapeHtml,
  };
}
