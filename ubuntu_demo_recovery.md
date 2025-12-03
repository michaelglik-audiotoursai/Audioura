# Ubuntu Demo Recovery Guide
## Quick Start Instructions for v1.2.8+103

### 🚀 **IMMEDIATE ACTIONS NEEDED**

1. **Start Ubuntu VM**
   ```bash
   # In VirtualBox: Start Ubuntu 25.04 VM
   # Wait for desktop to load
   ```

2. **Test Network Connectivity**
   ```bash
   # In Ubuntu terminal:
   ping 10.0.2.2  # Should reach Windows host
   ```

3. **Start Web Demo (Using Workaround)**
   ```bash
   # Copy and run the workaround script:
   cp /media/sf_audiotours/start_flutter_web_demo.sh ~/
   bash ~/start_flutter_web_demo.sh
   ```

4. **Access Demo in Windows**
   ```
   Open browser: http://localhost:8080
   ```

### 🔧 **CURRENT ISSUE: VirtualBox Symlink Problem**

**Problem**: Flutter v1.2.8+103 can't create plugin symlinks in VirtualBox shared folders

**Solution**: `start_flutter_web_demo.sh` script copies files to local Ubuntu storage

**What the script does**:
- Copies essential files to `~/audiotours_web_demo/`
- Handles missing assets/env files
- Runs `flutter pub get` locally
- Starts web server on port 8080
- Cleans up when stopped

### 🧪 **TESTING WEB STORAGE (v1.2.8+103 Feature)**

**New Feature**: Web storage using `shared_preferences` instead of `path_provider`

**Test Steps**:
1. Load demo in browser
2. Try downloading a tour
3. Check if tour data persists
4. Verify no "MissingPluginException" errors

**Expected Results**:
- ✅ Tours download successfully
- ✅ Data stored in browser localStorage
- ✅ No file system errors
- ✅ Version info displays correctly

### 🤖 **AUTOMATED TESTING**

**Run Selenium Test Suite**:
```bash
# In Windows (with Chrome installed):
python test_flutter_web_demo.py
```

**Test Coverage**:
- App loading
- Map functionality  
- Tour interaction
- Navigation
- Responsive design
- **Web storage functionality** (NEW)
- Error handling

**Success Criteria**:
- 80%+ pass rate = Demo Ready
- 60%+ pass rate = Functional
- <60% pass rate = Needs Work

### 🚨 **TROUBLESHOOTING**

**If Ubuntu VM won't start**:
- Check VirtualBox VM settings
- Verify sufficient RAM allocated (4GB+)
- Check host system resources

**If port forwarding fails**:
- VirtualBox → VM Settings → Network → Advanced → Port Forwarding
- Rule: TCP, Host Port 8080, Guest Port 8080

**If Flutter web server fails**:
```bash
# Check Flutter installation:
flutter doctor

# Check web support:
flutter config --enable-web

# Manual startup:
cd ~/audiotours_web_demo
flutter run -d web-server --web-port 8080 --web-hostname 0.0.0.0
```

**If symlink errors persist**:
- Use the workaround script (copies files locally)
- Don't try to run Flutter directly from shared folder
- VirtualBox shared folders don't support symlinks

### 📊 **DEMO PRESENTATION STRATEGY**

**Highlight These Features**:
1. **Cross-platform capability**: "Runs on mobile, web, desktop"
2. **Web storage support**: "New v1.2.8+103 feature"
3. **Service integration**: "Real-time tour downloads"
4. **Responsive design**: "Works on all screen sizes"

**Handle These Limitations**:
1. **Audio playback**: "Full audio experience on mobile"
2. **Voice control**: "Voice commands work on mobile devices"
3. **File operations**: "Advanced features require mobile platform"

### 🔄 **RECOVERY CHECKLIST**

- [ ] Ubuntu VM started and accessible
- [ ] Network connectivity verified (ping 10.0.2.2)
- [ ] Workaround script copied and executable
- [ ] Flutter web server running on port 8080
- [ ] Windows browser can access localhost:8080
- [ ] Demo loads without critical errors
- [ ] Web storage functionality tested
- [ ] Selenium tests executed (optional)

### 📱 **MOBILE APP ALTERNATIVE**

**If web demo fails completely**:
- Use `audioura-dev.apk` on Android device
- Connect to same Windows Docker services
- Demonstrate full functionality including:
  - Voice control
  - Audio playback
  - File storage
  - Complete tour experience

### 🎯 **SUCCESS METRICS**

**Demo Ready Indicators**:
- App loads in <10 seconds
- Map displays with tour markers
- Tours download successfully (7MB+)
- No critical JavaScript errors
- Web storage works (localStorage used)
- Responsive on mobile/tablet/desktop

**Version Verification**:
- App shows v1.2.8+103
- Web storage replaces path_provider
- No "MissingPluginException" errors
- Improved tour data persistence

---
**Last Updated**: 2025-01-15
**Current Version**: v1.2.8+103 with web storage support
**Status**: Ready for testing with workaround script