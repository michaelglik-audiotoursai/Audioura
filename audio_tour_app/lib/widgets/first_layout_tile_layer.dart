// [LOCAL-763 / D711 addendum 1 — bug fix; LOCAL-789 — correctness;
//  LOCAL-789B — real-device fix] A TileLayer that draws its tiles from the
// FIRST settled layout AND reloads them when the map's laid-out size settles,
// even when the map is created inside an IndexedStack + nested Navigator (the
// LOCAL-761 tab shell) under a variable-height header — WITHOUT ever disposing
// the TileLayer (or its network client) while tiles are still loading.
//
// THE BUGS (history):
//   * LOCAL-763 (Michael, 2026-10-25): the Home map opened with the markers but
//     a BLANK map; OSM tiles appeared only after a pinch-to-zoom. Markers draw
//     because MarkerLayer positions its points absolutely, independent of the
//     tile grid; tiles do not.
//   * LOCAL-789 (Michael, iPhone TestFlight 83, 2026-10-27): the map's TOP
//     ~60 % stayed plain grey (markers drawn on it) for ~30 s after entering
//     Home, the bottom ~40 % had tiles.
//   * LOCAL-789B (Michael, iPhone TestFlight 84, 2026-10-28): the map is now
//     ENTIRELY grey on entry; a single pinch draws it instantly. LOCAL-789's
//     fix made it WORSE, which is the clue to the real root cause.
//
// REAL ROOT CAUSE (flutter_map 6.2.1), the LOCAL-789B correction
// =============================================================
// LOCAL-763/789 wrapped the TileLayer in `KeyedSubtree(key: ValueKey(_epoch))`
// and bumped the epoch on every reload trigger. A ValueKey change DISPOSES the
// old TileLayer State and builds a fresh one. But in flutter_map 6.2.1:
//   * The default tile provider is `NetworkTileProvider` (tile_layer.dart:294),
//     which does NOT support cancellation — it uses a `RetryClient`.
//   * `TileLayer.dispose()` (line 499) calls `widget.tileProvider.dispose()`,
//     and `NetworkTileProvider.dispose()` calls `httpClient.close()`.
//   * Closing the `RetryClient` ABORTS every in-flight tile HTTP request on it
//     → "SocketException: Connection attempt cancelled".
//   * `TileImage.dispose()` (tile_image.dart:243) also completes
//     `cancelLoading`, abandoning the tile.
// On a real device the layout settles over SEVERAL frames (loading spinner →
// map, the async `_loadCustomLocation` setState flips the "Showing tours near:"
// banner which changes the header height, the LOCAL-761 hide-on-scroll bar
// comes and goes). Each height delta made the parent LayoutBuilder fire the
// reset, which bumped the epoch, which disposed the TileLayer MID-LOAD and
// cancelled its tiles — then a fresh TileLayer started loading, only to be
// disposed by the next height delta. That is a RESET STORM: the map stays grey
// until a user gesture changes the camera, no further resets fire, and the last
// TileLayer finally keeps its tiles. The epoch-key rebuild of LOCAL-789 is more
// destructive than LOCAL-763's reset-only attempt, which is exactly why build
// 84 is fully grey where 83 was only partly grey.
//
// Why `TileLayer.reset` cannot be relied on: in 6.2.1 the `reset` subscription
// is a `late final` only ever READ in `dispose()` (tile_layer.dart:384,497), so
// it is never created during the layer's life — firing `reset` does nothing
// (verified: a reset at a constant size requests zero new tiles). The stream is
// still forwarded here for forward-compat should flutter_map fix that.
//
// THE LOCAL-789B FIX (no key bump, no dispose, no timers)
// =======================================================
// Keep ONE STABLE TileLayer for the whole life of the map — never change its
// key, never dispose its provider while tiles load. To cover the whole viewport
// after the size settles, do exactly what the user's pinch does: NUDGE the
// shared `MapController`'s camera by an imperceptible amount (zoom + 1e-4). A
// real `move()` emits a `MapEventMove` that the live TileLayer's
// `_tileUpdateSubscription` recomputes its visible tile range from — loading
// every tile for the CURRENT (correct-size) viewport, with nothing disposed and
// no HTTP request cancelled. `move()` to an unchanged camera is a no-op that
// emits nothing (internal.dart:84), so the nudge must change zoom/center a hair;
// 1e-4 at the Home zooms is far below one pixel, so it is invisible.
//
// This is driven at most ONCE PER SETTLED SIZE and can never loop:
//   * A nudge is scheduled on a reload trigger (first layout / size event /
//     external size change), coalesced to one per frame.
//   * The nudge itself changes the camera, which re-emits size/position events;
//     those are IGNORED because we only nudge when the laid-out size differs
//     from the size we last nudged for (`_lastNudgedHeightSignature`). A nudge
//     does not change the laid-out HEIGHT, so it cannot re-trigger itself.

import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_map/flutter_map.dart';

/// Builds the [TileLayer] for [FirstLayoutTileLayer], wiring in the [reset]
/// stream this widget forwards. Callers pass their normal TileLayer arguments
/// and SHOULD forward [reset] to `TileLayer(reset: reset, …)` (harmless in
/// flutter_map 6.2.1 where the reload is driven by the camera nudge instead).
typedef TileLayerBuilder = TileLayer Function(Stream<void> reset);

/// A drop-in replacement for a `TileLayer` inside `FlutterMap.children` that
/// reloads its tiles the instant the map's layout size is known, and again
/// whenever that size changes for any reason — fixing the "blank map until the
/// first zoom" (LOCAL-763), "top band grey" (LOCAL-789) and "fully grey on
/// entry" (LOCAL-789B) bugs on maps built inside an IndexedStack / nested
/// Navigator under a variable-height header.
///
/// Unlike the LOCAL-789 version, this NEVER rebuilds the wrapped [TileLayer]
/// with a new key and never disposes it (or its network client) while tiles are
/// loading. The reload is driven by a one-shot, imperceptible camera nudge on
/// the shared [mapController] — equivalent to the pinch gesture that already
/// heals the map — so in-flight tile requests are never cancelled.
///
/// Usage — replace
/// ```dart
/// TileLayer(urlTemplate: '…', userAgentPackageName: '…')
/// ```
/// with
/// ```dart
/// FirstLayoutTileLayer(
///   mapController: _mapController,          // the FlutterMap's controller
///   externalReset: constraintsChanged.stream, // optional
///   builder: (reset) => TileLayer(
///     urlTemplate: '…', userAgentPackageName: '…', reset: reset),
/// )
/// ```
class FirstLayoutTileLayer extends StatefulWidget {
  const FirstLayoutTileLayer({
    super.key,
    required this.builder,
    this.mapController,
    this.externalReset,
  });

  /// Builds the wrapped [TileLayer]. The provided stream is forwarded to
  /// `TileLayer(reset: …)` for forward-compat; the actual reload is the camera
  /// nudge, so forwarding it is optional.
  final TileLayerBuilder builder;

  /// The same [MapController] passed to the surrounding [FlutterMap]. Used to
  /// perform the imperceptible camera nudge that reloads tiles after the size
  /// settles. If null (e.g. in a unit test that only checks the stable-key
  /// behaviour) the widget still forwards [externalReset] but cannot nudge.
  final MapController? mapController;

  /// [LOCAL-789] Optional stream a PARENT fires when the map's laid-out size
  /// changes for a reason flutter_map may not emit a size event for in time —
  /// e.g. a banner above the map appearing/disappearing. Each emission requests
  /// at most one camera nudge (coalesced per frame, and only if the size really
  /// changed). The widget only listens; it never closes this stream (the parent
  /// owns it).
  final Stream<void>? externalReset;

  @override
  State<FirstLayoutTileLayer> createState() => _FirstLayoutTileLayerState();
}

class _FirstLayoutTileLayerState extends State<FirstLayoutTileLayer> {
  // Broadcast so the TileLayer's internal listen() never fights our listeners
  // and a late subscriber still works. Forwarded for forward-compat only.
  final StreamController<void> _reset = StreamController<void>.broadcast();

  StreamSubscription<MapEvent>? _eventSub;
  StreamSubscription<void>? _externalSub;
  int? _controllerHashCode;

  // [LOCAL-789B] One-per-frame coalescing of reload triggers into a single
  // camera nudge. Multiple triggers in one frame (first-layout post-frame + a
  // size event + a LayoutBuilder constraint change) collapse into ONE nudge
  // against the final camera.
  bool _nudgeScheduled = false;

  // [LOCAL-789B] The map camera size we last nudged for. A nudge is only
  // performed when the current size differs from this — so the camera nudge
  // (which changes zoom, NOT the laid-out size) can never re-trigger itself,
  // and a burst of identical-size triggers nudges at most once. Null until the
  // first nudge.
  String? _lastNudgedSizeSignature;

  // [LOCAL-789B] Alternate the nudge direction so two consecutive nudges (first
  // layout, then a later real size change) always change the camera — a repeat
  // nudge to the same zoom would be a no-op that emits no event.
  bool _nudgeUp = true;

  @override
  void initState() {
    super.initState();
    _subscribeExternal();
  }

  @override
  void didUpdateWidget(covariant FirstLayoutTileLayer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.externalReset, widget.externalReset)) {
      _subscribeExternal();
    }
  }

  void _subscribeExternal() {
    _externalSub?.cancel();
    _externalSub = widget.externalReset?.listen((_) => _scheduleNudge());
  }

  /// Request a one-shot tile reload (camera nudge) on the NEXT frame, at most
  /// once per frame. Post-frame timing guarantees the nudge runs against the
  /// camera AFTER this frame's layout has settled the new size.
  void _scheduleNudge() {
    if (_nudgeScheduled) return;
    _nudgeScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _nudgeScheduled = false;
      if (!mounted) return;
      // Forward the (dead-in-6.2.1) reset stream for forward-compat.
      if (!_reset.isClosed) _reset.add(null);
      _nudgeCameraIfSizeChanged();
    });
  }

  /// The heal: if the map's laid-out size has changed since the last nudge,
  /// move the camera by an imperceptible amount so the live TileLayer recomputes
  /// its visible tile range for the new size — WITHOUT disposing anything. Does
  /// nothing when the size is unchanged, which is what stops the LOCAL-789 reset
  /// storm and prevents the nudge from re-triggering itself.
  void _nudgeCameraIfSizeChanged() {
    final controller = widget.mapController;
    if (controller == null) return;

    final MapCamera camera;
    try {
      camera = controller.camera;
    } catch (_) {
      // Controller not attached yet (map not mounted / in the LOCAL-793 loading
      // spinner window). The map re-centres via initialCenter on mount; a later
      // size settle will schedule another nudge.
      return;
    }

    final size = camera.nonRotatedSize;
    // nonRotatedSize can be the sentinel (0,0 or NaN) before the first layout.
    if (!size.x.isFinite || !size.y.isFinite || size.x <= 0 || size.y <= 0) {
      return;
    }
    final signature = '${size.x.toStringAsFixed(1)}x${size.y.toStringAsFixed(1)}';
    if (signature == _lastNudgedSizeSignature) {
      // Same size we already reloaded for: nothing to heal, and nudging again
      // would risk a loop. No-op.
      return;
    }
    _lastNudgedSizeSignature = signature;

    // A sub-pixel zoom delta: invisible to the user, but a real camera change so
    // move() emits a MapEventMove the TileLayer reloads from. Alternate the sign
    // so the next settled size is also a genuine change.
    final delta = _nudgeUp ? 1e-4 : -1e-4;
    _nudgeUp = !_nudgeUp;
    try {
      controller.move(camera.center, camera.zoom + delta);
    } catch (_) {
      // Controller detached between the guard and the move; a later settle will
      // retry. Never throw into the frame callback.
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // (Re)subscribe to the map's event stream when the controller changes, so a
    // MapEventNonRotatedSizeChange (when flutter_map does emit it) schedules a
    // nudge. Mirrors how TileLayer itself tracks the controller.
    final controller = MapController.of(context);
    if (_controllerHashCode != controller.hashCode) {
      _controllerHashCode = controller.hashCode;
      _eventSub?.cancel();
      _eventSub = controller.mapEventStream.listen(_onMapEvent);
    }
    // Cover the case where the size was already correct before we subscribed:
    // schedule one nudge after this frame. _nudgeCameraIfSizeChanged's
    // size-signature guard makes this a no-op if nothing actually changed.
    _scheduleNudge();
  }

  void _onMapEvent(MapEvent event) {
    // The layout just settled (or changed) its size: schedule a nudge. The
    // size-signature guard ignores the position/size churn our own nudge emits.
    if (event is MapEventNonRotatedSizeChange) {
      _scheduleNudge();
    }
  }

  @override
  void dispose() {
    _eventSub?.cancel();
    _externalSub?.cancel();
    _reset.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // [LOCAL-789B] NO KeyedSubtree / ValueKey: the TileLayer is STABLE for the
    // life of the map, so it is never disposed mid-load and its in-flight tile
    // requests are never cancelled. Reloads happen via the camera nudge above.
    return widget.builder(_reset.stream);
  }
}
