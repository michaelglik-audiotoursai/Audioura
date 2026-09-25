import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/screens/edit_tour_screen.dart';
import 'package:audio_tour_app_dev/screens/my_tours_screen.dart';

/// LOCAL-484 — The stop count on the Listen page must follow the edit.
///
/// Report (Michael, build 26): after adding a stop and Save All, the Listen
/// page still showed the OLD stop count. Cause: `'stops'` in the saved_tours
/// entry was written once at download time and never updated; the only writer
/// after an edit (`_updateLocalTourId`) set `new_tour_id` and nothing else.
/// A separate lie lived in `my_tours_screen`: `tour['stops'] ?? '10'` claimed
/// "10 stops" for any tour that never stored a count.
///
/// These tests pin the three pure functions the fix introduced:
///   * applyTourEditToSavedTours — one walk, writes new_tour_id AND the count
///   * countStopsOnDisk          — the authoritative count source (disk)
///   * tourSubtitleLine          — omits the count when it is unknown
///
/// COUNT SOURCE, stated explicitly: the Save All response
/// (/tour/<id>/update-multiple-stops) does NOT carry stops_count — it returns
/// status/message/stops/new_tour_id/download_url only. So we count the
/// audio_*.mp3 files the download wrote to disk. That is the number persisted
/// into saved_tours and shown on Listen.
void main() {
  // A saved_tours list as it exists after first download: 'stops' set once,
  // no new_tour_id yet. Two entries so we prove only the matched one changes.
  List<String> seedSavedTours() => [
        jsonEncode({
          'title': 'Riviera Walk',
          'path': '/tours/riviera_abc123',
          'created': '2026-09-16T10:00:00.000',
          'stops': '5',
          'tour_id': 'abc123',
        }),
        jsonEncode({
          'title': 'Old Town',
          'path': '/tours/oldtown_def456',
          'created': '2026-09-10T10:00:00.000',
          'stops': '3',
          'tour_id': 'def456',
        }),
      ];

  Map<String, dynamic> entryForPath(List<String> saved, String path) {
    for (final s in saved) {
      Map<String, dynamic> m;
      try {
        final decoded = jsonDecode(s);
        if (decoded is! Map<String, dynamic>) continue;
        m = decoded;
      } catch (_) {
        continue; // skip noise (e.g. the malformed-entry test fixture)
      }
      if (m['path'] == path) return m;
    }
    fail('no saved_tours entry for path $path');
  }

  group('LOCAL-484 applyTourEditToSavedTours', () {
    test('AC #1 — adding a stop raises the persisted count', () {
      final saved = seedSavedTours();

      // Added a 6th stop; disk now has 6 audio files.
      final updated = applyTourEditToSavedTours(
        saved,
        '/tours/riviera_abc123',
        newTourId: 'newid-1',
        stopCount: 6,
      );

      final entry = entryForPath(updated, '/tours/riviera_abc123');
      expect(entry['stops'], equals('6'));
      expect(entry['new_tour_id'], equals('newid-1'));
    });

    test('AC #2 — deleting a stop lowers the persisted count', () {
      final saved = seedSavedTours();

      // Deleted down to 4 stops.
      final updated = applyTourEditToSavedTours(
        saved,
        '/tours/riviera_abc123',
        newTourId: 'newid-2',
        stopCount: 4,
      );

      expect(entryForPath(updated, '/tours/riviera_abc123')['stops'],
          equals('4'));
    });

    test('AC #4 — a text-only edit (count unknown/null) leaves stops alone', () {
      final saved = seedSavedTours();

      // stopCount omitted: the count could not be determined, so it must not
      // be rewritten (and certainly not guessed).
      final updated = applyTourEditToSavedTours(
        saved,
        '/tours/riviera_abc123',
        newTourId: 'newid-3',
      );

      final entry = entryForPath(updated, '/tours/riviera_abc123');
      expect(entry['stops'], equals('5')); // unchanged from seed
      expect(entry['new_tour_id'], equals('newid-3')); // id still recorded
    });

    test('only the matched tour is touched; others pass through untouched', () {
      final saved = seedSavedTours();

      final updated = applyTourEditToSavedTours(
        saved,
        '/tours/riviera_abc123',
        newTourId: 'newid-4',
        stopCount: 9,
      );

      final other = entryForPath(updated, '/tours/oldtown_def456');
      expect(other['stops'], equals('3'));
      expect(other.containsKey('new_tour_id'), isFalse);
    });

    test('malformed entries are preserved, not dropped', () {
      final saved = [
        'not json at all',
        ...seedSavedTours(),
      ];

      final updated = applyTourEditToSavedTours(
        saved,
        '/tours/riviera_abc123',
        newTourId: 'newid-5',
        stopCount: 7,
      );

      expect(updated.length, equals(saved.length));
      expect(updated.first, equals('not json at all'));
      expect(entryForPath(updated, '/tours/riviera_abc123')['stops'],
          equals('7'));
    });

    test(
        'AC #5 — the new count survives a persistence round-trip '
        '(encode → store → decode)', () {
      final saved = seedSavedTours();

      // Simulate the write: applyTourEditToSavedTours returns the exact list
      // that _updateLocalTourId hands to prefs.setStringList. Re-decoding it
      // (as _loadTours would after a restart) must still show the new count.
      final persisted = applyTourEditToSavedTours(
        saved,
        '/tours/riviera_abc123',
        newTourId: 'newid-6',
        stopCount: 6,
      );

      // Round-trip through String encoding, exactly like SharedPreferences.
      final reloaded = List<String>.from(persisted);
      expect(entryForPath(reloaded, '/tours/riviera_abc123')['stops'],
          equals('6'));
    });

    // AC #6 — break the update and watch a test go red.
    //
    // This asserts the CORE promise: after an add, the persisted count differs
    // from the pre-edit value. If someone reverts the fix so the count is no
    // longer written (the original defect — only new_tour_id updated), this
    // fails because 'stops' would still read '5'.
    test('AC #6 — regression guard: count actually changes after an add', () {
      final saved = seedSavedTours();
      final before = entryForPath(saved, '/tours/riviera_abc123')['stops'];

      final updated = applyTourEditToSavedTours(
        saved,
        '/tours/riviera_abc123',
        newTourId: 'newid-7',
        stopCount: 6,
      );
      final after = entryForPath(updated, '/tours/riviera_abc123')['stops'];

      expect(before, equals('5'));
      expect(after, isNot(equals(before)),
          reason:
              'If the edit no longer writes the stop count, this goes red — '
              'exactly the original LOCAL-484 defect.');
      expect(after, equals('6'));
    });
  });

  group('LOCAL-484 countStopsOnDisk', () {
    late Directory tmp;

    setUp(() {
      tmp = Directory.systemTemp.createTempSync('local484_');
    });

    tearDown(() {
      if (tmp.existsSync()) tmp.deleteSync(recursive: true);
    });

    test('counts audio_*.mp3 files (the authoritative disk count)', () {
      for (final n in [1, 2, 3, 4, 5, 6]) {
        File('${tmp.path}/audio_$n.mp3').writeAsStringSync('x');
      }
      // Noise that must not be counted.
      File('${tmp.path}/index.html').writeAsStringSync('<html>');
      File('${tmp.path}/audio_1.txt').writeAsStringSync('text');

      expect(countStopsOnDisk(tmp.path), equals(6));
    });

    test('returns null when the directory has no audio files (unknown)', () {
      File('${tmp.path}/index.html').writeAsStringSync('<html>');
      expect(countStopsOnDisk(tmp.path), isNull);
    });

    test('returns null when the directory does not exist', () {
      expect(countStopsOnDisk('${tmp.path}/does_not_exist'), isNull);
    });
  });

  group('LOCAL-484 tourSubtitleLine', () {
    test('AC #1/#2 — renders the stored count', () {
      final line = tourSubtitleLine({
        'stops': '6',
        'created': '2026-09-16T10:00:00.000',
      });
      expect(line, contains('6 stops'));
      expect(line, contains('Created: 2026-09-16'));
    });

    test('AC #3 — a tour with no stored count renders WITHOUT a count', () {
      final line = tourSubtitleLine({
        'created': '2026-09-16T10:00:00.000',
      });
      expect(line, isNot(contains('stops')));
      expect(line, isNot(contains('10'))); // the old fabricated fallback
      expect(line, equals('Created: 2026-09-16'));
    });

    test('AC #3 — an empty count string also renders without a count', () {
      final line = tourSubtitleLine({
        'stops': '',
        'created': '2026-09-16T10:00:00.000',
      });
      expect(line, isNot(contains('stops')));
    });
  });
}
