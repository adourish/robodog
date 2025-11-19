# Verify System Fixes
# Check if the fixes were applied successfully

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  VERIFYING SYSTEM FIXES" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$allGood = $true

# Check 1: Shadow Copy Storage
Write-Host "1. Shadow Copy Storage:" -ForegroundColor Yellow
try {
    $vssOutput = vssadmin list shadowstorage 2>&1 | Out-String
    if ($vssOutput -match "Maximum Shadow Copy Storage space: 20") {
        Write-Host "   SUCCESS: Set to 20GB" -ForegroundColor Green
    } elseif ($vssOutput -match "Maximum Shadow Copy Storage space: UNBOUNDED") {
        Write-Host "   OK: Set to UNBOUNDED (unlimited)" -ForegroundColor Green
    } elseif ($vssOutput -match "You don't have the correct permissions") {
        Write-Host "   CANNOT VERIFY: Need Administrator privileges" -ForegroundColor Yellow
    } else {
        Write-Host "   NOT FIXED: Still at default limit" -ForegroundColor Red
        $allGood = $false
    }
} catch {
    Write-Host "   ERROR: $_" -ForegroundColor Red
    $allGood = $false
}
Write-Host ""

# Check 2: Wi-Fi Power Management
Write-Host "2. Wi-Fi Power Management:" -ForegroundColor Yellow
try {
    $regPath = "HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e972-e325-11ce-bfc1-08002be10318}"
    $subKeys = Get-ChildItem $regPath -ErrorAction SilentlyContinue
    
    $found = $false
    foreach ($key in $subKeys) {
        $driverDesc = (Get-ItemProperty -Path $key.PSPath -Name "DriverDesc" -ErrorAction SilentlyContinue).DriverDesc
        
        if ($driverDesc -like "*MediaTek*Wi-Fi*") {
            $found = $true
            $pnp = (Get-ItemProperty -Path $key.PSPath -Name "PnPCapabilities" -ErrorAction SilentlyContinue).PnPCapabilities
            
            Write-Host "   Adapter: $driverDesc" -ForegroundColor White
            Write-Host "   PnPCapabilities: $pnp" -ForegroundColor White
            
            if ($pnp -eq 24) {
                Write-Host "   SUCCESS: Power management disabled" -ForegroundColor Green
            } else {
                Write-Host "   NOT FIXED: Power management still enabled" -ForegroundColor Red
                $allGood = $false
            }
            break
        }
    }
    
    if (-not $found) {
        Write-Host "   WARNING: Wi-Fi adapter not found" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   ERROR: $_" -ForegroundColor Red
    $allGood = $false
}
Write-Host ""

# Check 3: Windows Defender
Write-Host "3. Windows Defender Service:" -ForegroundColor Yellow
try {
    $service = Get-Service -Name WinDefend
    Write-Host "   Status: $($service.Status)" -ForegroundColor White
    Write-Host "   Start Type: $($service.StartType)" -ForegroundColor White
    
    if ($service.Status -eq "Running") {
        Write-Host "   SUCCESS: Service is running" -ForegroundColor Green
    } else {
        Write-Host "   WARNING: Service is not running" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   ERROR: $_" -ForegroundColor Red
}
Write-Host ""

# Check 4: System File Integrity
Write-Host "4. System File Integrity:" -ForegroundColor Yellow
Write-Host "   To verify, run: sfc /verifyonly" -ForegroundColor White
Write-Host "   (This requires Administrator privileges)" -ForegroundColor Yellow
Write-Host ""

# Check for log file
Write-Host "5. Fix Script Log:" -ForegroundColor Yellow
$logFile = "C:\Projects\robodog\system_fixes_log.txt"
if (Test-Path $logFile) {
    $logInfo = Get-Item $logFile
    Write-Host "   Log file found: $logFile" -ForegroundColor Green
    Write-Host "   Last modified: $($logInfo.LastWriteTime)" -ForegroundColor White
    Write-Host "   Size: $($logInfo.Length) bytes" -ForegroundColor White
    Write-Host ""
    Write-Host "   Last 10 lines of log:" -ForegroundColor Cyan
    Get-Content $logFile -Tail 10 | ForEach-Object { Write-Host "   $_" -ForegroundColor White }
} else {
    Write-Host "   WARNING: No log file found" -ForegroundColor Yellow
    Write-Host "   The fix script may not have run yet" -ForegroundColor Yellow
}
Write-Host ""

# Summary
Write-Host "========================================" -ForegroundColor Cyan
if ($allGood) {
    Write-Host "  ALL FIXES VERIFIED!" -ForegroundColor Green
} else {
    Write-Host "  SOME FIXES NEED ATTENTION" -ForegroundColor Yellow
}
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not $allGood) {
    Write-Host "Run the fix script as Administrator:" -ForegroundColor Yellow
    Write-Host "  Right-click run_all_fixes.ps1 -> Run as Administrator" -ForegroundColor White
    Write-Host ""
}

Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
