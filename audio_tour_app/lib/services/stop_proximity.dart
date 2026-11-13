// [LOCAL-908] Arrival detection for "On the way" (pure Dart, no plugin).
//
// The player feeds GPS fixes in; the detector says "arrived at stop N" ONCE per
// approach. A stop re-arms only after the listener has moved out past
// [exitMetres], so GPS jitter at the edge cannot fire it repeatedly.
library stop_proximity;

import 'dart:io';
import 'dart:math' as math;

class StopCoord {
  final int index; // 0-based stop index
  final double lat;
  final double lng;
  const StopCoord(this.index, this.lat, this.lng);
}

double haversineMetres(double lat1, double lng1, double lat2, double lng2) {
  const r = 6371000.0;
  double rad(double d) => d * math.pi / 180.0;
  final dLat = rad(lat2 - lat1);
  final dLng = rad(lng2 - lng1);
  final a = math.pow(math.sin(dLat / 2), 2) +
      math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.pow(math.sin(dLng / 2), 2);
  return 2 * r * math.asin(math.min(1.0, math.sqrt(a.toDouble())));
}

class StopProximityDetector {
  final List<StopCoord> stops;
  final double arriveMetres;
  final double exitMetres;
  final Set<int> _inside = <int>{};

  StopProximityDetector(
    this.stops, {
    this.arriveMetres = 75,
    double? exitMetres,
  }) : exitMetres = exitMetres ?? arriveMetres * 1.6;

  /// Feed one fix. Returns the 0-based indices of stops newly arrived at
  /// (nearest first). Usually empty.
  List<int> onPosition(double lat, double lng) {
    final arrived = <MapEntry<int, double>>[];
    for (final s in stops) {
      final d = haversineMetres(lat, lng, s.lat, s.lng);
      if (_inside.contains(s.index)) {
        if (d > exitMetres) _inside.remove(s.index);
      } else if (d <= arriveMetres) {
        _inside.add(s.index);
        arrived.add(MapEntry(s.index, d));
      }
    }
    arrived.sort((a, b) => a.value.compareTo(b.value));
    return arrived.map((e) => e.key).toList();
  }

  void reset() => _inside.clear();

  /// Reads `Coordinates: lat, lng` from the tour's audio_N.txt files (N is
  /// 1-based, the format TourMapScreen and NavigationService already read).
  static Future<List<StopCoord>> loadFromTourDir(String tourPath,
      {int max = 60}) async {
    final out = <StopCoord>[];
    final re = RegExp(r'Coordinates:\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)');
    for (var n = 1; n <= max; n++) {
      final f = File('$tourPath/audio_$n.txt');
      try {
        if (!await f.exists()) {
          if (n > 1) break;
          continue;
        }
        final m = re.firstMatch(await f.readAsString());
        if (m == null) continue;
        final lat = double.tryParse(m.group(1)!);
        final lng = double.tryParse(m.group(2)!);
        if (lat != null && lng != null) out.add(StopCoord(n - 1, lat, lng));
      } catch (_) {}
    }
    return out;
  }
}
