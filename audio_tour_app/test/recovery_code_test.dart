import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/utils/recovery_code.dart';
import 'package:audio_tour_app_dev/screens/recovery_code_screen.dart';

/// [LOCAL-695] Recovery code — UI helpers + the two-section screen.
///
/// The helpers mirror the server's normalization (strip hyphens/spaces,
/// uppercase, map I/L→1, O→0, U→V) so the app sends a clean code and gives
/// immediate shape feedback. The widget test proves both sections render and
/// the Restore button rejects an obviously-incomplete code before any network
/// call (so a typo never fires a request).
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('normalizeRecoveryCode', () {
    test('strips hyphens/spaces and uppercases', () {
      expect(normalizeRecoveryCode('abcd-efgh jkmn-pqrs'), 'ABCDEFGHJKMNPQRS');
    });
    test('maps the ambiguous characters I/L→1, O→0, U→V', () {
      expect(normalizeRecoveryCode('ILOU'), '110V');
    });
    test('null/empty → empty', () {
      expect(normalizeRecoveryCode(null), '');
      expect(normalizeRecoveryCode(''), '');
    });
  });

  group('isPlausibleRecoveryCode', () {
    test('accepts a well-formed 16-symbol code in any case/format', () {
      expect(isPlausibleRecoveryCode('ABCD-EFGH-JKMN-PQRS'), isTrue);
      expect(isPlausibleRecoveryCode('abcdefghjkmnpqrs'), isTrue);
    });
    test('rejects wrong length', () {
      expect(isPlausibleRecoveryCode('ABCD-EFGH'), isFalse);
      expect(isPlausibleRecoveryCode('ABCD-EFGH-JKMN-PQRS-EXTRA'), isFalse);
    });
    test('accepts look-alikes because they normalize into the alphabet', () {
      // I,L,O,U are mapped to 1,1,0,V — all in the canonical alphabet.
      expect(isPlausibleRecoveryCode('ILOU-EFGH-JKMN-PQRS'), isTrue);
    });
  });

  group('formatRecoveryCodeForDisplay', () {
    test('groups a 16-char code 4×4 with hyphens', () {
      expect(formatRecoveryCodeForDisplay('ABCDEFGHJKMNPQRS'),
          'ABCD-EFGH-JKMN-PQRS');
    });
    test('leaves a non-16 code as trimmed/uppercased', () {
      expect(formatRecoveryCodeForDisplay('  abcd  '), 'abcd');
    });
  });

  // [LOCAL-740 / B5] The "email it to myself" intent and share body carry the
  // code so the listener can keep it OFF the phone. The app only opens the
  // composer/share sheet — it never sends anything itself.
  group('recoveryEmailUri / recoveryShareBody (B5)', () {
    const code = 'ABCD-EFGH-JKMN-PQRS';

    test('the mailto intent carries the code and the fixed subject', () {
      final uri = recoveryEmailUri(code);
      expect(uri.scheme, 'mailto');
      // The whole query, decoded, contains the subject and the code.
      final decoded = Uri.decodeFull(uri.query);
      expect(decoded, contains('subject=My Audioura recovery code'));
      expect(decoded, contains(code));
    });

    test('the share body carries the code and the off-phone reason', () {
      final body = recoveryShareBody(code);
      expect(body, contains(code));
      expect(body, contains('outside your phone'));
      expect(body, contains('lost, stolen or broken'));
    });

    test('the email subject is exactly the ticket wording', () {
      expect(kRecoveryEmailSubject, 'My Audioura recovery code');
    });
  });

  group('RecoveryCodeScreen widget', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({'user_id': 'USER-TEST-0001'});
    });

    testWidgets('renders both sections', (tester) async {
      await tester.pumpWidget(const MaterialApp(home: RecoveryCodeScreen()));
      await tester.pumpAndSettle();
      expect(find.text('Your recovery code'), findsOneWidget);
      // "Restore my Listen page" appears twice: the section header and the
      // button label.
      expect(find.text('Restore my Listen page'), findsNWidgets(2));
      expect(find.widgetWithText(ElevatedButton, 'Create my recovery code'),
          findsOneWidget);
      // The explanation line is present.
      expect(find.textContaining('Save this code'), findsOneWidget);
    });

    // [LOCAL-740 / B5] The off-phone text is always on the screen (it does not
    // wait for a code), so a listener learns to keep the code elsewhere before
    // they even make one.
    testWidgets('shows the off-phone text', (tester) async {
      await tester.pumpWidget(const MaterialApp(home: RecoveryCodeScreen()));
      await tester.pumpAndSettle();
      expect(
          find.textContaining(
              'Keep this code outside this phone, for example email it to '
              'yourself.'),
          findsOneWidget);
      expect(
          find.textContaining(
              'restores your Listen page on a new phone: your tours, paid '
              'tours and articles.'),
          findsOneWidget);
    });

    testWidgets('Restore rejects an incomplete code without a network call',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(home: RecoveryCodeScreen()));
      await tester.pumpAndSettle();
      // Enter an obviously-too-short code.
      await tester.enterText(find.byType(TextField), 'ABCD');
      // [LOCAL-740] The off-phone text made the page taller; scroll the Restore
      // button into view before tapping it (the body is a ListView).
      final restoreBtn =
          find.widgetWithText(ElevatedButton, 'Restore my Listen page');
      await tester.ensureVisible(restoreBtn);
      await tester.pumpAndSettle();
      await tester.tap(restoreBtn);
      await tester.pump();
      expect(find.textContaining('does not look like a complete recovery code'),
          findsOneWidget);
    });

    testWidgets('offer-after-purchase banner shows when offered', (tester) async {
      await tester.pumpWidget(const MaterialApp(
          home: RecoveryCodeScreen(offeredAfterPurchase: true)));
      await tester.pumpAndSettle();
      expect(find.textContaining('first purchase'), findsOneWidget);
    });

    // [LOCAL-740 / B5] Once a code is on screen, the three ways to keep it off
    // the phone are all present: Copy, Email it to myself, Share — plus the
    // New-code explanation.
    testWidgets('shows Copy, Email it to myself and Share when a code exists',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(
          home: RecoveryCodeScreen(initialCode: 'ABCD-EFGH-JKMN-PQRS')));
      await tester.pumpAndSettle();
      expect(find.widgetWithText(ElevatedButton, 'Copy'), findsOneWidget);
      expect(find.widgetWithText(OutlinedButton, 'Email it to myself'),
          findsOneWidget);
      expect(find.widgetWithText(OutlinedButton, 'Share'), findsOneWidget);
      expect(find.widgetWithText(OutlinedButton, 'New code'), findsOneWidget);
      // The New-code explanation (B5 wording).
      expect(
          find.textContaining(
              'Replaces your code. The old code stops working.'),
          findsOneWidget);
      // The code itself is shown (the restore field also uses this string as a
      // placeholder hint, so there is more than one match).
      expect(find.text('ABCD-EFGH-JKMN-PQRS'), findsWidgets);
    });
  });
}
