#!/usr/bin/env python3
"""Precise patch for _ensure_token. Reads file as bytes, finds exact slice, replaces."""

PATH = '/Users/BigBobby/Documents/GitHub/Mining Gaurdian/core/mining_guardian.py'

with open(PATH) as f:
    src = f.read()

# Marker that uniquely identifies the start of the method
START = '    def _ensure_token(self) -> str:\n        """Return a valid workspace token, re-authenticating if needed.\n\n        Tokens expire after ~30 minutes (observed from JWT payload).\n        We re-auth 60 seconds before expiry to avoid mid-scan failures.\n        """'

# Marker that uniquely identifies the end (the return statement followed by blank line and comment)
END = '        return self._ws_token\n\n    # ── Read: WebSocket one-shot fetch ───────────────────────'

start_idx = src.find(START)
end_idx = src.find(END)

if start_idx == -1:
    print("ERROR: start marker not found")
    exit(1)
if end_idx == -1:
    print("ERROR: end marker not found")
    exit(1)

# end_idx points to the start of END marker. We want to replace everything from
# start_idx through (end_idx + len("        return self._ws_token\n")), keeping
# the blank line and "# ── Read..." comment intact.
# So our replacement covers: start_idx -> end_idx + len("        return self._ws_token\n")

end_of_method_idx = end_idx + len('        return self._ws_token\n')

old_method_text = src[start_idx:end_of_method_idx]
print(f"Found method at bytes [{start_idx}:{end_of_method_idx}], length {len(old_method_text)}")

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

        return self._ws_token
'''

new_src = src[:start_idx] + new_method + src[end_of_method_idx:]

with open(PATH, 'w') as f:
    f.write(new_src)

print(f"PATCHED. Old method: {len(old_method_text)} bytes, new: {len(new_method)} bytes")
