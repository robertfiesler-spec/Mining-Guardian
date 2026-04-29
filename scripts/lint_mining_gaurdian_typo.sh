#!/usr/bin/env bash
# scripts/lint_mining_gaurdian_typo.sh
#
# B-6 regression guard. Fails (exit 1) if `Mining-Gaurdian` (the retired typo,
# missing the second `r`) appears anywhere outside the allowed-exception list.
#
# History: PR-2 (2026-04-28) replaced 65 path-string hits across 17 files with
# the canonical `Mining-Guardian`. 8 narrative hits across 4 files were
# intentionally retained as historical / warning context. This script enforces
# that boundary so the typo cannot regress on a future commit.
#
# Allowed-exception list (kept in lockstep with docs/LATENT_BUGS.md B-6):
#   - Narrative / historical references in active files:
#       CLAUDE.md
#       README.md
#       NEXT_SESSION.md
#       docs/LATENT_BUGS.md
#       docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md
#       docs/MG_UNIFIED_TODO_LIST.md
#       docs/REMAINING_WORK_2026-04-28.md
#   - Frozen historical record — dated handoff / log files (some still in
#     docs/, others moved into docs/archive/ during the 2026-04-29 doc sweep,
#     PR #91):
#       docs/DEMO_DAY_HANDOFF_2026_04_08.md
#       docs/S15_APPLIED.txt
#       docs/SESSION_2026-04-13_S21_TEST_AND_FIXES.md
#       docs/archive/**         (all historical handoffs / session logs)
#   - Frozen by design:
#       archive/**
#       fixes/2026-04-13/**
#   - Build artifact:
#       .coverage
#   - This lint's own infrastructure (must contain the typo string by
#     necessity — the script greps for it, the workflow names the job after
#     it):
#       scripts/lint_mining_gaurdian_typo.sh
#       .github/workflows/lint.yml
#
# Usage:
#   scripts/lint_mining_gaurdian_typo.sh           # from repo root
#   ./scripts/lint_mining_gaurdian_typo.sh --list  # print all current hits without filtering
#
# Exit codes:
#   0 - clean (only allowed-exception hits found)
#   1 - one or more disallowed hits found
#   2 - script error (not in repo root, grep missing, etc.)

set -euo pipefail

# Resolve to repo root regardless of cwd.
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/.." &>/dev/null && pwd)
cd "$REPO_ROOT"

if ! command -v grep >/dev/null 2>&1; then
    echo "ERROR: grep not found on PATH" >&2
    exit 2
fi

if [[ "${1:-}" == "--list" ]]; then
    echo "All current Mining-Gaurdian hits (unfiltered):"
    grep -rln 'Mining-Gaurdian' . --exclude-dir=.git 2>/dev/null || echo "(none)"
    exit 0
fi

# Allow-list: regex-anchored against the path returned by grep -l (always
# starts with `./`). Each entry is a literal-path or a directory prefix.
# Edit this list ONLY in lockstep with docs/LATENT_BUGS.md B-6.
read -r -d '' ALLOWED_PATTERNS <<'EOF' || true
^\./CLAUDE\.md$
^\./README\.md$
^\./NEXT_SESSION\.md$
^\./docs/LATENT_BUGS\.md$
^\./docs/MAC_MINI_DEPLOYMENT_RUNBOOK\.md$
^\./docs/MG_UNIFIED_TODO_LIST\.md$
^\./docs/REMAINING_WORK_2026-04-28\.md$
^\./docs/DEMO_DAY_HANDOFF_2026_04_08\.md$
^\./docs/S15_APPLIED\.txt$
^\./docs/SESSION_2026-04-13_S21_TEST_AND_FIXES\.md$
^\./docs/archive/
^\./archive/
^\./fixes/2026-04-13/
^\./\.coverage$
^\./scripts/lint_mining_gaurdian_typo\.sh$
^\./\.github/workflows/lint\.yml$
EOF

# Combine into a single anchored alternation for one grep -E.
ALLOWED_RE=$(echo "$ALLOWED_PATTERNS" | tr '\n' '|' | sed 's/|$//')

# Collect every file that contains the typo, then drop allow-listed paths.
ALL_HITS=$(grep -rln 'Mining-Gaurdian' . --exclude-dir=.git 2>/dev/null || true)

if [[ -z "$ALL_HITS" ]]; then
    echo "B-6 lint: clean (no Mining-Gaurdian hits anywhere)."
    exit 0
fi

DISALLOWED=$(echo "$ALL_HITS" | grep -E -v "$ALLOWED_RE" || true)

if [[ -n "$DISALLOWED" ]]; then
    echo "B-6 LINT VIOLATION: 'Mining-Gaurdian' typo found outside the allowed-exception list."
    echo
    echo "Disallowed hits:"
    while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        echo "  $f"
        # Show line numbers for the offending file.
        grep -n 'Mining-Gaurdian' "$f" | sed 's/^/    /'
    done <<< "$DISALLOWED"
    echo
    echo "If a new file legitimately needs to mention the typo as historical /"
    echo "narrative context, add it to BOTH:"
    echo "  - docs/LATENT_BUGS.md B-6 allowed-exception table"
    echo "  - scripts/lint_mining_gaurdian_typo.sh ALLOWED_PATTERNS"
    echo "in the same PR."
    exit 1
fi

echo "B-6 lint: clean (all $(echo "$ALL_HITS" | wc -l | tr -d ' ') hits are inside the allowed-exception list)."
exit 0
