// LOCAL-868 (D762, app side) — "Paste a list of places".
//
// Pure helpers (no widgets, no I/O) for the paste → free preview → reviewed
// list → generate flow, so every rule is unit-testable:
//
//   * the `POST /preview-stops {text, city}` request body;
//   * parsing the preview response into [PreviewStop]s (resolved or not);
//   * delete / drag-reorder on the previewed list;
//   * turning the reviewed list into the `user_stops` the generate request
//     carries — OBJECTS `{name, lat, lng, resolved_name}` (the LOCAL-867
//     contract), one per stop, in the listener's order.
//
// The reviewed stops are stored in the SAME stop maps the "I will name the
// stops" loop uses (`user_stops.dart`), with a few extra keys (lat/lng/…), so
// the existing review screen, `isStopListReady`, retry snapshot and generate
// flow all keep working unchanged (D564: one mechanism, never two).

import 'user_stops.dart';

/// Server cap on `text` (generate_tour_text_service.py `/preview-stops`).
const int kMaxPasteChars = 8000;

/// One stop of a previewed pasted list.
class PreviewStop {
  /// What the listener typed (e.g. "Cathedral").
  final String typedName;

  /// The display title the server settled on (curated alias title, else the
  /// typed name). This is what a generated stop is called.
  final String stopName;

  /// The authority's own name for the place ("Notre-Dame Cathedral Basilica of
  /// Saigon"), when resolved.
  final String? resolvedName;

  /// The authority's matched name (LOCAL-862 research alias), when resolved.
  final String? matchedName;

  final double? lat;
  final double? lng;

  /// `high` | `medium` | `low` | null when unresolved.
  final String? confidence;
  final String? source;
  final String? note;
  final String? reason;
  final bool unresolved;

  const PreviewStop({
    required this.typedName,
    required this.stopName,
    this.resolvedName,
    this.matchedName,
    this.lat,
    this.lng,
    this.confidence,
    this.source,
    this.note,
    this.reason,
    this.unresolved = false,
  });

  /// True when this stop can be drawn as a map pin.
  bool get hasPin => !unresolved && lat != null && lng != null;

  /// Parse one entry of the `/preview-stops` response `stops` array. Returns
  /// null for an entry with no usable name.
  static PreviewStop? fromJson(Map<String, dynamic> j) {
    String? s(Object? v) {
      final t = v?.toString().trim();
      return (t == null || t.isEmpty || t == 'null') ? null : t;
    }

    double? d(Object? v) =>
        v is num ? v.toDouble() : double.tryParse(v?.toString() ?? '');

    final typed = s(j['name']) ?? s(j['stop_name']);
    if (typed == null) return null;
    final lat = d(j['lat']);
    final lng = d(j['lng']);
    final unresolved =
        j['unresolved'] == true || lat == null || lng == null;
    return PreviewStop(
      typedName: typed,
      stopName: s(j['stop_name']) ?? typed,
      resolvedName: s(j['resolved_name']),
      matchedName: s(j['matched_name']),
      lat: unresolved ? null : lat,
      lng: unresolved ? null : lng,
      confidence: unresolved ? null : s(j['confidence']),
      source: s(j['source']),
      note: s(j['note']),
      reason: s(j['reason']),
      unresolved: unresolved,
    );
  }

  /// The user-stop map (same shape as `buildUserStop`) with the pin carried in
  /// extra keys. `text` is the stop's name — the rest of the app reads that.
  Map<String, dynamic> toUserStop({required int existingCount}) {
    final m = buildUserStop(stopName, existingCount: existingCount);
    m['pasted'] = true;
    m['typed_name'] = typedName;
    if (hasPin) {
      m['lat'] = lat;
      m['lng'] = lng;
    }
    if (resolvedName != null) m['resolved_name'] = resolvedName;
    if (matchedName != null) m['matched_name'] = matchedName;
    if (confidence != null) m['confidence'] = confidence;
    if (note != null) m['note'] = note;
    return m;
  }
}

/// The parsed `/preview-stops` response.
class PreviewResult {
  final String cityName;
  final List<PreviewStop> stops;
  const PreviewResult({required this.cityName, required this.stops});

  int get unresolvedCount => stops.where((s) => !s.hasPin).length;
}

/// The request body for `POST /preview-stops`.
Map<String, dynamic> buildPreviewBody(String text, String city) => {
      'text': text.trim(),
      'city': city.trim(),
    };

/// Why a paste cannot be previewed yet, or null when it can. Mirrors the
/// server's 400s so the listener gets the message before any request.
String? validatePasteInput(String text, String city) {
  if (text.trim().isEmpty) return 'Paste or type your list of places first.';
  if (text.length > kMaxPasteChars) {
    return 'That list is too long (max $kMaxPasteChars characters).';
  }
  return null;
}

/// Parse a decoded `/preview-stops` body. Throws [FormatException] on a body
/// that is not an ok preview with at least one stop.
PreviewResult parsePreviewResponse(Map<String, dynamic> body) {
  if (body['ok'] == false) {
    throw FormatException('${body['error'] ?? 'preview failed'}');
  }
  final raw = body['stops'];
  if (raw is! List) throw const FormatException('no stops in the preview');
  final stops = <PreviewStop>[];
  for (final e in raw) {
    if (e is Map) {
      final p = PreviewStop.fromJson(Map<String, dynamic>.from(e));
      if (p != null) stops.add(p);
    }
  }
  if (stops.isEmpty) throw const FormatException('no stops found in your list');
  final city = body['city'];
  final cityName = city is Map ? '${city['name'] ?? ''}' : '';
  return PreviewResult(cityName: cityName, stops: stops);
}

/// Remove the previewed stop at [index] (out of range → unchanged).
List<PreviewStop> removePreviewStopAt(List<PreviewStop> stops, int index) {
  if (index < 0 || index >= stops.length) return stops;
  stops.removeAt(index);
  return stops;
}

/// Move a previewed stop, with the index adjustment Flutter's
/// `ReorderableListView.onReorder` needs.
List<PreviewStop> reorderPreviewStops(
    List<PreviewStop> stops, int oldIndex, int newIndex) {
  if (oldIndex < 0 || oldIndex >= stops.length) return stops;
  var target = newIndex;
  if (oldIndex < target) target -= 1;
  if (target < 0) target = 0;
  if (target > stops.length - 1) target = stops.length - 1;
  stops.insert(target, stops.removeAt(oldIndex));
  return stops;
}

/// The reviewed list as numbered user-stop maps (what `_userStops` holds).
List<Map<String, dynamic>> previewStopsToUserStops(List<PreviewStop> stops) {
  final out = <Map<String, dynamic>>[];
  for (final p in stops) {
    out.add(p.toUserStop(existingCount: out.length));
  }
  renumberStops(out);
  return out;
}

/// What the generate request sends as `user_stops`.
///
/// For a list that came from the paste preview this is a list of OBJECTS
/// `{name, lat, lng, resolved_name}` (+ `matched_name` when known) in order —
/// the LOCAL-867 contract. An unresolved stop is `{name}` only: the server finds
/// it by name. A list built by hand (no `pasted` stop) is the plain string list
/// it always was, so the default request body is byte-for-byte unchanged.
List<Object> userStopsForGeneration(List<Map<String, dynamic>> stops) {
  final anyPasted = stops.any((s) => s['pasted'] == true);
  if (!anyPasted) return stopTitlesForGeneration(stops);
  return [
    for (final s in stops)
      <String, dynamic>{
        'name': (s['text'] as String? ?? '').trim(),
        if (s['lat'] is num && s['lng'] is num) ...{
          'lat': (s['lat'] as num).toDouble(),
          'lng': (s['lng'] as num).toDouble(),
        },
        if (s['resolved_name'] is String) 'resolved_name': s['resolved_name'],
        if (s['matched_name'] is String) 'matched_name': s['matched_name'],
      },
  ];
}

/// A short label for the confidence chip.
String confidenceLabel(PreviewStop s) {
  if (!s.hasPin) return 'no pin';
  switch (s.confidence) {
    case 'high':
      return 'high confidence';
    case 'medium':
      return 'medium confidence';
    case 'low':
      return 'low confidence';
    default:
      return 'pinned';
  }
}

/// Best-effort city for the paste box from the Create Tour request text
/// (`"walking tour for Ho Chi Minh City"` → `"Ho Chi Minh City"`). Same rule
/// the request parser uses for the location: the text after "for", else all of
/// it. Empty for blank input.
String cityFromRequestText(String request) {
  final t = request.trim();
  if (t.isEmpty) return '';
  final m = RegExp(r'\bfor\s+(.+)', caseSensitive: false).firstMatch(t);
  return (m != null ? m.group(1)! : t).trim();
}

/// City name from a Nominatim `reverse?format=json` body (used to pre-fill the
/// city from the current location). Null when nothing city-like is present.
String? cityFromNominatimReverse(Map<String, dynamic> body) {
  final a = body['address'];
  if (a is! Map) return null;
  for (final k in const [
    'city',
    'town',
    'municipality',
    'village',
    'county',
    'state',
  ]) {
    final v = a[k]?.toString().trim();
    if (v != null && v.isNotEmpty) return v;
  }
  return null;
}
