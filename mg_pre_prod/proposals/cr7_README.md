# CR-7 — Hardcoded Password Purge (DRAFT, do not apply yet)

**Status:** Patcher script ready and validated. **NOT for application until production
DB password is rotated.**

**Branch:** Future branch `hotfix/cr-7-password-purge-2026-XX-XX`. Do NOT branch
until rotation is done.

## Why this exists

The GitHub repo `robertfiesler-spec/Mining-Guardian` is **PUBLIC** and contains the
literal string `MiningGuardian2026!` in 30+ places across 10 files on `main` HEAD.
Anyone with internet access can read the production DB password. Removing it from
HEAD does NOT remove it from history — only password rotation can stop the leak.

## What the patcher does (`cr7_password_purge.py`)

Validated via dry-run + apply against a fresh `origin/main` clone. All checks pass:
- ✅ Removes literal from 5 code files (30 occurrences)
- ✅ Inserts `_require_db_password()` helper into `mg_import.py` after first import block
- ✅ Patched files compile cleanly (`python3 -m py_compile`)
- ✅ Idempotent (re-running is a no-op)

| File | Sites | Strategy |
|---|---|---|
| `mg_import_tool/mg_import.py` | 26 | Helper function + 7 regex patterns including HTML form value and JS fallback |
| `intelligence-catalog/catalog-api/catalog_api.py` | 1 | Fail-fast: raise if `DB_PASSWORD` env var missing |
| `scripts/migrate_to_postgres.py` | 1 | `os.environ['MG_DB_PASSWORD']` (KeyError if unset) |
| `intelligence-catalog/catalog-api/.env.example` | 1 | Replace with `CHANGE_ME_BEFORE_DEPLOY` |
| `intelligence-catalog/docker-compose.yml` | 1 | `${POSTGRES_PASSWORD:?...}` env interpolation |

## What the patcher does NOT do (manual cleanup needed)

These are documentation files. Patcher leaves them alone so the code commit is clean
and reviewable. Do these in a **separate doc-only commit** after the code change lands:

- `intelligence-catalog/deploy.ps1` (2 sites — connection-string examples)
- `mg_import_tool/README.md` (4 sites — usage docs)
- `docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md` (3 sites)
- `docs/SESSION_HANDOFF_2026-04-24.md` (3 sites)
- `NEXT_SESSION.md` (1 site)

Recommended replacement: `<DB_PASSWORD>` placeholder with note: "see VPS env file."

## Required execution order

**DO NOT execute steps out of order.** Each step assumes the previous succeeded.

1. **Pick a maintenance window** when scan loop downtime is acceptable (~3 min).
2. **Generate a new strong DB password** (e.g. `openssl rand -base64 32`).
3. **On the Postgres host (VPS, post-rename, path = `/root/Mining-Guardian/`):**
   ```bash
   sudo -u postgres psql -c "ALTER USER guardian_admin WITH PASSWORD '<new>';"
   sudo -u postgres psql -c "ALTER USER guardian_app WITH PASSWORD '<new>';"
   ```
   (If only one role is in use, skip the unused one.)
4. **Update VPS service env.** Either via systemd `Environment=` directives or a
   shared env file sourced by `EnvironmentFile=`. The 8 services need `MG_DB_PASSWORD`
   (and any catalog-api needs `DB_PASSWORD`).
5. **Restart all 8 services** (one at a time, watch journal for connection errors):
   ```bash
   for s in mining-guardian mining-guardian-alerts approval-api dashboard-api \
            intelligence-report overnight-automation slack-commands slack-listener; do
     systemctl restart "$s"
     sleep 5
     systemctl is-active "$s" || echo "FAILED: $s"
   done
   ```
6. **Verify connectivity** by running the smoke test:
   ```bash
   bash /root/Mining-Guardian/mg_pre_prod/proposals/post_cr4_smoke_test.sh
   ```
7. **Now (and only now) apply the code patch:**
   ```bash
   cd /home/user/workspace/Mining-Guardian   # or local dev clone
   git checkout main && git pull
   git checkout -b hotfix/cr-7-password-purge-$(date +%Y-%m-%d)
   python3 mg_pre_prod/proposals/cr7_password_purge.py --apply
   git add -A && git commit -m "cr-7: purge hardcoded DB password from code (rotated $(date +%Y-%m-%d))"
   git push origin hotfix/cr-7-password-purge-$(date +%Y-%m-%d)
   ```
   Open a PR. Merge it.
8. **Manual doc cleanup** in a second PR.
9. **Optional but recommended:** scrub git history with `git-filter-repo` or BFG.
   This is the only way to fully remove the literal from public history. Coordinate
   carefully — rewrites history, requires force-push, breaks existing clones.

## What can go wrong

| Failure mode | What it looks like | Fix |
|---|---|---|
| Patch applied before rotation | Services connect with old (compromised) password and keep working — you've achieved nothing security-wise | Rotate first, then patch. |
| Env var not propagated to systemd | Service fails to start with `RuntimeError: DB_PASSWORD env var is required` or `KeyError: 'MG_DB_PASSWORD'` | Check `systemctl cat <svc>` — confirm `Environment=` or `EnvironmentFile=`. |
| Patcher misses a site in code | Verify step at end of patcher reports "literal fully removed" | If literal still present, file an issue and add a regex pattern to `patch_mg_import`. |
| HTML form/JS UI breaks | Login form requires manual entry now (intentional) | Document for users that they must enter the DB password into the UI. |

## Decision the patcher made: HTML form default

`mg_import_tool/mg_import.py:5392` has `<input type="password" id="dbPass" value="MiningGuardian2026!">`
and JS at line 5610 with `|| 'MiningGuardian2026!'` fallback. Patcher replaces these
with `value=""` and removes the JS fallback. The user-facing impact: the import
tool's web UI will now have an empty password field by default. Users must type
the password each time. This is the correct security posture (the fallback was
the entire problem). Document this in the import tool README when you do the doc
cleanup commit.

## Validation already done

```
$ python3 cr7_password_purge.py --apply --repo-root /tmp/cr7_main

[patch] mg_import_tool/mg_import.py — 26 occurrence(s) removed
[patch] intelligence-catalog/catalog-api/catalog_api.py — 1 occurrence(s) removed
[patch] scripts/migrate_to_postgres.py — 1 occurrence(s) removed
[patch] intelligence-catalog/catalog-api/.env.example — 1 occurrence(s) removed
[patch] intelligence-catalog/docker-compose.yml — 1 occurrence(s) removed
Files changed: 5
Verification: literal fully removed from all 5 patched files.

$ python3 -m py_compile mg_import.py catalog_api.py migrate_to_postgres.py
(no errors)

$ python3 cr7_password_purge.py --apply --repo-root /tmp/cr7_main   # re-run
Files changed: 0   ← idempotent
```
