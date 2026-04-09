# Morning Kickoff Prompt

**Purpose:** Paste this into a fresh Claude chat at the start of every Mining Guardian work session. It forces Claude to read the entire project state before taking any action — preventing the "Claude proposes alternatives to plans that already exist" failure mode that ate the afternoon of April 9 2026.

**Created:** April 9 2026
**Lives at:** `docs/MORNING_KICKOFF_PROMPT.md` in the Mining Guardian repo
**Also lives at:** `#mg-ai-reports` Slack channel (pinned)

---

## The Prompt — paste everything below the line

---

Good morning. This is Bobby. Before we do anything today, I need you to do a complete review of the Mining Guardian project state. Do NOT ask me any questions, do NOT propose any plans, do NOT suggest any alternatives to anything until you have completed every step below. When you are done with all steps, come back with the summary I ask for at the end. Take as long as you need. I am going to get coffee.

**Step 1 — Read my core guidance.** Read `/Users/BigBobby/Documents/GitHub/Mining Gaurdian/CLAUDE.md` in full. This contains my Working Principles (2-vs-10 rule, work slowly and verify, scope discipline, stop-and-check, time budgets as hard caps), my Deployment Target section (Mac mini at customer site, open and useful by default, `# TEMP:` comment convention), the Session Kickoff Protocol, the Vision Anchors, the Failure Modes to Avoid, and the Document Map. These rules are binding for every decision you make today.

**Step 2 — Read the canonical vision.** Read `docs/VISION.md` in full. This is the single source of truth that synthesizes every other doc. If there is ever a conflict between what I say in a conversation and what this doc says, point it out — do not silently pick one.

**Step 3 — Read the current state docs.** Read `README.md` and `AI_ROADMAP.md`. README has the current architecture, fleet, services, DB schema, and key files. AI_ROADMAP has the current priority queue, 8 AI feature statuses, migration checklist, and build timeline.

**Step 4 — Read the most recent handoff note.** Look in `docs/` for files matching `RESUME_HERE_*` or `HANDOFF_*`. Read the most recent one by date. That tells you what the last session was doing and what the immediate next task is.

**Step 5 — Check git state.** Run `git status`, `git log --oneline -20`, and `git branch -a` on the main repo. Tell me if there are uncommitted changes, if I'm on a non-main branch, or if there are branches with un-merged work I should know about (especially `installer-build` if we're within a few weeks of the Mac mini arrival).

**Step 6 — Spot-check the production daemon.** SSH to VPS `root@187.124.247.182` (using osascript), run `systemctl status mining-guardian dashboard-api approval-api slack-listener slack-commands overnight-automation prometheus grafana-server`. Report which services are up and which are not. Also run `tail -20 /root/Mining-Gaurdian/logs/guardian_$(date +%Y-%m-%d).log` and flag any ERROR lines.

**Step 7 — Confirm the learning loop is alive.** On the VPS, run `python3 -c "import json; d=json.load(open('/root/Mining-Gaurdian/knowledge.json')); print('last_updated:', d.get('last_updated'), '| miners:', len(d.get('miner_profiles',{})), '| known_issues:', len(d.get('known_issues',[])), '| patterns:', len(d.get('patterns',[])), '| llm_scan_analyses:', len(d.get('llm_scan_analyses',[])), '| operator_rules:', len(d.get('operator_rules',[])))"` and tell me the numbers. If `last_updated` is more than 30 minutes old, something is wrong with the scan loop.

**Step 8 — Read yesterday's morning briefing from Slack.** Check channel `#mining-guardian` (C0AQ8SE1448) for yesterday's 7am morning briefing post and summarize anything notable — new dead boards, overnight actions, unusual temps, HVAC events.

**Step 9 — Come back with this exact report format.** Five sections, nothing else. No questions yet.

1. **Project vision (one paragraph, your own words).** Confirm you understand where Mining Guardian is going: Mac mini appliance at customer sites, two-tier AI (local Qwen for scans + Claude for weekly training), 8 AI features wired into the scan loop, federated monthly knowledge merge across customers, OpenClaw as the conversational brain routing Block Kit actions via Socket Mode on the Mac mini with no public ingress.
2. **What the last session was doing.** From the most recent resume/handoff note, in 3-5 sentences.
3. **Production health right now.** Services up/down, log errors if any, knowledge.json freshness and counts, anything alarming from the morning briefing.
4. **Current top priority, per the docs (not per you).** Whatever the existing roadmap says is next. Not your opinion. Not an alternative. What the docs say.
5. **The short list of questions the docs genuinely don't answer that you need from me to proceed.** Zero if the docs are sufficient. Maximum three. If you're tempted to ask a fourth, the fourth goes in a note at the bottom saying "I'll pick the most reasonable interpretation and note the assumption in my response."

After that report, wait for my reply. Do not start work until I confirm.

**Rules for the whole day that override everything else:**

- If you find yourself drafting a clarifying question, first ask yourself "is this answered in the docs I just read?" If yes, re-read the relevant doc and answer it yourself. If no, it belongs in your question list.
- If you find yourself proposing an alternative to a plan I've described, first ask yourself "is there an existing plan in the docs that I'm proposing to replace?" If yes, STOP. Do not propose alternatives to existing plans. Execute the existing plan or tell me what's blocking it.
- If you find yourself about to create a new file with "VISION" or "PLAN" or "ROADMAP" in the name, STOP. That file almost certainly already exists. Go find it.
- The main feature of Mining Guardian is the LLM and it getting smarter. Any solution that removes the LLM from the operator's decision flow is the wrong solution, even if it works technically. If you're tempted to build something that doesn't feed the learning loop, ask me first.
- Time budgets are hard caps. If I say "30 minutes max on X", at 30 minutes you stop and pivot, you do not "just keep going for 5 more minutes".
- When in doubt between 2-min-fast and 10-min-right, pick 10-min-right. We have three weeks.
- Never `cp config_template.json` over `config.json` on the VPS. Never.

Go.

---

## Bobby's side of the morning ritual

Things to do in parallel while Claude reads the repo:

1. Read the overnight morning briefing in `#mining-guardian` (posted 7am by cron) — 30 seconds
2. Check `#mg-ai-reports` for anything Qwen flagged overnight
3. Glance at Grafana Main dashboard — fleet online count, HVAC supply/return, top-5 worst miners — 60 seconds
4. Check `#mg-approvals` for anything that expired unanswered during quiet hours
5. Confirm ROBS-PC is awake and Qwen is reachable: `curl -s http://100.110.87.1:11434/api/tags | head -c 100`
6. Eyeball the warehouse if on-site — physical intuition catches things the data misses

Then Claude's 5-section report should be ready and the day can start.
