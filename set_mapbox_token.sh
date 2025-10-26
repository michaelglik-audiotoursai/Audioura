#!/bin/bash
# Script to set Mapbox access token in Docker environment

# Check if token is provided
if [ -z "$1" ]; then
  echo "Usage: $0 <mapbox_access_token>"
  echo "Example: $0 pk.eyJ1IjoieW91cnVzZXJuYW1lIiwiYSI6ImNqeHh4eHh4eHh4eHh4eHh4eHh4eHh4In0.xxxxxxxxxxxxxxxxxxxxxxxx"
  exit 1
fi

TOKEN=$1

# Update the Docker environment
echo "Setting Mapbox access token in Docker environment..."
docker exec -it development-tour-orchestrator-1 /bin/bash -c "echo 'export MAPBOX_ACCESS_TOKEN=$TOKEN' >> /etc/environment"
docker exec -it development-tour-orchestrator-1 /bin/bash -c "echo 'export MAPBOX_ACCESS_TOKEN=$TOKEN' >> /root/.bashrc"

# Restart the service to apply changes
echo "Restarting tour-orchestrator service..."
docker restart development-tour-orchestrator-1

echo "Done! Mapbox access token has been set."
echo "You can verify it by running: docker exec -it development-tour-orchestrator-1 /bin/bash -c 'echo \$MAPBOX_ACCESS_TOKEN'"