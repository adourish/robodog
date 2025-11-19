# Fix Shadow Copy Storage
# Run as Administrator

Write-Host "Fixing Shadow Copy Storage..." -ForegroundColor Cyan

try {
    # Check current shadow storage
    Write-Host "`nCurrent Shadow Storage Configuration:" -ForegroundColor Yellow
    vssadmin list shadowstorage
    
    Write-Host "`nResizing shadow storage to 20GB..." -ForegroundColor Cyan
    
    # Resize shadow storage
    vssadmin resize shadowstorage /for=C: /on=C: /maxsize=20GB
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n✓ Shadow storage successfully resized to 20GB!" -ForegroundColor Green
        
        Write-Host "`nNew Shadow Storage Configuration:" -ForegroundColor Yellow
        vssadmin list shadowstorage
        
        Write-Host "`n✓ System Restore points can now be created" -ForegroundColor Green
    } else {
        Write-Host "`n✗ Failed to resize shadow storage" -ForegroundColor Red
        Write-Host "Error code: $LASTEXITCODE" -ForegroundColor Red
    }
} catch {
    Write-Host "`n✗ Error: $_" -ForegroundColor Red
}

Write-Host "`nPress any key to continue..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
