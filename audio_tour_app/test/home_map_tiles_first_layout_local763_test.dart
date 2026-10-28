// [LOCAL-763] Red test for the Home-map "blank map until the first zoom" bug.
//
// Michael's retest (2026-10-25, both phones): the Home map opened with tour and
// location markers but NO map tiles; the OSM tiles appeared only after a pinch
// to zoom. The map now lives inside the LOCAL-761 IndexedStack + per-tab
// Navigator shell, where flutter_map 6.2.1's TileLayer can settle its layout
// size one frame AFTER it first computes its tile range — so it loads zero
// tiles and never refreshes until a user gesture fires a fresh MapEvent. The
// precise one-frame-late size settle is a flutter_map internal that only bites
// on a real surface (the widget-test LayoutBuilder gets constraints eagerly),
// so these tests pin the FIX's observable guarantees rather than trying to
// reproduce the device-only timing (that is verified on the emulator/simulator,
// see SUBMISSION_LOCAL-763.md):
//
//   1. A FirstLayoutTileLayer in the IndexedStack+Navigator shell requests OSM
//      tiles on the FIRST settled layout with NO gesture.
//   2. When the map's layout size changes, FirstLayoutTileLayer reloads the
//      tiles so the TileLayer draws against the new size. This is the mechanism
//      that heals the blank map once the deferred layout settles.
//
// [LOCAL-789B] The reload mechanism CHANGED: instead of rebuilding the TileLayer
// with a new key (which disposed its network client and cancelled every
// in-flight tile — the fully-grey-on-entry bug), FirstLayoutTileLayer now keeps
// ONE stable TileLayer and reloads it with an imperceptible camera NUDGE on the
// shared MapController (the pinch-equivalent). So the size-change test passes a
// MapController, and the heal is observed as new tile requests for the new
// viewport. See home_map_no_reset_storm_local789b_test.dart for the regression
// proof that nothing is disposed in a storm.
//
// The fake TileProvider COUNTS getImage calls (one per tile request) and
// returns a 1x1 transparent image, so the tests are deterministic and offline.

import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart' show SynchronousFuture;
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';

import 'package:audio_tour_app_dev/widgets/first_layout_tile_layer.dart';

/// A TileProvider that counts every tile request and returns a tiny
/// transparent image, so the map never touches the network. Each request gets a
/// UNIQUE image key so a reload is never hidden by the image cache.
class _CountingTileProvider extends TileProvider {
  int requests = 0;

  @override
  ImageProvider getImage(TileCoordinates coordinates, TileLayer options) {
    requests++;
    return _TransparentImageProvider(requests);
  }
}

/// A 1x1 fully-transparent ImageProvider so loaded tiles resolve instantly in
/// the test VM without any asset or network. [id] makes every key unique so a
/// reload really re-calls getImage (defeats the image cache).
class _TransparentImageProvider extends ImageProvider<_TransparentImageProvider> {
  _TransparentImageProvider(this.id);

  final int id;

  @override
  Future<_TransparentImageProvider> obtainKey(ImageConfiguration configuration) =>
      SynchronousFuture<_TransparentImageProvider>(this);

  @override
  ImageStreamCompleter loadImage(
      _TransparentImageProvider key, ImageDecoderCallback decode) {
    return OneFrameImageStreamCompleter(_oneByOne());
  }

  static Future<ImageInfo> _oneByOne() async {
    final recorder = ui.PictureRecorder();
    Canvas(recorder);
    final image = await recorder.endRecording().toImage(1, 1);
    return ImageInfo(image: image);
  }

  @override
  bool operator ==(Object other) =>
      other is _TransparentImageProvider && other.id == id;
  @override
  int get hashCode => id.hashCode;
}

/// Build a map inside an IndexedStack + Navigator whose real constraints arrive
/// only on a later frame — the LOCAL-761 tab shell in miniature. [useFix]
/// chooses between the plain TileLayer (bug) and FirstLayoutTileLayer (fix).
/// [controller], when given, is passed to both the FlutterMap and the
/// FirstLayoutTileLayer so the LOCAL-789B camera nudge can run.
Widget _mapInTabShell({
  required _CountingTileProvider provider,
  required bool useFix,
  MapController? controller,
}) {
  final map = FlutterMap(
    mapController: controller,
    options: const MapOptions(
      initialCenter: LatLng(42.3601, -71.0589),
      initialZoom: 13.0,
    ),
    children: [
      if (useFix)
        FirstLayoutTileLayer(
          mapController: controller,
          builder: (reset) => TileLayer(
            urlTemplate: 'https://tile.example/{z}/{x}/{y}.png',
            tileProvider: provider,
            reset: reset,
          ),
        )
      else
        TileLayer(
          urlTemplate: 'https://tile.example/{z}/{x}/{y}.png',
          tileProvider: provider,
        ),
    ],
  );

  // A Navigator inside an IndexedStack, exactly like main_screen.dart's tab
  // shell. The IndexedStack keeps the (single) child mounted.
  return MaterialApp(
    home: Scaffold(
      body: IndexedStack(
        index: 0,
        children: [
          Navigator(
            onGenerateRoute: (settings) => MaterialPageRoute(
              settings: settings,
              builder: (_) => map,
            ),
          ),
        ],
      ),
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
    '[LOCAL-763] FIX: map in IndexedStack+Navigator requests tiles on first '
    'layout with no gesture',
    (tester) async {
      final provider = _CountingTileProvider();
      final controller = MapController();
      await tester.pumpWidget(
          _mapInTabShell(provider: provider, useFix: true, controller: controller));
      // Let the post-frame size-settle + nudge run (no user gesture at all).
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));

      expect(
        provider.requests,
        greaterThan(0),
        reason:
            'The fixed map must request OSM tiles from the first settled layout '
            '— no pinch/zoom should be needed (Michael 2026-10-25).',
      );
    },
  );

  testWidgets(
    '[LOCAL-763/789B] FIX: a layout-size change reloads tiles (the heal path) '
    'via the camera nudge',
    (tester) async {
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.binding.setSurfaceSize(const Size(300, 300));
      final provider = _CountingTileProvider();
      final controller = MapController();
      await tester.pumpWidget(
          _mapInTabShell(provider: provider, useFix: true, controller: controller));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
      final afterFirstLayout = provider.requests;
      expect(afterFirstLayout, greaterThan(0));

      // A real size settle changes the map camera's nonRotatedSize, so
      // FirstLayoutTileLayer nudges the camera (zoom ± 1e-4); the live TileLayer
      // recomputes its visible range and loads tiles for the new size.
      await tester.binding.setSurfaceSize(const Size(600, 600));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
      await tester.pump(const Duration(milliseconds: 50));

      expect(
        provider.requests,
        greaterThan(afterFirstLayout),
        reason:
            'A layout-size change must trigger a tile reload via the camera '
            'nudge — this is what heals the blank map once the deferred '
            'IndexedStack layout settles (LOCAL-789B).',
      );
    },
  );
}
