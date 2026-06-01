#!/bin/bash
# ASSIGNMENT 21: REVERT PODFILE TO CLEAN STATE AND DIAGNOSE FRAMEWORK EMBEDDING
# This script does NOT attempt a fix. It collects evidence so Claude can choose
# the right fix in a follow-up assignment.

# Terminal session recorder
exec > >(tee ~/Desktop/revert_and_diagnose_session.txt) 2>&1

echo "🍎 iOS AMAZON-Q - REVERT AND DIAGNOSE (Assignment 21)"
echo "Date: $(python3 -c "import datetime; print(datetime.datetime.now())")"
echo ""

cd ~/Development/AudioTours/development/audio_tour_app

echo "=== STEP 1: BACKUP CURRENT (POST-V3) PODFILE ==="
cp ios/Podfile ios/Podfile.before_revert
echo "✅ Current Podfile backed up to ios/Podfile.before_revert"

echo ""
echo "=== STEP 2: WRITE CLEAN PODFILE (REMOVE V1/V2/V3 ADDITIONS) ==="
# This rewrites the post_install block to its pre-v1 state, keeping only
# the project's original customizations (IPHONEOS_DEPLOYMENT_TARGET, ENABLE_BITCODE,
# the bundle-target CODE_SIGNING_ALLOWED). Removes the BUILD_LIBRARY_FOR_DISTRIBUTION
# line and the entire CwlCatchException exclusion block that v1/v2/v3 added.

cat > ios/Podfile << 'EOF'
# Uncomment this line to define a global platform for your project
platform :ios, '13.0'

# CocoaPods analytics sends network stats synchronously affecting flutter build latency.
ENV['COCOAPODS_DISABLE_STATS'] = 'true'

project 'Runner', {
  'Debug' => :debug,
  'Profile' => :release,
  'Release' => :release,
}

def flutter_root
  generated_xcode_build_settings_path = File.expand_path(File.join('..', 'Flutter', 'Generated.xcconfig'), __FILE__)
  unless File.exist?(generated_xcode_build_settings_path)
    raise "#{generated_xcode_build_settings_path} must exist. If you're running pod install manually, make sure flutter pub get is executed first"
  end

  File.foreach(generated_xcode_build_settings_path) do |line|
    matches = line.match(/FLUTTER_ROOT\=(.*)/)
    return matches[1].strip if matches
  end
  raise "FLUTTER_ROOT not found in #{generated_xcode_build_settings_path}. Try deleting Generated.xcconfig, then run flutter pub get"
end

require File.expand_path(File.join('packages', 'flutter_tools', 'bin', 'podhelper'), flutter_root)

flutter_ios_podfile_setup

target 'Runner' do
  use_frameworks!
  use_modular_headers!

  flutter_install_all_ios_pods File.dirname(File.realpath(__FILE__))
  target 'RunnerTests' do
    inherit! :search_paths
  end
end

post_install do |installer|
  installer.pods_project.targets.each do |target|
    flutter_additional_ios_build_settings(target)
    # Force iOS 13.0+ deployment target for ALL pods (Flutter requirement)
    target.build_configurations.each do |config|
      config.build_settings['IPHONEOS_DEPLOYMENT_TARGET'] = '13.0'
      config.build_settings['ENABLE_BITCODE'] = 'NO'

      # Fix Swift version issues
      if target.respond_to?(:product_type) and target.product_type == "com.apple.product-type.bundle"
        config.build_settings['CODE_SIGNING_ALLOWED'] = 'NO'
      end
    end
  end
end
EOF
echo "✅ Clean Podfile written (CwlCatchException exclusion removed)"

echo ""
echo "=== STEP 3: CLEAN FLUTTER ARTIFACTS ==="
flutter clean || { echo "❌ flutter clean failed"; exit 1; }
echo "✅ Flutter artifacts cleaned"

echo ""
echo "=== STEP 4: REGENERATE FLUTTER EPHEMERAL FILES ==="
flutter pub get || { echo "❌ flutter pub get failed"; exit 1; }
echo "✅ Generated.xcconfig regenerated"

echo ""
echo "=== STEP 5: CLEAN AND INSTALL PODS ==="
cd ios
rm -rf Pods Podfile.lock
pod install || { echo "❌ pod install failed"; exit 1; }
cd ..
echo "✅ Pods installed cleanly"

echo ""
echo "=== STEP 6: BUILD RELEASE APP ==="
flutter build ios --release --no-codesign || { echo "❌ flutter build failed"; exit 1; }
echo "✅ Release build completed"

echo ""
echo "============================================================"
echo "=== STEP 7: DIAGNOSTIC CAPTURE (the whole point of this run) ==="
echo "============================================================"

RUNNER_APP="build/ios/Release-iphoneos/Runner.app"

echo ""
echo "--- DIAGNOSTIC 1: Contents of Runner.app/Frameworks/ ---"
echo "Question: is CwlCatchException.framework present in the app bundle?"
ls -la "$RUNNER_APP/Frameworks/" 2>&1 || echo "(Frameworks/ directory does not exist)"

echo ""
echo "--- DIAGNOSTIC 2: CwlCatchException.framework specifically ---"
if [ -d "$RUNNER_APP/Frameworks/CwlCatchException.framework" ]; then
    echo "✅ CwlCatchException.framework IS present in the app bundle:"
    ls -la "$RUNNER_APP/Frameworks/CwlCatchException.framework/"
    echo ""
    echo "Binary file info:"
    file "$RUNNER_APP/Frameworks/CwlCatchException.framework/CwlCatchException" 2>&1 || echo "(binary missing)"
else
    echo "❌ CwlCatchException.framework is NOT present in the app bundle"
    echo "(This means the framework was built but not embedded — that is the bug.)"
fi

echo ""
echo "--- DIAGNOSTIC 3: Runner binary linker references to CwlCatchException ---"
echo "Question: does the Runner binary expect to load CwlCatchException at runtime?"
otool -L "$RUNNER_APP/Runner" 2>&1 | grep -i cwl || echo "(No CwlCatchException reference in Runner binary)"

echo ""
echo "--- DIAGNOSTIC 4: Runner binary @rpath search paths ---"
echo "Question: does the Runner binary's rpath include @executable_path/Frameworks?"
otool -l "$RUNNER_APP/Runner" 2>&1 | grep -A2 LC_RPATH

echo ""
echo "--- DIAGNOSTIC 5: All .framework directories in build output ---"
echo "Question: which frameworks were built at all?"
find build/ios/Release-iphoneos -maxdepth 4 -name "*.framework" -type d 2>&1

echo ""
echo "--- DIAGNOSTIC 6: Code signing on CwlCatchException.framework (if it exists) ---"
if [ -d "$RUNNER_APP/Frameworks/CwlCatchException.framework" ]; then
    codesign -dvvv "$RUNNER_APP/Frameworks/CwlCatchException.framework" 2>&1 || echo "(framework not signed)"
else
    echo "(skipped — framework not in app bundle)"
fi

echo ""
echo "============================================================"
echo "=== STEP 8: ATTEMPT SIGN AND INSTALL ANYWAY ==="
echo "============================================================"
echo "Even if the embedding looks wrong, signing and installing lets us reproduce"
echo "the original launch crash and capture its details."

CERT_HASH="594584F3D3BC571D94A822A2158871CA13898701"
if ! security find-identity -v -p codesigning | grep -q "$CERT_HASH"; then
    echo "❌ Expected certificate $CERT_HASH not found in keychain — aborting sign/install"
    exit 1
fi

cat > entitlements.plist << 'EOF2'
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
EOF2

codesign --force --sign "$CERT_HASH" --entitlements entitlements.plist --timestamp "$RUNNER_APP" || { echo "❌ codesign failed"; exit 1; }
echo "✅ App signed"

DEVICE_ID="00008140-000558A902BA801C"
xcrun devicectl device install app --device "$DEVICE_ID" "$RUNNER_APP" || { echo "❌ devicectl install failed (expected if Frameworks/ is wrong)"; }

echo ""
echo "============================================================"
echo "=== STEP 9: NEXT STEPS FOR SIR MICHAEL ==="
echo "============================================================"
echo "1. Try launching Audioura on the iPhone."
echo "2. If it crashes, note the crash message (likely 'Library not loaded')."
echo "3. Optional: on the iPhone, open Settings → Privacy & Security →"
echo "   Analytics & Improvements → Analytics Data, find a recent"
echo "   'Audioura-...' crash log, AirDrop it to the Mac Mini, then copy"
echo "   into /Volumes/USB DISK/Audioura/results/."
echo "4. Copy the diagnostic artifacts (next step) to USB."
echo ""
echo "Done. Now copy results to USB:"

cp ~/Desktop/revert_and_diagnose_session.txt "/Volumes/USB DISK/Audioura/results/revert_and_diagnose_session.txt" 2>/dev/null || echo "⚠️  Could not auto-copy session log to USB"

echo "Session log saved to ~/Desktop/revert_and_diagnose_session.txt"
echo "Done."