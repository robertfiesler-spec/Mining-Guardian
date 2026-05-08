#!/usr/bin/env bash
# tests/installer/test_p026_image_sha_sidecar_portability.sh
#
# P-026 image-sidecar portability — every `runtime/images/*.sha256`
# that ships in the customer .pkg payload must carry a BASENAME-ONLY
# filename field, never an absolute build-Mac path.
#
# Background. The 2026-05-08 morning inspection of
# `MiningGuardian-1.0.3-d5f1f4da6cd3.pkg` (the post-P-024 build) found:
#
#   ./runtime/images/postgres-16-bookworm.tar.sha256:
#     ca691...  /Users/BigBobby/MiningGuardian-vendor/images/postgres-16-bookworm.tar
#
# That absolute path is build-Mac contamination — same class of finding
# as P-024's BigBobby/100.103.185.53 surface, just inside the payload's
# verification sidecar instead of an operator script. It also makes
# `shasum -c` non-portable: the customer Mini does not have
# `/Users/BigBobby/MiningGuardian-vendor/images/` and would have to
# manually edit the sidecar before verification. The fix in
# `installer/macos-pkg/scripts/build_pkg.sh` step 4c (post vendor
# rsync) walks `${PAYLOAD_DIR}/runtime/images/` and rewrites every
# `*.sha256` to `<hash>  <basename>` form. This test locks that in.
#
# This test:
#   1. Verifies build_pkg.sh parses (bash -n).
#   2. Statically asserts the normalisation block exists in build_pkg.sh
#      (awk-based, scoped to ${PAYLOAD_DIR}/runtime/images, runs after
#      the vendor rsync, idempotent on already-normalised sidecars).
#   3. Replays the exact awk normalisation against a fixture tree and
#      asserts:
#        * a sidecar with `/Users/BigBobby/...` is rewritten to
#          basename only.
#        * a sidecar with `/Volumes/...` is rewritten to basename only.
#        * an already-normalised sidecar is untouched (idempotent).
#        * the rewritten sidecars verify with `shasum -c` when run
#          from the same directory as the .tar.
#        * no surviving line contains `/`, `/Users/`, `/Volumes/`, or
#          the build vendor path.
#
# Run from repo root:
#     bash tests/installer/test_p026_image_sha_sidecar_portability.sh
#
# Exits 0 on success, non-zero on first failed assertion.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

BUILD_PKG="installer/macos-pkg/scripts/build_pkg.sh"

pass_count=0
fail_count=0

ok()   { echo "  OK  — $*";   pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL — $*" >&2; fail_count=$((fail_count + 1)); }

section() { echo; echo "## $*"; }

# ---------------------------------------------------------------------
section "1. build_pkg.sh parses"
# ---------------------------------------------------------------------
if bash -n "$BUILD_PKG" 2>/dev/null; then
    ok "build_pkg.sh parses (bash -n)"
else
    fail "build_pkg.sh has bash syntax errors"
fi

# ---------------------------------------------------------------------
section "2. Normalisation block is present in build_pkg.sh"
# ---------------------------------------------------------------------
# Marker comments — keep these stable so a regression that drops the
# block is visible in the assertion.
if /usr/bin/grep -qF "P-026 image-sidecar portability" "$BUILD_PKG"; then
    ok "build_pkg.sh marks the P-026 normalisation block"
else
    fail "build_pkg.sh missing 'P-026 image-sidecar portability' marker"
fi
# Loop over runtime/images/*.sha256.
if /usr/bin/grep -qF '${images_dir}"/*.sha256' "$BUILD_PKG"; then
    ok "build_pkg.sh iterates runtime/images/*.sha256"
else
    fail "build_pkg.sh missing the runtime/images/*.sha256 loop"
fi
# awk pipeline rewrites the path field via split(...,"/").
if /usr/bin/grep -qF 'split(rest, parts, "/")' "$BUILD_PKG"; then
    ok "build_pkg.sh uses awk split-on-/ for basename extraction"
else
    fail "build_pkg.sh awk basename pipeline missing"
fi
# Two-space separator (shasum format). The literal substring in the
# build script is the awk format `printf "%s  %s\n"` — the `\n` is two
# characters (`\` + `n`) inside the awk source. We pass them
# untouched to grep -F via bash single quotes.
if /usr/bin/grep -qF 'printf "%s  %s\n", hash, base' "$BUILD_PKG"; then
    ok "build_pkg.sh emits the shasum two-space separator"
else
    fail "build_pkg.sh awk emit format does not match shasum's '<hash>  <name>'"
fi

# ---------------------------------------------------------------------
section "3. Replay normalisation against a fixture tree"
# ---------------------------------------------------------------------
TMPDIR_PAYLOAD="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_PAYLOAD"' EXIT
mkdir -p "${TMPDIR_PAYLOAD}/runtime/images"

# Fixture #1: the actual problem we are fixing — `/Users/BigBobby/...`.
# Hash is exactly 64 hex chars (canonical SHA-256 output width).
printf 'ca6918abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123  /Users/BigBobby/MiningGuardian-vendor/images/postgres-16-bookworm.tar\n' \
    > "${TMPDIR_PAYLOAD}/runtime/images/postgres-16-bookworm.tar.sha256"

# Fixture #2: hypothetical `/Volumes/...` build path (a likely future
# regression if the build Mac is ever switched).
printf 'deadbeef00000000000000000000000000000000000000000000000000000000  /Volumes/Big-Bobby-T9/MiningGuardian-vendor/images/sample.tar\n' \
    > "${TMPDIR_PAYLOAD}/runtime/images/sample.tar.sha256"

# Fixture #3: already-normalised sidecar — must be left untouched.
printf '0123456789abcdef000000000000000000000000000000000000000000000000  already-normalised.tar\n' \
    > "${TMPDIR_PAYLOAD}/runtime/images/already-normalised.sha256"

# Replay the exact awk pipeline used in build_pkg.sh step 4c.
PAYLOAD_DIR="$TMPDIR_PAYLOAD"
images_dir="${PAYLOAD_DIR}/runtime/images"
for sidecar in "${images_dir}"/*.sha256; do
    [[ -f "$sidecar" ]] || continue
    tmp="$(/usr/bin/mktemp "${sidecar}.XXXXXX")"
    /usr/bin/awk '
        {
            hash = $1
            rest = $0
            sub(/^[^ ]+[ ]+/, "", rest)
            n = split(rest, parts, "/")
            base = parts[n]
            printf "%s  %s\n", hash, base
        }
    ' "$sidecar" > "$tmp"
    /bin/mv "$tmp" "$sidecar"
done

# 3a. Each sidecar must end up with no '/' in it.
slash_offenders=0
for sidecar in "${images_dir}"/*.sha256; do
    if /usr/bin/grep -q '/' "$sidecar"; then
        fail "sidecar still contains a slash: ${sidecar} -> $(cat "$sidecar")"
        slash_offenders=$((slash_offenders + 1))
    fi
done
if (( slash_offenders == 0 )); then
    ok "no normalised sidecar contains '/'"
fi

# 3b. None contain Bobby's-Mac home path.
if /usr/bin/grep -lF '/Users/BigBobby' "${images_dir}"/*.sha256 >/dev/null 2>&1; then
    fail "sidecar still contains '/Users/BigBobby' after normalisation"
else
    ok "no sidecar contains '/Users/BigBobby'"
fi

# 3c. None contain a /Volumes/ path.
if /usr/bin/grep -lE '^[^ ]+ +/Volumes/' "${images_dir}"/*.sha256 >/dev/null 2>&1; then
    fail "sidecar still contains a /Volumes/ build path after normalisation"
else
    ok "no sidecar contains a /Volumes/ build path"
fi

# 3d. None contain the build-vendor marker `MiningGuardian-vendor`.
if /usr/bin/grep -lF 'MiningGuardian-vendor' "${images_dir}"/*.sha256 >/dev/null 2>&1; then
    fail "sidecar still contains 'MiningGuardian-vendor' after normalisation"
else
    ok "no sidecar contains 'MiningGuardian-vendor'"
fi

# 3e. Specific basenames are right.
if /usr/bin/grep -qE '^[0-9a-f]{64}  postgres-16-bookworm\.tar$' \
        "${images_dir}/postgres-16-bookworm.tar.sha256"; then
    ok "postgres sidecar normalised to '<hash>  postgres-16-bookworm.tar'"
else
    fail "postgres sidecar shape wrong: $(cat "${images_dir}/postgres-16-bookworm.tar.sha256")"
fi
if /usr/bin/grep -qE '^[0-9a-f]{64}  sample\.tar$' \
        "${images_dir}/sample.tar.sha256"; then
    ok "sample sidecar normalised to '<hash>  sample.tar'"
else
    fail "sample sidecar shape wrong: $(cat "${images_dir}/sample.tar.sha256")"
fi

# 3f. Already-normalised sidecar must be untouched (idempotent).
if /usr/bin/grep -qE '^[0-9a-f]{64}  already-normalised\.tar$' \
        "${images_dir}/already-normalised.sha256"; then
    ok "already-normalised sidecar stays correct (idempotent)"
else
    fail "already-normalised sidecar shape wrong: $(cat "${images_dir}/already-normalised.sha256")"
fi

# 3g. The two-space separator (shasum's BSD/GNU canonical format) is
# preserved. `shasum -c` accepts one or more spaces, but matching the
# output of `shasum -a 256 <file>` exactly is the safer contract.
two_space_offenders=0
for sidecar in "${images_dir}"/*.sha256; do
    if ! /usr/bin/grep -qE '^[0-9a-f]+  [^ ]+$' "$sidecar"; then
        fail "sidecar separator wrong (expected '<hash>  <name>'): $(cat "$sidecar")"
        two_space_offenders=$((two_space_offenders + 1))
    fi
done
if (( two_space_offenders == 0 )); then
    ok "all normalised sidecars use the two-space '<hash>  <name>' separator"
fi

# 3h. End-to-end: a real `shasum -c` succeeds against a normalised
# sidecar when run from the images directory. This is the operator
# scenario this PR fixes.
if command -v /usr/bin/shasum >/dev/null 2>&1; then
    real_dir="$(mktemp -d)"
    real_tar="${real_dir}/some-image.tar"
    /bin/echo "fake image content for shasum -c roundtrip" > "$real_tar"
    real_hash="$(/usr/bin/shasum -a 256 "$real_tar" | /usr/bin/awk '{print $1}')"
    /bin/echo "${real_hash}  /Users/BigBobby/MiningGuardian-vendor/images/some-image.tar" > "${real_dir}/some-image.tar.sha256"
    # Replay the same normalisation
    tmp="$(/usr/bin/mktemp "${real_dir}/some-image.tar.sha256.XXXXXX")"
    /usr/bin/awk '
        {
            hash = $1
            rest = $0
            sub(/^[^ ]+[ ]+/, "", rest)
            n = split(rest, parts, "/")
            base = parts[n]
            printf "%s  %s\n", hash, base
        }
    ' "${real_dir}/some-image.tar.sha256" > "$tmp"
    /bin/mv "$tmp" "${real_dir}/some-image.tar.sha256"
    if ( cd "$real_dir" && /usr/bin/shasum -a 256 -c some-image.tar.sha256 ) >/dev/null 2>&1; then
        ok "shasum -c verifies normalised sidecar from the images dir"
    else
        fail "shasum -c failed on a normalised sidecar — format regression"
    fi
    rm -rf "$real_dir"
else
    ok "shasum not on PATH — skipping shasum -c roundtrip (Linux CI is fine)"
fi

# ---------------------------------------------------------------------
section "Summary"
# ---------------------------------------------------------------------
echo "  passed: ${pass_count}"
echo "  failed: ${fail_count}"

if (( fail_count > 0 )); then
    exit 1
fi
exit 0
