# System Health Report - Windows Laptop
**Generated:** November 18, 2025  
**Device:** ASUS ROG Zephyrus G14  
**Storage:** WD PC SN740 512GB NVMe SSD

---

## 🔍 Issues Found

### 🔴 CRITICAL ISSUES

#### 1. Shadow Copy Storage Limit Reached
**Error:** Volsnap - Shadow copies aborted  
**Frequency:** 4 errors in last 1000 events  
**Last Occurrence:** November 16, 2025 8:42 PM

**Issue:**
```
The shadow copies of volume C: were aborted because the shadow 
copy storage could not grow due to a user imposed limit.
```

**Impact:**
- System Restore points cannot be created
- Windows Backup may fail
- File History may not work properly
- No recovery points available if system fails

**Fix:**
```powershell
# Run as Administrator
vssadmin resize shadowstorage /for=C: /on=C: /maxsize=20GB
# Or set to UNBOUNDED (not recommended on small drives)
vssadmin resize shadowstorage /for=C: /on=C: /maxsize=UNBOUNDED
```

---

#### 2. Wi-Fi Driver Power Management Issue
**Error:** Microsoft-Windows-NDIS - Fatal error  
**Frequency:** 3 errors in last 1000 events  
**Last Occurrence:** November 16, 2025 3:24 PM

**Issue:**
```
Miniport Microsoft Wi-Fi Direct Virtual Adapter #2 had event 
Fatal error: The miniport has failed a power transition to 
operational power
```

**Impact:**
- Wi-Fi may disconnect randomly
- Wi-Fi Direct features may not work
- Miracast/wireless display issues
- Network instability

**Fix:**
```powershell
# Disable Wi-Fi adapter power management
Get-NetAdapter | Where-Object {$_.Name -like "*Wi-Fi*"} | ForEach-Object {
    $adapter = $_
    $powerMgmt = Get-WmiObject MSPower_DeviceEnable -Namespace root\wmi | Where-Object {$_.InstanceName -like "*$($adapter.InterfaceGuid)*"}
    if ($powerMgmt) {
        $powerMgmt.Enable = $false
        $powerMgmt.Put()
    }
}
```

**Manual Fix:**
1. Open Device Manager
2. Expand "Network adapters"
3. Right-click "MediaTek Wi-Fi 6E MT7922" → Properties
4. Go to "Power Management" tab
5. **Uncheck** "Allow the computer to turn off this device to save power"
6. Click OK
7. Repeat for "Microsoft Wi-Fi Direct Virtual Adapter" entries

---

### ⚠️ WARNINGS

#### 3. Windows Defender Service Timeout
**Error:** Service Control Manager  
**Frequency:** 1 error  
**Last Occurrence:** November 16, 2025 5:14 AM

**Issue:**
```
A timeout (30000 milliseconds) was reached while waiting for 
a transaction response from the WinDefend service.
```

**Impact:**
- Windows Defender may be slow to respond
- Real-time protection delays
- System performance impact

**Fix:**
```powershell
# Restart Windows Defender service
Restart-Service -Name WinDefend -Force

# If issue persists, repair Windows Defender
# Run as Administrator
DISM /Online /Cleanup-Image /RestoreHealth
sfc /scannow
```

---

#### 4. Win32k Warnings
**Frequency:** Multiple warnings (8+ in recent logs)  
**Pattern:** Occurs regularly

**Issue:**
- Win32k subsystem warnings (graphics/window management)
- May be related to display driver or application compatibility

**Impact:**
- Minor display glitches possible
- Application rendering issues
- Usually benign but worth monitoring

**Fix:**
- Update graphics drivers (see recommendations below)
- Update Windows to latest version
- Monitor for specific application crashes

---

## 💾 Driver Status

### Graphics Drivers

#### NVIDIA GeForce RTX 4060 Laptop GPU
- **Current Version:** 32.0.15.6636
- **Driver Date:** December 2, 2024
- **Status:** ✅ **UP TO DATE** (Very recent!)
- **Manufacturer:** NVIDIA

#### AMD Radeon 780M Graphics (Integrated)
- **Current Version:** 31.0.14084.3001
- **Driver Date:** October 25, 2023
- **Status:** ⚠️ **OUTDATED** (Over 1 year old)
- **Manufacturer:** AMD

**Recommendation:**
```
Update AMD integrated graphics driver:
1. Visit: https://www.amd.com/en/support
2. Select: Ryzen 7000 Series → Ryzen 9 7940HS
3. Download latest driver package
4. Or use AMD Software: Adrenalin Edition auto-update
```

---

### Network Drivers

#### MediaTek Wi-Fi 6E MT7922 (RZ616)
- **Current Version:** 3.4.2.1046
- **Driver Date:** June 10, 2024
- **Status:** ⚠️ **SHOULD UPDATE** (5 months old)
- **Manufacturer:** MediaTek

**Recommendation:**
```
Update Wi-Fi driver (may fix power management issues):
1. Visit ASUS support site for ROG Zephyrus G14
2. Download latest MediaTek Wi-Fi driver
3. Or use Windows Update to check for driver updates
```

#### MediaTek Bluetooth Adapter
- **Current Version:** 1.1037.2.433
- **Driver Date:** June 5, 2024
- **Status:** ⚠️ **SHOULD UPDATE**
- **Manufacturer:** MediaTek

---

### Audio Drivers

#### Realtek High Definition Audio
- **Current Version:** 6.0.9590.1
- **Driver Date:** October 16, 2023
- **Status:** ⚠️ **OUTDATED** (Over 1 year old)

#### NVIDIA High Definition Audio
- **Current Version:** 1.4.2.6
- **Driver Date:** October 19, 2024
- **Status:** ✅ **RECENT**

**Recommendation:**
```
Update Realtek audio driver:
1. Visit ASUS support for your model
2. Download latest audio driver package
3. Includes Dolby Atmos and audio enhancements
```

---

## 🔧 Recommended Actions

### IMMEDIATE (Do Today)

1. **Fix Shadow Copy Storage** ⭐ CRITICAL
   ```powershell
   # Run PowerShell as Administrator
   vssadmin resize shadowstorage /for=C: /on=C: /maxsize=20GB
   ```

2. **Disable Wi-Fi Power Management** ⭐ CRITICAL
   - Device Manager → Network adapters
   - MediaTek Wi-Fi 6E → Properties → Power Management
   - Uncheck "Allow computer to turn off this device"

3. **Restart Windows Defender**
   ```powershell
   Restart-Service -Name WinDefend -Force
   ```

---

### THIS WEEK

4. **Update AMD Integrated Graphics Driver**
   - Download from AMD website
   - Current: Oct 2023 → Target: Latest 2024/2025

5. **Update MediaTek Wi-Fi Driver**
   - Download from ASUS support
   - May resolve power management issues

6. **Update Realtek Audio Driver**
   - Download from ASUS support
   - Improves audio quality and stability

7. **Run Windows Update**
   ```powershell
   # Check for updates
   Get-WindowsUpdate
   # Or use Settings → Windows Update
   ```

---

### MAINTENANCE

8. **Run System File Checker**
   ```powershell
   # Run as Administrator
   sfc /scannow
   ```

9. **Run DISM Tool**
   ```powershell
   # Run as Administrator
   DISM /Online /Cleanup-Image /RestoreHealth
   ```

10. **Check Disk Health**
    ```powershell
    # Check SMART status
    Get-PhysicalDisk | Get-StorageReliabilityCounter
    ```

11. **Clean Up Disk Space**
    ```powershell
    # Run Disk Cleanup
    cleanmgr /d C:
    ```

---

## 📊 System Summary

### Hardware
- **Laptop:** ASUS ROG Zephyrus G14
- **CPU:** AMD Ryzen 9 7940HS (16 cores)
- **GPU 1:** NVIDIA GeForce RTX 4060 Laptop
- **GPU 2:** AMD Radeon 780M (Integrated)
- **Storage:** WD PC SN740 512GB NVMe SSD
- **Status:** ✅ Healthy

### Storage
- **C: Drive (OS):** NTFS, Healthy
- **Total Capacity:** 512 GB
- **File System:** NTFS
- **Health:** ✅ OK

### Driver Status Summary
| Component | Status | Action |
|-----------|--------|--------|
| NVIDIA GPU | ✅ Current | None |
| AMD GPU | ⚠️ Outdated | Update |
| Wi-Fi | ⚠️ Old | Update |
| Bluetooth | ⚠️ Old | Update |
| Realtek Audio | ⚠️ Outdated | Update |
| NVIDIA Audio | ✅ Recent | None |

---

## 🎯 Priority Order

### Priority 1 (Critical - Do Today)
1. ✅ Fix Shadow Copy storage limit
2. ✅ Disable Wi-Fi power management
3. ✅ Restart Windows Defender

### Priority 2 (Important - This Week)
4. 🔄 Update AMD integrated graphics
5. 🔄 Update MediaTek Wi-Fi driver
6. 🔄 Update Realtek audio driver
7. 🔄 Run Windows Update

### Priority 3 (Maintenance - This Month)
8. 🔧 Run SFC scan
9. 🔧 Run DISM repair
10. 🔧 Check disk health
11. 🔧 Clean up disk space

---

## 📝 Notes

- **Overall System Health:** Good (no critical hardware failures)
- **Main Issues:** Software/driver configuration, not hardware
- **Risk Level:** Low to Medium
- **Estimated Fix Time:** 30-60 minutes for all critical fixes

---

## 🔗 Useful Links

**ASUS Support:**
- https://www.asus.com/support/
- Search for "ROG Zephyrus G14" + your model year

**Driver Downloads:**
- AMD Graphics: https://www.amd.com/en/support
- NVIDIA Graphics: https://www.nvidia.com/Download/index.aspx
- MediaTek: Via ASUS support site

**Windows Tools:**
- Windows Update: Settings → Windows Update
- Device Manager: Win+X → Device Manager
- Disk Cleanup: Search "Disk Cleanup"

---

**Report Complete** ✅
