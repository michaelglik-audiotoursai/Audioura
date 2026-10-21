// [LOCAL-730 / D694, Privacy "Location and places"] Where the Treats screen is
// allowed to look for the points it asks the server about.
//
// The Privacy Policy (subscribed @ 936f1e97, legal/PRIVACY.md) now promises:
//   * Treats are chosen from the PLACES IN THE USER'S TOURS, or a place they
//     typed on Home;
//   * NEVER from the phone's location;
//   * the phone-location option may come later only as an opt-in that is off by
//     default.
//
// This resolver is the single source of truth for that promise. It deliberately
// does NOT import `geolocator` and has no path to the device GPS, so the Treats
// screen cannot regress to sending the phone's position (the "Red test" in
// test/treats_source_resolver_test.dart re-introduces a GPS fallback and proves
// the zero-Geolocator guarantee breaks). It is pure Dart + injectable readers so
// it is unit-testable with no WebView, no live server and no real files.
//
// Source order (a) > (b) > (c) > (d), first non-empty wins:
//   (a) the stops of the tour currently open or playing, if any;
//   (b) the stops of the downloaded tours on the Listen page, de-duplicated;
//   (c) the place last typed or searched on Home (custom_location_lat/lng);
//   (d) otherwise NOTHING — no request at all, and a friendly empty state.

import 'dart:convert';
import 'dart:io';

import 'package:shared_preferences/shared_preferences.dart';

/// A single geographic point (a tour stop or a typed Home place) the Treats
/// screen may ask the server about. Never the phone's GPS position.
class TreatPoint {
  final double lat;
  final double lng;
  const TreatPoint(this.lat, this.lng);

  /// Round to 2 decimals for a de-dup KEY and for any logging — ~1.1 km of
  /// precision, which is all the server needs and all we ever want to record
  /// (the Privacy promise: rounded coordinates or none).
  String get dedupKey =>
      '${lat.toStringAsFixed(2)},${lng.toStringAsFixed(2)}';

  Map<String, double> toJson() => {'lat': lat, 'lng': lng};

  @override
  bool operator ==(Object other) =>
      other is TreatPoint && other.lat == lat && other.lng == lng;

  @override
  int get hashCode => Object.hash(lat, lng);

  @override
  String toString() => 'TreatPoint($lat, $lng)';
}

/// Which source the points came from — used by the screen for messaging/tests.
enum TreatsSource { currentTour, downloadedTours, homePlace, none }

/// The resolved set of points plus which source produced them.
class TreatsSourceResult {
  final TreatsSource source;
  final List<TreatPoint> points;
  const TreatsSourceResult(this.source, this.points);

  bool get isEmpty => points.isEmpty;

  static const TreatsSourceResult empty =
      TreatsSourceResult(TreatsSource.none, <TreatPoint>[]);
}

/// Resolves the Treats points from the tour places, in the policy's order.
///
/// All I/O is injected so the order logic is testable with no files and no
/// SharedPreferences plugin. The production constructor wires the real readers.
class TreatsSourceResolver {
  /// The most server points one Treats request may carry (D694 / server cap).
  static const int maxPoints = 10;

  /// Returns the path of the tour currently open or playing, or null.
  final Future<String?> Function() currentTourPath;

  /// Returns the paths of the downloaded tours on the Listen page, nearest
  /// first by list order (most recent download last — we read them all and
  /// de-dup, so exact order only decides which duplicate is kept).
  final Future<List<String>> Function() downloadedTourPaths;

  /// Returns the stop coordinates for a tour directory [path], in stop order.
  /// Empty when the tour has no readable stop coordinates.
  final Future<List<TreatPoint>> Function(String path) stopsForTour;

  /// Returns the place last typed/searched on Home, or null when none is set.
  final Future<TreatPoint?> Function() homePlace;

  const TreatsSourceResolver({
    required this.currentTourPath,
    required this.downloadedTourPaths,
    required this.stopsForTour,
    required this.homePlace,
  });

  /// The production resolver, reading SharedPreferences + the tour files.
  factory TreatsSourceResolver.production() => const TreatsSourceResolver(
        currentTourPath: _readCurrentTourPath,
        downloadedTourPaths: _readDownloadedTourPaths,
        stopsForTour: readStopCoordinates,
        homePlace: _readHomePlace,
      );

  /// Resolve the points to ask the server about, in the policy's order.
  /// Never reads GPS. Returns [TreatsSourceResult.empty] for source (d).
  Future<TreatsSourceResult> resolve() async {
    // (a) the tour currently open or playing.
    final currentPath = await currentTourPath();
    if (currentPath != null && currentPath.isNotEmpty) {
      final pts = dedupe(await stopsForTour(currentPath));
      if (pts.isNotEmpty) {
        return TreatsSourceResult(TreatsSource.currentTour, _cap(pts));
      }
    }

    // (b) the downloaded tours on the Listen page, de-duplicated across tours.
    final downloaded = await downloadedTourPaths();
    final collected = <TreatPoint>[];
    for (final path in downloaded) {
      if (path.isEmpty) continue;
      collected.addAll(await stopsForTour(path));
    }
    final dedupedDownloaded = dedupe(collected);
    if (dedupedDownloaded.isNotEmpty) {
      return TreatsSourceResult(
          TreatsSource.downloadedTours, _cap(dedupedDownloaded));
    }

    // (c) the place last typed or searched on Home.
    final home = await homePlace();
    if (home != null) {
      return TreatsSourceResult(TreatsSource.homePlace, [home]);
    }

    // (d) nothing — the screen shows the friendly empty state, no request.
    return TreatsSourceResult.empty;
  }

  /// De-duplicate points by their 2-decimal key, preserving first-seen order.
  static List<TreatPoint> dedupe(List<TreatPoint> points) {
    final seen = <String>{};
    final out = <TreatPoint>[];
    for (final p in points) {
      if (seen.add(p.dedupKey)) out.add(p);
    }
    return out;
  }

  List<TreatPoint> _cap(List<TreatPoint> points) =>
      points.length <= maxPoints ? points : points.sublist(0, maxPoints);

  // --- Production readers (not touched by the order unit tests) ------------

  static Future<String?> _readCurrentTourPath() async {
    final prefs = await SharedPreferences.getInstance();
    final p = prefs.getString('current_tour_path');
    return (p != null && p.trim().isNotEmpty) ? p : null;
  }

  static Future<List<String>> _readDownloadedTourPaths() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getStringList('saved_tours') ?? const [];
    final paths = <String>[];
    for (final s in raw) {
      try {
        final m = json.decode(s);
        if (m is Map && m['path'] is String && (m['path'] as String).isNotEmpty) {
          paths.add(m['path'] as String);
        }
      } catch (_) {
        // skip an unparseable record
      }
    }
    return paths;
  }

  static Future<TreatPoint?> _readHomePlace() async {
    final prefs = await SharedPreferences.getInstance();
    final lat = prefs.getDouble('custom_location_lat');
    final lng = prefs.getDouble('custom_location_lng');
    if (lat == null || lng == null) return null;
    return TreatPoint(lat, lng);
  }

  /// Read the stop coordinates for a downloaded tour directory [path].
  ///
  /// Stop coordinates live in `audio_1.txt`, `audio_2.txt`, … inside the tour
  /// directory, one line `Coordinates: <lat>, <lng>` — exactly the format the
  /// map screen already parses (tour_map_screen.dart `_parsePoi`). We read them
  /// in stop order and stop at the first missing file. Never throws — a missing
  /// directory or unreadable file yields an empty list (⇒ falls through to the
  /// next source).
  static Future<List<TreatPoint>> readStopCoordinates(String path) async {
    final points = <TreatPoint>[];
    try {
      var i = 1;
      while (true) {
        final file = File('$path/audio_$i.txt');
        if (!await file.exists()) break;
        try {
          final pt = parseCoordinates(await file.readAsString());
          if (pt != null) points.add(pt);
        } catch (_) {
          // skip a single unreadable/odd stop file, keep going
        }
        i++;
      }
    } catch (_) {
      // directory missing / IO error ⇒ no points from this tour
    }
    return points;
  }

  /// Parse a `Coordinates: <lat>, <lng>` line out of a stop file's text.
  /// Returns null when the line is absent or the numbers do not parse. Pure, so
  /// it is unit-testable directly.
  static TreatPoint? parseCoordinates(String content) {
    final m = RegExp(r'Coordinates:\s*([-\d.]+)\s*,\s*([-\d.]+)')
        .firstMatch(content);
    if (m == null) return null;
    final lat = double.tryParse(m.group(1)!);
    final lng = double.tryParse(m.group(2)!);
    if (lat == null || lng == null) return null;
    return TreatPoint(lat, lng);
  }
}
