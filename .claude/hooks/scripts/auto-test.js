#!/usr/bin/env node
'use strict';

const path = require('path');
const { execSync } = require('child_process');
const {
  readStdinJson,
  findRelatedTests,
  findProjectRoot,
  readJsonSafe,
  detectPackageManager,
  logHookError,
} = require('./lib/utils');

/**
 * PostToolUse hook (Write/Edit): After editing a source file, find and run related tests.
 * Uses findRelatedTests to locate test files, then invokes the test runner.
 */

// Skip running tests for these file types
const SKIP_EXTENSIONS = new Set([
  '.json', '.md', '.css', '.scss', '.less', '.svg', '.png',
  '.jpg', '.gif', '.ico', '.lock', '.yaml', '.yml', '.toml',
]);

function detectTestRunner(projectRoot) {
  const pkg = readJsonSafe(path.join(projectRoot, 'package.json'));
  if (!pkg || !pkg.scripts) {
    return null;
  }

  // Check for test runner in scripts
  if (pkg.scripts.test) {
    const testScript = pkg.scripts.test;
    if (testScript.includes('vitest')) return 'vitest';
    if (testScript.includes('jest')) return 'jest';
    if (testScript.includes('mocha')) return 'mocha';
  }

  // Check devDependencies
  const deps = { ...pkg.devDependencies, ...pkg.dependencies };
  if (deps.vitest) return 'vitest';
  if (deps.jest) return 'jest';
  if (deps.mocha) return 'mocha';

  return null;
}

function buildTestCommand(runner, pm, testFiles) {
  const files = testFiles.join(' ');
  const prefix = pm === 'npm' ? 'npx' : pm;

  switch (runner) {
    case 'vitest':
      return `${prefix} vitest run ${files} --reporter=verbose 2>&1`;
    case 'jest':
      return `${prefix} jest ${files} --verbose 2>&1`;
    case 'mocha':
      return `${prefix} mocha ${files} 2>&1`;
    default:
      return null;
  }
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

    // Skip non-source files
    const ext = path.extname(filePath).toLowerCase();
    if (SKIP_EXTENSIONS.has(ext)) {
      process.exit(0);
    }

    // Find related test files
    const testFiles = findRelatedTests(filePath);
    if (testFiles.length === 0) {
      process.exit(0);
    }

    const projectRoot = findProjectRoot(path.dirname(filePath));
    if (!projectRoot) {
      process.exit(0);
    }

    const runner = detectTestRunner(projectRoot);
    if (!runner) {
      process.stdout.write(
        `[auto-test] Found test files but no test runner detected:\n` +
        testFiles.map((f) => `  ${path.relative(projectRoot, f)}`).join('\n') + '\n'
      );
      process.exit(0);
    }

    const pm = detectPackageManager(projectRoot);
    const command = buildTestCommand(runner, pm, testFiles);
    if (!command) {
      process.exit(0);
    }

    process.stdout.write(`[auto-test] Running ${runner} for related tests...\n`);

    try {
      const output = execSync(command, {
        encoding: 'utf8',
        cwd: projectRoot,
        timeout: 30000,
        stdio: ['pipe', 'pipe', 'pipe'],
      });
      process.stdout.write(`[auto-test] Tests passed.\n${output}\n`);
    } catch (execErr) {
      const output = execErr.stdout || execErr.stderr || execErr.message;
      process.stdout.write(`[auto-test] Tests failed:\n${output}\n`);
    }
  } catch (err) {
    logHookError('auto-test', err.message);
    process.stderr.write(`Warning [auto-test]: ${err.message}\n`);
  }
}

main();
