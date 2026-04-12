#!/usr/bin/env python3
"""Patch _ensure_token in mining_guardian.py to fix the AMS auth re-acquisition bug.

Root cause: when the workspace token expires in a long-running process, the
session cookie jar still contains the old workspace token. _login() writes a
new user_token cookie but does not clear the stale workspace cookie. The next
call to _select_workspace() may then send the stale workspace cookie alongside
the new Bearer header, which AMS rejects with HTTP 400.

Fix:
  1. Clear the session cookie jar before every re-auth
  2. On any failure during re-auth, reset _ws_token to None so the NEXT call
     attempts a fresh login rather than returning the stale cached token
  3. Add explicit retry on the workspace selection step
"""

import re

PATH = '/Users/BigBobby/Documents/GitHub/Mining Gaurdian/core/mining_guardian.py'

with open(PATH) as f:
    src = f.read()

# Find the existing _ensure_token method
old_method = '''    def _ensure_token(self) -> str:
        """Return a valid workspace token, re-authenticating if needed.

        Tokens expire after ~30 minutes (observed from JWT payload).
        We re-auth 60 seconds before expiry to avoid mid-scan failures.
        """
        now = datetime.now(timezone.utc)
        if self._ws_token and self._token_expiry and now < self._token_expiry:
            return self._ws_token

        user_token   = self._login()
        ws_token     = self._select_workspace(user_token)
        self._ws_token     = ws_token

        # Parse expiry from JWT payload (middle segment, base64-encoded JSON)
        try:
            import base64
            payload_b64 = ws_token.split(".")[1]
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            payload = json.loads(base64.b64decode(payload_b64))
            exp = payload.get("exp")
            if exp:
                self._token_expiry = datetime.fromtimestamp(exp, tz=timezone.utc) - timedelta(seconds=60)
        except Exception:
            # If we can't parse expiry, refresh every 25 minutes to be safe
            self._token_expiry = now + timedelta(minutes=25)

        return self._ws_token'''

new_method = '''    def _ensure_token(self) -> str:
        """Return a valid workspace token, re-authenticating if needed.

        Tokens expire after ~30 minutes (observed from JWT payload).
        We re-auth 60 seconds before expiry to avoid mid-scan failures.

        Bug fix (Apr 8 2026): long-running processes (overnight-automation,
        alert-listener) were getting HTTP 400 from select_workspace when the
        token expired. Root cause: stale session cookies were colliding with
        the new Bearer header during re-auth. Fix: clear the cookie jar before
        every re-auth, and on failure, reset _ws_token so the next call retries
        from scratch instead of returning the stale cached value.
        """
        now = datetime.now(timezone.utc)
        if self._ws_token and self._token_expiry and now < self._token_expiry:
            return self._ws_token

        # CRITICAL: clear the cookie jar before re-auth so stale workspace
        # tokens from a previous expired session do not interfere with the
        # new login + select_workspace flow.
        self.session.cookies.clear()

        try:
            user_token = self._login()
            ws_token   = self._select_workspace(user_token)
        except Exception as e:
            # Hard-reset cached state so the next call re-attempts fresh
            self._ws_token = None
            self._token_expiry = None
            self.session.cookies.clear()
            logger.error("AMS re-auth failed: %s — cleared cached token", e)
            raise

        self._ws_token = ws_token

        # Parse expiry from JWT payload (middle segment, base64-encoded JSON)
        try:
            import base64
            payload_b64 = ws_token.split(".")[1]
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            payload = json.loads(base64.b64decode(payload_b64))
            exp = payload.get("exp")
            if exp:
                self._token_expiry = datetime.fromtimestamp(exp, tz=timezone.utc) - timedelta(seconds=60)
        except Exception:
            # If we can't parse expiry, refresh every 25 minutes to be safe
            self._token_expiry = now + timedelta(minutes=25)

        return self._ws_token'''

if old_method not in src:
    print("ERROR: could not find existing _ensure_token method to replace")
    print("Searching for partial matches...")
    for line in src.split("\n"):
        if "_ensure_token" in line:
            print(f"  {line}")
    exit(1)

src = src.replace(old_method, new_method)
with open(PATH, 'w') as f:
    f.write(src)

print("PATCHED _ensure_token in mining_guardian.py")
print(f"  - Added cookies.clear() before re-auth")
print(f"  - Added exception handling that resets cached token on failure")
print(f"  - Added defensive cookies.clear() in failure path")
