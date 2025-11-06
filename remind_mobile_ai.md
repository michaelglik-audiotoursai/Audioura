# Mobile App Amazon-Q Context Reminder
## Who you are
1. **Mobile App Amazon-Q**: Responsible for Audioura mobile app development working with Services Amazon-Q
2. **CRITICAL LIMITATION**: ❌ **CANNOT BUILD APK** - Windows environment, APK requires Ubuntu VM with `bash build_flutter_clean.sh`
3. **Workflow**: Propose → Get approval → Implement → User builds in Ubuntu
4. **Location**: `C:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app\`
5. **Build Script**: `build_flutter_clean.sh` (must be copied to Ubuntu VM)
6. **Maintenance**: Update this file after significant changes and commit to GitHub
7. **Communication**: Use `c:\Users\micha\eclipse-workspace\amazon-q-communications\audiotours\requirements\`

## Current Project Status
**Project**: Audioura Mobile App Development
**Version**: v1.2.7+8 (Voice Navigation Commands)
**Branch**: Newsletters (`git push origin Newsletters`)
**Icon**: Audioura_3.png
**Build Status**: ❌ **CANNOT BUILD IN WINDOWS** - Requires Ubuntu VM

## Current Work: Voice Navigation Commands (v1.2.7+8)

### ✅ IMPLEMENTED - Ready for Testing
**Feature**: 5 voice commands to navigate from article view back to Listen Page:
- "Go to Listen Page" / "Listen Page"
- "Back to Listen Page" / "Return to Listen" / "Return to Listen Page" 
- "Back to article list" / "Article list"
- "Show all articles" / "All articles"

**Files Modified** (awaiting commit after testing):
- `lib/services/voice_control_service_news.dart` - Command detection
- `lib/screens/news_player_screen.dart` - Navigation handler
- `pubspec.yaml` - Version 1.2.7+8

### Recent Fixes
- ✅ Newsletter ID Bug (v1.2.7+7): Fixed `newsletter['id']` → `newsletter['newsletter_id']`
- 🔍 Newsletter Endpoint 404: ISSUE-055 pending Services Amazon-Q response

## Next Steps
1. **User builds APK** in Ubuntu VM: `bash build_flutter_clean.sh` (v1.2.7+8)
2. **Test voice navigation**: Article view → "Go to Listen Page" → Listen Page
3. **If successful**: Commit changes to Newsletters branch
4. **If issues**: Amazon-Q fixes without version increment

## Key Reminders
- ❌ **NEVER attempt APK build in Windows** - Always requires Ubuntu VM
- 🌿 **All commits go to Newsletters branch** - NOT main branch
- 📝 **Update this file** after significant changes
- 🔧 **No version increment** for build error fixes (same build not tested yet)
- 📋 **Communication layer** for Services Amazon-Q coordination