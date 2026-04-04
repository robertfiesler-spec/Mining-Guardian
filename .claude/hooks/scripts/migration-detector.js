#!/usr/bin/env node
'use strict';

/**
 * Migration Detection Script
 *
 * Detects migration files in git diffs, classifies operations as
 * destructive/additive/data-only, and outputs JSON with overallRisk.
 *
 * Usage:
 *   node migration-detector.js --base origin/main --head HEAD --format json
 *   node migration-detector.js --base HEAD~1 --format text
 *
 * Zero external dependencies — uses only Node.js built-ins and git.
 */

const { execFileSync } = require('child_process');
const { readFileSync } = require('fs');
const path = require('path');

// --- CLI Args ---

const args = process.argv.slice(2);
function getArg(name, fallback) {
  const idx = args.indexOf(`--${name}`);
  if (idx === -1 || idx + 1 >= args.length) return fallback;
  return args[idx + 1];
}

const BASE = getArg('base', 'origin/main');
const HEAD = getArg('head', 'HEAD');
const FORMAT = getArg('format', 'json');

// --- Migration Path Patterns ---

const MIGRATION_PATTERNS = [
  // Prisma
  { framework: 'prisma', glob: 'prisma/migrations/**/migration.sql' },
  { framework: 'prisma', glob: 'prisma/schema.prisma' },
  { framework: 'prisma', glob: 'prisma/schema/*.prisma' },
  // Drizzle
  { framework: 'drizzle', glob: 'drizzle/**/*.sql' },
  { framework: 'drizzle', glob: 'src/db/migrations/**/*.sql' },
  { framework: 'drizzle', glob: 'drizzle.config.ts' },
  // Knex
  { framework: 'knex', glob: 'migrations/**/*.{js,ts}' },
  { framework: 'knex', glob: 'db/migrations/**/*.{js,ts}' },
  // TypeORM
  { framework: 'typeorm', glob: 'src/migrations/**/*.ts' },
  { framework: 'typeorm', glob: 'migrations/**/*.ts' },
  // Sequelize
  { framework: 'sequelize', glob: 'migrations/**/*.{js,ts}' },
  { framework: 'sequelize', glob: 'db/migrate/**/*.{js,ts}' },
  // Raw SQL
  { framework: 'raw-sql', glob: 'db/migrate/**/*.sql' },
  { framework: 'raw-sql', glob: 'sql/**/*.sql' },
  { framework: 'raw-sql', glob: 'src/db/migrations/**/*.sql' },
];

// --- SQL Operation Patterns ---

const DESTRUCTIVE_PATTERNS = [
  { name: 'DROP TABLE', pattern: /DROP\s+TABLE/i },
  { name: 'DROP COLUMN', pattern: /ALTER\s+TABLE\s+\S+\s+DROP\s+COLUMN/i },
  { name: 'RENAME TABLE', pattern: /ALTER\s+TABLE\s+\S+\s+RENAME\s+TO/i },
  { name: 'RENAME COLUMN', pattern: /RENAME\s+COLUMN/i },
  { name: 'CHANGE TYPE', pattern: /ALTER\s+TABLE\s+\S+\s+ALTER\s+COLUMN\s+\S+\s+(SET\s+DATA\s+)?TYPE/i },
  { name: 'TRUNCATE', pattern: /TRUNCATE\s+TABLE/i },
  { name: 'DROP INDEX', pattern: /DROP\s+INDEX/i },
  { name: 'DROP CONSTRAINT', pattern: /DROP\s+CONSTRAINT/i },
];

const ADDITIVE_PATTERNS = [
  { name: 'CREATE TABLE', pattern: /CREATE\s+TABLE/i },
  { name: 'ADD COLUMN', pattern: /ADD\s+COLUMN/i },
  { name: 'CREATE INDEX', pattern: /CREATE\s+(UNIQUE\s+)?INDEX/i },
  { name: 'ADD CONSTRAINT', pattern: /ADD\s+CONSTRAINT/i },
];

const DATA_PATTERNS = [
  { name: 'UPDATE', pattern: /UPDATE\s+\S+\s+SET/i },
  { name: 'INSERT', pattern: /INSERT\s+INTO/i },
  { name: 'DELETE', pattern: /DELETE\s+FROM/i },
];

// --- Git Helpers ---

function getChangedFiles() {
  const opts = { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] };
  try {
    const output = execFileSync('git', ['diff', '--name-only', `${BASE}...${HEAD}`], opts);
    return output.trim().split('\n').filter(Boolean);
  } catch {
    try {
      const output = execFileSync('git', ['diff', '--name-only', BASE, HEAD], opts);
      return output.trim().split('\n').filter(Boolean);
    } catch {
      return [];
    }
  }
}

function getFileContent(filePath) {
  const opts = { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] };
  try {
    return execFileSync('git', ['show', `${HEAD}:${filePath}`], opts);
  } catch {
    try {
      return readFileSync(filePath, 'utf8');
    } catch {
      return '';
    }
  }
}

function getFileDiff(filePath) {
  const opts = { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] };
  try {
    return execFileSync('git', ['diff', `${BASE}...${HEAD}`, '--', filePath], opts);
  } catch {
    try {
      return execFileSync('git', ['diff', BASE, HEAD, '--', filePath], opts);
    } catch {
      return '';
    }
  }
}

// --- Pattern Matching ---

function matchesGlob(filePath, globPattern) {
  // Simple glob matching without external deps
  const regex = globPattern
    .replace(/\./g, '\\.')
    .replace(/\*\*/g, '{{DOUBLESTAR}}')
    .replace(/\*/g, '[^/]*')
    .replace(/\{\{DOUBLESTAR\}\}/g, '.*')
    .replace(/\{([^}]+)\}/g, (_, alts) => `(?:${alts.replace(/,/g, '|')})`);
  return new RegExp(`^${regex}$`).test(filePath);
}

function detectFramework(filePath) {
  for (const { framework, glob } of MIGRATION_PATTERNS) {
    if (matchesGlob(filePath, glob)) {
      return framework;
    }
  }
  return null;
}

function classifyOperations(content) {
  const operations = [];

  for (const { name, pattern } of DESTRUCTIVE_PATTERNS) {
    const matches = content.match(new RegExp(pattern.source, 'gi'));
    if (matches) {
      operations.push({ name, risk: 'high', count: matches.length });
    }
  }

  for (const { name, pattern } of ADDITIVE_PATTERNS) {
    const matches = content.match(new RegExp(pattern.source, 'gi'));
    if (matches) {
      operations.push({ name, risk: 'low', count: matches.length });
    }
  }

  for (const { name, pattern } of DATA_PATTERNS) {
    const matches = content.match(new RegExp(pattern.source, 'gi'));
    if (matches) {
      operations.push({ name, risk: 'medium', count: matches.length });
    }
  }

  return operations;
}

function classifyJsMigration(content) {
  // For JS/TS migration files, look for ORM-specific patterns
  const operations = [];
  const patterns = [
    { name: 'dropTable', risk: 'high', pattern: /\.dropTable\s*\(/gi },
    { name: 'dropColumn', risk: 'high', pattern: /\.dropColumn\s*\(/gi },
    { name: 'renameTable', risk: 'high', pattern: /\.renameTable\s*\(/gi },
    { name: 'renameColumn', risk: 'high', pattern: /\.renameColumn\s*\(/gi },
    { name: 'removeColumn', risk: 'high', pattern: /\.removeColumn\s*\(/gi },
    { name: 'changeColumn', risk: 'high', pattern: /\.changeColumn\s*\(/gi },
    { name: 'createTable', risk: 'low', pattern: /\.createTable\s*\(/gi },
    { name: 'addColumn', risk: 'low', pattern: /\.addColumn\s*\(/gi },
    { name: 'addIndex', risk: 'low', pattern: /\.addIndex\s*\(/gi },
    { name: 'addConstraint', risk: 'low', pattern: /\.addConstraint\s*\(/gi },
  ];

  for (const { name, risk, pattern } of patterns) {
    const matches = content.match(pattern);
    if (matches) {
      operations.push({ name, risk, count: matches.length });
    }
  }

  return operations;
}

// --- Main ---

function run() {
  const changedFiles = getChangedFiles();
  if (changedFiles.length === 0) {
    return outputResult({ migrationFiles: [], overallRisk: 'none', frameworks: [] });
  }

  const migrationFiles = [];
  const frameworksFound = new Set();

  for (const filePath of changedFiles) {
    const framework = detectFramework(filePath);
    if (!framework) continue;

    frameworksFound.add(framework);

    const isSql = filePath.endsWith('.sql') || filePath.endsWith('.prisma');
    const content = getFileContent(filePath);
    const diff = getFileDiff(filePath);

    // Classify based on the added lines in the diff (not full file)
    const addedLines = diff
      .split('\n')
      .filter(line => line.startsWith('+') && !line.startsWith('+++'))
      .map(line => line.slice(1))
      .join('\n');

    const contentToClassify = addedLines || content;
    const operations = isSql
      ? classifyOperations(contentToClassify)
      : classifyJsMigration(contentToClassify);

    // Schema-only files (e.g., prisma/schema.prisma) are informational
    const isSchemaFile = /schema\.prisma$|drizzle\.config\.ts$/.test(filePath);

    migrationFiles.push({
      path: filePath,
      framework,
      isSchemaFile,
      operations,
      fileRisk: computeFileRisk(operations),
    });
  }

  const overallRisk = computeOverallRisk(migrationFiles);

  return outputResult({
    migrationFiles,
    overallRisk,
    frameworks: [...frameworksFound],
    summary: buildSummary(migrationFiles, overallRisk),
  });
}

function computeFileRisk(operations) {
  if (operations.some(op => op.risk === 'high')) return 'high';
  if (operations.some(op => op.risk === 'medium')) return 'medium';
  if (operations.length > 0) return 'low';
  return 'none';
}

function computeOverallRisk(files) {
  const migrationFiles = files.filter(f => !f.isSchemaFile);
  if (migrationFiles.length === 0) {
    // Only schema files changed — informational
    return files.length > 0 ? 'low' : 'none';
  }
  if (migrationFiles.some(f => f.fileRisk === 'high')) return 'high';
  if (migrationFiles.some(f => f.fileRisk === 'medium')) return 'medium';
  if (migrationFiles.some(f => f.fileRisk === 'low')) return 'low';
  return 'none';
}

function buildSummary(files, overallRisk) {
  if (files.length === 0) return 'No migration files detected.';

  const destructive = files.flatMap(f => f.operations.filter(op => op.risk === 'high'));
  const additive = files.flatMap(f => f.operations.filter(op => op.risk === 'low'));
  const dataOps = files.flatMap(f => f.operations.filter(op => op.risk === 'medium'));

  const parts = [];
  parts.push(`${files.length} migration file(s) detected.`);
  parts.push(`Overall risk: ${overallRisk.toUpperCase()}.`);
  if (destructive.length > 0) {
    parts.push(`Destructive: ${destructive.map(d => d.name).join(', ')}.`);
  }
  if (dataOps.length > 0) {
    parts.push(`Data operations: ${dataOps.map(d => d.name).join(', ')}.`);
  }
  if (additive.length > 0) {
    parts.push(`Additive: ${additive.map(d => d.name).join(', ')}.`);
  }
  return parts.join(' ');
}

function outputResult(result) {
  if (FORMAT === 'json') {
    process.stdout.write(JSON.stringify(result, null, 2) + '\n');
  } else {
    // Text format for human readability
    if (result.migrationFiles.length === 0) {
      process.stdout.write('No migration files detected.\n');
      return;
    }

    process.stdout.write(`\nMIGRATION ANALYSIS\n`);
    process.stdout.write(`${'═'.repeat(50)}\n`);
    process.stdout.write(`Overall Risk:  ${result.overallRisk.toUpperCase()}\n`);
    process.stdout.write(`Frameworks:    ${result.frameworks.join(', ')}\n`);
    process.stdout.write(`Files:         ${result.migrationFiles.length}\n`);
    process.stdout.write(`${'─'.repeat(50)}\n\n`);

    for (const file of result.migrationFiles) {
      const tag = file.isSchemaFile ? ' (schema)' : '';
      process.stdout.write(`  ${file.path}${tag}\n`);
      process.stdout.write(`    Framework: ${file.framework} | Risk: ${file.fileRisk}\n`);
      if (file.operations.length > 0) {
        for (const op of file.operations) {
          const icon = op.risk === 'high' ? '!!' : op.risk === 'medium' ? ' ?' : ' +';
          process.stdout.write(`    ${icon} ${op.name} (x${op.count})\n`);
        }
      } else {
        process.stdout.write(`     + No risky operations detected\n`);
      }
      process.stdout.write('\n');
    }

    if (result.summary) {
      process.stdout.write(`${result.summary}\n`);
    }
  }
}

run();
