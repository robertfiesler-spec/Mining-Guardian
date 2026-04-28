# Mining Guardian — Locked Decisions

This is the canonical log of decisions that are committed and not subject to re-litigation without an explicit reversal entry. Each entry has the date it was locked, the question that was on the table, what was decided, and who decided it.

> Format borrowed from ADR-style records but kept lightweight. Append-only. To reverse a decision, add a new entry that references the old number.

---

## D-1 — `MG_DB_PASSWORD` rotation
- **Date locked:** 2026-04-24
- **Decided by:** Operator (Bobby) + agent
- **Decision:** New operational Postgres password is `tX-fhG#iJdm{V?>uuZ35G-Y)O5<UeN=5` (192-bit). Stored in `.env` files only, chmod 600. Never committed to git in any form.
- **Why:** Old password `MiningGuardian2026!` had leaked across at least 29 source locations including `docs/SESSION_HANDOFF_2026-04-24.md`. Hard-rotation required.
- **Implementation status (as of 2026-04-26):** 🔴 Pending — applies during CRIT-1 purge on Monday 2026-04-27.

---

## D-2 — `auto_approve_enabled` default
- **Date locked:** 2026-04-24
- **Decided by:** Operator + agent
- **Decision:** `auto_approve_enabled` defaults to `False` in all config templates and example envs. Customers must explicitly opt in.
- **Why:** Auto-approving miner restarts and config writes without human-in-the-loop is a customer-trust problem on first install. Default-deny matches the operator philosophy.
- **Implementation status (as of 2026-04-26):** ⏸ Status unknown — verify during Monday cleanup.

---

## D-3 — `outcome_checker.py` rewrite via psycopg
- **Date locked:** 2026-04-25
- **Decided by:** Operator + agent
- **Decision:** Replace the SQLite-era `outcome_checker.py` with a clean psycopg implementation. No shim, no compat layer.
- **Why:** Original module assumed SQLite quoting and column types. Half-shimming it produced two follow-up GROUP BY bugs (CR-5 phases 1 and 1B). Cleaner to rewrite.
- **Implementation status (as of 2026-04-26):** ✅ Done in PR #4 (commit `bcfbd58`).

---

## D-4 — `mg_import` session TTL
- **Date locked:** 2026-04-24
- **Decided by:** Operator + agent
- **Decision:** `MG_IMPORT_SESSION_TTL_SECONDS=28800` (8 hours).
- **Why:** Customer-side log import sessions need to survive a working day but expire overnight. 8 hours is the working compromise.
- **Implementation status (as of 2026-04-26):** 🔴 Pending — applies during CRIT-3 on Monday 2026-04-27.

---

## D-5 — `mg_import` HTML password input + handoff doc
- **Date locked:** 2026-04-24
- **Decided by:** Operator + agent
- **Decision:**
  - 5a: `mg_import` HTML password input value attribute = `""` (empty). No pre-fill.
  - 5b: `docs/SESSION_HANDOFF_2026-04-24.md` keeps the literal old password for historical accuracy AND adds a top-of-file note explaining it's been rotated and is non-functional.
  - 5c: Run `grep` for the old password literal one more time at apply time to catch anything new that leaked between then and now.
- **Why:** Avoids accidentally pre-filling a known string while preserving forensic value of the handoff doc.
- **Implementation status (as of 2026-04-26):** 🔴 Pending CRIT-1.

---

## D-6 — `migrate_to_postgres.py` import guard
- **Date locked:** 2026-04-24
- **Decided by:** Operator + agent
- **Decision:** `migrations/migrate_sqlite_to_postgres.py` raises an exception on import unless environment variable `MG_ALLOW_MIGRATION=1` is set.
- **Why:** Prevents accidental re-runs that could overwrite live Postgres data with stale SQLite contents.
- **Implementation status (as of 2026-04-26):** ⏸ Verify in current code — defer hard-deletion of the script to post-Mac-Mini.

---

## D-7 — Ollama hosting
- **Date locked:** 2026-04-26
- **Decided by:** Operator
- **Decision:** Ollama runs on the Mac Mini exclusively. Removed from `robs-pc`. Mac Mini hosts the entire customer install.
- **Why:** Operator quote: "Real quick ollama will now be on the Mac mini, no longer on the pc, it will all be contained on the new mac." Reduces moving parts, eliminates a cross-host dependency, makes the customer install self-contained.
- **Implementation status (as of 2026-04-26):** Built into installer rebuild and Section 7 of the unified to-do.

---

## D-8 — Ollama model on Mac Mini
- **Date locked:** 2026-04-26
- **Decided by:** Operator + agent recommendation accepted
- **Decision:** Ollama model = `qwen2.5:14b-instruct-q4_K_M`. NOT `qwen2.5:32b`.
- **Why:** Mac Mini envelope is 16 GB unified RAM. The 32b quant would eat ~20 GB resident and force swap, making inference too slow for the operational loop. The 14b q4 quant fits comfortably with headroom for the rest of the stack.
- **Implementation status (as of 2026-04-26):** Locked in installer Phase 8.

---

## D-9 — Mac Mini network and remote access
- **Date locked:** 2026-04-26
- **Decided by:** Operator + agent
- **Decision:**
  - Mac Mini sits on the miner LAN `192.168.188.0/24`
  - Tailscale installed for remote operator access only — data plane stays local
  - `OLLAMA_URL=http://localhost:11434/api/generate`
  - `CATALOG_DB_HOST=localhost`
- **Why:** Local-only data plane keeps inference and DB traffic off Tailscale (latency, exit-node concerns). Tailscale is purely for SSH/remote ops convenience.
- **Implementation status (as of 2026-04-26):** Encoded in installer Phase 12.

---

## D-10 — Mac Mini install date
- **Date locked:** 2026-04-26
- **Decided by:** Operator
- **Decision:** Mac Mini install moves to **Monday 2026-05-05**. Previously planned for Tuesday/Wednesday 2026-04-28/29.
- **Why:** Operator quote: "I would like everything done before we install on the Mac Mini. I truly want this to be a 100% representative of what customer would receive and load. All patches all fixes done. Paper written. I want to be our first customer. So if we push loading on the mini out that is fine. We were planing on May 5 anyway. I did not realize how far out we were. Remember slow and steady. I would rather be late and perfect than early and wrong."
- **Implementation status (as of 2026-04-26):** Active — see `docs/ROADMAP_TO_MAC_MINI_2026-05-05.md` for day-by-day plan.

---

## D-11 — Cutover gate (customer-grade exit criteria)
- **Date locked:** 2026-04-26
- **Decided by:** Operator's customer-#1 framing
- **Decision:** Mac Mini install does not happen until all 8 exit criteria in `docs/ROADMAP_TO_MAC_MINI_2026-05-05.md` are green:
  1. No leaked secrets in repo
  2. No hardcoded passwords or default API keys
  3. No dead code shipping (OpenClaw + orphan tables removed)
  4. One canonical catalog schema (N6 done)
  5. AI has data (C4 + C1/C3 done)
  6. Installer creates a working system from a blank Mac in one pass
  7. Daily paper trail in `SESSION_LOG_YYYY-MM-DD.md`
  8. Customer-facing docs done (Setup Manual + Program Instructions + Brochure)
- **Why:** Customer-#1 framing requires the install path to match what a paying customer receives.
- **Implementation status:** Active gate.

---

## D-12 — Documentation cadence
- **Date locked:** 2026-04-26
- **Decided by:** Operator
- **Decision:** Every working day from now through cutover gets a `SESSION_LOG_YYYY-MM-DD.md` committed. Decisions are appended to this file. Roadmap (`docs/ROADMAP_TO_MAC_MINI_2026-05-05.md`) is updated at end of day if scope shifted.
- **Why:** Operator quote: "I believe in over-documentation so we know what each day brings."
- **Implementation status:** Active.

---

## D-13 - Ollama model selection: install-time RAM auto-detect (supersedes D-8)
- **Date locked:** 2026-04-28
- **Decided by:** Operator + agent
- **Decision:** Installer detects host RAM at install time and selects the Ollama model accordingly. Customer can override via prompt.
  - **16 GB RAM** (e.g., base Mac Mini M4) picks `llama3.2:3b` (q4 default)
  - **24 GB RAM or more** picks `qwen2.5:14b-instruct-q4_K_M`
  - **Override:** Installer surfaces the auto-detected pick and lets the customer choose a different supported model before download.
- **Why:** D-8 hard-coded `qwen2.5:14b-instruct-q4_K_M` on the assumption every Mac Mini in the deployment fleet would be 16 GB. That assumption no longer holds. We now expect a mix of 16 GB and 24 GB+ Minis at customer sites, and 14b q4 on a 16 GB host pushes the working set close to swap once Postgres, Colima, and the MG app are also resident. `llama3.2:3b` keeps the 16 GB envelope responsive; the 14b model becomes the default the moment there is headroom for it.
- **Supersedes:** D-8 (Ollama model on Mac Mini). D-8 stays in this file as the historical record; D-13 is the live policy.
- **Implementation status (as of 2026-04-28):** Pending. Encoded in `mg/pr26-mac-mini-installer` (Phase 8: model selection step).

---

*Append new decisions below this line. Do not edit history.*
