---
name: Agent Delegation
description: When and how to delegate to subagents
---

# Agent Delegation

## When to Delegate

- Independent task with limited scope and clear expected output
- Multi-file/module work or codebase exploration for unfamiliar flows
- Reading 3+ files to answer a question (keeps main context clean)
- Research, doc lookups, or any investigation where only the summary matters
- Code review or analysis that produces verbose output

## When to Stay in Main Context

- Direct file edits (1-2 files)
- Back-and-forth conversations needing user input
- Tasks where user needs to see intermediate steps

## Handoff

- Provide: objective, file paths, constraints, expected output format
- Verify agent output before accepting -- agents can hallucinate paths

## Forbidden (always handle directly)

- Auth/permission changes, DB migrations, deployments, secrets

## Rules

- Sonnet for routine tasks; Opus for architecture/complex reasoning
- Never nest agents more than 1 level deep
- Parallel only for independent tasks; sequential for dependent work
- Prefer direct tool use for single-file, single-concern tasks
