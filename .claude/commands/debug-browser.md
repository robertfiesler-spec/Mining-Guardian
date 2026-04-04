---
suggest_when:
  - signal: file_extension
    value: ".tsx"
    min_edits: 3
    cooldown: 30
    message: "Editing React components? `/debug-browser` captures console errors and network failures live from the app"
  - signal: session_start
    condition: no_plan_many_edits
    cooldown: 60
    message: "UI issues to investigate? `/debug-browser` opens an interactive browser session to capture runtime errors"
---

# Debug Browser

Interactive browser debugging using Playwright MCP. Capture console errors, network failures, and runtime state directly from a running application.

## Your Task

Help the user debug browser-based issues by navigating to URLs, capturing console output, inspecting network failures, and analyzing runtime state.

$ARGUMENTS

## Prerequisites

### Playwright MCP Setup (One-Time)

The Playwright MCP server must be configured. Run once:

```bash
claude mcp add playwright -- npx @playwright/mcp@latest --console-level error
```

Or add to your `~/.claude.json` manually:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest", "--console-level", "error"]
    }
  }
}
```

### Console Level Options

| Level     | Captures                             |
| --------- | ------------------------------------ |
| `error`   | console.error, exceptions (default)  |
| `warning` | Above + console.warn                 |
| `info`    | Above + console.info, console.log    |
| `debug`   | All console output                   |

For verbose debugging, change `--console-level error` to `--console-level debug`.

### Authentication

For apps requiring login, set credentials in `.env.local` (git-ignored):

```bash
TEST_USER_EMAIL=test@example.com
TEST_USER_PASSWORD=your-test-password
```

Authentication is auto-detected when `--auth` is provided or when a login page redirect is detected. Supports Clerk email/password and Google OAuth. See the full auth playbook in `skills/dogfood/references/browser-auth.md`.

**Security Notes:**
- Never commit test credentials to git
- Use a dedicated test account, not a real user
- For Google OAuth, use a test account without 2FA

## Step 1: Parse Arguments

| Argument            | Example                       | Description                        |
| ------------------- | ----------------------------- | ---------------------------------- |
| `<url>`             | `http://localhost:3000/login` | URL to debug (required)            |
| `--auth`            |                               | Auto-login using test credentials  |
| `--console`         |                               | Focus on console errors            |
| `--network`         |                               | Focus on network failures          |
| `--interactive`     |                               | Keep browser open for exploration  |
| `--repro <steps>`   | `--repro "click login"`       | Steps to reproduce the issue       |

If no URL provided, prompt user:

```markdown
What URL should I debug? (e.g., http://localhost:3000)
```

## Step 2: Verify Dev Server Running

Before opening browser, check if URL is accessible:

```bash
curl -s -o /dev/null -w "%{http_code}" "$URL" || echo "not_reachable"
```

If not reachable:

```markdown
⚠️ Cannot reach $URL

Is your dev server running? Try:
- `npm run dev` or `pnpm dev`
- Check if the port is correct
- Verify no firewall blocking localhost
```

## Step 3: Open Browser and Navigate

Use Playwright MCP to open the URL. Tell the user you're using Playwright MCP:

```markdown
Opening browser via Playwright MCP...
```

Use the `playwright_navigate` tool to go to the URL. The browser will open in visible mode (not headless).

## Step 4: Authenticate (If --auth Flag or Login Detected)

If `--auth` flag is provided, or if navigation results in a login page (auto-detected):

### 4.1 Load Credentials

```bash
TEST_USER_EMAIL=$(grep '^TEST_USER_EMAIL=' .env.local 2>/dev/null | cut -d'=' -f2- | tr -d '"' | tr -d "'")
TEST_USER_PASSWORD=$(grep '^TEST_USER_PASSWORD=' .env.local 2>/dev/null | cut -d'=' -f2- | tr -d '"' | tr -d "'")
```

If empty, fall back to shell environment variables. If still empty, prompt user with `.env.local` setup instructions.

### 4.2 Detect Login Page

After navigation, auto-detect login pages by:

- **URL patterns**: `/sign-in`, `/login`, `/signin`, `/auth`, `accounts.clerk.dev`, `clerk.`
- **DOM signals**: Password input present, "Sign in" text visible

### 4.3 Complete Login Flow

**Clerk email/password** (Playwright MCP):
1. Fill email: `playwright_fill` on `input[name="identifier"]`, `input[type="email"]`, or `#identifier`
2. Click Continue (Clerk is multi-step)
3. Fill password: `playwright_fill` on `input[name="password"]` or `input[type="password"]`
4. Submit form (click "Sign in" or `playwright_press_key` Enter)
5. Wait for redirect away from login page

**Google OAuth** (Playwright MCP):
1. Click "Sign in with Google" button
2. Wait for Google login page (`accounts.google.com`)
3. Fill Google email: `playwright_fill` on `input[type="email"]`
4. Click Next
5. Fill Google password: `playwright_fill` on `input[type="password"]`
6. Click Next
7. Handle consent screen if shown (click Allow/Continue)
8. Wait for redirect back to app

For the full auth playbook with edge cases, see `skills/dogfood/references/browser-auth.md`.

### 4.4 Handle Auth Errors

| Error | Response |
| ----- | -------- |
| No credentials found | Report error, show `.env.local` setup instructions |
| Invalid credentials | Report error, suggest checking `.env.local` values |
| 2FA/MFA required | Inform user, suggest disabling for test account |
| CAPTCHA | Inform user, suggest `--interactive` for manual login |
| Rate limited | Wait and retry, or inform user |

## Step 5: Reproduce the Issue (If Steps Provided)

If `--repro` was provided or user described steps, execute them:

1. Parse the reproduction steps
2. Use Playwright MCP tools to interact:
   - `playwright_click` - Click elements
   - `playwright_fill` - Enter text
   - `playwright_select_option` - Select dropdowns
   - `playwright_press_key` - Keyboard input

Example reproduction:

```markdown
## Reproducing Issue

1. Clicking "Login" button...
2. Filling email field...
3. Clicking "Submit"...
4. Waiting for response...
```

## Step 6: Capture Debug Information

### Console Errors (--console or default)

After navigation/reproduction, capture console output:

```markdown
## Console Output

**Errors (2)**:
```
[error] TypeError: Cannot read property 'email' of undefined
    at UserSettings.tsx:42
    at renderWithHooks (react-dom.development.js:14985)

[error] Unhandled promise rejection: NetworkError
```

**Warnings (1)**:
```
[warn] React does not recognize the `isActive` prop on a DOM element
```
```

### Network Failures (--network or default)

Capture failed network requests:

```markdown
## Network Issues

**Failed Requests (2)**:
| Method | URL                     | Status | Error           |
| ------ | ----------------------- | ------ | --------------- |
| GET    | /api/user/settings      | 401    | Unauthorized    |
| POST   | /api/auth/refresh-token | 500    | Internal Error  |

**Slow Requests (>3s)**:
| Method | URL                | Duration |
| ------ | ------------------ | -------- |
| GET    | /api/products      | 4.2s     |
```

## Step 7: Analyze and Report

Compile findings into a debug report:

```markdown
## Browser Debug Report

**URL**: http://localhost:3000/settings
**Time**: 2024-01-15 14:30:52

### Summary

Found **2 console errors** and **1 network failure** that explain the issue.

### Root Cause Analysis

1. **Primary Issue**: API call to `/api/user/settings` returns 401 Unauthorized
   - This causes `user` to be undefined in the component
   - Which triggers the TypeError in UserSettings.tsx:42

2. **Secondary Issue**: Token refresh endpoint also failing (500)
   - Suggests auth state is corrupted or backend issue

### Recommended Actions

1. Check if auth token exists in localStorage/cookies
2. Verify the `/api/auth/refresh-token` endpoint is working
3. Add error handling for unauthorized state in UserSettings

### Next Steps

- Run `/debug --from-error "TypeError: Cannot read property 'email'"` for deeper analysis
- Check network tab manually for request/response details
- Review auth flow in the codebase
```

## Step 8: Interactive Mode (--interactive)

If `--interactive` flag or user wants to explore:

```markdown
Browser is open at $URL. What would you like me to do?

Available actions:
- Navigate to another page
- Click an element
- Fill a form
- Take a screenshot
- Check console for new errors
- Inspect a specific element

Type your request or say "done" to close the browser.
```

Keep browser open and respond to user requests until they say "done" or close.

## Error Handling

| Scenario                  | Response                                              |
| ------------------------- | ----------------------------------------------------- |
| Playwright MCP not setup  | Show setup instructions from Prerequisites            |
| URL not reachable         | Suggest starting dev server                           |
| Browser fails to open     | Check if Playwright browsers are installed            |
| No errors found           | Report clean state, suggest other debug approaches    |

### If Playwright MCP Not Available

```markdown
## Playwright MCP Not Configured

To use `/debug-browser`, you need to set up Playwright MCP first.

**Quick setup:**
```bash
claude mcp add playwright -- npx @playwright/mcp@latest --console-level error
```

**Then restart Claude Code** and try again.

For manual setup, see: https://github.com/microsoft/playwright-mcp
```

## Integration with /debug

`/debug-browser` complements the standard `/debug` command:

| Scenario                      | Use                                         |
| ----------------------------- | ------------------------------------------- |
| Error message, need root cause| `/debug --from-error "..."`                 |
| Need to see browser state     | `/debug-browser http://localhost:3000`      |
| Full debugging workflow       | `/debug-browser` → `/debug` with findings   |

Typical flow:

1. `/debug-browser http://localhost:3000/settings` - Capture browser errors
2. Find: "TypeError at UserSettings.tsx:42"
3. `/debug --from-error "TypeError at UserSettings.tsx:42"` - Analyze code

## Arguments

| Argument          | Description                                      |
| ----------------- | ------------------------------------------------ |
| `<url>`           | URL to debug (required)                          |
| `--auth`          | Auto-login using TEST_USER_EMAIL/PASSWORD        |
| `--console`       | Focus output on console errors                   |
| `--network`       | Focus output on network failures                 |
| `--interactive`   | Keep browser open for manual exploration         |
| `--repro <steps>` | Reproduction steps to execute                    |
| `--screenshot`    | Capture screenshot after navigation              |
| `--verbose`       | Show all console output, not just errors         |

## Examples

```bash
# Basic: Open URL and capture errors
/debug-browser http://localhost:3000/login

# Debug authenticated page (uses TEST_USER_EMAIL/PASSWORD)
/debug-browser --auth http://localhost:3000/dashboard

# Focus on network issues behind auth
/debug-browser --auth --network http://localhost:3000/api/settings

# Reproduce a bug
/debug-browser --repro "click #login-btn, wait 2s" http://localhost:3000

# Interactive exploration (can login manually)
/debug-browser --interactive http://localhost:3000/dashboard

# Capture screenshot with errors
/debug-browser --screenshot http://localhost:3000/broken-page
```

## Related Commands

| Command          | Use                                     |
| ---------------- | --------------------------------------- |
| `/debug`         | Hypothesis-driven debugging (code-side) |
| `/verify-visual` | Screenshot + accessibility capture      |
| `/verify`        | Quick lint, typecheck, tests            |

---

_Browser debugging captures what code analysis misses. When console.log isn't enough, open a real browser._

## Suggested Next

- `/debug` — hypothesis-driven debugging after capturing browser errors
- `/verify` — check for regressions after applying the fix
- `/create-commit` — commit the fix
