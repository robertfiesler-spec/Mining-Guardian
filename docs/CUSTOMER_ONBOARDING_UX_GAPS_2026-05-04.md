# Customer Onboarding UX Gaps — 2026-05-04

**Status:** Forward-looking design brief. NOT v1.0.3 scope. Tracked under `docs/MG_UNIFIED_TODO_LIST.md` §18 and `docs/DECISIONS.md` D-23.

This doc consolidates the customer-onboarding gaps Rob identified during the v1.0.3 install pause (`docs/handoffs/HANDOFF_2026-05-04_PAUSED_BEFORE_MINI_INSTALL.md`). It is the single place to look when scoping the next installer iteration that targets a nontechnical customer rather than the operator.

The v1.0.3 .pkg already on disk on the Mac Mini ships unchanged. Do NOT pull any of these gaps into the current pause-resume work. They are tracked here so a future session can pick them up cleanly.

---

## Why this document exists

Two specific moments in the 2026-05-04 install staging exposed real friction:

1. The Mini did not have the Desktop `MiningGuardian.conf` at all. Rob created it manually with `nano`, hand-edited the keys, hit one key-name typo (`REPLACE_ME_SITE_NAME` instead of `CUSTOMER_NAME`), and recovered. **A nontechnical customer would not have recovered.**
2. After the install, the customer still has to: install Tailscale, sign up if they do not have an account, sign in on the Mini, sign in on their phone or laptop, and figure out how to load Mining Guardian's Grafana dashboards by hand. None of that is automated today.

Rob's standing rule is "easy enough for someone who barely knows a computer." Today's installer is "easy enough for the operator who built it." The gap between those two is what this document tracks.

---

## Gap 1 — Customer-info collection should not be a hand-edited Desktop file

### What v1.0.3 does today

`installer/macos-pkg/scripts/postinstall.sh::step_collect_customer_info` reads `/Users/${SUDO_USER}/Desktop/MiningGuardian.conf`, validates it per the B-2 rules, and aborts with a Cocoa dialog + exit code 41 if it is missing or invalid. The customer is expected to drop the .conf on the Desktop before double-clicking the .pkg.

### Why this is fine for the operator

The operator can hand the customer a USB or AirDrop with a pre-filled .conf. That is a one-time setup ritual the operator handles.

### Why this is not fine for a customer-only path

The 2026-05-04 install needed manual `nano` editing, and a key-name was typo'd. If we ever want the customer to install without operator handholding, this UX has to disappear.

### Future direction (not v1.0.3)

- A native macOS Installer.app form pane (InstallerPane plugin) collecting the same fields with explicit labels, format hints, and inline validation feedback. Apple's plugin SDK is non-trivial; v1.0.3 deliberately deferred it.
- Or a first-run setup assistant launched by the postinstall script: a small native window (SwiftUI, Tk, or a localhost web UI auto-launched in Safari) that walks the customer through each field with format examples, then writes the .conf and re-launches postinstall.
- Validate Slack / AMS connectivity inside the form before allowing the customer to proceed. A misconfigured token should block "Continue", not surface as a postinstall failure 30 seconds later.

### Specific safeguards to design in

- Required-field labels in plain language ("Customer name — what should we call this site? Example: R&D Lab"), not config-key names.
- Slack-token format hints under each input ("Bot tokens start with `xoxb-`. App tokens start with `xapp-`.").
- AMS reachability check before "Continue".
- Slack webhook ping check before "Continue".
- "Test connection" button next to every credential field.
- An export-this-config button that writes the same .conf to `~/Desktop/` so the operator can audit it.

### Acceptance criteria

- Customer never sees a `nano` window.
- Customer never types a config-key name.
- Every credential is verified live before postinstall does any system change.

---

## Gap 2 — Tailscale guided onboarding

### What v1.0.3 does today

Postinstall checks if Tailscale is up on the Mini; if it is, it no-ops. If it is not, postinstall surfaces a Cocoa dialog telling the operator to run `tailscale up` separately. That is fine for the operator. For a customer who has never heard of Tailscale, it is not.

### Rob's stated direction

> Customers should be guided through Tailscale setup if they need private remote access. Customers can use a free Tailscale option for a small / two-computer setup. The installer or first-run UX should help customers sign up for or connect Tailscale when needed.

The Tailscale free tier covers small personal tailnets, including a Mini and the customer's phone, which is the typical Mining Guardian deployment shape. For shops that need more, the customer can upgrade.

### Future direction (not v1.0.3)

The setup assistant should:

1. **Detect the current state.** Tailscale not installed → offer to download and install (signed `.pkg` from Tailscale, never bundled in our payload — keeps our notary surface small). Tailscale installed but not signed in → walk the user through `tailscale up` with a "Open Tailscale Login" button. Tailscale signed in → green check.
2. **Explain why.** One short paragraph: "Tailscale lets you reach this Mini privately from anywhere. It is free for personal use and recommended for Mining Guardian customers."
3. **Show the customer the Mini's tailnet name** and the URLs they will use after setup (`http://<mini-tailnet-name>:8585/`, `:8686/`, `:8787/`).
4. **Add the customer's phone or laptop on the same screen.** A QR code linking to the Tailscale install page on iOS / macOS / Android, plus a verification step that the customer's other device shows up in `tailscale status` on the Mini.

### Acceptance criteria

- Customer with no Tailscale account before install ends up with a working tailnet, the Mini joined, and at least one of their other devices joined.
- Customer never copies a Tailscale auth key by hand.
- Customer never reads Tailscale documentation.

---

## Gap 3 — Grafana dashboard auto-provisioning

### What v1.0.3 does today

Nothing. Grafana is Gap 3 in `docs/DECISIONS.md` D-18, deferred from the v1.0.3 build per row 4 of `docs/MG_UNIFIED_TODO_LIST.md` §1.2. Today the customer would have no Grafana, and even if they installed it, the Mining Guardian dashboard JSON is not auto-loaded.

### Rob's stated direction

> The UX should also help customers get Grafana running, including loading Mining Guardian dashboard JSON automatically rather than asking them to build charts by hand.

### Future direction (not v1.0.3)

When Gap 3 is finally taken on:

1. Vendor `Grafana.app` into the .pkg payload.
2. Drop datasource provisioning yaml at `/usr/local/etc/grafana/provisioning/datasources/mining_guardian.yaml` pointing at the local Postgres + Prometheus.
3. Drop dashboard provisioning yaml at `/usr/local/etc/grafana/provisioning/dashboards/mining_guardian.yaml` pointing at a vendored `dashboards/` directory inside the install root.
4. Vendor every dashboard JSON the customer should see (the AI & Learning dashboard plus the standard fleet, HVAC, and Slack-queue dashboards) under the install root.
5. Register an 11th LaunchDaemon (`com.miningguardian.grafana.plist`) if `Grafana.app` does not auto-manage itself.
6. Expose `:3000` on `127.0.0.1` only. Cloudflare Tunnel handles remote access for the operator console; Grafana stays local-only by default.
7. The setup assistant should show the customer the Grafana URL, the default credentials (rotated to a per-install random value at postinstall time), and a "Open Grafana" button that opens the browser to the AI & Learning dashboard.

### Why JSON auto-load matters

The customer is not a Grafana operator. Asking a nontechnical user to import dashboard JSON by hand will fail every time. The provisioning YAML approach is the only path that reliably puts the dashboards in front of them on first boot.

### Acceptance criteria

- Customer opens Grafana on first boot and sees the AI & Learning dashboard already populated.
- No "Import JSON" step.
- No manual datasource configuration.
- Default credentials rotated per-install — the same `MG_DB_PASSWORD` / `openssl rand -hex 32` discipline applied to Grafana admin.

---

## Gap 4 — Pre-install Slack / AMS connectivity validation

### What v1.0.3 does today

`step_collect_customer_info` validates the SHAPE of the values (regexes — webhook URL prefix, token prefix, workspace ID is digits, email has `@`). It does not validate that the values actually work. A typo in the AMS password or Slack signing secret will sail past validation and surface as a postinstall failure or, worse, a silent runtime error after install completes.

### Future direction (not v1.0.3)

Before any system state is touched, the setup assistant should:

- POST a `chat.postMessage` "install starting" notice to the Slack webhook and confirm 2xx.
- Hit AMS `/api/v1/login` with the supplied email + password and confirm a session cookie comes back.
- Resolve the AMS workspace ID against the authenticated session and confirm the user has access.
- Surface a clear, plain-language error per failure ("Your AMS password did not work — check it and try again") rather than a Cocoa dialog quoting an exit code.

A failure here should keep the customer in the assistant; it should not abort to a half-installed system.

### Acceptance criteria

- Slack and AMS validation happen before any LaunchDaemon is loaded, before any DB is created, before any file is written outside the install root.
- Each failure mode has a customer-facing error message in plain language.
- Customer can fix the typo in-place without re-running the .pkg.

---

## Gap 5 — Support bundle

### Why this matters

When something goes wrong on a customer site, today the only debugging path is a Tailscale SSH session and a long Bash transcript. That is fine for the operator. It is not a customer-friendly support channel.

### Future direction (not v1.0.3)

A single `mg-support-bundle` command (also wired to a "Generate support bundle" button in the operator console at `:8787`) that:

- Captures the last 24h of logs from each of the 10 services.
- Captures `launchctl list | grep com.miningguardian` plus the last-run JSON stamps from `${INSTALL_ROOT}/logs/scheduled/*.last-run.json`.
- Captures the service-status output (postgres up? colima up? ollama up?).
- Captures a redacted shape of the `.env` (keys present, values redacted) — never the values.
- Captures the package version, install commit SHA, and notarization status.
- Emits a single tar.gz under `~/Desktop/MG-Support-<hostname>-<timestamp>.tar.gz` that the customer can email or AirDrop.

The "redacted" part is the key safety property — no AMS / Slack / DB password value, no `INTERNAL_API_SECRET`, ever leaves the Mini.

### Acceptance criteria

- One command. One file. No interactive prompts.
- Operator can read the file and reproduce the customer's state without further questions.
- File contains zero credential values.

---

## Gap 6 — `MG_DRY_RUN=true` should be the safe default and the customer should understand it

### What v1.0.3 does today

`MG_DRY_RUN` is one of the validated keys in the Desktop conf. The default value lives in the template. We never explain what it does to the customer.

### Future direction (not v1.0.3)

- Default `MG_DRY_RUN=true` in any customer-facing template. The customer must explicitly flip it to `false` to enable live remediation.
- The setup assistant should explain in one paragraph: "Mining Guardian will detect problems and ask you to approve fixes in Slack. To start, it will only send notices and not change miner state. Once you trust what you are seeing, you can switch it to live mode."
- The operator console should show a banner when `MG_DRY_RUN=true`: "DRY-RUN — no live actions."
- A one-click "Switch to live mode" button in the operator console (gated on customer confirmation) that flips the value, restarts the daemon, and re-runs the validation.

### Acceptance criteria

- New customer cannot accidentally enable live remediation on day one.
- Customer can self-serve the switch when ready, without editing `.env` by hand.
- Banner is impossible to miss when in dry-run.

---

## Gap 7 — Recovery / uninstall path should be visible, not buried

### What v1.0.3 does today

P-008 shipped `installer/macos-pkg/resources/uninstall.sh` (mode 0755, shellcheck-clean) and the conclusion.html mentions it briefly. Default behavior preserves `postgres-data` and `/var/log/mining-guardian` per the §"Critical Safety Rules" entry.

### Future direction (not v1.0.3)

- A "Reset Mining Guardian" button in the operator console that runs the uninstall script with `--dry-run` first, shows a preview of what will be removed, then asks for confirmation. The customer never has to drop to Terminal.
- Clear separation between "remove everything (default — keeps your data)" and "remove everything including data (`--purge-data`)". Use red affordance + double-confirmation for the destructive path.
- A "Re-run setup assistant" button that wipes the .conf and `.env`, runs the assistant again, and re-applies. Useful for customers who want to change their AMS password or rotate Slack tokens.

### Acceptance criteria

- Customer can recover from a misconfigured install without using Terminal.
- Customer cannot accidentally delete `postgres-data` — it is preserved by default and the destructive path requires double-confirm.

---

## Gap 8 — Screenshot-ready runbook

### Why this matters

Rob's standing rule on this install is "screenshots along the way." That is a one-time ritual today. For a customer-ready release, the install should be documented well enough that the customer can follow the screenshots without us watching.

### Future direction (not v1.0.3)

- A short PDF (or web doc) that walks through every dialog the customer will see, in order, with annotated screenshots: where to click, what to type, what success looks like.
- One PDF per resolution (Retina vs non-Retina), or SVG-first so we are not bound to pixel sizes.
- Update the PDF every time we change a dialog string.

### Acceptance criteria

- Nontechnical customer can install end-to-end with the PDF and no live support.
- Every dialog the .pkg shows has a corresponding annotated screenshot.

---

## What we are explicitly NOT doing as part of this brief

- Building any of the above today. The v1.0.3 .pkg sitting on the Mini is what gets installed. This brief is forward-looking only.
- Rewriting the conf-file approach to use a GUI form (that is the next major scope decision; tracked at D-23).
- Vendoring Grafana before the v1.0.3 Mini install verifies green.
- Auto-provisioning Cloudflare Tunnel (D-19 step 5 / row 9).

---

## Cross-references

| Topic | See |
|---|---|
| Pause point + resume checklist | `docs/handoffs/HANDOFF_2026-05-04_PAUSED_BEFORE_MINI_INSTALL.md` |
| Skip-VM smoke decision | `docs/DECISIONS.md` D-22 |
| Customer-onboarding scope decision | `docs/DECISIONS.md` D-23 |
| Open work tracking | `docs/MG_UNIFIED_TODO_LIST.md` §18 |
| Existing installer UX backlog | `docs/INSTALLER_UX_BACKLOG_2026-05-01.md` |
| Console operations (port 8787) | `docs/CONSOLE_OPERATIONS_GUIDE.md` |
| Web GUI operator console (Bucket 9 §10.1) | `docs/WEB_GUI_OPERATOR_CONSOLE.md` |
