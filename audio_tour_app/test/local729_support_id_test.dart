// [LOCAL-729 / D692] Flutter-side tests for the About Support ID — the public
// AU-XXXX device alias and its Copy button. These test the SupportIdRow widget
// and the deterministic local alias in isolation (no network, no plugins, no
// heavyweight About screen), the same way LOCAL-728 tested the notice widget.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/widgets/support_id_row.dart';

void main() {
  group('LOCAL-729 — Support ID alias (deterministic, well-formed)', () {
    test('computeLocalSupportId returns a well-formed AU-XXXX', () {
      final sid = computeLocalSupportId('USER-12345678');
      expect(sid.startsWith('AU-'), isTrue);
      expect(sid.length, 7);
      expect(isSupportIdShape(sid), isTrue);
    });

    test('it is deterministic — same device id → same alias', () {
      expect(computeLocalSupportId('USER-abc'),
          computeLocalSupportId('USER-abc'));
    });

    test('it never uses the ambiguous characters O/I/L/0/1', () {
      for (final uid in ['USER-1', 'USER-2', 'USER-zzz', 'USER-hello',
          'USER-00000001', 'USER-99999999']) {
        final body = computeLocalSupportId(uid).substring(3);
        for (final c in ['O', 'I', 'L', '0', '1']) {
          expect(body.contains(c), isFalse,
              reason: '$uid → ${computeLocalSupportId(uid)} must avoid $c');
        }
      }
    });

    test('different device ids generally give different aliases', () {
      final a = computeLocalSupportId('USER-aaaaaaaa');
      final b = computeLocalSupportId('USER-bbbbbbbb');
      expect(a == b, isFalse);
    });

    test('isSupportIdShape rejects a raw device id and malformed values', () {
      expect(isSupportIdShape('USER-12345678'), isFalse);
      expect(isSupportIdShape('AU-7K3Q'), isTrue);
      expect(isSupportIdShape('AU-7K3'), isFalse);    // too short
      expect(isSupportIdShape('AU-7K3QX'), isFalse);  // too long
      expect(isSupportIdShape('AU-7I0Q'), isFalse);   // ambiguous chars
    });
  });

  group('LOCAL-729 — SupportIdRow widget (shows the alias + Copy)', () {
    testWidgets('renders the Support ID label and value', (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(body: SupportIdRow(supportId: 'AU-7K3Q')),
      ));
      await tester.pumpAndSettle();
      expect(find.text('Support ID:'), findsOneWidget);
      expect(find.byKey(const Key('support_id_value')), findsOneWidget);
      expect(find.text('AU-7K3Q'), findsOneWidget);
      expect(find.byKey(const Key('support_id_copy')), findsOneWidget);
    });

    testWidgets('the Copy button copies the Support ID to the clipboard',
        (tester) async {
      // Capture the platform clipboard write.
      String? copied;
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        (MethodCall call) async {
          if (call.method == 'Clipboard.setData') {
            copied = (call.arguments as Map)['text'] as String?;
          }
          return null;
        },
      );
      var onCopiedCalled = false;
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: SupportIdRow(
            supportId: 'AU-7K3Q',
            onCopied: () => onCopiedCalled = true,
          ),
        ),
      ));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('support_id_copy')));
      await tester.pumpAndSettle();
      expect(copied, 'AU-7K3Q');
      expect(onCopiedCalled, isTrue);
    });

    testWidgets('without onCopied it shows a confirmation snackbar',
        (tester) async {
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        (MethodCall call) async => null,
      );
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(body: SupportIdRow(supportId: 'AU-7K3Q')),
      ));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('support_id_copy')));
      await tester.pump(); // start the snackbar
      expect(find.textContaining('AU-7K3Q copied'), findsOneWidget);
    });
  });
}
