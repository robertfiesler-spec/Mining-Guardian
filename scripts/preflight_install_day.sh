#!/usr/bin/env bash
# =============================================================================
# Mining Guardian — Install-Day Preflight (run on Mac Mini before installer)
# Date: 2026-04-30
# Tag:  v1.0.0-install-ready
#
# Purpose:
#   Verify the Mac Mini is ready to receive the MiningGuardian-1.0.0-*.pkg
#   installer. Runs read-only checks only — no system changes.
#
# Usage:
#   chmod +x scripts/preflight_install_day.sh
#   bash scripts/preflight_install_day.sh
#
# Exit codes:
#   0 = all green, safe to install
#   1 = one or more BLOCKING issues — DO NOT install until resolved
#   2 = WARN issues — review with operator before installing
# =============================================================================

set -u
PASS=0; WARN=0; FAIL=0
EXPECTED_PKG_SHA="1e65fe7827ffba2c8cd4daa0c2a42218bb156798521278fd0e567b0cef53a646"
EXPECTED_PKG_NAME="MiningGuardian-1.0.0-0f849bd217cc.pkg"
EXPECTED_TAG="v1.0.0-install-ready"
EXPECTED_MAIN_SHA="775b65308ab99fac16841eec6f27f65df3d3fd2d"

C_OK="\033[0;32m"; C_WARN="\033[0;33m"; C_BAD="\033[0;31m"; C_RST="\033[0m"
ok()   { echo -e "  ${C_OK}✓${C_RST} $*"; PASS=$((PASS+1)); }
warn() { echo -e "  ${C_WARN}!${C_RST} $*"; WARN=$((WARN+1)); }
bad()  { echo -e "  ${C_BAD}✗${C_RST} $*"; FAIL=$((FAIL+1)); }
hdr()  { echo; echo "=== $* ==="; }

hdr "1. macOS environment"
SW_VERS="$(sw_vers -productVersion 2>/dev/null || echo unknown)"
echo "  macOS: ${SW_VERS}"
case "${SW_VERS%%.*}" in
  14|15) ok "macOS major version ${SW_VERS%%.*} is supported" ;;
  *)     warn "macOS ${SW_VERS} not explicitly tested — proceed with caution" ;;
esac

ARCH="$(uname -m)"
echo "  Arch:  ${ARCH}"
case "${ARCH}" in
  arm64)  ok "Apple Silicon (expected)" ;;
  x86_64) warn "Intel Mac — installer was built for arm64; verify pkg variant" ;;
  *)      bad "Unknown arch ${ARCH}" ;;
esac

DISK_FREE_GB=$(df -g / | awk 'NR==2 {print $4}')
echo "  Free disk on /: ${DISK_FREE_GB} GB"
if [[ ${DISK_FREE_GB:-0} -ge 50 ]]; then ok "Disk free >= 50 GB"
elif [[ ${DISK_FREE_GB:-0} -ge 20 ]]; then warn "Disk free ${DISK_FREE_GB} GB — minimum is 20 GB but 50+ recommended"
else bad "Disk free ${DISK_FREE_GB} GB — INSUFFICIENT (need >= 20 GB)"
fi

hdr "2. Network reachability"
if ping -c 2 -t 3 1.1.1.1 >/dev/null 2>&1; then ok "Internet reachable (1.1.1.1)"
else bad "No internet — installer needs to fetch deps"
fi
if ping -c 2 -t 3 github.com >/dev/null 2>&1; then ok "github.com reachable"
else warn "github.com unreachable — repo pull may fail"
fi

hdr "3. Required tools (xcode-select, brew)"
if xcode-select -p >/dev/null 2>&1; then ok "Xcode CLT installed at $(xcode-select -p)"
else bad "Xcode CLT missing — run: xcode-select --install"
fi
if command -v brew >/dev/null 2>&1; then
  ok "Homebrew installed: $(brew --version | head -1)"
else
  warn "Homebrew not installed — installer will offer to install it"
fi
if command -v git >/dev/null 2>&1; then ok "git: $(git --version)"
else bad "git missing"
fi
if command -v psql >/dev/null 2>&1; then ok "psql: $(psql --version)"
else warn "psql not yet installed — installer will brew install postgresql@16"
fi
if command -v python3 >/dev/null 2>&1; then ok "python3: $(python3 --version)"
else bad "python3 missing"
fi

hdr "4. .pkg integrity check"
PKG_PATH=""
for cand in \
  "$HOME/Downloads/${EXPECTED_PKG_NAME}" \
  "/Volumes/MG Install/${EXPECTED_PKG_NAME}" \
  "$HOME/Documents/GitHub/Mining-Guardian/build/${EXPECTED_PKG_NAME}" \
  "./${EXPECTED_PKG_NAME}"; do
  if [[ -f "${cand}" ]]; then PKG_PATH="${cand}"; break; fi
done
if [[ -n "${PKG_PATH}" ]]; then
  echo "  Found .pkg at: ${PKG_PATH}"
  ACTUAL_SHA=$(shasum -a 256 "${PKG_PATH}" | awk '{print $1}')
  if [[ "${ACTUAL_SHA}" == "${EXPECTED_PKG_SHA}" ]]; then
    ok "sha256 matches expected (${EXPECTED_PKG_SHA:0:12}...)"
  else
    bad "sha256 MISMATCH — pkg may be corrupted or wrong build"
    echo "    expected: ${EXPECTED_PKG_SHA}"
    echo "    actual:   ${ACTUAL_SHA}"
  fi
  # Notarization staple check
  if command -v stapler >/dev/null 2>&1; then
    if stapler validate "${PKG_PATH}" >/dev/null 2>&1; then
      ok "Notarization staple is valid"
    else
      bad "Notarization staple invalid — Gatekeeper will block"
    fi
  else
    warn "stapler not available — skipping notarization check"
  fi
  # Signature check
  if pkgutil --check-signature "${PKG_PATH}" 2>&1 | grep -q "Status: signed"; then
    ok "Package signature valid"
  else
    bad "Package signature INVALID"
  fi
else
  bad "Could not find ${EXPECTED_PKG_NAME} in Downloads, USB, or build dir"
fi

hdr "5. Postgres reachability (only if already installed)"
if command -v psql >/dev/null 2>&1 && pgrep -f postgres >/dev/null 2>&1; then
  if psql -U "$(whoami)" -d postgres -c "SELECT version();" >/dev/null 2>&1; then
    ok "Local postgres responding"
    PG_VER=$(psql -U "$(whoami)" -d postgres -tAc "SHOW server_version;" 2>/dev/null)
    echo "    server_version: ${PG_VER}"
    if [[ "${PG_VER%%.*}" == "16" ]]; then ok "Postgres major version 16 (expected)"
    else warn "Postgres ${PG_VER} — installer expects 16.x"
    fi
  else
    warn "Postgres running but not responding to local user — installer will configure"
  fi
else
  echo "  (Postgres not installed yet — installer will brew install postgresql@16)"
fi

hdr "6. Repo state (if git clone already exists)"
if [[ -d "$HOME/Documents/GitHub/Mining-Guardian/.git" ]]; then
  cd "$HOME/Documents/GitHub/Mining-Guardian" || true
  CUR_HEAD=$(git rev-parse HEAD 2>/dev/null || echo unknown)
  echo "  HEAD: ${CUR_HEAD}"
  if [[ "${CUR_HEAD}" == "${EXPECTED_MAIN_SHA}" ]]; then
    ok "Repo HEAD matches expected install-ready commit"
  else
    warn "Repo HEAD differs — run: git fetch && git checkout ${EXPECTED_TAG}"
  fi
  if git tag -l | grep -q "^${EXPECTED_TAG}$"; then
    ok "Tag ${EXPECTED_TAG} present locally"
  else
    warn "Tag ${EXPECTED_TAG} not fetched — run: git fetch --tags"
  fi
else
  echo "  (repo not cloned yet — installer will clone)"
fi

hdr "7. Time / NTP"
DRIFT_SEC=$(sntp -t 5 time.apple.com 2>/dev/null | awk '/[+-][0-9]+\./ {print $1}' | head -1)
if [[ -n "${DRIFT_SEC}" ]]; then
  echo "  NTP offset: ${DRIFT_SEC}s"
  ok "Time sync responsive"
else
  warn "Could not query time.apple.com — verify date is accurate"
fi
echo "  Local time: $(date)"

hdr "8. SUMMARY"
echo "  PASS: ${PASS}"
echo "  WARN: ${WARN}"
echo "  FAIL: ${FAIL}"
echo
if [[ ${FAIL} -gt 0 ]]; then
  echo -e "${C_BAD}BLOCKED${C_RST} — resolve ${FAIL} failure(s) before running installer."
  exit 1
elif [[ ${WARN} -gt 0 ]]; then
  echo -e "${C_WARN}PROCEED WITH CAUTION${C_RST} — ${WARN} warning(s); review above."
  exit 2
else
  echo -e "${C_OK}ALL GREEN${C_RST} — Mac Mini ready for MiningGuardian install."
  exit 0
fi
