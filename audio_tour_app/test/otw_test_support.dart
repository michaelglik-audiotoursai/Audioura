// [LOCAL-908] Shared fakes + fixtures for the "On the way" tests.
import 'dart:convert';
import 'dart:io';

import 'package:audio_tour_app_dev/services/fillings_model.dart';
import 'package:audio_tour_app_dev/services/on_the_way_controller.dart';
import 'package:audio_tour_app_dev/services/on_the_way_settings.dart';

/// The payload LOCAL-907's own builder produced (fillings_payload.build_fillings
/// for a 4-stop car tour): leg 0 has 4 items (40 min), leg 1 none, leg 2 has 3.
FillingsPlan loadFixturePlan() {
  final f = File('test/fixtures/fillings_local907.json');
  return FillingsPlan.parse(jsonDecode(f.readAsStringSync()));
}

class FakeAudio implements TopicAudioOutput {
  final List<String> calls = [];
  FillingItem? playing;
  double? lastStart;
  @override
  Future<void> play(FillingItem item, {double startSec = 0}) async {
    calls.add('play:${item.segmentId}@$startSec');
    playing = item;
    lastStart = startSec;
  }

  @override
  Future<void> fadeOutAndStop(Duration fade) async {
    calls.add('fade:${fade.inMilliseconds}');
    playing = null;
  }

  @override
  Future<void> stop() async {
    calls.add('stop');
    playing = null;
  }
}

class Rig {
  final FakeAudio audio = FakeAudio();
  final List<int> stopsPlayed = [];
  final List<String> events = []; // "action:segment@at"
  late final OnTheWaySettings settings;
  late final OnTheWayController c;

  Rig({
    FillingsPlan? plan,
    bool autoPlay = true,
    bool alwaysQuiet = false,
    int totalStops = 4,
    String? tourLanguage,
    bool showEnglishNotice = false,
  }) {
    settings = OnTheWaySettings(
        autoPlay: autoPlay,
        alwaysQuiet: alwaysQuiet,
        showEnglishNotice: showEnglishNotice);
    c = OnTheWayController(
      plan: plan ?? loadFixturePlan(),
      settings: settings,
      audio: audio,
      playStop: (i) async => stopsPlayed.add(i),
      onEvent: (a, it, at) => events.add('$a:${it.segmentId}@${at.round()}'),
      totalStops: totalStops,
      tourLanguage: tourLanguage,
      stopTitle: (i) => ['Old Fort', 'Harbour', 'Market', 'Lighthouse'][i],
    );
  }

  bool _disposed = false;
  void dispose() {
    if (_disposed) return;
    _disposed = true;
    c.dispose();
    settings.dispose();
  }
}
