---
suggest_when:
  - signal: total_tool_calls
    value: 35
    cooldown: 90
    message: "Feature looking solid? `/deploy` for a Vercel preview URL"
  - signal: session_start
    condition: uncommitted_changes
    message: "Uncommitted changes from last session — commit and `/deploy` when ready"
  - signal: file_extension
    value: ".sql,.prisma"
    cooldown: 120
    message: "Migration files detected — `/deploy` runs migration safety checks before deploying"
---

# /deploy Command

Deploy to Vercel and get preview URLs.

## Usage

```
/deploy [environment]
```

Environments: `preview` (default), `production`

## Process

1. **Migration Check** — detect migration files, classify risk, gate if needed
2. **Verify** project is ready for deployment
3. **Build** locally to catch errors early
4. **Deploy** to Vercel
5. **Return** preview URL and deployment info

## Step 1: Migration Safety Check

Before running pre-deploy checks, scan the changeset for database migrations:

```bash
# Detect migration files between base branch and HEAD
node ~/.claude/hooks/scripts/migration-detector.js --base origin/main --head HEAD --format json
```

### If migrations detected

Display the risk summary and act based on overall risk level:

| Risk Level | Behavior |
|------------|----------|
| **none** | Proceed silently |
| **low** | Display summary, proceed automatically |
| **medium** | Display summary with warnings, **block unless `--confirm-migrations`** |
| **high** | Display summary with destructive operations highlighted, **block unless `--confirm-migrations`** |

**When blocked (medium/high without `--confirm-migrations`)**:

```
MIGRATION GATE — DEPLOY BLOCKED
═══════════════════════════════════════════════════
Risk Level:    HIGH
Files:         2 migration file(s) detected
Frameworks:    prisma
Destructive:   DROP COLUMN (x1), RENAME TABLE (x1)

To proceed, review the migrations and re-run:
  /deploy --confirm-migrations

Or run a dry-run first:
  npx prisma migrate diff --from-schema-datamodel prisma/schema.prisma --to-migrations prisma/migrations --script
═══════════════════════════════════════════════════
```

The deployer agent references the `migration-safety` skill for framework-specific dry-run commands based on the detected framework(s).

### If no migrations detected

Proceed to Step 2 without output.

## Step 2: Pre-Deploy Checks

Before deploying, verify:

- [ ] No TypeScript errors (`npx tsc --noEmit`)
- [ ] No ESLint errors (`npm run lint`)
- [ ] Tests pass (`npm test`)
- [ ] Build succeeds (`npm run build`)
- [ ] Environment variables configured

## Deploy Steps

### Preview Deployment

```bash
# 1. Install Vercel CLI if needed
npm i -g vercel

# 2. Deploy to preview
vercel

# Returns:
# - Preview URL: https://project-abc123.vercel.app
# - Inspect URL: https://vercel.com/team/project/abc123
```

### Production Deployment

```bash
# Deploy to production
vercel --prod

# Returns:
# - Production URL: https://project.vercel.app
# - Custom domain: https://project.com (if configured)
```

## Post-Deploy Smoke Tests

After a successful deploy, run smoke tests against the preview/production URL to verify the deployment is healthy. Skippable with `--skip-smoke`.

### Default Checks

1. **Root path** — `GET /` returns HTTP 200
2. **Response time** — under 5 seconds
3. **No server errors** — response body does not contain 500-class error markers

### Custom Paths (`--smoke-paths`)

Test additional critical routes:

```bash
/deploy --smoke-paths "/api/health,/login,/dashboard"
```

Each path is tested for HTTP 200 and response time. Failed paths are reported but do not auto-rollback.

### Smoke Test Output

```
POST-DEPLOY SMOKE TESTS
═══════════════════════════════════════════════════
/              200  320ms  PASS
/api/health    200  180ms  PASS
/login         200  450ms  PASS
/dashboard     503  ---    FAIL
═══════════════════════════════════════════════════
Result: 3/4 passed

⚠️ /dashboard returned 503 — check deployment logs
   Recommended: vercel logs <deployment-url> --follow
```

If ALL smoke tests fail, recommend rollback but do NOT auto-rollback. The deployer agent will suggest `vercel rollback` with the previous deployment ID.

## ACS Integration (Cross-Project Deployment Memory)

When `ACS_URL` is configured, the deploy command integrates with the Agent Cognition System:

### Pre-Deploy: Query Past Learnings

Before running checks, the deployer agent queries ACS for relevant deployment history:

```bash
if [[ -n "${ACS_URL:-}" ]]; then
  source ~/.claude/scripts/lib/acs-client.sh
  if acs_is_available; then
    acs_query "deployment issues, rollbacks, migration failures for $(basename $(pwd))" 10 2000
  fi
fi
```

Past deployment failures, rollback events, and migration pitfalls from any project are surfaced to inform the current deploy.

### Post-Deploy: Store Outcome

After deployment completes, the outcome is stored in ACS for future reference:

```bash
if [[ -n "${ACS_URL:-}" ]]; then
  source ~/.claude/scripts/lib/acs-client.sh
  if acs_is_available; then
    acs_store "Deploy outcome summary" "fact" "/deploy" "$(basename $(pwd))"
  fi
fi
```

**Graceful degradation**: All ACS calls have timeouts and error handling. If ACS is unavailable, deploy proceeds normally without cross-project context.

## Output Format

```
═══════════════════════════════════════════════════
DEPLOYMENT SUCCESSFUL ✓
═══════════════════════════════════════════════════

🌐 Preview URL:    https://project-abc123.vercel.app
🔍 Inspect URL:    https://vercel.com/team/project/abc123
📊 Build Time:     45s
📦 Bundle Size:    First Load JS: 87.2 kB
🔬 Smoke Tests:    3/3 passed (1.2s total)

Environment: Preview
Branch: feature/new-feature
Commit: abc1234 - "feat: add new feature"

═══════════════════════════════════════════════════
```

## Error Handling

If deployment fails:

1. Show error message from Vercel
2. Common fixes:
   - Missing environment variables
   - Build errors
   - Node version mismatch
3. Link to deployment logs

## Environment Variables

Remind about required env vars if missing:

```
⚠️ Missing environment variables detected:

Required for this deployment:
- DATABASE_URL
- NEXTAUTH_SECRET

Set via:
- Vercel Dashboard: Settings → Environment Variables
- CLI: vercel env add DATABASE_URL
```

## Flags

```
/deploy                        # Preview deployment
/deploy --prod                 # Production deployment
/deploy --skip-checks          # Skip pre-deploy verification
/deploy --env=staging          # Deploy to staging environment
/deploy --confirm-migrations   # Acknowledge migration risk and proceed
/deploy --skip-smoke           # Skip post-deploy smoke tests
/deploy --smoke-paths "..."    # Comma-separated paths to test (default: /)
/deploy --pipeline             # Run full deploy pipeline (migration check → quality gates → build → deploy → smoke tests)
/deploy --pipeline --dry-run   # Preview pipeline DAG without executing
```

## Pipeline Mode (`--pipeline`)

Run the full deploy workflow as a `/pipeline` DAG instead of sequential steps. Uses the template at `.claude/templates/ci/deploy-pipeline.json`.

```bash
# Run pipeline with approval gate
/deploy --pipeline

# Preview the DAG without executing
/deploy --pipeline --dry-run

# Resume a failed pipeline
/deploy --pipeline --resume
```

### Pipeline DAG

```
migration-check
  ├── typecheck ──┐
  ├── lint ───────┤
  └── test ───────┘
                  build
                    │
              approve-deploy (gate)
                    │
                  deploy
                    │
               smoke-test
```

The `approve-deploy` gate pauses for confirmation before deploying. Pass `--skip-checks` to remove the gate.

Conditional `notify-failure` node fires if deploy or smoke tests fail, sending a notification via `.claude/scripts/notify.sh`.

## Suggested Next

| If... | Run |
|-------|-----|
| Want to verify the deployed app | `/dogfood` — systematic exploratory QA with screenshots |
| Check deployment status | `/status` — show git state and progress |
