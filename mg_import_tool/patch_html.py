#!/usr/bin/env python3
"""
Apply the remaining HTML/JS edits to mg_import.py for the 3 UI features:
1. Browse Tables button in header + modal panel
2. Import History collapsible section
3. JS for both
"""

with open('/home/user/workspace/mg_import_tool/mg_import.py', 'r', encoding='utf-8') as f:
    content = f.read()

# ============================================================
# 1. Add "Browse Tables" button to the header (beside status)
# ============================================================
old_header = '''  <div class="header-status">
    <div class="status-dot" id="headerStatusDot"></div>
    <span id="headerStatusText">Not connected</span>
  </div>
</header>'''

new_header = '''  <div style="display:flex; align-items:center; gap:12px;">
    <button class="btn btn-ghost" onclick="openTableBrowser()" style="font-size:0.75rem; padding:5px 12px; border-color:var(--border-light);">
      <span>&#128196;</span> Browse Tables
    </button>
    <div class="header-status">
      <div class="status-dot" id="headerStatusDot"></div>
      <span id="headerStatusText">Not connected</span>
    </div>
  </div>
</header>'''

assert old_header in content, "ERROR: header-status block not found"
content = content.replace(old_header, new_header, 1)
print("✓ Browse Tables button added to header")


# ============================================================
# 2. Add CSS for new features (table browser modal + history)
#    Insert before the closing </style> tag of the main <style> block
# ============================================================
old_css_close = '''/* ===== SCROLLBAR ===== */
::-webkit-scrollbar { width: 6px; height: 6px; }'''

new_css = '''/* ===== TABLE BROWSER MODAL ===== */
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.7);
  z-index: 1000;
  display: flex; align-items: center; justify-content: center;
  opacity: 0; pointer-events: none;
  transition: opacity 0.2s;
}
.modal-overlay.active { opacity: 1; pointer-events: all; }
.modal-box {
  background: var(--bg-1);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  width: 92vw; max-width: 1100px;
  height: 82vh;
  display: flex; flex-direction: column;
  overflow: hidden;
}
.modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 18px;
  background: var(--bg-2);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.modal-header h2 {
  font-size: 0.9rem; color: var(--text-primary);
  display: flex; align-items: center; gap: 8px;
}
.modal-header h2 span { color: var(--accent); }
.modal-close {
  background: none; border: none; cursor: pointer;
  color: var(--text-muted); font-size: 1.1rem; line-height: 1;
  padding: 4px 8px; border-radius: var(--radius);
  transition: color 0.15s, background 0.15s;
}
.modal-close:hover { color: var(--text-primary); background: var(--bg-3); }
.modal-body {
  flex: 1; display: flex; overflow: hidden;
}
.browser-sidebar {
  width: 240px; flex-shrink: 0;
  background: var(--bg-2);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.browser-sidebar-header {
  padding: 10px 14px 6px;
  font-size: 0.7rem; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.07em;
  color: var(--text-muted);
  display: flex; align-items: center; justify-content: space-between;
  flex-shrink: 0;
}
.browser-table-list {
  flex: 1; overflow-y: auto;
  padding: 4px 0;
}
.browser-table-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 7px 14px;
  cursor: pointer;
  transition: background 0.12s;
  border-left: 3px solid transparent;
  gap: 6px;
}
.browser-table-item:hover { background: var(--bg-3); }
.browser-table-item.active {
  background: var(--accent-dim);
  border-left-color: var(--accent);
}
.browser-table-name {
  font-size: 0.78rem; font-family: var(--font-mono);
  color: var(--text-primary); overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; flex: 1;
}
.browser-table-count {
  font-size: 0.68rem; color: var(--text-muted);
  background: var(--bg-4); padding: 1px 5px;
  border-radius: 9px; flex-shrink: 0;
}
.browser-main {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
}
.browser-toolbar {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px;
  background: var(--bg-2); border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.browser-toolbar .tbl-name {
  font-family: var(--font-mono); font-size: 0.82rem;
  color: var(--accent); font-weight: 600;
}
.browser-toolbar .tbl-hint {
  font-size: 0.72rem; color: var(--text-muted);
}
.browser-grid-wrap {
  flex: 1; overflow: auto;
  padding: 0;
}
.browser-grid {
  border-collapse: collapse; width: 100%;
  font-family: var(--font-mono); font-size: 0.75rem;
  color: var(--text-primary);
}
.browser-grid th {
  background: var(--bg-3);
  padding: 7px 10px; text-align: left;
  font-size: 0.68rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--accent); white-space: nowrap;
  border-bottom: 1px solid var(--border);
  position: sticky; top: 0; z-index: 1;
}
.browser-grid td {
  padding: 5px 10px;
  border-bottom: 1px solid var(--border);
  max-width: 280px; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
  vertical-align: top;
}
.browser-grid tr:hover td { background: var(--bg-2); }
.browser-empty {
  display: flex; align-items: center; justify-content: center;
  height: 100%; color: var(--text-muted); font-size: 0.85rem;
}

/* ===== IMPORT HISTORY ===== */
.history-panel {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  margin-bottom: 4px;
}
.history-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 9px 16px;
  background: var(--bg-2); border-bottom: 1px solid var(--border);
  cursor: pointer; user-select: none;
}
.history-header:hover { background: var(--bg-3); }
.history-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 0.78rem; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--text-secondary);
}
.history-title .icon { color: var(--accent); }
.history-body {
  overflow: hidden;
  transition: max-height 0.25s ease;
}
.history-body.collapsed { display: none; }
.history-table {
  width: 100%; border-collapse: collapse;
  font-size: 0.77rem;
}
.history-table th {
  background: var(--bg-3); padding: 6px 12px;
  text-align: left; font-size: 0.68rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--text-muted); border-bottom: 1px solid var(--border);
}
.history-table td {
  padding: 6px 12px; border-bottom: 1px solid var(--border);
  color: var(--text-primary); vertical-align: top;
}
.history-table td.mono { font-family: var(--font-mono); font-size: 0.73rem; }
.history-table td.ok { color: var(--success); }
.history-table td.fail { color: var(--error); }
.history-empty {
  padding: 16px; text-align: center;
  color: var(--text-muted); font-size: 0.8rem;
}

/* ===== SCROLLBAR ===== */
::-webkit-scrollbar { width: 6px; height: 6px; }'''

assert old_css_close in content, "ERROR: CSS anchor not found"
content = content.replace(old_css_close, new_css, 1)
print("✓ CSS for table browser modal and history added")


# ============================================================
# 3. Add the table browser modal HTML before </body>
# ============================================================
old_before_script = '''<!-- ===== JAVASCRIPT ===== -->
<script>'''

new_modal_html = '''<!-- ===== TABLE BROWSER MODAL ===== -->
<div class="modal-overlay" id="tableBrowserModal">
  <div class="modal-box">
    <div class="modal-header">
      <h2><span>&#128196;</span> Browse Tables — knowledge schema</h2>
      <button class="modal-close" onclick="closeTableBrowser()">&#10005;</button>
    </div>
    <div class="modal-body">
      <!-- Sidebar: table list -->
      <div class="browser-sidebar">
        <div class="browser-sidebar-header">
          <span>Tables</span>
          <button class="btn btn-ghost" style="padding:2px 7px; font-size:0.68rem;" onclick="loadTableList()">&#8635;</button>
        </div>
        <div class="browser-table-list" id="browserTableList">
          <div class="browser-empty" style="padding:20px; font-size:0.78rem;">Click Refresh or open browser</div>
        </div>
      </div>
      <!-- Main: data grid -->
      <div class="browser-main">
        <div class="browser-toolbar" id="browserToolbar">
          <span class="tbl-hint">Select a table on the left to preview rows</span>
        </div>
        <div class="browser-grid-wrap" id="browserGridWrap">
          <div class="browser-empty">No table selected</div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ===== JAVASCRIPT ===== -->
<script>'''

assert old_before_script in content, "ERROR: script tag anchor not found"
content = content.replace(old_before_script, new_modal_html, 1)
print("✓ Table browser modal HTML added")


# ============================================================
# 4. Add Import History panel HTML below the import log
# ============================================================
old_after_log = '''</div><!-- /main-content -->
</div><!-- /app-body -->'''

new_history_html = '''  <!-- ===== IMPORT HISTORY ===== -->
  <div class="history-panel">
    <div class="history-header" onclick="toggleHistory()">
      <div class="history-title">
        <span class="icon">&#128203;</span>
        Import Session History
        <span id="historyCount" style="font-size:0.7rem; color:var(--text-muted); font-weight:400;">(0 sessions)</span>
      </div>
      <div style="display:flex; align-items:center; gap:8px;">
        <button class="btn btn-ghost" style="padding:3px 8px; font-size:0.7rem;" onclick="event.stopPropagation(); clearHistory()">Clear History</button>
        <span class="chevron open" id="historyChevron" style="color:var(--text-muted); font-size:0.65rem;">&#9660;</span>
      </div>
    </div>
    <div class="history-body" id="historyBody">
      <div class="history-empty" id="historyEmpty">No import sessions recorded yet — run an import to begin tracking</div>
      <table class="history-table" id="historyTable" style="display:none;">
        <thead>
          <tr>
            <th>#</th>
            <th>Timestamp (UTC)</th>
            <th>Files</th>
            <th>Rows Imported</th>
            <th>Errors</th>
            <th>Duration</th>
          </tr>
        </thead>
        <tbody id="historyTbody"></tbody>
      </table>
    </div>
  </div>

</div><!-- /main-content -->
</div><!-- /app-body -->'''

assert old_after_log in content, "ERROR: end-of-main-content anchor not found"
content = content.replace(old_after_log, new_history_html, 1)
print("✓ Import history panel HTML added")


# ============================================================
# 5. Add JS for table browser and import history
#    Insert before the // ========== INIT ========== section
# ============================================================
old_init = '''// ========== INIT ==========
document.addEventListener(\'DOMContentLoaded\', () => {'''

new_js = '''// ========== TABLE BROWSER ==========
async function openTableBrowser() {
  document.getElementById('tableBrowserModal').classList.add('active');
  await loadTableList();
}

function closeTableBrowser() {
  document.getElementById('tableBrowserModal').classList.remove('active');
}

// Close modal on overlay click (outside modal-box)
document.addEventListener('click', (e) => {
  const overlay = document.getElementById('tableBrowserModal');
  if (e.target === overlay) closeTableBrowser();
});

async function loadTableList() {
  const listEl = document.getElementById('browserTableList');
  listEl.innerHTML = '<div class="browser-empty" style="padding:20px;">Loading...</div>';
  const p = getConnParams();
  const params = new URLSearchParams({
    host: p.host, port: p.port, database: p.database, user: p.user, password: p.password
  });
  try {
    const res = await fetch('/api/browse-tables?' + params);
    const data = await res.json();
    if (!data.success) {
      listEl.innerHTML = `<div class="browser-empty" style="padding:12px; color:var(--error);">${escHtml(data.error)}</div>`;
      return;
    }
    if (data.tables.length === 0) {
      listEl.innerHTML = '<div class="browser-empty" style="padding:14px;">No tables in knowledge schema</div>';
      return;
    }
    listEl.innerHTML = data.tables.map((t, i) => `
      <div class="browser-table-item" id="bti_${i}" onclick="loadTableRows('${escHtml(t.name)}', ${i})">
        <span class="browser-table-name" title="${escHtml(t.name)}">${escHtml(t.name)}</span>
        <span class="browser-table-count">${t.row_count.toLocaleString()}</span>
      </div>
    `).join('');
  } catch(e) {
    listEl.innerHTML = `<div class="browser-empty" style="padding:12px; color:var(--error);">Request failed: ${escHtml(e.message)}</div>`;
  }
}

async function loadTableRows(tableName, itemIdx) {
  // Highlight active
  document.querySelectorAll('.browser-table-item').forEach((el, i) => {
    el.classList.toggle('active', i === itemIdx);
  });

  const toolbar = document.getElementById('browserToolbar');
  const gridWrap = document.getElementById('browserGridWrap');
  toolbar.innerHTML = `<span class="tbl-name">knowledge.${escHtml(tableName)}</span><span class="tbl-hint">Loading first 25 rows...</span>`;
  gridWrap.innerHTML = '<div class="browser-empty">Loading...</div>';

  const p = getConnParams();
  const params = new URLSearchParams({
    table_name: tableName,
    host: p.host, port: p.port, database: p.database, user: p.user, password: p.password
  });
  try {
    const res = await fetch('/api/browse-rows?' + params);
    const data = await res.json();
    if (!data.success) {
      gridWrap.innerHTML = `<div class="browser-empty" style="color:var(--error);">${escHtml(data.error)}</div>`;
      toolbar.innerHTML = `<span class="tbl-name">knowledge.${escHtml(tableName)}</span><span class="tbl-hint" style="color:var(--error);">Error loading rows</span>`;
      return;
    }
    toolbar.innerHTML = `
      <span class="tbl-name">knowledge.${escHtml(tableName)}</span>
      <span class="tbl-hint">Showing ${data.rows.length} of <strong style="color:var(--text-primary)">25</strong> rows (SELECT * LIMIT 25)</span>
    `;
    if (data.rows.length === 0) {
      gridWrap.innerHTML = '<div class="browser-empty">Table is empty</div>';
      return;
    }
    const thead = '<thead><tr>' + data.columns.map(c => `<th>${escHtml(c)}</th>`).join('') + '</tr></thead>';
    const tbody = '<tbody>' + data.rows.map(row =>
      '<tr>' + row.map(cell => `<td title="${escHtml(cell)}">${escHtml(cell.length > 60 ? cell.slice(0,57)+'...' : cell)}</td>`).join('') + '</tr>'
    ).join('') + '</tbody>';
    gridWrap.innerHTML = `<table class="browser-grid">${thead}${tbody}</table>`;
  } catch(e) {
    gridWrap.innerHTML = `<div class="browser-empty" style="color:var(--error);">Request failed: ${escHtml(e.message)}</div>`;
  }
}

// ========== IMPORT HISTORY ==========
let historyCollapsed = false;

function toggleHistory() {
  historyCollapsed = !historyCollapsed;
  document.getElementById('historyBody').classList.toggle('collapsed', historyCollapsed);
  document.getElementById('historyChevron').classList.toggle('open', !historyCollapsed);
  document.getElementById('historyChevron').innerHTML = historyCollapsed ? '&#9654;' : '&#9660;';
}

async function refreshHistory() {
  try {
    const res = await fetch('/api/import-history');
    const data = await res.json();
    const history = data.history || [];
    const countEl = document.getElementById('historyCount');
    const emptyEl = document.getElementById('historyEmpty');
    const tableEl = document.getElementById('historyTable');
    const tbody = document.getElementById('historyTbody');

    countEl.textContent = `(${history.length} session${history.length !== 1 ? 's' : ''})`;

    if (history.length === 0) {
      emptyEl.style.display = '';
      tableEl.style.display = 'none';
      return;
    }
    emptyEl.style.display = 'none';
    tableEl.style.display = '';
    tbody.innerHTML = history.map((h, i) => {
      const files = Array.isArray(h.filenames) ? h.filenames.join(', ') : (h.filenames || '—');
      const errClass = h.errors > 0 ? 'fail' : 'ok';
      const rowClass = h.rows_imported > 0 ? 'ok' : '';
      return `<tr>
        <td class="mono" style="color:var(--text-muted);">${i + 1}</td>
        <td class="mono">${escHtml(h.timestamp)}</td>
        <td style="font-size:0.72rem; max-width:300px; word-break:break-all;">${escHtml(files)}</td>
        <td class="mono ${rowClass}">${h.rows_imported.toLocaleString()}</td>
        <td class="mono ${errClass}">${h.errors}</td>
        <td class="mono" style="color:var(--text-muted);">${h.duration_s}s</td>
      </tr>`;
    }).join('');
  } catch(e) {
    // silently ignore history refresh errors
  }
}

async function clearHistory() {
  await fetch('/api/clear-history', { method: 'POST' });
  await refreshHistory();
}

// ========== INIT ==========
document.addEventListener(\'DOMContentLoaded\', () => {'''

assert old_init in content, "ERROR: INIT anchor not found"
content = content.replace(old_init, new_js, 1)
print("✓ Table browser + history JS added")


# ============================================================
# 6. Call refreshHistory() after each successful import
#    Hook into processImportResult
# ============================================================
old_process_result = '''  if (success) setHeaderStatus(\'connected\', \'Import complete\');
}'''

new_process_result = '''  if (success) setHeaderStatus(\'connected\', \'Import complete\');
  // Refresh import history panel after each import
  refreshHistory();
}'''

assert old_process_result in content, "ERROR: processImportResult anchor not found"
content = content.replace(old_process_result, new_process_result, 1)
print("✓ refreshHistory() hooked into processImportResult")


# ============================================================
# 7. Footer version bump
# ============================================================
content = content.replace(
    'mg_import v1.0 · Flask + psycopg2',
    'mg_import v2.0 · Flask + psycopg2'
)
print("✓ Version bumped to v2.0")


# ============================================================
# Write back
# ============================================================
with open('/home/user/workspace/mg_import_tool/mg_import.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("\n✅ All patches applied successfully!")
print(f"   Final file size: {len(content):,} characters")
