// [LOCAL-877] The app-wide "what is the listener on right now" session.
//
// Why this exists. Audio plays inside the tour player's WebView, so the
// player screen owns the audio. Before this, nothing outside that screen knew a
// tour was playing, so (a) MainScreen reset the Listen tab on every resume,
// popping the player and stopping the audio, and (b) there was no way to show a
// play/pause bar on other screens or to offer "Resume <tour>, stop N" after a
// cold start.
//
// The session is the single source of truth for: which tour/stop, whether it is
// playing, the position, and the commands (play/pause/next/previous) the live
// player exposes. It is persisted (tour + stop + position) so a killed app can
// offer to resume.

import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Immutable view of the session, rendered by the persistent player bar.
@immutable
class PlayerSnapshot {
  final String tourPath;
  final String tourTitle;
  final String? tourId;
  final String? jobId;
  final String? serverTourId;
  final String? originalLanguage;
  final int stopIndex; // 0-based
  final int? totalStops;
  final String? stopName;
  final bool playing;
  final double positionSeconds;
  final double durationSeconds;

  /// True once audio has actually started for this session. A tour that was
  /// merely opened (never played) must not raise the bar.
  final bool started;

  /// True while a live player screen is mounted and can take commands. False
  /// for a session restored from disk after a cold start (bar shows "Resume").
  final bool live;

  const PlayerSnapshot({
    required this.tourPath,
    required this.tourTitle,
    this.tourId,
    this.jobId,
    this.serverTourId,
    this.originalLanguage,
    this.stopIndex = 0,
    this.totalStops,
    this.stopName,
    this.playing = false,
    this.positionSeconds = 0,
    this.durationSeconds = 0,
    this.started = false,
    this.live = false,
  });

  double get progress => durationSeconds > 0
      ? (positionSeconds / durationSeconds).clamp(0.0, 1.0)
      : 0.0;

  bool get hasNext => totalStops == null || stopIndex + 1 < totalStops!;
  bool get hasPrevious => stopIndex > 0;

  PlayerSnapshot copyWith({
    int? stopIndex,
    int? totalStops,
    String? stopName,
    bool? playing,
    double? positionSeconds,
    double? durationSeconds,
    bool? started,
    bool? live,
  }) =>
      PlayerSnapshot(
        tourPath: tourPath,
        tourTitle: tourTitle,
        tourId: tourId,
        jobId: jobId,
        serverTourId: serverTourId,
        originalLanguage: originalLanguage,
        stopIndex: stopIndex ?? this.stopIndex,
        totalStops: totalStops ?? this.totalStops,
        stopName: stopName ?? this.stopName,
        playing: playing ?? this.playing,
        positionSeconds: positionSeconds ?? this.positionSeconds,
        durationSeconds: durationSeconds ?? this.durationSeconds,
        started: started ?? this.started,
        live: live ?? this.live,
      );

  Map<String, dynamic> toJson() => {
        'tour_path': tourPath,
        'tour_title': tourTitle,
        'tour_id': tourId,
        'job_id': jobId,
        'server_tour_id': serverTourId,
        'original_language': originalLanguage,
        'stop_index': stopIndex,
        'total_stops': totalStops,
        'stop_name': stopName,
        'position': positionSeconds,
      };

  static PlayerSnapshot? fromJson(Map<String, dynamic> j) {
    final path = j['tour_path'];
    final title = j['tour_title'];
    if (path is! String || path.isEmpty || title is! String) return null;
    return PlayerSnapshot(
      tourPath: path,
      tourTitle: title,
      tourId: j['tour_id'] as String?,
      jobId: j['job_id'] as String?,
      serverTourId: j['server_tour_id'] as String?,
      originalLanguage: j['original_language'] as String?,
      stopIndex: (j['stop_index'] as num?)?.toInt() ?? 0,
      totalStops: (j['total_stops'] as num?)?.toInt(),
      stopName: j['stop_name'] as String?,
      positionSeconds: (j['position'] as num?)?.toDouble() ?? 0,
      started: true,
      live: false,
    );
  }
}

/// What the live player lets the bar do.
class PlayerCommands {
  final Future<void> Function() play;
  final Future<void> Function() pause;
  final Future<void> Function() next;
  final Future<void> Function() previous;

  /// Where the live player sits, so the bar can bring it back on screen
  /// (select that tab, pop back to this route). Null in unit tests.
  final NavigatorState? navigator;
  final Route<dynamic>? route;

  const PlayerCommands({
    required this.play,
    required this.pause,
    required this.next,
    required this.previous,
    this.navigator,
    this.route,
  });
}

class PlayerSession {
  PlayerSession._();
  static final PlayerSession instance = PlayerSession._();

  static const String _prefsKey = 'player_last_session_v1';

  /// Null = idle (no tour in progress): the bar is hidden.
  final ValueNotifier<PlayerSnapshot?> snapshot = ValueNotifier(null);

  /// How many players have attached (a re-init on resume would bump this).
  int attachCount = 0;

  PlayerCommands? _commands;
  Object? _owner;
  DateTime _lastPersist = DateTime.fromMillisecondsSinceEpoch(0);

  PlayerCommands? get commands => _commands;
  bool get hasLivePlayer => _commands != null;

  /// Whether the bar should be on screen.
  bool get barVisible {
    final s = snapshot.value;
    return s != null && s.started;
  }

  /// A player screen mounted. [owner] identifies it so a late dispose of an
  /// OLD player cannot clobber a NEW one.
  void attach({
    required Object owner,
    required PlayerSnapshot initial,
    required PlayerCommands commands,
  }) {
    attachCount++;
    _owner = owner;
    _commands = commands;
    final prev = snapshot.value;
    // Re-opening the same tour keeps "started" so the bar does not flicker.
    final sameTour = prev != null && prev.tourPath == initial.tourPath;
    snapshot.value = initial.copyWith(
      started: sameTour ? prev.started : initial.started,
      live: true,
    );
  }

  /// Live state from the player (stop changed / play / pause / tick).
  void update(
    Object owner, {
    int? stopIndex,
    int? totalStops,
    String? stopName,
    bool? playing,
    double? positionSeconds,
    double? durationSeconds,
  }) {
    if (!identical(owner, _owner)) return;
    final s = snapshot.value;
    if (s == null) return;
    final nowPlaying = playing ?? s.playing;
    final next = s.copyWith(
      stopIndex: stopIndex,
      totalStops: totalStops,
      stopName: stopName,
      playing: nowPlaying,
      positionSeconds: positionSeconds,
      durationSeconds: durationSeconds,
      started: s.started || nowPlaying,
    );
    snapshot.value = next;
    _persistThrottled(next, force: stopIndex != null && stopIndex != s.stopIndex);
  }

  /// The player screen went away (user backed out, or the widget was
  /// disposed). The audio is gone with it; keep the position so the bar can
  /// offer "Resume".
  void detach(Object owner) {
    if (!identical(owner, _owner)) return;
    _owner = null;
    _commands = null;
    final s = snapshot.value;
    if (s == null) return;
    final next = s.copyWith(playing: false, live: false);
    snapshot.value = next;
    if (next.started) _persist(next);
  }

  /// The tour finished or the listener dismissed the bar.
  Future<void> clear() async {
    snapshot.value = null;
    _owner = null;
    _commands = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_prefsKey);
  }

  /// Cold start: load the last tour/stop so the bar can offer "Resume".
  /// [pathExists] lets the caller drop a tour whose files are gone.
  Future<PlayerSnapshot?> restore({
    bool Function(String path)? pathExists,
  }) async {
    if (snapshot.value != null) return snapshot.value; // a live one wins.
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_prefsKey);
    if (raw == null || raw.isEmpty) return null;
    try {
      final j = jsonDecode(raw);
      if (j is! Map<String, dynamic>) return null;
      final s = PlayerSnapshot.fromJson(j);
      if (s == null) return null;
      if (pathExists != null && !pathExists(s.tourPath)) {
        await prefs.remove(_prefsKey);
        return null;
      }
      if (snapshot.value == null) snapshot.value = s;
      return s;
    } catch (_) {
      return null;
    }
  }

  void _persistThrottled(PlayerSnapshot s, {bool force = false}) {
    if (!s.started) return;
    final now = DateTime.now();
    if (!force && now.difference(_lastPersist) < const Duration(seconds: 5)) {
      return;
    }
    _persist(s);
  }

  void _persist(PlayerSnapshot s) {
    _lastPersist = DateTime.now();
    unawaited(SharedPreferences.getInstance().then(
      (p) => p.setString(_prefsKey, jsonEncode(s.toJson())),
    ));
  }

  @visibleForTesting
  Future<void> resetForTest() async {
    snapshot.value = null;
    _owner = null;
    _commands = null;
    _lastPersist = DateTime.fromMillisecondsSinceEpoch(0);
  }
}
