# Geocoding for AudioTours

This document explains how geocoding works in the AudioTours application.

## Current Implementation

The application uses the OpenAI API to get accurate coordinates for any location in the world. This approach was chosen because:

1. It provides accurate coordinates for any location worldwide
2. It handles misspellings and variations in location names
3. It uses the same OpenAI API key that's already used for tour generation

## How Geocoding Works

When a tour is generated:

1. The tour orchestrator extracts the location name from the request
2. It sends a request to the OpenAI API asking for coordinates
3. It parses the response to extract the latitude and longitude
4. If coordinates are found, they are stored in the database
5. If no coordinates are found, NULL values are stored

## OpenAI API Integration

The application uses the same OpenAI API key that's used for tour generation. The key is automatically retrieved from the tour-generator service, so no additional configuration is needed.

The prompt used for geocoding is:
```
What are the latitude and longitude coordinates for [location]? Please respond with only the decimal coordinates in the format 'latitude, longitude' without any other text.
```

## Verifying Coordinates

You can verify coordinates using:

1. Google Maps: Right-click on a location and select "What's here?" to see coordinates
2. OpenStreetMap: Right-click and select "Show address" to see coordinates
3. The `get_coordinates_openai.py` script: `get_coordinates_openai.bat "Location Name" YOUR_OPENAI_API_KEY`

## Troubleshooting

If coordinates are not being stored correctly:

1. Check that the OpenAI API key is set correctly in the tour-generator service:
   ```
   docker exec -it development-tour-generator-1 bash -c "echo $OPENAI_API_KEY"
   ```

2. Check the logs for any OpenAI API errors:
   ```
   docker logs development-tour-orchestrator-1
   ```

3. Test the OpenAI API directly:
   ```
   get_coordinates_openai.bat "Your Location" YOUR_OPENAI_API_KEY
   ```

## Notes

- Coordinates are stored as latitude and longitude in decimal degrees
- The OpenAI API is very accurate for well-known locations
- The application uses GPT-3.5-turbo with a low temperature (0.2) for consistent results