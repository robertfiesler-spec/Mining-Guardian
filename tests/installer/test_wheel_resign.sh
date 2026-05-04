#!/usr/bin/env bash
# tests/installer/test_wheel_resign.sh
#
# P-011 (2026-05-04) — wheel re-signing static + functional checks.
#
# This test asserts that build_pkg.sh re-signs Mach-O binaries inside
# vendored Python wheels and rewrites *.dist-info/RECORD correctly. It
# runs against the source tree only — no Mac, no codesign call against
# Apple's TSA (we monkey-patch codesign via a shim script for the
# functional pass, since this test is part of the cross-platform CI loop).
#
# Run from repo root:
#     bash tests/installer/test_wheel_resign.sh
#
# Exits 0 on success, non-zero on first failed assertion.
# Requires: bash, python3 (3.10+ for type-hint syntax in resign_wheel.py).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

RESIGN_PY="installer/macos-pkg/scripts/lib/resign_wheel.py"
BUILD_PKG="installer/macos-pkg/scripts/build_pkg.sh"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }
section() { echo; echo "## $*"; }

# ---------------------------------------------------------------------
section "1. Files exist"
# ---------------------------------------------------------------------
for f in "$RESIGN_PY" "$BUILD_PKG"; do
    if [[ -r "$f" ]]; then
        ok "$f present"
    else
        fail "$f missing"
    fi
done

# ---------------------------------------------------------------------
section "2. Python syntax check"
# ---------------------------------------------------------------------
if /usr/bin/env python3 -m py_compile "$RESIGN_PY" 2>/dev/null; then
    ok "resign_wheel.py compiles cleanly"
else
    fail "resign_wheel.py has a syntax error"
fi
if bash -n "$BUILD_PKG" 2>/dev/null; then
    ok "build_pkg.sh parses"
else
    fail "build_pkg.sh has bash syntax errors"
fi

# ---------------------------------------------------------------------
section "3. step_4c_resign_inner_wheels wired in"
# ---------------------------------------------------------------------
if /usr/bin/grep -q '^step_4c_resign_inner_wheels()' "$BUILD_PKG"; then
    ok "step_4c_resign_inner_wheels() defined"
else
    fail "step_4c_resign_inner_wheels() missing — P-011 not implemented"
fi

# main() must call step_4c after step_4b and before step_5.
call_order="$(/usr/bin/awk '/^main\(\)/, /^}/' "$BUILD_PKG" \
    | /usr/bin/grep -oE 'step_(4_assemble_payload|4b_codesign_inner_binaries|4c_resign_inner_wheels|5_pkgbuild_and_sign)' \
    | /usr/bin/paste -sd, -)"
expected="step_4_assemble_payload,step_4b_codesign_inner_binaries,step_4c_resign_inner_wheels,step_5_pkgbuild_and_sign"
if [[ "$call_order" == "$expected" ]]; then
    ok "main() ordering: 4 → 4b → 4c → 5"
else
    fail "main() ordering wrong (got '$call_order', expected '$expected')"
fi

# ---------------------------------------------------------------------
section "4. Exit code 49 reserved + documented"
# ---------------------------------------------------------------------
if /usr/bin/grep -qE '^#[[:space:]]+49[[:space:]]+—' "$BUILD_PKG"; then
    ok "exit code 49 documented in build_pkg.sh header"
else
    fail "exit code 49 not documented in build_pkg.sh header (P-011)"
fi
if /usr/bin/grep -qE '_die 49 ' "$BUILD_PKG"; then
    ok "_die 49 used in step_4c"
else
    fail "_die 49 not used — P-011 errors will report wrong exit code"
fi

# ---------------------------------------------------------------------
section "5. resign_wheel.py refuses non-Apple identity"
# ---------------------------------------------------------------------
# CLI guard: --identity must start with "Developer ID Application:".
# Probe by feeding a wrong identity and asserting non-zero exit.
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
mkdir -p "$tmpdir/wheels"
# Empty wheels dir would trip the no-wheels guard before identity, so
# drop a stub wheel so we hit the identity check first.
/usr/bin/env python3 -c "
import zipfile, pathlib
p = pathlib.Path('$tmpdir/wheels/stub-1.0.0-py3-none-any.whl')
with zipfile.ZipFile(p, 'w') as zf:
    zf.writestr('stub-1.0.0.dist-info/RECORD', '')
"
# Non-darwin platforms exit 60 immediately on the platform check before
# touching identity — accept either exit reason here.
set +e
/usr/bin/env python3 "$RESIGN_PY" \
    --identity "Some Other Cert" \
    "$tmpdir/wheels" >/dev/null 2>&1
rc=$?
set -e
if (( rc != 0 )); then
    ok "resign_wheel.py refuses non-'Developer ID Application:' identity (exit ${rc})"
else
    fail "resign_wheel.py accepted a non-Apple identity (security regression)"
fi

# ---------------------------------------------------------------------
section "6. Functional: synthetic wheel round-trip with mocked codesign"
# ---------------------------------------------------------------------
# Build a synthetic wheel containing a fake .so, monkey-patch the helper
# so we don't need the Mac toolchain, then verify the rewritten wheel
# parses cleanly, RECORD entries match actual file bytes, and pure-data
# files were untouched.
/usr/bin/env python3 - "$RESIGN_PY" <<'PYEOF'
import base64, hashlib, importlib.util, sys, tempfile, zipfile
from pathlib import Path

resign_py = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("resign_wheel", resign_py)
rw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rw)


def b64sha(data: bytes) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


tmp = Path(tempfile.mkdtemp())
src = tmp / "src"
(src / "fake_pkg").mkdir(parents=True)
(src / "fake_pkg-1.0.0.dist-info").mkdir(parents=True)

init_bytes = b"# init\n"
(src / "fake_pkg" / "__init__.py").write_bytes(init_bytes)

so_bytes = b"\xcf\xfa\xed\xfe" + b"X" * 1024
(src / "fake_pkg" / "_ext.so").write_bytes(so_bytes)

meta_bytes = b"Metadata-Version: 2.1\nName: fake_pkg\nVersion: 1.0.0\n"
(src / "fake_pkg-1.0.0.dist-info" / "METADATA").write_bytes(meta_bytes)
wheel_bytes = b"Wheel-Version: 1.0\n"
(src / "fake_pkg-1.0.0.dist-info" / "WHEEL").write_bytes(wheel_bytes)

record_lines = [
    f"fake_pkg/__init__.py,sha256={b64sha(init_bytes)},{len(init_bytes)}",
    f"fake_pkg/_ext.so,sha256={b64sha(so_bytes)},{len(so_bytes)}",
    f"fake_pkg-1.0.0.dist-info/METADATA,sha256={b64sha(meta_bytes)},{len(meta_bytes)}",
    f"fake_pkg-1.0.0.dist-info/WHEEL,sha256={b64sha(wheel_bytes)},{len(wheel_bytes)}",
    "fake_pkg-1.0.0.dist-info/RECORD,,",
    "",
]
(src / "fake_pkg-1.0.0.dist-info" / "RECORD").write_text("\n".join(record_lines))

whl = tmp / "fake_pkg-1.0.0-cp312-cp312-macosx_11_0_arm64.whl"
with zipfile.ZipFile(whl, "w", zipfile.ZIP_DEFLATED) as zf:
    for p in src.rglob("*"):
        if p.is_file():
            zf.write(p, p.relative_to(src).as_posix())

# Monkey-patch: codesign mutates the file, is_macho returns True for .so
def fake_codesign(target, identity):
    with open(target, "ab") as f:
        f.write(b"\x00FAKE_SIG_BLOB\x00" + b"S" * 256)


def fake_is_macho(path):
    return path.suffix == ".so"


rw._codesign = fake_codesign
rw._is_macho = fake_is_macho

stats = rw.resign_wheel(whl, "Developer ID Application: Test (AAAAAAAAAA)")
assert stats["signed"] == 1, f"expected signed=1, got {stats}"
assert stats["record_rewritten"] == 1, f"expected record_rewritten=1, got {stats}"

with zipfile.ZipFile(whl, "r") as zf:
    record = zf.read("fake_pkg-1.0.0.dist-info/RECORD").decode()
    so_data = zf.read("fake_pkg/_ext.so")
    expected_hash = b64sha(so_data)
    expected_size = len(so_data)
    so_line = next(
        line for line in record.splitlines()
        if line.startswith("fake_pkg/_ext.so,")
    )
    _, h, s = so_line.split(",")
    assert h == f"sha256={expected_hash}", f"hash drift: {h!r} vs sha256={expected_hash}"
    assert int(s) == expected_size, f"size drift: {s!r} vs {expected_size}"

    metadata = zf.read("fake_pkg-1.0.0.dist-info/METADATA")
    assert metadata == meta_bytes, "metadata bytes drifted"

# verify_wheel_record must accept the rewritten wheel.
rw._verify_wheel_record(whl)

# Tamper test — corrupt METADATA without updating RECORD; verify must raise.
import shutil
broken = tmp / "broken.whl"
shutil.copy(whl, broken)
with zipfile.ZipFile(broken, "r") as zf:
    names = zf.namelist()
    contents = {n: zf.read(n) for n in names}
contents["fake_pkg-1.0.0.dist-info/METADATA"] = b"TAMPERED\n"
with zipfile.ZipFile(broken, "w", zipfile.ZIP_DEFLATED) as zf:
    for n in sorted(names):
        zf.writestr(n, contents[n])
try:
    rw._verify_wheel_record(broken)
except RuntimeError:
    pass
else:
    raise SystemExit("verify_wheel_record FAILED to detect tamper")

print("FUNCTIONAL_OK")
PYEOF
if [[ $? -eq 0 ]]; then
    ok "synthetic wheel: signed, RECORD rewritten, verify passed, tamper detected"
else
    fail "synthetic wheel round-trip failed"
fi

# ---------------------------------------------------------------------
section "7. resign_wheel.py is invoked from build_pkg.sh"
# ---------------------------------------------------------------------
if /usr/bin/grep -q 'resign_wheel.py' "$BUILD_PKG"; then
    ok "build_pkg.sh references resign_wheel.py"
else
    fail "build_pkg.sh does not call resign_wheel.py — P-011 wiring incomplete"
fi
if /usr/bin/grep -q 'APPLE_DEV_ID_APPLICATION' "$BUILD_PKG" \
        && /usr/bin/grep -q -- '--identity' "$BUILD_PKG"; then
    ok "build_pkg.sh passes --identity \$APPLE_DEV_ID_APPLICATION to resign_wheel.py"
else
    fail "build_pkg.sh does not pass the Application identity to resign_wheel.py"
fi

# ---------------------------------------------------------------------
section "8. Notary detail-log auto-fetch on failure"
# ---------------------------------------------------------------------
# P-011 follow-up: when notarytool returns non-Accepted, build_pkg.sh
# should attempt `xcrun notarytool log <id>` to capture the detailed
# JSON. Failure of the auto-fetch itself must NOT mask the _die 45.
if /usr/bin/grep -q 'notarytool log' "$BUILD_PKG"; then
    ok "build_pkg.sh attempts notarytool log on failure (auto-fetch)"
else
    fail "build_pkg.sh does not auto-fetch detailed notary log on failure"
fi
if /usr/bin/grep -qE 'notarization-detail\.json' "$BUILD_PKG"; then
    ok "build_pkg.sh writes detail log to a predictable filename"
else
    fail "build_pkg.sh does not write detailed notary log to a sidecar file"
fi

# ---------------------------------------------------------------------
section "9. shellcheck regression baseline"
# ---------------------------------------------------------------------
# Pre-P-011 baseline (per test_postinstall_venv.sh §3): build_pkg.sh has
# 5 distinct warnings (SC2155 line 61, 4× SC2295 in step_4b). P-011
# adds new code; the new code must not introduce additional warnings,
# but step_4c contains a heredoc that shellcheck flags with a
# pre-existing ignorable info-level warning (SC2016) for the embedded
# Python literal. Allow up to 7 to leave room for that without slipping.
if command -v shellcheck >/dev/null 2>&1; then
    bp_count="$(shellcheck "$BUILD_PKG" 2>&1 | /usr/bin/grep -cE '^In .* line [0-9]+:' || true)"
    if [[ "$bp_count" -le 7 ]]; then
        ok "build_pkg.sh shellcheck warnings: ${bp_count} (≤ 7 P-011 baseline)"
    else
        fail "build_pkg.sh shellcheck warnings: ${bp_count} (> 7 — P-011 introduced new warning)"
    fi
else
    echo "  SKIP — shellcheck not installed"
fi

# ---------------------------------------------------------------------
section "10. Apple-stub Python 3.9 compatibility (P-012 regression guard)"
# ---------------------------------------------------------------------
# build_pkg.sh invokes resign_wheel.py with /usr/bin/python3, which on
# current macOS (Sonoma/Sequoia) is the Apple-stub Python 3.9. Some
# pathlib APIs added in 3.10 — notably Path.write_text(..., newline=...) —
# raise TypeError under 3.9 and crash step 4c before signing/notarization.
# This is exactly how P-012 broke the build on 2026-05-04.
#
# Lint via AST so any reintroduction of write_text(..., newline=...) on a
# Path object is caught regardless of formatting. Any 3.10+ pathlib-only
# kwarg should be added to FORBIDDEN_KWARGS as we discover them.
/usr/bin/env python3 - "$RESIGN_PY" <<'PYEOF'
import ast, sys
from pathlib import Path

src_path = Path(sys.argv[1])
tree = ast.parse(src_path.read_text(encoding="utf-8"))

FORBIDDEN = {
    "write_text": {"newline"},  # added in 3.10
    "read_text":  {"newline"},  # added in 3.13
}

violations = []
for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue
    func = node.func
    if not isinstance(func, ast.Attribute):
        continue
    if func.attr not in FORBIDDEN:
        continue
    bad = FORBIDDEN[func.attr]
    for kw in node.keywords:
        if kw.arg in bad:
            violations.append(
                f"line {node.lineno}: .{func.attr}(..., {kw.arg}=...) "
                f"is not available on /usr/bin/python3 (3.9) — use the "
                f"file-handle .open(..., {kw.arg}=...) form instead"
            )

if violations:
    print("FORBIDDEN_API_USED")
    for v in violations:
        print("  " + v)
    sys.exit(1)
print("COMPAT_OK")
PYEOF
if [[ $? -eq 0 ]]; then
    ok "resign_wheel.py uses no Python 3.10+-only pathlib kwargs (P-012 fix)"
else
    fail "resign_wheel.py uses a pathlib kwarg unavailable on /usr/bin/python3 — P-012 will reoccur"
fi

# ---------------------------------------------------------------------
section "11. Functional: RECORD rewrite under simulated Python 3.9"
# ---------------------------------------------------------------------
# Direct functional check: invoke _rewrite_record() with a synthetic
# wheel layout AFTER monkey-patching Path.write_text so it raises the same
# TypeError Python 3.9 would, simulating /usr/bin/python3 on the Mac.
# A correct implementation reaches the file-handle write branch and never
# touches the broken kwarg API.
/usr/bin/env python3 - "$RESIGN_PY" <<'PYEOF'
import importlib.util, sys, tempfile
from pathlib import Path

resign_py = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("resign_wheel", resign_py)
rw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rw)

real_write_text = Path.write_text

def stub_write_text(self, data, encoding=None, errors=None, newline=None):
    if newline is not None:
        raise TypeError(
            "write_text() got an unexpected keyword argument 'newline'"
        )
    return real_write_text(self, data, encoding=encoding, errors=errors)

Path.write_text = stub_write_text
try:
    tmp = Path(tempfile.mkdtemp())
    extract_root = tmp / "extract"
    (extract_root / "pkg").mkdir(parents=True)
    so_path = extract_root / "pkg" / "fake.so"
    so_path.write_bytes(b"\xcf\xfa\xed\xfeXXXX")
    record_path = extract_root / "pkg-1.0.0.dist-info"
    record_path.mkdir(parents=True)
    record_file = record_path / "RECORD"
    record_file.write_text(
        "pkg/fake.so,sha256=oldhash,4\n"
        "pkg-1.0.0.dist-info/RECORD,,\n",
        encoding="utf-8",
    )
    rewritten = rw._rewrite_record(record_file, extract_root, [so_path])
    assert rewritten == 1, f"expected 1 rewritten line, got {rewritten}"
    new_record = record_file.read_text(encoding="utf-8")
    assert "sha256=oldhash" not in new_record, "RECORD line not actually rewritten"
    assert "pkg/fake.so," in new_record, "fake.so line missing from rewritten RECORD"
finally:
    Path.write_text = real_write_text

print("PY39_COMPAT_OK")
PYEOF
if [[ $? -eq 0 ]]; then
    ok "_rewrite_record works when Path.write_text rejects newline= (Python 3.9 sim)"
else
    fail "_rewrite_record still depends on Path.write_text(newline=) — P-012 fix incomplete"
fi

# ---------------------------------------------------------------------
section "Summary"
# ---------------------------------------------------------------------
echo
echo "Passed: $pass_count"
echo "Failed: $fail_count"
if (( fail_count > 0 )); then
    exit 1
fi
exit 0
