# Mining Guardian — Headless Mac Mini Addendum

**Companion to:** `docs/RUNBOOK_INSTALL_DAY_2026-04-30.md`
**Date:** 2026-04-30
**Tag:** `v1.0.0-install-ready` @ `b6b7d72`

> **Read this BEFORE Section 1 of the main runbook.** This addendum reorders the install so the Mac Mini ends up running headless (no keyboard, no mouse, no monitor) by the end of the day, with SSH and Screen Sharing as the only access paths.

---

## Why this exists

The Mac Mini is a **server**, not a desktop. After install day, it must run with:
- No monitor
- No keyboard
- No mouse
- No physical input of any kind

But install day **requires** a monitor and keyboard for the macOS Setup Assistant. There is no way around that — Apple does not let you skip it without a display. So the plan is: **keep peripherals attached through smoke tests, then unplug and walk away.**

---

## Critical rules

1. **DO NOT enable FileVault.** A headless Mini cannot auto-unlock FileVault after a power outage. The runbook does not enable it — confirm it stays OFF in System Settings → Privacy & Security.
2. **DO NOT skip Screen Sharing setup.** SSH alone is enough for 99% of work, but if something breaks at the GUI layer (e.g. a Gatekeeper prompt, a Software Update modal, a kernel-extension consent dialog), you need Screen Sharing to click through it remotely.
3. **DO NOT unplug peripherals until BOTH SSH and Screen Sharing are verified working from your laptop.** Verify the path BEFORE you remove the safety net.
4. **DO NOT enable auto-login** unless you accept that anyone with physical access boots straight to your desktop. For a server in a locked room or office, auto-login is fine and recommended (it lets the Mini come back from a power outage without anyone typing a password). For a server in an open area, leave it off.

---

## Phase H1 — Pre-arrival checklist (do this BEFORE you touch the Mini)

### On your router
1. Identify the MAC address of the Mac Mini's Ethernet port (printed on the box, or visible in System Settings after first boot).
2. Reserve a **static IP** for that MAC — pick an IP outside your DHCP pool, e.g. `192.168.1.50`.
3. Write that IP down. You'll need it for SSH.

### On your laptop (the machine you'll SSH from)
**On macOS or Linux:** Nothing to install — `ssh`, `scp`, and Screen Sharing (Finder → Go → Connect to Server → `vnc://192.168.1.50`) all work out of the box.

**On Windows:** Install one of:
- **Windows Terminal** (built-in OpenSSH client — works with `ssh user@ip` exactly like macOS/Linux)
- **PuTTY** (classic, more options, free)
- For Screen Sharing: **RealVNC Viewer** or **TigerVNC** (free)

### Generate an SSH key pair on the laptop (recommended, not required)
```bash
# macOS / Linux / Windows Terminal
ssh-keygen -t ed25519 -C "rob-laptop-$(hostname)" -f ~/.ssh/mg_mini_ed25519
# Press enter for empty passphrase, OR set one if you want extra security
# (you'll just have to type it on every connection)
```
This produces two files:
- `~/.ssh/mg_mini_ed25519` (private — never share, never copy off the laptop)
- `~/.ssh/mg_mini_ed25519.pub` (public — safe to copy anywhere)

You'll install the `.pub` on the Mini in Phase H3 below.

---

## Phase H2 — During Section 1 of the main runbook (peripherals still attached)

When the main runbook says "**Section 1, step 4**: set System Settings", do these IN THIS ORDER. The order matters because Screen Sharing depends on Sharing being open at all.

### Network
- **System Settings → Network → Ethernet → Details → TCP/IP**
  - Confirm the IP your router reserved is showing up (`192.168.1.50` or whatever you chose)
  - If it's not there, set "Configure IPv4: Manually" and enter it
- **System Settings → Network → Ethernet → Details → DNS** — leave on automatic unless you have a reason

### Sharing — turn on REMOTE LOGIN and SCREEN SHARING
- **System Settings → General → Sharing**
  - **Computer Name:** `mg-mac-mini`
  - **Local hostname:** `mg-mac-mini.local` (auto-set from Computer Name)
  - **Remote Login (SSH):** ON
    - "Allow access for: Only these users" → add user `mg`
    - Note the SSH command shown at the bottom: `ssh mg@192.168.1.50`
  - **Screen Sharing:** ON
    - "Allow access for: Only these users" → add user `mg`
    - "Anyone may request permission to control screen": **OFF**
    - "VNC viewers may control screen with password": **ON** if you want non-Apple clients (RealVNC, TigerVNC) to work — set a separate VNC password (NOT your account password)

### Energy (already in main runbook, but extra-critical headless)
- **System Settings → Energy**
  - Prevent automatic sleeping when display is off → **ON**
  - Wake for network access → **ON**
  - Start up automatically after a power failure → **ON**

### FileVault (CONFIRM OFF)
- **System Settings → Privacy & Security → FileVault** → must read "FileVault is turned off"
- If it's on, turn it off. Headless Macs cannot auto-unlock FileVault after a reboot.

### Auto-login (your call — see "Critical rules" rule 4)
- **System Settings → Users & Groups → click ⓘ next to user → Automatic login**
- For a Mini in a locked office/room: **ON** (recommended — survives power outages without intervention)
- For a Mini in an open area: **OFF**

### Software Update — disable automatic
- **System Settings → General → Software Update → Automatic Updates** → click ⓘ
  - "Check for updates": **OFF**
  - "Download new updates when available": **OFF**
  - "Install macOS updates": **OFF**
  - "Install application updates from App Store": **OFF**
  - "Install Security Responses and system files": **ON** (critical security only)

We pin macOS for the install. Updates happen on a planned cadence post-install, never as a surprise reboot.

---

## Phase H3 — Install your SSH public key on the Mini (peripherals still attached)

**On the Mac Mini (Terminal):**
```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
```

**On your laptop:**
```bash
# Print your public key
cat ~/.ssh/mg_mini_ed25519.pub
# Copy the entire output (one long line starting with "ssh-ed25519 AAAA...")
```

**Back on the Mac Mini (Terminal):**
```bash
# Edit authorized_keys and paste the public key as a new line
nano ~/.ssh/authorized_keys
# Paste, then Ctrl+O, Enter, Ctrl+X to save and exit
cat ~/.ssh/authorized_keys
# Should show your public key
```

---

## Phase H4 — Smoke-test remote access (peripherals still attached)

**This is the critical "verify before unplugging" step.** Do this with the Mini's monitor/keyboard still connected so you can fix anything that fails.

### From your laptop terminal:
```bash
# 1. SSH login (should not prompt for password if your key is installed)
ssh -i ~/.ssh/mg_mini_ed25519 mg@192.168.1.50
# You should see the Mini's prompt. Type `whoami` — should print `mg`.
# Type `exit` to disconnect.

# 2. SCP a test file
echo "headless test" > /tmp/headless.txt
scp -i ~/.ssh/mg_mini_ed25519 /tmp/headless.txt mg@192.168.1.50:/tmp/
ssh -i ~/.ssh/mg_mini_ed25519 mg@192.168.1.50 "cat /tmp/headless.txt && rm /tmp/headless.txt"
# Should print "headless test"
```

### Screen Sharing
- **macOS laptop:** Finder → Go menu → Connect to Server → `vnc://192.168.1.50` → connect with the user `mg` and that user's password (NOT your VNC password unless you enabled the VNC-viewer option). You should see the Mini's desktop.
- **Windows laptop:** Open RealVNC Viewer → enter `192.168.1.50` → connect with the VNC password you set in Phase H2.

If Screen Sharing fails: the most common cause is "Screen Sharing" being disabled while "Remote Management" is enabled (those two are mutually exclusive). Toggle Remote Management OFF in Sharing, then Screen Sharing ON.

**If both SSH and Screen Sharing work — proceed. If either fails — fix it before unplugging anything.**

---

## Phase H5 — Run the install (peripherals still attached)

Continue with the main runbook **Sections 2–6** as written. Keep the keyboard, mouse, and monitor connected throughout. Specifically, Phase 11 of `setup.sh` will prompt for Slack tokens — type them in at the local console.

When Section 6 ("First scan") passes and the alerts channel sees the "scan complete" post, proceed to Phase H6.

---

## Phase H6 — Cutover to headless

**ONLY after all of Section 5 and Section 6 have passed.** Do not skip the smoke tests.

### On the Mini (last commands at the local console):
```bash
# Confirm the Mini will survive a reboot without anyone touching it
# 1. Auto-launch test (only if you enabled auto-login in Phase H2)
sudo reboot
# Wait 60 seconds. Then from your laptop:
```

### From your laptop (while the Mini reboots):
```bash
# Wait for ping to come back
while ! ping -c 1 -W 1 192.168.1.50 >/dev/null 2>&1; do echo "waiting..."; sleep 2; done
echo "Mini is back."

# SSH in
ssh -i ~/.ssh/mg_mini_ed25519 mg@192.168.1.50

# Confirm daemons came back
sudo launchctl list | grep miningguardian
# Expect 9 entries (same as Section 5.1)

# Confirm dashboard API is up
curl -fsS http://127.0.0.1:8080/api/health
```

If the Mini comes back clean from a reboot — **you can unplug peripherals.** It survives power outages by definition.

### Unplug order (doesn't actually matter, but for completeness)
1. Monitor (HDMI/USB-C)
2. Mouse (USB)
3. Keyboard (USB / Bluetooth)
4. Power → Ethernet → leave plugged in

The Mini will continue running. It does not know or care that the peripherals are gone.

---

## Phase H7 — Daily-driver remote access cheat sheet

Pin this somewhere you'll find it.

```bash
# SSH in
ssh -i ~/.ssh/mg_mini_ed25519 mg@192.168.1.50

# View install log
ssh -i ~/.ssh/mg_mini_ed25519 mg@192.168.1.50 "tail -100 ~/mg-install-*.log"

# Check daemons
ssh -i ~/.ssh/mg_mini_ed25519 mg@192.168.1.50 "sudo launchctl list | grep miningguardian"

# Restart a single daemon (e.g. dashboard-api)
ssh -i ~/.ssh/mg_mini_ed25519 mg@192.168.1.50 "sudo launchctl kickstart -k system/com.miningguardian.dashboard-api"

# Pull latest code + restart
ssh -i ~/.ssh/mg_mini_ed25519 mg@192.168.1.50 "cd ~/code/Mining-Guardian && git pull && sudo launchctl kickstart -k system/com.miningguardian.scanner"

# Open Grafana from laptop
open http://192.168.1.50:3000  # macOS — opens browser

# Screen Sharing (macOS Finder)
# Cmd+K → vnc://192.168.1.50

# Reboot the Mini remotely (only when necessary)
ssh -i ~/.ssh/mg_mini_ed25519 mg@192.168.1.50 "sudo shutdown -r now"
```

---

## Troubleshooting headless-specific issues

### "I can't SSH in — connection refused"
- Confirm Remote Login is still on: `ssh` to nothing happens means the SSH daemon isn't running. Connect via Screen Sharing and re-enable Remote Login.
- Confirm the IP didn't change: on your router, check the DHCP lease for the Mini's MAC. If it shifted off your reservation, fix the reservation and reboot the Mini.

### "I can't SSH and I can't Screen Share — Mini is unreachable"
- Ping the Mini: `ping 192.168.1.50`. If no reply, it's a network problem (cable, router, switch).
- If ping works but neither SSH nor Screen Sharing connect: a firewall or sharing-services issue. **You'll need to plug the monitor back in to fix it.** This is why Phase H4 exists — verify before you walk away.

### "Mini won't come back after a power outage"
- FileVault is the #1 cause. Plug a monitor in, log in physically, turn FileVault OFF.
- Auto-login disabled is the #2 cause. Plug in, enable auto-login (or accept that you'll need to physically unlock after every outage).
- "Start up automatically after a power failure" was off. Plug in, turn it on (System Settings → Energy).

### "Screen Sharing is laggy / pixelated"
- Some Mac Minis throttle GPU when no display is attached. This affects Screen Sharing performance, not the underlying server. Two options:
  1. Plug in an HDMI dummy plug (cheap, ~$8 on Amazon, search "HDMI 4K headless plug")
  2. Just live with it — SSH is the primary path; Screen Sharing is the safety net

### "I forgot the Mini's IP"
- From your laptop's network: `arp -a | grep -i mac` (looks for "Apple" in vendor field)
- Or: `dns-sd -B _ssh._tcp` (macOS) — discovers SSH-advertising hosts on the LAN
- Or: connect to the router admin and check DHCP leases

---

## End-of-cutover checklist

When all of these are checked, the Mac Mini is officially in production headless mode:

- [ ] Static IP reserved on router and confirmed on Mini
- [ ] FileVault confirmed OFF
- [ ] Auto-login set per your security stance
- [ ] "Wake for network access" + "Auto-restart after power failure" + "Prevent sleep when display off" all ON
- [ ] Remote Login (SSH) ON, key-based auth working from laptop
- [ ] Screen Sharing ON, working from laptop
- [ ] All 9 launchd daemons running (Section 5.1)
- [ ] Dashboard API + Grafana reachable from laptop browser
- [ ] One full reboot cycle survived without peripherals attached
- [ ] Monitor, keyboard, mouse unplugged
- [ ] Tag pushed: `v1.0.0-installed-mac-mini-YYYYMMDD`
- [ ] `MG_UNIFIED_TODO_LIST.md` install row flipped to ✅

---

*Generated 2026-04-30 morning by Computer (headless install addendum).*
