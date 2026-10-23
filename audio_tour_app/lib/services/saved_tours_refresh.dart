import 'package:flutter/foundation.dart';

/// [LOCAL-750 C] A one-line signal that the saved_tours list changed because a
/// background/foreground community sync downloaded or refreshed a tour, so the
/// Listen page (MyToursScreen) reloads WITHOUT the user leaving and coming back.
///
/// It is a plain [ValueNotifier<int>] (a monotonically increasing tick) so there
/// are no plugins and a widget test can `bump()` and assert the Listen page
/// reloaded. [CommunityToursSync] bumps it after a run that downloaded or
/// refreshed anything; MyToursScreen listens and re-reads its list.
class SavedToursRefresh {
  SavedToursRefresh._();
  static final SavedToursRefresh instance = SavedToursRefresh._();

  /// Increments every time the saved_tours list changes under the app. A
  /// listener compares nothing — any change means "reload".
  final ValueNotifier<int> tick = ValueNotifier<int>(0);

  /// Signal that the saved_tours list changed (a sync downloaded/refreshed a
  /// tour). Safe to call from any isolate-bound context on the main isolate.
  void bump() {
    tick.value = tick.value + 1;
  }
}
