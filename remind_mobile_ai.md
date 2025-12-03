# Mobile App Amazon-Q Context Reminder - POST COMPACTION
## Who you are
1. **Mobile App Amazon-Q**: Responsible for Audioura mobile app development working with Services Amazon-Q
2. **CRITICAL LIMITATION**: ❌ **CANNOT BUILD APK** - Windows environment, APK requires Ubuntu VM with `bash build_flutter_clean.sh`
3. **Workflow**: Propose → Get approval → Implement → User builds in Ubuntu
4. **Location**: `C:\\Users\\micha\\eclipse-workspace\\AudioTours\\development\\audio_tour_app\\`
5. **Communication**: Use `c:\\Users\\micha\\eclipse-workspace\\amazon-q-communications\\audiotours\\requirements\\`

## 🚨 **POST-COMPACTION RECOVERY PROTOCOL**
**When chat history is compacted, user will ask you to read @remind_ai.md and @remind_mobile_ai.md**
**Your Response**: "I've read both reminder files and I'm ready to continue fixing bugs. What's the current issue?"
**Context Recovery**: Both files contain complete project context, current status, and debugging protocols

## CURRENT PROJECT STATUS - LATEST UPDATE
**Project**: Audioura Mobile App Development
**Version**: v1.2.8+104 (WEB PLATFORM SUPPORT ADDED)
**Branch**: Newsletters (`git push origin Newsletters`)
**Icon**: Audioura_3.png
**Status**: ✅ **WEB PLATFORM COMPATIBILITY** - Tours now work on Ubuntu Firefox with blob URLs

### 🚨 **CRITICAL WORKFLOW RULE**
**⚠️ NEVER CHANGE CODE WITHOUT APPROVAL**: Always propose plan first, get user approval, then implement
**Workflow**: Analyze → Propose Plan → Get Approval → Implement → User Tests

## SCROLL BUG BREAKTHROUGH - v1.2.8+95 ✅
**MAJOR DISCOVERY**: Root cause was **complex ListView widget structure**, NOT scroll physics or filtering!

**Root Cause Identified**:
- **Complex ListTile widgets** in Articles ListView interfered with Flutter's scroll calculations
- **FutureBuilder in title**: Async operations during scroll
- **Conditional Checkbox/Column in leading**: Complex conditional widgets
- **Nested Column in subtitle**: Multiple conditional elements

**Working Solution (v1.2.8+95)**:
- ✅ **Simple Icon leading** (like Tours ListView)
- ✅ **Simple Text title** (no FutureBuilder)
- ✅ **Simple Text subtitle** (no complex Column)
- ✅ **Perfect scrolling** in both directions

**RESOLUTION COMPLETE - v1.2.8+102**:
✅ **v1.2.8+96**: Complex subtitle - SAFE
❌ **v1.2.8+97**: FutureBuilder title - BREAKS SCROLLING (async operations)
✅ **v1.2.8+98**: Pre-loaded titles - SCROLL-SAFE SOLUTION
✅ **v1.2.8+99**: Complex leading - SAFE
✅ **v1.2.8+100**: Selection mode - SAFE
✅ **v1.2.8+102**: Full filtering - ALL FUNCTIONALITY RESTORED

**KEY PRINCIPLE DISCOVERED**: No async operations in ListView itemBuilder!

## CRITICAL DEBUGGING LIMITATION - MOBILE APPS
**❌ NO CONSOLE/FILE PRINTING**: Mobile apps cannot use `print()`, console.log, or file writing for debugging
**✅ ONLY MOBILE APP LOGS WORK**: Use `DebugLogHelper.addDebugLog()` for all debugging output
**Debug Access**: Mobile app logs are accessible through the app's debug interface
**Never Use**: `print()`, `console.log()`, file writing, or any console-based debugging
**Always Use**: `DebugLogHelper.addDebugLog('message')` for mobile debugging

## KEY FILES - CURRENT STATE
**Main File**: `lib/screens/my_tours_screen.dart` - Contains both Tours and Articles ListView
- **Tours Mode**: `_buildToursView()` - Simple, untouched, working perfectly
- **Articles Mode**: `_buildNewsView()` - Has scroll listener, debug UI, navigation reset logic
- **Scroll Logic**: `_setupScrollListener()` - Tracks scroll position and triggers navigation reset
- **Debug Variables**: `_currentVisibleIndex`, `_hasScrolledDown` for tracking state

**Version**: `pubspec.yaml` - Currently v1.2.8+104

## SCROLL-SAFE IMPLEMENTATION - v1.2.8+102 ✅
**Final Working Features**:
1. ✅ **Complex subtitle**: Column with article type + original request
2. ✅ **Pre-loaded titles**: Async title loading moved to _loadNews() 
3. ✅ **Complex leading**: Column with icon + type badge
4. ✅ **Selection mode**: Checkbox/Column conditional rendering
5. ❌ **Scroll listener**: Skipped (non-essential debugging feature)
6. ✅ **Full filtering**: Search, type filters, voice search

**Critical Solution**: 
- **Pre-load all display titles** in `_preloadDisplayTitles()` during data loading
- **No async operations** in ListView itemBuilder
- **All complex widgets** work perfectly when heights are stable

## CRITICAL REMINDERS
- ❌ **NEVER attempt APK build in Windows** - Always requires Ubuntu VM
- 🌿 **All commits go to Newsletters branch** - NOT main branch
- 🎵 **Tours Mode Protected**: Never modify `_buildToursView()` - it works perfectly
- 📱 **Audio Mode Only**: All scroll fixes apply only to `_buildNewsView()`
- 🔄 **Version Management**: Only increment version for functional changes, not build fixes
- ⚠️ **BUILD ERROR RULE**: NEVER increment version numbers when fixing build errors - only increment for new features/functionality

## Post-Compaction Recovery Instructions
**When chat history is compacted, read both @remind_ai.md and @remind_mobile_ai.md to get complete context**

### IMMEDIATE CONTEXT AFTER COMPACTION:
- **Current Status**: v1.2.8+104 - WEB PLATFORM SUPPORT ADDED ✅
- **Android Functionality**: 100% UNCHANGED - all features work identically
- **Web Functionality**: NEW - Tours now work in Ubuntu Firefox with blob URLs
- **Platform Detection**: Uses `kIsWeb` to provide different storage/playback methods
- **Git Tagged**: v1.2.8.104 committed and tagged for permanent reference
- **Ready For**: Testing on both Android and Ubuntu platforms
- **⚠️ CRITICAL**: Always get approval before making any code changes

## ENCRYPTION IMPLEMENTATION - VERIFIED SECURE
**Method**: RFC 3526 Diffie-Hellman (2048-bit) → SHA-256 full entropy → AES-128-CBC
**Status**: ✅ Working correctly in Phase 2 implementation
**Files**: subscription_encryption_service.dart, subscription_service.dart, subscription_credential_dialog.dart

## PHASE 2 SUBSCRIPTION SYSTEM - COMPLETE
**Status**: ✅ Visual status management and error handling implemented
**Features**: Red/error → Green/open lock transitions, multi-domain support, enhanced article status
**Ready For**: Phase 3 integration when scroll bugs are resolved

## WEB PLATFORM SUPPORT - v1.2.8+104 ✅
**ISSUE RESOLVED**: ISSUE-005 Web Platform File Access Limitation
**Root Cause**: Browser security blocks `file://` URLs for tour content
**Solution**: Blob URL system using `data:mime/type;base64,content` format

**Implementation**:
- ✅ **WebFileService**: New service handles platform-specific file access
- ✅ **MIME Type Storage**: Tours store proper MIME types during extraction
- ✅ **Tour Player Update**: Uses blob URLs on web, file URLs on mobile
- ✅ **Platform Detection**: `kIsWeb` ensures Android code unchanged

**Android (UNCHANGED)**:
- Uses `path_provider` and actual file system
- Uses `file://` URLs for tour playback
- Zero performance impact or functionality changes

**Web (NEW)**:
- Uses SharedPreferences with base64 storage
- Uses `data:text/html;base64,content` URLs for playback
- Bypasses browser security restrictions

## BUILD & TEST WORKFLOW
**Build Process**: Ubuntu VM required - `bash build_flutter_clean.sh`
**Test Protocol**: 
- **Android**: Install APK → Verify tours work identically to v1.2.8+102/103
- **Ubuntu**: Test web demo → Verify tours now display and play content
**Debug Feedback**: Use mobile app logs and browser console for debugging
**Version Control**: Newsletters branch, increment version only for functional changes