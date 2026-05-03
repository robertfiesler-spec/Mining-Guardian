# Handoff for the new chat — 2026-05-04 onward

## STOP. Read this in full before doing anything.

You are an AI assistant continuing the Mining Guardian project. The previous session was
ended on 2026-05-03 because of three days of session-continuity protocol failures,
documented in this file. You are walking into a project that has had three failed
.pkg releases (v1.0.0, v1.0.1, v1.0.2) and is now committed to v1.0.3 as the build
that finally delivers the customer-experience vision.

The operator (Rob) is paying credits for every action. He has explicitly said he is
considering canceling the service if quality does not improve. Treat that as a hard
constraint: every action must produce real value, no redundant subagents, no
re-deciding things already locked.

## STEP 1 — Required reading (in order, no skipping)

1. `docs/PROGRAM_STATE.md` — full state of program. THE cold-start reference.
2. `docs/DECISIONS.md` — D-1 through D-20. Especially D-13 through D-20.
3. `docs/audits/PKG_AUDIT_v1.0.2_FINDINGS_2026-05-03.md` — why v1.0.2 .pkg is broken.
4. `docs/INSTALL_PATHS_2026-05-03.md` — the canonical install-paths doc.
5. `docs/handoffs/HANDOFF_2026-05-03.md` — yesterday's full handoff including EOD.
6. `git log --oneline -20` on main — confirm last SHA matches end of HANDOFF_2026-05-03.
7. `gh pr list --state all --limit 10` — confirm no surprise merges.

## STEP 2 — Confirm context in chat

Before proposing ANY work, post in chat a brief confirmation that you have read all 6
items above. Do not list bullet summaries — the operator has read these. Just confirm.

## STEP 3 — First action: v1.0.3 discovery, no code

The first work to do is discovery of three things:

1. Does the existing scanner / intelligence code write pending approvals to a Postgres
   table or JSON file? Or are approvals only in Slack today? Grep:
   `grep -rn "approval\|pending_action\|live_action_queue" core/ intelligence/ clients/`.
2. What does the Grafana "Live Action Queue" panel at
   `grafana.fieslerfamily.com/d/llm_learning_001` actually do today? It DISPLAYS a queue
   ("No pending actions — system is running autonomously" was the latest screenshot).
   Is the Approve/Deny interactivity wired up, or is it display-only? The operator
   does not know — the discovery task answers this so D-19 console scope is grounded.
3. What does `mg_import_tool/` actually do today? It stays with the operator forever
   per D-20, but v1.0.3 needs to confirm it is not bundled into the customer .pkg.

Output of discovery: a short markdown report committed to
`docs/discoveries/DISCOVERY_2026-05-04.md` documenting findings and any reconciliation
needed. NO code changes from discovery — only documentation.

## STEP 4 — After discovery: PR train per D-18 implementation plan

The PR order locked in D-18 implementation plan:

1. venv creation in postinstall
2. catalog DB + 320-row seed in postinstall
3. customer-info Desktop conf flow in postinstall
4. Grafana vendoring + provisioning + LaunchDaemon
5. Scheduled-tasks launchd plists (replacing the cron entries from setup.sh phase_10)
6. Console (D-19) — full FastAPI/Jinja2/HTMX build under `console/`
7. Copy-bug fixes in welcome.html + conclusion.html
8. Real uninstall.sh under bin/
9. Cloudflare Tunnel + Access setup in postinstall
10. Version bump + RELEASE_NOTES_v1.0.3.md
11. Build, sign, notarize, staple v1.0.3
12. Smoke-test on clean Mac VM (UTM/Tart). Iterate until D-18 gate criteria all pass.
13. Install on Mini. Screenshots. Verify green per D-16 + D-18.
14. Then — and only then — VPS decommission + ROBS-PC container shutdown per D-16.

Each PR follows D-18 protocol: small, testable, single-concern, lint-clean,
"Affected docs and decisions" section in PR description (this protocol is being
formalized as D-21 in a follow-up PR — the next agent should read DECISIONS.md
on every session start to catch any new D-? entries).

## STEP 5 — Documentation discipline (the "always over document" mantra, operative)

Every PR description MUST include:

- "Closes audit gap #N" or "Closes copy bug #N" or "Closes integration bug #N" or "Builds
  console feature: <feature>" — naming the specific gap from D-18 or D-19 it addresses.
- A list of the D-? entries the PR touches.
- Lint result.
- For docs PRs: result of `grep -in "<topic>" docs/DECISIONS.md` to verify no contradiction.

Every session END must:

- Append EOD section to today's HANDOFF_YYYY-MM-DD.md.
- Create tomorrow's HANDOFF_YYYY-MM-DD.md with carry-forward state.
- Update PROGRAM_STATE.md if any locked claim changed.

## STEP 6 — Operator constraints (non-negotiable)

- "I would rather be late and perfect than early and wrong." — slip schedules to be right.
- "always comprehensive, and always over document" — operative, not decorative.
- "step by step please i need to focus" — one task at a time, never a bundle.
- "i have ocd and i hate slop or messes" — clean PRs, clean docs, clean commits.
- "stay away from anything cloud only and stay local" — Bitcoin SHA-256 miners only,
  no cloud-only deps.
- "leave no data behind lets get it all" — no destructive operations without explicit
  confirmation; the live VPS data is sacred until v1.0.3 ships.
- "remember the list grows as miners get added so it needs to reflect that on grafana,
  it is not a static number" — catalog count is dynamic, never hardcoded.
- During Mini install (when v1.0.3 ships): explicitly tell the operator when to take
  each screenshot, in real time, not after.

## STEP 7 — What NOT to do

- Do NOT touch the Mini until v1.0.3 is verified on a clean Mac VM.
- Do NOT touch the Hostinger VPS in any destructive way until v1.0.3 is on the Mini and verified.
- Do NOT touch the ROBS-PC Docker container until v1.0.3 is on the Mini and verified.
- Do NOT propose installing v1.0.2 .pkg anywhere — it is broken per audit.
- Do NOT spawn redundant subagents. Plan once, dispatch once.
- Do NOT re-decide D-1 through D-20 — they are locked.
- Do NOT ask the operator to re-confirm scope already in DECISIONS.md or PROGRAM_STATE.md.

## STEP 8 — Today's session-start SHA check

Last main SHA at end of 2026-05-03 session: `<MERGE_SHA_PLACEHOLDER>` (filled in by the
follow-up commit immediately after this PR squash-merges; until that follow-up lands,
treat the value as "the squash-merge SHA of this PR — confirm via `gh pr view N --json mergeCommit`").

Before proposing work, run `git log -1 --format=%H` on main and confirm it matches
this SHA or is later. If earlier, you are out of sync with the repo — re-clone before
proceeding.

## Open questions for operator (to ask AFTER discovery, not before)

1. Cloudflare API token — operator will paste into the Desktop conf at install time. No need to
   ask in advance.
2. Mini RAM tier (16 GB vs 24 GB+ — drives D-13 LLM model selection). Auto-detected by
   detect_ram.sh; not blocking discovery.
3. Mini hostname/screenshare info — confirmed in PROGRAM_STATE.md Section 3.3.
4. Operator's Cloudflare zone hostname for first customer (defaulted to mg.fieslerfamily.com per D-19;
   confirm only if a different subdomain is desired).

## Final note

The operator wrote: "i want you to write a document that if we did not do any work for 2 weeks
you could read it and know what we have done, what we are working on, whats right whats wrong
and what we have to do, this is for you not me."

That document is `docs/PROGRAM_STATE.md`. Read it before this file. Read it again at the start
of every session.
