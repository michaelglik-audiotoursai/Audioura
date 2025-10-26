# Flutter Mobile App Subsystem

## Location
- **Primary**: `c:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app\`
- **Package**: `com.audiotours.dev`

## Version Management
Update version in THREE places:
1. `pubspec.yaml` - Main version file
2. `pubspec_android_simple.yaml` - Android build config
3. `Dockerfile` - Container build version

## Common Issues & Solutions

### ClassNotFoundException (v167 Fix)
**Symptoms**: App crashes immediately with "keeps stopping"
**Root Cause**: Package name mismatch
- AndroidManifest.xml expects: `com.audiotours.dev.MainActivity`
- MainActivity.kt was in wrong package: `com.example.audio_tour_app`

**Fix Process**:
1. Update MainActivity.kt package to `com.audiotours.dev`
2. Move file to correct directory: `com/audiotours/dev/`
3. Remove old directory structure
4. Increment version in pubspec.yaml

### Build Process
- **Local Windows builds**: Often fail due to dependency conflicts
- **Recommended**: Use GitHub Actions for reliable Linux builds
- **Testing**: Install APK with `flutter install --use-application-binary="path/to/apk"`
- **Debug crashes**: `adb logcat -d *:E` from platform-tools directory

## GitHub Actions Integration
- Auto-builds trigger on version increments in `pubspec.yaml`
- Requires git push to master branch
- APK appears in GitHub releases after successful build
- Build logs available in GitHub Actions tab

## Key Files
- `lib/main.dart` - App entry point
- `android/app/src/main/AndroidManifest.xml` - Android configuration
- `android/app/build.gradle.kts` - Build configuration
- `pubspec.yaml` - Dependencies and version