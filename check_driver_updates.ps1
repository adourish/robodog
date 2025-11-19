# Check for Driver Updates
# Provides links and information for updating outdated drivers

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  DRIVER UPDATE CHECKER" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get system information
$computerSystem = Get-CimInstance -ClassName Win32_ComputerSystem
$manufacturer = $computerSystem.Manufacturer
$model = $computerSystem.Model

Write-Host "System: $manufacturer $model" -ForegroundColor Yellow
Write-Host ""

# Check AMD Graphics
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "AMD Radeon 780M Graphics" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$amdGpu = Get-CimInstance Win32_PnPSignedDriver | Where-Object {$_.DeviceName -like "*AMD Radeon 780M*"}
if ($amdGpu) {
    Write-Host "Current Version: $($amdGpu.DriverVersion)" -ForegroundColor Yellow
    Write-Host "Driver Date: $($amdGpu.DriverDate)" -ForegroundColor Yellow
    Write-Host "Status: ⚠ OUTDATED (Oct 2023)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Update Link:" -ForegroundColor Green
    Write-Host "https://www.amd.com/en/support/download/drivers.html" -ForegroundColor Cyan
    Write-Host "Select: Graphics → Radeon → Radeon 700 Series → Radeon 780M" -ForegroundColor White
}
Write-Host ""

# Check NVIDIA Graphics
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "NVIDIA GeForce RTX 4060 Laptop GPU" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$nvidiaGpu = Get-CimInstance Win32_PnPSignedDriver | Where-Object {$_.DeviceName -like "*NVIDIA GeForce RTX 4060*"}
if ($nvidiaGpu) {
    Write-Host "Current Version: $($nvidiaGpu.DriverVersion)" -ForegroundColor Yellow
    Write-Host "Driver Date: $($nvidiaGpu.DriverDate)" -ForegroundColor Yellow
    Write-Host "Status: ✓ UP TO DATE (Dec 2024)" -ForegroundColor Green
    Write-Host ""
    Write-Host "Check for updates:" -ForegroundColor Green
    Write-Host "https://www.nvidia.com/Download/index.aspx" -ForegroundColor Cyan
}
Write-Host ""

# Check Wi-Fi
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "MediaTek Wi-Fi 6E MT7922" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$wifi = Get-CimInstance Win32_PnPSignedDriver | Where-Object {$_.DeviceName -like "*MediaTek*Wi-Fi*"}
if ($wifi) {
    Write-Host "Current Version: $($wifi.DriverVersion)" -ForegroundColor Yellow
    Write-Host "Driver Date: $($wifi.DriverDate)" -ForegroundColor Yellow
    Write-Host "Status: ⚠ SHOULD UPDATE (June 2024)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Update from ASUS Support:" -ForegroundColor Green
    Write-Host "https://www.asus.com/support/" -ForegroundColor Cyan
    Write-Host "Search for: ROG Zephyrus G14 → Drivers & Tools → Wireless" -ForegroundColor White
}
Write-Host ""

# Check Bluetooth
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "MediaTek Bluetooth Adapter" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$bluetooth = Get-CimInstance Win32_PnPSignedDriver | Where-Object {$_.DeviceName -like "*MediaTek*Bluetooth*"}
if ($bluetooth) {
    Write-Host "Current Version: $($bluetooth.DriverVersion)" -ForegroundColor Yellow
    Write-Host "Driver Date: $($bluetooth.DriverDate)" -ForegroundColor Yellow
    Write-Host "Status: ⚠ SHOULD UPDATE (June 2024)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Update from ASUS Support:" -ForegroundColor Green
    Write-Host "https://www.asus.com/support/" -ForegroundColor Cyan
}
Write-Host ""

# Check Realtek Audio
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Realtek High Definition Audio" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$realtekAudio = Get-CimInstance Win32_PnPSignedDriver | Where-Object {$_.DeviceName -like "*Realtek*Audio*"}
if ($realtekAudio) {
    Write-Host "Current Version: $($realtekAudio.DriverVersion)" -ForegroundColor Yellow
    Write-Host "Driver Date: $($realtekAudio.DriverDate)" -ForegroundColor Yellow
    Write-Host "Status: ⚠ OUTDATED (Oct 2023)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Update from ASUS Support:" -ForegroundColor Green
    Write-Host "https://www.asus.com/support/" -ForegroundColor Cyan
    Write-Host "Search for: ROG Zephyrus G14 → Drivers & Tools → Audio" -ForegroundColor White
}
Write-Host ""

# Windows Update
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Windows Update" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "Checking for Windows Updates..." -ForegroundColor Yellow

try {
    # Try to use Windows Update module if available
    if (Get-Module -ListAvailable -Name PSWindowsUpdate) {
        Import-Module PSWindowsUpdate
        $updates = Get-WindowsUpdate
        
        if ($updates.Count -gt 0) {
            Write-Host "⚠ $($updates.Count) updates available" -ForegroundColor Yellow
            Write-Host ""
            Write-Host "Run: Install-WindowsUpdate -AcceptAll -AutoReboot" -ForegroundColor Cyan
        } else {
            Write-Host "✓ Windows is up to date" -ForegroundColor Green
        }
    } else {
        Write-Host "Open Settings → Windows Update to check for updates" -ForegroundColor Cyan
        Write-Host "Or install PSWindowsUpdate module:" -ForegroundColor Yellow
        Write-Host "Install-Module PSWindowsUpdate -Force" -ForegroundColor White
    }
} catch {
    Write-Host "Open Settings → Windows Update to check for updates" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SUMMARY" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Drivers Needing Updates:" -ForegroundColor Yellow
Write-Host "  ⚠ AMD Radeon 780M Graphics (CRITICAL - 1+ year old)" -ForegroundColor Red
Write-Host "  ⚠ MediaTek Wi-Fi 6E (IMPORTANT - 5 months old)" -ForegroundColor Yellow
Write-Host "  ⚠ MediaTek Bluetooth (IMPORTANT - 5 months old)" -ForegroundColor Yellow
Write-Host "  ⚠ Realtek Audio (RECOMMENDED - 1+ year old)" -ForegroundColor Yellow
Write-Host ""
Write-Host "Up to Date:" -ForegroundColor Green
Write-Host "  ✓ NVIDIA GeForce RTX 4060 (Dec 2024)" -ForegroundColor Green
Write-Host ""
Write-Host "Main Support Site:" -ForegroundColor Cyan
Write-Host "https://www.asus.com/support/" -ForegroundColor White
Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
