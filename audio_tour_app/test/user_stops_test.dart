import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/utils/user_stops.dart';

/// LOCAL-523 — the pure stop-list mechanism and inline validation.
///
/// These pin the SINGLE mechanism (D564) the "name your stops" loop is built
/// on: add → renumber, delete → renumber, reorder → renumber, and the
/// LOCAL-521 warnings computed inline (AC #3). No widget is pumped — the whole
/// loop's rules are exercised as values (AC #4).
void main() {
  group('addStop', () {
    test('appends a stop with the editor stop-map shape and action=add (AC #2)', () {
      final stops = <Map<String, dynamic>>[];
      addStop(stops, 'The old lighthouse');

      expect(stops.length, 1);
      final s = stops.first;
      expect(s['stop_number'], 1);
      expect(s['title'], 'Stop 1');
      expect(s['text'], 'The old lighthouse');
      expect(s['audio_file'], 'audio_1.mp3');
      expect(s['action'], 'add');
      expect(s['editable'], true);
    });

    test('trims text and renumbers as stops are added in order', () {
      final stops = <Map<String, dynamic>>[];
      addStop(stops, '  First  ');
      addStop(stops, 'Second');
      addStop(stops, 'Third');

      expect(stops.map((s) => s['text']).toList(), ['First', 'Second', 'Third']);
      expect(stops.map((s) => s['stop_number']).toList(), [1, 2, 3]);
      expect(stops.map((s) => s['title']).toList(), ['Stop 1', 'Stop 2', 'Stop 3']);
    });

    test('rejects blank / whitespace-only text (no empty stop stored)', () {
      final stops = <Map<String, dynamic>>[];
      addStop(stops, '   ');
      expect(stops, isEmpty);
    });
  });

  group('removeStopAt', () {
    test('removes then renumbers so numbers stay 1..N (AC #2)', () {
      final stops = <Map<String, dynamic>>[];
      addStop(stops, 'A');
      addStop(stops, 'B');
      addStop(stops, 'C');

      removeStopAt(stops, 1); // remove B

      expect(stops.map((s) => s['text']).toList(), ['A', 'C']);
      expect(stops.map((s) => s['stop_number']).toList(), [1, 2]);
      expect(stops.map((s) => s['title']).toList(), ['Stop 1', 'Stop 2']);
      expect(stops.map((s) => s['audio_file']).toList(), ['audio_1.mp3', 'audio_2.mp3']);
    });

    test('out-of-range index is ignored', () {
      final stops = <Map<String, dynamic>>[];
      addStop(stops, 'A');
      removeStopAt(stops, 5);
      expect(stops.length, 1);
    });
  });

  group('reorderStops', () {
    test('moving a later stop earlier renumbers to new order (AC #2)', () {
      final stops = <Map<String, dynamic>>[];
      addStop(stops, 'A');
      addStop(stops, 'B');
      addStop(stops, 'C');

      // Move C (index 2) to the front — Flutter passes newIndex accounting for
      // the removed slot, matching ReorderableListView semantics.
      reorderStops(stops, 2, 0);

      expect(stops.map((s) => s['text']).toList(), ['C', 'A', 'B']);
      expect(stops.map((s) => s['stop_number']).toList(), [1, 2, 3]);
      expect(stops.map((s) => s['title']).toList(), ['Stop 1', 'Stop 2', 'Stop 3']);
    });

    test('moving an earlier stop later applies the -1 index adjustment', () {
      final stops = <Map<String, dynamic>>[];
      addStop(stops, 'A');
      addStop(stops, 'B');
      addStop(stops, 'C');

      // Drag A (0) to the end: ReorderableListView reports newIndex = length (3).
      reorderStops(stops, 0, 3);

      expect(stops.map((s) => s['text']).toList(), ['B', 'C', 'A']);
      expect(stops.map((s) => s['stop_number']).toList(), [1, 2, 3]);
    });
  });

  group('validateNewStopEntry (inline entry warnings — AC #3)', () {
    test('empty entry warns', () {
      final w = validateNewStopEntry('   ', const []);
      expect(w, isNotNull);
      expect(w!.field, 'entry');
    });

    test('duplicate (case-insensitive, trimmed) warns', () {
      final stops = <Map<String, dynamic>>[];
      addStop(stops, 'Harbour');
      final w = validateNewStopEntry('  harbour ', stops);
      expect(w, isNotNull);
      expect(w!.message, contains('already'));
    });

    test('adding past the maximum warns', () {
      final stops = <Map<String, dynamic>>[];
      for (var i = 0; i < kMaxUserStops; i++) {
        addStop(stops, 'Stop text $i');
      }
      final w = validateNewStopEntry('one too many', stops);
      expect(w, isNotNull);
      expect(w!.message, contains('maximum'));
    });

    test('a fresh, unique, in-bounds entry has no warning', () {
      final stops = <Map<String, dynamic>>[];
      addStop(stops, 'A');
      expect(validateNewStopEntry('B', stops), isNull);
    });
  });

  group('validateStopList / isStopListReady (inline list warnings — AC #3)', () {
    test('empty list is not ready and warns to add at least one', () {
      final stops = <Map<String, dynamic>>[];
      expect(isStopListReady(stops), isFalse);
      final warnings = validateStopList(stops);
      expect(warnings.any((w) => w.message.contains('at least one')), isTrue);
    });

    test('a single valid stop is ready (AC #2 — 1 stop is enough)', () {
      final stops = <Map<String, dynamic>>[];
      addStop(stops, 'Only stop');
      expect(isStopListReady(stops), isTrue);
      expect(validateStopList(stops), isEmpty);
    });

    test('duplicate names anywhere warn', () {
      // Bypass addStop's dedupe to construct the invalid state directly.
      final stops = <Map<String, dynamic>>[
        {'stop_number': 1, 'title': 'Stop 1', 'text': 'Pier', 'action': 'add'},
        {'stop_number': 2, 'title': 'Stop 2', 'text': 'pier', 'action': 'add'},
      ];
      final warnings = validateStopList(stops);
      expect(warnings.any((w) => w.message.contains('same name')), isTrue);
      expect(isStopListReady(stops), isFalse);
    });

    test('a blank stop that slipped in warns', () {
      final stops = <Map<String, dynamic>>[
        {'stop_number': 1, 'title': 'Stop 1', 'text': '  ', 'action': 'add'},
      ];
      final warnings = validateStopList(stops);
      expect(warnings.any((w) => w.message.contains('no name')), isTrue);
    });
  });

  group('stopTitlesForGeneration', () {
    test('returns the ordered trimmed names — the user selection', () {
      final stops = <Map<String, dynamic>>[];
      addStop(stops, 'First');
      addStop(stops, 'Second');
      reorderStops(stops, 1, 0); // Second, First

      expect(stopTitlesForGeneration(stops), ['Second', 'First']);
    });
  });
}
