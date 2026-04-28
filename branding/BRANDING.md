# Mining Guardian — Brand System

**Owner:** Bobby Fiesler
**Curated by:** Computer (Lead Architect)
**Last updated:** April 21, 2026
**Status:** Official — use this for every customer-facing surface

---

## The Vibe (In One Sentence)

**A futuristic, industrial-grade mining fleet command center — chrome armor, electric blue energy, Bitcoin orange fire, deep space-black backgrounds.**

Not cute. Not soft. Not minimal. **Bold, hero-tier, serious, and impossible to mistake for anyone else's product.**

---

## The Story Behind the Mark

The primary logo tells you exactly what this product does in one glance:

- **The guardian helmet** — a sentinel watching over the fleet 24/7. Silver armor with orange visor/eyes. The AI is alert.
- **Crossed pickaxes** — this is mining. Industrial work. Not a trading app. Not a dashboard. A tool.
- **The Bitcoin coin crown** — SHA-256 only. We protect Bitcoin mining operations. Period.
- **Electric circuits in the background** — this is software-defined infrastructure. AI-first.
- **Blue sparks and orange lightning** — energy, vigilance, speed.
- **Shield frame** — protection is the core value proposition.

When a customer sees this logo, they should feel: *"This software knows what it's doing. Serious operators run this."*

---

## Color Palette

Extracted directly from the hero logos. Every color has a role.

### Primary Colors

| Role | Name | Hex | RGB | Use |
|------|------|-----|-----|-----|
| **Background** | Space Black | `#0A0E1A` | 10, 14, 26 | Main background. Deep navy-black. The "starfield" behind everything. |
| **Background Alt** | Deep Navy | `#001848` | 0, 24, 72 | Secondary panels, card backgrounds, layered surfaces. |
| **Accent Primary** | Bitcoin Orange | `#F7931A` | 247, 147, 26 | THE accent. Actions, highlights, the BTC coin, "live" indicators. The official Bitcoin orange. |
| **Accent Secondary** | Electric Blue | `#2BB4FF` | 43, 180, 255 | Secondary accent. Tech/data elements, info panels, the "Guardian" wordmark blue. |
| **Metal Primary** | Chrome Silver | `#D8D8D8` | 216, 216, 216 | Primary headings, logo lettering, "Mining" wordmark. |
| **Metal Highlight** | Bright Silver | `#F0F0F0` | 240, 240, 240 | Highlights on metal surfaces, pure white replacement. |
| **Metal Shadow** | Steel Gray | `#606060` | 96, 96, 96 | Depth on metal surfaces, borders, rule lines. |

### Semantic Colors (For UI States)

| Role | Hex | RGB | Use |
|------|-----|-----|-----|
| **Success** | `#26D962` | 38, 217, 98 | ✅ checkmarks, healthy status, passing checks |
| **Warning** | `#F7931A` | 247, 147, 26 | ⚠️ warnings — same as Bitcoin Orange (double-duty) |
| **Error / Alert** | `#FF3B30` | 255, 59, 48 | ❌ errors, critical alerts, failed checks |
| **Info** | `#2BB4FF` | 43, 180, 255 | ℹ️ info messages — same as Electric Blue |
| **Muted Text** | `#A8A8A8` | 168, 168, 168 | Secondary info, labels, captions |

### Color Rules

1. **Black is the canvas.** Never use white backgrounds. Dark always.
2. **Orange is Bitcoin. Use it sparingly for impact.** Never for bulk body text.
3. **Blue is the technology.** Use for data, tech, "info" — never mix with orange on the same accent.
4. **Chrome/silver is the voice.** Headings and the product name.
5. **Never use more than 3 accent colors on a single screen.** Orange + blue + silver is the max. Add semantic (green/red) only when needed.

---

## Logo Usage

### The Mark Library

All logos live in `branding/logos/`:

```
logos/
├── primary/              ← Use these first
│   ├── mg-shield-primary.png      ← Main hero logo (SET A style)
│   ├── mg-shield-setB.png         ← Alternative shield treatment
│   ├── mg-roundel.png             ← Circular "MG" roundel
│   ├── mg-roundel-setB.png        ← Alternative roundel
│   ├── mg-no-background.png       ← Transparent version
│   └── mg-black-background.png    ← Black background version
├── wordmark/             ← When space is limited
│   ├── mg-wordmark-stacked.png    ← MINING/GUARDIAN stacked
│   ├── mg-wordmark-horizontal.png ← Single line
│   └── mg-wordmark-horizontal-setB.png
├── icons/                ← App icons, favicons
│   ├── mg-app-icon-orange.png     ← Red-orange background app icon
│   ├── mg-app-icon-round.png      ← Round app icon
│   └── mg-icon-neon.png           ← Neon effect icon
└── badges/               ← Badges and seals
    ├── mg-badge-gold.png          ← Gold/bronze shield badge
    ├── mg-badge-silver.png        ← Silver shield badge
    └── mg-badge-blue.png          ← Blue shield badge
```

### Which Logo When

| Use Case | Logo | Why |
|----------|------|-----|
| **Installer welcome screen** | ASCII rendering of shield-primary | Hero moment. Set the tone. |
| **Dashboard header** | `mg-wordmark-horizontal.png` | Wide format, reads left-to-right |
| **Favicon / tab icon** | `mg-app-icon-round.png` | Square, scales to 32px |
| **Slack bot avatar** | `mg-roundel.png` | Circular crop needed |
| **Mac menu bar icon** | Monochrome silver version (to build) | Menu bars need simple shapes |
| **Customer documentation** | `mg-shield-primary.png` | Full hero treatment |
| **Email signatures** | `mg-wordmark-horizontal.png` | Wide, small |
| **GitHub README** | `mg-shield-primary.png` | Full hero |
| **Marketing / web hero** | `mg-spectrum-hero.png` | The showcase spectrum piece |
| **Inside reports/PDFs** | `mg-badge-silver.png` | Subtle watermark |

### Clearspace & Minimum Size

- **Clearspace:** Minimum 10% of logo height on all sides. Never cramp the mark.
- **Minimum size:**
  - Shield logo: 120px wide minimum (digital), 1 inch wide minimum (print)
  - Roundel: 64px wide minimum
  - Wordmark: 200px wide minimum

### What NOT to Do

- ❌ **Don't recolor the logo.** The colors are part of the identity.
- ❌ **Don't stretch or distort.** Scale proportionally only.
- ❌ **Don't put on busy backgrounds** — use the black-background version if the surface is noisy.
- ❌ **Don't add effects** — no drop shadows, bevels, outer glows. The logo already has depth baked in.
- ❌ **Don't use the logo and wordmark together** — pick one. They already include each other.

---

## Typography

### The Installer (Terminal)

Terminals are monospace-only. Rich library renders with the user's terminal font.
- **Headings in the wizard:** Bold `chrome_silver` — large Rich `Panel` titles
- **Body text:** Default terminal color (cream/off-white against black)
- **Accent highlights:** `bitcoin_orange` for interactive elements, `electric_blue` for data

### Documentation, Dashboards, Web

For anywhere that supports real typography:

| Role | Font | Fallback | Why |
|------|------|----------|-----|
| **Display / Hero** | [Chakra Petch](https://fonts.google.com/specimen/Chakra+Petch) | Orbitron, Rajdhani | Futuristic, industrial, reads well at size |
| **Headings** | [Space Grotesk](https://fonts.google.com/specimen/Space+Grotesk) | Inter | Clean, modern, confident |
| **Body** | [Inter](https://fonts.google.com/specimen/Inter) | SF Pro, system-ui | Workhorse — extremely legible |
| **Code / Data** | [JetBrains Mono](https://www.jetbrains.com/lp/mono/) | Menlo, monospace | Clearly differentiated I/l/1, 0/O |

### Bobby's Note About Comic Sans

Bobby mentioned he likes Comic Sans for the friendly feel. **Comic Sans doesn't match this brand** — the logos are industrial/futuristic, not playful. But the *intent* (friendly, approachable, not intimidating) should still come through in:

- **Voice and tone of copy** (see below)
- **Generous spacing** and clear hierarchy in layouts
- **Warm accent colors** (the orange feels friendlier than cold blue alone)
- **Clear, jargon-free language** in every customer-facing surface

---

## Voice & Tone

### Personality

- **Confident but not arrogant** — "Mining Guardian is monitoring your fleet" (not "Our advanced AI")
- **Plain-spoken** — "247 miners online" (not "247 endpoints enumerated")
- **Direct** — "Slack setup failed. Check your bot token." (not "An error has occurred")
- **Human** — "Setting up your site..." (not "Initializing deployment")

### Words We Use

- ✅ miner, fleet, site, operator, hashrate, cooling, firmware
- ✅ set up, check, verify, watch, protect, respond
- ✅ healthy, overheating, offline, stale, learning

### Words We Avoid

- ❌ "Disrupt", "revolutionize", "next-gen" — marketing fluff
- ❌ "Scrape", "crawl" — sounds invasive
- ❌ "Blockchain", "Web3", "Decentralized" — we're Bitcoin miners, period
- ❌ "AI-powered" as a buzzword — say what the AI does

### Sample Copy

**Good:**
> "Mining Guardian is watching your fleet. If something goes wrong, we'll ask you before taking action."

**Bad:**
> "Mining Guardian leverages cutting-edge AI to provide best-in-class fleet monitoring."

---

## Rich Terminal Color Palette (Installer)

These are the exact Rich library color constants we'll use in `wizard.py`:

```python
# branding/terminal_colors.py
BRAND_COLORS = {
    # Backgrounds (Rich handles these via styles)
    "bg_primary":      "#0A0E1A",   # space_black
    "bg_secondary":    "#001848",   # deep_navy

    # Accents
    "orange":          "#F7931A",   # bitcoin_orange - primary accent
    "blue":            "#2BB4FF",   # electric_blue - secondary accent
    "silver":          "#D8D8D8",   # chrome_silver - headings
    "silver_bright":   "#F0F0F0",   # bright_silver - highlights

    # Semantic
    "success":         "#26D962",   # green
    "warning":         "#F7931A",   # orange (reused)
    "error":           "#FF3B30",   # red
    "info":            "#2BB4FF",   # blue (reused)
    "muted":           "#A8A8A8",   # gray
}

# Rich styles
PANEL_STYLES = {
    "hero":            "bold bright_white on #0A0E1A",
    "panel_border":    "#F7931A",           # orange borders on primary panels
    "panel_border_alt":"#2BB4FF",           # blue borders on info panels
    "heading":         "bold #D8D8D8",
    "accent":          "bold #F7931A",
    "success":         "bold #26D962",
    "warning":         "bold #F7931A",
    "error":           "bold #FF3B30",
    "muted":           "#A8A8A8",
}
```

---

## The Installer Aesthetic

Given everything above, here's how the installer will look:

- **Every screen: Black background, no exceptions.**
- **Header panels: Orange borders, silver titles, white/cream text.**
- **Info panels: Blue borders, silver titles.**
- **Success/fail icons: Green ✅, Red ❌, Orange ⚠️, Blue ℹ️.**
- **Progress bars: Orange fill on dark background.**
- **The "Mining Guardian" title: ASCII-rendered from the wordmark, silver with orange underline.**
- **Spacing: Generous. Never cramped.**
- **Corner style: Double-line box corners (`╔╗╚╝`) for the hero Welcome screen, rounded corners (`╭╮╰╯`) for step panels.**

---

## Asset Delivery Roadmap

### Now (Have)
- ✅ Primary logos (Set A, Set B) in PNG
- ✅ Roundels, wordmarks, badges
- ✅ App icons
- ✅ Artwork spectrum pieces

### Needed (Will Build)
- 🔲 **SVG versions** of the primary shield — for web/docs scaling
- 🔲 **Monochrome/silhouette version** for Mac menu bar (16x16, 32x32)
- 🔲 **Favicon set** (16, 32, 48, 96, 192, 512px)
- 🔲 **ASCII art version** of the shield for terminal rendering
- 🔲 **Slack bot avatar** (PNG, 512x512, transparent background)
- 🔲 **Email signature template** (logo + tagline)
- 🔲 **GitHub social preview** (1280x640)
- 🔲 **Customer install cover page** (for docs / install reports)

---

## Changelog

| Date | Change | By |
|------|--------|-----|
| 2026-04-21 | Initial brand system captured from 60+ logo variants | Computer |

---

*This document governs every customer-facing surface. When in doubt, return here.*
