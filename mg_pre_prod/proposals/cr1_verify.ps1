# =============================================================================
# CR-1 VERIFICATION SCRIPT  (PowerShell -- paste into ROBS-PC PowerShell window)
# =============================================================================
# Purpose:
#   CR-1 in the CRIT-5 manifest was downgraded after a snapshot grep showed
#   that no attribute named `auto_approve_enabled` exists anywhere in the
#   repository. This script verifies that conclusion against the LIVE branch
#   (your working tree, not the audit snapshot) and pulls any AttributeError
#   traces from the recent VPS daemon log so we know what was actually firing.
#
# How to run:
#   1. Open PowerShell on ROBS-PC (NOT Git Bash).
#   2. cd C:\Users\User\Mining-Guardian
#   3. Paste this entire script into the PowerShell window and press Enter.
#      (Or save it as cr1_verify.ps1 and run: .\cr1_verify.ps1)
#
# What it does (read-only -- no commits, no file edits):
#   Section A -- Repo state sanity check
#   Section B -- Grep working tree for auto_approve references
#   Section C -- Grep working tree for the SPECIFIC token auto_approve_enabled
#   Section D -- Show full context of every match
#   Section E -- Pull recent VPS daemon AttributeError traces (via SSH)
#   Section F -- Summary verdict
#
# Output: prints to console + writes a timestamped report under
#         C:\Users\User\Mining-Guardian\cr1_verify_report_<UTC>.txt
# =============================================================================

# ---- 0. Setup ----
$ErrorActionPreference = "Continue"   # don't abort on grep-no-match
$RepoRoot = "C:\Users\User\Mining-Guardian"
$Stamp    = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss")
$Report   = Join-Path $RepoRoot ("cr1_verify_report_{0}.txt" -f $Stamp)

# helper -- write to both console and report file
function Tee-Both([string]$line) {
    Write-Host  $line
    Add-Content -Path $Report -Value $line
}

# initialize report
Set-Content -Path $Report -Value "CR-1 VERIFICATION REPORT -- $Stamp UTC"
Tee-Both "============================================================"

# ---- A. Repo state sanity check ----
Tee-Both ""
Tee-Both "[A] Repo state"
Tee-Both "------------------------------------------------------------"
Set-Location $RepoRoot

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
$head   = (git rev-parse --short HEAD).Trim()
$dirty  = (git status --porcelain).Trim()

Tee-Both ("    Branch:        " + $branch)
Tee-Both ("    HEAD:          " + $head)
Tee-Both ("    Working tree:  " + ($(if ($dirty) { "DIRTY" } else { "clean" })))
if ($dirty) {
    Tee-Both "    --- uncommitted changes ---"
    $dirty -split "`n" | ForEach-Object { Tee-Both ("        " + $_) }
}

# ---- B. Broad grep -- anything matching 'auto_approve' ----
Tee-Both ""
Tee-Both "[B] Broad grep: 'auto_approve' across .py files in working tree"
Tee-Both "------------------------------------------------------------"
$broad = Get-ChildItem -Path . -Recurse -Filter "*.py" -ErrorAction SilentlyContinue |
         Select-String -Pattern "auto_approve" -CaseSensitive:$false
if ($broad) {
    $broad | ForEach-Object {
        $rel = (Resolve-Path -Relative $_.Path)
        Tee-Both ("    " + $rel + ":" + $_.LineNumber + ":  " + $_.Line.Trim())
    }
    Tee-Both ("    --- " + $broad.Count + " matches total ---")
} else {
    Tee-Both "    (no matches -- no auto_approve reference anywhere)"
}

# ---- C. Narrow grep -- the SPECIFIC token 'auto_approve_enabled' ----
Tee-Both ""
Tee-Both "[C] Narrow grep: token 'auto_approve_enabled' (the CR-1 suspect)"
Tee-Both "------------------------------------------------------------"
$narrow = Get-ChildItem -Path . -Recurse -Filter "*.py" -ErrorAction SilentlyContinue |
          Select-String -Pattern "auto_approve_enabled" -CaseSensitive:$false
if ($narrow) {
    $narrow | ForEach-Object {
        $rel = (Resolve-Path -Relative $_.Path)
        Tee-Both ("    " + $rel + ":" + $_.LineNumber + ":  " + $_.Line.Trim())
    }
    Tee-Both ("    --- " + $narrow.Count + " matches -- CR-1 IS REAL, do not downgrade ---")
} else {
    Tee-Both "    (no matches -- confirms CR-1 downgrade: token does not exist)"
}

# ---- D. Full context of broad matches (3 lines before/after) ----
Tee-Both ""
Tee-Both "[D] Context of every 'auto_approve' match (3 lines around)"
Tee-Both "------------------------------------------------------------"
if ($broad) {
    $broad | ForEach-Object {
        $rel  = (Resolve-Path -Relative $_.Path)
        Tee-Both ""
        Tee-Both ("--- " + $rel + " around line " + $_.LineNumber + " ---")
        $start = [Math]::Max(1, $_.LineNumber - 3)
        $end   = $_.LineNumber + 3
        $lines = Get-Content $_.Path
        for ($i = $start; $i -le [Math]::Min($end, $lines.Count); $i++) {
            $marker = $(if ($i -eq $_.LineNumber) { ">>" } else { "  " })
            Tee-Both ("    " + $marker + " " + $i.ToString("0000") + ":  " + $lines[$i-1])
        }
    }
} else {
    Tee-Both "    (nothing to show -- no broad matches)"
}

# ---- E. VPS-side commands (run separately on the VPS) ----
Tee-Both ""
Tee-Both "[E] VPS-side commands (run separately on the VPS terminal)"
Tee-Both "------------------------------------------------------------"
Tee-Both "    This script is local-only by design. To complete CR-1 verification,"
Tee-Both "    SSH to the Mining Guardian VPS in your usual terminal and paste"
Tee-Both "    the block below. Send Rob/agent the output to merge into Section [F]."
Tee-Both ""
Tee-Both "    --- BEGIN VPS BLOCK (paste on VPS) ---"
Tee-Both ""
Tee-Both "    echo '=== journalctl guardian.service last 7d ==='"
Tee-Both "    journalctl -u guardian.service --since '7 days ago' --no-pager 2>/dev/null \\"
Tee-Both "        | grep -i -B 2 -A 20 'AttributeError' | head -200 \\"
Tee-Both "        || echo '(no AttributeError in journal)'"
Tee-Both "    echo"
Tee-Both "    echo '=== /var/log/guardian/*.log if present ==='"
Tee-Both "    ls -la /var/log/guardian/ 2>/dev/null || echo '(no /var/log/guardian dir)'"
Tee-Both "    grep -i -B 2 -A 20 'AttributeError' /var/log/guardian/*.log 2>/dev/null \\"
Tee-Both "        | tail -200 || echo '(no AttributeError in /var/log/guardian)'"
Tee-Both "    echo"
Tee-Both "    echo '=== narrow grep for the suspect token ==='"
Tee-Both "    journalctl -u guardian.service --since '30 days ago' --no-pager 2>/dev/null \\"
Tee-Both "        | grep -i 'auto_approve_enabled' \\"
Tee-Both "        || echo '(no auto_approve_enabled in journal)'"
Tee-Both ""
Tee-Both "    --- END VPS BLOCK ---"

# ---- F. Summary verdict ----
Tee-Both ""
Tee-Both "[F] Verdict"
Tee-Both "------------------------------------------------------------"
if (-not $narrow) {
    if ($broad) {
        Tee-Both "    auto_approve_enabled: NOT FOUND in working tree."
        Tee-Both ("    auto_approve (broad): FOUND " + $broad.Count + " match(es) -- these are env-var-driven, not attribute-driven.")
        Tee-Both "    => CR-1 downgrade is CONFIRMED. The 'AttributeError on auto_approve_enabled'"
        Tee-Both "       hypothesis from the original CRIT-5 manifest does not match the code."
        Tee-Both "    => Action: keep CR-1 in the manifest as 'verified non-issue (no attribute, no AttributeError trace)'."
        Tee-Both "       If section [E] surfaces a real AttributeError on a DIFFERENT attribute, escalate that"
        Tee-Both "       under a new ticket -- it is not CR-1."
    } else {
        Tee-Both "    No auto_approve references at all -- CR-1 is fully unfounded."
    }
} else {
    Tee-Both "    auto_approve_enabled: FOUND in working tree (see section [C])."
    Tee-Both "    => CR-1 was downgraded prematurely. Re-open."
}

Tee-Both ""
Tee-Both ("Report written to: " + $Report)
Tee-Both ("============================================================")
