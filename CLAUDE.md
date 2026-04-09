# Mining Guardian

AI-powered Bitcoin mining fleet monitor for BiXBiT USA, Fort Worth TX.
Monitors 49 miners across hydro racks and immersion tanks. Provides automated
remediation, Slack approval workflow, Grafana dashboards, and LLM-based
pattern learning.

## Stack Context

- **Language**: Python 3.12
- **Primary service**: mining_guardian.py — systemd daemon, runs every 5 min
- **Dashboard API**: dashboard_api.py — FastAPI on port 8585
- **Database**: SQLite (guardian.db) — never delete, never cp config_template.json over config.json
- **Monitoring**: Prometheus + Grafana (grafana.fieslerfamily.com)
- **LLM**: Qwen2.5 32B on Windows PC RTX 4090 via Ollama + Tailscale (primary), Claude API (weekly training)
- **Notifications**: Slack via Socket Mode (OpenClaw owns the connection)
- **Infrastructure**: VPS (Hostinger KVM 8, 187.124.247.182), Tailscale, Cloudflare tunnels — ALL TEMPORARY, see Deployment Target below

## Project-Specific Rules

### Critical Safety Rules — Never Violate

- NEVER cp config_template.json over config.json — overwrites AMS credentials and Slack tokens
- NEVER delete or truncate guardian.db — all historical data lives here
- NEVER add Bolt/slack-bolt — OpenClaw owns Socket Mode, conflicts will break Slack
- Pool management and miner settings are explicitly OUT OF SCOPE
- Dead board issues on S19JPros are suppressed after ticket creation — do not re-raise

### Working Principles (locked April 9 2026)

**The 2-vs-10 rule.** When facing any choice between a quick fix and a proper fix, the question is not "which is faster" — it is "which leaves us better off for the rest of the project." The rule: if we can fix it in 2 minutes and it will be ok, OR in 10 minutes and it will be right and better for the future, pick right. No more going back and re-doing things. We have ~3 weeks to finish — every re-do costs more than a deliberate up-front fix.

**Work slowly and verify.** Before editing a file, read it. Before running a command that changes state, say what it does and why. Before assuming a library, API, or tool works a certain way, check. Small verification steps are cheap; cleanup after a wrong assumption is expensive.

**Scope discipline during edits.** When editing a file for purpose A, do NOT also fix unrelated issue B in the same edit — even if B is obvious and easy. Note B separately and handle it as its own task. Mixing scopes is how we lose the ability to cleanly revert a change.

**Stop-and-check before irreversible actions.** Commits are reversible. Pushes are reversible-with-effort. Production config edits are reversible-if-backed-up. Config files overwritten via cp are sometimes not recoverable (see the `config_template.json` rule above). When in the last category, back up first, always.

**Time budgets are hard caps.** When a debug path has a stated budget (e.g., "30 min max on WSL2"), that budget is a commitment, not a suggestion. At the cap, stop and pivot to the fallback — do not keep banging. Bobby can always override the cap in the moment if he chooses, but the default is to respect it.

### Deployment Target (locked April 9 2026)

**The product is a single Mac mini running a docker-compose stack at a customer site, with normal internet access.** Between now and May 1 2026 we are building features on a Hostinger VPS with Cloudflare tunnels and host-level systemd services because that is the dev environment we have. None of that is the product. On May 1 we containerize Mining Guardian and move the whole stack to a Mac mini. Between now and then, every new piece of code, config, or infrastructure decision is evaluated by one question:

> *"Does this make the May 1 migration easier, harder, or neutral?"*

The answer should never be "harder." Easier or neutral are both fine.

**Design stance: open and useful by default, tightenable by choice.**

The Mac mini has full internet access. Grafana dashboards, the Mining Guardian dashboard, and the approval API should all be reachable from anywhere the customer wants to reach them — operator's phone, laptop, office, wherever. Slack works normally. Outbound HTTPS works normally. Claude API for weekly training works normally. Monthly knowledge.json sync works normally. **This is a normal internet-connected appliance, not a hardened bunker.**

Customers who want their deployment locked down (private network only, VPN-only access, restricted outbound) get that via configuration — we expose the knobs, they choose the settings. We do NOT pre-lock anything "for their own good." Customer choice beats developer gate-keeping every time.

**Containerization design decisions (applies to new code TODAY, even though the container work happens in May):**

- Do NOT hardcode VPS-specific paths, IPs, or hostnames in new code when the value can be read from config
- Do NOT add new systemd-specific features to services that will become containers (timers, socket activation, journal-specific log parsing)
- Do NOT assume Mining Guardian and OpenClaw are on different hosts — they will be two containers in the same docker-compose stack on the same Mac mini. Design inter-service communication as if they already are, using service name DNS inside a shared network and shared volumes for filesystem access
- DO favor configurable values over hardcoded ones, even if the only current value is a VPS-specific one. Swapping a config value is a May 1 one-line change. Rewriting code is not.
- DO document any temporary/throwaway values with a `# TEMP:` comment naming what the forever-value will be. Example: `# TEMP: VPS-specific, becomes "http://openclaw:18789/hooks" on May 1`. The May 1 migration should be mechanical, not archaeological.

**The "no media server" rule — scope discipline, not network discipline.**

The Mac mini runs Mining Guardian, OpenClaw, and what they need to do their job. That's it. No adding unrelated services "because why not." No hobbyist sprawl. Every new container or service has to earn its place by solving a real Mining Guardian problem. This is a focused operational tool, not a home lab.

(This rule is about scope and maintenance burden, NOT about network access. Grafana is in scope. Grafana is reachable from the internet. Both things are true.)

**We are NOT containerizing Mining Guardian today or this week.** The refactor is scheduled for May 1. Before then, keep shipping features on the VPS using whatever works today — just don't create new VPS-only assumptions that will need to be unwound.

### Architecture Rules

- ALL miner commands go through AMS first — direct device APIs (port 4028/4028) are fallback only
- PDU power readings ALWAYS take priority over miner-reported consumption
- Problem descriptions stated once at top, miners listed underneath — never repeat per miner
- Never truncate IP lists with "+N more" — show all miners
- Slack reporting throttled to 1 per hour maximum

### Domain Conventions

- Miner status: ONLINE / OFFLINE / AMS_SYNC (verified online but AMS says offline)
- Actions: RESTART / PDU_CYCLE / PHYSICAL_CYCLE / RESTART_CHECK_BOARDS / MONITOR / TEMP_ACTION_REQUIRED
- Temp zones: GREEN <76°C | YELLOW 76-85°C | RED 86°C+
- All cooling is liquid (hydro + immersion) — no fans, no air cooling references
- Hashrate thresholds: flag if below 80% of rated TH/s

### Repo Conventions

- Repo name has intentional space and typo: "Mining Gaurdian" — always quote in terminal
- Python files use venv — always `source venv/bin/activate` before running
- Commit messages: brief description of what changed and why
- Always test imports before pushing: `python3 -m py_compile <file>`

### Known Infrastructure

- VPS: root@187.124.247.182 (Tailscale: 100.106.123.83)
- Windows PC LLM: http://100.110.87.1:11434 (Qwen2.5 32B, must stay on)
- AMS API: https://api-staging.dev.bixbit.io/api/v1 (workspace 119)
- Grafana: grafana.fieslerfamily.com (admin / see memory)
- Dashboard: dashboard.fieslerfamily.com → VPS:8585
- Slack: slack.fieslerfamily.com → VPS:8686

## What Good Looks Like

- Clean, readable Python — no unnecessary complexity
- Every new DB table has an index on (miner_id, scanned_at)
- Every new Prometheus metric has correct labels (miner_ip, model, site, map_location)
- LLM prompts are concise — operators are busy, 10-15 lines max response
- Dashboard API endpoints return JSON only — no HTML except the status_html route
- All services restart cleanly via systemctl — no manual intervention needed

<!-- AI TOOLKIT INTEGRATION -->
## AI Toolkit

Installed: v0.5.0-alpha

### Workflow

```
/kickoff → /create-plan → /iterate → commit → /pre-pr-check → push
```

Use `/learn` immediately after correcting any mistake to make it permanent.

### Available Commands

See `.claude/WORKFLOW.md` for full command reference.

Key commands for this project:
- `/kickoff` — start session, read project context
- `/create-plan` — break feature into checklist
- `/iterate` — execute plan items in batches
- `/verify` — run linting/type checks
- `/learn` — turn a correction into a permanent rule
- `/checkpoint` — save session state before clearing context
- `/catchup` — restore from checkpoint after /clear
