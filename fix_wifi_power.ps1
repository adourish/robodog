# Fix Wi-Fi Power Management
# Run as Administrator

Write-Host "Fixing Wi-Fi Power Management Settings..." -ForegroundColor Cyan

# Get Wi-Fi adapter
$adapter = Get-NetAdapter | Where-Object {$_.InterfaceDescription -like "*MediaTek*Wi-Fi*"}

if ($adapter) {
    Write-Host "Found adapter: $($adapter.InterfaceDescription)" -ForegroundColor Green
    
    # Get the device ID
    $deviceID = (Get-PnpDevice | Where-Object {$_.FriendlyName -like "*MediaTek*Wi-Fi*"}).InstanceId
    
    if ($deviceID) {
        Write-Host "Device ID: $deviceID" -ForegroundColor Yellow
        
        # Disable power management via registry
        $regPath = "HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e972-e325-11ce-bfc1-08002be10318}"
        
        # Find the adapter's registry key
        $subKeys = Get-ChildItem $regPath -ErrorAction SilentlyContinue
        
        foreach ($key in $subKeys) {
            $driverDesc = (Get-ItemProperty -Path $key.PSPath -Name "DriverDesc" -ErrorAction SilentlyContinue).DriverDesc
            
            if ($driverDesc -like "*MediaTek*Wi-Fi*") {
                Write-Host "Found registry key: $($key.PSPath)" -ForegroundColor Green
                
                # Set power management properties
                try {
                    Set-ItemProperty -Path $key.PSPath -Name "PnPCapabilities" -Value 24 -Type DWord -ErrorAction Stop
                    Write-Host "✓ Disabled 'Allow computer to turn off this device'" -ForegroundColor Green
                    
                    # Additional power settings
                    Set-ItemProperty -Path $key.PSPath -Name "*WakeOnMagicPacket" -Value 0 -Type String -ErrorAction SilentlyContinue
                    Set-ItemProperty -Path $key.PSPath -Name "*WakeOnPattern" -Value 0 -Type String -ErrorAction SilentlyContinue
                    
                    Write-Host "✓ Power management settings updated" -ForegroundColor Green
                } catch {
                    Write-Host "⚠ Could not modify registry: $_" -ForegroundColor Yellow
                }
            }
        }
        
        Write-Host "`n✓ Wi-Fi power management fixed!" -ForegroundColor Green
        Write-Host "Please restart your computer for changes to take effect." -ForegroundColor Yellow
    } else {
        Write-Host "Could not find device ID" -ForegroundColor Red
    }
} else {
    Write-Host "Wi-Fi adapter not found" -ForegroundColor Red
}

Write-Host "`nPress any key to continue..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
