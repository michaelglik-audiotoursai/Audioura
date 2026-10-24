// test/local754b_translate_hidden_test.dart — LOCAL-754B / D708 (app side).
//
// Translation of organiser-audio tours is NOT offered (D708). The Listen ⋮ menu
// hides Translate for a tour whose saved record carries source_kind =
// 'organiser_audio' (stamped at download from the server tour row); a generated
// / ordinary tour keeps Translate. The decision is the pure top-level function
// isOrganiserAudioTour(tour) in my_tours_screen.dart (same pattern as
// canEditTour), so the menu gates on it and this test exercises the exact
// production rule without pumping the screen.
//
// Run: flutter test test/local754b_translate_hidden_test.dart

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/screens/my_tours_screen.dart';

void main() {
  group('LOCAL-754B isOrganiserAudioTour — Translate hidden for organiser audio',
      () {
    test('organiser-audio tour is recognised', () {
      final tour = {'title': 'River Walk', 'source_kind': 'organiser_audio'};
      expect(isOrganiserAudioTour(tour), isTrue,
          reason: 'a source_kind of organiser_audio must hide Translate');
    });

    test('generated tour (no source_kind) is NOT organiser audio', () {
      final tour = {'title': 'Generated Tour'};
      expect(isOrganiserAudioTour(tour), isFalse);
    });

    test('other source_kind values are not organiser audio', () {
      expect(isOrganiserAudioTour({'source_kind': 'generated'}), isFalse);
      expect(isOrganiserAudioTour({'source_kind': ''}), isFalse);
      expect(isOrganiserAudioTour({'source_kind': 42}), isFalse);
    });

    test('whitespace around the marker is tolerated', () {
      expect(isOrganiserAudioTour({'source_kind': '  organiser_audio '}),
          isTrue);
    });
  });
}
