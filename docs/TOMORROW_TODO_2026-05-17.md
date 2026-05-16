# Tomorrow's TODO — 2026-05-17

## Rob's request (verbatim, 2026-05-16 6:20 PM CDT)

> "No tomorrow I'm, but if you'd like to reference this for tomorrow, please make a note."

In context: Rob asked whether 4-5 weeks of cron findings (scattered across `latest_findings.json` files that get overwritten each run, and across `[BACKGROUND CRON RESULT]` messages in chat scrollback) could be pulled into ONE consolidated file. Answer: yes. He deferred the work to tomorrow.

## What to build tomorrow

**Output file:** `docs/CATALOG_INTAKE_BACKLOG_2026-05-17.md`

**Structure (5 sections):**

1. **New models found (not yet in catalog)** — manufacturer, model name, hashrate, power (W), efficiency (J/TH), cooling, release date, source URL, date found by cron
2. **New firmware releases** — manufacturer, model(s) affected, version string, release date, key changes, source URL
3. **Spec discrepancies to reconcile** — model, current catalog value, conflicting source value(s), source URLs, recommendation
4. **Field reports / failure patterns** — model, observation, source URL
5. **Rumors flagged** — model or claim, source, why flagged as unverified

**Sources to pull from:**

- This chat's full scrollback of `[BACKGROUND CRON RESULT]` messages (Apr 19 → May 16). Most complete history.
- `/home/user/workspace/cron_tracking/4cc981c0/state.json` + `aggregator_watcher/latest_findings.json` (aggregator, latest snapshot)
- `/home/user/workspace/cron_tracking/920d0231/state.json` + `manufacturer_watcher/latest_findings.json` (manufacturer, latest snapshot)
- `/home/user/workspace/cron_tracking/aa676933/` (firmware tracker — has dated `run_20260423_findings.json` + latest)
- `/home/user/workspace/cron_tracking/c8c4678d/` + `community_scanner/latest_findings.json` (community)
- `/home/user/workspace/cron_tracking/ebb3af70/` + `enrichment_sweep/*.csv` (the deleted deep-enrichment cron — kept dated files, ~8 days of history)

**Estimated size:** ~25-35 new models, ~6-8 firmware releases, ~10 spec discrepancies, ~5-8 field reports. One file, ~10-15 KB.

**Commit message suggestion:** `docs: consolidate 4-week catalog intake backlog from cron findings`

## Why this matters

The Field Intelligence Catalog (Postgres, 317 models on PC Docker) has been collecting NOTHING from these crons. Every finding has lived in throwaway JSON or chat scrollback. This file is the bridge — once it's built, the next step is an upsert script that pushes its contents into `hardware.miner_models`, `firmware.firmware_releases`, and `mg.spec_discrepancies`. But tomorrow is just the consolidation pass. Upsert script comes after.

## Status of broader plan

Still applies as written in `docs/SESSION_HANDOFF_2026-04-24.md`:

1. Finish DB (raw_json bug still open, 83-archive batch never ran)
2. Remove OpenClaw + Slack to Bolt
3. Top-down architecture review
4. Full audit
5. Finish installer
6. Mac Mini cutover (it arrived Apr 27, we're 3 weeks behind plan)

This backlog file is a prerequisite for #4 (audit catches "intel-collected-but-not-ingested" as a gap) and #5 (installer should ship with a populated catalog, not an outdated one).

## Reminder for whichever chat picks this up

- Rob has OCD, needs step-by-step, one action per turn
- "Bitcoin SHA-256 ONLY" — filter out anything Scrypt/Kaspa/etc during consolidation
- No autonomous multi-step execution — narrate every tool call before running it
- "from now on its just you" — single agent, no Mac Claude

— Computer, end of day 2026-05-16
