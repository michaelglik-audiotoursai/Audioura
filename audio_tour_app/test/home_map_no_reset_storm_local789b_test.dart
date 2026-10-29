// [LOCAL-789B] Regression test proving the Home-map tile layer no longer forms
// a RESET STORM — the root cause of the "fully grey on entry" bug (Michael,
// iPhone TestFlight 84, 2026-10-28).
//
// THE BUG: LOCAL-789 wrapped the TileLayer in a KeyedSubtree and bumped a
// ValueKey on every size/layout trigger. In flutter_map 6.2.1 a key change
// DISPOSES the old TileLayer, and TileLayer.dispose() disposes its tile
// provider. The default NetworkTileProvider.dispose() closes its RetryClient,
// which ABORTS every in-flight tile HTTP request ("Connection attempt
// cancelled"). Because the Home header settles over several frames (loading
// spinner → map, the async banner flip, the hide-on-scroll bar), the parent
// fired the reset repeatedly, so the TileLayer was disposed again and again
// mid-load — tiles were cancelled faster than they loaded and the map stayed
// grey until a pinch stopped the storm.
//
// THE FIX: FirstLayoutTileLayer keeps ONE stable TileLayer for the life of the
// map and reloads via an imperceptible camera nudge instead of a key rebuild.
// So the provider is NEVER disposed while the map is mounted, no matter how many
// reset triggers arrive, and in-flight tile loads are never cancelled.
//
// These tests instrument:
//   * provider.disposeCount — MUST stay 0 while the map is mounted, even under a
//     burst of external resets (the storm). Proves no dispose/cancel loop.
//   * camera-move (nudge) count — MUST be bounded (not an unbounded loop): a
//     burst of SAME-size triggers nudges at most a small, finite number of
//     times, and the nudge never re-triggers itself.
//   * on unmount the provider IS disposed exactly once (normal cleanup).

import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart' show SynchronousFuture;
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';

import 'package:audio_tour_app_dev/widgets/first_layout_tile_layer.dart';

/// Counts tile requests AND provider disposals, so a reset storm (which
/// disposes the provider on every key rebuild) is directly observable.
class _CountingTileProvider extends TileProvider {
  int requests = 0;
  int disposeCount = 0;

  @override
  ImageProvider getImage(TileCoordinates coordinates, TileLayer options) {
    requests++;
    return _TransparentImageProvider(requests);
  }

  @override
  void dispose() {
    disposeCount++;
    super.dispose();
  }
}

class _TransparentImageProvider
    extends ImageProvider<_TransparentImageProvider> {
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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
    '[LOCAL-789B] a burst of external resets NEVER disposes the tile provider '
    '(no reset storm, no cancelled tiles)',
    (tester) async {
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.binding.setSurfaceSize(const Size(400, 800));

      final provider = _CountingTileProvider();
      final external = StreamController<void>.broadcast();
      addTearDown(external.close);
      final controller = MapController();

      // Count camera moves sourced from the controller (our nudges).
      var nudges = 0;

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

      // Subscribe AFTER first layout so we count only storm-induced nudges.
      final sub = controller.mapEventStream.listen((e) {
        if (e is MapEventMove && e.source == MapEventSource.mapController) {
          nudges++;
        }
      });
      addTearDown(sub.cancel);

      final requestsAfterFirstLayout = provider.requests;
      expect(requestsAfterFirstLayout, greaterThan(0),
          reason: 'Tiles must load on first layout with no gesture.');
      expect(provider.disposeCount, 0,
          reason: 'The provider must not be disposed during normal life.');

      // THE STORM: fire the external reset many times across many frames at a
      // CONSTANT size — exactly what the Home LayoutBuilder did over the frames
      // the header took to settle. The OLD key-rebuild fix disposed the
      // provider on each one; the fix must dispose it ZERO times.
      for (var i = 0; i < 20; i++) {
        external.add(null);
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 16));
      }
      await tester.pump(const Duration(milliseconds: 100));

      expect(
        provider.disposeCount,
        0,
        reason:
            'A burst of resets must NOT dispose the tile provider — disposing it '
            'closes the network client and cancels in-flight tiles, which is the '
            'fully-grey-on-entry reset storm (LOCAL-789B).',
      );

      // The nudge must be BOUNDED: at a constant size the size-signature guard
      // lets at most one nudge through for that size, so a 20-reset burst does
      // NOT produce 20+ camera moves (which would be a loop). Allow a tiny slack
      // for the first-size nudge; the point is it is O(1), not O(bursts).
      expect(
        nudges,
        lessThanOrEqualTo(2),
        reason:
            'At a constant size the camera nudge must fire at most once (no '
            'loop) — a burst of resets must not produce a camera move per reset.',
      );

      // Tiles are still present (never cancelled): the request count never went
      // backwards and the provider was never torn down.
      expect(provider.requests, greaterThanOrEqualTo(requestsAfterFirstLayout));
    },
  );

  testWidgets(
    '[LOCAL-789B] the tile provider is disposed exactly once, only on unmount',
    (tester) async {
      final provider = _CountingTileProvider();
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
      expect(provider.disposeCount, 0,
          reason: 'Not disposed while mounted.');

      // Replace the whole tree → the map unmounts → the provider is disposed
      // once (normal cleanup), never more.
      await tester.pumpWidget(const MaterialApp(home: SizedBox()));
      await tester.pump();

      expect(provider.disposeCount, 1,
          reason:
              'The provider is disposed exactly once, only when the map '
              'unmounts (LOCAL-789B).');
    },
  );
}
