#!/bin/bash
echo "Adding coordinates code to tour_orchestrator_service.py"
cat /app/coordinates_code.py >> /app/tour_orchestrator_service.py

# Now modify the store_audio_tour function to use the new function
sed -i 's/coords = get_coordinates_for_location(request_string or tour_name)/coords = get_coordinates_from_generator(request_string or tour_name)/' /app/tour_orchestrator_service.py

echo "Code added and function modified"
