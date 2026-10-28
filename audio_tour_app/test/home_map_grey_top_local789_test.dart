// [LOCAL-789] Red/guard test for the Home-map "top ~60% grey for ~30 s after
// entering Home" bug (Michael, iPhone TestFlight 83, 2026-10-27).
//
// THE BUG: the Home map lives in a Column under a VARIABLE-height header — the
// orange "Showing tours near: …" banner appears the instant a place search sets
// _isUsingCustomLocation, and the LOCAL-761 hide-on-scroll bar comes and goes.
// When that header GROWS after the first layout, the Expanded map SHRINKS from
// the top; on the device, flutter_map's size event lagged the layout, so the
// TileLayer kept the tile range it had computed for the OLD (taller) viewport.
// LOCAL-763's FirstLayoutTileLayer reset only on MapEventNonRotatedSizeChange +
// one post-frame, so the newly-exposed TOP band had NO tiles (grey) until the
// next camera/location event ~30 s later.
//
// THE FIX: a LayoutBuilder around the map fires an EXTERNAL reset whenever the
// map's laid-out height changes; FirstLayoutTileLayer forwards that to the
// TileLayer's `reset` (coalesced to one per frame). These tests pin the two
// observable guarantees of that mechanism with a counting, offline tile
// provider — exactly the harness LOCAL-763 established:
//
//   1. Firing the externalReset stream reloads the tiles (the heal path that
//      covers the top band when the banner grows).
//   2. Growing a banner ABOVE the map — the real trigger — shrinks the map and
//      drives a reload through the LayoutBuilder→externalReset path, so the new
//      (shifted) viewport gets its tiles. No gesture, no timer.

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
    '[LOCAL-789] firing externalReset reloads tiles (the top-band heal path)',
    (tester) async {
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.binding.setSurfaceSize(const Size(400, 800));
      final provider = _CountingTileProvider();
      final external = StreamController<void>.broadcast();
      addTearDown(external.close);

      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: FlutterMap(
            options: const MapOptions(
              initialCenter: LatLng(42.3601, -71.0589),
              initialZoom: 13.0,
            ),
            children: [
              FirstLayoutTileLayer(
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

      // The parent fires the external reset (as the LayoutBuilder does when the
      // banner changes the map's height). The TileLayer must reload.
      external.add(null);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));

      expect(
        provider.requests,
        greaterThan(afterFirstLayout),
        reason:
            'externalReset must drive a tile reload so the top band gets tiles '
            'when the banner changes the map size (LOCAL-789).',
      );
    },
  );

  testWidgets(
    '[LOCAL-789] a banner appearing ABOVE the map shrinks it and reloads tiles '
    'for the new viewport (no gesture, no timer)',
    (tester) async {
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.binding.setSurfaceSize(const Size(400, 800));

      final provider = _CountingTileProvider();
      final sizeReset = StreamController<void>.broadcast();
      addTearDown(sizeReset.close);

      // A miniature of the Home body: a variable-height header above an
      // Expanded map, wrapped in the LayoutBuilder that fires sizeReset when the
      // map's laid-out height changes — exactly the home_screen.dart wiring. A
      // top-level StatefulWidget toggles the banner so the WHOLE body re-lays
      // out (as setState on _HomeScreenState does when _isUsingCustomLocation
      // flips), re-invoking the LayoutBuilder with the new constraints.
      await tester.pumpWidget(MaterialApp(
        home: _BannerHarness(provider: provider, sizeReset: sizeReset),
      ));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
      final afterFirstLayout = provider.requests;
      expect(afterFirstLayout, greaterThan(0));

      // Show the banner: the header grows, the Expanded map shrinks from the
      // top. The LayoutBuilder sees a new maxHeight → fires sizeReset → the
      // FirstLayoutTileLayer rebuilds the TileLayer, which re-requests the
      // tiles for the new viewport (so the newly-exposed top is not left grey).
      _BannerHarness.showBanner();
      await tester.pump(); // flip banner → relayout → LayoutBuilder fires reset
      await tester.pump(const Duration(milliseconds: 50)); // post-frame epoch++
      await tester.pump(const Duration(milliseconds: 50)); // rebuild + requests
      await tester.pump(const Duration(milliseconds: 50)); // tiles resolve

      expect(
        provider.requests,
        greaterThan(afterFirstLayout),
        reason:
            'When the banner grows and the map shrinks, the LayoutBuilder must '
            'drive a tile reload so the newly-exposed top is not left grey '
            '(LOCAL-789).',
      );
    },
  );
}

/// A tiny stand-in for the Home body: a variable-height banner above an
/// Expanded map, with the LOCAL-789 LayoutBuilder→sizeReset wiring. Exposes a
/// static [showBanner] so the test can flip the banner via a real top-level
/// setState (the whole column re-lays out, exactly as the Home screen does).
class _BannerHarness extends StatefulWidget {
  const _BannerHarness({required this.provider, required this.sizeReset});

  final TileProvider provider;
  final StreamController<void> sizeReset;

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
                options: const MapOptions(
                  initialCenter: LatLng(42.3601, -71.0589),
                  initialZoom: 13.0,
                ),
                children: [
                  FirstLayoutTileLayer(
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
