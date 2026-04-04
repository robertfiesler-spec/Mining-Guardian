---
suggest_when:
  - signal: file_extension
    value: ".ts"
    min_edits: 5
    cooldown: 30
    message: "Multiple source file edits — `/security-check` to scan for vulnerabilities"
  - signal: edits_since_commit
    value: 10
    cooldown: 45
    message: "Significant changes — `/security-check --owasp` for OWASP Top 10 audit before PR"
---

# Security Check

Focused security review of code changes in the current feature branch. Identifies security issues before merging.

## Usage

```
/security-check [options]
```

$ARGUMENTS

## Step 0: Detect Base Branch

Determine the base branch for comparison:

```bash
# Try upstream tracking branch first
BASE_BRANCH=$(git rev-parse --abbrev-ref @{upstream} 2>/dev/null)

# Fall back to common defaults
if [ -z "$BASE_BRANCH" ]; then
  if git rev-parse --verify origin/staging >/dev/null 2>&1; then
    BASE_BRANCH="origin/staging"
  elif git rev-parse --verify origin/master >/dev/null 2>&1; then
    BASE_BRANCH="origin/master"
  elif git rev-parse --verify origin/main >/dev/null 2>&1; then
    BASE_BRANCH="origin/main"
  fi
fi
```

Store `BASE_BRANCH` for subsequent steps. Report which base branch is being used.

## Step 1: Identify Changed Files

Run:

```bash
git diff --name-only ${BASE_BRANCH}...HEAD
```

Categorize changes by security relevance:

| Priority | File Patterns                                                  | Risk Level |
| -------- | -------------------------------------------------------------- | ---------- |
| Critical | `**/auth/**`, `**/middleware*`, `**/api/**/*.ts`               | High       |
| High     | `*.env*`, `**/config/**`, `package*.json`, `requirements*.txt` | High       |
| Medium   | `**/lib/**`, `**/utils/**`, `**/services/**`                   | Medium     |
| Low      | `*.md`, `*.css`, `*.test.*`                                    | Low        |

Focus review on Critical and High priority files first.

## Step 2: Secrets Scan

Scan for hardcoded secrets in changed files:

```bash
# Search for potential secrets (case-insensitive)
git diff ${BASE_BRANCH}...HEAD | grep -E "^\+" | grep -iE "(password|secret|api[_-]?key|token|credential|private[_-]?key|auth[_-]?token|bearer|jwt)" || true

# Check for high-entropy strings (potential keys)
git diff ${BASE_BRANCH}...HEAD | grep -E "^\+" | grep -E "['\"][A-Za-z0-9+/]{32,}['\"]" || true

# Check for common secret patterns
git diff ${BASE_BRANCH}...HEAD | grep -E "^\+" | grep -E "(sk_live_|pk_live_|ghp_|gho_|AKIA|aws_)" || true
```

**Fail conditions:**

- Any matches in non-example files
- Secrets in source code (not `.env.example`)

**Auto-check:** Verify `.env.example` is updated for new environment variables without actual values.

## Step 3: Dependency Audit

Detect package manager and run appropriate audit:

```bash
# Node.js (detect lock file)
if [ -f "pnpm-lock.yaml" ]; then
  pnpm audit --audit-level=moderate
elif [ -f "yarn.lock" ]; then
  yarn audit --level moderate
elif [ -f "package-lock.json" ]; then
  npm audit --audit-level=moderate
fi

# Python
if [ -f "requirements.txt" ] || [ -f "pyproject.toml" ]; then
  pip-audit 2>/dev/null || safety check 2>/dev/null || echo "Install pip-audit: pip install pip-audit"
fi
```

**For new dependencies**, verify:

- [ ] Package is from trusted source (npm/PyPI official)
- [ ] Has recent maintenance activity
- [ ] No known CVEs at critical/high level
- [ ] Appropriate number of weekly downloads

## Step 4: Code Security Review

Review changed files for these vulnerability patterns:

### 4.1 Injection Vulnerabilities

| Check             | Pattern                                                                      | Severity |
| ----------------- | ---------------------------------------------------------------------------- | -------- |
| SQL Injection     | String concatenation in queries, `$queryRawUnsafe`, template literals in SQL | Critical |
| Command Injection | `exec()`, `system()`, `eval()`, `child_process` with user input              | Critical |
| NoSQL Injection   | Unvalidated input in MongoDB queries                                         | High     |

### 4.2 Authentication/Authorization

| Check                 | What to Verify                               |
| --------------------- | -------------------------------------------- |
| Auth on new endpoints | All `app/api/**` routes have auth check      |
| Authorization         | Resource ownership verified before mutations |
| Session handling      | No session tokens in URLs or logs            |
| Password handling     | Using bcrypt/argon2, not storing plaintext   |

### 4.3 Data Handling

| Check                   | What to Verify                              |
| ----------------------- | ------------------------------------------- |
| Input validation        | Zod/Yup schemas on API boundaries           |
| Output encoding         | No `dangerouslySetInnerHTML` with user data |
| Sensitive data exposure | No passwords/tokens in responses or logs    |
| Error messages          | Don't leak stack traces or internal details |

### 4.4 File Operations

| Check             | Pattern                     | Fix                          |
| ----------------- | --------------------------- | ---------------------------- |
| Path traversal    | User input in file paths    | Validate and sanitize paths  |
| Upload validation | Missing file type checks    | Whitelist allowed extensions |
| Size limits       | No upload size restrictions | Set max file size            |

## Step 5: API Security (New Endpoints Only)

For any new files in `app/api/**`:

| Check            | Requirement                        |
| ---------------- | ---------------------------------- |
| Rate limiting    | Endpoint has rate limit configured |
| CORS             | Not using `*` in production        |
| HTTP methods     | Only intended methods allowed      |
| Request size     | Body size limits configured        |
| Response headers | Security headers applied           |

## Step 6: Infrastructure Changes

For config file changes (`*.config.*`, `docker*`, `*.yaml`, `*.yml`):

| Check             | What to Verify                      |
| ----------------- | ----------------------------------- |
| Exposed ports     | No unnecessary port exposure        |
| Environment       | Secrets use env vars, not hardcoded |
| Permissions       | Least privilege principle           |
| External services | New integrations documented         |

## Output Format

```markdown
## Security Check Results

**Branch:** feature/xyz → main
**Files Scanned:** 12 (8 high priority)
**Scan Depth:** [quick|standard|thorough]

---

### CRITICAL (must fix before merge)

**[SEC-001] Potential SQL Injection**

- File: `app/api/users/route.ts:45`
- Code: `prisma.$queryRawUnsafe(\`SELECT \* FROM users WHERE id = '${id}'\`)`
- Fix: Use parameterized query: `prisma.$queryRaw\`SELECT \* FROM users WHERE id = ${id}\``

---

### HIGH (should fix before merge)

**[SEC-002] Missing Auth Check**

- File: `app/api/reports/route.ts`
- Issue: New API endpoint without authentication
- Fix: Add `const session = await auth(); if (!session) return unauthorized();`

**[SEC-003] Vulnerable Dependency**

- Package: `lodash@4.17.20`
- CVE: CVE-2021-23337 (Prototype Pollution)
- Fix: `pnpm update lodash`

---

### MEDIUM (consider fixing)

**[SEC-004] Missing Input Validation**

- File: `app/api/posts/route.ts:23`
- Issue: Request body not validated with schema
- Fix: Add Zod validation before processing

---

### INFO (informational)

- New environment variable `API_SECRET` added - ensure in `.env.example`
- 2 new API endpoints detected - verify rate limiting configured

---

## Summary

| Severity | Count | Status   |
| -------- | ----- | -------- |
| Critical | 1     | BLOCKING |
| High     | 2     | BLOCKING |
| Medium   | 1     | Warning  |
| Info     | 2     | OK       |

**Verdict:** FIX REQUIRED - Address 3 blocking issues before merge
```

## Arguments

| Argument             | Description                                                           |
| -------------------- | --------------------------------------------------------------------- |
| `--quick`            | Secrets scan and dependency audit only (fastest)                      |
| `--thorough`         | Include static analysis and deeper code review                        |
| `--owasp`            | OWASP Top 10 structured audit (loads `security-reviewer` agent)       |
| `--all`              | Scan entire project, not just changed files                           |
| `--fix`              | Auto-fix issues where possible (update deps, add missing validations) |
| `--base <branch>`    | Specify base branch instead of auto-detect                            |
| `--files <pattern>`  | Only scan files matching pattern                                      |
| `--ignore <pattern>` | Ignore files matching pattern                                         |
| `--json`             | Output results as JSON for CI integration                             |
| `--fail-on <level>`  | Exit non-zero if issues at level (critical/high/medium)               |

## Quick Scan Mode

With `--quick`:

1. Run secrets scan only
2. Run dependency audit only
3. Skip code review steps
4. Report: "Quick scan passed. Run full `/security-check` for complete review."

## Thorough Mode

With `--thorough`:

1. All standard checks
2. Static analysis with semgrep (if available)
3. Deeper regex patterns for vulnerabilities
4. Check test coverage for security-critical code
5. Review security-related comments (TODO, FIXME, HACK)

## OWASP Mode

With `--owasp`, run a structured audit against OWASP Top 10 categories using the `security-reviewer` agent. Focuses on real exploitable vulnerabilities, not theoretical risks.

1. Run Steps 0–3 (scope, secrets, dependencies) as normal
2. Replace Step 4 code review with OWASP Top 10 category checks:
   - **A01: Broken Access Control** — Missing auth, direct object references, CORS `*`
   - **A02: Cryptographic Failures** — Plaintext passwords/tokens, weak hashing (MD5/SHA1), missing HTTPS
   - **A03: Injection** — SQL/command/NoSQL injection via string concat, `exec()`, `eval()`
   - **A04: Insecure Design** — Missing rate limiting, no account lockout, logic bypasses
   - **A05: Security Misconfiguration** — Debug mode in prod, default credentials, permissive access
   - **A06: Vulnerable Components** — Run dependency audit (pnpm/npm/pip)
   - **A07: Auth Failures** — Session tokens in URLs, missing expiration, no MFA on sensitive ops
   - **A08: Data Integrity Failures** — Missing input validation, `dangerouslySetInnerHTML` with user data
   - **A09: Logging Failures** — Sensitive data in logs, missing audit trail, exposed stack traces
   - **A10: SSRF** — User-controlled URLs in server-side requests, missing allowlisting
3. Tag each finding with its OWASP category (e.g., `OWASP: A03`) in the report
4. Include Steps 5–6 (API security, infrastructure) as normal

Combine with `--all` for full-project OWASP audit.

## CI Integration

For CI pipelines, use:

```bash
# In GitHub Actions or similar
/security-check --json --fail-on high
```

Returns exit code 1 if blocking issues found.

## Auto-Fix Capabilities

With `--fix`, automatically:

- Update vulnerable dependencies to patched versions
- Add missing `.env.example` entries (without values)
- Generate Zod schema stubs for unvalidated endpoints
- Add auth check boilerplate to unprotected routes

Report all auto-fixes applied.

## Related Commands

- `/pre-pr-check` - Full pre-PR validation including security
- `/review` - Code review with security as one dimension
- `/verify` - Quick lint/type/test verification

## Related

- **Agent**: `security-reviewer` — loaded for `--owasp` analysis
- **Skill**: `security` — remediation patterns and secure coding guidance
- **Rule**: `rules/security.md` — always-apply security constraints

## Notes

- Run before creating PRs for security-sensitive changes
- Address all CRITICAL and HIGH issues before merging
- Document accepted risks for any skipped warnings
- Consider running `--thorough` for auth/payment features
- Use `--owasp` for structured OWASP Top 10 audit on auth/payment features

## Suggested Next

- `/pre-pr-check` — full pre-PR validation (includes security as one dimension)
- `/create-commit` — commit after addressing security findings
