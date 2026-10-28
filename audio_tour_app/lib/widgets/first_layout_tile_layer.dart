// [LOCAL-763 / D711 addendum 1 — bug fix; LOCAL-789 — correctness] A TileLayer
// that is guaranteed to draw its tiles from the FIRST settled layout AND to
// reload them whenever the map's laid-out size changes, even when the map is
// created inside an IndexedStack + nested Navigator (the LOCAL-761 tab shell)
// under a variable-height header.
//
// THE BUGS:
//   * LOCAL-763 (Michael, 2026-10-25): the Home map opened with the markers but
//     a BLANK map; OSM tiles appeared only after a pinch-to-zoom. Markers draw
//     because MarkerLayer positions its points absolutely, independent of the
//     tile grid; tiles do not.
//   * LOCAL-789 (Michael, iPhone TestFlight 83, 2026-10-27): the map's TOP
//     ~60 % stayed plain grey (markers drawn on it) for ~30 s after entering
//     Home, the bottom ~40 % had tiles; it redrew normally only ~30 s later.
//     The orange "Showing tours near: …" banner (and the LOCAL-761 hide-on-
//     scroll bar) changes the header height AFTER the first layout, so the
//     Expanded map's size changes — and the tile range stayed computed for the
//     old viewport until the next camera/location event.
//
// ROOT CAUSE (flutter_map 6.2.1): `TileLayer` computes its visible tile range
// from `MapCamera.of(context)` in `didChangeDependencies`, then keeps itself up
// to date by listening to `MapController.mapEventStream`. `FlutterMap` settles
// its non-rotated size via `setNonRotatedSizeWithoutEmittingEvent` (updates the
// camera WITHOUT emitting) and schedules the `nonRotatedSizeChange` event for
// the NEXT frame. Inside the IndexedStack tab shell that post-frame broadcast
// event can be MISSED by the layer (its subscription is (re)created around the
// same frame), so the grid is never recomputed for the new size until a user
// gesture / location update produces a fresh MapEvent.
//
// IMPORTANT (why `TileLayer.reset` alone is NOT enough): in flutter_map 6.2.1
// the `reset` stream subscription is a `late final` that is only ever read in
// `dispose()`, so it NEVER actually listens during the layer's life — firing
// `reset` does nothing (verified: a reset at a constant size requests zero new
// tiles). LOCAL-763's reset-only fix therefore relied, in practice, on the
// post-gesture camera event; it did not heal a silent size change. This is the
// LOCAL-789 correction.
//
// THE FIX (no timers, library-version-independent): REBUILD the wrapped
// TileLayer with a changing `ValueKey` whenever the layout size is first known
// or changes. A fresh TileLayer State runs `didChangeDependencies` against the
// CURRENT (correct-size) camera and requests EVERY visible tile — so the whole
// viewport, including the previously-grey top band, is covered. Triggers:
//   1. the first post-frame after build (first settled layout);
//   2. a `MapEventNonRotatedSizeChange` (when flutter_map does emit it);
//   3. an [externalReset] the parent fires from a `LayoutBuilder` around the
//      `FlutterMap` when its `BoxConstraints` change (the banner/scroll-bar
//      case flutter_map may not emit for in time).
// All three are coalesced to AT MOST ONE rebuild per frame, so a burst of
// constraint changes cannot thrash the grid. The `reset` stream is still passed
// to the TileLayer (harmless, and forward-compatible should flutter_map fix the
// subscription), but the key bump is what actually heals the map.

import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_map/flutter_map.dart';

/// Builds the [TileLayer] for [FirstLayoutTileLayer], wiring in the [reset]
/// stream this widget drives. Callers pass their normal TileLayer arguments and
/// MUST forward [reset] to `TileLayer(reset: reset, …)`.
typedef TileLayerBuilder = TileLayer Function(Stream<void> reset);

/// A drop-in replacement for a `TileLayer` inside `FlutterMap.children` that
/// reloads its tiles the instant the map's layout size is known, and again
/// whenever that size changes for any reason — fixing both the "blank map until
/// the first zoom" bug (LOCAL-763) and the "top band grey for ~30 s" bug
/// (LOCAL-789) on maps built inside an IndexedStack / nested Navigator under a
/// variable-height header.
///
/// Usage — replace
/// ```dart
/// TileLayer(urlTemplate: '…', userAgentPackageName: '…')
/// ```
/// with
/// ```dart
/// FirstLayoutTileLayer(
///   externalReset: constraintsChanged.stream, // optional
///   builder: (reset) => TileLayer(
///     urlTemplate: '…', userAgentPackageName: '…', reset: reset),
/// )
/// ```
class FirstLayoutTileLayer extends StatefulWidget {
  const FirstLayoutTileLayer({
    super.key,
    required this.builder,
    this.externalReset,
  });

  /// Builds the wrapped [TileLayer]. The provided stream MUST be forwarded to
  /// `TileLayer(reset: …)` so the reload actually happens.
  final TileLayerBuilder builder;

  /// [LOCAL-789] Optional stream a PARENT fires when the map's laid-out size
  /// changes for a reason flutter_map may not emit a size event for in time —
  /// e.g. a banner above the map appearing/disappearing. Each emission forces a
  /// tile reload (coalesced to one per frame with the other triggers). The
  /// widget only listens; it never closes this stream (the parent owns it).
  final Stream<void>? externalReset;

  @override
  State<FirstLayoutTileLayer> createState() => _FirstLayoutTileLayerState();
}

class _FirstLayoutTileLayerState extends State<FirstLayoutTileLayer> {
  // Broadcast so the TileLayer's internal listen() never fights our listeners
  // and a late subscriber still works. Kept forwarded for forward-compat; the
  // actual reload is driven by [_epoch] (see the file header).
  final StreamController<void> _reset = StreamController<void>.broadcast();

  StreamSubscription<MapEvent>? _eventSub;
  StreamSubscription<void>? _externalSub;
  int? _controllerHashCode;
  bool _firedForCurrentSize = false;

  /// Bumped on every reload trigger; used as the wrapped TileLayer's
  /// [ValueKey], so a bump disposes the old TileLayer State and builds a fresh
  /// one that computes its tile range against the current camera and requests
  /// every visible tile.
  int _epoch = 0;

  // [LOCAL-789] One-per-frame debounce. Multiple triggers in the same frame
  // (first-layout post-frame + a size event + a LayoutBuilder constraint
  // change) collapse into a SINGLE rebuild against the final camera.
  bool _resetScheduled = false;

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
    _externalSub = widget.externalReset?.listen((_) => _scheduleReset());
  }

  /// Force a tile reload on the NEXT frame, at most once per frame. The
  /// post-frame timing guarantees the rebuild runs against the camera AFTER
  /// this frame's layout has settled the new size. Coalescing to one bump per
  /// frame also means a burst of triggers (first-layout + a size event + a
  /// LayoutBuilder constraint change) does not thrash the grid.
  void _scheduleReset() {
    if (_resetScheduled) return;
    _resetScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _resetScheduled = false;
      if (!mounted) return;
      // Fire the (forwarded) reset stream for forward-compat, then bump the
      // epoch so the TileLayer is rebuilt with a new key — the reload that
      // actually covers the whole current viewport.
      if (!_reset.isClosed) _reset.add(null);
      setState(() => _epoch++);
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // (Re)subscribe to the map's event stream when the controller changes. This
    // mirrors how TileLayer itself tracks the controller, so we never miss the
    // post-frame nonRotatedSizeChange that settles the first layout.
    final controller = MapController.of(context);
    if (_controllerHashCode != controller.hashCode) {
      _controllerHashCode = controller.hashCode;
      _eventSub?.cancel();
      _eventSub = controller.mapEventStream.listen(_onMapEvent);
    }
    // Cover the case where the size was already correct before we subscribed:
    // reload once after this frame so the TileLayer draws against the real
    // camera. Guarded so it only fires until the first size-based reload takes
    // over.
    if (!_firedForCurrentSize) {
      _scheduleReset();
    }
  }

  void _onMapEvent(MapEvent event) {
    // The layout just settled (or changed) its size: reload against the
    // now-correct camera. This is the event that was being missed.
    if (event is MapEventNonRotatedSizeChange) {
      _firedForCurrentSize = true;
      _scheduleReset();
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
    // The epoch keys the TileLayer so each reload trigger rebuilds it fresh.
    return KeyedSubtree(
      key: ValueKey<int>(_epoch),
      child: widget.builder(_reset.stream),
    );
  }
}
