# 04 — Brand Reference Card

**Source of truth:** `branding/BRANDING.md` — when this card and that file disagree, that file wins.

This is the at-a-glance card I'll keep open while building. Pin this one tab.

---

## The vibe in one sentence

**Futuristic, industrial-grade mining fleet command center — chrome armor, electric blue energy, Bitcoin orange fire, deep space-black backgrounds.**

Bold. Hero-tier. Serious. Not cute. Not minimal. Impossible to mistake for anyone else's product.

---

## Color palette (memorize the top 5)

```css
/* The 5 you'll use 95% of the time */
--bg-primary:     #0A0E1A;  /* space black — main background */
--bg-secondary:   #001848;  /* deep navy — cards, panels */
--accent-orange:  #F7931A;  /* bitcoin orange — actions, "live", warnings */
--accent-blue:    #2BB4FF;  /* electric blue — data, info, tech */
--text-primary:   #D8D8D8;  /* chrome silver — headings, body */

/* The next 4 you'll use 4% of the time */
--text-bright:    #F0F0F0;  /* highlights, hero text */
--text-muted:     #A8A8A8;  /* labels, captions */
--border:         #606060;  /* dividers, rule lines */
--bg-elevated:    #142039;  /* layered surfaces (derived, not in BRANDING.md — flag for confirm) */

/* The 4 you'll use 1% of the time (semantic) */
--success:        #26D962;
--warning:        #F7931A;  /* same as orange */
--error:          #FF3B30;
--info:           #2BB4FF;  /* same as blue */
```

### The color rules (DO NOT VIOLATE)

1. **Black is the canvas.** Never white backgrounds. Dark always.
2. **Orange = Bitcoin.** Sparingly. Never bulk body text.
3. **Blue = data/tech.** Never mix orange and blue on the same accent.
4. **Silver = voice.** Headings and product name.
5. **Max 3 accent colors per screen.** Orange + blue + silver. Add green/red only when needed.

---

## Typography

| Role | Font | Fallback | Use |
|---|---|---|---|
| **Display / Hero** | Chakra Petch | Orbitron, Rajdhani | Page titles, "MINING GUARDIAN" wordmark |
| **Headings** | Space Grotesk | Inter | Section headings, card titles |
| **Body** | Inter | system-ui | All body, labels, buttons |
| **Code / Data** | JetBrains Mono | Menlo | Hashrate values, miner IDs, hex |

**Sizing in app (tailwind tokens):**

```
text-xs    12px  /* captions, timestamps */
text-sm    14px  /* labels, secondary text */
text-base  16px  /* body */
text-lg    18px  /* card titles */
text-xl    20px  /* section headings */
text-2xl   24px  /* page titles */
text-4xl   36px  /* hero / Intelligence Report header */
```

---

## Voice & tone — the cheat sheet

### Always

- **Confident, not arrogant** — "Mining Guardian is monitoring your fleet"
- **Plain-spoken** — "247 miners online" (not "247 endpoints enumerated")
- **Direct** — "Slack setup failed. Check your bot token."
- **Human** — "Setting up your site..." (not "Initializing deployment")

### Never

- Marketing fluff: "disrupt", "revolutionize", "next-gen", "cutting-edge"
- Invasive verbs: "scrape", "crawl"
- Buzzwords: "Web3", "blockchain" (we say Bitcoin), "decentralized"
- "AI-powered" as a buzzword — say what the AI does

### Words we use

✅ miner, fleet, site, operator, hashrate, cooling, firmware
✅ set up, check, verify, watch, protect, respond
✅ healthy, overheating, offline, stale, learning

---

## Logos — which one when in the app

| Surface | File | Notes |
|---|---|---|
| **Login screen hero** | `branding/logos/primary/mg-shield-primary.png` | Big. Centered. The first impression. |
| **App header (always visible)** | `branding/logos/wordmark/mg-wordmark-horizontal.png` | Top-left, 32px tall |
| **Favicon** | `branding/logos/icons/mg-app-icon-round.png` | Generate full favicon set: 16, 32, 48, 96, 192, 512 |
| **Mobile home screen icon** | `branding/logos/icons/mg-app-icon-orange.png` | PWA manifest |
| **Empty states / 404** | `branding/logos/badges/mg-badge-silver.png` | Subtle |
| **Loading splash** | `branding/artwork/mg-spectrum-hero.png` | Full-bleed during cold load |

### Logo rules (from BRANDING.md, abbreviated)

- ❌ Don't recolor. ❌ Don't stretch. ❌ Don't add effects.
- ✅ Min sizes: shield 120px, roundel 64px, wordmark 200px wide.
- ✅ Clearspace ≥ 10% of logo height on all sides.

---

## Component patterns (the look at a glance)

### Cards / panels

```
┌─────────────────────────────────────────┐
│  ╭───────────────────────────────────╮  │  ← outer card: bg-secondary (#001848)
│  │  CHROME-SILVER HEADING            │  │  ← header text: --text-primary, Space Grotesk semibold
│  │  ─────────────────────────────    │  │  ← subtle 1px divider, --border at 30% opacity
│  │                                   │  │
│  │  Body text in chrome silver.      │  │  ← body: Inter, --text-primary
│  │  Accent values in orange:  247    │  │  ← inline data: Inter mono variant or JetBrains Mono, --accent-orange
│  │  Status                  ● ALIVE  │  │  ← status pill: rounded-full, --success bg with --text-bright
│  ╰───────────────────────────────────╯  │
└─────────────────────────────────────────┘
        ↑                       ↑
     2px orange or blue   12-16px padding
     border on hero panels  on all sides
```

### Buttons

- **Primary (the "do it" action):** Orange fill `#F7931A`, black text, 1px black inset border for depth, slight glow on hover (`box-shadow: 0 0 16px rgba(247,147,26,0.3)`)
- **Secondary:** Transparent background, 1px chrome-silver border, silver text, no glow on hover (just border brightens to `#F0F0F0`)
- **Destructive (deny, delete):** `#FF3B30` outline button → fills red on hover
- **Disabled:** 30% opacity, cursor not-allowed

### Status indicators (use everywhere)

```
●  ALIVE       --success #26D962  pulse animation 2s
●  WARN        --warning #F7931A  no pulse
●  OFFLINE     --error   #FF3B30  no pulse
●  STALE       --muted   #A8A8A8  no pulse
●  LEARNING    --info    #2BB4FF  pulse animation 2s
```

### Animations

- **Subtle by default.** All transitions ≤ 200ms.
- **Honor `prefers-reduced-motion`** — disable pulse, fades, slide-ins.
- **What animates:** status pulse (alive/learning), chart enter (200ms ease-out), modal/drawer (180ms slide), toast (220ms fade+slide).
- **What doesn't:** page transitions are instant. No router animations.

---

## Anti-patterns — these will get rejected in PR review

- ❌ White backgrounds anywhere
- ❌ Material Design "card with elevation 4" shadow stacks
- ❌ Pastel anything (pink, teal, lavender)
- ❌ Comic Sans (sorry — wrong vibe; the BRANDING.md note explicitly addresses this)
- ❌ Stock photography of generic data centers
- ❌ Emojis as primary UI elements (✅/⚠️/❌ in copy is fine; emoji-as-icon for nav is not)
- ❌ Marketing tooltips ("Try our new...!")
- ❌ Modals with rounded-2xl + backdrop-blur — too "consumer SaaS"; we use sharp-corner panels with hard 1px orange border for modals
- ❌ Gradient buttons. Flat orange. We are not Stripe.

---

## Quick sanity check (run before merging any UI)

1. Squint at the screen. Is the canvas black? If white-ish, fix.
2. Count accent colors. ≤ 3? If more, simplify.
3. Read the first sentence of body copy. Does it sound like a marketing brochure? If yes, rewrite.
4. Check status indicators. Is "alive" pulsing? Is "offline" red?
5. Hit Tab through the screen. Is focus visible? (Orange outline `2px solid #F7931A`.)
6. Toggle `prefers-reduced-motion`. Did anything still move that shouldn't?

---

*Next: `05_USER_FLOWS.md` — how each core action goes from click to done.*
