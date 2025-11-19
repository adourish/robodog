@echo off
:: Quick launcher for system fixes
:: This will request Administrator privileges automatically

echo ========================================
echo   SYSTEM HEALTH FIX LAUNCHER
echo ========================================
echo.
echo This will fix:
echo   - Shadow Copy storage limit
echo   - Wi-Fi power management
echo   - Windows Defender service
echo   - System file integrity
echo.
echo Press any key to continue...
pause >nul

:: Request Administrator privileges
powershell -Command "Start-Process PowerShell -ArgumentList '-ExecutionPolicy Bypass -File ""%~dp0run_all_fixes.ps1""' -Verb RunAs"
