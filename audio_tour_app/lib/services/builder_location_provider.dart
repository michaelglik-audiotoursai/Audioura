// [LOCAL-758] A tiny seam that lets the organiser-audio builder get the device
// location and geocode an address WITHOUT binding the widget to the real
// geolocator plugin or a live network — so a widget test can drive "Use my
// location" and "address search" with a fake, on a machine with no device and
// no internet.
//
// The default [BuilderLocationProvider] is the real one (geolocator +
// OpenStreetMap Nominatim, the same geocoder Home already uses). Tests pass a
// subclass or a [FakeBuilderLocationProvider] instead.

import 'dart:convert';

import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';

/// A resolved place: coordinates plus a human label to show as the stop's
/// chosen location (e.g. the address the user searched, or "My location").
class ResolvedPlace {
  final double latitude;
  final double longitude;
  final String? label;

  const ResolvedPlace(this.latitude, this.longitude, {this.label});

  LatLng get latLng => LatLng(latitude, longitude);
}

/// The seam. The real implementation talks to the device GPS and Nominatim;
/// tests override [currentLocation] and [geocode].
class BuilderLocationProvider {
  const BuilderLocationProvider();

  /// The device's current position, or null if permission is denied/unavailable.
  /// Mirrors the permission dance the rest of the app uses.
  Future<ResolvedPlace?> currentLocation() async {
    try {
      LocationPermission permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        return null;
      }
      final pos = await Geolocator.getCurrentPosition();
      return ResolvedPlace(pos.latitude, pos.longitude, label: 'My location');
    } catch (_) {
      return null;
    }
  }

  /// Geocode a free-text address to a place, or null if nothing matched.
  /// Uses OpenStreetMap Nominatim, the same service Home's place search uses.
  Future<ResolvedPlace?> geocode(String query) async {
    final q = query.trim();
    if (q.isEmpty) return null;
    try {
      final encoded = Uri.encodeComponent(q);
      final response = await http
          .get(
            Uri.parse(
                'https://nominatim.openstreetmap.org/search?q=$encoded&format=json&limit=1'),
            headers: {'User-Agent': 'AudioTours/1.0'},
          )
          .timeout(const Duration(seconds: 10));
      if (response.statusCode == 200) {
        final data = json.decode(response.body) as List;
        if (data.isNotEmpty) {
          final result = data.first as Map<String, dynamic>;
          final lat = double.tryParse(result['lat'].toString());
          final lon = double.tryParse(result['lon'].toString());
          if (lat != null && lon != null) {
            final label = (result['display_name'] as String?)?.trim();
            return ResolvedPlace(lat, lon,
                label: (label == null || label.isEmpty) ? q : label);
          }
        }
      }
    } catch (_) {}
    return null;
  }
}

/// A test double: returns the places it is seeded with, no device or network.
class FakeBuilderLocationProvider extends BuilderLocationProvider {
  final ResolvedPlace? myLocation;
  final ResolvedPlace? geocodeResult;

  const FakeBuilderLocationProvider({this.myLocation, this.geocodeResult});

  @override
  Future<ResolvedPlace?> currentLocation() async => myLocation;

  @override
  Future<ResolvedPlace?> geocode(String query) async => geocodeResult;
}
