import 'dart:convert';
import 'dart:io';
import 'package:geolocator/geolocator.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:http/http.dart' as http;
import '../screens/debug_log_viewer_screen.dart';

/// Result states from a nearby-service lookup.
/// D162: three distinguishable states — found / none found / could not search.
enum ServiceLookupState { found, noneFound, couldNotSearch }

class ServiceLookupResult {
  final ServiceLookupState state;
  /// e.g. "a public fountain 200 metres ahead, just past the church"
  final String? description;
  /// Distance in metres (rounded to nearest 50)
  final int? distanceMetres;
  /// Landmark reference
  final String? landmark;

  const ServiceLookupResult({
    required this.state,
    this.description,
    this.distanceMetres,
    this.landmark,
  });
}

class NextStopResult {
  final ServiceLookupState state;
  /// e.g. "300 metres ahead"
  final String? distanceDescription;
  final int? distanceMetres;
  final String? stopName;

  const NextStopResult({
    required this.state,
    this.distanceDescription,
    this.distanceMetres,
    this.stopName,
  });
}

/// Runtime navigation service — queries LOCAL-337 for nearby amenities and
/// next-stop distance. Falls back gracefully if the endpoint is unavailable
/// (LOCAL-337 may not be merged yet).
class NavigationService {
  static final NavigationService _instance = NavigationService._internal();
  factory NavigationService() => _instance;
  NavigationService._internal();

  /// Look up the nearest water source or toilet.
  /// [type] is 'water' or 'toilet'.
  Future<ServiceLookupResult> findNearbyService(String type) async {
    try {
      final position = await _getCurrentPosition();
      if (position == null) {
        await DebugLogHelper.addDebugLog('NAV: Could not get position for $type lookup');
        return const ServiceLookupResult(state: ServiceLookupState.couldNotSearch);
      }

      final result = await _queryServer(type, position);
      return result;
    } catch (e) {
      await DebugLogHelper.addDebugLog('NAV: Error in findNearbyService($type): $e');
      return const ServiceLookupResult(state: ServiceLookupState.couldNotSearch);
    }
  }

  /// Get distance to the next stop from current position.
  /// Reads stop coordinates from the tour's audio_N.txt files.
  Future<NextStopResult> getNextStopDistance(int nextStopIndex, String tourPath) async {
    try {
      final position = await _getCurrentPosition();
      if (position == null) {
        await DebugLogHelper.addDebugLog('NAV: Could not get position for next-stop lookup');
        return const NextStopResult(state: ServiceLookupState.couldNotSearch);
      }

      // Read the next stop's coordinates from its audio_N.txt file
      final coords = await _getStopCoordinates(nextStopIndex, tourPath);
      if (coords == null) {
        await DebugLogHelper.addDebugLog('NAV: No coordinates for stop $nextStopIndex');
        return const NextStopResult(state: ServiceLookupState.noneFound);
      }

      final distanceMetres = Geolocator.distanceBetween(
        position.latitude,
        position.longitude,
        coords['lat'] as double,
        coords['lng'] as double,
      ).round();

      // Round to nearest 50m for spoken naturalness
      final rounded = ((distanceMetres + 25) ~/ 50) * 50;
      final displayDistance = rounded < 50 ? 50 : rounded;

      await DebugLogHelper.addDebugLog(
          'NAV: Next stop $nextStopIndex is ${distanceMetres}m away (rounded: ${displayDistance}m)');

      return NextStopResult(
        state: ServiceLookupState.found,
        distanceDescription: '$displayDistance metres ahead',
        distanceMetres: displayDistance,
        stopName: coords['name'] as String?,
      );
    } catch (e) {
      await DebugLogHelper.addDebugLog('NAV: Error in getNextStopDistance: $e');
      return const NextStopResult(state: ServiceLookupState.couldNotSearch);
    }
  }

  /// Query the LOCAL-337 navigation endpoint.
  /// Falls back gracefully if endpoint is unavailable.
  Future<ServiceLookupResult> _queryServer(String type, Position position) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final mode = prefs.getString('server_mode') ?? 'cloud';
      final ip = prefs.getString('server_ip') ?? '192.168.1.100';

      // LOCAL-337 endpoint: port 5009, /nearby-services
      final baseUrl = mode == 'cloud'
          ? 'https://api.audioura.com'
          : 'http://$ip:5009';
      final url = Uri.parse('$baseUrl/nearby-services');

      final response = await http.post(
        url,
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'type': type,
          'latitude': position.latitude,
          'longitude': position.longitude,
        }),
      ).timeout(const Duration(seconds: 5));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        if (data['found'] == true) {
          return ServiceLookupResult(
            state: ServiceLookupState.found,
            description: data['description'] as String?,
            distanceMetres: data['distance_metres'] as int?,
            landmark: data['landmark'] as String?,
          );
        } else {
          return const ServiceLookupResult(state: ServiceLookupState.noneFound);
        }
      } else if (response.statusCode == 404) {
        await DebugLogHelper.addDebugLog('NAV: LOCAL-337 endpoint returned 404 — not deployed yet');
        return const ServiceLookupResult(state: ServiceLookupState.couldNotSearch);
      } else {
        await DebugLogHelper.addDebugLog('NAV: Server returned ${response.statusCode}');
        return const ServiceLookupResult(state: ServiceLookupState.couldNotSearch);
      }
    } catch (e) {
      // Connection refused, timeout, etc. — LOCAL-337 not available
      await DebugLogHelper.addDebugLog('NAV: Server unreachable ($e) — LOCAL-337 may not be deployed');
      return const ServiceLookupResult(state: ServiceLookupState.couldNotSearch);
    }
  }

  Future<Position?> _getCurrentPosition() async {
    try {
      final permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        return null;
      }
      return await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 5),
        ),
      );
    } catch (e) {
      await DebugLogHelper.addDebugLog('NAV: getCurrentPosition error: $e');
      return null;
    }
  }

  /// Parse coordinates from audio_N.txt (same format as TourMapScreen).
  Future<Map<String, dynamic>?> _getStopCoordinates(int stopIndex, String tourPath) async {
    try {
      final file = File('$tourPath/audio_$stopIndex.txt');
      if (!await file.exists()) return null;

      final content = await file.readAsString();
      final coordMatch =
          RegExp(r'Coordinates:\s*([-\d.]+)\s*,\s*([-\d.]+)').firstMatch(content);
      if (coordMatch == null) return null;

      final lat = double.tryParse(coordMatch.group(1)!);
      final lng = double.tryParse(coordMatch.group(2)!);
      if (lat == null || lng == null) return null;

      // Extract stop name (first line)
      final lines = content.split('\n');
      final name = lines.isNotEmpty ? lines[0].trim() : 'Stop $stopIndex';

      return {'lat': lat, 'lng': lng, 'name': name};
    } catch (e) {
      await DebugLogHelper.addDebugLog('NAV: Error reading stop $stopIndex coordinates: $e');
      return null;
    }
  }
}
