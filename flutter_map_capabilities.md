# Flutter Map Capabilities for AudioTours

## Custom Icons & Markers
Flutter Map supports:
- **Custom icons** for different tour types (walking tour, treat, museum, etc.)
- **Interactive markers** that respond to taps
- **Popup windows** with tour information
- **Clustering** for multiple tours in the same area
- **Custom styling** for different tour categories

## Example Implementation

### 1. Custom Markers
```dart
MarkerLayer(
  markers: [
    Marker(
      point: LatLng(42.2763, -72.3997), // Clapp Memorial Library
      width: 40,
      height: 40,
      child: GestureDetector(
        onTap: () => _onTourMarkerTapped(tourId: "123", location: "Clapp Memorial Library"),
        child: Icon(
          Icons.tour, // or custom walking tour icon
          color: Colors.blue,
          size: 30,
        ),
      ),
    ),
    Marker(
      point: LatLng(42.3601, -71.0589), // Boston Common
      width: 40,
      height: 40,
      child: GestureDetector(
        onTap: () => _onTreatMarkerTapped(treatId: "456"),
        child: Icon(
          Icons.local_cafe, // treat icon
          color: Colors.orange,
          size: 30,
        ),
      ),
    ),
  ],
)
```

### 2. Interactive Behavior
```dart
void _onTourMarkerTapped({required String tourId, required String location}) async {
  // Show loading dialog
  showDialog(context: context, builder: (_) => LoadingDialog());
  
  try {
    // 1. Download tour from your Docker service
    final tourZip = await _downloadTourFromService(tourId, location);
    
    // 2. Unzip and store locally
    final localTourPath = await _unzipAndStoreTour(tourZip);
    
    // 3. Add to My Tours
    await _addToMyTours(localTourPath);
    
    // 4. Navigate to audio tour
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => AudioTourScreen(tourPath: localTourPath))
    );
    
  } catch (e) {
    // Handle error
    _showErrorDialog("Failed to load tour: $e");
  }
}
```

### 3. Tour Download Service
```dart
Future<Uint8List> _downloadTourFromService(String tourId, String location) async {
  final response = await http.get(
    Uri.parse('http://your-docker-host:5003/download-tour/$tourId'),
    headers: {'Content-Type': 'application/json'},
  );
  
  if (response.statusCode == 200) {
    return response.bodyBytes;
  } else {
    throw Exception('Failed to download tour');
  }
}
```

## Required Flutter Map Features

### Dependencies (pubspec.yaml)
```yaml
dependencies:
  flutter_map: ^6.1.0
  latlong2: ^0.8.1
  http: ^1.1.0
  archive: ^3.4.0  # for unzipping
  path_provider: ^2.1.0  # for local storage
```

### Map Widget Structure
```dart
FlutterMap(
  options: MapOptions(
    initialCenter: LatLng(42.3601, -71.0589), // Boston area
    initialZoom: 10.0,
  ),
  children: [
    // Base map tiles (free)
    TileLayer(
      urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      userAgentPackageName: 'com.example.audiotours',
    ),
    
    // Tour markers
    MarkerLayer(markers: _buildTourMarkers()),
    
    // Treat markers
    MarkerLayer(markers: _buildTreatMarkers()),
    
    // User location
    MarkerLayer(markers: [_buildUserLocationMarker()]),
  ],
)
```

## Backend Service Integration

You'll need a service to deliver tours from your PostgreSQL database:

### New Docker Service: tour-delivery
```python
@app.route('/tours-near/<lat>/<lng>')
def get_tours_near_location(lat, lng):
    # Query database for tours within radius
    tours = query_tours_near(float(lat), float(lng), radius_km=50)
    return jsonify([{
        'id': tour.id,
        'name': tour.tour_name,
        'lat': tour.lat,
        'lng': tour.lng,
        'type': 'walking_tour'
    } for tour in tours])

@app.route('/download-tour/<tour_id>')
def download_tour(tour_id):
    # Get tour zip from database
    tour = get_tour_by_id(tour_id)
    return send_file(
        BytesIO(tour.audio_tour),
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'{tour.tour_name}.zip'
    )
```

## Advantages of Flutter Map for Your Use Case

1. **Free**: No costs or API limits
2. **Custom Icons**: Full control over marker appearance
3. **Interactive**: Rich tap/gesture handling
4. **Offline Support**: Can cache tiles for offline use
5. **Performance**: Smooth scrolling and zooming
6. **Integration**: Easy to integrate with your existing Docker services

## Implementation Steps

1. Replace Mapbox with Flutter Map
2. Create tour delivery service in Docker
3. Implement marker tap handlers
4. Add tour download/unzip functionality
5. Integrate with "My Tours" page

This approach gives you complete control over the user experience while keeping costs at zero!