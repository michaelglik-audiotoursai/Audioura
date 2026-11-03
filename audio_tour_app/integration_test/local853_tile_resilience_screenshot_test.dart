// [LOCAL-853] Live screenshot run on the iOS simulator proving the Home map's
// tile resilience: with the tile host BLOCKED (the SocketException /
// "Failed host lookup" Michael's iPhone hit from Vietnam), the map still shows
// previously-cached tiles plus the pins and NEVER blocks Home; with no cache it
// shows the grey map plus pins (still never blocks); then with the host
// UNBLOCKED the tiles recover.
//
// It renders the REAL production path — a FlutterMap with FirstLayoutTileLayer
// wrapping a TileLayer whose tileProvider is the REAL ResilientTileProvider —
// and only swaps in (a) an injected http client that simulates the blocked /
// unblocked host and (b) an in-memory TileCache the test can pre-seed. No
// network and no backend are touched, so the run is deterministic and $0 (no
// tours, per the task budget) and never points at :5002.
//
// Usage:
//   flutter drive \
//     --driver=test_driver/local853_screenshot_driver.dart \
//     --target=integration_test/local853_tile_resilience_screenshot_test.dart \
//     -d <booted-simulator-id>
library;

import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:integration_test/integration_test.dart';
import 'package:latlong2/latlong.dart';

import 'package:audio_tour_app_dev/config/map_tiles.dart';
import 'package:audio_tour_app_dev/services/resilient_tile_provider.dart';
import 'package:audio_tour_app_dev/widgets/first_layout_tile_layer.dart';

/// In-memory cache the test can pre-seed with a visible tile.
class _SeedCache extends TileCache {
  final Map<String, Uint8List> store = {};
  @override
  Future<Uint8List?> read(String url) async => store[url];
  @override
  Future<void> write(String url, Uint8List bytes) async => store[url] = bytes;
  @override
  Future<void> clear() async => store.clear();
}

/// A client that simulates a BLOCKED tile host (DNS/connect failure), exactly
/// like the SocketException Michael's iPhone logged.
class _BlockedClient extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    throw const SocketException(
        "Failed host lookup: 'tile.openstreetmap.org'");
  }
}

/// A client that serves a solid-colour PNG for every tile (host UNBLOCKED).
class _ColorClient extends http.BaseClient {
  _ColorClient(this.bytes);
  final Uint8List bytes;
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    return http.StreamedResponse(Stream.value(bytes), 200);
  }
}

/// Build a solid-colour 256×256 PNG so cached/live tiles are visibly coloured
/// (distinguishable from the grey no-tile background).
Future<Uint8List> _solidPng(Color color) async {
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder);
  canvas.drawRect(
    const Rect.fromLTWH(0, 0, 256, 256),
    Paint()..color = color,
  );
  final img = await recorder.endRecording().toImage(256, 256);
  final data = await img.toByteData(format: ui.ImageByteFormat.png);
  return data!.buffer.asUint8List();
}

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  Future<void> settle(WidgetTester tester) async {
    for (var i = 0; i < 10; i++) {
      await tester.pump(const Duration(milliseconds: 200));
    }
  }

  Future<void> shot(WidgetTester tester, String name) async {
    await settle(tester);
    await binding.convertFlutterSurfaceToImage();
    await settle(tester);
    await binding.takeScreenshot(name);
  }

  Widget buildMap({
    required http.Client client,
    required TileCache cache,
    required MapController controller,
    required String namespace,
  }) {
    return MaterialApp(
      home: Scaffold(
        appBar: AppBar(title: const Text('LOCAL-853 Home map tiles')),
        body: FlutterMap(
          mapController: controller,
          options: const MapOptions(
            initialCenter: LatLng(42.3601, -71.0589), // Boston, like Home
            initialZoom: 13,
          ),
          children: [
            // The REAL Home wrapper + provider. Only the http client and cache
            // are injected for the test.
            FirstLayoutTileLayer(
              mapController: controller,
              builder: (reset) => TileLayer(
                urlTemplate: MapTiles.primaryTemplate,
                userAgentPackageName: MapTiles.userAgentPackageName,
                tileProvider: ResilientTileProvider(
                  httpClient: client,
                  cache: cache,
                  debugKeyNamespace: namespace,
                ),
                reset: reset,
              ),
            ),
            // Pins: these draw independent of the tile grid, so they stay
            // visible even when every tile fails — the "map never blocks Home".
            MarkerLayer(
              markers: const [
                Marker(
                  point: LatLng(42.3601, -71.0589),
                  width: 36,
                  height: 36,
                  child: Icon(Icons.location_pin,
                      color: Colors.red, size: 36),
                ),
                Marker(
                  point: LatLng(42.3651, -71.0609),
                  width: 36,
                  height: 36,
                  child: Icon(Icons.location_pin,
                      color: Colors.deepPurple, size: 36),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  // Seed a generous z12–13 Boston grid so the initial viewport is covered.
  void seedBoston(_SeedCache cache, Uint8List tile) {
    for (var z = 12; z <= 13; z++) {
      for (var x = 2470; x <= 2530; x++) {
        for (var y = 3000; y <= 3060; y++) {
          final url = MapTiles.primaryTemplate
              .replaceAll('{z}', '$z')
              .replaceAll('{x}', '$x')
              .replaceAll('{y}', '$y');
          cache.store[url] = tile;
        }
      }
    }
  }

  // 1) BLOCKED host, cache PRE-SEEDED with green tiles: the map shows the
  //    cached green tiles plus the pins — Home is usable offline/flaky.
  testWidgets('01 blocked host serves CACHED tiles + pins (never blocks Home)',
      (tester) async {
    final green = await _solidPng(const Color(0xFF66BB6A));
    final seeded = _SeedCache();
    seedBoston(seeded, green);
    await tester.pumpWidget(buildMap(
        client: _BlockedClient(),
        cache: seeded,
        controller: MapController(),
        namespace: 'state1'));
    await shot(tester, '01_blocked_host_cached_tiles_and_pins');
  });

  // 2) BLOCKED host, EMPTY cache: grey map + pins, still never blocks Home,
  //    never crashes (the provider returns the transparent tile).
  testWidgets('02 blocked host, no cache: grey map + pins, no crash',
      (tester) async {
    await tester.pumpWidget(buildMap(
        client: _BlockedClient(),
        cache: _SeedCache(),
        controller: MapController(),
        namespace: 'state2'));
    await shot(tester, '02_blocked_host_no_cache_grey_plus_pins');
  });

  // 3) UNBLOCKED host: tiles recover (blue tiles now load from the network).
  testWidgets('03 host unblocked: tiles recover from the network',
      (tester) async {
    final blue = await _solidPng(const Color(0xFF42A5F5));
    await tester.pumpWidget(buildMap(
        client: _ColorClient(blue),
        cache: _SeedCache(),
        controller: MapController(),
        namespace: 'state3'));
    await shot(tester, '03_host_unblocked_tiles_recover');
  });
}
