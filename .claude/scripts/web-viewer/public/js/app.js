/**
 * Main application entry point
 * Initializes WebSocket connection and coordinates UI updates
 */

// Global state
let wsManager = null;
let currentState = {
  orchestrator: null,
  session: null,
  plan: null,
  plans: {},
};

/**
 * Initialize application on page load
 */
document.addEventListener('DOMContentLoaded', () => {
  console.log('[App] Initializing...');

  // Show loading overlay
  showLoading();

  // Initialize WebSocket connection
  initializeWebSocket();

  // Set up UI event handlers
  initializeUIHandlers();
});

/**
 * Initialize WebSocket connection
 */
function initializeWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  const wsUrl = `${protocol}//${host}/ws`;

  console.log('[App] Connecting to WebSocket:', wsUrl);
  wsManager = new WebSocketManager(wsUrl);

  // Connection events
  wsManager.on('connected', handleConnected);
  wsManager.on('disconnected', handleDisconnected);
  wsManager.on('reconnecting', handleReconnecting);
  wsManager.on('failed', handleConnectionFailed);
  wsManager.on('error', handleError);

  // Message events
  wsManager.on('message', handleMessage);

  // Start connection
  wsManager.connect();
}

/**
 * Handle successful connection
 */
function handleConnected() {
  console.log('[App] WebSocket connected');
  updateConnectionStatus('connected', 'Connected');

  // Clear any active countdown intervals
  const loadingOverlay = document.getElementById('loading-overlay');
  if (loadingOverlay && loadingOverlay.dataset.countdownInterval) {
    clearInterval(parseInt(loadingOverlay.dataset.countdownInterval, 10));
    delete loadingOverlay.dataset.countdownInterval;
  }

  hideLoading();
}

/**
 * Handle disconnection
 */
function handleDisconnected() {
  console.log('[App] WebSocket disconnected');
  updateConnectionStatus('disconnected', 'Disconnected');

  // Show loading overlay if this is an unexpected disconnection
  // (intentional closes are handled by the wsManager)
  if (wsManager && !wsManager.isIntentionalClose) {
    showLoading('Connection lost...');
  }
}

/**
 * Handle reconnection attempt
 */
function handleReconnecting(data) {
  console.log('[App] Reconnecting...', data);
  updateConnectionStatus(
    'reconnecting',
    `Reconnecting (${data.attempt}/${wsManager.maxReconnectAttempts})`,
  );

  // Show reconnection notification
  showReconnectingState(data.attempt, wsManager.maxReconnectAttempts, data.delay);
}

/**
 * Handle connection failure
 */
function handleConnectionFailed(message) {
  console.error('[App] Connection failed:', message);
  updateConnectionStatus('error', 'Connection Failed');
  showError(
    message || 'Failed to connect to server after multiple attempts',
    true, // Show retry button
  );
}

/**
 * Handle WebSocket error
 */
function handleError(error) {
  console.error('[App] WebSocket error:', error);
}

/**
 * Handle incoming WebSocket message
 */
function handleMessage(message) {
  console.log('[App] Handling message:', message.type);

  // Show brief loading indicator for state updates
  if (message.type === 'state_update') {
    showDataLoadingIndicator();
  }

  switch (message.type) {
    case 'state_update':
      handleStateUpdate(message);
      break;

    case 'log':
      handleLogMessage(message);
      break;

    case 'error':
      handleErrorMessage(message);
      break;

    default:
      console.warn('[App] Unknown message type:', message.type);
  }

  // Update last update timestamp
  updateLastUpdateTime();
}

/**
 * Handle state update message
 */
function handleStateUpdate(message) {
  // Update orchestrator state
  if (message.orchestrator) {
    currentState.orchestrator = message.orchestrator;
    updateCostMetrics(message.orchestrator.costs);
    updateAgentSummary(message.orchestrator.agents);

    // Update agent grid if dashboard module is loaded
    if (typeof updateAgentGrid === 'function') {
      updateAgentGrid(message.orchestrator.agents.agents);
    }

    // Update process cards if process panel module is loaded
    if (typeof updateProcessGrid === 'function') {
      updateProcessGrid(message.orchestrator.instances);
    }

    // Update instance tabs if log viewer module is loaded
    if (typeof updateInstanceTabs === 'function') {
      updateInstanceTabs(message.orchestrator);
    }
  }

  // Update session state
  if (message.session) {
    currentState.session = message.session;

    // Update plan progress if dashboard module is loaded
    if (typeof updatePlanProgress === 'function') {
      updatePlanProgress(message.session);
    }
  }

  // Update plan definition
  if (message.plan) {
    currentState.plan = message.plan;

    // Update story checklist if dashboard module is loaded
    if (typeof updateStoryChecklist === 'function') {
      updateStoryChecklist(message.plan);
    }
  }

  // Update all plans (multitask mode)
  if (message.plans) {
    currentState.plans = message.plans;

    if (typeof updateMultiPlanDisplay === 'function') {
      updateMultiPlanDisplay(message.plans);
    }
  }
}

/**
 * Handle log message
 */
function handleLogMessage(message) {
  // Forward to log viewer if module is loaded
  if (typeof appendLogLines === 'function') {
    appendLogLines(message.instanceId, message.lines);
  }
}

/**
 * Handle error message
 */
function handleErrorMessage(message) {
  console.error('[App] Server error:', message.message);
  showError(message.message);
}

/**
 * Update connection status indicator
 */
function updateConnectionStatus(status, text) {
  const statusIndicator = document.getElementById('status-indicator');
  const statusText = document.getElementById('status-text');

  if (statusIndicator && statusText) {
    // Remove all status classes
    statusIndicator.className = 'status-indicator';

    // Add appropriate status class
    statusIndicator.classList.add(`status-${status}`);
    statusText.textContent = text;
  }
}

/**
 * Update cost metrics
 */
function updateCostMetrics(costs) {
  if (!costs) return;

  const formatCost = (cost) => `$${cost.toFixed(2)}`;

  const costToday = document.getElementById('cost-today');
  const costSession = document.getElementById('cost-session');
  const cost7Day = document.getElementById('cost-7day');
  const cost30Day = document.getElementById('cost-30day');

  if (costToday) costToday.textContent = formatCost(costs.today);
  if (costSession) costSession.textContent = formatCost(costs.sessions);
  if (cost7Day) cost7Day.textContent = formatCost(costs.sevenDay);
  if (cost30Day) cost30Day.textContent = formatCost(costs.thirtyDay);
}

/**
 * Update agent summary statistics
 */
function updateAgentSummary(agentSummary) {
  if (!agentSummary) return;

  const activeCount = document.getElementById('agents-active');
  const pendingCount = document.getElementById('agents-pending');
  const completedCount = document.getElementById('agents-completed');
  const errorCount = document.getElementById('agents-error');

  if (activeCount) activeCount.textContent = agentSummary.activeCount || 0;
  if (pendingCount) pendingCount.textContent = agentSummary.pendingCount || 0;
  if (completedCount) completedCount.textContent = agentSummary.completedCount || 0;
  if (errorCount) errorCount.textContent = agentSummary.errorCount || 0;
}

/**
 * Update last update timestamp
 */
function updateLastUpdateTime() {
  const lastUpdate = document.getElementById('last-update');
  if (lastUpdate) {
    const now = new Date();
    lastUpdate.textContent = now.toLocaleTimeString();
    lastUpdate.setAttribute('datetime', now.toISOString());
  }
}

/**
 * Show brief data loading indicator
 */
function showDataLoadingIndicator() {
  const statusText = document.getElementById('status-text');
  if (statusText && wsManager && wsManager.getState() === 'connected') {
    const originalText = statusText.textContent;
    statusText.textContent = 'Updating...';

    // Reset to original text after brief delay
    setTimeout(() => {
      statusText.textContent = originalText;
    }, 500);
  }
}

/**
 * Show loading overlay
 */
function showLoading(message = 'Connecting to server...') {
  const loadingOverlay = document.getElementById('loading-overlay');
  const loadingText = document.querySelector('.loading-text');

  if (loadingOverlay) {
    loadingOverlay.classList.remove('hidden');
    if (loadingText) {
      loadingText.textContent = message;
    }
  }
}

/**
 * Hide loading overlay
 */
function hideLoading() {
  const loadingOverlay = document.getElementById('loading-overlay');
  if (loadingOverlay) {
    loadingOverlay.classList.add('hidden');
  }
}

/**
 * Show reconnecting state with countdown
 */
function showReconnectingState(attempt, maxAttempts, delay) {
  const loadingOverlay = document.getElementById('loading-overlay');
  const loadingText = document.querySelector('.loading-text');

  if (loadingOverlay && loadingText) {
    loadingOverlay.classList.remove('hidden');

    // Show initial message
    const seconds = Math.ceil(delay / 1000);
    loadingText.textContent = `Connection lost. Retrying in ${seconds}s (${attempt}/${maxAttempts})`;

    // Update countdown every second
    let remainingSeconds = seconds;
    const countdownInterval = setInterval(() => {
      remainingSeconds--;
      if (remainingSeconds > 0) {
        loadingText.textContent = `Connection lost. Retrying in ${remainingSeconds}s (${attempt}/${maxAttempts})`;
      } else {
        loadingText.textContent = `Reconnecting... (${attempt}/${maxAttempts})`;
        clearInterval(countdownInterval);
      }
    }, 1000);

    // Store interval ID for cleanup if connection succeeds early
    loadingOverlay.dataset.countdownInterval = countdownInterval;
  }
}

/**
 * Show error modal
 */
function showError(message, showRetry = false) {
  const errorModal = document.getElementById('error-modal');
  const errorMessage = document.getElementById('error-message');
  const errorRetry = document.getElementById('error-retry');

  if (errorModal && errorMessage) {
    errorMessage.textContent = message;
    errorModal.classList.remove('hidden');

    // Show/hide retry button
    if (errorRetry) {
      if (showRetry) {
        errorRetry.classList.remove('hidden');
      } else {
        errorRetry.classList.add('hidden');
      }
    }
  }
}

/**
 * Hide error modal
 */
function hideError() {
  const errorModal = document.getElementById('error-modal');
  if (errorModal) {
    errorModal.classList.add('hidden');
  }
}

/**
 * Initialize UI event handlers
 */
function initializeUIHandlers() {
  // Error modal dismiss button
  const errorDismiss = document.getElementById('error-dismiss');
  if (errorDismiss) {
    errorDismiss.addEventListener('click', hideError);
  }

  // Error modal retry button
  const errorRetry = document.getElementById('error-retry');
  if (errorRetry) {
    errorRetry.addEventListener('click', handleRetryConnection);
  }

  // Close error modal on escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      hideError();
    }
  });

  // Theme toggle
  initializeThemeToggle();
}

/**
 * Initialize theme toggle button
 * Reads saved preference from localStorage, applies it, and wires button click
 */
function initializeThemeToggle() {
  const THEME_KEY = 'web-viewer-theme';
  const toggle = document.getElementById('theme-toggle');
  if (!toggle) return;

  // Apply saved theme on load
  const savedTheme = localStorage.getItem(THEME_KEY);
  if (savedTheme === 'neon') {
    document.documentElement.setAttribute('data-theme', 'neon');
    toggle.textContent = '🌙';
  }

  toggle.addEventListener('click', () => {
    const isNeon = document.documentElement.getAttribute('data-theme') === 'neon';
    if (isNeon) {
      document.documentElement.removeAttribute('data-theme');
      localStorage.removeItem(THEME_KEY);
      toggle.textContent = '⚡';
    } else {
      document.documentElement.setAttribute('data-theme', 'neon');
      localStorage.setItem(THEME_KEY, 'neon');
      toggle.textContent = '🌙';
    }
  });
}

/**
 * Handle retry connection button click
 */
function handleRetryConnection() {
  console.log('[App] Retrying connection...');
  hideError();
  showLoading('Reconnecting...');

  // Reset reconnection state and try again
  if (wsManager) {
    wsManager.reconnectAttempts = 0;
    wsManager.isIntentionalClose = false;
    wsManager.connect();
  }
}

/**
 * Clean up on page unload
 */
window.addEventListener('beforeunload', () => {
  if (wsManager) {
    wsManager.close();
  }
});
