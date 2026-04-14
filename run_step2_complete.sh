#!/bin/bash
echo "=== MAC MINI STEP 2: COMPLETE FLUTTER iOS TEST WITH GIT ===" > step2_complete_log.txt
echo "Starting complete Flutter iOS test at $(date)" >> step2_complete_log.txt
echo "" >> step2_complete_log.txt

echo "1. Pulling latest changes from Git..." >> step2_complete_log.txt
cd ~/Development/AudioTours
git pull origin Newsletters >> step2_complete_log.txt 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Git pull SUCCESSFUL" >> step2_complete_log.txt
else
    echo "❌ Git pull FAILED" >> step2_complete_log.txt
fi

echo "" >> step2_complete_log.txt
echo "2. Navigating to development directory..." >> step2_complete_log.txt
cd ~/Development/AudioTours/development >> step2_complete_log.txt 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Successfully navigated to development directory" >> step2_complete_log.txt
    echo "Current directory: $(pwd)" >> step2_complete_log.txt
else
    echo "❌ Failed to navigate to development directory" >> step2_complete_log.txt
    exit 1
fi

echo "" >> step2_complete_log.txt
echo "3. Checking Flutter installation..." >> step2_complete_log.txt
if command -v flutter &> /dev/null; then
    echo "✅ Flutter command available" >> step2_complete_log.txt
    flutter --version >> step2_complete_log.txt 2>&1
else
    echo "❌ Flutter command NOT FOUND" >> step2_complete_log.txt
    echo "Need to install Flutter SDK" >> step2_complete_log.txt
fi

echo "" >> step2_complete_log.txt
echo "4. Checking Xcode installation..." >> step2_complete_log.txt
if command -v xcodebuild &> /dev/null; then
    echo "✅ Xcode command available" >> step2_complete_log.txt
    xcodebuild -version >> step2_complete_log.txt 2>&1
else
    echo "❌ Xcode command NOT FOUND" >> step2_complete_log.txt
    echo "Need to install Xcode" >> step2_complete_log.txt
fi

echo "" >> step2_complete_log.txt
echo "5. Navigating to Flutter app directory..." >> step2_complete_log.txt
cd ~/Development/AudioTours/development/audio_tour_app >> step2_complete_log.txt 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Successfully navigated to audio_tour_app" >> step2_complete_log.txt
    echo "Current directory: $(pwd)" >> step2_complete_log.txt
else
    echo "❌ Failed to navigate to audio_tour_app" >> step2_complete_log.txt
fi

echo "" >> step2_complete_log.txt
echo "6. Checking Flutter project structure..." >> step2_complete_log.txt
if [ -f pubspec.yaml ]; then
    echo "✅ pubspec.yaml exists" >> step2_complete_log.txt
    echo "App version:" >> step2_complete_log.txt
    grep "version:" pubspec.yaml >> step2_complete_log.txt 2>&1
else
    echo "❌ pubspec.yaml missing" >> step2_complete_log.txt
fi

if [ -d ios ]; then
    echo "✅ ios/ directory exists" >> step2_complete_log.txt
    echo "iOS project files:" >> step2_complete_log.txt
    ls -la ios/ >> step2_complete_log.txt 2>&1
else
    echo "❌ ios/ directory missing" >> step2_complete_log.txt
fi

echo "" >> step2_complete_log.txt
echo "7. Running Flutter doctor..." >> step2_complete_log.txt
if command -v flutter &> /dev/null; then
    flutter doctor >> step2_complete_log.txt 2>&1
else
    echo "❌ Flutter not available for doctor check" >> step2_complete_log.txt
fi

echo "" >> step2_complete_log.txt
echo "8. Testing Flutter iOS build (dry run)..." >> step2_complete_log.txt
if command -v flutter &> /dev/null; then
    flutter build ios --dry-run >> step2_complete_log.txt 2>&1
    if [ $? -eq 0 ]; then
        echo "✅ Flutter iOS build dry-run SUCCESSFUL" >> step2_complete_log.txt
    else
        echo "❌ Flutter iOS build dry-run FAILED" >> step2_complete_log.txt
    fi
else
    echo "❌ Cannot test Flutter build - Flutter not installed" >> step2_complete_log.txt
fi

echo "" >> step2_complete_log.txt
echo "9. Committing results to Git..." >> step2_complete_log.txt
cd ~/Development/AudioTours/development
git add step2_complete_log.txt >> step2_complete_log.txt 2>&1
git commit -m "Mac Mini Step 2 Flutter iOS compilation test results" >> step2_complete_log.txt 2>&1
git push origin Newsletters >> step2_complete_log.txt 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Git commit and push SUCCESSFUL" >> step2_complete_log.txt
else
    echo "❌ Git commit and push FAILED" >> step2_complete_log.txt
fi

echo "" >> step2_complete_log.txt
echo "STEP 2 COMPLETE FLUTTER iOS TEST FINISHED at $(date)" >> step2_complete_log.txt
echo "READY FOR iOS AMAZON-Q ANALYSIS" >> step2_complete_log.txt