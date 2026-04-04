#!/usr/bin/env node
'use strict';

const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');
const { readStdinJson, findProjectRoot, logHookError } = require('./lib/utils');

/**
 * PostToolUse hook (Write/Edit): Run TypeScript type checking after .ts/.tsx edits.
 * Reports errors inline to stdout.
 */

function findTsConfig(startDir) {
  let dir = startDir;
  const root = path.parse(dir).root;

  while (dir !== root) {
    if (fs.existsSync(path.join(dir, 'tsconfig.json'))) {
      return dir;
    }
    dir = path.dirname(dir);
  }
  return null;
}

async function main() {
  try {
    const input = await readStdinJson();
    const toolName = input.tool_name;
    const toolInput = input.tool_input || {};

    // Only process Write and Edit tool calls
    if (toolName !== 'Write' && toolName !== 'Edit') {
      process.exit(0);
    }

    const filePath = toolInput.file_path || '';
    if (!filePath) {
      process.exit(0);
    }

    // Only check TypeScript files
    if (!/\.(ts|tsx)$/.test(filePath)) {
      process.exit(0);
    }

    // Verify the file exists
    if (!fs.existsSync(filePath)) {
      process.exit(0);
    }

    // Find tsconfig.json
    const tsRoot = findTsConfig(path.dirname(filePath));
    if (!tsRoot) {
      process.stderr.write('[type-check] No tsconfig.json found. Skipping.\n');
      process.exit(0);
    }

    // Run tsc --noEmit
    let tscOutput = '';
    try {
      // Try local tsc first, then npx
      const tscBin = fs.existsSync(path.join(tsRoot, 'node_modules', '.bin', 'tsc'))
        ? path.join(tsRoot, 'node_modules', '.bin', 'tsc')
        : 'npx tsc';

      tscOutput = execSync(`${tscBin} --noEmit 2>&1`, {
        encoding: 'utf8',
        cwd: tsRoot,
        timeout: 30000,
        stdio: ['pipe', 'pipe', 'pipe'],
      });
    } catch (execErr) {
      tscOutput = execErr.stdout || execErr.stderr || '';
    }

    if (!tscOutput || !tscOutput.trim()) {
      process.stdout.write(`[type-check] No TypeScript errors.\n`);
      process.exit(0);
    }

    // Filter errors to only show those for the edited file
    const basename = path.basename(filePath);
    const relativePath = path.relative(tsRoot, filePath);
    const errorLines = tscOutput
      .split('\n')
      .filter((line) => line.includes(basename) || line.includes(relativePath));

    if (errorLines.length > 0) {
      process.stdout.write(
        `[type-check] TypeScript errors in ${basename}:\n` +
        errorLines.join('\n') + '\n'
      );
    } else {
      process.stdout.write(`[type-check] No TypeScript errors in ${basename}.\n`);
    }
  } catch (err) {
    logHookError('type-check', err.message);
    process.stderr.write(`Warning [type-check]: ${err.message}\n`);
  }
}

main();
