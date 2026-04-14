#!/bin/bash
echo "=== MAC MINI DIAGNOSTIC STEP 1 ===" > step1_diagnostic.txt
echo "Starting diagnostic at $(date)" >> step1_diagnostic.txt
echo "" >> step1_diagnostic.txt

echo "TEST 1: AudioTours directory" >> step1_diagnostic.txt
if [ -d ~/Development/AudioTours ]; then
    echo "✅ ~/Development/AudioTours EXISTS" >> step1_diagnostic.txt
    echo "Contents:" >> step1_diagnostic.txt
    ls -la ~/Development/AudioTours/ >> step1_diagnostic.txt 2>&1
else
    echo "❌ ~/Development/AudioTours MISSING" >> step1_diagnostic.txt
fi

echo "" >> step1_diagnostic.txt
echo "TEST 2: Git repository" >> step1_diagnostic.txt
if [ -d ~/Development/AudioTours/.git ]; then
    echo "✅ Git repository EXISTS" >> step1_diagnostic.txt
    cd ~/Development/AudioTours
    echo "Current branch:" >> step1_diagnostic.txt
    git branch >> step1_diagnostic.txt 2>&1
    echo "Git status:" >> step1_diagnostic.txt
    git status >> step1_diagnostic.txt 2>&1
else
    echo "❌ Git repository MISSING" >> step1_diagnostic.txt
fi

echo "" >> step1_diagnostic.txt
echo "TEST 3: Development subdirectory" >> step1_diagnostic.txt
if [ -d ~/Development/AudioTours/development ]; then
    echo "✅ development/ subdirectory EXISTS" >> step1_diagnostic.txt
    echo "Key files in development/:" >> step1_diagnostic.txt
    ls -la ~/Development/AudioTours/development/ | grep -E "(audio_tour_app|\.py|\.sh|docker)" >> step1_diagnostic.txt 2>&1
else
    echo "❌ development/ subdirectory MISSING" >> step1_diagnostic.txt
fi

echo "" >> step1_diagnostic.txt
echo "TEST 4: Flutter app" >> step1_diagnostic.txt
if [ -d ~/Development/AudioTours/development/audio_tour_app ]; then
    echo "✅ audio_tour_app/ EXISTS" >> step1_diagnostic.txt
    echo "Flutter key files:" >> step1_diagnostic.txt
    ls -la ~/Development/AudioTours/development/audio_tour_app/pubspec.yaml >> step1_diagnostic.txt 2>&1
    ls -la ~/Development/AudioTours/development/audio_tour_app/ios/ >> step1_diagnostic.txt 2>&1
else
    echo "❌ audio_tour_app/ MISSING" >> step1_diagnostic.txt
fi

echo "" >> step1_diagnostic.txt
echo "DIAGNOSTIC COMPLETED at $(date)" >> step1_diagnostic.txt