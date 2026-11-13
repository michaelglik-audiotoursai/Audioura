// [LOCAL-908] The listener's "On the way" preferences.
//
//  * autoPlay (default on): after a stop, the leg's first topic starts after a
//    countdown. Off => the leg starts quiet; the listener taps "Play a topic".
//  * alwaysQuiet (default off): topics are off entirely. The player behaves
//    exactly as it did before topics existed.
//  * showEnglishNotice (default off = hide): for a translated tour whose topics
//    are English-only, hide the section; on => keep it and say "Topics
//    available in English".
library on_the_way_settings;

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class OnTheWaySettings extends ChangeNotifier {
  static const String autoPlayKey = 'otw_auto_play';
  static const String alwaysQuietKey = 'otw_always_quiet';
  static const String englishNoticeKey = 'otw_show_english_notice';

  bool _autoPlay = true;
  bool _alwaysQuiet = false;
  bool _showEnglishNotice = false;

  OnTheWaySettings({
    bool autoPlay = true,
    bool alwaysQuiet = false,
    bool showEnglishNotice = false,
  })  : _autoPlay = autoPlay,
        _alwaysQuiet = alwaysQuiet,
        _showEnglishNotice = showEnglishNotice;

  bool get autoPlay => _autoPlay;
  bool get alwaysQuiet => _alwaysQuiet;
  bool get showEnglishNotice => _showEnglishNotice;

  static Future<OnTheWaySettings> load() async {
    final p = await SharedPreferences.getInstance();
    return OnTheWaySettings(
      autoPlay: p.getBool(autoPlayKey) ?? true,
      alwaysQuiet: p.getBool(alwaysQuietKey) ?? false,
      showEnglishNotice: p.getBool(englishNoticeKey) ?? false,
    );
  }

  Future<void> setAutoPlay(bool v) => _set(autoPlayKey, v, () => _autoPlay = v);
  Future<void> setAlwaysQuiet(bool v) =>
      _set(alwaysQuietKey, v, () => _alwaysQuiet = v);
  Future<void> setShowEnglishNotice(bool v) =>
      _set(englishNoticeKey, v, () => _showEnglishNotice = v);

  Future<void> _set(String key, bool v, VoidCallback apply) async {
    apply();
    notifyListeners();
    try {
      final p = await SharedPreferences.getInstance();
      await p.setBool(key, v);
    } catch (_) {}
  }
}
