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
**Version**: v1.2.8+96 (Systematic Feature Restoration - Complex Subtitle Test)
**Branch**: Newsletters (`git push origin Newsletters`)
**Icon**: Audioura_3.png
**Status**: ✅ **SCROLL BUG SOLVED** - Root cause identified, systematic restoration in progress

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

**Current Phase - Systematic Restoration**:
**v1.2.8+96**: Testing complex subtitle restoration
**Next Steps**: Restore features one by one to identify exact breaking point
1. Complex subtitle → FutureBuilder title → Complex leading → Selection mode → Scroll listener → Filtering

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

**Version**: `pubspec.yaml` - Currently v1.2.8+96

## SYSTEMATIC RESTORATION PROTOCOL
**Feature Restoration Order**:
1. **v1.2.8+96**: Complex subtitle (Column with article type + original request)
2. **v1.2.8+97**: FutureBuilder title (async title loading)
3. **v1.2.8+98**: Complex leading (Column with icon + type badge)
4. **v1.2.8+99**: Selection mode (Checkbox leading)
5. **v1.2.8+100**: Scroll listener + yellow highlight
6. **v1.2.8+101**: Filtering logic

**Testing Protocol**:
- Test each version individually
- If scrolling breaks, that feature is the culprit
- Implement scroll-safe version of breaking feature
- Continue restoration until all features work with perfect scrolling

## CRITICAL REMINDERS
- ❌ **NEVER attempt APK build in Windows** - Always requires Ubuntu VM
- 🌿 **All commits go to Newsletters branch** - NOT main branch
- 🎵 **Tours Mode Protected**: Never modify `_buildToursView()` - it works perfectly
- 📱 **Audio Mode Only**: All scroll fixes apply only to `_buildNewsView()`
- 🔄 **Version Management**: Only increment version for functional changes, not build fixes

## Post-Compaction Recovery Instructions
**When chat history is compacted, read both @remind_ai.md and @remind_mobile_ai.md to get complete context**

### IMMEDIATE CONTEXT AFTER COMPACTION:
- **Current Status**: v1.2.8+96 systematic feature restoration in progress
- **Breakthrough**: Complex ListView widgets were the root cause, not scroll physics
- **Working Base**: v1.2.8+95 with simplified ListView structure scrolls perfectly
- **Current Test**: v1.2.8+96 testing complex subtitle restoration
- **Restoration Plan**: Add features incrementally to identify exact breaking point
- **Next Phase**: Complete feature restoration with scroll-safe implementations
- **⚠️ CRITICAL**: Always get approval before making any code changes

## ENCRYPTION IMPLEMENTATION - VERIFIED SECURE
**Method**: RFC 3526 Diffie-Hellman (2048-bit) → SHA-256 full entropy → AES-128-CBC
**Status**: ✅ Working correctly in Phase 2 implementation
**Files**: subscription_encryption_service.dart, subscription_service.dart, subscription_credential_dialog.dart

## PHASE 2 SUBSCRIPTION SYSTEM - COMPLETE
**Status**: ✅ Visual status management and error handling implemented
**Features**: Red/error → Green/open lock transitions, multi-domain support, enhanced article status
**Ready For**: Phase 3 integration when scroll bugs are resolved

## BUILD & TEST WORKFLOW
**Build Process**: Ubuntu VM required - `bash build_flutter_clean.sh`
**Test Protocol**: Install APK → Test scroll behavior → Report results with debug info
**Debug Feedback**: Use yellow highlight and manual refresh to describe exact behavior
**Version Control**: Newsletters branch, increment version only for functional changes