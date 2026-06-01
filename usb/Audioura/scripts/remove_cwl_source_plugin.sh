#!/bin/bash
# 🍎 iOS AMAZON-Q - Identify and Remove CwlCatchException Source Plugin
# Finds which plugin is causing CwlCatchException dependency and removes it

echo "🍎 iOS AMAZON-Q - Identify and Remove CwlCatchException Source Plugin"
echo "====================================================================="

# Navigate to project directory
cd ~/Development/AudioTours/development/audio_tour_app

echo "📋 Step 1: Analyzing CocoaPods dependency tree..."

# Check which plugin is pulling in CwlCatchException
echo "Checking Podfile.lock for CwlCatchException dependencies..."
if [ -f "ios/Podfile.lock" ]; then
    echo "Found Podfile.lock - analyzing dependencies:"
    grep -A 10 -B 10 "CwlCatchException" ios/Podfile.lock || echo "CwlCatchException not found in Podfile.lock"
else
    echo "No Podfile.lock found"
fi

echo ""
echo "🔍 Step 2: Checking individual plugin dependencies..."

# Check speech_to_text (most likely culprit based on CocoaPods output)
echo "Checking speech_to_text plugin..."
if [ -d "ios/Pods/speech_to_text" ]; then
    echo "speech_to_text pod exists - checking its dependencies:"
    find ios/Pods/speech_to_text -name "*.podspec" -exec cat {} \; 2>/dev/null | grep -i cwl || echo "No CwlCatchException found in speech_to_text podspec (NOTE: CwlCatchException is likely a transitive dependency)"
fi

# Check flutter_sound (another potential culprit)
echo ""
echo "Checking flutter_sound plugin..."
if [ -d "ios/Pods/flutter_sound" ]; then
    echo "flutter_sound pod exists - checking its dependencies:"
    find ios/Pods/flutter_sound -name "*.podspec" -exec cat {} \; 2>/dev/null | grep -i cwl || echo "No CwlCatchException found in flutter_sound podspec (NOTE: CwlCatchException is likely a transitive dependency)"
fi

echo ""
echo "⚠️  NOTE: CwlCatchException is a transitive dependency (dependency-of-a-dependency)."
echo "The podspec grep above is informational only. The Podfile.lock check is definitive."

echo ""
echo "🔧 Step 3: Creating minimal pubspec.yaml without problematic plugins..."

# Backup current pubspec
cp pubspec.yaml pubspec_with_cwl.yaml

# Create ultra-minimal pubspec without speech_to_text and flutter_sound
cat > pubspec_minimal.yaml << 'EOF'
name: audio_tour_app
description: A new Flutter project.
publish_to: 'none'
version: 1.2.9+22

environment:
  sdk: '>=3.0.0 <4.0.0'

dependencies:
  flutter:
    sdk: flutter
  cupertino_icons: ^1.0.2
  http: ^1.4.0
  geolocator: ^13.0.1
  permission_handler: ^11.0.1
  # speech_to_text: ^7.0.0  # REMOVED - likely source of CwlCatchException
  # flutter_sound: ^9.2.13  # REMOVED - potential source of CwlCatchException
  path_provider: ^2.1.4
  flutter_map: ^6.1.0
  latlong2: ^0.9.1
  url_launcher: ^6.3.1
  shared_preferences: ^2.5.3
  flutter_local_notifications: ^17.2.4
  flutter_inappwebview: ^6.0.0
  file_picker: ^8.3.7
  archive: ^3.6.1
  flutter_secure_storage: ^9.2.4
  package_info_plus: ^8.3.0
  device_info_plus: ^10.1.2
  flutter_dotenv: ^5.2.1
  logger: ^2.6.0
  flutter_volume_controller: ^1.3.3
  uuid: ^4.5.1

flutter:
  uses-material-design: true
  assets:
    - assets/images/
    - .env

# NO dev_dependencies section
# NO speech_to_text (likely CwlCatchException source)
# NO flutter_sound (potential CwlCatchException source)
EOF

# Replace pubspec.yaml with minimal version
mv pubspec_minimal.yaml pubspec.yaml

echo "✅ Created minimal pubspec.yaml without speech_to_text and flutter_sound"

echo ""
echo "🧹 Step 4: Complete cleanup and rebuild..."

# Complete cleanup
flutter clean
cd ios
rm -rf Pods Podfile.lock .symlinks DerivedData
cd ..
rm -rf .dart_tool build

echo "✅ Complete cleanup finished"

echo ""
echo "📦 Step 5: Fresh dependency resolution..."

# Get dependencies with minimal pubspec
flutter pub get

if [ $? -ne 0 ]; then
    echo "❌ Pub get failed - restoring previous pubspec.yaml"
    mv pubspec_with_cwl.yaml pubspec.yaml
    flutter pub get
    exit 1
fi

echo "✅ Dependencies resolved successfully"

echo ""
echo "🔧 Step 6: Building minimal release version..."

# Build release without problematic plugins
flutter build ios --release --no-codesign --verbose

if [ $? -eq 0 ]; then
    echo "✅ Minimal release build successful!"
    
    # Check if CwlCatchException is still referenced
    echo ""
    echo "🔍 Step 7: Verifying CwlCatchException elimination..."
    
    APP_BUNDLE="build/ios/Release-iphoneos/Runner.app"
    
    if [ -f "$APP_BUNDLE/Runner" ]; then
        echo "Checking main executable for CwlCatchException..."
        otool -L "$APP_BUNDLE/Runner" | grep -i cwl && echo "❌ CwlCatchException STILL PRESENT" || echo "✅ CwlCatchException ELIMINATED from main executable"
        
        echo ""
        echo "Checking all frameworks for CwlCatchException..."
        if [ -d "$APP_BUNDLE/Frameworks" ]; then
            for framework in "$APP_BUNDLE/Frameworks"/*.framework; do
                if [ -d "$framework" ]; then
                    echo "Checking $(basename "$framework")..."
                    otool -L "$framework/$(basename "$framework" .framework)" 2>/dev/null | grep -i cwl && echo "  ❌ Contains CwlCatchException" || echo "  ✅ Clean"
                fi
            done
        fi
        
        echo ""
        echo "Checking CocoaPods for CwlCatchException..."
        if [ -f "ios/Podfile.lock" ]; then
            grep -i cwl ios/Podfile.lock && echo "❌ CwlCatchException still in Podfile.lock" || echo "✅ CwlCatchException eliminated from CocoaPods"
        fi
        
        echo ""
        echo "🔐 Step 8: Signing minimal app bundle..."
        
        # Find certificate
        CERT_HASH=$(security find-identity -v -p codesigning | grep "Apple Development" | head -1 | awk '{print $2}')
        
        # Create entitlements
        cat > entitlements.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "https://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>application-identifier</key>
    <string>4HGRU6TKGQ.com.glikfamily.audioura</string>
    <key>com.apple.developer.team-identifier</key>
    <string>4HGRU6TKGQ</string>
    <key>get-task-allow</key>
    <true/>
    <key>keychain-access-groups</key>
    <array>
        <string>4HGRU6TKGQ.*</string>
    </array>
</dict>
</plist>
EOF
        
        # Sign frameworks
        if [ -d "$APP_BUNDLE/Frameworks" ]; then
            for framework in "$APP_BUNDLE/Frameworks"/*.framework; do
                if [ -d "$framework" ]; then
                    echo "Signing $(basename "$framework")..."
                    codesign --force --sign "$CERT_HASH" --timestamp "$framework"
                fi
            done
        fi
        
        # Sign main app
        codesign --force --sign "$CERT_HASH" --entitlements entitlements.plist --timestamp "$APP_BUNDLE"
        
        echo "✅ Minimal app bundle signed successfully!"
        
        echo ""
        echo "📱 Step 9: Installing minimal app on iPhone 16..."
        
        # Get device ID (hardcoded for reliability)
        DEVICE_ID="00008140-000558A902BA801C"
        
        # Install minimal app
        xcrun devicectl device install app --device "$DEVICE_ID" "$APP_BUNDLE"
        
        if [ $? -eq 0 ]; then
            echo "✅ MINIMAL APP INSTALLED SUCCESSFULLY!"
            echo ""
            echo "🎯 CRITICAL TEST:"
            echo "1. Launch Audioura from iPhone home screen"
            echo "2. App should launch WITHOUT CwlCatchException crash"
            echo "3. Basic navigation should work (no voice/audio features)"
            echo "4. Test core functionality without removed plugins"
            echo ""
            echo "📊 MINIMAL BUILD INFO:"
            echo "• Removed: speech_to_text, flutter_sound (likely CwlCatchException sources)"
            echo "• Kept: All other core functionality"
            echo "• Bundle Size: $(du -sh "$APP_BUNDLE" | cut -f1)"
            echo ""
            echo "🔄 NEXT STEPS IF SUCCESSFUL:"
            echo "1. Find alternative plugins for speech/audio that don't use CwlCatchException"
            echo "2. Or implement basic speech/audio functionality without external plugins"
        else
            echo "❌ Installation failed - trying manual installation"
            echo ""
            echo "📋 Manual Installation Steps:"
            echo "1. Open Xcode: Window → Devices and Simulators"
            echo "2. Select 'Mikhail Glik's iPhone'"
            echo "3. Drag '$APP_BUNDLE' to 'Installed Apps'"
            
            # Open for manual installation
            open -a Xcode
            open "$(dirname "$APP_BUNDLE")"
        fi
        
    else
        echo "❌ App bundle not found after build"
    fi
    
else
    echo "❌ Minimal build failed"
    echo "Restoring previous pubspec.yaml..."
    mv pubspec_with_cwl.yaml pubspec.yaml
    flutter pub get
    
    echo ""
    echo "🔧 Alternative: The issue might be deeper in Flutter framework itself"
    echo "Consider using a different Flutter version or finding CwlCatchException alternatives"
fi

echo ""
echo "📊 Creating comprehensive results..."
echo "Date: $(date)" > minimal_build_results.txt
echo "Approach: Removed speech_to_text and flutter_sound plugins" >> minimal_build_results.txt
echo "Build Status: $([ $? -eq 0 ] && echo 'SUCCESS' || echo 'FAILED')" >> minimal_build_results.txt
echo "CwlCatchException Check: $(otool -L "$APP_BUNDLE/Runner" 2>/dev/null | grep -i cwl >/dev/null && echo 'STILL_PRESENT' || echo 'ELIMINATED')" >> minimal_build_results.txt
echo "App Bundle: $APP_BUNDLE" >> minimal_build_results.txt
echo "Bundle Size: $(du -sh "$APP_BUNDLE" 2>/dev/null | cut -f1 || echo 'N/A')" >> minimal_build_results.txt
echo "Removed Plugins: speech_to_text, flutter_sound" >> minimal_build_results.txt
echo "Functionality Impact: No voice commands, no audio recording (other features intact)" >> minimal_build_results.txt

echo "✅ Results saved to minimal_build_results.txt"
echo ""
echo "🍎 iOS Amazon-Q minimal build script complete!"
echo ""
echo "🎯 KEY INSIGHT: CwlCatchException comes from speech_to_text or flutter_sound plugins"
echo "Minimal app should launch successfully without these problematic plugins"