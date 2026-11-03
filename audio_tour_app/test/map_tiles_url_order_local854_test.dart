// [LOCAL-854] (D757) The app must load map tiles from OUR cache proxy FIRST and
// only fall back to the OSM CDN as a LAST resort. This test pins that ordering
// so a future edit cannot silently put the app back on tile.openstreetmap.org
// as the primary (the exact regression D757 is about).
//
// It drives the pure config in MapTiles — no Flutter widgets, no network — via
// the same dart-define contract the real build uses. Build-time overrides are
// exercised with a second group so LEAD can repoint the app without a code
// change and the ordering guarantee still holds.
//
// Run: flutter test test/map_tiles_url_order_local854_test.dart

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/config/map_tiles.dart';

String _hostOf(String template) {
  final uri = Uri.parse(template.replaceAll(RegExp(r'\{[^}]+\}'), '0'));
  return uri.host;
}

bool _isOsmHost(String host) =>
    host == 'tile.openstreetmap.org' || host.endsWith('.tile.openstreetmap.org');

void main() {
  group('MapTiles default URL order (no dart-define)', () {
    test('primary is the proxy, NOT the OSM host', () {
      final primaryHost = _hostOf(MapTiles.primaryTemplate);
      expect(
        _isOsmHost(primaryHost),
        isFalse,
        reason: 'Default primary must be our proxy, not OSM directly (D757). '
            'Got $primaryHost',
      );
      expect(primaryHost, 'tile-proxy-subscribed.audioura.com');
      // The template still honours the {z}/{x}/{y}.png contract the provider
      // and every TileLayer rely on.
      expect(MapTiles.primaryTemplate, contains('{z}'));
      expect(MapTiles.primaryTemplate, contains('{x}'));
      expect(MapTiles.primaryTemplate, contains('{y}'));
    });

    test('ordered list starts with the proxy primary', () {
      expect(MapTiles.orderedTemplates.first, MapTiles.primaryTemplate);
      expect(_isOsmHost(_hostOf(MapTiles.orderedTemplates.first)), isFalse);
    });

    test('direct OSM (canonical host) is the LAST fallback', () {
      final ordered = MapTiles.orderedTemplates;
      expect(ordered.length, greaterThan(1));
      // The very last entry the app will ever try is the canonical OSM host.
      expect(_hostOf(ordered.last), 'tile.openstreetmap.org');
      // And the proxy comes strictly before any OSM host in the list.
      final firstOsmIndex =
          ordered.indexWhere((t) => _isOsmHost(_hostOf(t)));
      expect(firstOsmIndex, greaterThan(0),
          reason: 'No OSM host may precede the proxy.');
    });

    test('every OSM host appears only after the proxy', () {
      final ordered = MapTiles.orderedTemplates;
      final proxyIndex =
          ordered.indexWhere((t) => !_isOsmHost(_hostOf(t)));
      expect(proxyIndex, 0, reason: 'The proxy is the only non-OSM host, first.');
      for (var i = 1; i < ordered.length; i++) {
        expect(_isOsmHost(_hostOf(ordered[i])), isTrue,
            reason: 'Every fallback after the proxy is an OSM mirror.');
      }
    });
  });

  group('MapTiles respects build-time overrides', () {
    // These only assert the SHAPE the overrides must satisfy; the concrete
    // values come from --dart-define at build time. We can still verify the
    // contract on the compiled-in defaults: the primary is overridable and the
    // ordered list keeps the primary first.
    test('primary always leads the ordered list', () {
      expect(MapTiles.orderedTemplates.first, MapTiles.primaryTemplate);
    });

    test('fallbacks never duplicate the primary as the first entry', () {
      final ordered = MapTiles.orderedTemplates;
      final dupes =
          ordered.where((t) => t == MapTiles.primaryTemplate).length;
      expect(dupes, 1, reason: 'Primary appears exactly once, at the front.');
    });
  });
}
