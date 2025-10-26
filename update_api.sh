#!/bin/bash
# Script to rebuild and restart the user-api-2 service

echo "Rebuilding user-api-2 service..."
docker-compose build user-api-2

echo "Restarting user-api-2 service..."
docker-compose restart user-api-2

echo "Waiting for service to start..."
sleep 5

echo "Testing new SQL endpoint..."
curl -X POST -H "Content-Type: application/json" \
  -d '{"sql":"SELECT COUNT(*) FROM tour_requests"}' \
  http://localhost:5003/sql

echo -e "\n\nTesting update_tour endpoint..."
curl -X POST -H "Content-Type: application/json" \
  -d '{"tour_id":"tour_1981b2356dc","status":"completed"}' \
  http://localhost:5003/update_tour

echo -e "\n\nDone!"