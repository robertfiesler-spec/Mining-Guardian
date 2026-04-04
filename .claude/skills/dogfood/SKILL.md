---
name: dogfood
description: Systematically explore and test a web application to find bugs, UX issues, and other problems. Use when asked to "dogfood", "QA", "exploratory test", "find issues", "bug hunt", "test this app/site/platform", or review the quality of a web application. Produces a structured report with full reproduction evidence -- step-by-step screenshots, repro videos, and detailed repro steps for every issue -- so findings can be handed directly to the responsible teams.
---

# Dogfood

Systematically explore a web application, find issues, and produce a report with full reproduction evidence for every finding.

## Setup

Only the **Target URL** is required. Everything else has sensible defaults -- use them unless the user explicitly provides an override.

| Parameter | Default | Example override |
|-----------|---------|-----------------|
| **Target URL** | _(required)_ | `vercel.com`, `http://localhost:3000` |
| **Session name** | Slugified domain (e.g., `vercel.com` -> `vercel-com`) | `--session my-session` |
| **Output directory** | `./dogfood-output/` | `Output directory: /tmp/qa` |
| **Scope** | Full app | `Focus on the billing page` |
| **Authentication** | Auto-detected from `.env.local` | Reads `TEST_USER_EMAIL` and `TEST_USER_PASSWORD` |

If the user says something like "dogfood vercel.com", start immediately with defaults. Do not ask clarifying questions about credentials -- they are read from `.env.local` automatically.

Always use `agent-browser` directly -- never `npx agent-browser`. The direct binary uses the fast Rust client. `npx` routes through Node.js and is significantly slower.

## Workflow

```
1. Initialize    Set up session, output dirs, report file
2. Authenticate  Sign in if needed, save state
3. Orient        Navigate to starting point, take initial snapshot
4. Explore       Systematically visit pages and test features
5. Document      Screenshot + record each issue as found
6. Wrap up       Update summary counts, close session
```

### 1. Initialize

```bash
mkdir -p {OUTPUT_DIR}/screenshots {OUTPUT_DIR}/videos
```

Copy the report template into the output directory and fill in the header fields:

```bash
cp {SKILL_DIR}/templates/dogfood-report-template.md {OUTPUT_DIR}/report.md
```

Start a named session:

```bash
agent-browser --session {SESSION} open {TARGET_URL}
agent-browser --session {SESSION} wait --load networkidle
```

### 2. Authenticate

Read [references/browser-auth.md](references/browser-auth.md) for the complete auth playbook.

Authentication is **automatic**. Before starting, read credentials from `.env.local`:

```bash
TEST_USER_EMAIL=$(grep '^TEST_USER_EMAIL=' .env.local 2>/dev/null | cut -d'=' -f2- | tr -d '"' | tr -d "'")
TEST_USER_PASSWORD=$(grep '^TEST_USER_PASSWORD=' .env.local 2>/dev/null | cut -d'=' -f2- | tr -d '"' | tr -d "'")
```

If no credentials found and the page is a login page, ask the user to set up `.env.local`.

**Login page detection** runs after every navigation. Check:
- URL contains `/sign-in`, `/login`, `/signin`, `/auth`, `clerk`, `accounts.google.com`
- Snapshot shows password inputs or "Sign in" text

**Auth flow priority**:
1. Try loading saved auth state first:
   ```bash
   if [ -f "{OUTPUT_DIR}/auth-state.json" ]; then
     agent-browser --session {SESSION} state load {OUTPUT_DIR}/auth-state.json
     agent-browser --session {SESSION} reload
     agent-browser --session {SESSION} wait --load networkidle
     agent-browser --session {SESSION} snapshot -i
     # If still on login page -> state is stale, proceed with fresh auth
   fi
   ```
   **Use `reload`, not `open`.** The page is already at `{TARGET_URL}` from Step 1. `reload` reloads the current page with the newly loaded cookies. `open` opens a fresh page load that can race with the state load and drop the session.
2. If Clerk email/password form detected -> fill email, click Continue, fill password, submit
3. If only Google Sign-In button visible -> click it, complete Google OAuth flow (fill Google email, Next, password, Next, handle consent)
4. For OTP/email codes: ask the user, wait for their response, enter code

After successful login, **wait for the post-login redirect to fully settle** before doing anything else:

```bash
agent-browser --session {SESSION} wait --load networkidle
sleep 2
# Verify redirect settled — URL should no longer match login patterns
agent-browser --session {SESSION} snapshot -i
# If still on a login page, wait longer and re-check before saving
agent-browser --session {SESSION} state save {OUTPUT_DIR}/auth-state.json
```

**Do NOT call `open` after login.** The login flow already redirects you to an authenticated page. Calling `open` triggers a new page load that races with the session and can drop auth cookies or open a new browser window. If you need a specific page after login, take a snapshot first to confirm auth, then navigate within the existing tab:

```bash
agent-browser --session {SESSION} snapshot -i
# Confirm you are NOT on a login page, then navigate in-tab
agent-browser --session {SESSION} eval "window.location.href = '{DESIRED_URL}'"
agent-browser --session {SESSION} wait --load networkidle
```

**Session keepalive:** Auth tokens and cookies expire based on server-side timeouts. The agent often spends 30-60+ seconds thinking between navigations, which servers interpret as inactivity. To prevent mid-session expiration:

- **Re-save auth state every 3-5 pages** during exploration (Step 4). This captures refreshed cookies/tokens:
  ```bash
  agent-browser --session {SESSION} state save {OUTPUT_DIR}/auth-state.json
  ```
- If a mid-session redirect to a login page is detected, **skip loading saved state and go straight to fresh auth** — the saved state is from the same session that just expired and will not work.

### 3. Orient

Take an initial annotated screenshot and snapshot to understand the app structure:

```bash
agent-browser --session {SESSION} screenshot --annotate {OUTPUT_DIR}/screenshots/initial.png
agent-browser --session {SESSION} snapshot -i
```

Identify the main navigation elements and map out the sections to visit.

### 4. Explore

Read [references/issue-taxonomy.md](references/issue-taxonomy.md) for the full list of what to look for and the exploration checklist.

**Navigation rule: click links, don't `open` URLs.**

Navigate between pages by clicking links and buttons in the current page using `click @{ref}`. Do NOT use `open` to navigate during exploration — `open` can create a new browser window, lose session state, or drop auth cookies. Reserve `open` for the initial page load in Step 1 only.

```bash
# GOOD: click a nav link to go to another page
agent-browser --session {SESSION} click @{NAV_LINK_REF}
agent-browser --session {SESSION} wait --load networkidle

# BAD: using open mid-exploration — can open new window, drop session
agent-browser --session {SESSION} open http://localhost:3000/other-page
```

If you must navigate to a URL that has no clickable link (e.g., a deep-linked page), use `eval` to set `window.location.href` which navigates within the existing tab:

```bash
agent-browser --session {SESSION} eval "window.location.href = '{URL}'"
agent-browser --session {SESSION} wait --load networkidle
```

**Strategy -- work through the app systematically:**

- Start from the main navigation. Visit each top-level section by clicking nav links.
- Within each section, test interactive elements: click buttons, fill forms, open dropdowns/modals.
- Check edge cases: empty states, error handling, boundary inputs.
- Try realistic end-to-end workflows (create, edit, delete flows).
- Check the browser console for errors periodically.

**At each page:**

```bash
agent-browser --session {SESSION} snapshot -i
agent-browser --session {SESSION} screenshot --annotate {OUTPUT_DIR}/screenshots/{page-name}.png
agent-browser --session {SESSION} errors
agent-browser --session {SESSION} console
```

**Every 3-5 pages**, re-save auth state to capture refreshed cookies:

```bash
agent-browser --session {SESSION} state save {OUTPUT_DIR}/auth-state.json
```

**If redirected to a login page mid-exploration:** Do NOT try loading saved auth state — it is from the current session that just expired. Go straight to fresh auth (Step 2, priority 2+). After re-authenticating, save the new state immediately and navigate back to the page you were trying to reach using `eval "window.location.href = '{URL}'"` (not `open`).

Use your judgment on how deep to go. Spend more time on core features and less on peripheral pages. If you find a cluster of issues in one area, investigate deeper.

### 5. Document Issues (Repro-First)

Steps 4 and 5 happen together -- explore and document in a single pass. When you find an issue, stop exploring and document it immediately before moving on. Do not explore the whole app first and document later.

Every issue must be reproducible. When you find something wrong, do not just note it -- prove it with evidence. The goal is that someone reading the report can see exactly what happened and replay it.

**Choose the right level of evidence for the issue:**

#### Interactive / behavioral issues (functional, ux, console errors on action)

These require user interaction to reproduce -- use full repro with video and step-by-step screenshots:

1. **Start a repro video** _before_ reproducing:

```bash
agent-browser --session {SESSION} record start {OUTPUT_DIR}/videos/issue-{NNN}-repro.webm
```

2. **Walk through the steps at human pace.** Pause 1-2 seconds between actions so the video is watchable. Take a screenshot at each step:

```bash
agent-browser --session {SESSION} screenshot {OUTPUT_DIR}/screenshots/issue-{NNN}-step-1.png
sleep 1
# Perform action (click, fill, etc.)
sleep 1
agent-browser --session {SESSION} screenshot {OUTPUT_DIR}/screenshots/issue-{NNN}-step-2.png
sleep 1
# ...continue until the issue manifests
```

3. **Capture the broken state.** Pause so the viewer can see it, then take an annotated screenshot:

```bash
sleep 2
agent-browser --session {SESSION} screenshot --annotate {OUTPUT_DIR}/screenshots/issue-{NNN}-result.png
```

4. **Stop the video:**

```bash
agent-browser --session {SESSION} record stop
```

5. Write numbered repro steps in the report, each referencing its screenshot.

#### Static / visible-on-load issues (typos, placeholder text, clipped text, misalignment, console errors on load)

These are visible without interaction -- a single annotated screenshot is sufficient. No video, no multi-step repro:

```bash
agent-browser --session {SESSION} screenshot --annotate {OUTPUT_DIR}/screenshots/issue-{NNN}.png
```

Write a brief description and reference the screenshot in the report. Set **Repro Video** to `N/A`.

---

**For all issues:**

1. **Append to the report immediately.** Do not batch issues for later. Write each one as you find it so nothing is lost if the session is interrupted.

2. **Increment the issue counter** (ISSUE-001, ISSUE-002, ...).

### 6. Wrap Up

Aim to find **5-10 well-documented issues**, then wrap up. Depth of evidence matters more than total count -- 5 issues with full repro beats 20 with vague descriptions.

After exploring:

1. Re-read the report and update the summary severity counts so they match the actual issues. Every `### ISSUE-` block must be reflected in the totals.
2. Close the session:

```bash
agent-browser --session {SESSION} close
```

3. Tell the user the report is ready and summarize findings: total issues, breakdown by severity, and the most critical items.

## Guidance

- **Repro is everything.** Every issue needs proof -- but match the evidence to the issue. Interactive bugs need video and step-by-step screenshots. Static bugs (typos, placeholder text, visual glitches visible on load) only need a single annotated screenshot.
- **Don't record video for static issues.** A typo or clipped text doesn't benefit from a video. Save video for issues that involve user interaction, timing, or state changes.
- **For interactive issues, screenshot each step.** Capture the before, the action, and the after -- so someone can see the full sequence.
- **Write repro steps that map to screenshots.** Each numbered step in the report should reference its corresponding screenshot. A reader should be able to follow the steps visually without touching a browser.
- **Be thorough but use judgment.** You are not following a test script -- you are exploring like a real user would. If something feels off, investigate.
- **Write findings incrementally.** Append each issue to the report as you discover it. If the session is interrupted, findings are preserved. Never batch all issues for the end.
- **Never delete output files.** Do not `rm` screenshots, videos, or the report mid-session. Do not close the session and restart. Work forward, not backward.
- **Never read the target app's source code.** You are testing as a user, not auditing code. Do not read HTML, JS, or config files of the app under test. All findings must come from what you observe in the browser.
- **Check the console.** Many issues are invisible in the UI but show up as JS errors or failed requests.
- **Test like a user, not a robot.** Try common workflows end-to-end. Click things a real user would click. Enter realistic data.
- **Type like a human.** When filling form fields during video recording, use `type` instead of `fill` -- it types character-by-character. Use `fill` only outside of video recording when speed matters.
- **Pace repro videos for humans.** Add `sleep 1` between actions and `sleep 2` before the final result screenshot. Videos should be watchable at 1x speed -- a human reviewing the report needs to see what happened, not a blur of instant state changes.
- **Be efficient with commands.** Batch multiple `agent-browser` commands in a single shell call when they are independent (e.g., `agent-browser ... screenshot ... && agent-browser ... console`). Use `agent-browser --session {SESSION} scroll down 300` for scrolling -- do not use `key` or `evaluate` to scroll.

## References

| Reference | When to Read |
|-----------|--------------|
| [references/issue-taxonomy.md](references/issue-taxonomy.md) | Start of session -- calibrate what to look for, severity levels, exploration checklist |
| [references/browser-auth.md](references/browser-auth.md) | When app requires authentication -- credential loading, login detection, Clerk/Google flows |

## Templates

| Template | Purpose |
|----------|---------|
| [templates/dogfood-report-template.md](templates/dogfood-report-template.md) | Copy into output directory as the report file |
