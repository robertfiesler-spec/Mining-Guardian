/**
 * Log viewer component for instance logs
 * Manages instance tabs and log streaming with auto-scroll
 */

// Global state
let instances = new Map(); // instanceId -> { name, logs: [] }
let activeInstance = null;
let autoScrollEnabled = true;
const MAX_LOG_LINES = 1000; // Maximum lines to keep in memory per instance
const SEARCH_DEBOUNCE_MS = 300;

// Search and filter state
let currentSearchTerm = '';
let currentLevelFilter = 'all';
let searchDebounceTimer = null;

/**
 * Initialize log viewer on page load
 */
document.addEventListener('DOMContentLoaded', () => {
  initializeLogControls();
});

/**
 * Initialize log control event handlers
 */
function initializeLogControls() {
  // Clear logs button
  const clearButton = document.getElementById('clear-logs');
  if (clearButton) {
    clearButton.addEventListener('click', handleClearLogs);
  }

  // Auto-scroll toggle
  const autoScrollCheckbox = document.getElementById('auto-scroll');
  if (autoScrollCheckbox) {
    autoScrollCheckbox.addEventListener('change', (e) => {
      autoScrollEnabled = e.target.checked;
      if (autoScrollEnabled) {
        scrollToBottom();
      }
    });
  }

  // Search input with debounce
  const searchInput = document.getElementById('log-search');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
      searchDebounceTimer = setTimeout(() => {
        currentSearchTerm = e.target.value.trim().toLowerCase();
        renderLogs();
      }, SEARCH_DEBOUNCE_MS);
    });
  }

  // Level filter dropdown
  const levelFilter = document.getElementById('log-level-filter');
  if (levelFilter) {
    levelFilter.addEventListener('change', (e) => {
      currentLevelFilter = e.target.value;
      renderLogs();
    });
  }
}

/**
 * Get health status for an instance based on heartbeat freshness
 * @param {Object} instance - Instance object with health fields
 * @returns {'healthy'|'stale'|'crashed'|'completed'} Health classification
 */
function getInstanceHealthStatus(instance) {
  if (!instance) return 'stale';

  const status = instance.status;
  if (status === 'crashed') return 'crashed';
  if (status === 'completed' || status === 'stopped') return 'completed';

  const heartbeat = instance.lastHeartbeat;
  if (!heartbeat) return 'stale';

  const now = new Date();
  const lastBeat = new Date(heartbeat);
  const diffSeconds = (now - lastBeat) / 1000;

  if (diffSeconds < 30) return 'healthy';
  if (diffSeconds < 120) return 'stale';
  return 'stale';
}

/**
 * Update instance tabs from orchestrator state
 * Creates/updates tabs for each active instance with health indicators
 */
function updateInstanceTabs(orchestratorState) {
  if (!orchestratorState?.instances) return;

  const tabsContainer = document.getElementById('instance-tabs');
  if (!tabsContainer) return;

  const instanceIds = Object.keys(orchestratorState.instances);

  // If no instances, show empty state
  if (instanceIds.length === 0) {
    tabsContainer.innerHTML = '<p class="empty-state">No active instances</p>';
    showEmptyLogState();
    return;
  }

  // Create tabs for each instance
  tabsContainer.innerHTML = '';
  instanceIds.forEach((instanceId) => {
    const instance = orchestratorState.instances[instanceId];

    // Initialize instance in our state if not present
    if (!instances.has(instanceId)) {
      instances.set(instanceId, {
        name: instance.name || instanceId,
        logs: [],
      });
    }

    // Create tab element with health indicators
    const tab = createInstanceTab(instanceId, instance);
    tabsContainer.appendChild(tab);
  });

  // Activate first instance if none is active
  if (!activeInstance && instanceIds.length > 0) {
    switchToInstance(instanceIds[0]);
  }

  // Update health summary
  updateHealthSummary(orchestratorState);
}

/**
 * Create a tab element for an instance with health indicators
 * @param {string} instanceId - Instance identifier
 * @param {Object} instance - Full instance object with health fields
 */
function createInstanceTab(instanceId, instance) {
  const instanceName = instance.name || instanceId;
  const tab = document.createElement('button');
  tab.className = 'instance-tab';
  tab.id = `instance-tab-${instanceId}`;
  tab.setAttribute('role', 'tab');
  tab.setAttribute('aria-controls', 'log-viewer');
  tab.setAttribute('aria-selected', 'false');

  // Health dot
  const healthStatus = getInstanceHealthStatus(instance);
  const healthDot = `<span class="health-dot health-${healthStatus}" title="${healthStatus}"></span>`;

  // Runtime display
  const runtime = instance.runtimeSeconds;
  const runtimeStr = typeof runtime === 'number' && runtime > 0
    ? ` <span class="tab-runtime">${formatDuration(runtime)}</span>`
    : '';

  // Crash count badge
  const crashCount = instance.crashCount;
  const crashBadge = typeof crashCount === 'number' && crashCount > 0
    ? ` <span class="crash-badge" title="${crashCount} crash(es)">${crashCount}</span>`
    : '';

  tab.innerHTML = `${healthDot}${escapeHtml(instanceName)}${runtimeStr}${crashBadge}`;

  // Click handler
  tab.addEventListener('click', () => {
    switchToInstance(instanceId);
  });

  return tab;
}

/**
 * Update the health summary section with aggregate counts
 * @param {Object} orchestratorState - Current orchestrator state
 */
function updateHealthSummary(orchestratorState) {
  if (!orchestratorState?.instances) return;

  let healthy = 0;
  let stale = 0;
  let crashed = 0;
  let totalRuntime = 0;

  for (const instance of Object.values(orchestratorState.instances)) {
    const health = getInstanceHealthStatus(instance);
    if (health === 'healthy') healthy++;
    else if (health === 'stale') stale++;
    else if (health === 'crashed') crashed++;

    if (typeof instance.runtimeSeconds === 'number') {
      totalRuntime += instance.runtimeSeconds;
    }
  }

  const healthyEl = document.getElementById('instances-healthy');
  const staleEl = document.getElementById('instances-stale');
  const crashedEl = document.getElementById('instances-crashed');
  const runtimeEl = document.getElementById('total-runtime');

  if (healthyEl) healthyEl.textContent = healthy;
  if (staleEl) staleEl.textContent = stale;
  if (crashedEl) crashedEl.textContent = crashed;
  if (runtimeEl) runtimeEl.textContent = formatDuration(totalRuntime);
}

/**
 * Switch to a different instance
 */
function switchToInstance(instanceId) {
  if (!instances.has(instanceId)) return;

  // Update active instance
  activeInstance = instanceId;

  // Update tab states
  const allTabs = document.querySelectorAll('.instance-tab');
  allTabs.forEach((tab) => {
    const tabInstanceId = tab.id.replace('instance-tab-', '');
    const isActive = tabInstanceId === instanceId;

    tab.classList.toggle('active', isActive);
    tab.setAttribute('aria-selected', isActive.toString());
  });

  // Render logs for active instance
  renderLogs();
}

/**
 * Append log lines to a specific instance
 * Called from app.js when log messages arrive via WebSocket
 */
function appendLogLines(instanceId, lines) {
  if (!Array.isArray(lines) || lines.length === 0) return;

  // Get or create instance state
  let instance = instances.get(instanceId);
  if (!instance) {
    instance = {
      name: instanceId,
      logs: [],
    };
    instances.set(instanceId, instance);
  }

  // Add new lines to instance logs
  instance.logs.push(...lines);

  // Trim logs if exceeding max lines
  if (instance.logs.length > MAX_LOG_LINES) {
    instance.logs = instance.logs.slice(-MAX_LOG_LINES);
  }

  // Re-render if this is the active instance
  if (instanceId === activeInstance) {
    renderLogs();
  }
}

/**
 * Render logs for the active instance
 */
function renderLogs() {
  const logContent = document.getElementById('log-content');
  if (!logContent) return;

  // If no active instance, show empty state
  if (!activeInstance || !instances.has(activeInstance)) {
    showEmptyLogState();
    return;
  }

  const instance = instances.get(activeInstance);
  const logs = instance.logs;

  // If no logs, show empty state
  if (logs.length === 0) {
    logContent.innerHTML = '<div class="empty-state"><p>No logs yet</p></div>';
    return;
  }

  // Create log lines with search/filter applied
  const fragment = document.createDocumentFragment();
  logs.forEach((line) => {
    const lineElement = createLogLineElement(line);

    // Apply level filter
    if (currentLevelFilter !== 'all') {
      const lineLevel = getLogLineLevel(line);
      if (lineLevel !== currentLevelFilter) {
        lineElement.classList.add('log-line-hidden');
      }
    }

    // Apply search highlighting
    if (currentSearchTerm && !lineElement.classList.contains('log-line-hidden')) {
      const lowerLine = line.toLowerCase();
      if (lowerLine.includes(currentSearchTerm)) {
        highlightSearchTerm(lineElement, line, currentSearchTerm);
      } else {
        lineElement.classList.add('log-line-hidden');
      }
    }

    fragment.appendChild(lineElement);
  });

  // Replace content
  logContent.innerHTML = '';
  logContent.appendChild(fragment);

  // Auto-scroll if enabled
  if (autoScrollEnabled) {
    scrollToBottom();
  }
}

/**
 * Create a log line element with color coding
 */
function createLogLineElement(text) {
  const div = document.createElement('div');
  div.className = 'log-line';

  // Color code based on log level
  const lowerText = text.toLowerCase();
  if (lowerText.includes('error') || lowerText.includes('fail')) {
    div.classList.add('log-error');
  } else if (lowerText.includes('warn')) {
    div.classList.add('log-warning');
  } else if (lowerText.includes('info')) {
    div.classList.add('log-info');
  }

  // Set text content (already stripped of ANSI codes by server)
  div.textContent = text;

  return div;
}

/**
 * Show empty log state
 */
function showEmptyLogState() {
  const logContent = document.getElementById('log-content');
  if (logContent) {
    logContent.innerHTML = '<div class="empty-state"><p>No logs available</p></div>';
  }
}

/**
 * Handle clear logs button click
 */
function handleClearLogs() {
  if (!activeInstance) return;

  const instance = instances.get(activeInstance);
  if (instance) {
    instance.logs = [];
    renderLogs();
  }
}

/**
 * Scroll log viewer to bottom
 */
function scrollToBottom() {
  const logViewer = document.getElementById('log-viewer');
  if (logViewer) {
    logViewer.scrollTop = logViewer.scrollHeight;
  }
}

/**
 * Classify a log line by level
 * @param {string} text - Log line text
 * @returns {'error'|'warning'|'info'|'other'} Level classification
 */
function getLogLineLevel(text) {
  const lower = text.toLowerCase();
  if (lower.includes('error') || lower.includes('fail')) return 'error';
  if (lower.includes('warn')) return 'warning';
  if (lower.includes('info')) return 'info';
  return 'other';
}

/**
 * Highlight search term within a log line element
 * @param {HTMLElement} lineElement - The log line div
 * @param {string} originalText - Original line text
 * @param {string} searchTerm - Lowercase search term
 */
function highlightSearchTerm(lineElement, originalText, searchTerm) {
  const lowerText = originalText.toLowerCase();
  const parts = [];
  let lastIndex = 0;

  let index = lowerText.indexOf(searchTerm, lastIndex);
  while (index !== -1) {
    if (index > lastIndex) {
      parts.push(document.createTextNode(originalText.slice(lastIndex, index)));
    }
    const mark = document.createElement('mark');
    mark.className = 'log-highlight';
    mark.textContent = originalText.slice(index, index + searchTerm.length);
    parts.push(mark);
    lastIndex = index + searchTerm.length;
    index = lowerText.indexOf(searchTerm, lastIndex);
  }

  if (lastIndex < originalText.length) {
    parts.push(document.createTextNode(originalText.slice(lastIndex)));
  }

  lineElement.textContent = '';
  parts.forEach((part) => lineElement.appendChild(part));
}
