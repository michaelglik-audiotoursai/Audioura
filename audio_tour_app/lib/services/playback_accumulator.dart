import 'dart:math' as math;

/// Accumulates the ACTUAL playback time of a single audio element so a stop can
/// be verified as "listened" LOCALLY, offline (LOCAL-670C).
///
/// Michael (2026-10-10): "Audioura must do some storage and verification
/// locally, and send info to a server only that was valid and when it had
/// connection." The 670B rule — a stop counts once the audio crosses 80% — is
/// wrong offline because a listener can simply SCRUB to 85% without hearing a
/// word. 670C counts only time that was really played:
///
///   * accumulate media-time only while the element is PLAYING,
///   * only at NORMAL or NEAR-NORMAL speed (≤ [maxCountedRate], so 1.5× counts
///     but a 3× skim does not),
///   * a SEEK / SCRUB (a jump in currentTime far larger than the wall-clock
///     time that elapsed) adds NOTHING — only the real elapsed slice is kept.
///
/// A stop is LISTENED when the accumulated played time reaches
/// [listenedFraction] (80%) of the audio's duration, OR playback reaches the
/// end having already played ≥ [listenedFraction] (so a listener who played
/// 80%+ and let it run to the end is counted even if the last ticks were
/// sparse).
///
/// This class is PURE: it holds no timers and does no I/O. The player feeds it
/// discrete events (play/pause/seek/rateChange and periodic position ticks);
/// the WebView bridge or a test drives those. That keeps the verification rule
/// unit-testable in isolation (see test/playback_accumulator_test.dart).
class PlaybackAccumulator {
  /// Fraction of the stop's duration that must be genuinely played to count as
  /// listened (0.80 — mirrors 670B's threshold and the server gate).
  static const double listenedFraction = 0.80;

  /// Fastest playback rate that still counts as "near-normal" and accumulates
  /// time. 1.5× counts (common speed-listening); anything faster does not add
  /// time, matching "normal or near-normal speed".
  static const double maxCountedRate = 1.5;

  /// Tolerance (seconds) added to the expected media advance when deciding
  /// whether a currentTime change is normal playback vs a seek. Covers tick
  /// jitter, decode hiccups and coarse timer resolution without ever letting a
  /// real scrub slip through: a seek jumps far more than one tick's worth.
  static const double _seekToleranceSeconds = 1.0;

  final double durationSeconds;
  final double _listenedThresholdSeconds;

  double _playedSeconds = 0.0;
  bool _playing = false;
  double _rate = 1.0;

  /// The last known media position (currentTime) and the wall-clock instant we
  /// observed it, used to size the next accumulation slice and to detect seeks.
  double? _lastPositionSeconds;
  DateTime? _lastWallClock;

  bool _reachedEnd = false;

  PlaybackAccumulator({required this.durationSeconds})
      : assert(durationSeconds > 0, 'durationSeconds must be > 0'),
        _listenedThresholdSeconds = durationSeconds * listenedFraction;

  /// Total media-time genuinely played so far (seconds).
  double get playedSeconds => _playedSeconds;

  /// Fraction of the stop genuinely played so far (0..1, clamped).
  double get playedFraction =>
      durationSeconds <= 0 ? 0.0 : math.min(1.0, _playedSeconds / durationSeconds);

  /// Whether the stop is verified LISTENED: ≥ 80% genuinely played, OR the end
  /// was reached after ≥ 80% had been played.
  bool get isListened {
    if (_playedSeconds + 1e-6 >= _listenedThresholdSeconds) return true;
    return _reachedEnd && _playedSeconds + 1e-6 >= _listenedThresholdSeconds;
  }

  /// Playback started (or resumed) at [atWallClock] with position [positionSeconds].
  void onPlay(double positionSeconds, {required DateTime atWallClock}) {
    _playing = true;
    _lastPositionSeconds = positionSeconds;
    _lastWallClock = atWallClock;
  }

  /// Playback paused/stopped. First credits the slice up to this point.
  void onPause(double positionSeconds, {required DateTime atWallClock}) {
    _advance(positionSeconds, atWallClock);
    _playing = false;
    _lastPositionSeconds = positionSeconds;
    _lastWallClock = atWallClock;
  }

  /// The playback rate changed (e.g. the user picked 1.5×). Credits the slice
  /// played at the OLD rate first, then adopts the new rate for subsequent
  /// slices.
  void onRateChange(double rate,
      {required double positionSeconds, required DateTime atWallClock}) {
    if (_playing) {
      _advance(positionSeconds, atWallClock);
    }
    _rate = rate;
    _lastPositionSeconds = positionSeconds;
    _lastWallClock = atWallClock;
  }

  /// A periodic position report while playing (the WebView's `timeupdate`).
  /// Credits only the slice consistent with real elapsed time; a jump far
  /// beyond that (a seek/scrub) credits nothing and simply re-anchors.
  void onTick(double positionSeconds, {required DateTime atWallClock}) {
    if (_playing) {
      _advance(positionSeconds, atWallClock);
    }
    _lastPositionSeconds = positionSeconds;
    _lastWallClock = atWallClock;
  }

  /// The user seeked/scrubbed to [positionSeconds]. Adds nothing; just
  /// re-anchors so the next real slice is measured from here.
  void onSeek(double positionSeconds, {required DateTime atWallClock}) {
    _lastPositionSeconds = positionSeconds;
    _lastWallClock = atWallClock;
  }

  /// Playback reached the end of the media. Credits the final slice, then marks
  /// the end reached (which, combined with ≥ 80% already played, counts).
  void onEnded(double positionSeconds, {required DateTime atWallClock}) {
    if (_playing) {
      _advance(positionSeconds, atWallClock);
    }
    _playing = false;
    _reachedEnd = true;
    _lastPositionSeconds = positionSeconds;
    _lastWallClock = atWallClock;
  }

  /// Credit the slice between the last anchor and ([positionSeconds],
  /// [atWallClock]) IF it looks like genuine, near-normal-speed playback.
  void _advance(double positionSeconds, DateTime atWallClock) {
    final lastPos = _lastPositionSeconds;
    final lastWall = _lastWallClock;
    if (lastPos == null || lastWall == null) {
      _lastPositionSeconds = positionSeconds;
      _lastWallClock = atWallClock;
      return;
    }

    final mediaDelta = positionSeconds - lastPos;
    // Backwards jump (rewind) or no movement: nothing to credit.
    if (mediaDelta <= 0) return;

    // Too fast to count as near-normal listening.
    if (_rate > maxCountedRate) return;

    final wallDelta =
        atWallClock.difference(lastWall).inMicroseconds / 1e6;
    if (wallDelta <= 0) {
      // No wall time elapsed but media advanced → a seek. Credit nothing.
      return;
    }

    // How much media SHOULD advance in this wall slice at the current rate,
    // plus a small tolerance for jitter. If the media advanced by much more,
    // the surplus is a seek — credit only the plausible real portion.
    final expectedMedia = wallDelta * _rate + _seekToleranceSeconds;
    final credited = math.min(mediaDelta, expectedMedia);
    if (credited > 0) {
      _playedSeconds += credited;
    }
  }
}
