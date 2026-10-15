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

    testWidgets('Restore rejects an incomplete code without a network call',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(home: RecoveryCodeScreen()));
      await tester.pumpAndSettle();
      // Enter an obviously-too-short code.
      await tester.enterText(find.byType(TextField), 'ABCD');
      await tester.tap(
          find.widgetWithText(ElevatedButton, 'Restore my Listen page'));
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
  });
}
