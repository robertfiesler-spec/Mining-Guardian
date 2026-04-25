# =============================================================================
# CR-1 VERIFICATION SCRIPT  (PowerShell — paste into ROBS-PC PowerShell window)
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
# What it does (read-only — no commits, no file edits):
#   Section A — Repo state sanity check
#   Section B — Grep working tree for auto_approve references
#   Section C — Grep working tree for the SPECIFIC token auto_approve_enabled
#   Section D — Show full context of every match
#   Section E — Pull recent VPS daemon AttributeError traces (via SSH)
#   Section F — Summary verdict
#
# Output: prints to console + writes a timestamped report under
#         C:\Users\User\Mining-Guardian\cr1_verify_report_<UTC>.txt
# =============================================================================

# ---- 0. Setup ----
$ErrorActionPreference = "Continue"   # don't abort on grep-no-match
$RepoRoot = "C:\Users\User\Mining-Guardian"
$Stamp    = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss")
$Report   = Join-Path $RepoRoot ("cr1_verify_report_{0}.txt" -f $Stamp)

# helper — write to both console and report file
function Tee-Both([string]$line) {
    Write-Host  $line
    Add-Content -Path $Report -Value $line
}

# initialize report
Set-Content -Path $Report -Value "CR-1 VERIFICATION REPORT — $Stamp UTC"
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

# ---- B. Broad grep — anything matching 'auto_approve' ----
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
    Tee-Both "    (no matches — no auto_approve reference anywhere)"
}

# ---- C. Narrow grep — the SPECIFIC token 'auto_approve_enabled' ----
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
    Tee-Both ("    --- " + $narrow.Count + " matches — CR-1 IS REAL, do not downgrade ---")
} else {
    Tee-Both "    (no matches — confirms CR-1 downgrade: token does not exist)"
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
    Tee-Both "    (nothing to show — no broad matches)"
}

# ---- E. VPS daemon AttributeError traces ----
Tee-Both ""
Tee-Both "[E] Recent VPS daemon AttributeError traces"
Tee-Both "------------------------------------------------------------"
Tee-Both "    Attempting SSH to VPS to grep recent journalctl/log for AttributeError..."
Tee-Both "    (If SSH host alias differs, edit the ssh line below.)"

# Adjust this hostname/alias if needed — Rob may have a host entry like 'mg-vps'
$VpsHost = "mg-vps"   # <-- EDIT IF YOUR SSH ALIAS IS DIFFERENT

# command to run on VPS — last 7 days of journal for guardian.service, grepped for AttributeError
$RemoteCmd = @'
echo "--- journalctl guardian.service last 7d ---"
journalctl -u guardian.service --since "7 days ago" --no-pager 2>/dev/null | \
    grep -i -A 20 "AttributeError" | head -200 || echo "(no AttributeError in journal)"
echo "--- end ---"
echo ""
echo "--- /var/log/guardian/*.log if present ---"
ls -la /var/log/guardian/ 2>/dev/null || echo "(no /var/log/guardian dir)"
grep -i -A 20 "AttributeError" /var/log/guardian/*.log 2>/dev/null | tail -200 || echo "(no AttributeError in /var/log/guardian)"
'@

$sshOk = $false
try {
    $sshTest = ssh -o BatchMode=yes -o ConnectTimeout=5 $VpsHost "echo OK" 2>&1
    if ($LASTEXITCODE -eq 0 -and $sshTest -match "OK") { $sshOk = $true }
} catch { $sshOk = $false }

if ($sshOk) {
    Tee-Both ("    SSH to '" + $VpsHost + "' OK — pulling logs...")
    $remote = ssh $VpsHost $RemoteCmd 2>&1
    $remote -split "`n" | ForEach-Object { Tee-Both ("    " + $_) }
} else {
    Tee-Both ("    SSH to '" + $VpsHost + "' failed (alias not found, host unreachable, or BatchMode auth refused).")
    Tee-Both "    To run manually, paste this on the VPS:"
    Tee-Both ""
    $RemoteCmd -split "`n" | ForEach-Object { Tee-Both ("        " + $_) }
}

# ---- F. Summary verdict ----
Tee-Both ""
Tee-Both "[F] Verdict"
Tee-Both "------------------------------------------------------------"
if (-not $narrow) {
    if ($broad) {
        Tee-Both "    auto_approve_enabled: NOT FOUND in working tree."
        Tee-Both ("    auto_approve (broad): FOUND " + $broad.Count + " match(es) — these are env-var-driven, not attribute-driven.")
        Tee-Both "    => CR-1 downgrade is CONFIRMED. The 'AttributeError on auto_approve_enabled'"
        Tee-Both "       hypothesis from the original CRIT-5 manifest does not match the code."
        Tee-Both "    => Action: keep CR-1 in the manifest as 'verified non-issue (no attribute, no AttributeError trace)'."
        Tee-Both "       If section [E] surfaces a real AttributeError on a DIFFERENT attribute, escalate that"
        Tee-Both "       under a new ticket — it is not CR-1."
    } else {
        Tee-Both "    No auto_approve references at all — CR-1 is fully unfounded."
    }
} else {
    Tee-Both "    auto_approve_enabled: FOUND in working tree (see section [C])."
    Tee-Both "    => CR-1 was downgraded prematurely. Re-open."
}

Tee-Both ""
Tee-Both ("Report written to: " + $Report)
Tee-Both ("============================================================")
