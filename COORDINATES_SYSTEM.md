# Coordinates System for AudioTours

This document explains how the coordinates system works in the AudioTours application.

## Overview

The AudioTours application now uses a dedicated service called `coordinates-fromai` to get coordinates for any location using the OpenAI API. This service is used by the tour orchestrator to add coordinates to tours in the database.

## Architecture

The coordinates system consists of the following components:

1. **coordinates-fromai service**: A dedicated service that uses OpenAI to get coordinates for any location
2. **tour-orchestrator service**: Uses the coordinates-fromai service to get coordinates for tours
3. **PostgreSQL database**: Stores the coordinates in the `lat` and `lng` columns of the `audio_tours` table

## How It Works

When a tour is generated:

1. The tour orchestrator extracts the location name from the request
2. It sends a request to the coordinates-fromai service to get coordinates for the location
3. The coordinates-fromai service uses OpenAI to get accurate coordinates
4. The tour orchestrator stores the coordinates in the database
5. The mobile app displays the coordinates on a map

## Testing

You can test the coordinates system in several ways:

1. **Test the coordinates-fromai service directly**:
   ```
   test_coordinates_service_v2.bat "Keene Public Library, Keene, NH"
   ```

2. **Generate a tour through the mobile app or API**:
   Generate a tour for a location like "Boston Public Library, Boston, MA"

3. **Check the database**:
   ```
   docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c "SELECT tour_name, lat, lng FROM audio_tours ORDER BY id DESC LIMIT 5;"
   ```

## Troubleshooting

If coordinates are not being stored correctly:

1. Check if the coordinates-fromai service is running:
   ```
   docker ps | findstr coordinates-fromai
   ```

2. Check the logs:
   ```
   docker-compose logs coordinates-fromai
   docker-compose logs tour-orchestrator
   ```

3. If the coordinates-fromai service is not running, fix it:
   ```
   fix_coordinates_service.bat
   ```

## Building the Mobile App

To build the mobile app with the latest coordinates system:

1. Update the version:
   ```
   verify_and_update_app.bat
   ```

2. Build the app:
   ```
   cd audio_tour_app
   flutter build apk
   ```

The mobile app will now display coordinates for all tours that have them in the database.