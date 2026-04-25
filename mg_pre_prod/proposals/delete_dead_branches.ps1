# delete_dead_branches.ps1
# ----------------------------------------------------------------------
# Deletes 4 dead remote branches on robertfiesler-spec/Mining-Guardian.
#
# All 4 branches were verified 0 commits ahead of main on 2026-04-25
# during the pre-prod audit. SHA pinning below ensures the script
# refuses to run if any branch has advanced since verification.
#
# Branches:
#   feature/ai-learning-enhancements  f1b3cdc  (0 ahead, 394 behind)
#   realtime-and-observability        e5626c2  (0 ahead, 342 behind)
#   refactor/repo-structure           e46db9b  (0 ahead, 412 behind)
#   security/hardening-apr21          c2ca55c  (0 ahead, 103 behind)
#
# Usage (from PowerShell on ROBS-PC):
#   .\delete_dead_branches.ps1               # dry-run, lists what would happen
#   .\delete_dead_branches.ps1 -Apply        # actually delete
#
# Requires: gh CLI authenticated (gh auth status)
# Run AFTER the Sunday typo rename and CR-4 PR merge.
# ----------------------------------------------------------------------

param(
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'

$Owner = 'robertfiesler-spec'
$Repo  = 'Mining-Guardian'

# Branch -> expected short SHA (pinned 2026-04-25 17:48 CDT)
$Branches = [ordered]@{
    'feature/ai-learning-enhancements' = 'f1b3cdc'
    'realtime-and-observability'       = 'e5626c2'
    'refactor/repo-structure'          = 'e46db9b'
    'security/hardening-apr21'         = 'c2ca55c'
}

Write-Host '=========================================='
Write-Host 'Mining-Guardian dead-branch cleanup'
Write-Host "Repo: $Owner/$Repo"
if ($Apply) {
    Write-Host 'MODE: APPLY  (branches WILL be deleted)' -ForegroundColor Yellow
} else {
    Write-Host 'MODE: DRY-RUN  (no changes; pass -Apply to delete)' -ForegroundColor Cyan
}
Write-Host '=========================================='
Write-Host ''

# Pre-flight: gh auth
try {
    $null = & gh auth status 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'gh auth status failed' }
} catch {
    Write-Host 'ERROR: gh CLI not authenticated. Run: gh auth login' -ForegroundColor Red
    exit 1
}

# Verify each branch SHA against pinned value
$verified = @()
$drift    = @()
$missing  = @()

foreach ($entry in $Branches.GetEnumerator()) {
    $branch      = $entry.Key
    $expectedSha = $entry.Value
    $apiPath     = "repos/$Owner/$Repo/branches/$branch"

    Write-Host "Checking $branch (expected $expectedSha) ... " -NoNewline
    $raw = & gh api $apiPath 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'NOT FOUND' -ForegroundColor DarkYellow
        $missing += $branch
        continue
    }

    $actualFullSha = ($raw | ConvertFrom-Json).commit.sha
    $actualShort   = $actualFullSha.Substring(0,7)

    if ($actualShort -eq $expectedSha) {
        Write-Host "OK ($actualShort)" -ForegroundColor Green
        $verified += [pscustomobject]@{ Branch=$branch; Sha=$actualShort }
    } else {
        Write-Host "DRIFT (got $actualShort)" -ForegroundColor Red
        $drift += [pscustomobject]@{ Branch=$branch; Expected=$expectedSha; Actual=$actualShort }
    }
}

Write-Host ''
Write-Host '------ Summary ------'
Write-Host ("  Verified: {0}" -f $verified.Count)
Write-Host ("  Drift:    {0}" -f $drift.Count)
Write-Host ("  Missing:  {0}" -f $missing.Count)
Write-Host ''

if ($drift.Count -gt 0) {
    Write-Host 'ABORT: One or more branches have advanced since pinning.' -ForegroundColor Red
    Write-Host 'Re-verify ahead/behind counts before deleting:' -ForegroundColor Red
    foreach ($d in $drift) {
        Write-Host ("  {0}: expected {1}, actual {2}" -f $d.Branch, $d.Expected, $d.Actual) -ForegroundColor Red
    }
    exit 2
}

if ($verified.Count -eq 0) {
    Write-Host 'Nothing to do (no branches verified).' -ForegroundColor Cyan
    exit 0
}

if (-not $Apply) {
    Write-Host 'DRY-RUN: would delete the following branches:' -ForegroundColor Cyan
    foreach ($v in $verified) {
        Write-Host ("  - {0}  ({1})" -f $v.Branch, $v.Sha)
    }
    Write-Host ''
    Write-Host 'Re-run with -Apply to delete.' -ForegroundColor Cyan
    exit 0
}

# APPLY mode
Write-Host 'Deleting verified branches...' -ForegroundColor Yellow
$deleted = 0
$failed  = @()
foreach ($v in $verified) {
    $ref = "repos/$Owner/$Repo/git/refs/heads/$($v.Branch)"
    Write-Host ("  DELETE {0} ({1}) ... " -f $v.Branch, $v.Sha) -NoNewline
    & gh api -X DELETE $ref 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'OK' -ForegroundColor Green
        $deleted++
    } else {
        Write-Host 'FAILED' -ForegroundColor Red
        $failed += $v.Branch
    }
}

Write-Host ''
Write-Host ("Deleted: {0} / {1}" -f $deleted, $verified.Count)
if ($failed.Count -gt 0) {
    Write-Host 'Failed branches:' -ForegroundColor Red
    foreach ($f in $failed) { Write-Host "  - $f" -ForegroundColor Red }
    exit 3
}

Write-Host 'Done.' -ForegroundColor Green
exit 0
