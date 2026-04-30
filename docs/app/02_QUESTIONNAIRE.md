# 02 — Questionnaire

**The decisions only you can make.** I've put my recommendation in **bold** under each. If everything looks good, you can reply "yes to all defaults" and we move on. Push back wherever you disagree.

---

## A. Reach & access

### Q1. Who can reach the app?

- **A) LAN-only.** Only devices on the same WiFi/Ethernet as the Mac Mini.
- B) LAN + Tailscale/VPN. Same as A, plus you and approved devices anywhere in the world (via Tailscale).
- C) Public internet (with login). The app is on a real domain anyone can hit.

> **My rec: B (Tailscale).** A is safest but means you can't approve a 2am alert when you're on the road. C is too risky for a tool that controls your miners. Tailscale gives you "phone reach" without exposing the Mac Mini to the public internet. Setup is ~10 minutes.

### Q2. Domain name for the app?

The Mini is `mg-mac-mini.local` on the LAN. That works in browsers but looks ugly. Options:

- **A) Stick with `mg-mac-mini.local:8443`** — zero setup, ugly but functional
- B) Buy a real domain (e.g. `miningguardian.app`) and point a subdomain at the Tailscale IP — costs $12/yr, takes 15 minutes
- C) Tailscale's free MagicDNS hostname (e.g. `mg-mini.tail-scale.ts.net`) — free, no DNS work needed

> **My rec: C (MagicDNS).** Free, no public DNS exposure, works on every Tailscale-connected device. We can revisit a real domain when you have a second customer.

### Q3. HTTPS?

- A) HTTP only on LAN — easiest
- **B) HTTPS with self-signed cert** — browser warns once per device, then trusts forever
- C) HTTPS with Let's Encrypt + a real domain — most polished but requires Q2 = B

> **My rec: B (self-signed).** The app handles miner credentials and Slack tokens. HTTPS is non-negotiable. Self-signed avoids the domain dependency.

---

## B. Authentication

### Q4. Login model?

- **A) One operator, one password.** Single login, stored as bcrypt hash in Postgres.
- B) One operator + recovery code. Same as A, plus a printable one-time recovery code.
- C) Multiple operators with roles (admin / read-only). Real auth.

> **My rec: A for v1, B for v1.1.** You're the only operator. Don't build role-based auth before we need it.

### Q5. Session duration?

- A) 1 hour idle timeout
- **B) 24 hours, "remember this device" checkbox extends to 30 days**
- C) Never expire (until explicit logout)

> **My rec: B.** You'll be on your phone half-asleep at 2am — short timeouts are infuriating. 24h with optional extension is the standard.

### Q6. 2FA?

- A) None for v1
- **B) Optional TOTP (Google Authenticator / 1Password)** for v1, off by default
- C) Required TOTP for v1

> **My rec: B.** Build the plumbing now, leave it off by default, you turn it on when you want.

---

## C. Mobile / form factor

### Q7. Mobile support strategy?

- A) Desktop browser only. Mobile is post-v1.
- **B) Responsive web app — works on phone, tablet, desktop. Same code.**
- C) Progressive Web App (PWA) — installable to home screen, works offline-ish.
- D) Native iOS/Android apps. Full mobile.

> **My rec: B for v1, C for v1.1.** Responsive web hits 90% of the value at 20% of the cost. PWA upgrade is a 1-day add-on later if you want a home-screen icon.

### Q8. Push notifications to phone?

- A) No app push for v1 — Slack is good enough
- B) Browser push notifications (works on Android, partial on iOS)
- **C) Stick with Slack for push, app for everything else** — defer browser push to v1.1

> **My rec: C.** Slack already works for push. Don't reinvent it. The app is for "I got the Slack ping, now let me see what's going on."

---

## D. Visual & interaction

### Q9. Light mode option?

- **A) Dark mode only.** The brand is space-black canvas. Light mode breaks the identity.
- B) Dark default, light optional
- C) Auto (follow system)

> **My rec: A.** The brand system is explicit: "Black is the canvas. Never use white backgrounds." Adding a light mode would dilute the identity. We can revisit if you ever feel differently.

### Q10. Animations / motion?

- A) Minimal — instant transitions, no flourishes
- **B) Subtle motion** — page transitions, status indicators pulse, charts animate in
- C) Heavy motion — hero animations, particle effects on the Intelligence Report

> **My rec: B.** Subtle motion sells "this product is alive and watching." Heavy motion is showy and slows down operators in a hurry. Always honor `prefers-reduced-motion`.

### Q11. Logo placement on every screen?

- **A) Wordmark in top-left header, roundel as favicon, full shield only on login screen.**
- B) Shield on every page header
- C) No logo in-app, only on login

> **My rec: A.** Standard pattern. The brand doesn't need shouting on every screen — operators are already there.

---

## E. Functionality scope

### Q12. Approve/deny — explanation field?

- A) Optional free-text field
- **B) Optional free-text field + canned reasons** ("not the issue", "fixing manually", "miner is in maintenance", "false positive")
- C) Required explanation for every deny

> **My rec: B.** Canned reasons train the AI faster (we can categorize denial reasons), free-text catches edge cases, no friction for quick yes/no.

### Q13. Bulk actions?

- **A) Yes — select multiple miners, apply action to all**
- B) One-at-a-time only

> **My rec: A.** When the AC fails and 12 miners overheat at once, you do not want to click 12 times.

### Q14. Show predicted profitability in Intelligence Report?

- **A) Yes — current hashrate × current BTC price − power cost = today's net**
- B) Yes, with disclaimer
- C) No — too risky to show numbers that could be wrong

> **My rec: A.** This is the "are we making money" screen. You explicitly want this. Add a small "estimate" footnote.

### Q15. Manual scan trigger?

- **A) Yes — "Scan now" button on fleet view**
- B) No — schedule only

> **My rec: A.** Operators want a "verify it's actually working" button.

### Q16. Show miner credentials in app?

- A) Yes, plain text (LAN-only context, you trust the LAN)
- **B) Stored encrypted, shown masked, "reveal" button shows once**
- C) Never shown — write-only

> **My rec: B.** Standard pattern. Lets you debug from the app without giving anyone shoulder-surfing distance the keys.

---

## F. Operations

### Q17. App update strategy?

- A) Manual — `git pull && rebuild` over SSH
- **B) "Check for updates" button** in app settings, runs the same `git pull && rebuild` server-side
- C) Auto-update on a schedule

> **My rec: B.** You stay in control. App tells you "v1.0.3 is available, click here to update," you approve. C is too aggressive for v1.

### Q18. Backup strategy for app data (settings, schedules, decisions)?

- A) Manual — operator runs `pg_dump` on a schedule
- **B) Daily automatic local Postgres dump to `/var/mining-guardian/backups/`, rotate 14 days**
- C) Cloud backup (rejected — local-first rule)

> **My rec: B.** Same Mac Mini, separate directory. If the disk dies, that's a different recovery problem; covered by your time-machine on the Mini.

### Q19. Audit log of operator actions?

- **A) Yes — every approve/deny/setting change logged with timestamp + IP**
- B) No

> **My rec: A.** Cheap to build, valuable for "what did I click last Tuesday at 3am" forensics.

### Q20. Show errors / log tail in-app?

- A) No — operators SSH in if they need logs
- **B) "Recent errors" panel on fleet view** showing last 10 daemon errors
- C) Full log streaming UI

> **My rec: B.** Defeats the whole "no SSH" goal if you have to SSH for logs. C is overkill — power users still have Grafana.

---

## G. Timing & cadence

### Q21. When do we start building?

- **A) This weekend, Saturday morning**
- B) Next week
- C) After the install has been stable for 7 days

> **My rec: A.** You said "this weekend" already — confirming.

### Q22. What's the first thing built?

- A) Login screen (brand-y, sets the visual tone)
- **B) Approve/deny screen** (the highest-value flow, validates the auth + API plumbing in one shot)
- C) Fleet view (most data-heavy, exposes most issues early)

> **My rec: B.** Highest leverage. If approve/deny works end-to-end, we know auth + API + brand + responsive layout all work. Login + fleet view come right after.

### Q23. How long does v1 take?

- A) 2 weeks of focused build
- **B) 4 weekends of part-time build (~30–40 hours total)**
- C) 6+ weeks, no rush

> **My rec: B.** Realistic given you have a day job and Mining Guardian backend operations to attend. We'll define "Phase 0 done" in two weekends.

---

## H. Open-ended (free-text)

### Q24. What's a feature you've seen in another fleet/ops app you wish we had?
> _(Your answer here — anything you've seen elsewhere that made you go "I want that")_

### Q25. What's a feature in another app you actively hated and want us to avoid?
> _(Your answer — usability anti-patterns to dodge)_

### Q26. Anything I missed?
> _(Open mic — anything about scope, brand, tone, scheduling, anything)_

---

## How to reply

Easiest format:

```
Q1: B
Q2: default
Q3: yes default
Q4: A
... etc.
Q24: I've always loved how Linear lets you keyboard-shortcut everything
Q25: hated when Notion buries my settings 4 menus deep
Q26: also want a "mute all alerts for 2 hours" button
```

If you say "yes to all defaults" and answer 24/25/26, that's enough to start.

---

*Next: `03_TECHNICAL_DECISIONS.md` for the stack recommendations.*
