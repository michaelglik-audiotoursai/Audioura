import 'package:shared_preferences/shared_preferences.dart';

import 'saved_tours_refresh.dart';

/// [LOCAL-787] The single writer of the `saved_tours` SharedPreferences list.
///
/// Michael (Pixel-7, Android 13) saw the Listen page stay empty for ~30 s after
/// "Tour downloaded successfully" (and after a translation), then fill. The
/// cause: `SavedToursRefresh` (LOCAL-750 C) is the signal MyToursScreen listens
/// to, but of the many writers of `saved_tours` only the community sync bumped
/// it. Every other writer left the Listen page to reload on some later,
/// unrelated event.
///
/// The fix is to funnel every write of `saved_tours` through [save], which
/// writes the list AND bumps [SavedToursRefresh] in the same step. No caller
/// has to remember to bump; forgetting is no longer possible. A grep test
/// (test/no_raw_saved_tours_write_test.dart) enforces that this file is the only
/// place in lib/ that calls `setStringList('saved_tours', …)`.
///
/// `bump()` only reaches the main isolate; a write from a background isolate
/// (background_service, background_tour_monitor) cannot notify the UI this way.
/// MyToursScreen therefore also reloads on resume and when the Listen tab is
/// selected, and `_loadTours` calls `prefs.reload()` first so a background
/// isolate's write is seen.
class SavedToursStore {
  SavedToursStore._();

  /// The SharedPreferences key holding the saved tours list.
  static const String key = 'saved_tours';

  /// Write the `saved_tours` list and signal the Listen page to reload.
  ///
  /// Use this instead of `prefs.setStringList('saved_tours', …)` everywhere in
  /// the app. [bumpRefresh] can be set false for a write that runs in a
  /// background isolate (where the bump cannot cross to the UI isolate anyway),
  /// but leaving it true there is harmless.
  static Future<bool> save(
    SharedPreferences prefs,
    List<String> tours, {
    bool bumpRefresh = true,
  }) async {
    final ok = await prefs.setStringList(key, tours);
    if (bumpRefresh) {
      SavedToursRefresh.instance.bump();
    }
    return ok;
  }
}
