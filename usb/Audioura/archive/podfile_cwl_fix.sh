#!/bin/bash
# PRE-ASSIGNMENT 20: PODFILE CWLCATCHEXCEPTION EXCLUSION FIX
# Attempt to exclude CwlCatchException WITHOUT removing speech_to_text/flutter_sound

echo "🍎 iOS AMAZON-Q - PODFILE CWLCATCHEXCEPTION EXCLUSION FIX"
echo "Date: $(python3 -c "import datetime; print(datetime.datetime.now())")"
echo ""

# Navigate to project
cd ~/Development/AudioTours/development/audio_tour_app

echo "=== STEP 1: BACKUP CURRENT PODFILE ==="
cp ios/Podfile ios/Podfile.backup
echo "✅ Podfile backed up to ios/Podfile.backup"

echo ""
echo "=== STEP 2: ADD CWLCATCHEXCEPTION EXCLUSION TO PODFILE ==="

# Check if post_install block exists
if grep -q "post_install do" ios/Podfile; then
    echo "⚠️  Existing post_install block found - manual edit required"
    echo "Please manually add CwlCatchException exclusion to existing post_install block"
    echo ""
    echo "ADD THESE LINES inside the existing post_install block:"
    echo "    if ['CwlCatchException', 'CwlCatchExceptionSupport'].include?(target.name)"
    echo "      target.build_configurations.each do |config|"
    echo "        config.build_settings['EXCLUDED_ARCHS[sdk=iphoneos*]'] = 'arm64'"
    echo "        config.build_settings['SKIP_INSTALL'] = 'YES'"
    echo "      end"
    echo "    end"
    echo ""
    echo "Press ENTER when manual edit is complete..."
    read
else
    echo "✅ No existing post_install block - adding complete block"
    
    # Add complete post_install block
    cat >> ios/Podfile << 'EOF'

post_install do |installer|
  installer.pods_project.targets.each do |target|
    target.build_configurations.each do |config|
      config.build_settings['BUILD_LIBRARY_FOR_DISTRIBUTION'] = 'NO'
    end
    if ['CwlCatchException', 'CwlCatchExceptionSupport'].include?(target.name)
      target.build_configurations.each do |config|
        config.build_settings['EXCLUDED_ARCHS[sdk=iphoneos*]'] = 'arm64'
        config.build_settings['SKIP_INSTALL'] = 'YES'
      end
    end
  end
end
EOF
    echo "✅ CwlCatchException exclusion block added to Podfile"
fi

echo ""
echo "=== STEP 3: REBUILD COCOAPODS WITH EXCLUSION ==="
cd ios
rm -rf Pods Podfile.lock
echo "✅ Cleaned existing Pods and Podfile.lock"

echo "Running pod install with CwlCatchException exclusion..."
pod install

echo ""
echo "=== STEP 4: CHECK IF CWLCATCHEXCEPTION WAS EXCLUDED ==="
if grep -i "cwlcatchexception" Podfile.lock; then
    echo "❌ CwlCatchException still present in Podfile.lock"
    PODFILE_FIX_SUCCESS=false
else
    echo "✅ CwlCatchException successfully excluded from Podfile.lock"
    PODFILE_FIX_SUCCESS=true
fi

echo ""
echo "=== STEP 5: BUILD RELEASE APP ==="
cd ..
flutter clean
flutter build ios --release --no-codesign

echo ""
echo "=== STEP 6: VERIFY CWLCATCHEXCEPTION ELIMINATION ==="
echo "Checking Runner binary for CwlCatchException references..."
if otool -L build/ios/Release-iphoneos/Runner.app/Runner | grep -i cwl; then
    echo "❌ CwlCatchException still referenced in Runner binary"
    BINARY_CHECK_SUCCESS=false
else
    echo "✅ No CwlCatchException references found in Runner binary"
    BINARY_CHECK_SUCCESS=true
fi

echo ""
echo "=== STEP 7: SIGN AND INSTALL APP ==="
if [ "$PODFILE_FIX_SUCCESS" = true ] && [ "$BINARY_CHECK_SUCCESS" = true ]; then
    echo "✅ Podfile fix successful - proceeding with signing and installation"
    
    # Find Apple Developer certificate
    CERT_HASH=$(security find-identity -v -p codesigning | grep "Apple Development: Mikhail Glik" | awk '{print $2}')
    
    if [ -z "$CERT_HASH" ]; then
        echo "❌ Apple Developer certificate not found"
        exit 1
    fi
    
    echo "Using certificate: $CERT_HASH"
    
    # Create entitlements
    cat > entitlements.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>application-identifier</key>
    <string>4HGRU6TKGQ.com.glikfamily.audioura</string>
    <key>com.apple.developer.team-identifier</key>
    <string>4HGRU6TKGQ</string>
</dict>
</plist>
EOF
    
    # Sign app with entitlements
    codesign --force --sign "$CERT_HASH" --entitlements entitlements.plist --timestamp build/ios/Release-iphoneos/Runner.app
    
    echo "✅ App signed successfully"
    
    # Install via devicectl
    DEVICE_ID="00008140-000558A902BA801C"
    xcrun devicectl device install app --device "$DEVICE_ID" build/ios/Release-iphoneos/Runner.app
    
    echo "✅ App installation attempted"
    echo ""
    echo "🎉 PODFILE FIX COMPLETE - TEST APP LAUNCH ON IPHONE"
    echo "Expected: App launches without CwlCatchException crash"
    echo "Expected: Full functionality including speech_to_text and flutter_sound"
    
else
    echo "❌ Podfile fix failed - CwlCatchException still present"
    echo "Next step: Execute remove_cwl_source_plugin.sh (with UDID fix applied)"
fi

echo ""
echo "=== RESULTS SUMMARY ==="
echo "Podfile Fix Success: $PODFILE_FIX_SUCCESS"
echo "Binary Check Success: $BINARY_CHECK_SUCCESS"
echo "speech_to_text preserved: $(grep -q speech_to_text pubspec.yaml && echo "YES" || echo "NO")"
echo "flutter_sound preserved: $(grep -q flutter_sound pubspec.yaml && echo "YES" || echo "NO")"
echo ""
echo "Test app launch and report results!"