/// LOCAL-161: Wallet balance visibility fixes — rendered proof.
///
/// States tested:
///   1. Free tier + $10 balance → balance now shows
///   2. Free tier + $0 balance → no $0.00 displayed
///   3. PPU + negative balance → renders "-$0.50" not "$-0.50"
///   4. PPU + healthy balance → unchanged (regression guard)
///   5. Unlimited + cost-stop → unchanged (regression guard)
///
/// Run:
///   python3 tests/test_local161_wallet_balance_visibility.py   # create users
///   cd audio_tour_app
///   flutter test integration_test/wallet_balance_visibility_test.dart \
///     --dart-define=WALLET_DEBUG_PORT=5102 \
///     --dart-define=DEBUG_SERVER_IP=192.168.0.136 \
///     --dart-define=LOCAL161_RUN_ID=<run_id> \
///     -d macos
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/screens/wallet_screen.dart';

const _runId = String.fromEnvironment('LOCAL161_RUN_ID');

Map<String, String> _users(String runId) => {
      'free_positive': 'test_161_free_pos_$runId',
      'free_zero': 'test_161_free_zero_$runId',
      'ppu_negative': 'test_161_ppu_neg_$runId',
      'ppu_healthy': 'test_161_ppu_healthy_$runId',
      'unlimited_mid': 'test_161_unlim_$runId',
    };

/// Pump WalletScreen, wait for load, dump all text widgets.
Future<List<String>> _renderWalletForUser(
    WidgetTester tester, String userId) async {
  final prefs = await SharedPreferences.getInstance();
  await prefs.setString('user_id', userId);
  await prefs.setString('server_mode', 'local');
  await prefs.setString('server_ip', '192.168.0.136');
  await prefs.setBool('use_mock_wallet', false);

  await tester.pumpWidget(const MaterialApp(home: WalletScreen()));

  // Wait for async load
  int attempts = 0;
  while (attempts < 100) {
    await tester.pump(const Duration(milliseconds: 100));
    attempts++;
    if (find.byType(CircularProgressIndicator).evaluate().isEmpty) {
      break;
    }
  }

  if (attempts >= 100) {
    debugPrint('=== WARNING: Still loading after 10s');
  }

  // Dump all rendered Text widgets
  final textWidgets = find.byType(Text);
  final allTexts = <String>[];
  for (final element in textWidgets.evaluate()) {
    final widget = element.widget as Text;
    if (widget.data != null && widget.data!.isNotEmpty) {
      allTexts.add(widget.data!);
    }
  }
  return allTexts;
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  if (_runId.isEmpty) {
    debugPrint(
        'ERROR: Pass --dart-define=LOCAL161_RUN_ID=<id> from Python script');
    return;
  }

  final users = _users(_runId);
  debugPrint('=== LOCAL-161 Wallet Balance Visibility ===');
  debugPrint('=== Run ID: $_runId');

  group('LOCAL-161: Wallet balance visibility fixes', () {
    testWidgets('FIX 1: Free tier + \$10 balance shows balance',
        (tester) async {
      final userId = users['free_positive']!;
      debugPrint('\n=== STATE: Free tier, positive balance ===');
      debugPrint('=== User: $userId');

      final texts = await _renderWalletForUser(tester, userId);

      debugPrint('=== RENDERED TEXT ===');
      for (final t in texts) {
        debugPrint('  TEXT: "$t"');
      }
      debugPrint('=== END (${texts.length} widgets) ===');

      // Verify: balance $10.00 is now rendered
      final hasBalance = texts.any((t) => t.contains('10.00'));
      final hasAvailableBalance = texts.contains('Available Balance');
      final hasFreePlan = texts.contains('Free Plan');
      final hasUpgrade = texts.any(
          (t) => t.contains('Upgrade to generate unlimited tours and articles'));

      debugPrint('=== ASSERTIONS ===');
      debugPrint('  Balance \$10.00 shown? $hasBalance');
      debugPrint('  "Available Balance" label? $hasAvailableBalance');
      debugPrint('  "Free Plan" still shown? $hasFreePlan');
      debugPrint('  Upgrade prompt still shown? $hasUpgrade');

      expect(hasBalance, isTrue,
          reason: 'FIX 1: Balance should be visible for free tier with credit');
      expect(hasFreePlan, isTrue,
          reason: 'Free Plan label should still appear');
      expect(hasUpgrade, isTrue,
          reason: 'Upgrade prompt should remain');
    });

    testWidgets('FIX 1: Free tier + \$0 balance does NOT show \$0.00',
        (tester) async {
      final userId = users['free_zero']!;
      debugPrint('\n=== STATE: Free tier, zero balance ===');
      debugPrint('=== User: $userId');

      final texts = await _renderWalletForUser(tester, userId);

      debugPrint('=== RENDERED TEXT ===');
      for (final t in texts) {
        debugPrint('  TEXT: "$t"');
      }
      debugPrint('=== END (${texts.length} widgets) ===');

      // Verify: no "$0.00" in the balance card area
      // (transaction history may show "$0.00" for cache hits, so check
      // specifically for "Available Balance" label absence)
      final hasAvailableBalance = texts.contains('Available Balance');
      final hasFreePlan = texts.contains('Free Plan');

      debugPrint('=== ASSERTIONS ===');
      debugPrint('  "Available Balance" label? $hasAvailableBalance');
      debugPrint('  "Free Plan" shown? $hasFreePlan');

      expect(hasAvailableBalance, isFalse,
          reason:
              'Zero balance should NOT show "Available Balance" — no distracting \$0.00');
      expect(hasFreePlan, isTrue);
    });

    testWidgets('FIX 2: PPU negative balance renders -\$0.50 not \$-0.50',
        (tester) async {
      final userId = users['ppu_negative']!;
      debugPrint('\n=== STATE: PPU, negative balance ===');
      debugPrint('=== User: $userId');

      final texts = await _renderWalletForUser(tester, userId);

      debugPrint('=== RENDERED TEXT ===');
      for (final t in texts) {
        debugPrint('  TEXT: "$t"');
      }
      debugPrint('=== END (${texts.length} widgets) ===');

      // Verify: renders -$0.50, NOT $-0.50
      final hasCorrectNeg = texts.contains('-\$0.50');
      final hasBrokenNeg = texts.contains('\$-0.50');

      debugPrint('=== ASSERTIONS ===');
      debugPrint('  Correct "-\$0.50"? $hasCorrectNeg');
      debugPrint('  Broken "\$-0.50"? $hasBrokenNeg');

      expect(hasCorrectNeg, isTrue,
          reason: 'FIX 2: Negative balance should render as -\$0.50');
      expect(hasBrokenNeg, isFalse,
          reason: 'FIX 2: \$-0.50 format should no longer appear');
    });

    testWidgets('REGRESSION: PPU healthy balance unchanged', (tester) async {
      final userId = users['ppu_healthy']!;
      debugPrint('\n=== STATE: PPU, healthy balance (regression guard) ===');
      debugPrint('=== User: $userId');

      final texts = await _renderWalletForUser(tester, userId);

      debugPrint('=== RENDERED TEXT ===');
      for (final t in texts) {
        debugPrint('  TEXT: "$t"');
      }
      debugPrint('=== END (${texts.length} widgets) ===');

      // Same as LOCAL-160 State 3
      expect(texts.contains('Available Balance'), isTrue);
      expect(texts.any((t) => t.contains('10.00')), isTrue);
      expect(texts.contains('Pay-Per-Use'), isTrue);
      expect(texts.contains('Top Up'), isTrue);
    });

    testWidgets('REGRESSION: Unlimited cost-stop unchanged', (tester) async {
      final userId = users['unlimited_mid']!;
      debugPrint('\n=== STATE: Unlimited, cost-stop (regression guard) ===');
      debugPrint('=== User: $userId');

      final texts = await _renderWalletForUser(tester, userId);

      debugPrint('=== RENDERED TEXT ===');
      for (final t in texts) {
        debugPrint('  TEXT: "$t"');
      }
      debugPrint('=== END (${texts.length} widgets) ===');

      // Same as LOCAL-160 State 6
      expect(texts.contains('Monthly Allowance'), isTrue);
      expect(texts.any((t) => t.contains('12.50')), isTrue);
      expect(texts.any((t) => t.contains('25.00')), isTrue);
      expect(texts.any((t) => t.contains('% used')), isTrue);
      expect(texts.contains('Unlimited'), isTrue);
    });
  });
}
