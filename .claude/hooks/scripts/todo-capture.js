#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const { readStdinJson, findProjectRoot } = require('./lib/utils');

/**
 * PostToolUse hook: Detect TODO/FIXME/HACK/XXX patterns in Bash output.
 *
 * Suggests /create-todo when code markers are found in tool output.
 * Checks against existing TODO.md to avoid suggesting already-tracked items.
 * Session-keyed cooldown prevents suggestion spam (5 min between suggestions).
 *
 * Always exits 0 — errors are logged to stderr, never block execution.
 */

const COOLDOWN_MS = 5 * 60 * 1000; // 5 minutes
const MAX_OUTPUT_LENGTH = 50_000;
const TODO_PATTERN = /\b(TODO|FIXME|HACK|XXX):\s*(.+)/gi;

function getStateFilePath() {
  const sessionId = process.env.CLAUDE_SESSION_ID || process.env.CLAUDE_AGENT_ID || 'default';
  const sanitized = sessionId.replace(/[^a-zA-Z0-9_-]/g, '_');
  return path.join(os.tmpdir(), `claude-todo-capture-${sanitized}.json`);
}

function loadState() {
  try {
    return JSON.parse(fs.readFileSync(getStateFilePath(), 'utf8'));
  } catch {
    return { lastSuggested: 0 };
  }
}

function saveState(state) {
  try {
    fs.writeFileSync(getStateFilePath(), JSON.stringify(state), 'utf8');
  } catch {
    // Non-critical
  }
}

function loadExistingTodos(projectRoot) {
  const todoPath = path.join(projectRoot, 'TODO.md');
  try {
    return fs.readFileSync(todoPath, 'utf8').toLowerCase();
  } catch {
    return '';
  }
}

async function main() {
  try {
    const event = await readStdinJson();
    if (!event || !event.tool_output) {
      process.exit(0);
    }

    // Check cooldown before expensive work
    const state = loadState();
    const now = Date.now();
    if (now - state.lastSuggested < COOLDOWN_MS) {
      process.exit(0);
    }

    const output = typeof event.tool_output === 'string'
      ? event.tool_output
      : JSON.stringify(event.tool_output);

    // Skip oversized output to avoid expensive regex on build logs, test output, etc.
    if (output.length > MAX_OUTPUT_LENGTH) {
      process.exit(0);
    }

    // Find TODO/FIXME/HACK/XXX markers in output
    TODO_PATTERN.lastIndex = 0;
    const matches = [];
    let match;
    while ((match = TODO_PATTERN.exec(output)) !== null) {
      matches.push({ marker: match[1], text: match[2].trim().substring(0, 100) });
    }

    if (matches.length === 0) {
      process.exit(0);
    }

    // Check against existing TODO.md to avoid suggesting already-tracked items
    const projectRoot = findProjectRoot() || process.cwd();
    const knownTodos = loadExistingTodos(projectRoot);

    const newItems = matches.filter(m => {
      const keywords = m.text.toLowerCase().split(/\s+/).slice(0, 4).join(' ');
      return !knownTodos.includes(keywords);
    });

    if (newItems.length === 0) {
      process.exit(0);
    }

    // Suggest
    const first = newItems[0];
    const extra = newItems.length > 1 ? ` (+${newItems.length - 1} more)` : '';
    process.stdout.write(
      `[todo-capture] Found ${first.marker}: "${first.text}"${extra} — use \`/create-todo\` to track it\n`
    );

    state.lastSuggested = now;
    saveState(state);
  } catch (err) {
    process.stderr.write(`Warning [todo-capture]: ${err.message}\n`);
  }
  process.exit(0);
}

main();
