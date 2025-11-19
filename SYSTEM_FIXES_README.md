# System Fixes - Quick Start Guide

## 🚀 Quick Fix (Recommended)

**Run this ONE script as Administrator:**

```powershell
# Right-click → Run as Administrator
.\run_all_fixes.ps1
```

This will automatically fix:
- ✅ Shadow Copy storage limit
- ✅ Wi-Fi power management
- ✅ Windows Defender service
- ✅ System file integrity

**Then restart your computer.**

---

## 📋 Individual Fix Scripts

If you prefer to run fixes individually:

### 1. Fix Shadow Copy Storage (CRITICAL)
```powershell
# Right-click → Run as Administrator
.\fix_shadow_storage.ps1
```
**Fixes:** System Restore not working, backup failures

### 2. Fix Wi-Fi Power Management (CRITICAL)
```powershell
# Right-click → Run as Administrator
.\fix_wifi_power.ps1
```
**Fixes:** Wi-Fi disconnections, network instability

### 3. Fix Windows Defender (IMPORTANT)
```powershell
# Right-click → Run as Administrator
.\fix_windows_defender.ps1
```
**Fixes:** Defender service timeouts, slow response

### 4. Check Driver Updates (RECOMMENDED)
```powershell
# Can run without Administrator
.\check_driver_updates.ps1
```
**Shows:** Which drivers need updating and where to get them

---

## ⚠️ Important Notes

### Administrator Privileges Required

Most fixes require Administrator privileges:

1. **Right-click** the PowerShell script
2. Select **"Run as Administrator"**
3. Click **"Yes"** when prompted

### Execution Policy

If you get an error about execution policy:

```powershell
# Run PowerShell as Administrator, then:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### After Running Fixes

**RESTART YOUR COMPUTER** for all changes to take effect.

---

## 📊 What Each Fix Does

### Shadow Copy Storage Fix
- Increases shadow storage limit from default to 20GB
- Allows System Restore to create recovery points
- Enables Windows Backup to function properly
- **Impact:** CRITICAL - No backups without this

### Wi-Fi Power Management Fix
- Disables "Allow computer to turn off device to save power"
- Prevents Wi-Fi adapter from entering low-power states
- Stops network disconnections during sleep/idle
- **Impact:** CRITICAL - Fixes frequent disconnects

### Windows Defender Fix
- Restarts the Windows Defender service
- Updates virus definitions
- Clears service timeout issues
- **Impact:** IMPORTANT - Ensures real-time protection

### System File Check
- Scans Windows system files for corruption
- Repairs corrupted files automatically
- Ensures system stability
- **Impact:** MAINTENANCE - Prevents future issues

---

## 🔧 Driver Updates Needed

After running the fixes, update these drivers:

### Priority 1 (Critical)
**AMD Radeon 780M Graphics**
- Current: Oct 2023 (over 1 year old!)
- Download: https://www.amd.com/en/support
- **Why:** Performance improvements, bug fixes, security updates

### Priority 2 (Important)
**MediaTek Wi-Fi 6E MT7922**
- Current: June 2024 (5 months old)
- Download: ASUS Support site
- **Why:** May fix remaining power management issues

**MediaTek Bluetooth**
- Current: June 2024 (5 months old)
- Download: ASUS Support site
- **Why:** Improved connectivity and stability

### Priority 3 (Recommended)
**Realtek Audio**
- Current: Oct 2023 (over 1 year old)
- Download: ASUS Support site
- **Why:** Better audio quality, Dolby Atmos updates

---

## 🌐 Driver Download Links

### ASUS Support (Main Site)
https://www.asus.com/support/
- Search for: "ROG Zephyrus G14"
- Select your model year
- Go to: Drivers & Tools

### AMD Graphics
https://www.amd.com/en/support
- Select: Graphics → Radeon → Radeon 700 Series → Radeon 780M

### NVIDIA Graphics (Already Up to Date!)
https://www.nvidia.com/Download/index.aspx
- Your NVIDIA driver is current (Dec 2024)
- No update needed

---

## ✅ Verification

After running fixes and restarting, verify:

### Check Shadow Copy
```powershell
vssadmin list shadowstorage
```
Should show: "Maximum Shadow Copy Storage space: 20 GB"

### Check Wi-Fi Power Management
1. Open Device Manager
2. Network adapters → MediaTek Wi-Fi 6E
3. Properties → Power Management
4. Should be UNCHECKED: "Allow computer to turn off this device"

### Check Windows Defender
```powershell
Get-Service WinDefend
```
Should show: Status = Running

### Check System Files
```powershell
# Run as Administrator
sfc /verifyonly
```
Should show: "did not find any integrity violations"

---

## 🔄 Maintenance Schedule

### Weekly
- Run Windows Update
- Check for driver updates

### Monthly
- Run `sfc /scannow`
- Check disk space
- Review system logs

### Quarterly
- Update all drivers
- Clean up disk space
- Review startup programs

---

## 📞 Need Help?

### If Fixes Don't Work

1. **Check Event Viewer** for new errors:
   ```powershell
   Get-WinEvent -LogName System -MaxEvents 50 | Where-Object {$_.LevelDisplayName -eq "Error"}
   ```

2. **Run DISM Tool** (if SFC fails):
   ```powershell
   # Run as Administrator
   DISM /Online /Cleanup-Image /RestoreHealth
   ```

3. **Safe Mode** (if system is unstable):
   - Restart → Hold Shift while clicking Restart
   - Troubleshoot → Advanced → Startup Settings → Restart
   - Press 4 for Safe Mode

### Resources

- **System Health Report:** `SYSTEM_HEALTH_REPORT.md`
- **ASUS Support:** https://www.asus.com/support/
- **Windows Support:** https://support.microsoft.com/

---

## 📝 Files Included

| File | Purpose | Admin Required |
|------|---------|----------------|
| `run_all_fixes.ps1` | Run all fixes at once | ✅ Yes |
| `fix_shadow_storage.ps1` | Fix System Restore | ✅ Yes |
| `fix_wifi_power.ps1` | Fix Wi-Fi disconnects | ✅ Yes |
| `fix_windows_defender.ps1` | Fix Defender service | ✅ Yes |
| `check_driver_updates.ps1` | Check driver status | ❌ No |
| `SYSTEM_HEALTH_REPORT.md` | Detailed analysis | - |
| `SYSTEM_FIXES_README.md` | This file | - |

---

## ⏱️ Time Required

- **Quick Fix (run_all_fixes.ps1):** 5-10 minutes
- **Individual Fixes:** 2-3 minutes each
- **Driver Updates:** 15-30 minutes total
- **System Restart:** 2-3 minutes

**Total Time:** 30-45 minutes for complete system health restoration

---

**🎉 Your system will be much healthier after these fixes!**

**Remember to restart your computer after running the fixes.**
