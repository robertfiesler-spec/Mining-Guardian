# Keys & Secrets — Installer

**This file is intentionally a placeholder. No secret values live in this
repo, ever.**

Per Vision Anchor 7 (local-only, no cloud-only operational dependencies)
and the project-wide rule that secrets never get committed, every secret
the installer needs is read at build time from the operator's local
machine and **never** stored in git history.

---

## Source of truth

All Apple Developer / notarization secrets for the macOS `.pkg` build
live at exactly one path on the build Mac, outside the repo. The
canonical location is **operator-chosen** — the build script reads the
path from the operator's environment, not from a hardcoded location.
On the current build Mac that path is, by example:

```
/Users/BigBobby/Documents/Apple Cert/CREDENTIALS_NOTES.txt
```

A second developer signing the .pkg from a different home directory
should replace `/Users/BigBobby/...` with `${HOME}/Documents/Apple Cert/...`
or the equivalent on their Mac and update the build environment
accordingly.

That file contains:

- The Apple Developer Issuer UUID (the long `f53661a7-...`-shaped value)
- The `.p8` private key file path
- The notarization App-Specific Password (if used instead of API key)
- The Developer ID Installer cert reference
- Any keychain item names the build script reads from

If that file is lost or the Mac is replaced, regenerate every value from
[appleid.apple.com](https://appleid.apple.com/) and
[App Store Connect → Users and Access → Keys](https://appstoreconnect.apple.com/access/api).
Do **not** restore from a cloud backup of the file unless the cloud
backup is encrypted-at-rest with a key that is itself stored locally
(per Vision Anchor 7).

---

## Public-facing identifiers (safe to commit, already in `README.md`)

These are *not* secrets — Apple expects them to appear in `notarytool`
invocations and build scripts, and they identify the developer publicly:

- **Team ID:** `ARJZ5FYU94`
- **Apple Developer email:** `robfiesler25@gmail.com`
- **Notarization Key ID:** `FPZJ87B3QF`

If you're not sure whether a given value is safe to commit, the rule is:
**if Apple's docs show the value being passed on a command line in
example output, it's a public identifier; otherwise treat it as secret.**

---

## Other secrets the installer touches

### Postgres password (`MG_DB_PASSWORD`)

The live DB password is locked in `docs/DECISIONS.md` as D-1 and is read
from the `MG_DB_PASSWORD` environment variable at runtime. The installer
must:

1. **Generate a fresh password** at install time on the target Mini (do
   not reuse the password from the existing PC Docker container).
2. **Write it to a launchd `EnvironmentVariables` plist** that has
   `0600` permissions and is owned by the service user only.
3. **Print the new password once to the install log**, then refuse to
   re-print it — operator's job to capture it.
4. **Never echo the password to stdout** during `postinstall.sh` —
   `set +x` before any `psql` invocation that uses it.

### GitHub PAT for repo pull

If the installer pulls the repo from GitHub (vs. shipping the source as
part of the `.pkg` payload), it must use a **read-only** PAT scoped to
the `Mining-Guardian` repo only, and the PAT must be entered
interactively during install — not embedded in the `.pkg`.

The cleaner path (and the one we should default to) is to **bundle the
source into the `.pkg` payload at build time** so the installer needs no
GitHub access at all. See `README.md` "Build pipeline" step 4.

---

## What this file is not

- **Not** a secret store. There are no real values here.
- **Not** a backup of `CREDENTIALS_NOTES.txt`. If the Mac is wiped, this
  file does not help you recover.
- **Not** authoritative on what counts as a secret — `docs/DECISIONS.md`
  D-1 and the project-wide gitignore + pre-commit hooks are the
  enforcement layer.

---

## References

- `README.md` (this directory) — Apple Developer / notarization section
- `docs/DECISIONS.md` D-1 — `MG_DB_PASSWORD` handling
- `docs/CLAUDE.md` — Vision Anchor 7 (local-only)
- `/Users/BigBobby/Documents/Apple Cert/CREDENTIALS_NOTES.txt` — local-only
  source of truth (NOT in this repo, NOT in cloud backup)
