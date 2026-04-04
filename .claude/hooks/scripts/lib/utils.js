#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const { execSync } = require('child_process');

/**
 * Walk up from cwd looking for package.json or .git to find project root.
 * @returns {string|null} Absolute path to project root, or null if not found.
 */
function findProjectRoot(startDir) {
  let dir = startDir || process.cwd();
  const root = path.parse(dir).root;

  while (dir !== root) {
    if (fs.existsSync(path.join(dir, 'package.json')) || fs.existsSync(path.join(dir, '.git'))) {
      return dir;
    }
    dir = path.dirname(dir);
  }
  return null;
}

/**
 * Detect the package manager by checking lockfiles in the project root.
 * @returns {string} One of: pnpm, yarn, bun, npm (default).
 */
function detectPackageManager(projectRoot) {
  const root = projectRoot || findProjectRoot() || process.cwd();

  const lockfiles = [
    { file: 'pnpm-lock.yaml', manager: 'pnpm' },
    { file: 'yarn.lock', manager: 'yarn' },
    { file: 'bun.lockb', manager: 'bun' },
    { file: 'package-lock.json', manager: 'npm' },
  ];

  for (const { file, manager } of lockfiles) {
    if (fs.existsSync(path.join(root, file))) {
      return manager;
    }
  }
  return 'npm';
}

/**
 * Read a JSON file safely. Returns parsed object or null on failure.
 * @param {string} filePath - Absolute path to JSON file.
 * @returns {object|null}
 */
function readJsonSafe(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    return JSON.parse(content);
  } catch {
    return null;
  }
}

/**
 * Write a JSON file safely, creating parent directories if needed.
 * @param {string} filePath - Absolute path to JSON file.
 * @param {object} data - Data to serialize.
 * @returns {boolean} True on success, false on failure.
 */
function writeJsonSafe(filePath, data) {
  try {
    const dir = path.dirname(filePath);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + '\n', 'utf8');
    return true;
  } catch (err) {
    process.stderr.write(`Warning: Failed to write ${filePath}: ${err.message}\n`);
    return false;
  }
}

/**
 * Get the current git branch name.
 * @returns {string|null} Branch name or null if not in a git repo.
 */
function getGitBranch() {
  try {
    return execSync('git rev-parse --abbrev-ref HEAD', {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    }).trim();
  } catch {
    return null;
  }
}

/**
 * Ensure a directory exists, creating it recursively if needed.
 * @param {string} dirPath - Absolute path to directory.
 * @returns {boolean} True if directory exists or was created.
 */
function ensureDir(dirPath) {
  try {
    fs.mkdirSync(dirPath, { recursive: true });
    return true;
  } catch {
    return false;
  }
}

/**
 * Count learnings files in .ai/memory/learnings/ directory.
 * Counts both .md and .json files.
 * @param {string} projectRoot - Absolute path to project root.
 * @returns {number} Number of learning files found.
 */
function countLearnings(projectRoot) {
  const learningsDir = path.join(projectRoot, '.ai', 'memory', 'learnings');
  try {
    const files = fs.readdirSync(learningsDir);
    return files.filter((f) => f.endsWith('.md') || f.endsWith('.json')).length;
  } catch {
    return 0;
  }
}

/**
 * Count staged learning files in .ai/memory/staging/ directory.
 * Only counts unpromoted entries (.md and .json files).
 * @param {string} projectRoot - Absolute path to project root.
 * @returns {number} Number of staged learning files found.
 */
function countStagedLearnings(projectRoot) {
  const stagingDir = path.join(projectRoot, '.ai', 'memory', 'staging');
  try {
    const files = fs.readdirSync(stagingDir);
    return files.filter((f) => f.endsWith('.md') || f.endsWith('.json')).length;
  } catch {
    return 0;
  }
}

/**
 * Generate a short session ID (8 hex characters from timestamp + random).
 * @returns {string} Session ID string.
 */
function generateSessionId() {
  const timestamp = Date.now().toString(16).slice(-4);
  const random = Math.random().toString(16).slice(2, 6);
  return `${timestamp}${random}`;
}

/**
 * Get a summary of uncommitted git changes (e.g., "3 files changed, 45 insertions, 12 deletions").
 * @param {string} cwd - Working directory for git command.
 * @returns {string|null} Summary string or null if no changes / not in git.
 */
function getGitDiffSummary(cwd) {
  try {
    const output = execSync('git diff --stat HEAD 2>/dev/null | tail -1', {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
      cwd,
      shell: true,
    }).trim();
    if (output) {
      return output;
    }
    // Try staged changes if no unstaged
    const staged = execSync('git diff --stat --cached 2>/dev/null | tail -1', {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
      cwd,
      shell: true,
    }).trim();
    return staged || null;
  } catch {
    return null;
  }
}

/**
 * Get the last N files edited from git diff.
 * Includes both staged and unstaged changes.
 * @param {string} cwd - Working directory for git command.
 * @param {number} limit - Maximum number of files to return.
 * @returns {string[]} Array of file paths.
 */
function getLastEditedFiles(cwd, limit) {
  const n = limit || 5;
  try {
    // Combine staged and unstaged changes
    const unstaged = execSync('git diff --name-only 2>/dev/null', {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
      cwd,
    }).trim();
    const staged = execSync('git diff --name-only --cached 2>/dev/null', {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
      cwd,
    }).trim();

    const files = new Set();
    if (unstaged) {
      unstaged.split('\n').forEach((f) => files.add(f));
    }
    if (staged) {
      staged.split('\n').forEach((f) => files.add(f));
    }

    // If no staged/unstaged, try last commit
    if (files.size === 0) {
      const lastCommit = execSync('git diff --name-only HEAD~1 HEAD 2>/dev/null', {
        encoding: 'utf8',
        stdio: ['pipe', 'pipe', 'pipe'],
        cwd,
      }).trim();
      if (lastCommit) {
        lastCommit.split('\n').forEach((f) => files.add(f));
      }
    }

    return Array.from(files).slice(0, n);
  } catch {
    return [];
  }
}

/**
 * Format a relative time string from an ISO timestamp (e.g., "2 hours ago").
 * @param {string} isoTimestamp - ISO-8601 timestamp string.
 * @returns {string} Human-readable relative time.
 */
function formatRelativeTime(isoTimestamp) {
  try {
    const then = new Date(isoTimestamp).getTime();
    const now = Date.now();
    const diffMs = now - then;
    const diffMin = Math.floor(diffMs / 60000);
    const diffHr = Math.floor(diffMin / 60);
    const diffDays = Math.floor(diffHr / 24);

    if (diffMin < 1) return 'just now';
    if (diffMin < 60) return `${diffMin} minute${diffMin === 1 ? '' : 's'} ago`;
    if (diffHr < 24) return `${diffHr} hour${diffHr === 1 ? '' : 's'} ago`;
    if (diffDays < 30) return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
    return new Date(isoTimestamp).toLocaleDateString();
  } catch {
    return 'unknown';
  }
}

/**
 * Find test files related to a given source file.
 * Checks for: foo.test.ts, foo.spec.ts, __tests__/foo.ts (and .tsx/.js/.jsx variants).
 * @param {string} filePath - Absolute path to the source file.
 * @returns {string[]} Array of absolute paths to existing test files.
 */
function findRelatedTests(filePath) {
  const dir = path.dirname(filePath);
  const ext = path.extname(filePath);
  const base = path.basename(filePath, ext);
  const results = [];

  // Skip if the file itself is a test
  if (/\.(test|spec)\.(ts|tsx|js|jsx)$/.test(filePath)) {
    return [filePath];
  }

  const extensions = ['.ts', '.tsx', '.js', '.jsx'];
  const suffixes = ['.test', '.spec'];

  for (const testExt of extensions) {
    for (const suffix of suffixes) {
      // Same directory: foo.test.ts, foo.spec.ts
      const sameDir = path.join(dir, `${base}${suffix}${testExt}`);
      if (fs.existsSync(sameDir)) {
        results.push(sameDir);
      }
    }

    // __tests__ directory: __tests__/foo.ts
    const testsDir = path.join(dir, '__tests__', `${base}${testExt}`);
    if (fs.existsSync(testsDir)) {
      results.push(testsDir);
    }

    // __tests__ directory with suffix: __tests__/foo.test.ts
    for (const suffix of suffixes) {
      const testsDirWithSuffix = path.join(dir, '__tests__', `${base}${suffix}${testExt}`);
      if (fs.existsSync(testsDirWithSuffix)) {
        results.push(testsDirWithSuffix);
      }
    }
  }

  return results;
}

/**
 * Read JSON input from stdin (used by Claude Code hook protocol).
 * @returns {Promise<object>} Parsed JSON from stdin, or empty object.
 */
function readStdinJson() {
  return new Promise((resolve) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => { data += chunk; });
    process.stdin.on('end', () => {
      try {
        resolve(JSON.parse(data));
      } catch {
        resolve({});
      }
    });
    // Handle case where stdin is already closed or empty
    if (process.stdin.readableEnded) {
      resolve({});
    }
  });
}

/**
 * Get recent git commits since a given timestamp.
 * @param {string} cwd - Working directory for git command.
 * @param {string|null} sinceTimestamp - ISO-8601 timestamp to filter commits from. If null, returns last N commits.
 * @param {number} limit - Maximum number of commits to return.
 * @returns {string[]} Array of one-line commit summaries.
 */
function getRecentCommits(cwd, sinceTimestamp, limit) {
  const n = limit || 10;
  try {
    const sinceArg = sinceTimestamp ? `--since="${sinceTimestamp}"` : '';
    const cmd = `git log --oneline ${sinceArg} -n ${n} 2>/dev/null`;
    const output = execSync(cmd, {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
      cwd,
      shell: true,
    }).trim();
    return output ? output.split('\n') : [];
  } catch {
    return [];
  }
}

/**
 * Get active plan progress by reading plan files in docs/plans/.
 * @param {string} projectRoot - Absolute path to project root.
 * @returns {{ total: number, completed: number, planName: string, nextStory: string|null }|null}
 */
function getActivePlanProgress(projectRoot) {
  const plansDir = path.join(projectRoot, 'docs', 'plans');
  try {
    if (!fs.existsSync(plansDir)) return null;
    const files = fs.readdirSync(plansDir).filter((f) => f.endsWith('.json') || f.endsWith('.md'));
    if (files.length === 0) return null;

    // Sort by modification time, most recent first
    const sorted = files
      .map((f) => ({ name: f, mtime: fs.statSync(path.join(plansDir, f)).mtimeMs }))
      .sort((a, b) => b.mtime - a.mtime);

    const planFile = sorted[0].name;
    const planPath = path.join(plansDir, planFile);
    const content = fs.readFileSync(planPath, 'utf8');

    // Try JSON plan format
    if (planFile.endsWith('.json')) {
      const plan = JSON.parse(content);
      const stories = plan.stories || [];
      const completed = stories.filter((s) => s.passes === true).length;
      const nextStory = stories.find((s) => !s.passes);
      return {
        total: stories.length,
        completed,
        planName: plan.name || planFile.replace('.json', ''),
        nextStory: nextStory ? (nextStory.title || nextStory.name || null) : null,
      };
    }

    // Try markdown plan with checkboxes
    const checkboxes = content.match(/- \[[ x]\]/g) || [];
    const checked = content.match(/- \[x\]/gi) || [];
    if (checkboxes.length > 0) {
      return {
        total: checkboxes.length,
        completed: checked.length,
        planName: planFile.replace('.md', ''),
        nextStory: null,
      };
    }

    return null;
  } catch {
    return null;
  }
}

/**
 * Prune files in a directory, keeping only the most recent N files.
 * Files are sorted lexicographically (works with timestamp-prefixed names).
 * @param {string} dirPath - Absolute path to directory.
 * @param {number} keepCount - Number of most recent files to keep.
 * @param {string} extension - File extension filter (e.g., '.json'). Null for all files.
 */
function pruneDirectory(dirPath, keepCount, extension) {
  try {
    if (!fs.existsSync(dirPath)) return;
    let files = fs.readdirSync(dirPath);
    if (extension) {
      files = files.filter((f) => f.endsWith(extension));
    }
    files.sort(); // lexicographic = chronological for timestamp names
    const toRemove = files.slice(0, Math.max(0, files.length - keepCount));
    for (const f of toRemove) {
      fs.unlinkSync(path.join(dirPath, f));
    }
  } catch {
    // Fail silently - pruning is best-effort
  }
}

/**
 * Validate toolkit config.json for required fields.
 * Reads config from the project root (or ~/.claude/config.json as fallback).
 * @param {string} projectRoot - Absolute path to project root.
 * @returns {{ warnings: string[] }} Array of human-readable warning strings for missing/invalid fields.
 */
function validateConfig(projectRoot) {
  const warnings = [];

  // Locate config file
  const candidates = [
    path.join(projectRoot, 'config.json'),
    path.join(os.homedir(), '.claude', 'config.json'),
  ];

  let config = null;
  for (const candidate of candidates) {
    config = readJsonSafe(candidate);
    if (config) break;
  }

  if (!config) {
    warnings.push('config.json not found — run /init to generate one');
    return { warnings };
  }

  // Required top-level fields
  if (!config.version) {
    warnings.push('config.json missing "version" field');
  }

  // Stack fields used by stack-aware commands
  if (!config.stack || typeof config.stack !== 'object') {
    warnings.push('config.json missing "stack" section');
  } else if (!config.stack.framework) {
    warnings.push('config.json missing "stack.framework" (e.g., "nextjs")');
  }

  // Git fields used by commit-guard hook
  if (!config.git || typeof config.git !== 'object') {
    warnings.push('config.json missing "git" section (commit validation disabled)');
  } else {
    if (!config.git.commitFormat) {
      warnings.push('config.json missing "git.commitFormat" (commit-guard hook disabled)');
    }
    if (!Array.isArray(config.git.allowedTypes) || config.git.allowedTypes.length === 0) {
      warnings.push('config.json missing "git.allowedTypes" array (commit-guard hook disabled)');
    }
  }

  return { warnings };
}

/**
 * Append a structured hook error entry to ~/.ai/hook-errors.log.
 * Each line is a JSON object: { timestamp, hook, error, file? }
 * @param {string} hookName - Name of the hook (e.g., "auto-test", "type-check").
 * @param {string} errorMessage - The error message or stack trace.
 * @param {string} [filePath] - Optional file path that triggered the error.
 */
function logHookError(hookName, errorMessage, filePath) {
  try {
    const logPath = path.join(os.homedir(), '.ai', 'hook-errors.log');
    const dir = path.dirname(logPath);
    fs.mkdirSync(dir, { recursive: true });

    const entry = {
      timestamp: new Date().toISOString(),
      hook: hookName,
      error: errorMessage,
    };
    if (filePath) {
      entry.file = filePath;
    }

    fs.appendFileSync(logPath, JSON.stringify(entry) + '\n', 'utf8');
  } catch {
    // Fail silently — logging errors should never break the hook
  }
}

/**
 * Read recent hook errors from ~/.ai/hook-errors.log.
 * @param {number} [withinHours=24] - Only return errors from the last N hours.
 * @param {number} [limit=10] - Maximum number of entries to return.
 * @returns {{ timestamp: string, hook: string, error: string, file?: string }[]}
 */
function getRecentHookErrors(withinHours, limit) {
  const hours = withinHours || 24;
  const max = limit || 10;
  const logPath = path.join(os.homedir(), '.ai', 'hook-errors.log');

  try {
    if (!fs.existsSync(logPath)) return [];

    const content = fs.readFileSync(logPath, 'utf8').trim();
    if (!content) return [];

    const cutoff = Date.now() - hours * 60 * 60 * 1000;
    const lines = content.split('\n');

    // Read from the end for efficiency
    const results = [];
    for (let i = lines.length - 1; i >= 0 && results.length < max; i--) {
      try {
        const entry = JSON.parse(lines[i]);
        if (new Date(entry.timestamp).getTime() >= cutoff) {
          results.push(entry);
        } else {
          break; // Entries are chronological, so stop at first old entry
        }
      } catch {
        continue;
      }
    }

    return results.reverse();
  } catch {
    return [];
  }
}

/**
 * Write a plain text file safely, creating parent directories if needed.
 * @param {string} filePath - Absolute path to file.
 * @param {string} content - Text content to write.
 * @returns {boolean} True on success, false on failure.
 */
function writeFileSafe(filePath, content) {
  try {
    const dir = path.dirname(filePath);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(filePath, content, 'utf8');
    return true;
  } catch (err) {
    process.stderr.write(`Warning: Failed to write ${filePath}: ${err.message}\n`);
    return false;
  }
}

module.exports = {
  findProjectRoot,
  detectPackageManager,
  readJsonSafe,
  writeJsonSafe,
  writeFileSafe,
  getGitBranch,
  findRelatedTests,
  readStdinJson,
  ensureDir,
  countLearnings,
  countStagedLearnings,
  generateSessionId,
  getGitDiffSummary,
  getLastEditedFiles,
  formatRelativeTime,
  getRecentCommits,
  getActivePlanProgress,
  pruneDirectory,
  validateConfig,
  logHookError,
  getRecentHookErrors,
};
