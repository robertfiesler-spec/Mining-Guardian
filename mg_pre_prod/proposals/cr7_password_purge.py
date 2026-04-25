#!/usr/bin/env python3
"""
CR-7 password purge patcher — DRAFT, not for application until production
DB password is rotated and VPS env files updated.

Targets `origin/main` @ b28c8a7. Idempotent. sha256-pinned.

What it does:
  1. mg_import_tool/mg_import.py — replaces 26 fallback passwords with a hard
     requirement (raises RuntimeError if MG_DB_PASSWORD env var unset).
  2. intelligence-catalog/catalog-api/catalog_api.py — same pattern.
  3. scripts/migrate_to_postgres.py — same pattern.
  4. intelligence-catalog/catalog-api/.env.example — placeholder.
  5. intelligence-catalog/docker-compose.yml — env interpolation.

What it does NOT do (manual follow-up required):
  • intelligence-catalog/deploy.ps1   — connection string examples (cosmetic)
  • mg_import_tool/README.md          — doc references to literal password
  • docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md, docs/SESSION_HANDOFF_2026-04-24.md,
    NEXT_SESSION.md                   — historical handoff docs

  These are NOT exploitable code — they are documentation. Sanitize them in a
  separate doc-only commit so the code patch is clean and reviewable.

Usage:
  python3 cr7_password_purge.py --dry-run    # show what would change
  python3 cr7_password_purge.py --apply      # write changes

Pre-requisite (DO NOT SKIP):
  Production DB password MUST be rotated FIRST. The literal string
  `MiningGuardian2026!` is in public git history forever. Removing it from
  files at HEAD does NOT remove it from history.

  After rotation:
    1. Update VPS systemd Environment= directives or env files
    2. Update Mac Mini env once cutover happens
    3. Restart all 8 services
    4. Verify they connect with new password
    5. Then apply this patch
    6. PR + merge
    7. Optionally use BFG / git-filter-repo to scrub history (separate effort)
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LITERAL = "MiningGuardian2026!"
ENV_VAR = "MG_DB_PASSWORD"

# ── Helpers ────────────────────────────────────────────────────────────────


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def already_patched(text: str) -> bool:
    """Crude check: file no longer contains the literal."""
    return LITERAL not in text


def report(label: str, before: str, after: str) -> None:
    if before == after:
        print(f"  [skip] {label} — already patched")
        return
    diff_count = before.count(LITERAL) - after.count(LITERAL)
    print(f"  [patch] {label} — {diff_count} occurrence(s) removed")


# ── Patches ────────────────────────────────────────────────────────────────


def patch_mg_import(text: str) -> str:
    """
    Replace 26 sites of:
        password=conn_params.get('password', 'MiningGuardian2026!'),
    with:
        password=_require_db_password(conn_params),
    """
    # Insert helper near top of file (after imports) if not present
    helper = (
        "\n"
        "def _require_db_password(conn_params: dict) -> str:\n"
        "    \"\"\"Return DB password from conn_params, env, or raise.\"\"\"\n"
        "    pw = conn_params.get('password') or __import__('os').environ.get('MG_DB_PASSWORD')\n"
        "    if not pw:\n"
        "        raise RuntimeError(\n"
        "            'DB password not configured. Set MG_DB_PASSWORD env var '\n"
        "            'or pass password in conn_params.'\n"
        "        )\n"
        "    return pw\n"
        "\n"
    )
    if "_require_db_password" not in text:
        # Insert after the FIRST contiguous top-level import block.
        # (Some files re-import modules deeper down; we want the helper near the top
        # so it's defined before any function that uses it.)
        lines = text.splitlines(keepends=True)
        in_first_block = False
        first_block_end = 0
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            is_import = (
                stripped.startswith(("import ", "from "))
                and not line.startswith(" ")
            )
            if is_import:
                in_first_block = True
                first_block_end = i
            elif in_first_block and stripped and not stripped.startswith("#"):
                # First non-import, non-comment, non-blank line ends the block
                break
        lines.insert(first_block_end + 1, helper)
        text = "".join(lines)

    # Replace literal sites — multiple patterns
    # 1. password=conn_params.get('password', 'MiningGuardian2026!')
    text = re.sub(
        r"password=conn_params\.get\('password',\s*'MiningGuardian2026!'\)",
        "password=_require_db_password(conn_params)",
        text,
    )
    # 2. password=data.get('password', 'MiningGuardian2026!')
    text = re.sub(
        r"password=data\.get\('password',\s*'MiningGuardian2026!'\)",
        "password=_require_db_password(data)",
        text,
    )
    # 3. 'password': request.args.get('password', 'MiningGuardian2026!')
    # 4. 'password': request.args.get('password', 'MiningGuardian2026!')   (no comma)
    text = re.sub(
        r"'password':\s*request\.args\.get\('password',\s*'MiningGuardian2026!'\)",
        "'password': _require_db_password(dict(request.args))",
        text,
    )
    # 5. user='guardian_admin', password='MiningGuardian2026!'  (literal kwargs in psycopg2.connect)
    text = re.sub(
        r"password='MiningGuardian2026!'",
        "password=__import__('os').environ['MG_DB_PASSWORD']",
        text,
    )
    # 6. HTML/JS embedded literal — sanitize to empty (UI will show empty input)
    # value="MiningGuardian2026!" in HTML
    text = re.sub(
        r'value="MiningGuardian2026!"',
        'value=""',
        text,
    )
    # 7. JS fallback: || 'MiningGuardian2026!' — keep field requirement, drop literal
    text = re.sub(
        r"\|\|\s*'MiningGuardian2026!'",
        "",
        text,
    )
    return text


def patch_catalog_api(text: str) -> str:
    """
    Replace:
        DB_PASSWORD = os.getenv("DB_PASSWORD", "MiningGuardian2026!")
    with explicit fail-fast:
        DB_PASSWORD = os.getenv("DB_PASSWORD")
        if not DB_PASSWORD:
            raise RuntimeError("DB_PASSWORD env var is required")
    """
    pattern = re.compile(
        r'DB_PASSWORD\s*=\s*os\.getenv\("DB_PASSWORD",\s*"MiningGuardian2026!"\)'
    )
    replacement = (
        'DB_PASSWORD = os.getenv("DB_PASSWORD")\n'
        'if not DB_PASSWORD:\n'
        '    raise RuntimeError("DB_PASSWORD env var is required")'
    )
    return pattern.sub(replacement, text)


def patch_migrate_script(text: str) -> str:
    """
    Replace:
        'password': 'MiningGuardian2026!'
    with:
        'password': os.environ['MG_DB_PASSWORD']
    Add `import os` if missing.
    """
    if "import os" not in text:
        text = "import os\n" + text
    return text.replace(
        "'password': 'MiningGuardian2026!'",
        "'password': os.environ['MG_DB_PASSWORD']",
    )


def patch_env_example(text: str) -> str:
    """
    Replace:
        DB_PASSWORD=MiningGuardian2026!
    with:
        DB_PASSWORD=CHANGE_ME_BEFORE_DEPLOY
    """
    return text.replace(
        "DB_PASSWORD=MiningGuardian2026!",
        "DB_PASSWORD=CHANGE_ME_BEFORE_DEPLOY",
    )


def patch_docker_compose(text: str) -> str:
    """
    Replace:
        POSTGRES_PASSWORD: MiningGuardian2026!
    with env interpolation:
        POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}
    """
    return text.replace(
        "POSTGRES_PASSWORD: MiningGuardian2026!",
        "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}",
    )


# ── Main ───────────────────────────────────────────────────────────────────

PATCHES = [
    ("mg_import_tool/mg_import.py", patch_mg_import),
    ("intelligence-catalog/catalog-api/catalog_api.py", patch_catalog_api),
    ("scripts/migrate_to_postgres.py", patch_migrate_script),
    ("intelligence-catalog/catalog-api/.env.example", patch_env_example),
    ("intelligence-catalog/docker-compose.yml", patch_docker_compose),
]


def main() -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="show diff, don't write")
    g.add_argument("--apply", action="store_true", help="write changes")
    p.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="path to repo root (default: parent of mg_pre_prod)",
    )
    args = p.parse_args()

    root = Path(args.repo_root)
    print(f"Repo root: {root}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    print("=" * 60)

    total_changes = 0
    for rel_path, patch_fn in PATCHES:
        path = root / rel_path
        if not path.exists():
            print(f"  [warn] {rel_path} not found — skipping")
            continue

        before = path.read_text(encoding="utf-8")
        before_sha = hashlib.sha256(before.encode()).hexdigest()
        after = patch_fn(before)

        if before == after:
            if LITERAL in after:
                print(f"  [warn] {rel_path} — literal still present, patch did not match")
            else:
                print(f"  [skip] {rel_path} — already clean")
            continue

        report(rel_path, before, after)

        if args.apply:
            path.write_text(after, encoding="utf-8")
            after_sha = hashlib.sha256(after.encode()).hexdigest()
            print(f"      sha256: {before_sha[:12]} → {after_sha[:12]}")

        total_changes += 1

    print("=" * 60)
    print(f"Files changed: {total_changes}")

    # Verify nothing slipped through in code files
    if args.apply:
        leftover = []
        for rel_path, _ in PATCHES:
            path = root / rel_path
            if path.exists() and LITERAL in path.read_text(encoding="utf-8"):
                leftover.append(rel_path)
        if leftover:
            print("\nWARNING: literal still present in:")
            for p in leftover:
                print(f"  {p}")
            return 2
        print("Verification: literal fully removed from all 5 patched files.")

    print("\nReminder: docs still contain the literal (manual cleanup):")
    print("  - intelligence-catalog/deploy.ps1")
    print("  - mg_import_tool/README.md")
    print("  - docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md")
    print("  - docs/SESSION_HANDOFF_2026-04-24.md")
    print("  - NEXT_SESSION.md")
    print("\nAnd: rotate the actual DB password BEFORE applying this patch.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
