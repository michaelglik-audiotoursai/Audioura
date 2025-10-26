#!/bin/bash
echo "Modifying store_audio_tour function..."
sed -i 's/coords = get_coordinates_for_location(request_string or tour_name)/coords = get_coordinates_from_generator(request_string or tour_name)/' /app/tour_orchestrator_service.py
echo "Function modified"
