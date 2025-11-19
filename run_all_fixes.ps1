# Master Fix Script - Run All System Fixes
# MUST RUN AS ADMINISTRATOR

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SYSTEM HEALTH FIX - ALL REPAIRS" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "⚠ WARNING: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Right-click this script and select 'Run as Administrator'" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Press any key to exit..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

Write-Host "✓ Running with Administrator privileges" -ForegroundColor Green
Write-Host ""

# Fix 1: Shadow Copy Storage
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "FIX 1: Shadow Copy Storage" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

try {
    Write-Host "Resizing shadow storage to 20GB..." -ForegroundColor Yellow
    vssadmin resize shadowstorage /for=C: /on=C: /maxsize=20GB | Out-Null
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Shadow storage fixed!" -ForegroundColor Green
    } else {
        Write-Host "⚠ Shadow storage resize returned code: $LASTEXITCODE" -ForegroundColor Yellow
    }
} catch {
    Write-Host "✗ Error fixing shadow storage: $_" -ForegroundColor Red
}

Write-Host ""
Start-Sleep -Seconds 2

# Fix 2: Wi-Fi Power Management
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "FIX 2: Wi-Fi Power Management" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

try {
    $regPath = "HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e972-e325-11ce-bfc1-08002be10318}"
    $subKeys = Get-ChildItem $regPath -ErrorAction SilentlyContinue
    
    $fixed = $false
    foreach ($key in $subKeys) {
        $driverDesc = (Get-ItemProperty -Path $key.PSPath -Name "DriverDesc" -ErrorAction SilentlyContinue).DriverDesc
        
        if ($driverDesc -like "*MediaTek*Wi-Fi*") {
            Write-Host "Found: $driverDesc" -ForegroundColor Yellow
            Set-ItemProperty -Path $key.PSPath -Name "PnPCapabilities" -Value 24 -Type DWord -ErrorAction Stop
            Write-Host "✓ Wi-Fi power management disabled!" -ForegroundColor Green
            $fixed = $true
            break
        }
    }
    
    if (-not $fixed) {
        Write-Host "⚠ Wi-Fi adapter not found in registry" -ForegroundColor Yellow
    }
} catch {
    Write-Host "✗ Error fixing Wi-Fi: $_" -ForegroundColor Red
}

Write-Host ""
Start-Sleep -Seconds 2

# Fix 3: Windows Defender
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "FIX 3: Windows Defender Service" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

try {
    Write-Host "Restarting Windows Defender..." -ForegroundColor Yellow
    Restart-Service -Name WinDefend -Force -ErrorAction Stop
    Write-Host "✓ Windows Defender restarted!" -ForegroundColor Green
} catch {
    Write-Host "⚠ Could not restart service (may be protected)" -ForegroundColor Yellow
    Write-Host "Updating definitions instead..." -ForegroundColor Yellow
    Update-MpSignature -ErrorAction SilentlyContinue
    Write-Host "✓ Definitions updated" -ForegroundColor Green
}

Write-Host ""
Start-Sleep -Seconds 2

# Fix 4: System File Check
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "FIX 4: System File Integrity" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "Running System File Checker (this may take several minutes)..." -ForegroundColor Yellow
Write-Host "Please wait..." -ForegroundColor Yellow

try {
    $sfcResult = sfc /scannow
    if ($sfcResult -match "did not find any integrity violations") {
        Write-Host "✓ System files are healthy!" -ForegroundColor Green
    } elseif ($sfcResult -match "found corrupt files and successfully repaired them") {
        Write-Host "✓ System files repaired!" -ForegroundColor Green
    } else {
        Write-Host "⚠ SFC completed with warnings" -ForegroundColor Yellow
    }
} catch {
    Write-Host "✗ Error running SFC: $_" -ForegroundColor Red
}

Write-Host ""
Start-Sleep -Seconds 2

# Summary
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  FIXES COMPLETE!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Restart your computer for changes to take effect" -ForegroundColor White
Write-Host "2. Update drivers (AMD GPU, MediaTek Wi-Fi, Realtek Audio)" -ForegroundColor White
Write-Host "3. Run Windows Update" -ForegroundColor White
Write-Host ""
Write-Host "Driver update links saved in SYSTEM_HEALTH_REPORT.md" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
