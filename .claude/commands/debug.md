---
suggest_when:
  - signal: file_extension
    value: ".ts"
    min_edits: 5
    cooldown: 30
    message: "Many edits to the same area — `/debug` offers structured hypothesis-driven debugging"
---
# Debug

Systematic hypothesis-driven debugging workflow. Form hypotheses, instrument code, test, and eliminate until root cause is found.

## Your Task

Guide the user through a structured debugging process that mirrors how expert debuggers work: observe, hypothesize, test, eliminate, repeat.

$ARGUMENTS

## Step 0: Detect Flags

Check `$ARGUMENTS` for flags. If **no flags detected**, present options before proceeding:

> **How should we debug?**
>
> | Option | Flag | Best for |
> |--------|------|----------|
> | **Structured** (default) | _(none)_ | Complex or unfamiliar bugs — full hypothesis workflow |
> | **Quick** | `--quick` | Obvious bugs — typos, clear error messages, simple null checks |
> | **From error** | `--from-error "msg"` | You have a specific error message to trace |
> | **From test** | `--from-test name` | A specific test is failing |
>
> Add `--verbose` to any mode for detailed reasoning at each step.
>
> Which mode? (or just describe the bug and I'll pick)

If the user describes the bug inline (e.g., `/debug the settings page crashes`), infer the best mode:
- If the description includes an error message → treat as `--from-error`
- If the description references a test name → treat as `--from-test`
- If the bug sounds trivial (typo, missing import) → use `--quick`
- Otherwise → use structured (default)

## Philosophy

**Debugging is a scientific process, not guesswork.**

- Form hypotheses BEFORE making changes
- Test ONE hypothesis at a time
- Let evidence guide you, not intuition
- Document what you learn for future debugging

## Step 1: Gather Bug Information

Ask the user for (or extract from context):

```markdown
## Bug Report

**What's happening?**
[Description of the bug]

**What should happen?**
[Expected behavior]

**How do you trigger it?**

1. [Step 1]
2. [Step 2]
3. [Bug occurs]

**Error messages/logs:**
```

[Any error output, stack traces, console logs]

```

**When did it start?**
- [ ] Always been broken
- [ ] After a specific change (which?)
- [ ] Intermittent/flaky

**Environment:**
- Browser/Runtime: [e.g., Chrome 120, Node 20]
- OS: [e.g., macOS 14.2]
- Relevant versions: [e.g., React 18, Next.js 14]
```

## Step 2: Reproduce the Bug

**CRITICAL**: Before hypothesizing, confirm you can reproduce the bug.

```bash
# Run the repro steps
# Observe the actual behavior
# Capture any error output
```

If you cannot reproduce:

- Ask for more specific steps
- Check environment differences
- Consider if it's intermittent (race condition, timing, state-dependent)

**Output**:

```markdown
## Reproduction Confirmed

**Repro command**: `pnpm dev` then navigate to /settings
**Observed**: Error "Cannot read property 'email' of undefined"
**Stack trace points to**: `src/components/UserSettings.tsx:42`
```

## Step 3: Form Hypotheses

Based on the bug and your codebase knowledge, form 2-4 hypotheses about the root cause.

**Good hypotheses are:**

- Specific and testable
- Based on the error location and message
- Ordered by likelihood

```markdown
## Hypotheses

| #   | Hypothesis                                                      | Likelihood | How to Test                                  |
| --- | --------------------------------------------------------------- | ---------- | -------------------------------------------- |
| H1  | User object is null when component mounts before auth completes | High       | Add console.log to check user state on mount |
| H2  | API returns malformed user object missing email field           | Medium     | Log API response, check network tab          |
| H3  | Race condition between auth state and route guard               | Medium     | Add timestamps to auth flow logs             |
| H4  | Cache returning stale/incomplete user data                      | Low        | Clear cache, check cache contents            |

**Starting with**: H1 (most likely based on "undefined" error)
```

### Hypothesis Generation Tips

**For "undefined" errors:**

- Data not loaded yet (async timing)
- Data doesn't exist (null/undefined from API)
- Wrong property path (typo, changed schema)
- Scope issue (variable shadowing, closure)

**For "unexpected behavior" (no error):**

- State not updating (stale closure, missing dependency)
- Wrong conditional logic (off-by-one, edge case)
- Event handler not firing (binding, propagation)
- CSS/rendering issue (z-index, display, overflow)

**For "intermittent" bugs:**

- Race condition (async ordering)
- Memory/state leak (accumulating state)
- External dependency (API, network, time)
- Uncontrolled input (user timing, random data)

## Step 4: Instrument Code

Add targeted logging/debugging code to test the CURRENT hypothesis.

**Instrumentation Rules:**

1. Add MINIMAL instrumentation - just enough to test the hypothesis
2. Make logs identifiable - prefix with `[DEBUG H1]`
3. Include timestamps for timing issues
4. Log both entry AND exit of suspect functions
5. Capture relevant state/variables

```typescript
// Example instrumentation for H1: User null on mount
console.log("[DEBUG H1] UserSettings mounting, user:", user);
console.log("[DEBUG H1] Auth state:", authState);

useEffect(() => {
  console.log("[DEBUG H1] useEffect running, user:", user);
  return () => console.log("[DEBUG H1] useEffect cleanup");
}, [user]);
```

**For different bug types:**

```typescript
// Timing issues - add timestamps
console.log(`[DEBUG H1] ${Date.now()} - Auth started`);
console.log(`[DEBUG H1] ${Date.now()} - User loaded`);

// State issues - log before/after
console.log("[DEBUG H1] State BEFORE:", JSON.stringify(state));
// ... operation ...
console.log("[DEBUG H1] State AFTER:", JSON.stringify(state));

// API issues - log request/response
console.log("[DEBUG H1] API Request:", { url, params });
console.log("[DEBUG H1] API Response:", response);

// Event issues - confirm handler fires
console.log("[DEBUG H1] Click handler called with:", event.target);
```

**Show the user what you're adding:**

````markdown
## Instrumentation Added

**Testing**: H1 - User null on mount

**Files modified**:

- `src/components/UserSettings.tsx:38-45` - Added mount logging

**To run**:

```bash
pnpm dev
# Navigate to /settings
# Check browser console for [DEBUG H1] logs
```
````

**Looking for**: Whether `user` is undefined when component mounts

````

## Step 5: Execute and Observe

Run the instrumented code and capture results.

```bash
# Terminal: Run the app
pnpm dev

# Or run specific test
pnpm test src/components/UserSettings.test.tsx

# Or run e2e
pnpm e2e --headed
````

**Capture the output:**

```markdown
## Observation Results

**Hypothesis tested**: H1 - User null on mount

**Console output**:
```

[DEBUG H1] UserSettings mounting, user: undefined
[DEBUG H1] Auth state: { isLoading: true, user: null }
[DEBUG H1] useEffect running, user: undefined
[DEBUG H1] UserSettings mounting, user: { id: '123', email: 'test@example.com' }

```

**Analysis**:
Component mounts TWICE - first with undefined user (while auth loading),
second with valid user. Error occurs on first mount.

**Hypothesis H1**: ✅ CONFIRMED - User is undefined on initial mount
```

## Step 6: Analyze and Decide

Based on observations, update your hypothesis status:

| Status          | Meaning                                          | Next Action              |
| --------------- | ------------------------------------------------ | ------------------------ |
| ✅ CONFIRMED    | Evidence supports this is the root cause         | Proceed to fix           |
| ❌ ELIMINATED   | Evidence contradicts hypothesis                  | Test next hypothesis     |
| 🔄 REFINED      | Partially correct, need more specific hypothesis | Refine and re-test       |
| ❓ INCONCLUSIVE | Not enough evidence                              | Add more instrumentation |

```markdown
## Hypothesis Status Update

| #   | Hypothesis                 | Status        | Evidence                                            |
| --- | -------------------------- | ------------- | --------------------------------------------------- |
| H1  | User null on mount         | ✅ CONFIRMED  | Console shows undefined on first render             |
| H2  | API returns malformed data | ❌ ELIMINATED | API response is correct when it arrives             |
| H3  | Race condition             | 🔄 REFINED    | It's a timing issue but simpler than race condition |
| H4  | Cache issue                | ❌ ELIMINATED | Not using cache for this data                       |

**Root cause identified**: Component renders before auth state is ready.
**Proceeding to**: Fix
```

### If No Hypothesis Confirmed

If all hypotheses eliminated:

1. Review the evidence collected
2. Form NEW hypotheses based on what you learned
3. Return to Step 3

```markdown
## New Hypotheses (Round 2)

Based on Round 1 findings, the bug is NOT in [X, Y, Z].

New hypotheses:
| # | Hypothesis | Likelihood | How to Test |
|---|------------|------------|-------------|
| H5 | ... | ... | ... |
```

## Step 7: Implement Fix

Once root cause is confirmed, implement a targeted fix.

**Fix should:**

- Address the ROOT CAUSE, not symptoms
- Be minimal - don't refactor unrelated code
- Include defensive coding where appropriate
- Not introduce new bugs

````markdown
## Fix Implementation

**Root cause**: Component accesses user.email before user is loaded

**Fix approach**: Add loading state check before rendering user data

**Changes**:

```typescript
// Before (broken)
export function UserSettings() {
  const { user } = useAuth();
  return <div>{user.email}</div>; // 💥 Crashes if user undefined
}

// After (fixed)
export function UserSettings() {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return <LoadingSpinner />;
  }

  if (!user) {
    return <Redirect to="/login" />;
  }

  return <div>{user.email}</div>; // ✅ Safe - user guaranteed
}
```
````

````

## Step 8: Verify Fix

Confirm the fix works and doesn't introduce regressions.

```bash
# 1. Reproduce original bug - should be fixed
pnpm dev
# Navigate to /settings - no more error

# 2. Run existing tests
pnpm test

# 3. Run type check
pnpm typecheck

# 4. If applicable, run e2e
pnpm e2e
````

```markdown
## Verification Results

**Original bug**: ✅ Fixed - No error on /settings page
**Test suite**: ✅ All tests pass
**Type check**: ✅ No errors
**Manual testing**: ✅ Tested login → settings flow

**Ready to**: Clean up instrumentation and commit
```

## Step 9: Clean Up

Remove all debugging instrumentation before committing.

```bash
# Search for debug logs
grep -r "DEBUG H" src/

# Remove all instrumentation
# (Show diff of removals)
```

```markdown
## Cleanup Complete

**Removed**:

- `src/components/UserSettings.tsx:38-45` - Debug console.logs

**Final state**: Code is clean, fix is in place
```

## Step 10: Document Learnings (Optional but Recommended)

If this bug represents a pattern that could recur, suggest `/learn`:

```markdown
## Learning Opportunity

This bug pattern (accessing properties before data loads) is common.

**Suggest running `/learn` to document**:

- "Always check loading state before accessing async data"
- "Components that depend on auth should handle the loading state"

Would you like me to run `/learn` to prevent similar bugs?
```

---

## Quick Debug Mode (`--quick`)

For simple bugs, skip the formal process:

```markdown
## Quick Debug

**Bug**: [one-line description]
**Likely cause**: [immediate hypothesis]
**Checking**: [what to look at]

[Immediately investigate and fix]
```

Use `--quick` for:

- Obvious typos or syntax errors
- Simple null checks
- Clear error messages pointing to exact location
- Bugs you've seen before

---

## Arguments

| Argument                  | Description                                    |
| ------------------------- | ---------------------------------------------- |
| `--quick`                 | Skip formal hypothesis process for simple bugs |
| `--from-error [message]`  | Start with an error message to analyze         |
| `--from-test [test-name]` | Start from a failing test                      |
| `--verbose`               | Show detailed reasoning at each step           |

## Keyboard Shortcuts (During Debug Session)

| Key | Action                           |
| --- | -------------------------------- |
| `h` | Add new hypothesis               |
| `t` | Test current hypothesis          |
| `e` | Eliminate hypothesis             |
| `c` | Confirm hypothesis as root cause |
| `f` | Proceed to fix                   |
| `r` | Reset and start over             |

## Integration with Other Commands

| Scenario                          | Command                                      |
| --------------------------------- | -------------------------------------------- |
| Bug becomes complex feature fix   | `/create-plan --debug` to create plan        |
| Need to understand codebase first | `@architect` for system overview             |
| Multiple related bugs             | Create tracking issue, debug each            |
| Performance bug                   | Use browser DevTools profiler, then `/debug` |

## Common Debugging Patterns

### Pattern: "Works locally, fails in CI/prod"

**Hypotheses to consider:**

- Environment variables missing/different
- Node/npm version differences
- Database state differences
- Timezone/locale differences
- File system case sensitivity (Linux vs macOS)

### Pattern: "Works sometimes, fails randomly"

**Hypotheses to consider:**

- Race condition (async ordering)
- Uninitialized state on fast navigation
- Cache inconsistency
- External service flakiness
- Time-dependent logic

### Pattern: "Used to work, now broken"

**Hypotheses to consider:**

- Recent code change (`git log`, `git bisect`)
- Dependency update (`git diff package.json`)
- Environment change (Node version, env vars)
- External API change
- Data schema change

### Pattern: "Only fails with specific data"

**Hypotheses to consider:**

- Edge case not handled (empty, null, special chars)
- Data type mismatch (string vs number)
- Encoding issue (Unicode, UTF-8)
- Size/length limit exceeded
- Invalid data from source

---

## Example Debug Session

```markdown
## Debug Session: Settings page crash

### Step 1: Bug Report

- **What's happening**: Error "Cannot read property 'email' of undefined" on /settings
- **Expected**: Settings page loads with user info
- **Repro**: Login → Click Settings in nav → Error
- **Error**: TypeError at UserSettings.tsx:42

### Step 2: Reproduction

✅ Reproduced - Error occurs consistently after login

### Step 3: Hypotheses

| #   | Hypothesis                      | Likelihood |
| --- | ------------------------------- | ---------- |
| H1  | User null before auth completes | High       |
| H2  | API returning bad data          | Medium     |

### Step 4: Instrumentation

Added console.log to UserSettings.tsx for user state on mount

### Step 5: Observation
```

[DEBUG H1] user: undefined (first mount)
[DEBUG H1] user: {id: '123', email: '...'} (second mount)

```

### Step 6: Analysis
H1 ✅ CONFIRMED - Component mounts before auth ready

### Step 7: Fix
Added loading state check before accessing user properties

### Step 8: Verify
✅ Bug fixed, all tests pass

### Step 9: Cleanup
Removed debug console.logs

### Result: RESOLVED
Root cause: Missing loading state handling
Fix: Added isLoading check with spinner fallback
```

---

## Related Commands

| Command                 | Use                                     |
| ----------------------- | --------------------------------------- |
| `/create-plan --debug`  | When bug fix needs a full plan          |
| `/verify`               | Quick lint/type/test check              |
| `/learn`                | Document debugging lessons              |
| `@build-error-resolver` | For build/lint/type errors specifically |

---

_Debugging is twice as hard as writing code. If you write code as cleverly as possible, you are by definition not smart enough to debug it. — Brian Kernighan_

## Suggested Next

- `/verify` — run lint, typecheck, and tests after the fix is applied
- `/create-commit` — commit the fix once verified
- `/pre-pr-check` — full pre-PR validation before merging
