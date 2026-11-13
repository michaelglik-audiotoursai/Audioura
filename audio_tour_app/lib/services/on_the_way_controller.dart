// [LOCAL-908] The "On the way" state machine (D772).
//
// Between two stops the app can play region topics ("fillings", LOCAL-907). The
// listener must always know what is playing — a stop, or an optional topic on
// the way — and it must be safe while driving. This controller owns that state:
//
//   stop       a stop is the current thing ("Stop 3 of 8 · <title>")
//   countdown  a stop just ended; the leg's default topic starts in N s
//   topic      an optional topic is playing
//   quiet      on the way, nothing playing ("On the way to Stop 4 · quiet")
//
// It is plain Dart (a ChangeNotifier): audio, stop playback and events go
// through small interfaces so tests drive it with fakes and a fake clock. With
// no fillings, or "always quiet", it never leaves `stop` and does nothing — the
// player behaves exactly as before.
library on_the_way_controller;

import 'dart:async';

import 'package:flutter/foundation.dart';

import 'fillings_model.dart';
import 'on_the_way_settings.dart';

enum OtwMode { stop, countdown, topic, quiet }

/// What a hardware/OS "next" (Bluetooth, CarPlay, Android Auto, steering wheel)
/// should do.
enum MediaNextAction { nextStop, skipTopic, ignore }

/// The single mapping of a media-session "next" press (LOCAL-908 item 3).
///   * during a stop (or when topics are off): today's behaviour — next stop;
///   * during a topic or its countdown: skip the topic (next menu item; after
///     the last item, silence);
///   * in silence on the way: ignored, so a driver who pressed "next" once too
///     many times is not thrown into the next stop's narration early. (Arrival
///     starts the stop by itself; the screen can start it too.)
MediaNextAction mapMediaNext(OtwMode mode, {bool topicsActive = true}) {
  if (!topicsActive) return MediaNextAction.nextStop;
  switch (mode) {
    case OtwMode.stop:
      return MediaNextAction.nextStop;
    case OtwMode.countdown:
    case OtwMode.topic:
      return MediaNextAction.skipTopic;
    case OtwMode.quiet:
      return MediaNextAction.ignore;
  }
}

/// Plays a topic's audio. The real one drives an <audio> in the tour WebView.
abstract class TopicAudioOutput {
  Future<void> play(FillingItem item, {double startSec = 0});
  Future<void> fadeOutAndStop(Duration fade);
  Future<void> stop();
}

class ResumeOffer {
  final FillingItem item;
  final double positionSec;
  const ResumeOffer(this.item, this.positionSec);
}

typedef PlayStop = Future<void> Function(int stopIndex0);
typedef EventSink = void Function(String action, FillingItem item, double atSec);

class OnTheWayController extends ChangeNotifier {
  OnTheWayController({
    required FillingsPlan plan,
    required this.settings,
    required this.audio,
    required this.playStop,
    required this.onEvent,
    this.totalStops,
    this.stopTitle,
    this.countdownSeconds = 5,
    this.fade = const Duration(milliseconds: 600),
    this.maxArrivalWait = const Duration(seconds: 20),
    this.tourLanguage,
  }) : _plan = plan {
    settings.addListener(_onSettings);
  }

  final OnTheWaySettings settings;
  final TopicAudioOutput audio;
  final PlayStop playStop;
  final EventSink onEvent;
  /// Known once the page reports it; may arrive after construction.
  int? totalStops;
  final String? Function(int stopIndex0)? stopTitle;
  final int countdownSeconds;
  final Duration fade;
  final Duration maxArrivalWait;
  final String? tourLanguage;

  FillingsPlan _plan;
  OtwMode _mode = OtwMode.stop;
  int _currentStop = 0; // 0-based: the stop playing, or the one just left
  int _itemIndex = -1; // index in the leg of the topic playing / counting down
  FillingItem? _item;
  int _countdownLeft = 0;
  double _topicPos = 0;
  bool _arriving = false;
  ResumeOffer? _resume;
  final Set<int> _seen = <int>{};
  Timer? _countdownTimer;
  Timer? _arrivalTimer;
  bool _disposed = false;

  // ── read-only view ────────────────────────────────────────────────────────
  OtwMode get mode => _mode;
  int get currentStop => _currentStop;
  int get stopNumber => _currentStop + 1;
  int get nextStopNumber => _currentStop + 2;
  FillingItem? get item => _item;
  int get itemIndex => _itemIndex;
  int get countdownLeft => _countdownLeft;
  double get topicPositionSec => _topicPos;
  bool get arriving => _arriving;
  ResumeOffer? get resume => _resume;
  FillingsPlan get plan => _plan;

  /// Topics are enabled and there is something to play somewhere.
  bool get active => !settings.alwaysQuiet && !_plan.isEmpty;

  /// The leg after the current stop, when topics are on and it has items.
  FillingLeg? get leg => active ? _plan.legAfterStop(_currentStop + 1) : null;

  /// True when this tour's topics are not in the tour's language and the
  /// listener chose to keep them ("Topics available in English").
  bool get englishOnlyNotice =>
      settings.showEnglishNotice && _plan.hasForeign(tourLanguage);

  /// 0-based stop indices after which the player must HOLD the page's own
  /// auto-advance so the topic countdown can run instead.
  List<int> get holdAfterStops {
    if (!active) return const [];
    final out = <int>[];
    for (final l in _plan.legs) {
      final idx = l.afterStop - 1;
      if (totalStops == null || idx + 1 < totalStops!) out.add(idx);
    }
    return out;
  }

  /// The media-session "next" handler should be registered with the OS only
  /// while topics are the thing that "next" means.
  bool get mediaNextIsTopicSkip =>
      _mode == OtwMode.topic || _mode == OtwMode.countdown;

  MediaNextAction get mediaNext => mapMediaNext(_mode, topicsActive: active);

  // ── inputs from the player ────────────────────────────────────────────────
  void replacePlan(FillingsPlan plan) {
    _plan = plan;
    _notify();
  }

  /// A stop started playing (by itself, by a tap, by voice, or by arrival).
  void onStopStarted(int stopIndex0) {
    if (_mode == OtwMode.stop && stopIndex0 == _currentStop) return;
    final wasTopic = _mode == OtwMode.topic;
    _cancelTimers();
    _arriving = false;
    if (wasTopic) unawaited(audio.stop());
    _mode = OtwMode.stop;
    _currentStop = stopIndex0;
    _item = null;
    _itemIndex = -1;
    _notify();
  }

  /// A stop's audio reached its end. If a leg of topics follows, start the
  /// countdown (auto-play on) or go quiet (auto-play off).
  void onStopFinished(int stopIndex0) {
    if (!active || _mode != OtwMode.stop || stopIndex0 != _currentStop) return;
    if (totalStops != null && stopIndex0 + 1 >= totalStops!) return; // last
    final l = _plan.legAfterStop(stopIndex0 + 1);
    if (l == null || l.items.isEmpty) return;
    _seen.clear();
    if (settings.autoPlay) {
      _beginCountdown(0);
    } else {
      _goQuiet();
    }
  }

  /// The listener tapped "Skip" or pressed hardware "next" during a topic or
  /// its countdown.
  void skip() {
    final l = leg;
    if (l == null) return;
    if (_mode == OtwMode.countdown) {
      final from = _itemIndex;
      _countdownTimer?.cancel();
      _seen.add(l.items[from].segmentId);
      final n = _firstUnseen(l, from + 1);
      if (n == null) {
        _goQuiet();
      } else {
        _beginCountdown(n);
      }
    } else if (_mode == OtwMode.topic) {
      final cur = _item!;
      final from = _itemIndex;
      onEvent('skip', cur, _topicPos);
      _seen.add(cur.segmentId);
      unawaited(audio.fadeOutAndStop(const Duration(milliseconds: 250)));
      final n = _firstUnseen(l, from + 1);
      if (n == null) {
        _goQuiet();
      } else {
        _startTopic(l.items[n], n);
      }
    }
  }

  /// The listener picked item [index] from the menu.
  void choose(int index) {
    final l = leg;
    if (l == null || index < 0 || index >= l.items.length) return;
    if (_mode == OtwMode.stop) return;
    final it = l.items[index];
    _cancelCountdown();
    onEvent('choose', it, 0);
    _startTopic(it, index);
  }

  /// "Quiet" in the menu: stop the topic, stay quiet until the next stop.
  void chooseQuiet() {
    if (_mode == OtwMode.stop) return;
    if (_mode == OtwMode.topic) {
      unawaited(audio.fadeOutAndStop(const Duration(milliseconds: 300)));
    }
    _goQuiet();
  }

  /// The one-tap "Play a topic" button (in silence): the leg's default topic —
  /// the first not yet heard, else the first.
  void playTopic() {
    final l = leg;
    if (l == null || _mode == OtwMode.stop || _mode == OtwMode.topic) return;
    _cancelCountdown();
    final n = _firstUnseen(l, 0) ?? 0;
    _startTopic(l.items[n], n);
  }

  /// "Resume <topic> later": continue the topic that arrival cut off.
  void resumeLater() {
    final r = _resume;
    if (r == null || _mode == OtwMode.stop || _mode == OtwMode.topic) return;
    _cancelCountdown();
    _resume = null;
    final l = leg;
    var idx = -1;
    if (l != null) {
      idx = l.items.indexWhere((i) => i.segmentId == r.item.segmentId);
    }
    _startTopic(r.item, idx, startSec: r.positionSec);
  }

  void onTopicPosition(double sec) {
    if (_mode != OtwMode.topic) return;
    _topicPos = sec;
    // No notify: position ticks are frequent and nothing on screen shows them.
  }

  /// The topic audio played to its end.
  void onTopicEnded() {
    if (_mode != OtwMode.topic) return;
    final cur = _item!;
    final l = leg;
    onEvent('finish', cur, _topicPos > 0 ? _topicPos : cur.minutes * 60);
    _seen.add(cur.segmentId);
    if (_resume?.item.segmentId == cur.segmentId) _resume = null;
    if (_arriving) {
      _completeArrival();
      return;
    }
    if (l == null) {
      _goQuiet();
      return;
    }
    final n = _firstUnseen(l, _itemIndex + 1);
    if (n != null && settings.autoPlay) {
      _beginCountdown(n);
    } else {
      _goQuiet();
    }
  }

  /// The topic audio could not play (offline, bad URL). Silence, no event.
  void onTopicFailed() {
    if (_mode != OtwMode.topic) return;
    if (_arriving) {
      _completeArrival();
      return;
    }
    _goQuiet();
  }

  /// GPS reached stop [stopIndex0] (StopProximityDetector). During a topic:
  /// fade out at the end of the current sentence (or at once when no sentence
  /// timestamps are known), play the stop, and offer to resume the topic on the
  /// next leg.
  void onArrival(int stopIndex0) {
    if (!active || _mode == OtwMode.stop || stopIndex0 <= _currentStop) return;
    if (_arriving) return;
    _pendingArrival = stopIndex0;
    if (_mode == OtwMode.topic) {
      final cur = _item!;
      _resume = ResumeOffer(cur, _topicPos);
      _arriving = true;
      final wait = _untilSentenceEnd(cur, _topicPos);
      _notify();
      if (wait == null || wait <= Duration.zero) {
        _completeArrival();
      } else {
        _arrivalTimer = Timer(wait, _completeArrival);
      }
    } else {
      _cancelTimers();
      _arriveAt(stopIndex0);
    }
  }

  int? _pendingArrival;

  // ── internals ─────────────────────────────────────────────────────────────
  Duration? _untilSentenceEnd(FillingItem it, double pos) {
    for (final e in it.sentenceEnds) {
      if (e >= pos) {
        final ms = ((e - pos) * 1000).round();
        final d = Duration(milliseconds: ms);
        return d > maxArrivalWait ? null : d;
      }
    }
    return null;
  }

  Future<void> _completeArrival() async {
    _arrivalTimer?.cancel();
    final target = _pendingArrival;
    if (target == null) return;
    _pendingArrival = null;
    if (_mode == OtwMode.topic) {
      try {
        await audio.fadeOutAndStop(fade);
      } catch (_) {}
    }
    if (_disposed) return;
    _arriveAt(target);
  }

  void _arriveAt(int stopIndex0) {
    _arriving = false;
    _cancelTimers();
    _mode = OtwMode.stop;
    _currentStop = stopIndex0;
    _item = null;
    _itemIndex = -1;
    _notify();
    unawaited(playStop(stopIndex0));
  }

  int? _firstUnseen(FillingLeg l, int from) {
    for (var i = from < 0 ? 0 : from; i < l.items.length; i++) {
      if (!_seen.contains(l.items[i].segmentId)) return i;
    }
    return null;
  }

  void _beginCountdown(int index) {
    final l = leg;
    if (l == null) return;
    _cancelTimers();
    _mode = OtwMode.countdown;
    _itemIndex = index;
    _item = l.items[index];
    _countdownLeft = countdownSeconds;
    _notify();
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (t) {
      _countdownLeft--;
      if (_countdownLeft <= 0) {
        t.cancel();
        final cur = _item;
        final lg = leg;
        if (cur != null && lg != null && _mode == OtwMode.countdown) {
          _startTopic(cur, _itemIndex);
        }
      } else {
        _notify();
      }
    });
  }

  void _startTopic(FillingItem it, int index, {double startSec = 0}) {
    _cancelTimers();
    _mode = OtwMode.topic;
    _item = it;
    _itemIndex = index;
    _topicPos = startSec;
    _seen.add(it.segmentId);
    _notify();
    onEvent('start', it, startSec);
    unawaited(() async {
      try {
        await audio.play(it, startSec: startSec);
      } catch (_) {
        onTopicFailed();
      }
    }());
  }

  void _goQuiet() {
    _cancelTimers();
    _arriving = false;
    _mode = OtwMode.quiet;
    _item = null;
    _itemIndex = -1;
    _notify();
  }

  void _cancelCountdown() {
    _countdownTimer?.cancel();
    _countdownTimer = null;
  }

  void _cancelTimers() {
    _cancelCountdown();
    _arrivalTimer?.cancel();
    _arrivalTimer = null;
  }

  void _onSettings() {
    if (settings.alwaysQuiet && _mode != OtwMode.stop) {
      // Topics turned off entirely while on the way: stop and look as before.
      final wasTopic = _mode == OtwMode.topic;
      _cancelTimers();
      _arriving = false;
      if (wasTopic) unawaited(audio.fadeOutAndStop(const Duration(milliseconds: 300)));
      _mode = OtwMode.stop;
      _item = null;
      _itemIndex = -1;
    }
    _notify();
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _cancelTimers();
    settings.removeListener(_onSettings);
    super.dispose();
  }
}
