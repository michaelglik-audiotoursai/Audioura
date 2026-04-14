#!/bin/bash
cd ~/Development/AudioTours/development
echo "=== STEP 1: GIT REPOSITORY VERIFICATION ===" > step1_results.txt
echo "Checking if setup guide created proper structure..." >> step1_results.txt
echo "" >> step1_results.txt
echo "1. Checking ~/Development/AudioTours directory:" >> step1_results.txt
if [ -d ~/Development/AudioTours ]; then
    echo "✅ ~/Development/AudioTours EXISTS" >> step1_results.txt
else
    echo "❌ ~/Development/AudioTours MISSING" >> step1_results.txt
fi
echo "" >> step1_results.txt
echo "2. Checking Git repository status:" >> step1_results.txt
if [ -d ~/Development/AudioTours/.git ]; then
    echo "✅ Git repository EXISTS" >> step1_results.txt
    cd ~/Development/AudioTours
    echo "Current branch:" >> development/step1_results.txt
    git branch >> development/step1_results.txt 2>&1
else
    echo "❌ Git repository MISSING" >> step1_results.txt
fi
echo "" >> ~/Development/AudioTours/development/step1_results.txt
echo "3. Checking development subdirectory:" >> ~/Development/AudioTours/development/step1_results.txt
if [ -d ~/Development/AudioTours/development ]; then
    echo "✅ development/ subdirectory EXISTS" >> ~/Development/AudioTours/development/step1_results.txt
    echo "Contents:" >> ~/Development/AudioTours/development/step1_results.txt
    ls -la ~/Development/AudioTours/development/ >> ~/Development/AudioTours/development/step1_results.txt 2>&1
else
    echo "❌ development/ subdirectory MISSING" >> ~/Development/AudioTours/development/step1_results.txt
fi
echo "" >> ~/Development/AudioTours/development/step1_results.txt
echo "4. Checking Flutter app directory:" >> ~/Development/AudioTours/development/step1_results.txt
if [ -d ~/Development/AudioTours/development/audio_tour_app ]; then
    echo "✅ audio_tour_app/ EXISTS" >> ~/Development/AudioTours/development/step1_results.txt
    echo "Flutter files present:" >> ~/Development/AudioTours/development/step1_results.txt
    ls -la ~/Development/AudioTours/development/audio_tour_app/pubspec.yaml >> ~/Development/AudioTours/development/step1_results.txt 2>&1
    ls -la ~/Development/AudioTours/development/audio_tour_app/lib/ >> ~/Development/AudioTours/development/step1_results.txt 2>&1
    ls -la ~/Development/AudioTours/development/audio_tour_app/ios/ >> ~/Development/AudioTours/development/step1_results.txt 2>&1
else
    echo "❌ audio_tour_app/ MISSING" >> ~/Development/AudioTours/development/step1_results.txt
fi
echo "" >> ~/Development/AudioTours/development/step1_results.txt
echo "STEP 1 VERIFICATION COMPLETED" >> ~/Development/AudioTours/development/step1_results.txt