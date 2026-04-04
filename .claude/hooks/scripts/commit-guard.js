#!/usr/bin/env node
'use strict';

const { readStdinJson, logHookError } = require('./lib/utils');

/**
 * PreToolUse hook (Bash): Validate conventional commit format.
 * Only activates on `git commit` commands.
 * Exits with code 2 to block invalid commits.
 */

const VALID_TYPES = [
  'feat', 'fix', 'docs', 'style', 'refactor',
  'test', 'chore', 'perf', 'ci', 'build',
];

// Match: type(scope): description  OR  type: description
const CONVENTIONAL_COMMIT_RE = /^([\w]+)(?:\(([^)]+)\))?:\s+.+/;

function extractCommitMessage(command) {
  // Match -m "message", -m 'message', or -m message (up to next flag)
  const patterns = [
    /-m\s+"([^"]+)"/,
    /-m\s+'([^']+)'/,
    /-m\s+(\S+)/,
    /--message[= ]"([^"]+)"/,
    /--message[= ]'([^']+)'/,
  ];

  for (const pat of patterns) {
    const match = command.match(pat);
    if (match) {
      return match[1];
    }
  }

  // HEREDOC pattern: -m "$(cat <<'EOF'\n...\nEOF\n)"
  const heredocMatch = command.match(/-m\s+"\$\(cat\s+<<'?EOF'?\n([\s\S]*?)\nEOF/);
  if (heredocMatch) {
    return heredocMatch[1].trim();
  }

  return null;
}

async function main() {
  try {
    const input = await readStdinJson();
    const toolName = input.tool_name;
    const toolInput = input.tool_input || {};

    // Only process Bash tool calls
    if (toolName !== 'Bash') {
      process.exit(0);
    }

    const command = toolInput.command || '';

    // Only activate on git commit commands
    if (!command.match(/\bgit\s+commit\b/)) {
      process.exit(0);
    }

    // Skip --amend without -m (reuses previous message)
    if (command.match(/--amend/) && !command.match(/-m\b|--message/)) {
      process.exit(0);
    }

    const message = extractCommitMessage(command);
    if (!message) {
      // Could not extract message - might be interactive, let it pass
      process.exit(0);
    }

    // Validate conventional commit format
    const match = message.match(CONVENTIONAL_COMMIT_RE);
    if (!match) {
      process.stderr.write(
        `BLOCKED: Commit message does not follow conventional format.\n` +
        `Expected: type(scope): description\n` +
        `Example:  feat(auth): add OAuth2 login flow\n` +
        `Got:      ${message}\n`
      );
      process.exit(2);
    }

    const commitType = match[1];
    if (!VALID_TYPES.includes(commitType)) {
      process.stderr.write(
        `BLOCKED: Invalid commit type "${commitType}".\n` +
        `Valid types: ${VALID_TYPES.join(', ')}\n`
      );
      process.exit(2);
    }
  } catch (err) {
    logHookError('commit-guard', err.message);
    process.stderr.write(`Warning [commit-guard]: ${err.message}\n`);
  }
}

main();
