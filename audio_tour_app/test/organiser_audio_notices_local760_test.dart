// test/organiser_audio_notices_local760_test.dart — LOCAL-760 / D708 / D709.
//
// Pure wording + decision helpers for the round-2 organiser-audio work:
//   * The Edit/Translate DISABLED ⓘ notices for an organiser-audio ("broadcast")
//     tour, owner vs member (build item 2).
//   * The translation-failure message: a server 403 translation_not_offered maps
//     to the D708 broadcast text; the ORIGINAL "older tour" case keeps its own
//     wording (build item 3).
// These are top-level pure functions (no BuildContext) so the exact wording is
// pinned by a golden test and shared by my_tours_screen and home_screen.
//
// RED on 127cd384: lib/utils/organiser_audio_notices.dart does not exist yet.
//
// Run: flutter test test/organiser_audio_notices_local760_test.dart

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/utils/organiser_audio_notices.dart';

void main() {
  group('LOCAL-760 Edit disabled ⓘ notice', () {
    test('member sees the "maintained on the organiser\'s own site" text', () {
      final msg = editDisabledNotice(isOwner: false);
      expect(msg, contains('Editing is not available for broadcast tours'));
      expect(msg, contains("organiser's own site"));
      // A member must NOT be told to open the builder.
      expect(msg.contains('Make a tour from your own audio'), isFalse);
    });

    test('owner is pointed at the builder on the community page', () {
      final msg = editDisabledNotice(isOwner: true);
      expect(msg, contains('Editing is not available for broadcast tours'));
      expect(msg, contains('Make a tour from your own audio'));
    });
  });

  group('LOCAL-760 Translate disabled ⓘ notice', () {
    test('D708 broadcast wording with the code', () {
      final msg = translateDisabledNotice();
      expect(msg, contains('Translation is not available for broadcast tours'));
      expect(msg, contains('the audio belongs to the organiser'));
      expect(msg, contains('D708'));
    });
  });

  group('LOCAL-760 translation-failure message', () {
    test('403 translation_not_offered → the D708 broadcast text', () {
      final msg = translationFailureMessage(
        translationNotOffered: true,
        failedLanguageNames: 'Russian',
      );
      expect(msg, contains('Translation is not available for broadcast tours'));
      expect(msg, contains('D708'));
      // The misleading "older tour" wording must be GONE for this case.
      expect(msg.contains('older tour'), isFalse);
    });

    test('ordinary per-language failure keeps the "older tour" wording', () {
      final msg = translationFailureMessage(
        translationNotOffered: false,
        failedLanguageNames: 'Russian',
      );
      expect(msg, contains('Russian'));
      expect(msg, contains('older tour'));
      expect(msg.contains('broadcast tours'), isFalse);
    });
  });
}
