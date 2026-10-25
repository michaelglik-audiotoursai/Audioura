// [LOCAL-763 / D711 addendum 1 — bug fix] A TileLayer that is guaranteed to
// draw its tiles from the FIRST settled layout, even when the map is created
// inside an IndexedStack + nested Navigator (the LOCAL-761 tab shell).
//
// THE BUG (Michael's retest 2026-10-25): on both phones the Home map opened
// with the tour/location markers but a BLANK map — the OSM tiles appeared only
// after the user pinched to zoom. Markers draw because MarkerLayer positions
// its points absolutely, independent of the tile grid; tiles do not.
//
// ROOT CAUSE (flutter_map 6.2.1): `TileLayer` computes its visible tile range
// from `MapCamera.of(context)` in `didChangeDependencies`, then keeps itself up
// to date by listening to `MapController.mapEventStream`. When the map is first
// laid out inside the IndexedStack tab shell, `FlutterMap` settles its
// non-rotated size via `setNonRotatedSizeWithoutEmittingEvent` (which updates
// the camera WITHOUT emitting) and schedules the `nonRotatedSizeChange` event
// for the NEXT frame (post-frame, so a setState in an onMapEvent callback does
// not throw during build). If the TileLayer's first `didChangeDependencies`
// ran against a pre-layout / zero-size camera, it computed an EMPTY tile range
// and loaded nothing; the later size-change event could then be missed on the
// broadcast stream, so the grid stayed empty until a user gesture produced a
// fresh MapEvent. That is the "tiles appear only after a zoom" Michael saw.
//
// THE FIX (flutter_map's own mechanism — not a timer hack): `TileLayer` accepts
// a `reset` stream; when it emits, the layer removes all tiles and reloads them
// against the CURRENT (correct-size) camera. This widget owns such a stream and
// fires it exactly when the map's non-rotated size settles to a real value —
// i.e. the moment the layout is known — by listening to the map event stream
// for `MapEventNonRotatedSizeChange`. It fires once more right after the first
// build (post-frame) to cover the case where the size was already correct
// before this layer subscribed. Both triggers are driven by map readiness /
// size, so there is no arbitrary delay.

import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_map/flutter_map.dart';

/// Builds the [TileLayer] for [FirstLayoutTileLayer], wiring in the [reset]
/// stream this widget drives. Callers pass their normal TileLayer arguments and
/// MUST forward [reset] to `TileLayer(reset: reset, …)`.
typedef TileLayerBuilder = TileLayer Function(Stream<void> reset);

/// A drop-in replacement for a `TileLayer` inside `FlutterMap.children` that
/// reloads its tiles the instant the map's layout size is known, fixing the
/// "blank map until the first zoom" bug on maps built inside an IndexedStack /
/// nested Navigator (LOCAL-763).
///
/// Usage — replace
/// ```dart
/// TileLayer(urlTemplate: '…', userAgentPackageName: '…')
/// ```
/// with
/// ```dart
/// FirstLayoutTileLayer(
///   builder: (reset) => TileLayer(
///     urlTemplate: '…', userAgentPackageName: '…', reset: reset),
/// )
/// ```
class FirstLayoutTileLayer extends StatefulWidget {
  const FirstLayoutTileLayer({super.key, required this.builder});

  /// Builds the wrapped [TileLayer]. The provided stream MUST be forwarded to
  /// `TileLayer(reset: …)` so the reload actually happens.
  final TileLayerBuilder builder;

  @override
  State<FirstLayoutTileLayer> createState() => _FirstLayoutTileLayerState();
}

class _FirstLayoutTileLayerState extends State<FirstLayoutTileLayer> {
  // Broadcast so the TileLayer's internal listen() never fights the size
  // listener, and so a late subscriber still works.
  final StreamController<void> _reset = StreamController<void>.broadcast();

  StreamSubscription<MapEvent>? _eventSub;
  int? _controllerHashCode;
  bool _firedForCurrentSize = false;

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
    // fire once after this frame so the TileLayer reloads against the real
    // camera. Guarded so it only fires until the first successful size-based
    // reset takes over.
    if (!_firedForCurrentSize) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && !_reset.isClosed) _reset.add(null);
      });
    }
  }

  void _onMapEvent(MapEvent event) {
    // The layout just settled (or changed) its size: reload tiles against the
    // now-correct camera. This is the event that was being missed.
    if (event is MapEventNonRotatedSizeChange) {
      _firedForCurrentSize = true;
      if (mounted && !_reset.isClosed) _reset.add(null);
    }
  }

  @override
  void dispose() {
    _eventSub?.cancel();
    _reset.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.builder(_reset.stream);
}
