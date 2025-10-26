#!/bin/bash
echo "Adding coordinates endpoint to app.py"
cat /app/coordinates_endpoint.py >> /app/app.py
echo "Endpoint added"
