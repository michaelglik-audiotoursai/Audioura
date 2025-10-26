# Mapbox Integration for AudioTours

This document explains how to set up and use Mapbox for geocoding in the AudioTours application.

## Getting a Mapbox Access Token

1. Go to [Mapbox](https://www.mapbox.com/) and create an account if you don't have one
2. Navigate to your account dashboard
3. Create a new access token or use an existing one
4. Make sure the token has the following scopes:
   - Geocoding API
   - Maps API

## Setting Up the Access Token

### Recommended Method (Direct)

```
set_mapbox_token_direct.bat YOUR_MAPBOX_ACCESS_TOKEN
```

This script will:
1. Create a Python module with your token
2. Copy it directly into the Docker container
3. Restart the tour orchestrator service

### Alternative Method (Environment Variable)

```
set_mapbox_token.bat YOUR_MAPBOX_ACCESS_TOKEN
```

## How Geocoding Works

The application uses Mapbox's Geocoding API to convert location names (like "Enfield Public Library, Connecticut") into geographic coordinates (latitude and longitude).

When a tour is generated:

1. The tour orchestrator extracts the location name from the request
2. It calls the Mapbox Geocoding API with this location name
3. If coordinates are found, they are stored in the database
4. If no coordinates are found, NULL values are stored

## Verifying the Setup

After setting the token, you can verify it's working by:

1. Generating a new tour and checking the logs:
   ```
   docker logs development-tour-orchestrator-1
   ```
   
   You should see messages like:
   ```
   Using Mapbox token from mapbox_token.py: pk.eyJ...xxxxx
   Requesting coordinates for 'Hall Memorial Library, Ellington CT' from Mapbox API
   Mapbox API response status: 200
   Found coordinates for 'Hall Memorial Library, Ellington CT': lat=41.9037, lng=-72.4616
   ```

2. Checking the database to verify coordinates were stored:
   ```
   docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c "SELECT tour_name, lat, lng FROM audio_tours ORDER BY id DESC LIMIT 5;"
   ```

## Troubleshooting

If coordinates are not being stored correctly:

1. Try the direct method to set the token:
   ```
   set_mapbox_token_direct.bat YOUR_MAPBOX_TOKEN
   ```

2. Check the logs for any Mapbox API errors:
   ```
   docker logs development-tour-orchestrator-1
   ```

3. Test the Mapbox API directly:
   ```
   curl "https://api.mapbox.com/geocoding/v5/mapbox.places/Enfield%20Public%20Library%20Connecticut.json?access_token=YOUR_TOKEN&limit=1"
   ```

4. If all else fails, rebuild the Docker container:
   ```
   docker-compose down
   docker-compose up -d
   ```
   Then set the token again using the direct method.

## Notes

- The free tier of Mapbox allows for 100,000 geocoding requests per month
- Coordinates are stored as latitude and longitude in decimal degrees
- If geocoding fails, NULL values are stored in the database