// [LOCAL-471] Proof that the map's audio_N.txt parser still reads a file that
// carries the new `Coordinate-Confidence:` line.
//
// This reifies tour_map_screen.dart's _parsePoi EXACTLY — same regexes, same
// line[0]-is-the-name rule — with no Flutter imports, so it runs under a plain
// `dart run` without `flutter pub get` (which would hit the network and is
// avoided while Michael is generating tours locally). The Python suite asserts
// these regex literals are still the ones present in the .dart source
// (test_the_app_regexes_are_still_the_ones_we_ported), so this copy cannot
// silently drift from the app.
//
// Run: dart run tests/dart/local471_map_parser_check.dart

class TourPoi {
  final int index;
  final String name;
  final String type;
  final String address;
  final double lat;
  final double lng;
  TourPoi(this.index, this.name, this.type, this.address, this.lat, this.lng);
}

// Verbatim from tour_map_screen.dart::_parsePoi.
TourPoi? parsePoi(int index, String content) {
  final coordMatch =
      RegExp(r'Coordinates:\s*([-\d.]+)\s*,\s*([-\d.]+)').firstMatch(content);
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

  return TourPoi(index, name, type, address, lat, lng);
}

void main() {
  // A stop exactly as the emitter now writes it: the confidence line sits
  // between Coordinates: and Type/Specialty:.
  const withConfidence = 'Musee Matisse\n'
      'Address: 164 Avenue des Arenes, 06000 Nice\n'
      'Coordinates: 43.719450, 7.275970\n'
      'Coordinate-Confidence: high\n'
      'Type/Specialty: Museum\n'
      'The narration the visitor hears.';

  var failures = 0;
  void check(String label, bool ok) {
    print('${ok ? "PASS" : "FAIL"}: $label');
    if (!ok) failures++;
  }

  final poi = parsePoi(1, withConfidence);
  check('parser returns a POI for a file with the confidence line', poi != null);
  if (poi != null) {
    check('name is still line 0 (not the confidence line)', poi.name == 'Musee Matisse');
    check('latitude parsed correctly', (poi.lat - 43.71945).abs() < 1e-5);
    check('longitude parsed correctly', (poi.lng - 7.27597).abs() < 1e-5);
    check('Type/Specialty still parsed', poi.type == 'Museum');
    check('Address still parsed', poi.address.startsWith('164 Avenue'));
  }

  // A low-confidence stop must still plot (the pin is drawn; only its style
  // differs — and that styling is Mobile-Kiro's job, not this task's).
  const lowConf = 'Villa Leopolda\n'
      'Coordinates: 43.710900, 7.278400\n'
      'Coordinate-Confidence: low\n';
  final poi2 = parsePoi(2, lowConf);
  check('a low-confidence stop still parses and plots', poi2 != null);

  // A file WITHOUT the line (legacy tour) still parses — additive, not required.
  const legacy = 'Old Stop\nCoordinates: 43.7, 7.2\nType/Specialty: Walk\n';
  check('legacy file with no confidence line still parses', parsePoi(3, legacy) != null);

  if (failures == 0) {
    print('\nALL PARSER CHECKS PASSED');
  } else {
    print('\n$failures CHECK(S) FAILED');
    // Non-zero exit so CI / a human notices.
    throw StateError('$failures parser check(s) failed');
  }
}
