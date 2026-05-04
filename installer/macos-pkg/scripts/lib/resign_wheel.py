#!/usr/bin/env python3
# installer/macos-pkg/scripts/lib/resign_wheel.py
#
# P-011 (2026-05-04) — re-sign every Mach-O binary inside a vendored Python
# wheel with the Developer ID Application identity, hardened runtime, and a
# secure timestamp, then update the wheel's *.dist-info/RECORD manifest so
# pip still accepts the modified wheel as a valid install source.
#
# WHY THIS EXISTS
# ---------------
# Apple's notary service walks every Mach-O file inside the .pkg payload —
# including ones embedded inside .whl archives at
#   Payload/Library/Application Support/MiningGuardian/python-wheels/*.whl/*.so
# — and rejects the submission if any of them is:
#   * not signed with a valid Developer ID Application certificate
#   * built without a secure timestamp
#   * built without hardened runtime
#
# Apple notary submission 750c089f-f0a1-4d40-bf15-e8c295828027 (2026-05-04,
# v1.0.3 first build, sha 295aec38f2ee, MiningGuardian-1.0.3-295aec38f2ee.pkg)
# returned `Invalid` for exactly this reason. Detailed log called out e.g.:
#   * aiohttp-3.13.5-cp312-cp312-macosx_*.whl/aiohttp/_http_writer.cpython-312-darwin.so
#   * aiohttp-3.13.5-...whl/aiohttp/_http_parser.cpython-312-darwin.so
#   * aiohttp-3.13.5-...whl/aiohttp/_websocket/mask.cpython-312-darwin.so
#   * aiohttp-3.13.5-...whl/aiohttp/_websocket/reader_c.cpython-312-darwin.so
#   * bcrypt-5.0.0-...universal2.whl/bcrypt/_bcrypt.abi3.so       (x86_64 + arm64)
#   * matplotlib-3.10.9-...whl/matplotlib/<multiple>.so
# All same root cause: vendored upstream wheels ship .so files that are NOT
# signed with our Developer ID. PyPI does not require it. Apple does.
#
# THE SHAPE OF THE FIX
# --------------------
# A .whl file is a ZIP archive with a manifest at <pkg>-<ver>.dist-info/RECORD.
# Each line has the form:
#   <relative_path>,sha256=<base64-urlsafe-no-pad>,<bytes>
# RECORD itself is listed without sha or size (its own line ends in ",,").
# pip verifies every file's sha256 + size against this manifest at install
# time. If we codesign a .so in place but don't update RECORD, the install
# breaks. So:
#   1. Unzip the wheel to a temp dir.
#   2. Find every Mach-O file via `file -b` (covers .so, .dylib, fat
#      universal2 binaries — codesign handles all three).
#   3. codesign --force --sign "$APPLE_DEV_ID_APPLICATION" \
#                --options runtime --timestamp <path>
#   4. For every file we modified, recompute sha256 + size and rewrite the
#      RECORD line.
#   5. Re-zip the wheel into a new file with deterministic ordering, so
#      diffs are reviewable and so wheels rebuilt on different hosts produce
#      identical bytes (modulo the codesign blob).
#
# WHAT WE DO NOT DO
# -----------------
#   * We do NOT re-sign files that aren't Mach-O. Pure-Python wheels are
#     skipped entirely (still valid pip install sources, no codesign needed).
#   * We do NOT touch *.dist-info/INSTALLER, *.dist-info/REQUESTED, or any
#     metadata file. Their RECORD lines stay byte-identical.
#   * We do NOT re-sign Mach-O files inside .app or .framework bundles
#     embedded in a wheel — wheels don't ship those, and even if a future
#     wheel did, the bundle would need --deep + --options runtime which is
#     out of scope here. Add a guard if/when that case appears.
#
# CALLED FROM
# -----------
#   installer/macos-pkg/scripts/build_pkg.sh::step_4c_resign_inner_wheels
#
# Exit codes:
#   0   success
#   60  argument / environment error (missing args, codesign, identity)
#   61  wheel I/O error (unreadable, malformed, missing RECORD)
#   62  codesign failure on at least one inner Mach-O
#   63  RECORD manifest rewrite failure or post-rewrite verification failed

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# Logging — keep stable so tests / build log can grep deterministic markers.
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    print(f"[resign_wheel] {msg}", flush=True)


def _die(code: int, msg: str) -> None:
    print(f"[resign_wheel] FATAL ({code}) {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


# ---------------------------------------------------------------------------
# Mach-O detection (Apple's `file` utility output is stable enough for this).
# ---------------------------------------------------------------------------

_MACHO_MARKERS: tuple[str, ...] = (
    "Mach-O 64-bit",
    "Mach-O 32-bit",
    "Mach-O universal binary",
)


def _is_macho(path: Path) -> bool:
    """Return True iff `file -b path` reports a Mach-O of any kind.

    This is intentionally conservative: a wheel's `.so` may technically be
    a regular ELF if someone vendored a Linux wheel by mistake. We codesign
    only Mach-O. Linux ELFs and other formats are skipped silently — they
    can't be loaded on macOS anyway, but failing the build for them would
    be wrong.
    """
    try:
        out = subprocess.check_output(
            ["/usr/bin/file", "-b", str(path)],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return False
    return any(marker in out for marker in _MACHO_MARKERS)


# ---------------------------------------------------------------------------
# RECORD manifest format (PEP 376 / PEP 491).
# ---------------------------------------------------------------------------

def _record_hash(path: Path) -> str:
    """sha256 in PEP 376 form: 'sha256=<urlsafe-b64-no-pad>'."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    digest = base64.urlsafe_b64encode(h.digest()).rstrip(b"=").decode("ascii")
    return f"sha256={digest}"


def _find_record_path(extract_root: Path) -> Path:
    """Locate <pkg>-<ver>.dist-info/RECORD inside an unpacked wheel.

    A valid PEP 491 wheel has exactly one *.dist-info directory at the top
    level. If we find zero or multiple, the wheel is malformed and we
    refuse to touch it (better to fail the build than ship broken wheels).
    """
    candidates = sorted(extract_root.glob("*.dist-info/RECORD"))
    if not candidates:
        raise FileNotFoundError("no *.dist-info/RECORD in wheel")
    if len(candidates) > 1:
        raise ValueError(
            f"multiple *.dist-info/RECORD in wheel: {[str(c) for c in candidates]}"
        )
    return candidates[0]


def _rewrite_record(record_path: Path, extract_root: Path,
                    changed: Iterable[Path]) -> int:
    """Rewrite RECORD lines for files we modified.

    Each non-empty line in RECORD is `path,hash,size`. We only touch lines
    whose `path` matches a file in `changed`. The path in RECORD is wheel-
    relative with forward slashes, regardless of OS.

    Returns the number of lines rewritten.
    """
    changed_set: set[str] = {
        str(p.relative_to(extract_root)).replace(os.sep, "/")
        for p in changed
    }

    rewritten = 0
    new_lines: list[str] = []
    with record_path.open("r", encoding="utf-8", newline="") as fh:
        # We deliberately preserve the original line endings the wheel
        # shipped with by reading raw text and rewriting line-by-line.
        for raw in fh.readlines():
            stripped = raw.rstrip("\r\n")
            if not stripped:
                new_lines.append(raw)
                continue
            parts = stripped.split(",")
            if len(parts) != 3:
                # Malformed RECORD line — leave it alone so we don't corrupt
                # something we don't understand.
                new_lines.append(raw)
                continue
            wheel_rel, _old_hash, _old_size = parts
            if wheel_rel in changed_set:
                target = extract_root / wheel_rel
                new_hash = _record_hash(target)
                new_size = str(target.stat().st_size)
                # Preserve trailing newline style (\r\n vs \n) if present.
                trailer = raw[len(stripped):]
                new_lines.append(f"{wheel_rel},{new_hash},{new_size}{trailer}")
                rewritten += 1
            else:
                new_lines.append(raw)

    # Path.write_text(newline=...) only exists in Python 3.10+. build_pkg.sh
    # invokes us with /usr/bin/python3 (Apple-stub), which is 3.9 on current
    # macOS — fall back to the file-handle API, which has supported `newline`
    # since 3.0. Pass newline="" so no \n→\r\n translation happens here; we
    # already preserved the original trailers when we built `new_lines`.
    with record_path.open("w", encoding="utf-8", newline="") as fh:
        fh.write("".join(new_lines))
    return rewritten


# ---------------------------------------------------------------------------
# codesign wrapper.
# ---------------------------------------------------------------------------

def _codesign(target: Path, identity: str) -> None:
    """codesign --force --sign IDENTITY --options runtime --timestamp TARGET.

    --force replaces any existing signature on the upstream-vendored .so.
    --options runtime opts the binary into hardened runtime (Apple notary
        rejects unhardened third-party Mach-O).
    --timestamp requests a secure timestamp from Apple's TSA — required
        for notarization. Needs network at build time.
    """
    cmd = [
        "/usr/bin/codesign",
        "--force",
        "--sign", identity,
        "--options", "runtime",
        "--timestamp",
        str(target),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"codesign failed for {target}: {proc.stderr.strip() or proc.stdout.strip()}"
        )


# ---------------------------------------------------------------------------
# Re-zip: produce a wheel that pip will accept.
# ---------------------------------------------------------------------------

def _rezip(extract_root: Path, out_wheel: Path) -> None:
    """Create a deterministic .whl from `extract_root`.

    We sort the file list lexicographically so two builds on two hosts
    produce identical bytes (modulo codesign blob, which is itself
    deterministic-ish — it depends on the timestamp authority response,
    which is fine for notarization).

    We use ZIP_DEFLATED (level 6 — the Python default) to match what pip
    download produced. The wheel format does not require a specific
    compression method, but staying close to upstream keeps diffs sane.
    """
    file_paths: list[Path] = sorted(
        p for p in extract_root.rglob("*") if p.is_file()
    )
    with zipfile.ZipFile(
        out_wheel, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6,
    ) as zf:
        for fp in file_paths:
            arcname = str(fp.relative_to(extract_root)).replace(os.sep, "/")
            zf.write(fp, arcname)


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------

def resign_wheel(wheel_path: Path, identity: str) -> dict[str, int]:
    """Re-sign every Mach-O inside `wheel_path` with `identity`.

    Returns a small stats dict for the caller to log:
        {"signed": <int>, "skipped_nonmacho": <int>, "record_rewritten": <int>}

    Raises on any failure. Caller is expected to translate exceptions into
    process exit codes (see `main`).
    """
    if not wheel_path.is_file():
        raise FileNotFoundError(f"wheel not found: {wheel_path}")
    if wheel_path.suffix != ".whl":
        raise ValueError(f"not a .whl file: {wheel_path}")

    stats = {"signed": 0, "skipped_nonmacho": 0, "record_rewritten": 0}

    with tempfile.TemporaryDirectory(prefix="mg_resign_wheel_") as tmp_str:
        tmp = Path(tmp_str)
        extract_root = tmp / "wheel"
        extract_root.mkdir()

        # 1. Unzip.
        with zipfile.ZipFile(wheel_path, "r") as zf:
            zf.extractall(extract_root)

        # 2. Find Mach-O. We restrict to extension .so / .dylib / .dyld
        # plus a permissive `is_macho` fallback for files with no extension
        # (rare but seen in some scientific wheels). Pure-Python files are
        # skipped instantly without invoking `file`.
        candidates: list[Path] = []
        for path in extract_root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix in (".so", ".dylib"):
                candidates.append(path)
            elif path.suffix == "":
                # No extension — could be a loose Mach-O. `file` will tell us.
                if _is_macho(path):
                    candidates.append(path)

        if not candidates:
            stats["skipped_nonmacho"] = 1
            _log(
                f"  skip {wheel_path.name}: no Mach-O candidates "
                "(pure-Python wheel)"
            )
            return stats

        # Filter to true Mach-O. A `.so` extension on a Linux ELF would
        # otherwise be passed to codesign (which would fail noisily).
        macho_files: list[Path] = [p for p in candidates if _is_macho(p)]
        if not macho_files:
            stats["skipped_nonmacho"] = 1
            _log(
                f"  skip {wheel_path.name}: extensions matched but no Mach-O "
                "(likely Linux ELF or non-Mach-O .so) — wheel left untouched"
            )
            return stats

        # 3. codesign each Mach-O.
        for macho in macho_files:
            _codesign(macho, identity)
            stats["signed"] += 1

        # 4. Update RECORD.
        try:
            record = _find_record_path(extract_root)
        except (FileNotFoundError, ValueError) as exc:
            raise RuntimeError(f"cannot locate RECORD in {wheel_path.name}: {exc}")
        stats["record_rewritten"] = _rewrite_record(
            record, extract_root, macho_files,
        )
        if stats["record_rewritten"] != len(macho_files):
            raise RuntimeError(
                f"RECORD rewrite mismatch for {wheel_path.name}: "
                f"{stats['record_rewritten']} updated vs {len(macho_files)} signed"
            )

        # 5. Re-zip into a sibling temp file, then move atomically over the
        # original wheel. This guarantees we never leave a half-rewritten
        # wheel on disk if the rezip fails partway.
        new_wheel = tmp / wheel_path.name
        _rezip(extract_root, new_wheel)

        # 6. Sanity-verify the new wheel can be opened and that RECORD's
        # entries match the actual zip contents we just wrote. This catches
        # programmer error before we ship to Apple notary.
        _verify_wheel_record(new_wheel)

        shutil.move(str(new_wheel), str(wheel_path))

    _log(
        f"  resigned {wheel_path.name}: "
        f"{stats['signed']} Mach-O, "
        f"{stats['record_rewritten']} RECORD line(s) rewritten"
    )
    return stats


def _verify_wheel_record(wheel_path: Path) -> None:
    """Open the wheel, locate RECORD, and recompute every entry's sha + size.

    pip runs the same check at install time. If our rewrite produced a
    RECORD that doesn't match the bytes in the zip, pip will refuse to
    install the wheel — which would be the worst possible outcome (notary
    accepts the .pkg, customer Mac fails at `pip install`). Catch it here.
    """
    with zipfile.ZipFile(wheel_path, "r") as zf:
        names = zf.namelist()
        record_names = [n for n in names if n.endswith(".dist-info/RECORD")]
        if len(record_names) != 1:
            raise RuntimeError(
                f"verify: expected exactly one .dist-info/RECORD in "
                f"{wheel_path.name}, got {len(record_names)}"
            )
        record_text = zf.read(record_names[0]).decode("utf-8")

        for raw in record_text.splitlines():
            if not raw.strip():
                continue
            parts = raw.split(",")
            if len(parts) != 3:
                continue
            rel, hash_field, size_field = parts
            if not hash_field:
                # The RECORD line for RECORD itself has empty hash + size.
                continue
            if rel not in names:
                raise RuntimeError(
                    f"verify: RECORD references missing file '{rel}' "
                    f"in {wheel_path.name}"
                )
            data = zf.read(rel)
            actual_size = len(data)
            if size_field and int(size_field) != actual_size:
                raise RuntimeError(
                    f"verify: size mismatch for {rel} in {wheel_path.name}: "
                    f"RECORD={size_field} actual={actual_size}"
                )
            expected = hash_field.split("=", 1)[1]
            actual = base64.urlsafe_b64encode(
                hashlib.sha256(data).digest(),
            ).rstrip(b"=").decode("ascii")
            if expected != actual:
                raise RuntimeError(
                    f"verify: sha256 mismatch for {rel} in {wheel_path.name}"
                )


# ---------------------------------------------------------------------------
# CLI: process every *.whl under a directory, log a summary, exit non-zero
# on the first hard failure.
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Re-sign Mach-O binaries inside a directory of vendored Python "
            "wheels and rewrite each wheel's *.dist-info/RECORD manifest."
        ),
    )
    parser.add_argument(
        "wheels_dir",
        type=Path,
        help="directory containing *.whl files (typically "
             "<payload>/python-wheels/ inside the .pkg staging tree)",
    )
    parser.add_argument(
        "--identity",
        required=True,
        help='Developer ID Application string, e.g. '
             '"Developer ID Application: Robert Fiesler (ARJZ5FYU94)"',
    )
    args = parser.parse_args(argv)

    if sys.platform != "darwin":
        _die(60, f"resign_wheel.py runs on macOS only (sys.platform={sys.platform})")

    if not args.wheels_dir.is_dir():
        _die(60, f"wheels_dir does not exist: {args.wheels_dir}")

    if not Path("/usr/bin/codesign").exists():
        _die(60, "/usr/bin/codesign missing — Xcode CLT not installed?")

    if not args.identity.startswith("Developer ID Application:"):
        _die(
            60,
            "--identity must be a 'Developer ID Application:' string "
            "(got: %r)" % args.identity,
        )

    wheels = sorted(args.wheels_dir.glob("*.whl"))
    if not wheels:
        _die(60, f"no *.whl found under {args.wheels_dir}")

    total_signed = 0
    total_record = 0
    total_skipped = 0
    failed: list[tuple[str, str]] = []

    for whl in wheels:
        try:
            stats = resign_wheel(whl, args.identity)
            total_signed += stats["signed"]
            total_record += stats["record_rewritten"]
            total_skipped += stats["skipped_nonmacho"]
        except (zipfile.BadZipFile, FileNotFoundError, ValueError) as exc:
            failed.append((whl.name, f"wheel I/O: {exc}"))
            _log(f"  ERROR {whl.name}: wheel I/O — {exc}")
        except RuntimeError as exc:
            # Distinguish codesign failures from RECORD/verify failures so
            # the caller can tell which exit code to use.
            msg = str(exc)
            if msg.startswith("codesign failed"):
                failed.append((whl.name, f"codesign: {exc}"))
            else:
                failed.append((whl.name, f"record: {exc}"))
            _log(f"  ERROR {whl.name}: {exc}")

    _log(
        f"summary: {len(wheels)} wheel(s) processed — "
        f"{total_signed} Mach-O signed, "
        f"{total_record} RECORD line(s) rewritten, "
        f"{total_skipped} pure-Python wheel(s) skipped, "
        f"{len(failed)} failure(s)"
    )

    if failed:
        # Pick the most-actionable exit code. Codesign failures are 62;
        # RECORD/verify failures are 63; wheel I/O is 61.
        codes = []
        for _, reason in failed:
            if reason.startswith("codesign:"):
                codes.append(62)
            elif reason.startswith("record:"):
                codes.append(63)
            else:
                codes.append(61)
        # Highest exit code wins (most severe class — RECORD breakage is
        # worse than a single codesign failure because it bricks pip).
        return max(codes)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
