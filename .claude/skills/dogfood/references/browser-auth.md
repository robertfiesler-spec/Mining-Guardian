# Browser Authentication Reference

Reference for authenticating into web applications during dogfood QA and browser debugging sessions. Both agent-browser and Playwright MCP flows are covered.

## Credential Loading

Before any auth flow, read credentials from the project's `.env.local`:

```bash
TEST_USER_EMAIL=$(grep '^TEST_USER_EMAIL=' .env.local 2>/dev/null | cut -d'=' -f2- | tr -d '"' | tr -d "'")
TEST_USER_PASSWORD=$(grep '^TEST_USER_PASSWORD=' .env.local 2>/dev/null | cut -d'=' -f2- | tr -d '"' | tr -d "'")
```

If both are empty, fall back to shell environment variables (they may already be exported). If still empty, report to the user:

```
No test credentials found.

Set these in your project's .env.local:

  TEST_USER_EMAIL=your-test-email@example.com
  TEST_USER_PASSWORD=your-test-password

Then restart the session.
```

**Security notes:**
- Never commit credentials to git (`.env.local` is gitignored by Next.js)
- Use a dedicated test account, not a real user account
- For Google OAuth, use a Google Workspace test account without 2FA

## Login Page Auto-Detection

Auth detection runs **automatically** after every navigation -- no `--auth` flag required.

### URL signals (check current URL after navigation)

- Path contains: `/sign-in`, `/login`, `/signin`, `/auth`
- Domain contains: `accounts.clerk.dev`, `clerk.`
- URL contains: `accounts.google.com/o/oauth2`

### DOM signals (check via snapshot if URL does not match)

- Page contains a password input field
- Page contains text: "Sign in", "Log in", "Create account"
- Page contains an email/identifier input inside a form

### Decision logic

1. Navigate to target URL, wait for `networkidle`
2. Check URL against patterns above
3. If no URL match, take snapshot and check DOM signals
4. If any signal fires -> enter auth flow
5. If no signals -> not a login page, proceed normally

Auto-detection also applies to **mid-session redirects** (e.g., session expired during exploration).

## Auth State Reuse

### Loading saved state (try first — initial session start only)

Before fresh login **at the start of a session**, check for existing auth state from a previous run:

**agent-browser:**
```bash
if [ -f "{OUTPUT_DIR}/auth-state.json" ]; then
  agent-browser --session {SESSION} state load {OUTPUT_DIR}/auth-state.json
  agent-browser --session {SESSION} reload
  agent-browser --session {SESSION} wait --load networkidle
  agent-browser --session {SESSION} snapshot -i
  # If still on login page -> state is stale, proceed with fresh auth
fi
```

**Use `reload`, not `open`.** The page is already loaded from the initial navigation. `reload` reloads with the newly applied cookies. `open` triggers a full fresh navigation that can race with the state load and drop auth cookies.

**Playwright MCP:** Load cookies/storage state from previous session file, then reload the current page.

If loaded state results in a login page (session expired), discard it and proceed with fresh auth.

### Mid-session expiration (skip saved state)

When a login page redirect is detected **during active exploration** (not at session start), the saved auth state is from the current session that just expired. Loading it will fail — **skip straight to fresh auth** (Clerk/Google/OTP flow). After re-authenticating, save the new state immediately.

Why this happens: The agent spends 30-60+ seconds analyzing snapshots and writing reports between browser navigations. Servers interpret this as inactivity and expire the session, even though the dogfood session is actively running.

### Saving state (after successful login + periodically)

**agent-browser:**
```bash
agent-browser --session {SESSION} state save {OUTPUT_DIR}/auth-state.json
```

Save auth state:
1. **After initial login** — for reuse in future dogfood runs
2. **Every 3-5 pages during exploration** — captures refreshed cookies/tokens so the saved state stays current

**Playwright MCP:** Save browser cookies/storage to the output directory.

## Auth Flow Priority

When a login page is detected, follow this priority:

1. **Saved auth state** -- load and verify (fastest, **initial session start only** — skip during mid-session re-auth)
2. **Clerk email/password form** -- if email/identifier input detected
3. **Google OAuth button** -- if only "Sign in with Google" visible (no email/password form)
4. **OTP/email code** -- ask the user, wait for their response, enter code

## Clerk Email/Password Flow

### agent-browser

```bash
# 1. Snapshot to identify form elements
agent-browser --session {SESSION} snapshot -i

# 2. Fill email/identifier field
agent-browser --session {SESSION} fill @{EMAIL_INPUT_REF} "{TEST_USER_EMAIL}"

# 3. Click Continue/Next (Clerk is multi-step)
agent-browser --session {SESSION} click @{CONTINUE_BUTTON_REF}
agent-browser --session {SESSION} wait --load networkidle

# 4. Snapshot for password step
agent-browser --session {SESSION} snapshot -i

# 5. Fill password
agent-browser --session {SESSION} fill @{PASSWORD_INPUT_REF} "{TEST_USER_PASSWORD}"

# 6. Submit
agent-browser --session {SESSION} click @{SUBMIT_BUTTON_REF}
agent-browser --session {SESSION} wait --load networkidle

# 7. Verify -- URL should no longer match login patterns
agent-browser --session {SESSION} snapshot -i
```

Use `fill` (not `type`) during auth -- speed matters, no video is recording.

### Playwright MCP

1. Fill email: `playwright_fill` on `input[name="identifier"]`, `input[type="email"]`, or `#identifier`
2. Click Continue button
3. Fill password: `playwright_fill` on `input[name="password"]` or `input[type="password"]`
4. Click "Sign in" / Submit button (or `playwright_press_key` Enter)
5. Wait for navigation away from login page

## Google OAuth Flow

For apps where Google Sign-In is the **only** login option (no email/password form visible).

### Detection

After snapshot, look for:
- Button text containing "Sign in with Google" or "Continue with Google"
- Google branded sign-in button (Google logo)
- No visible email/password input fields

### agent-browser

```bash
# 1. Snapshot and identify Google Sign-In button
agent-browser --session {SESSION} snapshot -i

# 2. Click Google Sign-In button
agent-browser --session {SESSION} click @{GOOGLE_BUTTON_REF}
agent-browser --session {SESSION} wait --load networkidle
sleep 2

# 3. Snapshot Google's login page
agent-browser --session {SESSION} snapshot -i

# 4. Fill Google email (look for input type="email" or id="identifierId")
agent-browser --session {SESSION} fill @{GOOGLE_EMAIL_REF} "{TEST_USER_EMAIL}"

# 5. Click Next
agent-browser --session {SESSION} click @{GOOGLE_NEXT_REF}
agent-browser --session {SESSION} wait --load networkidle
sleep 2

# 6. Snapshot for password step
agent-browser --session {SESSION} snapshot -i

# 7. Fill Google password (input type="password" or name="Passwd")
agent-browser --session {SESSION} fill @{GOOGLE_PASSWORD_REF} "{TEST_USER_PASSWORD}"

# 8. Click Next to sign in
agent-browser --session {SESSION} click @{GOOGLE_SUBMIT_REF}
agent-browser --session {SESSION} wait --load networkidle
sleep 3

# 9. Handle consent screen if shown
agent-browser --session {SESSION} snapshot -i
# If "Allow" / "Continue" consent prompt visible, click it

# 10. Verify redirect back to app domain
agent-browser --session {SESSION} snapshot -i
```

### Playwright MCP

1. Click "Sign in with Google" button via `playwright_click`
2. Wait for Google login page
3. Fill email: `playwright_fill` on `input[type="email"]`
4. Click Next
5. Fill password: `playwright_fill` on `input[type="password"]`
6. Click Next
7. Handle consent screen if shown (click Allow/Continue)
8. Wait for redirect back to app

### Google OAuth challenges

| Challenge | Mitigation |
|-----------|------------|
| "Choose an account" screen | Click matching email or "Use another account" |
| Consent screen | Click "Allow" / "Continue" if prompted |
| 2FA on Google account | Inform user: use a test account without 2FA |
| Google blocks automation | Use saved auth state; Google Workspace test accounts are more lenient |
| Popup vs redirect | Clerk typically uses redirect mode; wait for URL to change to `accounts.google.com` |

## Error Handling

| Error | Response |
|-------|----------|
| No credentials in .env.local or env | Report error with `.env.local` setup instructions |
| Invalid credentials (Clerk) | Snapshot shows error text -> report with fix suggestions |
| Invalid credentials (Google) | "Wrong password" shown -> report with fix suggestions |
| 2FA/MFA required | Inform user, suggest disabling 2FA on test account |
| CAPTCHA detected | Inform user: "Log in manually first, then save auth state for reuse" |
| Rate limited | Wait 30s and retry once; if still limited, inform user |
| Auth state stale (session start) | Discard saved state, attempt fresh login |
| Session expired mid-exploration | Skip saved state (same session), do fresh login immediately |
| Login form not recognized | Take screenshot, report: "Could not identify login form" |
