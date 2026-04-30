# Mining Guardian Customer App — Planning Bundle

**Status:** Pre-build prep, 2026-04-30 (during install day)
**Owner:** Bobby Fiesler
**Architect:** Computer
**Read order:** 01 → 02 → 03 → 04 → 05 → 06 → 07

---

## What this folder is

You're about to build a customer-facing app on top of the Mining Guardian backend. This folder is **the complete pre-build planning package** — everything you need to read, decide on, and approve before a single line of app code gets written.

**Nothing in this folder is code.** This is decisions, roadmap, branding rules, user flows, and the questionnaire. We will not start building until the questionnaire is answered and the technical decisions are signed off.

---

## How to read this (in order)

| # | File | What it answers | Time |
|---|------|-----------------|------|
| 01 | `01_VISION_AND_SCOPE.md` | What are we building? Who is it for? What does it do at v1? | 10 min |
| 02 | `02_QUESTIONNAIRE.md` | **The decisions only you can make.** With my recommendations next to each. | 20 min |
| 03 | `03_TECHNICAL_DECISIONS.md` | Recommended stack with reasoning. You sign off. | 15 min |
| 04 | `04_BRAND_REFERENCE_CARD.md` | One-pager pulled from `BRANDING.md` — colors, fonts, logos, tone. | 5 min |
| 05 | `05_USER_FLOWS.md` | The five core flows the app must support, step by step. | 20 min |
| 06 | `06_INFORMATION_ARCHITECTURE.md` | Sitemap, screen list, navigation structure. | 10 min |
| 07 | `07_ROADMAP.md` | Phase breakdown. What ships in MVP, what comes after, milestones. | 10 min |

**Total reading time: ~90 minutes.** Read on the plane home, on the couch this weekend, whenever.

---

## What's expected of you

1. **Read 01–07 in order.** Take notes if you want.
2. **Answer the questionnaire (file 02).** It's the only file with decisions you HAVE to make — about 20 questions, each with my recommendation pre-filled. You can just say "yes to all my recommendations" if everything looks good.
3. **Sign off on the technical decisions (file 03).** Same deal — recommendations pre-filled, you approve or push back.
4. **Then we build.** Once 02 and 03 are signed off, I'll scaffold the project, build the design system in code, and start on the first screen.

---

## Ground rules I'm holding myself to

These come from your standing preferences and the brand system:

- **Local-first, no cloud-only dependencies.** Fleet data never leaves the customer's premises. Cloud LLMs are rejected.
- **Bitcoin SHA-256 miners only.** Never altcoins, never Web3, never blockchain-as-buzzword.
- **Black backgrounds, no exceptions.** Never white. The brand is space-black canvas with Bitcoin orange and electric blue accents.
- **Voice: confident but not arrogant, plain-spoken, direct, human.** Never "disrupt", "leverage", "next-gen", "AI-powered" as a buzzword.
- **Never call SQLite "live".** Never use the words "scrape" or "crawl".
- **Over-document, step-by-step, rather late and perfect than early and wrong.**
- **Don't ask for confirmation on minor decisions.** Default to my recommendation. Push back if I'm wrong.

---

## What's NOT in scope for this prep bundle

- **Any code.** Zero lines. Pure planning.
- **Mobile native apps (iOS/Android).** v1 is web. We'll talk mobile in a later phase.
- **Multi-tenant SaaS architecture.** v1 is single-customer (you), running on the Mac Mini. Multi-customer is post-v1.
- **Public marketing website.** That's a separate project.
- **Billing / payments / accounts.** Not in v1. The app authenticates one operator (you) on a private LAN.

---

## Open questions captured (answers come from file 02)

These are things past sessions didn't lock down:
- Mobile/PWA support — yes, no, later?
- Frontend framework — React vs Vue vs Svelte
- Domain name for the app
- Authentication approach (since this is local-first)
- Whether the app is local-only or also reachable over the internet (Tailscale? VPN?)

---

*Generated 2026-04-30 morning by Computer (app prep cascade, while user was at Mac Mini install).*
