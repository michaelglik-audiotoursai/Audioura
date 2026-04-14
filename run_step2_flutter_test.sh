#!/bin/bash
echo "=== MAC MINI STEP 2: FLUTTER iOS COMPILATION TEST ===" > step2_results.txt
echo "Starting Flutter iOS compilation test at $(date)" >> step2_results.txt
echo "" >> step2_results.txt

echo "1. Checking Flutter installation..." >> step2_results.txt
if command -v flutter &> /dev/null; then
    echo "✅ Flutter command available" >> step2_results.txt
    flutter --version >> step2_results.txt 2>&1
else
    echo "❌ Flutter command NOT FOUND" >> step2_results.txt
    echo "Need to install Flutter SDK" >> step2_results.txt
fi

echo "" >> step2_results.txt
echo "2. Checking Xcode installation..." >> step2_results.txt
if command -v xcodebuild &> /dev/null; then
    echo "✅ Xcode command available" >> step2_results.txt
    xcodebuild -version >> step2_results.txt 2>&1
else
    echo "❌ Xcode command NOT FOUND" >> step2_results.txt
    echo "Need to install Xcode" >> step2_results.txt
fi

echo "" >> step2_results.txt
echo "3. Navigating to Flutter app directory..." >> step2_results.txt
cd ~/Development/AudioTours/development/audio_tour_app
if [ $? -eq 0 ]; then
    echo "✅ Successfully navigated to audio_tour_app" >> step2_results.txt
    echo "Current directory: $(pwd)" >> step2_results.txt
else
    echo "❌ Failed to navigate to audio_tour_app" >> step2_results.txt
    exit 1
fi

echo "" >> step2_results.txt
echo "4. Checking Flutter project structure..." >> step2_results.txt
if [ -f pubspec.yaml ]; then
    echo "✅ pubspec.yaml exists" >> step2_results.txt
    echo "App version:" >> step2_results.txt
    grep "version:" pubspec.yaml >> step2_results.txt 2>&1
else
    echo "❌ pubspec.yaml missing" >> step2_results.txt
fi

if [ -d ios ]; then
    echo "✅ ios/ directory exists" >> step2_results.txt
    echo "iOS project files:" >> step2_results.txt
    ls -la ios/ >> step2_results.txt 2>&1
else
    echo "❌ ios/ directory missing" >> step2_results.txt
fi

echo "" >> step2_results.txt
echo "5. Running Flutter doctor..." >> step2_results.txt
if command -v flutter &> /dev/null; then
    flutter doctor >> step2_results.txt 2>&1
else
    echo "❌ Flutter not available for doctor check" >> step2_results.txt
fi

echo "" >> step2_results.txt
echo "6. Testing Flutter iOS build (dry run)..." >> step2_results.txt
if command -v flutter &> /dev/null; then
    flutter build ios --dry-run >> step2_results.txt 2>&1
    if [ $? -eq 0 ]; then
        echo "✅ Flutter iOS build dry-run SUCCESSFUL" >> step2_results.txt
    else
        echo "❌ Flutter iOS build dry-run FAILED" >> step2_results.txt
    fi
else
    echo "❌ Cannot test Flutter build - Flutter not installed" >> step2_results.txt
fi

echo "" >> step2_results.txt
echo "STEP 2 FLUTTER COMPILATION TEST COMPLETED at $(date)" >> step2_results.txt