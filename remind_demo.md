# AudioTours Demo Amazon-Q Context
## Ubuntu Demo Environment & Status

### 🎯 **Demo Amazon-Q Role & Responsibilities**
**RESPONSIBLE FOR:**
- Ubuntu demo functionality and troubleshooting
- Cross-platform testing and validation
- Demo presentation guidance and strategy
- Automated testing with Selenium
- VirtualBox configuration and networking
- Demo environment setup and recovery

**NOT RESPONSIBLE FOR:**
- Backend Docker services (Services Amazon-Q responsibility)
- Mobile app code changes (Mobile App Amazon-Q responsibility)
- Database modifications or service fixes

**COMMUNICATION PROTOCOL:**
- Issues with services: Create MD file in `c:\Users\micha\eclipse-workspace\amazon-q-communications\audiotours\requirements\`
- Mobile app issues: Communicate via same communication layer
- Focus on demo environment, testing, and presentation aspects only

### 🖥️ **Current Demo Environment**
- **Host OS**: Windows 10/11
- **VM**: Ubuntu 25.04 in VirtualBox (NAT networking)
- **Ubuntu IP**: 10.0.2.15 (guest)
- **Windows IP**: 10.0.2.2 (host from Ubuntu perspective)
- **Flutter Project**: `/home/Ubuntu/audiotours_local/audio_tour_app/`
- **Demo URL**: `http://localhost:8080` (Windows browser via port forwarding)

### 🌐 **Network Configuration**
**VirtualBox Port Forwarding Rule:**
- Protocol: TCP
- Host IP: (empty)
- Host Port: 8080
- Guest IP: (empty) 
- Guest Port: 8080

**Connectivity Status:**
- ✅ Ubuntu → Windows: `ping 10.0.2.2` (successful)
- ❌ Windows → Ubuntu: `ping 10.0.2.15` (blocked by NAT)
- ✅ Port forwarding: Windows `localhost:8080` → Ubuntu `8080`

### 📱 **Demo Application Status**
**Flutter Web Demo:**
- ✅ **App loads**: Successfully displays in Windows browser
- ✅ **Map functionality**: Tours load and display correctly
- ✅ **UI navigation**: All screens accessible
- ✅ **Service connectivity**: Tours download (7MB+ successful)
- ❌ **File storage**: `path_provider` plugin not web-compatible
- ❌ **Tour playback**: Empty pages due to storage limitation

**Current Demo Limitations:**
- Version/Build/User ID show "Error loading" (expected for web)
- Tours download but can't be saved locally
- Audio playback unavailable in web version
- Voice control not functional in browser

### 🔧 **Demo Setup Commands**
```bash
# Ubuntu Terminal - Start Flutter Web Server
cd /home/Ubuntu/audiotours_local/audio_tour_app/
flutter config --enable-web
flutter clean && flutter pub get
flutter run -d web-server --web-port 8080 --web-hostname 0.0.0.0

# Windows Browser - Access Demo
http://localhost:8080
```

### 🎪 **Demo Presentation Strategy**
**What Works Well:**
1. **Cross-platform capability**: "App runs on mobile, web, and desktop"
2. **Map integration**: "Real-time tour discovery based on location"
3. **Service architecture**: "Tours download from microservices"
4. **UI/UX design**: "Clean, intuitive interface"
5. **Scalability**: "58 tours available in Boston area"

**How to Handle Limitations:**
1. **File storage**: "Web version demonstrates UI - full functionality on mobile"
2. **Audio playback**: "Voice control and audio work on mobile devices"
3. **Version info**: "Device-specific info available on mobile platforms"
4. **Empty tour pages**: "Tours require mobile file system for full experience"

### 🚨 **Known Issues & Workarounds**
**Issue**: Tours download but show empty pages
- **Root Cause**: `MissingPluginException` for `path_provider` in web
- **Demo Response**: "This demonstrates our service connectivity - full tour experience requires mobile platform"
- **Technical Fix**: Mobile App Amazon-Q needs to add web storage support

**Issue**: Ubuntu screen goes dark during demo
- **Quick Fix**: Move mouse, press any key, or Ctrl+Alt+T
- **Recovery**: `sudo service gdm3 restart` if GUI frozen

### 🔄 **Demo Recovery Procedures**
**If Flutter Server Stops:**
```bash
cd /home/Ubuntu/audiotours_local/audio_tour_app/
flutter run -d web-server --web-port 8080 --web-hostname 0.0.0.0
```

**If Ubuntu Becomes Unresponsive:**
1. Move mouse or press keys
2. Ctrl+Alt+F1 then Ctrl+Alt+F7 (switch terminals)
3. `sudo service gdm3 restart`
4. VM restart (last resort)

**If Windows Can't Access Demo:**
1. Verify VirtualBox port forwarding rule exists
2. Check Ubuntu Flutter server is running
3. Try `http://127.0.0.1:8080` instead of localhost
4. Restart VM if networking fails

### 🎯 **Demo Script Outline**
**Opening (30 seconds):**
- "AudioTours mobile app running in Ubuntu, displayed in Windows browser"
- "Demonstrates cross-platform Flutter development"

**Core Features (2 minutes):**
- Map with location-based tour discovery
- Service architecture downloading tours in real-time
- Clean UI design and navigation
- Multiple tour types (walking, museum)

**Technical Highlights (1 minute):**
- Microservices architecture (mention Docker containers)
- Real-time location services
- Scalable tour delivery system
- Cross-platform compatibility

**Closing (30 seconds):**
- "Full audio and voice control experience available on mobile"
- "Web version demonstrates UI and service integration"

### 📊 **Demo Metrics to Highlight**
- **58 tours** available in Boston area
- **7MB+ tour data** successfully downloaded
- **Real-time location** services working
- **Multiple platforms** supported (mobile, web, desktop)
- **Microservices architecture** with Docker containers

### 🛠️ **Technical Architecture for Demo**
**Flutter Web App (Ubuntu)** ↔ **Port Forwarding** ↔ **Windows Browser**
                ↓
**Docker Services (Windows)** → **PostgreSQL Database** → **Tour Data**

**Service Endpoints Demonstrated:**
- `http://192.168.0.217:5005/tours-near/` (tour discovery)
- `http://192.168.0.217:5005/download-tour/` (tour download)
- Real-time location services
- Map tile delivery

### 🔮 **Future Demo Enhancements**
**Short-term (Mobile App Amazon-Q):**
- Add web storage support using `shared_preferences`
- Enable basic tour playback in browser
- Fix version info display for web platform

**Long-term:**
- Voice control simulation in web version
- Progressive Web App (PWA) capabilities
- Offline tour caching for web

### 📝 **Demo Feedback & Improvements**
**Successful Elements:**
- Cross-platform demonstration effective
- Service connectivity impressive
- UI design well-received
- Technical architecture clear

**Areas for Enhancement:**
- Need mobile device for full feature demo
- Audio capabilities require native platform
- File storage limitations need explanation

### 🎪 **Demo Environment Maintenance**
**Regular Checks:**
- VirtualBox VM performance
- Ubuntu system updates
- Flutter SDK updates
- Port forwarding configuration
- Network connectivity between host/guest

**Before Each Demo:**
1. Start Ubuntu VM
2. Verify network connectivity (`ping 10.0.2.2`)
3. Start Flutter web server
4. Test Windows browser access
5. Prepare explanation for limitations

### 📱 **Mobile Demo Alternative**
**If Full Demo Needed:**
- Use actual Android device with installed APK
- Connect to same Windows Docker services
- Demonstrate voice control and audio playback
- Show complete tour experience with file storage

**APK Location**: `c:\Users\micha\eclipse-workspace\AudioTours\development\audioura-dev.apk`

### 🔄 **Context Recovery Instructions**
**When Chat History Compacted:**
1. Read `@remind_ai.md` for project context
2. Read `@remind_demo.md` (this file) for demo status
3. Verify current demo environment status
4. Resume demo guidance and troubleshooting

**Key Recovery Points:**
- Ubuntu VM with Flutter web server
- VirtualBox port forwarding configuration
- Known limitations and workarounds
- Demo presentation strategy
- Technical architecture overview

### 🔧 **CURRENT SESSION STATUS (v1.2.8+103)**
**Latest Developments:**
- ✅ **APK Built**: v1.2.8+103 with Mobile App Amazon-Q web storage fixes
- ✅ **Build Scripts**: `build_flutter_clean.sh` and `start_flutter_web_demo.sh` created
- ❌ **VirtualBox Symlink Issue**: Flutter can't create symlinks in shared folders
- ✅ **Workaround**: Copy to local Ubuntu directory (`~/audiotours_web_demo/`)
- ✅ **Automated Testing**: Selenium test suite created (`test_flutter_web_demo.py`)

**Current Challenge:**
- **Symlink Error**: `PathAccessException: Cannot create link` in VirtualBox shared folder
- **Root Cause**: v1.2.8+103 has more plugins requiring symlinks than previous versions
- **Solution**: Use `start_flutter_web_demo.sh` script that copies to local Ubuntu storage

**Working Scripts:**
1. **`build_flutter_clean.sh`**: Builds APK from shared folder (works)
2. **`start_flutter_web_demo.sh`**: Copies files locally and starts web server (fixes symlink issue)
3. **`test_flutter_web_demo.py`**: Selenium automation for testing web demo

**Demo Workflow:**
```bash
# 1. Build APK (from ~)
bash build_flutter_clean.sh

# 2. Start web demo (from ~)
bash start_flutter_web_demo.sh

# 3. Access in Windows: http://localhost:8080
# 4. Run automated tests: python test_flutter_web_demo.py
```

**Key Files Created:**
- `/development/start_flutter_web_demo.sh` - Web demo launcher with cleanup
- `/development/test_flutter_web_demo.py` - Selenium test automation
- `/development/build_flutter_local.sh` - Local build script (deprecated)

**Assets Issue Fixed:**
- Script now copies `assets/` and `.env` files
- Creates empty directories if missing
- Handles compilation errors gracefully

**Test Automation Ready:**
- 7 comprehensive tests covering app load, map, tours, navigation, responsive design, web storage, error handling
- Pass rate scoring: 80%+ = Demo Ready, 60%+ = Functional, <60% = Needs Work
- Automated validation of demo functionality

---
**Last Updated**: 2025-01-15 (Session Update)
**Demo Environment**: Ubuntu 25.04 + VirtualBox + Flutter Web
**Status**: v1.2.8+103 ready with workaround scripts
**Current Version**: v1.2.8+103 with web storage support
**Next Steps**: Test web storage functionality and run Selenium automation