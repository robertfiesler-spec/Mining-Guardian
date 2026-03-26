# Mining Guardian

Automated monitoring and remediation system for bitcoin mining fleets.

Mining Guardian connects to your AMS (Miner Management System) via API, evaluates live miner telemetry against a configurable policy ruleset, and either automatically applies safe fixes or routes violations to an operator for approval before any action is taken.

---

## How It Works

1. **Scan** — fetches the miner list from AMS, then pulls fresh per-miner telemetry for accurate rule evaluation
2. **Evaluate** — runs each miner's state through the policy engine; any parameter outside defined bounds generates a `MinerFinding`
3. **Notify** — sends findings to the OpenClaw webhook for operator visibility
4. **Remediate** — approved fixes are patched back to AMS; a 30-minute cooldown prevents repeat actions on the same miner


---

## Key Features

- Policy-based miner parameter validation (hashrate, temperature, power profile, and more)
- Configurable rules via `config.json` — no code changes needed to add new checks
- Three approval modes: `manual`, `auto-low-risk`, and headless daemon (auto-deny with logging)
- HTTP retry with exponential backoff on all AMS API calls (handles transient 5xx and rate limits)
- Remediation cooldown cache — prevents hammering the same miner/key pair every scan cycle
- Secret management via `env:` prefix — keeps API keys out of config files on disk
- OpenClaw webhook integration for operator notifications and approval routing
- `dry_run` mode enabled by default — safe to deploy before AMS endpoints are finalized

---

## Approval Modes

| Mode | Behavior |
|---|---|
| `manual` | Prompts operator via CLI (TTY) or auto-denies in headless environments |
| `auto-low-risk` | Automatically approves low-risk keys (fans, DNS, power profile); escalates critical findings |

OpenClaw interactive approval (webhook → operator reply → APPROVE/DENY) is stubbed and ready to wire in `ApprovalInterface.request_approval()`.


---

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/mining-guardian.git
cd mining-guardian
pip install requests
```

---

## Configuration

Copy the example config and edit for your environment:

```bash
python mining_guardian.py  # auto-generates config.example.json on first run
cp config.example.json config.json
```

Key fields in `config.json`:

```json
{
  "ams_base_url": "https://ams.internal.example",
  "ams_api_key": "env:AMS_API_KEY",
  "dry_run": true,
  "approval_mode": "manual",
  "scan_interval_seconds": 300
}
```


**Secret management** — prefix any config value with `env:` to source it from the environment instead of storing it in the file:

```json
"ams_api_key": "env:AMS_API_KEY"
```

Then set the variable in your shell or systemd unit:

```bash
export AMS_API_KEY=your-key-here
```

---

## Running

Single scan:

```bash
python mining_guardian.py
```

Continuous loop (runs every `scan_interval_seconds`):

```python
from mining_guardian import GuardianConfig, MiningGuardian

config = GuardianConfig.from_file("config.json")
MiningGuardian(config).loop()
```


---

## Policy Rules

Rules are defined in `config.json` under the `rules` array. Each rule specifies a telemetry key, an operator, an expected value, a severity, and an optional recommended fix.

Supported operators: `eq`, `neq`, `lt`, `lte`, `gt`, `gte`, `between`, `in`

Example rules:

```json
[
  {
    "key": "telemetry.hashrate_ths",
    "operator": "gte",
    "expected": 130,
    "severity": "critical",
    "recommended_fix": null,
    "note": "Hashrate below expected floor — requires operator review"
  },
  {
    "key": "telemetry.chip_temp_c",
    "operator": "between",
    "expected": [40, 75],
    "severity": "critical",
    "recommended_fix": "efficiency",
    "note": "Temperature outside normal envelope — drop to efficiency power profile"
  },
  {
    "key": "config.power.profile",
    "operator": "in",
    "expected": ["balanced", "efficiency", "immersion-140th"],
    "severity": "warning",
    "recommended_fix": "balanced",
    "note": "Unexpected power profile detected"
  }
]
```


---

## Repository Structure

```
Mining Guardian/
├── mining_guardian.py      # Core daemon — policy engine, AMS client, orchestrator
├── config.json             # Your live config (gitignored)
├── config.example.json     # Auto-generated reference config
├── .gitignore
└── README.md
```

---

## Safety Model

Mining Guardian uses a human-in-the-loop design by default. `dry_run: true` is set out of the box — no changes are applied to miners until you explicitly disable it and approve actions. Critical findings never auto-remediate regardless of approval mode.

---

## Roadmap

- OpenClaw interactive approval (webhook → operator reply)
- Smart PDU telemetry integration
- Predictive miner failure detection
- Fleet-level analytics and reporting
- Firmware version drift detection

---

*Built by Rob Fiesler — BiXBiT USA*
