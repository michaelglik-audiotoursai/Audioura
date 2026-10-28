import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/utils/map_zoom.dart';

/// [LOCAL-793] The "never 0 tours when a tour is close" half of Michael's bug.
///
/// Michael's "Hi Chi Minh" search landed ~11 km off District 1 and the map said
/// "0 tours in this map area" although four HCMC tours were 7–12 mi away. The
/// rule: after relocating, if no tour is in view, zoom out (up to ~50 km) to
/// show the nearest tour, or announce "Nearest tours: N km away". A tour within
/// 25 km must NEVER yield "0 tours".
///
/// The decision is pure ([decideZoomOut]); the widget test renders its outcome
/// to prove the UI shows the nearby tour instead of a false "0 tours".
void main() {
  group('decideZoomOut', () {
    test('a tour already in view → keep (no zoom)', () {
      final d = decideZoomOut(tourInView: true, nearestTourKm: 3);
      expect(d.action, ZoomOutAction.keep);
    });

    test('no tour anywhere → keep (nothing to zoom to)', () {
      final d = decideZoomOut(tourInView: false, nearestTourKm: null);
      expect(d.action, ZoomOutAction.keep);
    });

    test('tour 12 km away, none in view → zoom OUT to show it', () {
      final d = decideZoomOut(tourInView: false, nearestTourKm: 12);
      expect(d.action, ZoomOutAction.zoomToShow);
      // Must zoom OUT from the default place zoom (13) so a 12 km tour is on
      // screen, and the chosen zoom's view radius must actually cover 12 km.
      expect(d.zoom, isNotNull);
      expect(d.zoom!, lessThan(13.0));
      // Invert zoomForRadiusKm: a 12 km tour needs a half-view of ≥ 12 km.
      final radiusAtZoom = 5.0 * (1 << (13 - d.zoom!.round())).toDouble();
      expect(radiusAtZoom, greaterThanOrEqualTo(12.0));
    });

    test('a tour within 25 km is never "0 tours" — it is zoomed to', () {
      for (final km in [1, 7, 12, 20, 25]) {
        final d = decideZoomOut(tourInView: false, nearestTourKm: km.toDouble());
        expect(d.action, ZoomOutAction.zoomToShow,
            reason: 'a tour $km km away must be shown, not "0 tours"');
      }
    });

    test('a tour beyond 50 km → announce the distance, do not zoom the world',
        () {
      final d = decideZoomOut(tourInView: false, nearestTourKm: 120);
      expect(d.action, ZoomOutAction.announceDistance);
      expect(d.nearestKm, 120);
    });
  });

  group('zoomForRadiusKm', () {
    test('monotonic: a larger radius means a smaller (more zoomed-out) level',
        () {
      expect(zoomForRadiusKm(20), lessThan(zoomForRadiusKm(5)));
      expect(zoomForRadiusKm(50), lessThan(zoomForRadiusKm(20)));
    });

    test('clamped to a sane range', () {
      expect(zoomForRadiusKm(100000), greaterThanOrEqualTo(3.0));
      expect(zoomForRadiusKm(0.01), lessThanOrEqualTo(15.0));
    });
  });

  testWidgets(
      'zero tours in view + one tour 12 km away → UI shows the tour, not "0 tours"',
      (tester) async {
    // Simulate a relocate that loaded no tours into the view, with the nearest
    // tour 12 km away. The widget acts on decideZoomOut exactly as the Home
    // screen does, and must render the nearby tour rather than a "0 tours"
    // message.
    const nearestKm = 12.0;
    final decision =
        decideZoomOut(tourInView: false, nearestTourKm: nearestKm);

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(builder: (context) {
          switch (decision.action) {
            case ZoomOutAction.keep:
              return const Text('0 tours in this map area');
            case ZoomOutAction.zoomToShow:
              return Text('Showing tours near here (zoom '
                  '${decision.zoom!.toStringAsFixed(1)})');
            case ZoomOutAction.announceDistance:
              return Text('Nearest tours: ${decision.nearestKm} km away');
          }
        }),
      ),
    ));
    await tester.pump();

    // The false "0 tours" message must NOT appear for a 12 km tour.
    expect(find.text('0 tours in this map area'), findsNothing);
    // The zoom-to-show message must appear.
    expect(find.textContaining('Showing tours near here'), findsOneWidget);
  });

  testWidgets('a tour 120 km away shows "Nearest tours: 120 km away"',
      (tester) async {
    final decision = decideZoomOut(tourInView: false, nearestTourKm: 120);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(builder: (context) {
          if (decision.action == ZoomOutAction.announceDistance) {
            return Text('Nearest tours: ${decision.nearestKm} km away');
          }
          return const Text('0 tours in this map area');
        }),
      ),
    ));
    await tester.pump();
    expect(find.text('Nearest tours: 120 km away'), findsOneWidget);
    expect(find.text('0 tours in this map area'), findsNothing);
  });
}
