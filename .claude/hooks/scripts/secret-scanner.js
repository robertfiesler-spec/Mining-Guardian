#!/usr/bin/env node
'use strict';

const { readStdinJson, logHookError } = require('./lib/utils');

/**
 * PreToolUse hook (Write/Edit): Scan file content for secrets and credentials.
 * Exits with code 2 to block the tool use if secrets are detected.
 */

const SECRET_PATTERNS = [
  { name: 'AWS Access Key', pattern: /AKIA[0-9A-Z]{16}/ },
  { name: 'AWS Secret Key', pattern: /(?:aws_secret_access_key|AWS_SECRET_ACCESS_KEY)\s*[=:]\s*[A-Za-z0-9/+=]{40}/ },
  { name: 'GitHub Token', pattern: /gh[pos]_[A-Za-z0-9_]{36,}/ },
  { name: 'Stripe Secret Key', pattern: /sk_live_[A-Za-z0-9]{24,}/ },
  { name: 'Stripe Publishable Key', pattern: /pk_live_[A-Za-z0-9]{24,}/ },
  { name: 'JWT Token', pattern: /eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+/ },
  { name: 'Private Key', pattern: /-----BEGIN\s+(RSA|EC|DSA|OPENSSH|PGP)?\s*PRIVATE KEY-----/ },
  { name: 'Password Assignment', pattern: /(?:password|passwd|pwd)\s*[=:]\s*['"][^'"]{8,}['"]/ },
  { name: 'Secret Assignment', pattern: /(?:secret|api_key|apikey|api_secret)\s*[=:]\s*['"][^'"]{8,}['"]/ },
  { name: 'Slack Token', pattern: /xox[bprs]-[A-Za-z0-9-]{10,}/ },
  { name: 'Twilio Key', pattern: /SK[0-9a-fA-F]{32}/ },
  { name: 'Database URL with Credentials', pattern: /(?:postgres|mysql|mongodb|redis):\/\/[^:]+:[^@]+@/ },
  { name: 'Generic Bearer Token', pattern: /Bearer\s+[A-Za-z0-9\-._~+/]+=*/ },
];

// Files that commonly contain example/test patterns (skip scanning)
const SKIP_PATTERNS = [
  /\.test\.(ts|tsx|js|jsx)$/,
  /\.spec\.(ts|tsx|js|jsx)$/,
  /__tests__\//,
  /\.example$/,
  /\.sample$/,
  /fixtures?\//,
  /mocks?\//,
];

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

    // Skip test/fixture files
    if (SKIP_PATTERNS.some((p) => p.test(filePath))) {
      process.exit(0);
    }

    // Get the content to scan
    const content = toolInput.content || toolInput.new_string || '';
    if (!content) {
      process.exit(0);
    }

    // Scan for secrets
    const findings = [];
    for (const { name, pattern } of SECRET_PATTERNS) {
      if (pattern.test(content)) {
        findings.push(name);
      }
    }

    if (findings.length > 0) {
      const types = findings.join(', ');
      process.stderr.write(
        `BLOCKED: Potential secrets detected in ${filePath || 'file content'}.\n` +
        `Found: ${types}\n` +
        `Remove credentials before writing. Use environment variables instead.\n`
      );
      process.exit(2);
    }
  } catch (err) {
    logHookError('secret-scanner', err.message);
    process.stderr.write(`Warning [secret-scanner]: ${err.message}\n`);
  }
}

main();
