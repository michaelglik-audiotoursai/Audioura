/// LOCAL-160: Wallet UX findings — render the wallet screen for 6 different
/// user states and dump the rendered text for each.
///
/// User IDs are passed via --dart-define. Run the Python script first to create
/// the users, then pass the run_id:
///
///   flutter test integration_test/wallet_ux_findings_test.dart \
///     --dart-define=WALLET_DEBUG_PORT=5102 \
///     --dart-define=DEBUG_SERVER_IP=192.168.0.136 \
///     --dart-define=UX160_RUN_ID=<run_id> \
///     -d macos
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/screens/wallet_screen.dart';

const _runId = String.fromEnvironment('UX160_RUN_ID');

/// All user IDs based on the run_id from the Python script.
Map<String, String> _users(String runId) => {
      'free_zero': 'test_ux160_free_zero_$runId',
      'free_positive': 'test_ux160_free_pos_$runId',
      'ppu_healthy': 'test_ux160_ppu_healthy_$runId',
      'ppu_low': 'test_ux160_ppu_low_$runId',
      'ppu_zero': 'test_ux160_ppu_zero_$runId',
      'unlimited_mid': 'test_ux160_unlim_$runId',
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

  // Wait for async load to complete
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
    debugPrint('ERROR: Pass --dart-define=UX160_RUN_ID=<id> from Python script');
    return;
  }

  final users = _users(_runId);
  debugPrint('=== LOCAL-160 UX Findings ===');
  debugPrint('=== Run ID: $_runId');

  group('LOCAL-160: Wallet UX findings — all states', () {
    testWidgets('STATE 1: Free tier, zero balance', (tester) async {
      final userId = users['free_zero']!;
      debugPrint('\n=== STATE 1: Free tier, zero balance ===');
      debugPrint('=== User: $userId');

      final texts = await _renderWalletForUser(tester, userId);

      debugPrint('=== RENDERED TEXT ===');
      for (final t in texts) {
        debugPrint('  TEXT: "$t"');
      }
      debugPrint('=== END (${texts.length} widgets) ===');

      expect(texts.contains('Wallet'), isTrue);
    });

    testWidgets('STATE 2: Free tier, positive balance (\$10)', (tester) async {
      final userId = users['free_positive']!;
      debugPrint('\n=== STATE 2: Free tier, positive balance ===');
      debugPrint('=== User: $userId');

      final texts = await _renderWalletForUser(tester, userId);

      debugPrint('=== RENDERED TEXT ===');
      for (final t in texts) {
        debugPrint('  TEXT: "$t"');
      }
      debugPrint('=== END (${texts.length} widgets) ===');

      // Key finding: does balance show or just upgrade prompt?
      final showsBalance = texts.any((t) => t.contains('10.00'));
      final showsFreePlan = texts.contains('Free Plan');
      debugPrint('=== FINDING: Shows balance \$10.00? $showsBalance');
      debugPrint('=== FINDING: Shows "Free Plan" upgrade prompt? $showsFreePlan');
    });

    testWidgets('STATE 3: PPU, healthy balance (\$10)', (tester) async {
      final userId = users['ppu_healthy']!;
      debugPrint('\n=== STATE 3: PPU, healthy balance ===');
      debugPrint('=== User: $userId');

      final texts = await _renderWalletForUser(tester, userId);

      debugPrint('=== RENDERED TEXT ===');
      for (final t in texts) {
        debugPrint('  TEXT: "$t"');
      }
      debugPrint('=== END (${texts.length} widgets) ===');

      expect(texts.contains('Available Balance'), isTrue);
      expect(texts.any((t) => t.contains('10.00')), isTrue);
    });

    testWidgets('STATE 4: PPU, low balance (\$1.50)', (tester) async {
      final userId = users['ppu_low']!;
      debugPrint('\n=== STATE 4: PPU, low balance ===');
      debugPrint('=== User: $userId');

      final texts = await _renderWalletForUser(tester, userId);

      debugPrint('=== RENDERED TEXT ===');
      for (final t in texts) {
        debugPrint('  TEXT: "$t"');
      }
      debugPrint('=== END (${texts.length} widgets) ===');

      final hasLowBanner = texts.any((t) => t.contains('Low balance'));
      debugPrint('=== FINDING: Low balance banner? $hasLowBanner');
    });

    testWidgets('STATE 5: PPU, negative balance (-\$0.50)', (tester) async {
      final userId = users['ppu_zero']!;
      debugPrint('\n=== STATE 5: PPU, negative balance ===');
      debugPrint('=== User: $userId');

      final texts = await _renderWalletForUser(tester, userId);

      debugPrint('=== RENDERED TEXT ===');
      for (final t in texts) {
        debugPrint('  TEXT: "$t"');
      }
      debugPrint('=== END (${texts.length} widgets) ===');

      // Check how negative balance is rendered
      final negativeText = texts.where((t) => t.contains('-'));
      debugPrint('=== FINDING: Texts with minus sign: $negativeText');
    });

    testWidgets('STATE 6: Unlimited, cost-stop at 50%', (tester) async {
      final userId = users['unlimited_mid']!;
      debugPrint('\n=== STATE 6: Unlimited, cost-stop progress ===');
      debugPrint('=== User: $userId');

      final texts = await _renderWalletForUser(tester, userId);

      debugPrint('=== RENDERED TEXT ===');
      for (final t in texts) {
        debugPrint('  TEXT: "$t"');
      }
      debugPrint('=== END (${texts.length} widgets) ===');

      final hasCostStop = texts.contains('Monthly Allowance');
      final hasProgress = texts.any((t) => t.contains('% used'));
      debugPrint('=== FINDING: Monthly Allowance rendered? $hasCostStop');
      debugPrint('=== FINDING: Progress % rendered? $hasProgress');
    });
  });
}
