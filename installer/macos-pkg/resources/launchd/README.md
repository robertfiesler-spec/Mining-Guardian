# Mining Guardian — macOS LaunchDaemon Plists

Bucket 6 / installer rebuild — the 8 plist templates the macOS installer renders
into `/Library/LaunchDaemons/` during a customer install, mirroring the 8
`*.service` units running today on the VPS.

## Inventory

| # | Plist | Mirrors systemd unit | Entry point | Throttle |
|---|---|---|---|---|
| 1 | `com.miningguardian.scanner.plist` | `mining-guardian.service` | `core/mining_guardian.py` | 10s |
| 2 | `com.miningguardian.dashboard-api.plist` | `dashboard-api.service` | `api/dashboard_api.py` | 10s |
| 3 | `com.miningguardian.approval-api.plist` | `approval-api.service` | `api/approval_api.py` | 10s |
| 4 | `com.miningguardian.slack-listener.plist` | `slack-listener.service` | `api/slack_approval_listener.py` | 10s |
| 5 | `com.miningguardian.slack-commands.plist` | `slack-commands.service` | `api/slack_command_handler.py` | 10s |
| 6 | `com.miningguardian.overnight-automation.plist` | `overnight-automation.service` | `core/overnight_automation.py` | 30s |
| 7 | `com.miningguardian.alerts.plist` | `mining-guardian-alerts.service` | `api/ams_alert_listener.py` | 10s |
| 8 | `com.miningguardian.intelligence-report.plist` | `intelligence-report.service` | `api/intelligence_report_api.py` | 5s |

The 9th launchd plist on a Mac Mini install — `com.miningguardian.feedback-loop-daemon.plist` —
lives separately at `deploy/com.miningguardian.feedback-loop-daemon.plist`
(D-14 PR-4b) and is rendered by the installer alongside these 8. It is the
catalog-side feedback-loop daemon and is independent of the 8 operational
services in this directory.

## Install layout (set up by `installer/macos-pkg/scripts/postinstall.sh`)

```
/Library/LaunchDaemons/
    com.miningguardian.scanner.plist            (mode 0644, owner root:wheel)
    com.miningguardian.dashboard-api.plist
    com.miningguardian.approval-api.plist
    com.miningguardian.slack-listener.plist
    com.miningguardian.slack-commands.plist
    com.miningguardian.overnight-automation.plist
    com.miningguardian.alerts.plist
    com.miningguardian.intelligence-report.plist
    com.miningguardian.feedback-loop-daemon.plist   (from deploy/)

/usr/local/MiningGuardian/
    .env                                        (mode 0600, owner root:wheel)
    venv/
    core/, api/, intelligence-catalog/db/       (the repo)
    bin/
        scanner_launcher.sh                     (mode 0755, owner root:wheel)
        dashboard_api_launcher.sh
        approval_api_launcher.sh
        slack_listener_launcher.sh
        slack_commands_launcher.sh
        overnight_automation_launcher.sh
        alerts_launcher.sh
        intelligence_report_launcher.sh
        feedback_loop_daemon_launcher.sh        (from deploy/)
    logs/                                       (mode 0755, owner root:wheel)
        scanner.{out,err}.log
        dashboard-api.{out,err}.log
        ... etc.
```

## Why launcher wrappers?

launchd has no equivalent of systemd's `EnvironmentFile=` directive. Rather
than embedding secrets (`MG_DB_PASSWORD`, `AMS_PASSWORD`, etc.) directly into
the plist (which sits world-readable in `/Library/LaunchDaemons/`), each plist
invokes a small wrapper at `/usr/local/MiningGuardian/bin/*_launcher.sh` that:

1. Verifies `/usr/local/MiningGuardian/.env` exists.
2. Verifies the venv Python is present and executable.
3. Verifies the entry point file exists.
4. Sources `.env` so every `KEY=VALUE` is exported into the env.
5. `exec`s `python -u <entry-point>`.

The wrappers are committed at `installer/macos-pkg/resources/launchd/launchers/`.
They are **identical in shape** save for the entry-point path; this is intentional,
both for review-ability and so the `postinstall.sh` install loop can copy them
all uniformly.

## Loading

After `postinstall.sh` drops the files in place:

```bash
for plist in /Library/LaunchDaemons/com.miningguardian.*.plist; do
    sudo launchctl bootstrap system "$plist"
done
```

Verify:

```bash
sudo launchctl list | grep com.miningguardian
# Should show 9 entries (8 services + feedback-loop-daemon).
# Last column should be the Label; PID column should be a number,
# not "-", and exit-code column should be 0.
```

If any entry shows exit-code != 0 immediately on load, check
`/usr/local/MiningGuardian/logs/<service>.err.log` — the launcher wrapper's
`FATAL: ...` line tells you which precondition failed.

## Unloading (e.g. uninstall, or to stop everything for an update)

```bash
for plist in /Library/LaunchDaemons/com.miningguardian.*.plist; do
    sudo launchctl bootout system "$plist" 2>/dev/null || true
done
```

## Divergences from the systemd units

The plists are intentionally close to the `.service` units, with these
differences:

1. **Resource limits.** `mining-guardian-alerts.service` caps at
   `MemoryMax=256M` / `TasksMax=20`; launchd has no equivalent. Documented in
   `com.miningguardian.alerts.plist` itself.
2. **Install root.** systemd path is `/root/Mining-Guardian`; macOS path is
   `/usr/local/MiningGuardian`. Reflected in every entry point and log path.
3. **`User=root`.** systemd runs as root; launchd LaunchDaemons also run as
   root by default. S-7 (dedicated `miningguardian` user) is the longer-term
   plan and is tracked separately in `docs/MG_UNIFIED_TODO_LIST.md` §3.2 — when
   it lands, every plist in this directory adds `<key>UserName</key>` +
   `<key>GroupName</key>` and the install root chowns to that user.
4. **Restart cadence.** `RestartSec` from systemd maps directly to
   `ThrottleInterval` on launchd. Values are preserved verbatim (10s for most,
   30s for overnight-automation, 5s for intelligence-report).
5. **Logging.** systemd routes to journald; launchd writes to
   `StandardOutPath` / `StandardErrorPath` files under
   `/usr/local/MiningGuardian/logs/`. Operators tail those directly.

## Adding a new service

1. Add the systemd unit at `deploy/<name>.service`.
2. Add the plist at `installer/macos-pkg/resources/launchd/com.miningguardian.<name>.plist`,
   modelled on the closest existing plist.
3. Add the launcher at `installer/macos-pkg/resources/launchd/launchers/<name>_launcher.sh`
   (chmod +x in the commit).
4. Add the row to the inventory table at the top of this file.
5. Update `installer/macos-pkg/scripts/postinstall.sh` to copy the new plist
   and launcher into place.

## See also

- `installer/macos-pkg/scripts/postinstall.sh` — install-time orchestration
- `installer/macos-pkg/scripts/preinstall.sh` — pre-install checks
- `deploy/*.service` — the systemd source-of-truth that these plists mirror
- `docs/MG_UNIFIED_TODO_LIST.md` Section 7 — installer rebuild plan
- `docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md` — the deployment runbook
