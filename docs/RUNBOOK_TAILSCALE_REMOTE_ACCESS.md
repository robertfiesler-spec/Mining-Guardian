# Runbook — Tailscale Remote Access for `miningguardian` Mini

**Created:** 2026-04-30
**Applies to:** Mac Mini hostname `miningguardian`, macOS user `miningguardian`
**Reason:** On-site LAN address `192.168.188.100` is only reachable when you're physically at the office. Tailscale gives the Mini a stable address that works from anywhere.

---

## TL;DR — three addresses, three situations

| You are… | Use this address | Notes |
|---|---|---|
| **At the office** (same LAN as the Mini) | `192.168.188.100` *or* `miningguardian.local` | Fastest. Pure LAN, no Tailscale relay. |
| **Anywhere else, on Tailscale** | `100.69.66.32` *or* `miningguardian` (MagicDNS) | Works over any internet connection. |
| **Anywhere else, NOT on Tailscale** | You can't reach it. | Connect to your tailnet first. |

The MagicDNS name `miningguardian` is the **safest default** — Tailscale auto-resolves it whether you're on LAN or remote, and it survives Tailscale IP changes (which can happen if a device is ever removed and re-added to the tailnet).

---

## Connection cheatsheet

### From any device on your tailnet

```bash
# SSH (preferred — uses Tailscale by MagicDNS)
ssh miningguardian@miningguardian

# Or by Tailscale IP if MagicDNS isn't configured
ssh miningguardian@100.69.66.32

# Screen Sharing (macOS Finder → Go → Connect to Server)
vnc://miningguardian
# or
vnc://100.69.66.32
```

### From a Windows laptop on Tailscale

```powershell
# SSH (built-in OpenSSH)
ssh miningguardian@miningguardian

# Screen Sharing — RealVNC Viewer with target:
miningguardian
# or
100.69.66.32
```

### From the office LAN (no Tailscale needed)

```bash
ssh miningguardian@192.168.188.100
ssh miningguardian@miningguardian.local
```

---

## How to verify Tailscale is working on the Mini

Either via Screen Sharing, or by SSHing in via LAN once when you're at the office:

```bash
# Status — should say "Logged in" and show 100.69.66.32
tailscale status

# Confirm the Mini's own IP
tailscale ip -4

# Confirm SSH is allowed inbound
sudo systemsetup -getremotelogin   # → "Remote Login: On"
```

If `tailscale status` shows the Mini as logged out, log it back in:

```bash
sudo tailscale up --ssh
```

(`--ssh` is optional but recommended — it lets you use `tailscale ssh miningguardian` from any tailnet device without managing keys per host. Currently you're using regular OpenSSH keys, which also works fine.)

---

## Troubleshooting — "I can't reach the Mini from outside the office"

Run these in order:

1. **Is your laptop on the tailnet right now?**
   ```bash
   tailscale status        # macOS/Linux
   ```
   On Windows: open the Tailscale tray icon — it should show "Connected" and list your devices including `miningguardian`.

2. **Can you ping the Mini's Tailscale IP?**
   ```bash
   ping -c 3 100.69.66.32
   ```
   No reply → Mini is offline, or Tailscale on the Mini is down.

3. **Has the Tailscale IP changed?**
   IPs can change if the Mini was removed and re-added to the tailnet. Check the [Tailscale admin console](https://login.tailscale.com/admin/machines) → look for `miningguardian` → confirm the current `100.x.x.x` address.
   **This is why MagicDNS name is preferred — it never changes.**

4. **Is the Mini powered on?**
   - If you have a smart plug or remote power, check it.
   - If it's truly unreachable and on-site help is unavailable, the Mini's auto-restart-after-power-failure setting (enabled during install) means a brief power cycle should bring it back.

5. **Is SSH itself working?**
   If ping works but SSH hangs:
   ```bash
   ssh -v miningguardian@miningguardian
   ```
   Verbose output will show whether the connection completes the TLS handshake.

---

## Installer day (May 1) — using Tailscale

If you're not on-site for the installer run, every command in `RUNBOOK_INSTALL_DAY_2026-04-30.md` works the same — just substitute the address:

```bash
# Copy the .pkg up
scp ~/Downloads/MiningGuardian-1.0.0-0f849bd217cc.pkg \
    miningguardian@miningguardian:/tmp/

# Run the installer
ssh miningguardian@miningguardian \
  "sudo installer -pkg /tmp/MiningGuardian-1.0.0-0f849bd217cc.pkg -target /"

# Watch logs during Phase 11 (Slack token entry)
ssh miningguardian@miningguardian "tail -f /var/log/install.log"
```

---

## Why we have three addresses

| Address | When it works | When it doesn't |
|---|---|---|
| `192.168.188.100` (LAN static) | Office Wi-Fi or Ethernet | Anywhere off-site |
| `miningguardian.local` (mDNS) | Same LAN segment | Off-site, or across VLANs |
| `100.69.66.32` (Tailscale IP) | Anywhere on tailnet | Off tailnet |
| `miningguardian` (Tailscale MagicDNS) | Anywhere on tailnet | Off tailnet |

You don't need to memorize the IPs — the two **names** (`miningguardian.local` for office, `miningguardian` for remote) cover every case.

---

## Sources / references

- Tailscale MagicDNS docs: https://tailscale.com/kb/1081/magicdns
- Tailscale SSH: https://tailscale.com/kb/1193/tailscale-ssh
- macOS Remote Login (Settings → General → Sharing → Remote Login)
