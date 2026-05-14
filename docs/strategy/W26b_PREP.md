# W26b — Installer Grafana Dashboard Catch-Up (Prep & Runbook)

> **Status:** prep doc written 2026-05-13 evening. Execution date: 2026-05-14 morning.
> **Estimated wall time:** ~60 min focused work + testing buffer.
> **Risk:** Low. No live services modified. Repo-only change. No customer impact unless the .pkg is built immediately.

---

## 1 · Why this exists

After W25 (dashboard_api bind) + W25b (Postgres-strict /fleet/board_stats) + W26a (Intelligence Catalog dashboard renders), the Mini at `100.69.66.32` runs 9 fully-working Grafana dashboards:

| Dashboard | Source | Shipped in repo? |
|---|---|---|
| `intelligence_catalog_live_queries.json` | New, built in W26a | ✅ yes (PR #211) |
| `mining_guardian_ai_learning.json` | VPS tarball restore | ❌ no |
| `mining_guardian_board_health.json` | VPS tarball restore | ❌ no |
| `mining_guardian_fleet_overview.json` | VPS tarball restore | ❌ no |
| `mining_guardian_intelligence_report.json` | VPS tarball restore | ❌ no |
| `mining_guardian_main.json` | VPS tarball restore | ❌ no |
| `mining_guardian_mobile.json` | VPS tarball restore | ❌ no |
| `mining_guardian_per_miner.json` | VPS tarball restore | ❌ no |
| `mining_guardian_pool_stats.json` | VPS tarball restore | ❌ no |

The repo's `installer/macos-pkg/resources/grafana/dashboards/` currently ships only 3 May-2 dashboards (`fleet_overview.json`, `miner_models_catalog.json`, `scans_health.json`) plus W26a's catalog dashboard. The 8 VPS-restored dashboards live only on the Mini's filesystem and in backup tarballs.

**Two real problems with that:**
1. **Durability.** If the Mini's disk fails, those 8 dashboards are gone except from backup tarballs. The repo is the disaster-recovery source of truth; the Mini is the deployment target.
2. **Installer parity.** A customer running today's installer .pkg gets 3 dashboards. The same customer reproducing Bobby's production-deploy by hand gets 9 dashboards. That divergence makes "what does the customer see" an unanswerable question.

W26b closes the gap by mirroring all 8 VPS-restored dashboards into the repo.

---

## 2 · Why these dashboards live in `reference-mini/`

**5 of the 8 dashboards contain hardcoded `100.69.66.32` references** in iframe URLs and panel content:

```text
mining_guardian_ai_learning.json:       2 sites
mining_guardian_board_health.json:      1 site
mining_guardian_fleet_overview.json:    1 site
mining_guardian_intelligence_report.json: 1 site
mining_guardian_per_miner.json:         1 site
```

`100.69.66.32` is **Bobby's specific Tailscale IP**. It is not a customer's IP. Any customer running the .pkg installer and getting one of these dashboards would see broken iframes pointing at a host that doesn't exist on their network.

Three plausible ways to handle this:

| Approach | Pros | Cons |
|---|---|---|
| **A. Strip hardcoded IPs at build time** | Clean ship | Requires templating system, build-time substitution, runtime config injection. Big design surface. |
| **B. Skip the 5 IP-containing dashboards** | Simple | Loses 5 of 8 (62%). Defeats most of W26b's value. |
| **C. Ship as-is in clearly-labeled subfolder** | Honest, preserves work, surfaces the templating gap as future work | Customer .pkg shouldn't auto-deploy these |

**Decision (locked 2026-05-13 evening):** Approach C.

The dashboards go in `installer/macos-pkg/resources/grafana/dashboards/reference-mini/`. The folder name is documentation: anything inside is **Mini-specific reference content**, not for customer auto-deploy. The installer's main dashboards directory continues to hold customer-deployable dashboards only.

The proper templating fix becomes a future W item — assigned **W32** on 2026-05-14 (a dedicated session with design discussion; W27 was already taken by `field_observed_specs`).

---

## 3 · Step-by-step runbook

### Step 0 — Pre-flight (5 min)

Confirm starting state matches expectations.

```bash
cd /Users/BigBobby/Documents/GitHub/Mining-Guardian
git status                              # main, clean (modulo 3 PNGs + .claude)
git log --oneline -1                    # 5cf154f or later

# Mini reachable
ssh miningguardian@100.69.66.32 'echo ok' # should respond

# The 8 source files exist on Mini
ssh miningguardian@100.69.66.32 'ls "/Library/Application Support/MiningGuardian/grafana/dashboards/" | grep "^mining_guardian_" | grep -v "pre-w26"' | wc -l
# Expected: 8

# Tests pass before we start (regression baseline)
.venv-p018-tests/bin/python -m pytest tests/ 2>&1 | tail -3
# Expected: all pass
```

If any check fails, stop and diagnose before proceeding.

### Step 1 — Branch (1 min)

```bash
git checkout -b w26b-installer-dashboard-mirror-vps-restore
```

### Step 2 — Pull files from Mini (5 min)

```bash
mkdir -p /tmp/w26b
scp 'miningguardian@100.69.66.32:/Library/Application\ Support/MiningGuardian/grafana/dashboards/mining_guardian_*.json' /tmp/w26b/

# Verify 8 files pulled
ls /tmp/w26b/ | grep -v pre-w26 | wc -l                # expected: 8
ls /tmp/w26b/                                          # eyeball the names

# DO NOT pull the *.pre-w26-* backups — those are local-only debug artifacts
```

### Step 3 — Stage in repo (5 min)

```bash
mkdir -p installer/macos-pkg/resources/grafana/dashboards/reference-mini
cp /tmp/w26b/mining_guardian_*.json installer/macos-pkg/resources/grafana/dashboards/reference-mini/

# Verify 8 files landed
ls installer/macos-pkg/resources/grafana/dashboards/reference-mini/ | wc -l   # expected: 8

# DO NOT modify the files. Ship them byte-for-byte as the Mini has them.
git status
```

**Sanity-check:** Run a quick diff sample to make sure files match Mini byte-for-byte:

```bash
diff /tmp/w26b/mining_guardian_main.json installer/macos-pkg/resources/grafana/dashboards/reference-mini/mining_guardian_main.json
# Expected: no output (identical)
```

### Step 4 — Update installer README (10 min)

Add a section to `installer/macos-pkg/resources/grafana/README.md` (create if absent) explaining the folder structure:

```markdown
## Dashboard organization

`dashboards/` contains the customer-deployable Grafana dashboards bundled with
the .pkg installer. These dashboards must work on any customer's Mac Mini
without modification — no hardcoded IPs, no Mini-specific paths, no operator-
private references.

`dashboards/reference-mini/` contains reference snapshots of dashboards that
run on the developer Mini at 100.69.66.32. **These are not customer-deployable
as-shipped** — they contain hardcoded IP references and other Mini-specific
content. They live in the repo for durability (so a Mini disk failure doesn't
lose them) and to make the eventual templating work tractable. Future W27 will
template the IP references and promote the templated versions into the
customer-deployable set.

The customer installer's Grafana provisioning config only autoloads dashboards
from `dashboards/` (the top level), not from `reference-mini/`. The reference
folder is informational, not operational.
```

> **Note (2026-05-14):** the "Future W27" templating work referenced just
> above was assigned its real number — **W32** — once it became clear W27
> was already taken by `field_observed_specs`. See `EXECUTION_PLAN_STATUS.md`.
> A separate sibling defect (W31) surfaced during this runbook's Step 6
> smoke: 2 of the 8 dashboards (`per_miner`, `ai_learning`) use inline-
> `<script>` HTML panels that Grafana 13's sanitizer does not execute.

The provisioning config that excludes `reference-mini/` from autoload may need
to be checked or added:

```bash
cat installer/macos-pkg/resources/grafana/provisioning/dashboards/mining_guardian.yml
# Look at the `path:` field. If it autoloads recursively, we may need to
# explicitly exclude reference-mini/. If it only loads the directory it
# names, we're fine.
```

If the provisioning yaml needs adjustment, include that change in the same PR.

### Step 5 — Cohort guard test (25 min)

Write `tests/test_w26b_installer_dashboard_set.py`. Asserts in the spirit of W26a S6 (sibling sweep):

- **S1:** All 8 expected dashboards exist under `reference-mini/`. (Explicit allowlist — surfaces accidental rename/delete.)
- **S2:** Every dashboard JSON in `dashboards/` (including `reference-mini/`) parses as valid JSON. (No corruption on ship.)
- **S3:** Every dashboard has an integer `schemaVersion >= 30`. (Modern enough that Grafana 13's migrator doesn't run on load.)
- **S4:** Files under `reference-mini/` are allowed to contain hardcoded `100.69.66.32`. No assertion either way.
- **S5:** Files under `dashboards/` directly (NOT under `reference-mini/`) must NOT contain hardcoded `100.69.66.32`. This is the customer-shipability gate.
- **S6:** The `reference-mini/` folder has a README that explains its purpose (or the parent README does — verify the docs land).

Template the test on `tests/test_w26a_catalog_dashboard_grafana13_compat.py` — same shape, same docstring style, same assertion structure.

Run:
```bash
.venv-p018-tests/bin/python -m pytest tests/test_w26b_installer_dashboard_set.py -v
# Expected: 6/6 pass
```

Then full regression:
```bash
.venv-p018-tests/bin/python -m pytest tests/ 2>&1 | tail -5
# Expected: all pass
```

### Step 6 — Live-Mini smoke (5 min)

The Mini already has these files; W26b only mirrors to repo. So no Mini deploy needed. But verify the 8 dashboards still load (regression baseline before declaring done):

In Safari over Tailscale, refresh each dashboard in turn:
- `http://100.69.66.32:3000/d/<uid>/<slug>` for each of the 8

(UIDs are inside each JSON — pick them from the file content or from the dashboard sidebar in Grafana.)

Confirm each loads without panel errors. Screenshot for the PR if useful.

### Step 7 — Bundle untracked wordmark PNGs (5 min) (optional, if same PR feels right)

```bash
git status | grep mining_guardian_
# 3 untracked PNGs:
#   installer/macos-pkg/resources/grafana/mining_guardian_icon.png
#   installer/macos-pkg/resources/grafana/mining_guardian_primary.png
#   installer/macos-pkg/resources/grafana/mining_guardian_wordmark.png
git add installer/macos-pkg/resources/grafana/*.png
```

These were restored during W25 Grafana stand-up but never committed. Folding them in here is OK by Failure Mode 9 — same bug class (installer Grafana asset drift). Or split into a tiny micro-PR if you prefer the cleaner ledger.

### Step 8 — Commit & PR (10 min)

```bash
git add installer/macos-pkg/resources/grafana/dashboards/reference-mini/
git add installer/macos-pkg/resources/grafana/README.md   # if you updated it
git add tests/test_w26b_installer_dashboard_set.py
git add installer/macos-pkg/resources/grafana/*.png        # if Step 7 included

git status                                                  # eyeball

git commit -m "W26b: mirror 8 VPS-restored dashboards into installer reference-mini/

After W25 + W25b + W26a brought the Mini's Grafana to a fully-working
state with 9 dashboards, the repo's installer still shipped only 3
May-2-era dashboards + W26a's catalog dashboard. The other 8 lived
only on the Mini's filesystem and in backup tarballs.

This PR mirrors the 8 into the repo so:
1. Mini disk failure doesn't lose them (durability)
2. Installer parity reduces 'what does the customer actually see'
   ambiguity

5 of the 8 dashboards have hardcoded references to 100.69.66.32
(Bobby's Tailscale IP). They cannot be customer-deployable as-is.
Decision (per W26b_PREP §2): ship in dashboards/reference-mini/
subfolder to clearly label as Mini-specific reference content; defer
the IP-templating problem to a future W item.

Cohort guard test tests/test_w26b_installer_dashboard_set.py:
  S1: 8 expected dashboards present under reference-mini/
  S2: every dashboard JSON parses
  S3: every dashboard schemaVersion >= 30
  S4: reference-mini/ may contain hardcoded IPs (no assertion)
  S5: dashboards/ directly must NOT contain hardcoded IPs
  S6: reference-mini/ has documentation explaining its purpose

Live-Mini regression check: all 8 dashboards still load on
Grafana 13.0.1 at http://100.69.66.32:3000 (no deploy needed,
Mini already has these files; this PR only mirrors to repo).

Also folds in 3 untracked wordmark PNGs at
installer/macos-pkg/resources/grafana/mining_guardian_*.png
restored during W25. Same bug class (installer Grafana asset drift).

Test results: <fill in actual count after running>."

git push -u origin w26b-installer-dashboard-mirror-vps-restore
# Open PR, request review, merge, local cleanup
```

### Step 9 — Local cleanup post-merge

```bash
git checkout main
git pull origin main
git branch -d w26b-installer-dashboard-mirror-vps-restore
```

---

## 4 · Reversibility

Every step is reversible by `rm` or `git reset`. Nothing about W26b touches the live Mini or its services. The Mini already has these dashboards; we're snapshotting them into the repo, not deploying changes outward.

The only "risk" is shipping a customer-facing .pkg before we've finished the IP-templating work — but that risk is mitigated by Step 4 (README explains `reference-mini/` is not customer-deployable) and Step 5 S5 (cohort guard test refuses to let hardcoded IPs land in the customer-deployable dashboards/ directly).

---

## 5 · Open decisions for during execution

None expected. If you encounter:

- **A 9th dashboard you didn't expect** — stop and ask Bobby. Don't ship without confirmation.
- **A dashboard with a non-IP form of hardcoded reference** (e.g. hostname, internal URL, Slack channel ID) — stop and ask. Either it's also Mini-specific (goes in `reference-mini/`) or it represents a different bug class that doesn't belong in W26b.
- **A dashboard whose `schemaVersion` is unexpectedly low** (causing S3 to fail) — stop and ask. Either we bump it as part of W26b (Failure Mode 9 expands the cohort) or we exclude that one dashboard explicitly. Don't silently silence the test.

---

## 6 · After W26b lands

Update `docs/EXECUTION_PLAN_STATUS.md` History section with a one-line entry citing the PR number and main HEAD. Mark W26b `[X]` if you added it to the table during execution.

The next plausible W-items (in rough priority order):

1. **W24** — Grafana password secret management. Currently inlined in Mini's deployed yaml. Couples nicely with the Postgres password rotation.
2. **Postgres password rotation** — leaked in chat. Separate dedicated session, ~30-60 min.
3. **W23 final close** — `guardian_app` → `mg` standardization across the codebase. Trivial scan-and-replace.
4. **W17** — 151 naked `datetime.now()` → tz-aware. Sweep.
5. **W32** — IP templating for the `reference-mini/` dashboards so they can graduate to customer-deployable. (Originally referred to in this doc as "a future W item" / "W27 or sibling" — W27 was already taken by `field_observed_specs`, so it was assigned the real number W32 on 2026-05-14. A sibling defect, W31, also surfaced during W26b Step 6 smoke: inline-`<script>` HTML panels not executing under Grafana 13's sanitizer.)

---

*End of W26b prep. Estimated total: ~60 min focused work, 90 min including testing buffer and PR review.*
