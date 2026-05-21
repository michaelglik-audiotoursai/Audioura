import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:geolocator/geolocator.dart';
import 'dart:io';
import 'dart:async';
import '../screens/debug_log_viewer_screen.dart';

class TourPoi {
  final int index;
  final String name;
  final String type;
  final String address;
  final LatLng coords;

  TourPoi({
    required this.index,
    required this.name,
    required this.type,
    required this.address,
    required this.coords,
  });
}

class TourMapScreen extends StatefulWidget {
  final String tourPath;
  final String tourTitle;
  final int? focusStopIndex; // 1-based, matches audio_N.txt numbering

  const TourMapScreen({
    super.key,
    required this.tourPath,
    required this.tourTitle,
    this.focusStopIndex,
  });

  @override
  State<TourMapScreen> createState() => _TourMapScreenState();
}

class _TourMapScreenState extends State<TourMapScreen> {
  final MapController _mapController = MapController();
  List<TourPoi> _pois = [];
  LatLng? _userLocation;
  StreamSubscription<Position>? _locationSub;
  bool _loading = true;
  String? _error;
  bool _fittedWithLocation = false;

  @override
  void initState() {
    super.initState();
    _loadPois();
    _startLocationTracking();
  }

  @override
  void dispose() {
    _locationSub?.cancel();
    super.dispose();
  }

  Future<void> _loadPois() async {
    final pois = <TourPoi>[];
    int i = 1;
    while (true) {
      final file = File('${widget.tourPath}/audio_$i.txt');
      if (!await file.exists()) break;
      try {
        final content = await file.readAsString();
        final poi = _parsePoi(i, content);
        if (poi != null) pois.add(poi);
      } catch (e) {
        await DebugLogHelper.addDebugLog('MAP: Error reading audio_$i.txt: $e');
      }
      i++;
    }
    _applyCoordJitter(pois);
    await DebugLogHelper.addDebugLog('MAP: Loaded ${pois.length} POIs for ${widget.tourTitle}');
    if (mounted) {
      setState(() {
        _pois = pois;
        _loading = false;
        if (pois.isEmpty) _error = 'No map data found for this tour.';
      });
      if (pois.isNotEmpty) _fitBounds();
    }
  }

  void _applyCoordJitter(List<TourPoi> pois) {
    // NF8: offset POIs sharing identical coords so all markers are visible (~8m)
    const double step = 0.00008;
    final offsets = <String, int>{};
    for (int i = 0; i < pois.length; i++) {
      final key = '${pois[i].coords.latitude},${pois[i].coords.longitude}';
      final n = offsets[key] ?? 0;
      if (n > 0) {
        // Spread duplicates: N=1 → (+step,0), N=2 → (0,+step), N=3 → (-step,0), ...
        final dx = [step, 0.0, -step, 0.0][n % 4];
        final dy = [0.0, step, 0.0, -step][n % 4];
        pois[i] = TourPoi(
          index: pois[i].index, name: pois[i].name,
          type: pois[i].type, address: pois[i].address,
          coords: LatLng(pois[i].coords.latitude + dx, pois[i].coords.longitude + dy),
        );
      }
      offsets[key] = n + 1;
    }
  }

  TourPoi? _parsePoi(int index, String content) {
    final coordMatch = RegExp(r'Coordinates:\s*([-\d.]+)\s*,\s*([-\d.]+)').firstMatch(content); // matches "Coordinates: lat, lon"
    if (coordMatch == null) return null;
    final lat = double.tryParse(coordMatch.group(1)!);
    final lng = double.tryParse(coordMatch.group(2)!);
    if (lat == null || lng == null) return null;

    final lines = content.split('\n');
    final name = lines.isNotEmpty ? lines[0].trim() : 'Stop $index';

    final typeMatch = RegExp(r'Type/Specialty:\s*(.+)').firstMatch(content);
    final type = typeMatch?.group(1)?.trim() ?? '';

    final addrMatch = RegExp(r'Address:\s*(.+)').firstMatch(content);
    final address = addrMatch?.group(1)?.trim() ?? '';

    return TourPoi(
      index: index,
      name: name,
      type: type,
      address: address,
      coords: LatLng(lat, lng),
    );
  }

  Future<void> _startLocationTracking() async {
    try {
      LocationPermission permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.deniedForever ||
          permission == LocationPermission.denied) return;

      final pos = await Geolocator.getCurrentPosition();
      if (mounted) {
        setState(() => _userLocation = LatLng(pos.latitude, pos.longitude));
      }

      _locationSub = Geolocator.getPositionStream(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.high, distanceFilter: 5),
      ).listen((pos) {
        if (mounted) {
          setState(() => _userLocation = LatLng(pos.latitude, pos.longitude));
          if (!_fittedWithLocation && _pois.isNotEmpty) {
            _fittedWithLocation = true;
            _fitBounds();
          }
        }
      });
    } catch (e) {
      await DebugLogHelper.addDebugLog('MAP: Location error: $e');
    }
  }

  void _fitBounds({bool forceFitAll = false}) {
    if (forceFitAll) _fittedWithLocation = true; // NF6: prevent GPS first-fix from overriding explicit fit-all
    if (_pois.isEmpty) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final focus = (!forceFitAll && widget.focusStopIndex != null) ? _focusPoi() : null;
      final points = focus != null && _userLocation != null
          ? [_userLocation!, focus.coords]
          : _pois.map((p) => p.coords).toList();
      if (_userLocation != null && focus == null) points.add(_userLocation!);
      if (points.length == 1) {
        _mapController.move(points.first, 15);
        return;
      }
      final bounds = LatLngBounds.fromPoints(points);
      _mapController.fitCamera(
        CameraFit.bounds(bounds: bounds, padding: const EdgeInsets.all(64)),
      );
    });
  }

  TourPoi? _focusPoi() {
    if (_pois.isEmpty) return null;
    // If a specific stop is requested, use it
    if (widget.focusStopIndex != null) {
      try {
        return _pois.firstWhere((p) => p.index == widget.focusStopIndex);
      } catch (_) {}
    }
    // Fallback: nearest POI to user location
    if (_userLocation == null) return _pois.first;
    final dist = Distance();
    TourPoi? nearest;
    double minDist = double.infinity;
    for (final poi in _pois) {
      final d = dist(_userLocation!, poi.coords);
      if (d < minDist) {
        minDist = d;
        nearest = poi;
      }
    }
    return nearest;
  }

  void _showPoiDetails(TourPoi poi) {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (context) => Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(
                  backgroundColor: const Color(0xFF3498db),
                  radius: 16,
                  child: Text(
                    '${poi.index}',
                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 13),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    poi.name,
                    style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold),
                  ),
                ),
              ],
            ),
            if (poi.type.isNotEmpty) ...[
              const SizedBox(height: 8),
              Row(
                children: [
                  const Icon(Icons.category, size: 16, color: Colors.grey),
                  const SizedBox(width: 6),
                  Expanded(child: Text(poi.type, style: const TextStyle(color: Colors.grey))),
                ],
              ),
            ],
            if (poi.address.isNotEmpty) ...[
              const SizedBox(height: 6),
              Row(
                children: [
                  const Icon(Icons.location_on, size: 16, color: Colors.grey),
                  const SizedBox(width: 6),
                  Expanded(child: Text(poi.address, style: const TextStyle(color: Colors.grey))),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          widget.focusStopIndex != null && _pois.any((p) => p.index == widget.focusStopIndex)
              ? '${widget.tourTitle} — Stop ${widget.focusStopIndex}'
              : widget.tourTitle,
          overflow: TextOverflow.ellipsis,
        ),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: const Icon(Icons.my_location),
            tooltip: 'Center on my location',
            onPressed: () {
              if (_userLocation != null) {
                _mapController.move(_userLocation!, 15);
              }
            },
          ),
          IconButton(
            icon: const Icon(Icons.fit_screen),
            tooltip: 'Fit all stops',
            onPressed: () => _fitBounds(forceFitAll: true),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text(_error!, style: const TextStyle(color: Colors.grey, fontSize: 16)))
              : _buildMap(),
    );
  }

  Widget _buildMap() {
    final next = _focusPoi();
    return FlutterMap(
      mapController: _mapController,
      options: MapOptions(
        initialCenter: _pois.isNotEmpty ? _pois.first.coords : const LatLng(0, 0),
        initialZoom: 14,
      ),
      children: [
        TileLayer(
          urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
          userAgentPackageName: 'com.glikfamily.audioura',
        ),
        // Arrow line from user to nearest POI
        if (_userLocation != null && next != null)
          PolylineLayer(
            polylines: [
              Polyline(
                points: [_userLocation!, next.coords],
                color: Colors.blue.withOpacity(0.6),
                strokeWidth: 2.5,
                isDotted: true,
              ),
            ],
          ),
        // POI numbered markers
        MarkerLayer(
          markers: [
            ..._pois.map((poi) => Marker(
              point: poi.coords,
              width: 36,
              height: 36,
              child: GestureDetector(
                onTap: () => _showPoiDetails(poi),
                child: Container(
                  decoration: BoxDecoration(
                    color: poi.index == next?.index ? Colors.orange : const Color(0xFF3498db), // NF7: index compare
                    shape: BoxShape.circle,
                    border: Border.all(color: Colors.white, width: 2),
                    boxShadow: const [BoxShadow(color: Colors.black26, blurRadius: 4)],
                  ),
                  child: Center(
                    child: Text(
                      '${poi.index}',
                      style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.bold,
                        fontSize: 13,
                      ),
                    ),
                  ),
                ),
              ),
            )),
            // User location blue dot
            if (_userLocation != null)
              Marker(
                point: _userLocation!,
                width: 20,
                height: 20,
                child: Container(
                  decoration: BoxDecoration(
                    color: Colors.blue,
                    shape: BoxShape.circle,
                    border: Border.all(color: Colors.white, width: 2.5),
                    boxShadow: const [BoxShadow(color: Colors.black26, blurRadius: 4)],
                  ),
                ),
              ),
          ],
        ),
      ],
    );
  }
}
