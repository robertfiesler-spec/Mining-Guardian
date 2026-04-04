#!/usr/bin/env node
'use strict';

const path = require('path');
const { execSync } = require('child_process');
const {
  findProjectRoot,
  getGitBranch,
  readJsonSafe,
  writeJsonSafe,
  ensureDir,
  countLearnings,
  getLastEditedFiles,
} = require('./lib/utils');

/**
 * PreCompact hook: Save current state before context compaction.
 *
 * This is the MOST CRITICAL hook -- without it, long sessions lose context
 * when the conversation is compacted. It saves the 3 most important items:
 *   1. current_task: what is being worked on
 *   2. key_decisions: important decisions made this session
 *   3. file_dependencies: files currently being modified
 *
 * Enhanced for memory persistence (STORY-8):
 * - Saves structured snapshot to .ai/memory/pre-compact-snapshot.json
 * - Includes branch, timestamp, learning count
 * - Reads task context from environment variables and session state
 * - Combines staged + unstaged + recently edited files
 *
 * Memory file format (pre-compact-snapshot.json):
 * {
 *   "current_task": "Implementing OAuth2 login",
 *   "key_decisions": [
 *     "Using next-auth for session management",
 *     "JWT tokens with 24h expiry"
 *   ],
 *   "file_dependencies": ["src/auth/provider.tsx", "src/auth/callback.ts"],
 *   "branch": "feat/oauth2",
 *   "learnings_count": 3,
 *   "timestamp": "2026-02-13T12:00:00Z"
 * }
 *
 * TODO: Implement 30-day archival cleanup for old snapshots
 */
async function main() {
  try {
    const projectRoot = findProjectRoot() || process.cwd();
    const memoryDir = path.join(projectRoot, '.ai', 'memory');

    // Ensure memory directory exists
    ensureDir(memoryDir);

    const snapshotPath = path.join(memoryDir, 'pre-compact-snapshot.json');

    // --- 1. Current Task ---
    // Priority: env var > session state active_task > plan file > null
    let currentTask = process.env.CLAUDE_ACTIVE_TASK || null;

    if (!currentTask) {
      const sessionPath = path.join(memoryDir, 'session-state.json');
      const session = readJsonSafe(sessionPath) || {};
      currentTask = session.active_task || null;
    }

    // Try to infer from plan files if no explicit task
    if (!currentTask) {
      currentTask = inferCurrentTaskFromPlans(projectRoot);
    }

    // --- 2. Key Decisions ---
    // Read from env var (pipe-separated) or existing snapshot
    let keyDecisions = [];
    if (process.env.CLAUDE_KEY_DECISIONS) {
      keyDecisions = process.env.CLAUDE_KEY_DECISIONS
        .split('|')
        .map((d) => d.trim())
        .filter(Boolean);
    } else {
      // Preserve decisions from existing snapshot if available
      const existingSnapshot = readJsonSafe(snapshotPath);
      if (existingSnapshot && Array.isArray(existingSnapshot.key_decisions)) {
        keyDecisions = existingSnapshot.key_decisions;
      }
    }

    // --- 3. File Dependencies ---
    // Combine: staged files + unstaged modified files + recently edited from session
    const fileDependencies = collectFileDependencies(projectRoot, memoryDir);

    // --- Additional context ---
    const branch = getGitBranch();
    const learningsCount = countLearnings(projectRoot);

    const snapshot = {
      current_task: currentTask,
      key_decisions: keyDecisions,
      file_dependencies: fileDependencies,
      branch: branch || null,
      learnings_count: learningsCount,
      timestamp: new Date().toISOString(),
    };

    const success = writeJsonSafe(snapshotPath, snapshot);
    if (success) {
      const parts = [];
      if (currentTask) {
        parts.push(`task="${currentTask.slice(0, 50)}${currentTask.length > 50 ? '...' : ''}"`);
      }
      parts.push(`decisions=${keyDecisions.length}`);
      parts.push(`files=${fileDependencies.length}`);
      parts.push(`learnings=${learningsCount}`);
      process.stdout.write(
        `[pre-compact] Context snapshot saved: ${parts.join(', ')}\n`
      );
    }
  } catch (err) {
    // Fail gracefully - compaction should proceed even if snapshot fails
    process.stderr.write(`Warning [pre-compact]: ${err.message}\n`);
  }
}

/**
 * Collect all file dependencies from multiple sources.
 * Returns a deduplicated list of files currently being modified.
 * @param {string} projectRoot - Absolute path to project root.
 * @param {string} memoryDir - Absolute path to .ai/memory/.
 * @returns {string[]} Deduplicated file paths.
 */
function collectFileDependencies(projectRoot, memoryDir) {
  const files = new Set();

  // Staged files
  try {
    const staged = execSync('git diff --name-only --cached 2>/dev/null', {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
      cwd: projectRoot,
    }).trim();
    if (staged) {
      staged.split('\n').forEach((f) => files.add(f));
    }
  } catch {
    // Not in git - skip
  }

  // Unstaged modified files
  try {
    const unstaged = execSync('git diff --name-only 2>/dev/null', {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
      cwd: projectRoot,
    }).trim();
    if (unstaged) {
      unstaged.split('\n').forEach((f) => files.add(f));
    }
  } catch {
    // Not in git - skip
  }

  // Recently edited files from session state
  const sessionPath = path.join(memoryDir, 'session-state.json');
  const session = readJsonSafe(sessionPath);
  if (session) {
    const lastFiles = session.last_files || session.lastEdited || [];
    lastFiles.forEach((f) => files.add(f));
  }

  return Array.from(files);
}

/**
 * Try to infer the current task from plan files in docs/plans/.
 * Looks for in-progress stories.
 * @param {string} projectRoot - Absolute path to project root.
 * @returns {string|null} Description of current task, or null.
 */
function inferCurrentTaskFromPlans(projectRoot) {
  const fs = require('fs');
  const plansDir = path.join(projectRoot, 'docs', 'plans');

  try {
    if (!fs.existsSync(plansDir)) {
      return null;
    }

    const planFiles = fs.readdirSync(plansDir).filter((f) => f.endsWith('.md') || f.endsWith('.json'));

    for (const file of planFiles) {
      const filePath = path.join(plansDir, file);

      if (file.endsWith('.json')) {
        const plan = readJsonSafe(filePath);
        if (plan && Array.isArray(plan.stories)) {
          // Check for status === 'in_progress' (some plan formats)
          // or passes === false (toolkit plan format - not yet completed)
          const inProgress = plan.stories.find(
            (s) => s.status === 'in_progress' || (s.passes === false && s.status !== 'pending')
          );
          // Fallback: find first story that hasn't passed yet
          const notPassed = inProgress || plan.stories.find((s) => s.passes === false);
          if (notPassed) {
            return notPassed.title || notPassed.description || null;
          }
        }
      }

      if (file.endsWith('.md')) {
        try {
          const content = fs.readFileSync(filePath, 'utf8');
          // Look for "status: in_progress" or "currently working on" patterns
          const inProgressMatch = content.match(/(?:status:\s*in.?progress|currently working on)[:\s]*(.+)/i);
          if (inProgressMatch) {
            const task = inProgressMatch[1].trim().slice(0, 100);
            // Only return if the match contains meaningful text (not just dates/formatting)
            if (task.length > 3 && /[a-zA-Z]{3,}/.test(task)) {
              return task;
            }
          }
        } catch {
          // Skip unreadable files
        }
      }
    }
  } catch {
    // Plans directory doesn't exist or is unreadable - that is fine
  }

  return null;
}

main();
