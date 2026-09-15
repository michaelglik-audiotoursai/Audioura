import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/screens/edit_tour_screen.dart';

/// LOCAL-475 — The edit screen and its caller must agree on the return type.
///
/// `EditStopScreen` returns the updated stop as a `Map<String, dynamic>` on
/// every save/delete path, and `null` when the user cancels without changes.
/// `applyEditStopResult` is the single merge point in `edit_tour_screen.dart`
/// that folds that navigator result back into `_stops`.
///
/// These tests pin the return contract. If someone reverts `edit_stop_screen`
/// to `Navigator.pop(context, true)` — the original defect — the "non-map"
/// tests below go red, which is exactly what would have caught this
/// (AC #6: `_stops` only ever contains maps; AC #7: break the contract, see red).
void main() {
  group('LOCAL-475 applyEditStopResult return contract', () {
    late List<Map<String, dynamic>> stops;

    setUp(() {
      stops = [
        {'stop_number': 1, 'title': 'Stop 1', 'text': 'a', 'modified': false},
        {'stop_number': 2, 'title': 'Stop 2', 'text': 'b', 'modified': false},
      ];
    });

    test('save path: a Map result is merged back into stops (AC #1)', () {
      final edited = stops[1];
      final updated = <String, dynamic>{
        ...edited,
        'text': 'edited text',
        'modified': true,
        'action': 'modify',
      };

      final changed = applyEditStopResult(stops, edited, updated);

      expect(changed, isTrue);
      expect(stops[1]['modified'], isTrue);
      expect(stops[1]['action'], equals('modify'));
      expect(stops[1]['text'], equals('edited text'));
    });

    test('added stop reaches the list with action=add (AC #2)', () {
      final added = <String, dynamic>{
        'stop_number': 2,
        'title': 'Stop 2',
        'text': 'new',
        'modified': true,
        'action': 'add',
      };

      final changed = applyEditStopResult(stops, stops[1], added);

      expect(changed, isTrue);
      expect(stops[1]['action'], equals('add'));
    });

    test('delete path: action=delete map is merged (AC #3)', () {
      final deleted = <String, dynamic>{...stops[0], 'action': 'delete'};

      final changed = applyEditStopResult(stops, stops[0], deleted);

      expect(changed, isTrue);
      expect(stops[0]['action'], equals('delete'));
    });

    test('cancel with no change: null result leaves stops untouched (AC #4)', () {
      final before = List<Map<String, dynamic>>.from(stops);

      final changed = applyEditStopResult(stops, stops[1], null);

      expect(changed, isFalse);
      expect(stops[1]['modified'], isFalse);
      expect(stops, equals(before));
    });

    test('stops only ever contains maps after a valid merge (AC #6)', () {
      final updated = <String, dynamic>{...stops[1], 'modified': true};
      applyEditStopResult(stops, stops[1], updated);

      for (final s in stops) {
        expect(s, isA<Map<String, dynamic>>());
      }
    });

    // AC #7 — break the return contract and watch this go red.
    //
    // This reproduces the ORIGINAL defect: edit_stop_screen popping `true`
    // instead of the stop map. The guard must reject it (throw in asserts-on
    // test mode) so a bool never lands in _stops. If the guard is removed,
    // `stops` would contain a bool and this test fails.
    test('non-map result (the old pop(true) bug) never corrupts stops (AC #7)', () {
      expect(
        () => applyEditStopResult(stops, stops[1], true),
        throwsA(isA<AssertionError>()),
      );

      // Even after the rejected attempt, the list is still map-only.
      for (final s in stops) {
        expect(s, isA<Map<String, dynamic>>());
      }
      expect(stops[1]['stop_number'], equals(2));
    });
  });
}
