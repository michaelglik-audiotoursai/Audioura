import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/playback_accumulator.dart';

/// LOCAL-670C — the playback-time accumulator must count ONLY genuinely played
/// time. Michael (2026-10-10): a stop is "listened" from REAL play time, so a
/// scrub to the end does not fake it. Four scenarios from the ticket:
///   straight play / seek-to-end / scrub / 1.5× speed.
///
/// The accumulator is pure and clock-driven by the test: we feed it wall-clock
/// instants so there is no timing flakiness.
void main() {
  // A 100-second stop; 80% = 80s is the listened threshold.
  const dur = 100.0;
  final t0 = DateTime.utc(2026, 10, 11, 1, 0, 0);
  DateTime at(double seconds) =>
      t0.add(Duration(milliseconds: (seconds * 1000).round()));

  group('straight play', () {
    test('playing through at 1× to >=80% counts as listened', () {
      final acc = PlaybackAccumulator(durationSeconds: dur);
      acc.onPlay(0, atWallClock: at(0));
      // Tick once per 10 real seconds, media advancing in lock-step.
      for (var s = 10.0; s <= 85.0; s += 10.0) {
        acc.onTick(s, atWallClock: at(s));
      }
      expect(acc.playedSeconds, greaterThanOrEqualTo(80.0));
      expect(acc.isListened, isTrue);
    });

    test('playing only halfway is NOT listened', () {
      final acc = PlaybackAccumulator(durationSeconds: dur);
      acc.onPlay(0, atWallClock: at(0));
      for (var s = 10.0; s <= 50.0; s += 10.0) {
        acc.onTick(s, atWallClock: at(s));
      }
      expect(acc.playedSeconds, lessThan(80.0));
      expect(acc.isListened, isFalse);
    });
  });

  group('seek-to-end', () {
    test('a seek straight to the end does NOT count as listened', () {
      final acc = PlaybackAccumulator(durationSeconds: dur);
      acc.onPlay(0, atWallClock: at(0));
      // Play 5 real seconds, then SEEK to 99s and let it end immediately.
      acc.onTick(5, atWallClock: at(5));
      acc.onSeek(99, atWallClock: at(6)); // jump — adds nothing
      acc.onEnded(100, atWallClock: at(6)); // ended right after the seek
      // Only the genuine ~5s was credited; reaching the end after a scrub must
      // NOT satisfy the 80% rule.
      expect(acc.playedSeconds, lessThan(80.0));
      expect(acc.isListened, isFalse);
    });

    test('end reached AFTER genuinely playing >=80% does count', () {
      final acc = PlaybackAccumulator(durationSeconds: dur);
      acc.onPlay(0, atWallClock: at(0));
      for (var s = 10.0; s <= 90.0; s += 10.0) {
        acc.onTick(s, atWallClock: at(s));
      }
      acc.onEnded(100, atWallClock: at(100));
      expect(acc.playedSeconds, greaterThanOrEqualTo(80.0));
      expect(acc.isListened, isTrue);
    });
  });

  group('scrub', () {
    test('repeated forward scrubs never accumulate to listened', () {
      final acc = PlaybackAccumulator(durationSeconds: dur);
      acc.onPlay(0, atWallClock: at(0));
      // Barely any real time passes, but currentTime leaps forward each tick —
      // classic scrubbing. Each leap is a seek, crediting nothing.
      acc.onSeek(30, atWallClock: at(1));
      acc.onSeek(60, atWallClock: at(2));
      acc.onSeek(95, atWallClock: at(3));
      acc.onTick(95, atWallClock: at(3)); // no media advance
      expect(acc.playedSeconds, lessThan(80.0));
      expect(acc.isListened, isFalse);
    });

    test('a big currentTime jump within one tick credits only the plausible slice', () {
      final acc = PlaybackAccumulator(durationSeconds: dur);
      acc.onPlay(0, atWallClock: at(0));
      // 2 real seconds elapse but currentTime jumps 50s → a seek embedded in a
      // tick. Only ~2s (plus tolerance) may be credited, never the 50s.
      acc.onTick(50, atWallClock: at(2));
      expect(acc.playedSeconds, lessThan(5.0));
      expect(acc.isListened, isFalse);
    });
  });

  group('1.5x speed', () {
    test('near-normal 1.5x playback DOES accumulate and reaches listened', () {
      final acc = PlaybackAccumulator(durationSeconds: dur);
      acc.onRateChange(1.5, positionSeconds: 0, atWallClock: at(0));
      acc.onPlay(0, atWallClock: at(0));
      // At 1.5×, 60 real seconds advance media by ~90s (> 80% of 100s).
      var media = 0.0;
      for (var wall = 5.0; wall <= 60.0; wall += 5.0) {
        media += 5.0 * 1.5; // media advances 7.5s per 5 real seconds
        acc.onTick(media, atWallClock: at(wall));
      }
      expect(acc.playedSeconds, greaterThanOrEqualTo(80.0));
      expect(acc.isListened, isTrue);
    });

    test('too-fast 3x playback does NOT accumulate', () {
      final acc = PlaybackAccumulator(durationSeconds: dur);
      acc.onRateChange(3.0, positionSeconds: 0, atWallClock: at(0));
      acc.onPlay(0, atWallClock: at(0));
      var media = 0.0;
      for (var wall = 5.0; wall <= 40.0; wall += 5.0) {
        media += 5.0 * 3.0; // 15s media per 5 real seconds
        acc.onTick(media, atWallClock: at(wall));
      }
      // Above the near-normal cap (1.5×) nothing is credited.
      expect(acc.playedSeconds, 0.0);
      expect(acc.isListened, isFalse);
    });
  });

  group('pause/resume', () {
    test('time while paused is not counted; resuming continues the tally', () {
      final acc = PlaybackAccumulator(durationSeconds: dur);
      acc.onPlay(0, atWallClock: at(0));
      acc.onTick(40, atWallClock: at(40)); // 40s genuine
      acc.onPause(40, atWallClock: at(41));
      // 10 minutes pass paused (position unchanged).
      acc.onPlay(40, atWallClock: at(641));
      acc.onTick(85, atWallClock: at(686)); // +45s genuine
      expect(acc.playedSeconds, greaterThanOrEqualTo(80.0));
      expect(acc.isListened, isTrue);
    });
  });
}
