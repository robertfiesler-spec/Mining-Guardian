@echo off
:: ============================================================================
:: Mining Guardian — Intelligence Catalog Importer Launcher
:: Double-click this file (or the desktop shortcut) to start the tool.
:: It will open your browser to http://localhost:5050 automatically.
:: Close this window to stop the server.
:: ============================================================================

title Mining Guardian Import Tool
color 0A

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║   Mining Guardian — Intelligence Catalog Importer   ║
echo  ║                                                     ║
echo  ║   Starting server on http://localhost:5050           ║
echo  ║   Your browser will open automatically.             ║
echo  ║                                                     ║
echo  ║   Close this window to stop the server.             ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

:: Navigate to the script's own directory
cd /d "%~dp0"

:: Load secrets (MG_DB_PASSWORD, MG_IMPORT_PASSWORD, MG_IMPORT_SECRET_KEY) from
:: %USERPROFILE%\.mining-guardian\secrets.bat if it exists. The installer
:: writes that file with `set` lines, e.g.:
::     set MG_DB_PASSWORD=...
::     set MG_IMPORT_PASSWORD=...
::     set MG_IMPORT_SECRET_KEY=...
if exist "%USERPROFILE%\.mining-guardian\secrets.bat" (
    call "%USERPROFILE%\.mining-guardian\secrets.bat"
) else (
    echo.
    echo  WARNING: %USERPROFILE%\.mining-guardian\secrets.bat not found.
    echo  mg_import will refuse to start without MG_DB_PASSWORD,
    echo  MG_IMPORT_PASSWORD, and MG_IMPORT_SECRET_KEY in the environment.
    echo.
)

:: Wait 2 seconds then open browser in background
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:5050"

:: Run the Flask app (this blocks until you close the window)
python mg_import.py

:: If python isn't on PATH, try py launcher
if %ERRORLEVEL% NEQ 0 (
    echo Trying py launcher...
    py mg_import.py
)

pause
