/// [LOCAL-793] After a Home place search relocates the map, decide how to make
/// a nearby tour visible instead of showing a false "0 tours in this map area".
///
/// Michael, iPhone TestFlight 83 (2026-10-27): searching "Hi Chi Minh, Vietnam"
/// landed ~11 km from District 1 and the map said "0 tours in this map area",
/// even though four Ho Chi Minh City tours were 7–12 mi away — zooming out by
/// hand revealed them. The rule: never claim "0 tours" when a tour is within a
/// sensible reach of where we landed; zoom out to include it, or (if it is far)
/// tell the listener exactly how far the nearest tour is.
///
/// These are PURE functions so a widget/unit test can assert the decision for
/// "one tour 12 km away" without a live map or server.
library;

import 'dart:math';

/// The outcome of the post-relocation "is a tour visible?" check.
enum ZoomOutAction {
  /// A tour is already inside the current view — do nothing.
  keep,

  /// The nearest tour is within [kMaxZoomOutRadiusKm]; zoom OUT so it is on
  /// screen. [zoom] is the map zoom level to apply.
  zoomToShow,

  /// The nearest tour is farther than [kMaxZoomOutRadiusKm]; do not zoom the
  /// whole world — show a "Nearest tours: N km away" message with a button.
  announceDistance,
}

/// How far out we will auto-zoom to pull a tour into view. Beyond this we show
/// the "Nearest tours: N km away" message instead (LOCAL-793: "zoom out step by
/// step, max ~50 km"). A tour within 25 km must NEVER yield "0 tours".
const double kMaxZoomOutRadiusKm = 50.0;

/// The decision for a freshly relocated map.
class ZoomOutDecision {
  final ZoomOutAction action;

  /// Set for [ZoomOutAction.zoomToShow]: the zoom level to apply.
  final double? zoom;

  /// Set for [ZoomOutAction.announceDistance]: the nearest tour's distance in
  /// km, rounded for display.
  final int? nearestKm;

  const ZoomOutDecision._(this.action, {this.zoom, this.nearestKm});

  const ZoomOutDecision.keep() : this._(ZoomOutAction.keep);
  const ZoomOutDecision.zoomToShow(double zoom)
      : this._(ZoomOutAction.zoomToShow, zoom: zoom);
  const ZoomOutDecision.announce(int nearestKm)
      : this._(ZoomOutAction.announceDistance, nearestKm: nearestKm);
}

/// Decide what to do after relocating, given:
///   * [tourInView]       — whether any tour is already inside the view;
///   * [nearestTourKm]    — distance to the nearest tour anywhere (null = none
///                          known at all).
///
/// Rules:
///   * A tour already on screen → [ZoomOutAction.keep].
///   * No tour known anywhere → [ZoomOutAction.keep] (nothing to zoom to; the
///     normal empty-area view stands).
///   * Nearest tour within [kMaxZoomOutRadiusKm] → zoom out to a level whose
///     view radius covers it ([zoomForRadiusKm]).
///   * Nearest tour beyond [kMaxZoomOutRadiusKm] → announce the distance.
ZoomOutDecision decideZoomOut({
  required bool tourInView,
  required double? nearestTourKm,
}) {
  if (tourInView) return const ZoomOutDecision.keep();
  if (nearestTourKm == null) return const ZoomOutDecision.keep();
  if (nearestTourKm <= kMaxZoomOutRadiusKm) {
    // Add a small margin so the pin is comfortably inside the view, not on the
    // very edge, then convert the needed radius to a zoom level.
    final radius = max(nearestTourKm * 1.3, 2.0);
    return ZoomOutDecision.zoomToShow(zoomForRadiusKm(radius));
  }
  return ZoomOutDecision.announce(nearestTourKm.round());
}

/// Approximate the map zoom level whose half-view (centre-to-edge) spans
/// [radiusKm]. Web-Mercator: the whole world (~20000 km across) is zoom 0 and
/// each zoom step halves the span. Clamped to a sane 3..15 so we never show the
/// whole globe or dive in past street level.
double zoomForRadiusKm(double radiusKm) {
  if (radiusKm <= 0) return 15.0;
  // At zoom 13 the half-view is ~5 km (the app's default place zoom). Each zoom
  // level out doubles the span: z = 13 - log2(radius / 5).
  const double baseZoom = 13.0;
  const double baseRadiusKm = 5.0;
  final double z = baseZoom - (log(radiusKm / baseRadiusKm) / log(2));
  return z.clamp(3.0, 15.0);
}
