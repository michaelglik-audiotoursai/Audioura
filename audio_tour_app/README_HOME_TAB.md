# Home Tab with Map Integration

This update adds a new Home tab to the Audio Tours app that displays a map with nearby tours.

## Features

- New Home tab as the default landing page
- Mapbox integration to display a map
- Shows user's current location (if permission granted)
- Displays tour markers for tours in the database
- 10-mile radius search for nearby tours
- Clicking on a tour marker allows adding it to My Tours

## Setup Instructions

1. **Environment Variables**:
   - Make sure the `MAPBOX_ACCESS_TOKEN` environment variable is set
   - The app will read this token from the environment

2. **Docker Services**:
   - A new `map-delivery` service has been added to docker-compose.yml
   - This service runs on port 5005 and provides nearby tour data

3. **Build and Run**:
   - Run `flutter pub get` to install new dependencies
   - Build and run the app as usual

## Technical Details

- The Home tab is now the first tab in the bottom navigation bar
- The map shows tours within a 10-mile radius of the user's location
- If location permission is denied, it falls back to:
  1. Previously saved location
  2. Default location (Boston Town Hall)
- Tours from the database are displayed as markers on the map
- Clicking a marker allows adding the tour to My Tours and playing it

## Version History

- v1.0.0+94: Added Home tab with map integration