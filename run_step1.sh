#!/bin/bash
echo "=== MAC MINI STEP 1 EXECUTION LOG ===" > step1_execution.txt
echo "Starting Step 1 at $(date)" >> step1_execution.txt
echo "" >> step1_execution.txt

echo "1. Checking if AudioTours directory exists..." >> step1_execution.txt
if [ -d ~/Development/AudioTours ]; then
    echo "✅ ~/Development/AudioTours EXISTS" >> step1_execution.txt
    cd ~/Development/AudioTours >> step1_execution.txt 2>&1
    echo "Current directory: $(pwd)" >> step1_execution.txt
else
    echo "❌ ~/Development/AudioTours MISSING - Setup guide Step 10 not completed" >> step1_execution.txt
    echo "Available directories in ~/Development/:" >> step1_execution.txt
    ls -la ~/Development/ >> step1_execution.txt 2>&1
    echo "STEP 1 FAILED - DIRECTORY MISSING" >> step1_execution.txt
    exit 1
fi

echo "" >> step1_execution.txt
echo "2. Pulling latest changes..." >> step1_execution.txt
git pull origin Newsletters >> step1_execution.txt 2>&1

echo "" >> step1_execution.txt
echo "3. Checking development subdirectory..." >> step1_execution.txt
if [ -d ~/Development/AudioTours/development ]; then
    echo "✅ development/ subdirectory EXISTS" >> step1_execution.txt
    cd ~/Development/AudioTours/development >> step1_execution.txt 2>&1
    echo "Current directory: $(pwd)" >> step1_execution.txt
else
    echo "❌ development/ subdirectory MISSING" >> step1_execution.txt
    echo "Contents of AudioTours directory:" >> step1_execution.txt
    ls -la ~/Development/AudioTours/ >> step1_execution.txt 2>&1
    echo "STEP 1 FAILED - DEVELOPMENT DIRECTORY MISSING" >> step1_execution.txt
    exit 1
fi

echo "" >> step1_execution.txt
echo "4. Running verification script..." >> step1_execution.txt
if [ -f step1_verify.sh ]; then
    bash step1_verify.sh >> step1_execution.txt 2>&1
else
    echo "❌ step1_verify.sh script MISSING" >> step1_execution.txt
    echo "Available files:" >> step1_execution.txt
    ls -la >> step1_execution.txt 2>&1
    echo "STEP 1 FAILED - VERIFICATION SCRIPT MISSING" >> step1_execution.txt
    exit 1
fi

echo "" >> step1_execution.txt
echo "5. Committing results to Git..." >> step1_execution.txt
git add step1_results.txt step1_execution.txt >> step1_execution.txt 2>&1
git commit -m "Mac Mini Step 1 execution results" >> step1_execution.txt 2>&1
git push origin Newsletters >> step1_execution.txt 2>&1

echo "" >> step1_execution.txt
echo "Step 1 completed at $(date)" >> step1_execution.txt
echo "READY FOR iOS AMAZON-Q ANALYSIS" >> step1_execution.txt