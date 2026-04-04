# Hooks

Hooks are trigger-based automations that fire on specific lifecycle events.

## Claude Code Hooks

These hooks integrate with Claude Code's hook system to provide real-time agent tracking and code quality automation.

### Agent Registration (TUI Integration)

Automatically tracks Claude agent sessions for the TUI dashboard.

**Files:**

- `pre-tool-use/agent-register.sh` - Registers agent on first tool use, updates activity on subsequent uses
- `stop/agent-deregister.sh` - Marks agent as completed when session ends
- `lib/orchestrator-utils.sh` - Shared utilities for orchestrator state management

**How it works:**

1. On first tool use, creates a new agent entry in `.claude/state/orchestrator.json`
2. Updates the agent's `currentCommand` on each subsequent tool use
3. Marks the agent as `completed` when the session ends

**Environment Variables:**

- `CLAUDE_AGENT_NAME` - Custom agent name (default: "Manual Agent")
- `CLAUDE_SESSION_ID` - Session identifier (auto-generated if not set)

**Agent Types (auto-detected):**

- `executor` - Bash commands
- `explorer` - Read, Glob, Grep operations
- `editor` - Write, Edit operations
- `orchestrator` - Task delegation
- `general` - Other tools

**Usage:**
Once configured in `settings.json`, agents are automatically tracked. View them in the TUI:

```bash
./scripts/tui-wrapper.sh
# Select [R] Real Tracking mode
```

---

### Code Quality Hooks

**PreToolUse:**

- `tmux-reminder.sh` - Warns about long-running commands outside tmux
- `block-md-creation.sh` - Prevents unwanted markdown file creation
- `git-push-review.sh` - Review commits before push, warns about protected branches
- `push-guard.js` (Node.js) - Run quality gates (typecheck, lint, format) before push; bypass with `--no-verify`

**PostToolUse:**

- `prettier-format.sh` - Auto-formats edited files
- `console-log-guard.sh --check` - Warns about `console.log` additions in edits
- `a11y-design-check.sh` - Checks accessibility in React components

**Stop:**

- `console-log-guard.sh --audit` - Audits modified files for `console.log` at session end

---

## Git Hooks (Husky)

### pre-commit

Runs before each commit to ensure code quality.

**Triggers:** Before `git commit`

**Actions:**

1. Run TypeScript type checking
2. Run ESLint on staged files
3. Run Prettier on staged files
4. Run affected unit tests

**Setup:**

```bash
# Install husky and lint-staged
npm install -D husky lint-staged

# Initialize husky
npx husky init
```

```json
// package.json
{
  "lint-staged": {
    "*.{ts,tsx}": ["eslint --fix", "prettier --write"],
    "*.{json,md}": ["prettier --write"]
  }
}
```

```bash
# .husky/pre-commit
npx lint-staged
npx tsc --noEmit
```

---

### pre-push

Runs before pushing to remote.

**Triggers:** Before `git push`

**Actions:**

1. Run full test suite
2. Verify build succeeds
3. Check for security vulnerabilities
4. Scan for hardcoded secrets

**Setup:**

```bash
# .husky/pre-push
npm test
npm run build
npm audit --audit-level=high

# Security scan for secrets (blocks push if secrets detected)
if git diff origin/main...HEAD | grep -qiE "(sk_live_|pk_live_|ghp_|AKIA|password\s*=|api[_-]?key\s*=)"; then
  echo "ERROR: Potential secrets detected in commits. Run /security-check for details."
  exit 1
fi
```

**Alternative - Claude Code Integration:**

For more comprehensive security scanning, you can configure a pre-push reminder:

```bash
# .husky/pre-push
echo "Reminder: Run '/security-check' before creating PR for security-sensitive changes"
npm test
npm run build
```

---

### post-checkout

Runs after switching branches.

**Triggers:** After `git checkout` or `git switch`

**Actions:**

1. Install dependencies if package.json changed
2. Run database migrations if needed
3. Clear local cache if needed

**Setup:**

```bash
# .husky/post-checkout
# $1 = previous HEAD, $2 = new HEAD, $3 = branch checkout flag

# Check if package.json changed
if git diff --name-only $1 $2 | grep -q "package.json"; then
  npm install
fi

# Check if migrations changed
if git diff --name-only $1 $2 | grep -q "prisma/migrations"; then
  npx prisma migrate dev
fi
```

---

### on-file-create

When Claude creates new files, apply templates and standards.

**Triggers:** File creation in watched directories

**Actions:**

- Components: Add standard imports, prop types template
- Hooks: Add JSDoc template
- API routes: Add error handling boilerplate

**Example Component Template:**

```typescript
// Auto-applied when creating components/*.tsx
import { type ComponentProps } from 'react';

interface ${ComponentName}Props {
  // TODO: Define props
}

export function ${ComponentName}({ }: ${ComponentName}Props) {
  return (
    <div>
      {/* TODO: Implement */}
    </div>
  );
}
```

---

### on-error

When errors occur during Claude operations.

**Triggers:** TypeScript errors, lint errors, test failures

**Actions:**

1. Parse error message
2. Suggest fix based on error type
3. Offer to apply fix automatically

**Common Error Handlers:**

| Error Pattern                             | Suggested Fix                                                |
| ----------------------------------------- | ------------------------------------------------------------ |
| `Type 'X' is not assignable to type 'Y'`  | Check type definitions, add type assertion or fix data shape |
| `Cannot find module 'X'`                  | Install missing dependency                                   |
| `Property 'X' does not exist on type 'Y'` | Add to interface or check spelling                           |
| `'X' is declared but never used`          | Remove unused variable or add `_` prefix                     |

---

## Configuration

Hooks can be enabled/disabled in `.ai/config.json`:

```json
{
  "hooks": {
    "pre-commit": true,
    "pre-push": true,
    "post-checkout": true,
    "on-file-create": true,
    "on-error": true
  }
}
```

## Custom Hooks

Create custom hooks in `.ai/hooks/`:

```markdown
# .ai/hooks/my-custom-hook.md

## Trigger

Describe when this hook should fire

## Actions

1. Step one
2. Step two

## Script

\`\`\`bash

# Commands to execute

\`\`\`
```
