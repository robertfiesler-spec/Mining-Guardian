#!/usr/bin/env node
'use strict';

const { execSync } = require('child_process');
const path = require('path');
const { readStdinJson, findProjectRoot, detectPackageManager, readJsonSafe, logHookError } = require('./lib/utils');

/**
 * PreToolUse hook (Bash): Run quality gates before git push.
 * Auto-detects typecheck, lint, and format scripts from package.json.
 * Exits with code 2 to block push if any check fails.
 * Pass --no-verify in the push command to bypass (toolkit convention,
 * not a native git push flag).
 *
 * Note: git-push-review.sh also hooks on git push (guards main/master).
 * Both hooks run independently — this one gates on quality checks,
 * that one gates on branch protection.
 */

const SCRIPT_TIMEOUT = 60_000; // 60 seconds per check

// Scripts to look for in package.json, in execution order
const QUALITY_SCRIPTS = [
  { key: 'typecheck', label: 'Type check' },
  { key: 'lint:ci', fallback: 'lint', label: 'Lint' },
  { key: 'format:check', label: 'Format check' },
];

const ALLOWED_SCRIPT_PATTERN = /^[a-zA-Z0-9:_-]+$/;

async function main() {
  try {
    const input = await readStdinJson();
    if (input.tool_name !== 'Bash') process.exit(0);

    const command = (input.tool_input || {}).command || '';

    // Only activate on git push commands
    if (!/\bgit\s+push\b/.test(command)) process.exit(0);

    // Skip dry runs — no need for quality gates on a simulated push
    if (/--dry-run/.test(command)) process.exit(0);

    // Allow explicit bypass (toolkit convention, not a native git push flag)
    if (/--no-verify/.test(command)) process.exit(0);

    const projectRoot = findProjectRoot();
    if (!projectRoot) process.exit(0);

    const pkg = readJsonSafe(path.join(projectRoot, 'package.json'));
    if (!pkg || !pkg.scripts) process.exit(0);

    const pm = detectPackageManager(projectRoot);

    // Resolve which scripts exist
    const checks = [];
    for (const { key, fallback, label } of QUALITY_SCRIPTS) {
      if (pkg.scripts[key]) {
        checks.push({ script: key, label });
      } else if (fallback && pkg.scripts[fallback]) {
        checks.push({ script: fallback, label });
      }
    }

    if (checks.length === 0) process.exit(0);

    process.stderr.write(`[push-guard] Running ${checks.length} quality gate(s) before push...\n`);

    for (const { script, label } of checks) {
      if (!ALLOWED_SCRIPT_PATTERN.test(script)) {
        process.stderr.write(`[push-guard] Skipping suspicious script name: ${script}\n`);
        continue;
      }
      try {
        execSync(`${pm} run ${script}`, {
          cwd: projectRoot,
          timeout: SCRIPT_TIMEOUT,
          stdio: ['pipe', 'pipe', 'pipe'],
          encoding: 'utf8',
        });
        process.stderr.write(`  ✓ ${label} passed\n`);
      } catch (err) {
        const output = (err.stderr || err.stdout || '').trim();
        const snippet = output.split('\n').slice(0, 20).join('\n');
        process.stderr.write(
          `BLOCKED: ${label} failed (${pm} run ${script})\n` +
          (snippet ? `\n${snippet}\n` : '')
        );
        process.exit(2);
      }
    }

    process.stderr.write(`[push-guard] All checks passed ✓\n`);
  } catch (err) {
    logHookError('push-guard', err.message);
    // Don't block on hook errors — fail open
  }
}

main();
