# Mining Guardian — macOS Hybrid `.pkg` Installer

**Branch:** `mg/mac-mini-installer`
**Forked from:** `main` at `5e4f1ee` on 2026-04-28
**Target hardware:** Mac Mini (sealed in box at user's office, 16 GB RAM)
**Target install date:** May 5–9, 2026 (per cutover scope γ)

This directory holds the build inputs, scripts, and resources for the
double-click macOS `.pkg` installer that stands up Mining Guardian on a
fresh Mac Mini.

---

## Locked decisions this installer must honor

The following decisions are locked in `docs/DECISIONS.md` and **must not be
re-litigated** without explicit operator sign-off. They define the shape of
this installer.

### Q1 — Installer shape: Hybrid `~500 MB .pkg` (double-click)

> **NOT** a terminal-driven Rich wizard. The user clicks the `.pkg`, types
> their admin password once, and the installer runs end-to-end with a
> native macOS Installer.app GUI.

Anything in this directory that drifts toward a terminal wizard is wrong.
If you find yourself writing `rich.prompt.Prompt.ask(...)` in here, stop —
that contradicts Q1. The 2026-04-28 attempt to ship terminal-wizard specs
into the repo (PR #28) was caught and closed; the specs only survive in
the `archive/installer-build-20260428` tag for historical reference.

### D-13 — Ollama install-time RAM auto-detection (supersedes D-8)

The installer detects available RAM at install time and chooses the local
LLM model accordingly:

| RAM detected     | Model installed                       |
|------------------|---------------------------------------|
| 16 GB            | `llama3.2:3b`                         |
| 24 GB or more    | `qwen2.5:14b-instruct-q4_K_M`         |

The user may override the auto-selection during install. The Mac Mini in
the box is 16 GB, so the default install path will land on `llama3.2:3b`.

### Cutover scope — Option γ

The Mini replaces **both** the Hostinger VPS (187.124.247.182, Tailscale
100.106.123.83) **and** the ROBS-PC catalog. After successful cutover:

- Cloudflare tunnels move off the VPS to the Mini
- The PC Docker `mining-guardian-db` Postgres is decommissioned (data
  re-imported into the Mini's Postgres first; full backup retained on
  D: drive)
- The Mini becomes the on-site canonical database host **and** the local
  LLM host

### Vision Anchors that constrain the installer

- **Vision Anchor 6:** Bitcoin SHA-256 miners ONLY — installer must not
  ship altcoin scaffolding, Ethereum tooling, or anything non-SHA-256.
- **Vision Anchor 7:** Local-only, no cloud-only operational dependencies
  — every component installed must work with the network unplugged. No
  cloud-only auth, no cloud-only LLMs, no cloud-only databases.

---

## Directory layout

```
installer/macos-pkg/
├── README.md              ← this file (locked-decision quotes)
├── KEYS_AND_SECRETS.md    ← placeholder; real values stay local-only
├── scripts/               ← preinstall / postinstall / RAM-detect shell scripts
└── resources/             ← Distribution.xml, branding artwork, license, intro
```

**Note on build output:** the build script creates a transient `build/`
directory at `make pkg` time. It is **not** tracked in git — the repo-root
`.gitignore` already excludes any `build/` directory, and the signed +
notarized `.pkg` artifact is dropped on the operator's local disk and
distributed out-of-band (USB drive for the May 5 install).

---

## Apple Developer / notarization

Public-facing identifiers (safe to commit, used by `notarytool`):

- **Team ID:** `ARJZ5FYU94`
- **Apple Developer email:** `robfiesler25@gmail.com`
- **Notarization Key ID:** `FPZJ87B3QF`

Private values (Issuer UUID, the `.p8` private key file path, the
notarization password) live **only** at:

```
/Users/BigBobby/Documents/Apple Cert/CREDENTIALS_NOTES.txt
```

Do not copy the private values into this repo. See
`KEYS_AND_SECRETS.md` for the full handling rules.

---

## What goes here vs. what does not

**Goes here:**
- The `Distribution.xml` that describes the `.pkg` to macOS Installer.app
- `preinstall.sh` — RAM detection, dependency checks, refuse-to-install gates
- `postinstall.sh` — Ollama install + correct model pull, Postgres setup,
  systemd-equivalent (launchd) plist drop, first-run baseline scan trigger
- Branding artwork pulled from `branding/` (the welcome screen, logos)
- Localized strings, license text, intro/welcome HTML

**Does NOT go here:**
- The Mining Guardian application code itself — that lives at the repo
  root (`mining_guardian.py`, `core/`, `clients/`, `predictor.py`, etc.)
  and is bundled into the `.pkg` payload at build time, not stored here.
- Postgres database dumps — those live on `D:\MiningGuardian\db-backups\`
  and are pulled at install time (or shipped on a separate USB drive for
  the May 5 install if bandwidth at the office is unreliable).
- Apple Developer secrets — see "Apple Developer / notarization" above.
- Anything Bitcoin-altcoin or cloud-only — see Vision Anchors 6 and 7.

---

## Build pipeline (to be implemented)

The eventual `make pkg` target should:

1. Verify Apple Developer cert + notarization credentials are reachable
2. Run a clean `git status` check (refuse to build with a dirty tree)
3. Stamp the build with the current git SHA + the version from `__version__`
4. Assemble the payload (app code + dependencies, vendored)
5. Sign the payload with the Developer ID Installer cert
6. Submit to Apple notarization via `notarytool`
7. Staple the notarization ticket
8. Drop the final `.pkg` in `build/` with a SHA-256 sidecar
9. Print the install command for the operator

This is **not yet implemented**. First implementation commit will land on
this branch.

---

## References

- `docs/DECISIONS.md` — Q1, D-13, cutover scope γ, Vision Anchors
- `docs/CLAUDE.md` — current architecture, paths, branches, schema
- `docs/SESSION_LOG_2026-04-27.md` — live-DB cutover record (addendum #3)
- `docs/LATENT_BUGS.md` — known unfixed defects (B-3 / B-4 / B-5 are
  installer-relevant — fix or document around before shipping)
- `branding/BRANDING.md` — brand system, logos, hero artwork, Screen 1
- Tag `archive/installer-build-20260428` (`ec7d359`) — historical
  installer-build branch, terminal-wizard era, **do not copy from**
- `KEYS_AND_SECRETS.md` — secret handling rules for this installer
