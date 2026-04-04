#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const { readStdinJson } = require('./lib/utils');

/**
 * PostToolUse hook: Unified suggestion engine.
 *
 * Combines two formerly separate hooks:
 * 1. Compaction suggestions — every COMPACT_THRESHOLD tool uses
 * 2. Command suggestions — pattern-based triggers from suggest-triggers.json
 *
 * Tracks tool use count, file edits, extensions, and cooldowns in a single
 * session-keyed temp file. Outputs at most one suggestion per tool call
 * (compaction takes priority at threshold boundaries).
 *
 * Always exits 0 — errors are logged to stderr, never block execution.
 */

const COMPACT_THRESHOLD = 15;

function getStateFilePath() {
  const sessionId = process.env.CLAUDE_SESSION_ID || process.env.CLAUDE_AGENT_ID || 'default';
  const sanitized = sessionId.replace(/[^a-zA-Z0-9_-]/g, '_');
  return path.join(os.tmpdir(), `claude-suggest-state-${sanitized}.json`);
}

function loadState() {
  try {
    const content = fs.readFileSync(getStateFilePath(), 'utf8');
    return JSON.parse(content);
  } catch {
    return {
      total_tool_calls: 0,
      edits_since_commit: 0,
      extension_counts: {},
      last_suggested: {},
    };
  }
}

function saveState(state) {
  try {
    fs.writeFileSync(getStateFilePath(), JSON.stringify(state), 'utf8');
  } catch {
    // Non-critical — state loss means at worst a repeated suggestion
  }
}

function loadRegistry() {
  const candidates = [
    path.join(__dirname, 'suggest-triggers.json'),
    path.join(os.homedir(), '.claude', 'hooks', 'scripts', 'suggest-triggers.json'),
  ];

  for (const candidate of candidates) {
    try {
      const content = fs.readFileSync(candidate, 'utf8');
      return JSON.parse(content);
    } catch {
      continue;
    }
  }

  return null;
}

function getFileExtension(filePath) {
  if (!filePath) return null;
  const base = path.basename(filePath);
  const testMatch = base.match(/\.(test|spec)\.(ts|tsx|js|jsx)$/);
  if (testMatch) return `.${testMatch[1]}.${testMatch[2]}`;
  return path.extname(filePath) || null;
}

function isCooldownActive(state, command, cooldownMinutes) {
  const lastTime = state.last_suggested[command];
  if (!lastTime) return false;
  const elapsed = (Date.now() - lastTime) / 60000;
  return elapsed < cooldownMinutes;
}

function evaluateTrigger(trigger, state) {
  const { signal, value, min_edits, cooldown, command } = trigger;

  // Skip session_start triggers — handled in session-start.js
  if (signal === 'session_start') return false;

  if (isCooldownActive(state, command, cooldown || 15)) return false;

  switch (signal) {
    case 'edits_since_commit': {
      if (value === 0) {
        return state.edits_since_commit === 0 && state.total_tool_calls > 5;
      }
      return state.edits_since_commit >= value;
    }

    case 'file_extension': {
      const count = state.extension_counts[value] || 0;
      const threshold = min_edits || 1;
      return count >= threshold;
    }

    case 'total_tool_calls': {
      return state.total_tool_calls >= value;
    }

    default:
      return false;
  }
}

async function main() {
  try {
    const input = await readStdinJson();
    const state = loadState();

    state.total_tool_calls++;

    const toolName = input.tool_name || '';
    const toolInput = input.tool_input || {};

    // Track file edits
    if (toolName === 'Edit' || toolName === 'Write') {
      state.edits_since_commit++;
      const filePath = toolInput.file_path || '';
      const ext = getFileExtension(filePath);
      if (ext) {
        state.extension_counts[ext] = (state.extension_counts[ext] || 0) + 1;
      }
    }

    // Reset counters on git commit
    if (toolName === 'Bash') {
      const cmd = toolInput.command || '';
      if (/git\s+commit/.test(cmd)) {
        state.edits_since_commit = 0;
        state.extension_counts = {};
      }
    }

    // Compaction suggestion takes priority at threshold boundaries
    let suggested = false;
    if (state.total_tool_calls > 0 && state.total_tool_calls % COMPACT_THRESHOLD === 0) {
      process.stdout.write(
        `[suggest-actions] ${state.total_tool_calls} tool uses in this session. ` +
        `Consider running /compact to free up context window space.\n`
      );
      suggested = true;
    }

    // Command suggestions (at most one per call, skip if compaction already fired)
    if (!suggested) {
      const registry = loadRegistry();
      if (registry && Array.isArray(registry.triggers)) {
        for (const trigger of registry.triggers) {
          if (evaluateTrigger(trigger, state)) {
            state.last_suggested[trigger.command] = Date.now();
            process.stdout.write(`[suggest] ${trigger.message}\n`);
            break;
          }
        }
      }
    }

    saveState(state);
  } catch (err) {
    process.stderr.write(`Warning [suggest-actions]: ${err.message}\n`);
  }
}

main();
