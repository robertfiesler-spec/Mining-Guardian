#!/usr/bin/env node
'use strict';

const path = require('path');
const { execSync } = require('child_process');
const {
  findProjectRoot,
  getGitBranch,
  writeJsonSafe,
  writeFileSafe,
  readJsonSafe,
  ensureDir,
  generateSessionId,
  getGitDiffSummary,
  getLastEditedFiles,
  getRecentCommits,
  getActivePlanProgress,
  pruneDirectory,
} = require('./lib/utils');

/**
 * SessionEnd hook: Save session state for continuity across sessions.
 *
 * Enhanced for memory persistence (STORY-8):
 * - Writes current state to .ai/memory/session-state.json with:
 *   branch, last_files, uncommitted, active_task, todos, timestamp, session_id
 * - Ensures .ai/memory/ directory exists (mkdirp)
 * - Preserves accumulated tasks from previous session state
 * - Reads active_task from CLAUDE_ACTIVE_TASK env var or existing state
 *
 * Memory file format (session-state.json):
 * {
 *   "branch": "feat/my-feature",
 *   "last_files": ["src/app.tsx", "src/utils.ts"],
 *   "uncommitted": "3 files changed, 45 insertions, 12 deletions",
 *   "active_task": "Implementing user authentication flow",
 *   "todos": ["Add error handling", "Write integration tests"],
 *   "timestamp": "2026-02-13T12:00:00Z",
 *   "session_id": "abc123"
 * }
 *
 * Session archival: Also writes timestamped archives to .ai/memory/sessions/
 * with enriched data (commits, plan progress, duration). Keeps last 10 sessions.
 * Writes .ai/memory/session-summary.md for Claude Code memory bridging.
 */
async function main() {
  try {
    const projectRoot = findProjectRoot() || process.cwd();
    const memoryDir = path.join(projectRoot, '.ai', 'memory');

    // Ensure memory directory exists
    ensureDir(memoryDir);

    const sessionPath = path.join(memoryDir, 'session-state.json');

    // Load existing session to preserve accumulated data
    const existing = readJsonSafe(sessionPath) || {};

    // Gather current git state
    const branch = getGitBranch();

    // Get last 5 files edited (staged + unstaged changes)
    const lastFiles = getLastEditedFiles(projectRoot, 5);

    // Get uncommitted changes summary (e.g., "3 files changed, 45 insertions, 12 deletions")
    const uncommitted = getGitDiffSummary(projectRoot);

    // Determine active task:
    // Priority: env var > existing session state > null
    const activeTask = process.env.CLAUDE_ACTIVE_TASK
      || existing.active_task
      || null;

    // Gather pending TODOs:
    // Priority: env var (comma-separated) > existing session todos > empty
    let todos = [];
    if (process.env.CLAUDE_TODOS) {
      todos = process.env.CLAUDE_TODOS.split(',').map((t) => t.trim()).filter(Boolean);
    } else if (Array.isArray(existing.todos) && existing.todos.length > 0) {
      todos = existing.todos;
    }

    // Also check todos.json for additional pending items
    const todosPath = path.join(memoryDir, 'todos.json');
    const todosFile = readJsonSafe(todosPath);
    if (todosFile && Array.isArray(todosFile.items)) {
      const pendingFromFile = todosFile.items
        .filter((t) => t.status === 'pending')
        .map((t) => t.text || t.content || 'untitled');
      if (pendingFromFile.length > 0 && todos.length === 0) {
        todos = pendingFromFile;
      }
    }

    // Generate or preserve session ID
    const sessionId = existing.session_id || generateSessionId();

    const sessionState = {
      branch: branch || null,
      last_files: lastFiles,
      uncommitted: uncommitted || null,
      active_task: activeTask,
      todos,
      timestamp: new Date().toISOString(),
      session_id: sessionId,
    };

    const success = writeJsonSafe(sessionPath, sessionState);
    if (success) {
      const fileCount = lastFiles.length;
      const todoCount = todos.length;
      const parts = [
        `branch=${branch || 'none'}`,
        `files=${fileCount}`,
        `todos=${todoCount}`,
      ];
      if (activeTask) {
        parts.push(`task="${activeTask.slice(0, 40)}${activeTask.length > 40 ? '...' : ''}"`);
      }
      process.stdout.write(
        `[session-end] State saved: ${parts.join(', ')}\n`
      );
    }

    // --- Session Archive ---
    // Append to timestamped archive so /catchup can show session history
    const sessionsDir = path.join(memoryDir, 'sessions');
    ensureDir(sessionsDir);

    // Gather enriched data for archive
    const prevTimestamp = existing.timestamp || null;
    const commitsSince = getRecentCommits(projectRoot, prevTimestamp, 20);
    const planProgress = getActivePlanProgress(projectRoot);
    const durationMs = prevTimestamp
      ? Date.now() - new Date(prevTimestamp).getTime()
      : null;

    const archiveEntry = {
      ...sessionState,
      commits_made: commitsSince,
      task_progress: planProgress,
      session_duration_estimate_ms: durationMs,
    };

    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const archivePath = path.join(sessionsDir, `${ts}.json`);
    writeJsonSafe(archivePath, archiveEntry);

    // Keep only the 10 most recent archives
    pruneDirectory(sessionsDir, 10, '.json');

    // --- Session Summary (for memory bridging) ---
    const commitCount = commitsSince.length;
    const commitList = commitsSince.slice(0, 5).map((c) => `  - ${c}`).join('\n');
    const fileList = lastFiles.map((f) => `  - ${f}`).join('\n');
    const planLine = planProgress
      ? `**Plan**: ${planProgress.planName} (${planProgress.completed}/${planProgress.total} complete)`
      : '**Plan**: None active';
    const durationStr = durationMs
      ? `~${Math.round(durationMs / 60000)} minutes`
      : 'unknown';

    const summary = [
      `# Session Summary: ${branch || 'detached'}`,
      `**Date**: ${sessionState.timestamp}`,
      `**Branch**: ${branch || 'none'}`,
      `**Duration**: ${durationStr}`,
      `**Commits**: ${commitCount}${commitCount > 0 ? '\n' + commitList : ''}`,
      `**Files touched**:${lastFiles.length > 0 ? '\n' + fileList : ' none'}`,
      planLine,
      activeTask ? `**Active task**: ${activeTask}` : '',
      todoCount > 0 ? `**Pending**: ${todoCount} items` : '',
    ].filter(Boolean).join('\n');

    writeFileSafe(path.join(memoryDir, 'session-summary.md'), summary);

    process.stdout.write(
      `[session-end] Archive saved, ${commitCount} commits recorded\n`
    );
  } catch (err) {
    // Fail gracefully - do not block session termination
    process.stderr.write(`Warning [session-end]: ${err.message}\n`);
  }
}

main();
