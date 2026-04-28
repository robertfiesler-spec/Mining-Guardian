# Afternoon runbook — 2026-04-27 (paste-along, top to bottom)

Everything below is meant to be pasted into PowerShell **one block at a
time** from `C:\Users\User\Mining-Guardian`. After each block, stop and
read the output before pasting the next.

`MG_DB_PASSWORD` must already be set in your shell. If `$env:MG_DB_PASSWORD`
prints empty, set it first.

---

## Block A — refresh local clone (git)

```powershell
cd C:\Users\User\Mining-Guardian
git status                                  # confirm working tree clean
git checkout main
git pull origin main
git log -1 --oneline                        # should now show a recent main commit
```

If git status shows the three known stowaways
(`core/mining_guardian.py.pre_cr2_backup`, `cr1_verify_report_*.txt`,
`mg_sql_patch.zip`), they are untracked and safe to leave or delete. They
will not block the checkout.

---

## Block B — copy the third migration into the container

```powershell
docker cp `
  C:\Users\User\Mining-Guardian\intelligence-catalog\seed-data\staging_schema.sql `
  mining-guardian-db:/tmp/staging.sql

docker exec mining-guardian-db ls -la /tmp/000_bootstrap.sql /tmp/002_layer2.sql /tmp/staging.sql
```

All three should now be present in the container.

---

## Block C — apply the three migrations (idempotent)

Each command runs inside a single transaction (`-1`) so a failure rolls
that file back cleanly.

```powershell
docker exec -e PGPASSWORD=$env:MG_DB_PASSWORD mining-guardian-db `
  psql -U guardian_admin -d mining_guardian -1 -f /tmp/000_bootstrap.sql

docker exec -e PGPASSWORD=$env:MG_DB_PASSWORD mining-guardian-db `
  psql -U guardian_admin -d mining_guardian -1 -f /tmp/002_layer2.sql

docker exec -e PGPASSWORD=$env:MG_DB_PASSWORD mining-guardian-db `
  psql -U guardian_admin -d mining_guardian -1 -f /tmp/staging.sql
```

Sanity check (the new staging schema must now exist):

```powershell
docker exec -e PGPASSWORD=$env:MG_DB_PASSWORD mining-guardian-db `
  psql -U guardian_admin -d mining_guardian `
  -c "\dn staging"
```

---

## Block D — capture the pre-import baseline

```powershell
docker cp `
  C:\Users\User\Mining-Guardian\mg_import_tool\tools\verify_pre_import.sql `
  mining-guardian-db:/tmp/verify_pre_import.sql

docker exec -e PGPASSWORD=$env:MG_DB_PASSWORD mining-guardian-db `
  psql -U guardian_admin -d mining_guardian `
  -f /tmp/verify_pre_import.sql `
  > D:\MiningGuardian\db-backups\pre-migration\baseline_2026-04-27.txt

Get-Content D:\MiningGuardian\db-backups\pre-migration\baseline_2026-04-27.txt | Select-Object -First 30
```

---

## Block E — backup #2 (post-migration)

```powershell
docker exec -e PGPASSWORD=$env:MG_DB_PASSWORD mining-guardian-db `
  pg_dump -U guardian_admin -d mining_guardian -F c `
  -f /tmp/mg_post_migration_2026-04-27.dump

docker cp mining-guardian-db:/tmp/mg_post_migration_2026-04-27.dump `
  D:\MiningGuardian\db-backups\pre-migration\

Get-ChildItem D:\MiningGuardian\db-backups\pre-migration\ | Format-Table Name, Length
```

You should now see three `.dump` files in that folder:
`mining_guardian_2026-04-13.dump`, `mg_pre_pr_apply_2026-04-27.dump`,
`mg_post_migration_2026-04-27.dump`.

---

## Block F — boot the importer web UI for the test batch

```powershell
cd C:\Users\User\Mining-Guardian\mg_import_tool
.\launch_mg_import.bat
```

The browser will open `http://127.0.0.1:8420`. Log in with the importer
password, fill the connection form (host=`localhost`, port=`5432`,
db=`mining_guardian`, user=`guardian_admin`, password = the same value
that's in `$env:MG_DB_PASSWORD`), click **Test Connection**.

Then drop ONE small `.tgz` from `Documents\Miner Logs` into the upload
zone. Watch the SSE log scroll. We want to see:

- `▶ <archive name>` header
- a sequence of `EXECUTE` messages
- a `Resolver: tier1=N tier2=N unresolved=N` summary line
- exit status `success`

If anything red appears, **stop and report**. We'll diagnose before
committing to the full 131.

---

## Block G — full bulk run (after the test passes)

You can leave the web UI running — the script does not need it. Open a
**second** PowerShell window and:

```powershell
cd C:\Users\User\Mining-Guardian\mg_import_tool
python tools\run_full_import.py `
  --archives-dir "C:\Users\User\Documents\Miner Logs" `
  --pg-host localhost --pg-port 5432 `
  --pg-user guardian_admin --pg-db mining_guardian `
  --log-file D:\MiningGuardian\db-backups\pre-migration\full_import_2026-04-27.log
```

The log streams to your console **and** to the `.log` file on D:. Expect
a few minutes of `[ N/131] OK <name> in X.Xs` lines, then a banner
summary at the bottom.

---

## Block H — capture the post-import snapshot (run this when bulk import finishes)

First pull the corrected `verify_post_import.sql` from origin — the one in
your working tree had two real bugs (orphan-check used a non-existent
`import_id` FK; the D1 block referenced columns that don't exist on
`mg.import_runs`). Both were rewritten while the bulk import was running.

```powershell
cd C:\Users\User\Mining-Guardian
git pull origin mg/pr25-bulk-import-tools                      # picks up commit 36d54d7
git log -1 --oneline mg_import_tool/tools/verify_post_import.sql
```

You should see commit `36d54d7 fix(verify_post_import.sql): orphan-check
joins + mg.import_runs JSONB schema`.

Then run the snapshot:

```powershell
docker cp `
  C:\Users\User\Mining-Guardian\mg_import_tool\tools\verify_post_import.sql `
  mining-guardian-db:/tmp/verify_post_import.sql

docker exec -e PGPASSWORD=$env:MG_DB_PASSWORD mining-guardian-db `
  psql -U guardian_admin -d mining_guardian `
  -f /tmp/verify_post_import.sql `
  > D:\MiningGuardian\db-backups\pre-migration\post_import_2026-04-27.txt

Get-Content D:\MiningGuardian\db-backups\pre-migration\post_import_2026-04-27.txt |
  Select-Object -First 60
```

Then the diff:

```powershell
Compare-Object `
  (Get-Content D:\MiningGuardian\db-backups\pre-migration\baseline_2026-04-27.txt) `
  (Get-Content D:\MiningGuardian\db-backups\pre-migration\post_import_2026-04-27.txt) |
  Format-Table SideIndicator, InputObject -AutoSize |
  Select-Object -First 100
```

What to expect:

- `knowledge.field_log_*` row counts all UP (sometimes by millions for
  `power_samples` and `antminer_autotune`).
- `mg.import_runs` UP by exactly 1 (the new bulk-run summary row).
- `mg.unresolved_models` populated (any non-zero is fine; this is the
  manual review queue).
- `staging.miner_model_proposals` / `manufacturer_proposals` /
  `alias_proposals` populated (PR #15 dual-write evidence).
- `D4: orphan check` — every child table must report `0` orphan_rows.
  Anything non-zero means parent rollback during import — STOP and ping.
- **Unchanged (must match baseline exactly):** `hardware.*`, `ops.*`,
  `firmware.*`, `repair.*`, `facility.*`. These are the catalog tables
  the importer never writes. Any drift here is a bug.

If everything looks right, paste the first 60 lines of
`post_import_2026-04-27.txt` plus the Compare-Object output back here.

---

## Block I — backup #3 (the dump we ship to the Mac Mini)

This is the dump that becomes the customer's database on May 5. Run it
only *after* Block H is clean.

```powershell
docker exec -e PGPASSWORD=$env:MG_DB_PASSWORD mining-guardian-db `
  pg_dump -U guardian_admin -d mining_guardian -F c `
  -f /tmp/mg_post_import_2026-04-27.dump

docker cp mining-guardian-db:/tmp/mg_post_import_2026-04-27.dump `
  D:\MiningGuardian\db-backups\pre-migration\

docker exec mining-guardian-db rm /tmp/mg_post_import_2026-04-27.dump
```

Verify size + integrity:

```powershell
Get-ChildItem D:\MiningGuardian\db-backups\pre-migration\mg_post_import_2026-04-27.dump |
  Format-Table Name, Length, LastWriteTime

# Round-trip header check — exits 0 if the dump is well-formed:
docker cp `
  D:\MiningGuardian\db-backups\pre-migration\mg_post_import_2026-04-27.dump `
  mining-guardian-db:/tmp/verify.dump
docker exec mining-guardian-db pg_restore --list /tmp/verify.dump | Select-Object -First 10
docker exec mining-guardian-db rm /tmp/verify.dump
```

Expect: file size meaningfully larger than the 157 MB pre-migration dump
(the bulk import added millions of rows). The `pg_restore --list` header
should begin with the TOC entries — any error there means a corrupt dump
and we re-run.

Label for handoff: this file IS the Mac Mini install corpus. Do not
overwrite, do not delete, do not modify.

Paste the `Get-ChildItem` output and the first 10 TOC lines back here.

---

## Block J — open PR #25 (agent-driven, no paste required)

Once Block H and Block I are both clean, just say `open PR 25`. The agent
will:

1. Append `docs/SESSION_LOG_2026-04-27_addendum3_skeleton.md` to
   `docs/SESSION_LOG_2026-04-27.md` (with all `TODO_FILL` placeholders
   filled in from the Block H + Block I outputs you pasted).
2. Drop the skeleton file.
3. Commit on `mg/pr25-bulk-import-tools` and push.
4. Open PR #25 against `main` via `gh pr create` — title `Live DB
   re-import (136 archives) — PR #25 + SESSION_LOG addendum #3`, body
   = the addendum text.
5. Drop the `git stash` (which was just the same mg_import.py patch
   that's already on the branch).

No PowerShell from you for Block J — the agent has GitHub credentials
and will run the whole sequence. You'll get the PR URL back to review.

---

That's the entire afternoon path. Stop anywhere it surprises you.
