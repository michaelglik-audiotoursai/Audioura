# AudioTours AI Context Reminder
## System Overview - Quick Recovery Guide

### 🏗️ **Project Structure**
```
c:\Users\micha\eclipse-workspace\AudioTours\development\
├── audio_tour_app/                    # Flutter Mobile App
│   ├── lib/screens/                   # UI Screens
│   ├── lib/services/                  # Mobile Services
│   └── pubspec.yaml                   # Version: 1.2.5+214
├── Docker Services (Microservices)
├── Database: PostgreSQL (development-postgres-2-1)
└── GitHub Repo: Audio-Tours (Tag: v1.2.2.104)
```

### 🐳 **Docker Services Architecture**
```bash
# Core Services
development-tour-processor-1:5001      # Tour generation & MP3 creation
development-tour-orchestrator-1:5002   # Tour workflow coordination
development-postgres-2-1:5432          # PostgreSQL database
development-map-delivery-1:5005        # Map & tour delivery
development-coordinates-1:5006          # Location services
development-treats-1:5007               # Local treats/POIs

# News/Newsletter Services  
news-orchestrator-1:5012               # News workflow coordination
news-generator-1:5010                  # News content processing
news-processor-1:5011                  # News audio generation
newsletter-processor-1:5017            # Newsletter crawling & processing
polly-tts-1:5018                      # Amazon Polly TTS (replaces gTTS)
```

### 📱 **Mobile App (Flutter)**
- **Location**: `c:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app\`
- **Current Version**: 1.2.5+214
- **Modes**: Tours (default) / Audio (news/newsletters)
- **Key Features**: Voice control, auto-download, error handling
- **CRITICAL BUILD LIMITATION**: ❌ **Cannot build mobile app in Windows**
- **Build Process**: Must use Ubuntu client in Oracle Virtual Box
- **Build Command**: `bash build_flutter_clean.sh`
- **APK Output**: `app-release-dev.apk` in development directory

### 🗄️ **Database Schema (PostgreSQL)**
```sql
-- Core Tables
tour_requests(id, tour_id, request_string, status, finished_at, coordinates)
audio_tours(id, tour_name, tour_data, coordinates)
treats(id, name, description, lat, lng, image_base64)

-- News Tables  
article_requests(article_id, article_text, request_string, status, major_points)
news_audios(article_id, article_name, news_article)
newsletters(id, url, name, created_at)
newsletters_article_link(newsletter_id, article_requests_id)
```

### 🔧 **Recent Major Changes (v1.2.5+214 - REQ-016)**
1. **Complete Tour Editing**: Add/delete/reorder stops with bulk save operations
2. **Clean State Logic**: Handles add+modify, modify+delete, add+delete scenarios
3. **"Moved" UI Indicators**: Purple indicators with swap icons for reordered stops
4. **UUID Tour Support**: Fixed critical issue where new tours couldn't be edited
5. **Automatic Tour Refresh**: Downloads updated tours after editing using version API
6. **Voice Control Compatibility**: Sequential audio file naming (audio_1.mp3, audio_2.mp3)

### 🎯 **Current Issues & Solutions**
- **REQ-016 Tour Editing**: ✅ Complete implementation with clean state logic
- **ISSUE-009 FIXED**: ✅ Voice control fix deployed by Services Amazon-Q
  - Root Cause: Missing id="audio1" attributes in REQ-016 HTML
  - Fix Applied: Added sequential IDs (audio1, audio2, audio3) to audio elements
  - Status: Ready for testing on newly generated tours
- **UUID Tour Support**: ✅ Fixed - new tours now fully editable
- **Voice Recognition**: ✅ Works correctly, ready for validation

### 🚀 **Development Workflow**
1. **Modify files locally** in development directory
2. **Copy to containers**: `docker cp local_file container:/app/file`
3. **Restart containers**: `docker restart container_name`
4. **Update version numbers** in pubspec.yaml
5. **CRITICAL: ALWAYS COMMIT TO GIT** after each working change
6. **Commit & tag**: `git tag v1.2.6.XXX`

### 📱 **Mobile App Build & Test Workflow**
**IMPORTANT**: Amazon-Q cannot build mobile apps in Windows environment

#### Build Process:
1. **Update version** in `pubspec.yaml`: `version: 1.2.5+XXX`
2. **Switch to Ubuntu VM** (Oracle Virtual Box)
3. **Run build script**: `bash build_flutter_clean.sh`
4. **APK location**: `app-release-dev.apk` in development directory

#### Testing Process:
1. **Install APK** on Android device
2. **Test specific feature** (e.g., tour editing)
3. **Check debug logs** for error messages
4. **Verify fix works** as expected
5. **Report results** back to Amazon-Q

#### For REQ-016 Tour Editing (v1.2.5+214):
1. **Test tour**: Framingham Public Library tour (or newly generated)
2. **Expected result**: Complete editing functionality (add/delete/reorder)
3. **Verify**: "Moved" indicators appear for reordered stops
4. **CRITICAL**: Voice control should now work (ISSUE-009 FIXED)
5. **Check**: Audio elements have proper id="audio1" attributes

### 🔥 **MANDATORY GIT WORKFLOW - NEVER SKIP THIS**
**ALWAYS commit changes to Git after each successful modification. This prevents losing functionality if files get corrupted.**

**Standard commit sequence:**
```bash
git add audio_tour_app/lib/screens/home_screen.dart
git add audio_tour_app/pubspec.yaml  
git add audio_tour_app/lib/main.dart
git add *.py  # Add any modified services
git commit -m "v1.2.2+XXX - [Description of changes]"
```

**Use safe_commit.bat to avoid long filename issues:**
```bash
call safe_commit.bat
```

**Why this is critical:**
- Files can get corrupted during complex edits
- Git allows instant recovery to working state
- Version history prevents losing functionality
- Multiple commits create restore points

**NEVER make multiple changes without committing working states!**

### 📋 **Common Commands**
```bash
# Container Management
docker ps                                    # List running containers
docker logs container_name --tail 20        # Check logs
docker restart container_name               # Restart service
docker cp file.py container:/app/file.py    # Deploy changes

# Database Access
docker exec development-postgres-2-1 psql -U admin -d audiotours -c "SELECT * FROM table;"

# Mobile App
cd audio_tour_app && flutter build apk --release
```

### 🔑 **Key Service Endpoints**
- **Tour Generation**: POST localhost:5002/generate-complete-tour
- **Newsletter Processing**: POST localhost:5017/process_newsletter  
- **Polly TTS**: POST localhost:5018/synthesize
- **Map Delivery**: GET localhost:5005/tours-near/{lat}/{lng}
- **Treats**: GET localhost:5007/treats-near/{lat}/{lng}

### 🎵 **Voice Control System**
- **Trigger**: Triple volume button press or mic button
- **Commands**: "Next Tour", "Previous Tour", "Play", "Pause", "Next Stop"
- **Implementation**: `voice_control_service.dart` + `voice_methods.dart`
- **Navigation**: Uses `available_tours` list in SharedPreferences

### 📊 **Version Management**
- **Mobile App**: pubspec.yaml version field (1.2.2+105)
- **Services**: SERVICE_VERSION constants in Python files
- **GitHub**: Tags for major releases (v1.2.2.104)
- **Sync Rule**: All versions must match for reproducibility

### 🔄 **Recovery Steps**
1. **Check Git status first**: `git status` and `git log --oneline -10`
2. **If files corrupted**: `git checkout HEAD -- filename` to restore
3. **If major corruption**: `git reset --hard HEAD` (loses uncommitted changes)
4. Verify Docker containers are running: `docker ps`
5. Test mobile app connection to services
6. Check database connectivity
7. Review recent commits for context
8. Test voice commands and error handling

### ⚠️ **Critical Reminders**
- **NEVER attempt Flutter builds in Windows** - Always use Ubuntu VM
- **Always increment version** before requesting builds
- **Test thoroughly** before committing version tags
- **Report build results** back to Amazon-Q for confirmation

### 🛡️ **File Corruption Prevention**
- **Long filename issues**: Use `.gitignore` and `cleanup_long_paths.bat`
- **Syntax errors**: Always test build after changes
- **Lost functionality**: Commit working states before major changes
- **Service sync**: Copy to containers AND commit to Git
- **Version tracking**: Update version numbers with each commit

### 🎯 **Next Priorities**
- **CRITICAL**: Test ISSUE-009 voice control fix on newly generated tours
- Verify "Next Step", "Play", "Pause" commands work in modified tours
- Confirm HTML audio elements have proper id attributes
- Complete REQ-016 validation with working voice commands
- Mobile app UI/UX refinements for tour editing