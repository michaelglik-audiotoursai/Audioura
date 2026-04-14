#!/bin/bash
echo "=== MAC MINI STEP 1 EXECUTION LOG ===" > step1_execution.txt
echo "Starting Step 1 at $(date)" >> step1_execution.txt
echo "" >> step1_execution.txt

echo "1. Changing to AudioTours directory..." >> step1_execution.txt
cd ~/Development/AudioTours >> step1_execution.txt 2>&1
echo "Current directory: $(pwd)" >> step1_execution.txt

echo "" >> step1_execution.txt
echo "2. Pulling latest changes..." >> step1_execution.txt
git pull origin Newsletters >> step1_execution.txt 2>&1

echo "" >> step1_execution.txt
echo "3. Changing to development directory..." >> step1_execution.txt
cd ~/Development/AudioTours/development >> step1_execution.txt 2>&1
echo "Current directory: $(pwd)" >> step1_execution.txt

echo "" >> step1_execution.txt
echo "4. Running verification script..." >> step1_execution.txt
bash step1_verify.sh >> step1_execution.txt 2>&1

echo "" >> step1_execution.txt
echo "5. Committing results to Git..." >> step1_execution.txt
git add step1_results.txt step1_execution.txt >> step1_execution.txt 2>&1
git commit -m "Mac Mini Step 1 execution results" >> step1_execution.txt 2>&1
git push origin Newsletters >> step1_execution.txt 2>&1

echo "" >> step1_execution.txt
echo "Step 1 completed at $(date)" >> step1_execution.txt
echo "READY FOR iOS AMAZON-Q ANALYSIS" >> step1_execution.txt