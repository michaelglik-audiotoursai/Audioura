import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';

import '../config/map_tiles.dart';
import '../services/preview_stops_service.dart';
import '../services/resilient_tile_provider.dart';
import '../utils/pasted_list.dart';

/// Keys the tests (and the generator screen) address.
const Key kPasteTextKey = Key('paste_list_text');
const Key kPasteCityKey = Key('paste_list_city');
const Key kPastePreviewButtonKey = Key('paste_list_preview');
const Key kPasteUseButtonKey = Key('paste_list_use');
const Key kPasteMapKey = Key('paste_list_map');

/// What the screen pops: the reviewed, ordered list and the city it was
/// resolved in.
class PastedListResult {
  final List<PreviewStop> stops;
  final String city;

  /// The text as pasted, so re-opening the box resumes where the listener was.
  final String text;
  const PastedListResult(
      {required this.stops, required this.city, required this.text});
}

/// Looks up the city for the current location (test seam).
typedef CityLocator = Future<String?> Function();

/// LOCAL-868 — "Paste a list of places".
///
/// Step 1: a multi-line box + a city field. Step 2 ("Preview", a FREE call to
/// `POST /preview-stops`): the stops in order as a list (typed name, resolved
/// name, confidence chip, note) AND a map with numbered pins on the tile proxy.
/// Unresolved stops say "no pin, we'll find it by name". Delete and drag
/// reorder both update the list and the pins. "Use these N stops" pops a
/// [PastedListResult]; nothing paid happens on this screen.
class PasteListScreen extends StatefulWidget {
  /// Text to pre-fill (a share-sheet hand-off, or a previous paste).
  final String? initialText;

  /// City to pre-fill (the Create Tour location). When empty the screen asks
  /// [locateCity], then the device location.
  final String? initialCity;

  /// Test seams.
  final PreviewPoster? previewPost;
  final CityLocator? locateCity;
  final bool showTiles;

  const PasteListScreen({
    super.key,
    this.initialText,
    this.initialCity,
    this.previewPost,
    this.locateCity,
    this.showTiles = true,
  });

  @override
  State<PasteListScreen> createState() => _PasteListScreenState();
}

enum _Step { paste, review }

class _PasteListScreenState extends State<PasteListScreen> {
  late final TextEditingController _text;
  late final TextEditingController _city;
  _Step _step = _Step.paste;
  bool _loading = false;
  String? _error;
  List<PreviewStop> _stops = [];
  // Bumped whenever the pin set changes so the map re-fits and redraws.
  int _mapEpoch = 0;

  @override
  void initState() {
    super.initState();
    _text = TextEditingController(text: widget.initialText ?? '');
    _city = TextEditingController(text: widget.initialCity ?? '');
    if (_city.text.trim().isEmpty) unawaited(_prefillCity());
  }

  @override
  void dispose() {
    _text.dispose();
    _city.dispose();
    super.dispose();
  }

  Future<void> _prefillCity() async {
    String? c;
    try {
      c = await (widget.locateCity ?? _cityFromDeviceLocation)();
    } catch (_) {
      c = null;
    }
    // Never overwrite something the listener already typed.
    if (!mounted || c == null || c.isEmpty || _city.text.trim().isNotEmpty) {
      return;
    }
    setState(() => _city.text = c!);
  }

  static Future<String?> _cityFromDeviceLocation() async {
    if (!await Geolocator.isLocationServiceEnabled()) return null;
    var perm = await Geolocator.checkPermission();
    if (perm == LocationPermission.denied ||
        perm == LocationPermission.deniedForever) {
      return null; // The paste box must not raise a permission prompt.
    }
    final pos = await Geolocator.getLastKnownPosition() ??
        await Geolocator.getCurrentPosition(
          locationSettings: const LocationSettings(
              accuracy: LocationAccuracy.low,
              timeLimit: Duration(seconds: 8)),
        );
    final r = await http.get(
      Uri.parse('https://nominatim.openstreetmap.org/reverse'
          '?format=json&zoom=10&addressdetails=1'
          '&lat=${pos.latitude}&lon=${pos.longitude}'),
      headers: {'User-Agent': MapTiles.userAgentPackageName},
    ).timeout(const Duration(seconds: 8));
    if (r.statusCode != 200) return null;
    final body = jsonDecode(utf8.decode(r.bodyBytes));
    return body is Map<String, dynamic> ? cityFromNominatimReverse(body) : null;
  }

  Future<void> _preview() async {
    final text = _text.text;
    final invalid = validatePasteInput(text, _city.text);
    if (invalid != null) {
      setState(() => _error = invalid);
      return;
    }
    FocusScope.of(context).unfocus();
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final r = await PreviewStopsService.preview(text, _city.text,
          post: widget.previewPost);
      if (!mounted) return;
      setState(() {
        _stops = List<PreviewStop>.from(r.stops);
        _step = _Step.review;
        _mapEpoch++;
        _loading = false;
      });
    } on PreviewStopsException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  void _delete(int i) => setState(() {
        removePreviewStopAt(_stops, i);
        _mapEpoch++;
      });

  void _reorder(int o, int n) => setState(() {
        reorderPreviewStops(_stops, o, n);
        _mapEpoch++;
      });

  void _use() {
    if (_stops.isEmpty) return;
    Navigator.pop(context,
        PastedListResult(
            stops: List.of(_stops),
            city: _city.text.trim(),
            text: _text.text));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_step == _Step.paste
            ? 'Paste a list of places'
            : 'Review your stops'),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
      ),
      body: _step == _Step.paste ? _buildPaste() : _buildReview(),
    );
  }

  // ── Step 1: paste ─────────────────────────────────────────────────────────
  Widget _buildPaste() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Paste the places in the order you want to visit them. We will '
            'find each one on the map before you generate. The preview is free.',
            style: TextStyle(color: Colors.blue.shade800),
          ),
          const SizedBox(height: 12),
          TextField(
            key: kPasteTextKey,
            controller: _text,
            minLines: 6,
            maxLines: 12,
            keyboardType: TextInputType.multiline,
            maxLength: kMaxPasteChars,
            decoration: const InputDecoration(
              labelText: 'Your places',
              hintText: 'e.g. Cathedral → Post Office → Book Street',
              alignLabelWithHint: true,
              border: OutlineInputBorder(),
              filled: true,
              fillColor: Colors.white,
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            key: kPasteCityKey,
            controller: _city,
            textInputAction: TextInputAction.done,
            decoration: const InputDecoration(
              labelText: 'City',
              hintText: 'e.g. Ho Chi Minh City',
              prefixIcon: Icon(Icons.location_city),
              border: OutlineInputBorder(),
              filled: true,
              fillColor: Colors.white,
            ),
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: _ErrorRow(message: _error!),
            ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              key: kPastePreviewButtonKey,
              onPressed: _loading ? null : _preview,
              icon: _loading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.map_outlined),
              label: Text(_loading ? 'Finding your places…' : 'Preview'),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF2c3e50),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 14),
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ── Step 2: review ────────────────────────────────────────────────────────
  Widget _buildReview() {
    final unresolved = _stops.where((s) => !s.hasPin).length;
    return Column(
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(12),
          color: Colors.green.shade50,
          child: Text(
            _stops.isEmpty
                ? 'No stops left. Go back to edit your list.'
                : 'Your tour will visit these ${_stops.length} '
                    'stop${_stops.length == 1 ? '' : 's'}, in this order. '
                    'Drag to reorder, tap delete to remove.'
                    '${unresolved > 0 ? ' $unresolved without a pin will be found by name.' : ''}',
            style: TextStyle(
                color: Colors.green.shade900, fontWeight: FontWeight.w500),
          ),
        ),
        SizedBox(height: 220, child: _buildMap()),
        Expanded(
          child: ReorderableListView.builder(
            buildDefaultDragHandles: false,
            itemCount: _stops.length,
            onReorder: _reorder,
            itemBuilder: (context, i) => _stopTile(i),
          ),
        ),
        SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => setState(() => _step = _Step.paste),
                    child: const Text('Edit list'),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  flex: 2,
                  child: ElevatedButton(
                    key: kPasteUseButtonKey,
                    onPressed: _stops.isEmpty ? null : _use,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF27ae60),
                      foregroundColor: Colors.white,
                    ),
                    child: Text('Use these ${_stops.length} stops'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _stopTile(int i) {
    final s = _stops[i];
    final resolvedDiffers = s.resolvedName != null &&
        s.resolvedName!.toLowerCase() != s.stopName.toLowerCase();
    return Card(
      key: ValueKey('paste-stop-$i-${s.stopName}-${s.lat}-${s.lng}'),
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor:
              s.hasPin ? const Color(0xFF3498db) : Colors.grey.shade500,
          foregroundColor: Colors.white,
          child: Text('${i + 1}'),
        ),
        title: Text(s.stopName),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (s.typedName.toLowerCase() != s.stopName.toLowerCase())
              Text('You wrote: ${s.typedName}',
                  style: const TextStyle(fontSize: 12)),
            if (resolvedDiffers)
              Text('Found: ${s.resolvedName}',
                  style: const TextStyle(fontSize: 12)),
            if (s.note != null)
              Text(s.note!,
                  style: const TextStyle(
                      fontSize: 12, fontStyle: FontStyle.italic)),
            if (!s.hasPin)
              Text("no pin, we'll find it by name",
                  style: TextStyle(fontSize: 12, color: Colors.orange.shade900)),
            const SizedBox(height: 4),
            Chip(
              label: Text(confidenceLabel(s),
                  style: const TextStyle(fontSize: 11)),
              visualDensity: VisualDensity.compact,
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              backgroundColor: _chipColor(s),
            ),
          ],
        ),
        isThreeLine: true,
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            IconButton(
              icon: const Icon(Icons.delete, color: Colors.red),
              tooltip: 'Delete stop',
              onPressed: () => _delete(i),
            ),
            ReorderableDragStartListener(
              index: i,
              child: const Icon(Icons.drag_handle, color: Colors.grey),
            ),
          ],
        ),
      ),
    );
  }

  Color _chipColor(PreviewStop s) {
    if (!s.hasPin) return Colors.grey.shade300;
    switch (s.confidence) {
      case 'high':
        return Colors.green.shade100;
      case 'medium':
        return Colors.amber.shade100;
      default:
        return Colors.orange.shade100;
    }
  }

  Widget _buildMap() {
    final pins = <Marker>[];
    final points = <LatLng>[];
    for (var i = 0; i < _stops.length; i++) {
      final s = _stops[i];
      if (!s.hasPin) continue;
      final p = LatLng(s.lat!, s.lng!);
      points.add(p);
      pins.add(Marker(
        point: p,
        width: 30,
        height: 30,
        child: Container(
          key: ValueKey('paste-pin-${i + 1}'),
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: const Color(0xFF2c3e50),
            shape: BoxShape.circle,
            border: Border.all(color: Colors.white, width: 2),
          ),
          child: Text('${i + 1}',
              style: const TextStyle(
                  color: Colors.white,
                  fontSize: 12,
                  fontWeight: FontWeight.bold)),
        ),
      ));
    }
    if (points.isEmpty) {
      return Container(
        color: Colors.grey.shade200,
        alignment: Alignment.center,
        child: const Text('No pins to show. We will find each stop by name.'),
      );
    }
    final options = points.length == 1
        ? MapOptions(initialCenter: points.first, initialZoom: 15)
        : MapOptions(
            initialCameraFit: CameraFit.bounds(
              bounds: LatLngBounds.fromPoints(points),
              padding: const EdgeInsets.all(36),
              maxZoom: 17,
            ),
          );
    return FlutterMap(
      key: ValueKey('paste-map-$_mapEpoch'),
      options: options,
      children: [
        if (widget.showTiles)
          TileLayer(
            urlTemplate: MapTiles.primaryTemplate,
            userAgentPackageName: MapTiles.userAgentPackageName,
            tileProvider: ResilientTileProvider(),
          ),
        MarkerLayer(key: kPasteMapKey, markers: pins),
      ],
    );
  }
}

class _ErrorRow extends StatelessWidget {
  final String message;
  const _ErrorRow({required this.message});

  @override
  Widget build(BuildContext context) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.warning_amber_rounded,
              color: Colors.orange.shade800, size: 18),
          const SizedBox(width: 6),
          Expanded(
            child: Text(message,
                style: TextStyle(color: Colors.orange.shade900, fontSize: 13)),
          ),
        ],
      );
}
