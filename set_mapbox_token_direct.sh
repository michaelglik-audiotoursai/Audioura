#!/bin/bash
# Script to directly modify the tour_orchestrator_service.py file to include the Mapbox token

# Check if token is provided
if [ -z "$1" ]; then
  echo "Usage: $0 <mapbox_access_token>"
  echo "Example: $0 pk.eyJ1IjoieW91cnVzZXJuYW1lIiwiYSI6ImNqeHh4eHh4eHh4eHh4eHh4eHh4eHh4In0.xxxxxxxxxxxxxxxxxxxxxxxx"
  exit 1
fi

TOKEN=$1

# Create a temporary file with the token
cat > mapbox_token_temp.py << EOF
# This file contains the Mapbox access token
MAPBOX_ACCESS_TOKEN = "$TOKEN"
EOF

# Copy the file to the Docker container
echo "Copying token file to Docker container..."
docker cp mapbox_token_temp.py development-tour-orchestrator-1:/app/mapbox_token.py

# Remove the temporary file
rm mapbox_token_temp.py

# Restart the service
echo "Restarting tour-orchestrator service..."
docker restart development-tour-orchestrator-1

echo "Done! Mapbox token has been set."
echo "You can verify it by generating a new tour and checking the logs."