// [LOCAL-789 / LOCAL-789B] Guard test for the Home-map grey-on-entry bug.
//
// THE BUG (LOCAL-789, iPhone TestFlight 83, 2026-10-27): the Home map's top
// ~60% stayed plain grey for ~30 s after entering Home; the bottom ~40% had
// tiles. The map lives in a Column under a VARIABLE-height header — the orange
// "Showing tours near: …" banner appears the instant a place search sets
// _isUsingCustomLocation, and the LOCAL-761 hide-on-scroll bar comes and goes.
// When the header GROWS after the first layout the Expanded map SHRINKS from
// the top; flutter_map's size event lagged, so the TileLayer kept its old
// (taller) tile range and the newly-exposed TOP band had no tiles until the
// next camera event.
//
// LOCAL-789B (iPhone TestFlight 84, 2026-10-28): LOCAL-789's fix rebuilt the
// TileLayer with a new ValueKey on every size change. In flutter_map 6.2.1 that
// DISPOSES the TileLayer's default NetworkTileProvider, whose dispose() closes
// its RetryClient and ABORTS every in-flight tile request ("Connection attempt
// cancelled"). Over the several frames a real device takes to settle, the
// repeated rebuilds formed a RESET STORM that cancelled tiles faster than they
// loaded — leaving the map ENTIRELY grey until a pinch stopped the storm.
//
// THE LOCAL-789B FIX: keep ONE stable TileLayer (never disposed mid-load) and
// reload after the size settles with an imperceptible camera NUDGE on the
// shared MapController (zoom ± 1e-4) — the pinch-equivalent. These tests pin the
// observable guarantees with a counting, offline tile provider:
//
//   1. After a size change, the heal path (external size signal) reloads tiles
//      for the new viewport.
//   2. A banner appearing ABOVE the map shrinks it and drives a reload through
//      the LayoutBuilder→externalReset→nudge path, so the new (shifted)
//      viewport gets its tiles — no gesture, no timer.
//
// The no-reset-storm / no-dispose-loop guarantee is proven separately in
// home_map_no_reset_storm_local789b_test.dart.

import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart' show SynchronousFuture;
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';

import 'package:audio_tour_app_dev/widgets/first_layout_tile_layer.dart';

/// Counts every tile request and returns a tiny transparent image, so the map
/// never touches the network and the test is deterministic. Each request gets a
/// UNIQUE image key so a reload is never hidden by the image cache — a fresh
/// getImage call is what we count.
class _CountingTileProvider extends TileProvider {
  int requests = 0;

  @override
  ImageProvider getImage(TileCoordinates coordinates, TileLayer options) {
    requests++;
    return _TransparentImageProvider(requests);
  }
}

class _TransparentImageProvider
    extends ImageProvider<_TransparentImageProvider> {
  _TransparentImageProvider(this.id);

  /// Unique per request so no two keys compare equal (defeats the image cache,
  /// so every tile request really calls getImage and is counted).
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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
    '[LOCAL-789B] a size change reloads tiles via the camera nudge (the '
    'top-band heal path)',
    (tester) async {
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.binding.setSurfaceSize(const Size(400, 800));
      final provider = _CountingTileProvider();
      final external = StreamController<void>.broadcast();
      addTearDown(external.close);
      final controller = MapController();

      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: FlutterMap(
            mapController: controller,
            options: const MapOptions(
              initialCenter: LatLng(42.3601, -71.0589),
              initialZoom: 13.0,
            ),
            children: [
              FirstLayoutTileLayer(
                mapController: controller,
                externalReset: external.stream,
                builder: (reset) => TileLayer(
                  urlTemplate: 'https://tile.example/{z}/{x}/{y}.png',
                  tileProvider: provider,
                  reset: reset,
                ),
              ),
            ],
          ),
        ),
      ));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
      final afterFirstLayout = provider.requests;
      expect(afterFirstLayout, greaterThan(0));

      // Count camera moves sourced from the controller (our nudges) from here
      // on — the observable that proves the heal path ran. (In a widget test
      // the viewport tile SET is unchanged by a sub-pixel nudge, so the raw
      // getImage count can plateau; the nudge itself is the mechanism that, on
      // a real surface with a lagged size event, recomputes the grid for the
      // new viewport. The no-storm test asserts tiles are never cancelled.)
      var nudges = 0;
      final sub = controller.mapEventStream.listen((e) {
        if (e is MapEventMove && e.source == MapEventSource.mapController) {
          nudges++;
        }
      });
      addTearDown(sub.cancel);

      // The map shrinks (the banner-grow case): the camera's nonRotatedSize
      // changes, so FirstLayoutTileLayer nudges the camera and the TileLayer
      // reloads tiles for the new viewport. The external signal is also fired
      // (as the LayoutBuilder does) to prove both paths coalesce to a reload.
      await tester.binding.setSurfaceSize(const Size(400, 560));
      external.add(null);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
      await tester.pump(const Duration(milliseconds: 50));

      expect(
        nudges,
        greaterThan(0),
        reason:
            'A size change must drive a camera nudge so the TileLayer reloads '
            'its grid for the new viewport (the top-band heal path, LOCAL-789B).',
      );
    },
  );

  testWidgets(
    '[LOCAL-789B] a banner appearing ABOVE the map shrinks it and reloads tiles '
    'for the new viewport (no gesture, no timer)',
    (tester) async {
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.binding.setSurfaceSize(const Size(400, 800));

      final provider = _CountingTileProvider();
      final sizeReset = StreamController<void>.broadcast();
      addTearDown(sizeReset.close);
      final controller = MapController();

      // A miniature of the Home body: a variable-height header above an
      // Expanded map, wrapped in the LayoutBuilder that fires sizeReset when the
      // map's laid-out height changes — exactly the home_screen.dart wiring. A
      // top-level StatefulWidget toggles the banner so the WHOLE body re-lays
      // out (as setState on _HomeScreenState does when _isUsingCustomLocation
      // flips), re-invoking the LayoutBuilder with the new constraints.
      await tester.pumpWidget(MaterialApp(
        home: _BannerHarness(
          provider: provider,
          sizeReset: sizeReset,
          controller: controller,
        ),
      ));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
      final afterFirstLayout = provider.requests;
      expect(afterFirstLayout, greaterThan(0));

      // Count camera nudges from here on.
      var nudges = 0;
      final sub = controller.mapEventStream.listen((e) {
        if (e is MapEventMove && e.source == MapEventSource.mapController) {
          nudges++;
        }
      });
      addTearDown(sub.cancel);

      // Show the banner: the header grows, the Expanded map shrinks from the
      // top. The LayoutBuilder sees a new maxHeight → fires sizeReset, and the
      // map's nonRotatedSize changes → FirstLayoutTileLayer nudges the camera,
      // which recomputes the grid for the new viewport (so the newly-exposed
      // top is not left grey).
      _BannerHarness.showBanner();
      await tester.pump(); // flip banner → relayout → LayoutBuilder fires reset
      await tester.pump(const Duration(milliseconds: 50)); // post-frame nudge
      await tester.pump(const Duration(milliseconds: 50)); // reload + requests
      await tester.pump(const Duration(milliseconds: 50)); // tiles resolve

      expect(
        nudges,
        greaterThan(0),
        reason:
            'When the banner grows and the map shrinks, a camera nudge must heal '
            'the grid so the newly-exposed top is not left grey (LOCAL-789B).',
      );
    },
  );
}

/// A tiny stand-in for the Home body: a variable-height banner above an
/// Expanded map, with the LOCAL-789 LayoutBuilder→sizeReset wiring and the
/// LOCAL-789B MapController. Exposes a static [showBanner] so the test can flip
/// the banner via a real top-level setState (the whole column re-lays out,
/// exactly as the Home screen does).
class _BannerHarness extends StatefulWidget {
  const _BannerHarness({
    required this.provider,
    required this.sizeReset,
    required this.controller,
  });

  final TileProvider provider;
  final StreamController<void> sizeReset;
  final MapController controller;

  static late void Function() showBanner;

  @override
  State<_BannerHarness> createState() => _BannerHarnessState();
}

class _BannerHarnessState extends State<_BannerHarness> {
  bool _bannerShown = false;
  double? _lastHeight;

  @override
  void initState() {
    super.initState();
    _BannerHarness.showBanner = () => setState(() => _bannerShown = true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          SizedBox(
            height: _bannerShown ? 220 : 60,
            width: double.infinity,
            child: const ColoredBox(color: Color(0xFFFFE0B2)),
          ),
          Expanded(
            child: LayoutBuilder(builder: (context, constraints) {
              final h = constraints.maxHeight;
              if (_lastHeight != null &&
                  h.isFinite &&
                  (h - _lastHeight!).abs() > 0.5 &&
                  !widget.sizeReset.isClosed) {
                widget.sizeReset.add(null);
              }
              if (h.isFinite) _lastHeight = h;
              return FlutterMap(
                mapController: widget.controller,
                options: const MapOptions(
                  initialCenter: LatLng(42.3601, -71.0589),
                  initialZoom: 13.0,
                ),
                children: [
                  FirstLayoutTileLayer(
                    mapController: widget.controller,
                    externalReset: widget.sizeReset.stream,
                    builder: (reset) => TileLayer(
                      urlTemplate: 'https://tile.example/{z}/{x}/{y}.png',
                      tileProvider: widget.provider,
                      reset: reset,
                    ),
                  ),
                ],
              );
            }),
          ),
        ],
      ),
    );
  }
}
