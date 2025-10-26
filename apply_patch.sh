#!/bin/bash
# Make a backup of the original file
cp /app/tour_orchestrator_service.py /app/tour_orchestrator_service.py.bak_patch

# Find the line before "# Step 8: Store in database"
line_num=$(grep -n "# Step 8: Store in database" /app/tour_orchestrator_service.py | cut -d: -f1)

# Insert the patch before that line
head -n $line_num /app/tour_orchestrator_service.py > /app/tour_orchestrator_service.py.new
cat /app/coordinates_patch.txt >> /app/tour_orchestrator_service.py.new
tail -n +$line_num /app/tour_orchestrator_service.py >> /app/tour_orchestrator_service.py.new

# Replace the original file
mv /app/tour_orchestrator_service.py.new /app/tour_orchestrator_service.py

echo "Patch applied successfully"
