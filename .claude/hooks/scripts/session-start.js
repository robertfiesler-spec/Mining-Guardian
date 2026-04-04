#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const { execSync } = require('child_process');
const {
  findProjectRoot,
  detectPackageManager,
  readJsonSafe,
  getGitBranch,
  ensureDir,
  countLearnings,
  countStagedLearnings,
  formatRelativeTime,
  validateConfig,
  getRecentHookErrors,
} = require('./lib/utils');

/**
 * Evaluate session_start triggers from the compiled registry.
 * Returns an array of suggestion lines (max 3).
 */
function evaluateSessionStartTriggers(projectRoot) {
  const suggestions = [];
  const MAX_SUGGESTIONS = 3;

  // Load trigger registry
  let registry = null;
  const candidates = [
    path.join(__dirname, 'suggest-triggers.json'),
    path.join(os.homedir(), '.claude', 'hooks', 'scripts', 'suggest-triggers.json'),
  ];

  for (const candidate of candidates) {
    try {
      registry = JSON.parse(fs.readFileSync(candidate, 'utf8'));
      break;
    } catch {
      continue;
    }
  }

  if (!registry || !Array.isArray(registry.triggers)) return suggestions;

  // Filter to session_start triggers only
  const sessionTriggers = registry.triggers.filter(t => t.signal === 'session_start');

  for (const trigger of sessionTriggers) {
    if (suggestions.length >= MAX_SUGGESTIONS) break;

    try {
      if (checkCondition(trigger.condition, projectRoot)) {
        suggestions.push(`  → ${trigger.message}`);
      }
    } catch {
      // Skip failed condition checks
    }
  }

  return suggestions;
}

/**
 * Evaluate a session_start condition against the current project state.
 */
function checkCondition(condition, projectRoot) {
  switch (condition) {
    case 'incomplete_plan': {
      const plansDir = path.join(projectRoot, 'docs', 'plans');
      try {
        const files = fs.readdirSync(plansDir).filter(f => f.endsWith('.json'));
        for (const file of files) {
          const plan = JSON.parse(fs.readFileSync(path.join(plansDir, file), 'utf8'));
          const stories = plan.stories || plan.items || [];
          if (stories.some(s => s.passes === false || s.status === 'pending')) {
            return true;
          }
        }
      } catch {
        // No plans dir or parse error
      }
      return false;
    }

    case 'staged_learnings': {
      const stagingDir = path.join(projectRoot, '.ai', 'memory', 'staging');
      try {
        const files = fs.readdirSync(stagingDir);
        return files.length > 0;
      } catch {
        return false;
      }
    }

    case 'uncommitted_changes': {
      try {
        const output = execSync('git status --porcelain', {
          encoding: 'utf8',
          stdio: ['pipe', 'pipe', 'pipe'],
          cwd: projectRoot,
        }).trim();
        return output.length > 0;
      } catch {
        return false;
      }
    }

    case 'no_plan_many_edits': {
      // Check there's no active plan AND there are uncommitted changes
      const plansDir = path.join(projectRoot, 'docs', 'plans');
      let hasActivePlan = false;
      try {
        const files = fs.readdirSync(plansDir).filter(f => f.endsWith('.json'));
        hasActivePlan = files.length > 0;
      } catch {
        // No plans dir
      }

      if (hasActivePlan) return false;

      try {
        const output = execSync('git status --porcelain', {
          encoding: 'utf8',
          stdio: ['pipe', 'pipe', 'pipe'],
          cwd: projectRoot,
        }).trim();
        return output.split('\n').length >= 3;
      } catch {
        return false;
      }
    }

    case 'stalled_loop': {
      // Check loop-diagnostics.jsonl for repeated iterations on the same story
      // without any commits (indicates the loop is stuck)
      const diagFile = path.join(projectRoot, '.claude', 'state', 'loop-diagnostics.jsonl');
      try {
        const lines = fs.readFileSync(diagFile, 'utf8').trim().split('\n');
        // Look at the last 3+ entries — if all target the same story with no commits, it's stalled
        const recent = lines.slice(-3).map(l => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
        if (recent.length >= 3) {
          const sameStory = recent.every(r => r.story_id === recent[0].story_id);
          const noCommits = recent.every(r => r.commit_detected === false);
          if (sameStory && noCommits) return true;
        }
      } catch {
        // No diagnostics file
      }
      return false;
    }

    case 'no_agent_context': {
      // Check for CLAUDE.md, .claude/CLAUDE.md, or AGENTS.md
      try {
        const candidates = [
          path.join(projectRoot, 'CLAUDE.md'),
          path.join(projectRoot, '.claude', 'CLAUDE.md'),
          path.join(projectRoot, 'AGENTS.md'),
        ];
        return !candidates.some(f => fs.existsSync(f));
      } catch {
        return false;
      }
    }

    case 'first_session': {
      // True when no previous session state exists for this project
      const sessionPath = path.join(projectRoot, '.ai', 'memory', 'session-state.json');
      return !fs.existsSync(sessionPath);
    }

    case 'has_todos_or_issues': {
      // True when TODO.md has unchecked items
      const todoPath = path.join(projectRoot, 'TODO.md');
      try {
        const content = fs.readFileSync(todoPath, 'utf8');
        return /- \[ \]/.test(content);
      } catch {
        return false;
      }
    }

    case 'no_pyramid_large_project': {
      // True when no pyramid summaries exist and project has 20+ source files
      const pyramidDir = path.join(projectRoot, '.claude', 'pyramid');
      const hasPyramid = fs.existsSync(path.join(pyramidDir, 'L1-overview.md'));
      if (hasPyramid) {
        // Check staleness — suggest refresh if 200+ commits behind
        try {
          const meta = JSON.parse(fs.readFileSync(path.join(pyramidDir, '.pyramid-meta.json'), 'utf8'));
          const sha = meta.git_sha;
          if (sha) {
            const distance = execSync(`git rev-list --count ${sha}..HEAD 2>/dev/null`, {
              encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'], cwd: projectRoot,
            }).trim();
            return parseInt(distance, 10) >= 200;
          }
        } catch {
          // Can't check staleness — pyramid exists, don't nag
        }
        return false;
      }
      // No pyramid — check if project is large enough to benefit
      try {
        const output = execSync(
          'find . -type f \\( -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \\) ' +
          '-not -path "*/node_modules/*" -not -path "*/.next/*" -not -path "*/dist/*" | head -25',
          { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'], cwd: projectRoot }
        ).trim();
        const fileCount = output ? output.split('\n').length : 0;
        return fileCount >= 20;
      } catch {
        return false;
      }
    }

    default:
      return false;
  }
}

/**
 * SessionStart hook: Load project context at session initialization.
 *
 * Enhanced for memory persistence (STORY-8):
 * - Reads .ai/memory/session-state.json for last session's summary
 * - Shows pending tasks from previous session
 * - Shows active branch and last files edited
 * - Loads pre-compaction snapshot if it exists
 * - Counts learnings from .ai/memory/learnings/
 * - Evaluates session_start triggers for command suggestions
 * - Outputs a structured greeting with all context
 */
async function main() {
  try {
    const projectRoot = findProjectRoot() || process.cwd();
    const memoryDir = path.join(projectRoot, '.ai', 'memory');

    // Ensure memory directory exists for downstream hooks
    ensureDir(memoryDir);

    const sections = [];

    // --- Section 1: Environment ---
    const envLines = [];
    const pm = detectPackageManager(projectRoot);
    envLines.push(`  Package manager: ${pm}`);

    const branch = getGitBranch();
    if (branch) {
      envLines.push(`  Branch: ${branch}`);
      try {
        const dirty = execSync('git status --porcelain', {
          encoding: 'utf8',
          stdio: ['pipe', 'pipe', 'pipe'],
          cwd: projectRoot,
        }).trim();
        const dirtyCount = dirty ? dirty.split('\n').length : 0;
        if (dirtyCount > 0) {
          envLines.push(`  Uncommitted changes: ${dirtyCount} file${dirtyCount === 1 ? '' : 's'}`);
        }
      } catch {
        // git status failed - skip
      }
    } else {
      envLines.push('  Git: not a repository');
    }

    if (envLines.length > 0) {
      sections.push(`Environment:\n${envLines.join('\n')}`);
    }

    // --- Section 2: Previous Session State ---
    const sessionPath = path.join(memoryDir, 'session-state.json');
    const prevSession = readJsonSafe(sessionPath);
    if (prevSession && prevSession.timestamp) {
      const sessionLines = [];
      const relTime = formatRelativeTime(prevSession.timestamp);
      sessionLines.push(`  Last active: ${relTime}`);

      if (prevSession.branch) {
        sessionLines.push(`  Branch: ${prevSession.branch}`);
        // Flag if branch changed since last session
        if (branch && branch !== prevSession.branch) {
          sessionLines.push(`  ** Branch changed: ${prevSession.branch} -> ${branch}`);
        }
      }

      // Show last files edited (up to 5)
      const lastFiles = prevSession.last_files || prevSession.lastEdited || [];
      if (lastFiles.length > 0) {
        sessionLines.push(`  Last files edited:`);
        for (const file of lastFiles.slice(0, 5)) {
          sessionLines.push(`    - ${file}`);
        }
        if (lastFiles.length > 5) {
          sessionLines.push(`    ... and ${lastFiles.length - 5} more`);
        }
      }

      // Show active task if one was saved
      if (prevSession.active_task) {
        sessionLines.push(`  Active task: ${prevSession.active_task}`);
      }

      // Show uncommitted changes summary
      if (prevSession.uncommitted) {
        sessionLines.push(`  Uncommitted: ${prevSession.uncommitted}`);
      }

      sections.push(`Previous Session:\n${sessionLines.join('\n')}`);
    }

    // --- Section 3: Pending Tasks / TODOs ---
    const taskLines = [];

    // Check session-state todos
    if (prevSession && Array.isArray(prevSession.todos) && prevSession.todos.length > 0) {
      taskLines.push(`  From last session:`);
      for (const todo of prevSession.todos.slice(0, 5)) {
        taskLines.push(`    - ${typeof todo === 'string' ? todo : todo.text || todo.content || 'untitled'}`);
      }
      if (prevSession.todos.length > 5) {
        taskLines.push(`    ... and ${prevSession.todos.length - 5} more`);
      }
    }

    // Check todos.json file (legacy/parallel storage)
    const todosPath = path.join(memoryDir, 'todos.json');
    const todos = readJsonSafe(todosPath);
    if (todos && Array.isArray(todos.items)) {
      const pending = todos.items.filter((t) => t.status === 'pending');
      if (pending.length > 0) {
        taskLines.push(`  From todos.json: ${pending.length} pending`);
        for (const todo of pending.slice(0, 5)) {
          taskLines.push(`    - ${todo.text || todo.content || 'untitled'}`);
        }
        if (pending.length > 5) {
          taskLines.push(`    ... and ${pending.length - 5} more`);
        }
      }
    }

    if (taskLines.length > 0) {
      sections.push(`Pending Tasks:\n${taskLines.join('\n')}`);
    }

    // --- Section 4: Pre-Compaction Snapshot ---
    const snapshotPath = path.join(memoryDir, 'pre-compact-snapshot.json');
    const snapshot = readJsonSafe(snapshotPath);
    if (snapshot && snapshot.timestamp) {
      const snapLines = [];
      const snapTime = formatRelativeTime(snapshot.timestamp);
      snapLines.push(`  Saved: ${snapTime}`);

      if (snapshot.current_task) {
        snapLines.push(`  Task: ${snapshot.current_task}`);
      }

      if (Array.isArray(snapshot.key_decisions) && snapshot.key_decisions.length > 0) {
        snapLines.push(`  Key decisions:`);
        for (const decision of snapshot.key_decisions.slice(0, 3)) {
          snapLines.push(`    - ${decision}`);
        }
      }

      if (Array.isArray(snapshot.file_dependencies) && snapshot.file_dependencies.length > 0) {
        snapLines.push(`  Files in progress:`);
        for (const file of snapshot.file_dependencies.slice(0, 5)) {
          snapLines.push(`    - ${file}`);
        }
      }

      sections.push(`Pre-Compaction Snapshot (context recovered):\n${snapLines.join('\n')}`);
    }

    // --- Section 5: Learnings & Staging ---
    const learningsCount = countLearnings(projectRoot);
    const stagedCount = countStagedLearnings(projectRoot);
    const learningLines = [];
    if (learningsCount > 0) {
      learningLines.push(`  Learnings: ${learningsCount} pattern${learningsCount === 1 ? '' : 's'} in .ai/memory/learnings/`);
    }
    if (stagedCount > 0) {
      learningLines.push(`  Staged: ${stagedCount} pattern${stagedCount === 1 ? '' : 's'} ready for review → \`/evolve\` to promote to permanent rules`);
    } else if (learningsCount > 0) {
      learningLines.push(`  Staged: 0 — run \`/learn --pattern\` or \`/wrap-up\` to stage learnings for \`/evolve\``);
    }
    if (learningLines.length > 0) {
      sections.push(`Learning Pipeline:\n${learningLines.join('\n')}`);
    }

    // --- Section 6: Napkin ---
    // Surface per-repo napkin so the napkin skill is truly "always active"
    const napkinCandidates = [
      path.join(projectRoot, '.claude', 'napkin.md'),
      path.join(os.homedir(), '.claude', 'napkin.md'),
    ];
    for (const napkinPath of napkinCandidates) {
      try {
        const napkinContent = fs.readFileSync(napkinPath, 'utf8');
        const lineCount = napkinContent.split('\n').length;
        const relPath = napkinPath.startsWith(projectRoot)
          ? '.claude/napkin.md'
          : '~/.claude/napkin.md';
        sections.push(
          `Napkin: ${relPath} (${lineCount} lines)\n  Read this file before starting work — it contains mistakes, corrections, and patterns from previous sessions.`
        );
        break; // Use the first napkin found (project-local wins)
      } catch {
        // No napkin at this path
      }
    }

    // --- Section 7: Config Validation ---
    const { warnings: configWarnings } = validateConfig(projectRoot);
    if (configWarnings.length > 0) {
      const warnLines = configWarnings.map((w) => `  ⚠ ${w}`);
      sections.push(`Config Warnings:\n${warnLines.join('\n')}`);
    }

    // --- Section 8: Recent Hook Errors ---
    const recentErrors = getRecentHookErrors(24, 5);
    if (recentErrors.length > 0) {
      const errorLines = recentErrors.map((e) => {
        const time = formatRelativeTime(e.timestamp);
        const fileInfo = e.file ? ` (${e.file})` : '';
        return `  [${e.hook}] ${e.error}${fileInfo} — ${time}`;
      });
      sections.push(`Hook Errors (last 24h):\n${errorLines.join('\n')}\n  Log: ~/.ai/hook-errors.log`);
    }

    // --- Section 9: Suggested Commands ---
    const suggestLines = evaluateSessionStartTriggers(projectRoot);
    if (suggestLines.length > 0) {
      sections.push(`Suggested Commands:\n${suggestLines.join('\n')}`);
    }

    // --- Output structured greeting ---
    if (sections.length > 0) {
      const divider = '─'.repeat(50);
      const output = [
        `[session-start] ${divider}`,
        `Session Context Loaded`,
        '',
        ...sections.map((s) => s),
        divider,
      ].join('\n');
      process.stdout.write(output + '\n');
    } else {
      process.stdout.write('[session-start] New session (no previous context found)\n');
    }
  } catch (err) {
    // Fail gracefully - session should still start even if context loading fails
    process.stderr.write(`Warning [session-start]: ${err.message}\n`);
  }
}

main();
