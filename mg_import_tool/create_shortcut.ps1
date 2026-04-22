# ============================================================================
# Creates a Desktop shortcut for the Mining Guardian Import Tool
# Run once: right-click this file → Run with PowerShell
# ============================================================================

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BatPath   = Join-Path $ScriptDir "launch_mg_import.bat"
$IconPath  = Join-Path $ScriptDir "mg_import.ico"
$Desktop   = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "MG Import Tool.lnk"

# Create the shortcut
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $BatPath
$Shortcut.WorkingDirectory = $ScriptDir
$Shortcut.Description = "Mining Guardian Intelligence Catalog Importer"
$Shortcut.WindowStyle = 1  # Normal window

# Use a built-in Windows icon if no custom .ico exists
if (Test-Path $IconPath) {
    $Shortcut.IconLocation = $IconPath
} else {
    # Database icon from shell32.dll
    $Shortcut.IconLocation = "%SystemRoot%\System32\shell32.dll,15"
}

$Shortcut.Save()

Write-Host ""
Write-Host "  Desktop shortcut created: $ShortcutPath" -ForegroundColor Green
Write-Host "  Double-click 'MG Import Tool' on your desktop to launch." -ForegroundColor Green
Write-Host ""
Write-Host "  Press any key to close..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
