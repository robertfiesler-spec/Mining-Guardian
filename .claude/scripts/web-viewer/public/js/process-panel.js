/**
 * Process panel component for displaying instance process cards
 * Shows per-instance status, runtime, heartbeat, PID, and crash info
 */

/**
 * Update process grid with current instances
 * @param {Record<string, Object>} instances - Instance map from orchestrator state
 */
function updateProcessGrid(instances) {
  const processGrid = document.getElementById('process-grid');
  if (!processGrid) return;

  const instanceEntries = instances ? Object.entries(instances) : [];

  if (instanceEntries.length === 0) {
    processGrid.innerHTML = '<div class="empty-state"><p>No active instances</p></div>';
    return;
  }

  const cardsHTML = instanceEntries
    .map(([id, instance]) => createProcessCard(id, instance))
    .join('');
  processGrid.innerHTML = cardsHTML;
}

/**
 * Create HTML for a single process card
 * @param {string} instanceId - Instance identifier
 * @param {Object} instance - Instance object with health fields
 * @returns {string} HTML string for process card
 */
function createProcessCard(instanceId, instance) {
  const name = escapeHtml(instance.name || `Instance ${instanceId}`);
  const branch = escapeHtml(instance.branch || '—');
  const plan = escapeHtml(instance.plan || '—');
  const status = instance.status || 'running';
  const statusBadge = getProcessStatusBadge(status);

  const pid = instance.pid ? `PID ${instance.pid}` : 'No PID';
  const runtime = typeof instance.runtimeSeconds === 'number'
    ? formatDuration(instance.runtimeSeconds)
    : '—';

  const heartbeat = instance.lastHeartbeat
    ? formatRelativeTime(new Date(instance.lastHeartbeat).getTime())
    : '—';

  const exitCodeDisplay = instance.exitCode != null
    ? `<div class="process-detail">
        <span class="process-detail-label">Exit Code</span>
        <span class="process-detail-value">${escapeHtml(formatExitCode(instance.exitCode))}</span>
      </div>`
    : '';

  const crashCount = instance.crashCount || 0;
  const crashBadgeHTML = crashCount > 0
    ? `<span class="process-crash-badge" onclick="toggleCrashPanel('${instanceId}')" title="${crashCount} crash(es)">${crashCount} crash${crashCount !== 1 ? 'es' : ''}</span>`
    : '';

  const healthStatus = getProcessHealthStatus(instance);

  return `
    <article class="process-card process-status-${status}" data-instance-id="${instanceId}">
      <header class="process-card-header">
        <div class="process-card-title-row">
          <span class="health-dot health-${healthStatus}"></span>
          <h3 class="process-card-title">${name}</h3>
          ${statusBadge}
        </div>
        <div class="process-card-meta">
          <code class="process-branch">${branch}</code>
          ${crashBadgeHTML}
        </div>
      </header>

      <div class="process-card-body">
        <div class="process-metrics">
          <div class="process-detail">
            <span class="process-detail-label">${pid}</span>
            <span class="process-detail-value">${runtime}</span>
          </div>
          <div class="process-detail">
            <span class="process-detail-label">Heartbeat</span>
            <span class="process-detail-value">${heartbeat}</span>
          </div>
          ${exitCodeDisplay}
        </div>
      </div>

      ${createCrashDetailPanel(instanceId, instance.crashLog)}
    </article>
  `;
}

/**
 * Get health status classification for a process instance
 * @param {Object} instance - Instance with health fields
 * @returns {'healthy'|'stale'|'crashed'|'completed'} Health classification
 */
function getProcessHealthStatus(instance) {
  if (!instance) return 'stale';
  const status = instance.status;
  if (status === 'crashed') return 'crashed';
  if (status === 'completed' || status === 'stopped') return 'completed';

  const heartbeat = instance.lastHeartbeat;
  if (!heartbeat) return 'stale';

  const diffSeconds = (Date.now() - new Date(heartbeat).getTime()) / 1000;
  if (diffSeconds < 30) return 'healthy';
  if (diffSeconds < 120) return 'stale';
  return 'stale';
}

/**
 * Get status badge HTML for process status
 * @param {string} status - Process status
 * @returns {string} HTML for status badge
 */
function getProcessStatusBadge(status) {
  const badges = {
    running: '<span class="badge badge-success">Running</span>',
    active: '<span class="badge badge-success">Active</span>',
    crashed: '<span class="badge badge-error">Crashed</span>',
    completed: '<span class="badge badge-info">Completed</span>',
    stopped: '<span class="badge badge-neutral">Stopped</span>',
    paused: '<span class="badge badge-warning">Paused</span>',
  };
  return badges[status] || '<span class="badge badge-neutral">Unknown</span>';
}

/**
 * Create crash detail panel HTML
 * @param {string} instanceId - Instance identifier
 * @param {Array} crashLog - Array of crash events
 * @returns {string} HTML string for crash panel
 */
function createCrashDetailPanel(instanceId, crashLog) {
  if (!Array.isArray(crashLog) || crashLog.length === 0) return '';

  const eventsHTML = crashLog.map((event) => {
    const timestamp = event.timestamp
      ? formatRelativeTime(new Date(event.timestamp).getTime())
      : '—';
    const exitCode = formatExitCode(event.exitCode != null ? event.exitCode : event.exit_code);
    const pid = event.pid || '—';
    const runtime = typeof event.runtimeSeconds === 'number'
      ? formatDuration(event.runtimeSeconds)
      : typeof event.runtime_seconds === 'number'
        ? formatDuration(event.runtime_seconds)
        : '—';
    const message = escapeHtml(event.message || '');

    return `
      <div class="crash-event">
        <div class="crash-event-header">
          <span class="badge badge-error">Crash</span>
          <span>${escapeHtml(timestamp)}</span>
        </div>
        <div class="crash-event-details">
          <span>Exit: ${escapeHtml(exitCode)}</span>
          <span>PID: ${pid}</span>
          <span>Runtime: ${escapeHtml(runtime)}</span>
        </div>
        ${message ? `<div class="crash-event-message">${message}</div>` : ''}
      </div>
    `;
  }).join('');

  return `
    <div class="crash-panel hidden" id="crash-panel-${instanceId}">
      <h4 class="crash-panel-title">Crash History</h4>
      ${eventsHTML}
    </div>
  `;
}

/**
 * Toggle crash detail panel visibility
 * @param {string} instanceId - Instance identifier
 */
function toggleCrashPanel(instanceId) {
  const panel = document.getElementById(`crash-panel-${instanceId}`);
  if (panel) {
    panel.classList.toggle('hidden');
  }
}

// Enable module imports for testing
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { getProcessHealthStatus, getProcessStatusBadge, createCrashDetailPanel };
}
