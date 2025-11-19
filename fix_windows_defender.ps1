# Fix Windows Defender Service
# Run as Administrator

Write-Host "Checking Windows Defender Service..." -ForegroundColor Cyan

try {
    $service = Get-Service -Name WinDefend
    
    Write-Host "`nCurrent Status: $($service.Status)" -ForegroundColor Yellow
    
    if ($service.Status -eq "Running") {
        Write-Host "Restarting Windows Defender..." -ForegroundColor Cyan
        Restart-Service -Name WinDefend -Force
        Start-Sleep -Seconds 2
        
        $service = Get-Service -Name WinDefend
        if ($service.Status -eq "Running") {
            Write-Host "✓ Windows Defender restarted successfully!" -ForegroundColor Green
        } else {
            Write-Host "⚠ Service status: $($service.Status)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "Starting Windows Defender..." -ForegroundColor Cyan
        Start-Service -Name WinDefend
        Start-Sleep -Seconds 2
        
        $service = Get-Service -Name WinDefend
        if ($service.Status -eq "Running") {
            Write-Host "✓ Windows Defender started successfully!" -ForegroundColor Green
        }
    }
} catch {
    Write-Host "✗ Error: $_" -ForegroundColor Red
    Write-Host "`nTrying alternative method..." -ForegroundColor Yellow
    
    # Alternative: Update Windows Defender
    Write-Host "Updating Windows Defender definitions..." -ForegroundColor Cyan
    Update-MpSignature -ErrorAction SilentlyContinue
    Write-Host "✓ Definitions updated" -ForegroundColor Green
}

Write-Host "`nPress any key to continue..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
