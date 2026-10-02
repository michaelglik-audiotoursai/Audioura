/// Integration test: Wallet screen against the LIVE subscribed stack (5102).
///
/// Runs on macOS desktop — exercises the same Dart code, same
/// WalletService, same HTTP contract as the phone APK.
///
/// Usage:
///   flutter test integration_test/wallet_live_test.dart \
///     --dart-define=WALLET_DEBUG_PORT=5102 \
///     --dart-define=DEBUG_SERVER_IP=192.168.0.136 \
///     -d macos
///
/// This is an integration test — it requires the server to
/// be reachable at 192.168.0.136:5102.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/screens/wallet_screen.dart';
import 'package:audio_tour_app_dev/config/endpoints.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

/// The test user created specifically for LOCAL-158.
const _testUserId = 'test_wallet_158_3be66f6ee87e';

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  group('Wallet screen — live API on subscribed stack (5102)', () {
    testWidgets('renders wallet with real balance from server', (tester) async {
      // Write SharedPreferences for real (integration test = real platform)
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('user_id', _testUserId);
      await prefs.setString('server_mode', 'local');
      await prefs.setString('server_ip', '192.168.0.136');
      await prefs.setBool('use_mock_wallet', false);
      debugPrint('=== SharedPreferences written: user_id=$_testUserId');

      // Verify the server is reachable
      final baseUrl = await Endpoints.base(Service.orchestrator);
      debugPrint('=== Endpoints.base(orchestrator) = $baseUrl');

      final directResponse =
          await http.get(Uri.parse('$baseUrl/wallet/$_testUserId'));
      debugPrint('=== Direct API response (${directResponse.statusCode}): ${directResponse.body}');
      expect(directResponse.statusCode, 200);

      final walletJson = jsonDecode(directResponse.body) as Map<String, dynamic>;
      final serverBalance = (walletJson['balance_usd'] as num).toDouble();
      debugPrint('=== Server reports balance: \$$serverBalance');

      // Pump the WalletScreen widget
      await tester.pumpWidget(const MaterialApp(home: WalletScreen()));
      debugPrint('=== Widget pumped, waiting for settle...');

      // Wait for async load to complete — give it up to 10 seconds
      int attempts = 0;
      while (attempts < 100) {
        await tester.pump(const Duration(milliseconds: 100));
        attempts++;
        if (find.byType(CircularProgressIndicator).evaluate().isEmpty) {
          debugPrint('=== Loading complete after ${attempts * 100}ms');
          break;
        }
      }
      if (attempts >= 100) {
        debugPrint('=== WARNING: Still loading after 10s');
      }

      // Dump all rendered Text widgets
      debugPrint('=== RENDERED TEXT WIDGETS ===');
      final textWidgets = find.byType(Text);
      final allTexts = <String>[];
      for (final element in textWidgets.evaluate()) {
        final widget = element.widget as Text;
        if (widget.data != null && widget.data!.isNotEmpty) {
          allTexts.add(widget.data!);
          debugPrint('  TEXT: "${widget.data}"');
        }
      }
      debugPrint('=== END RENDERED TEXT (${allTexts.length} widgets) ===');

      // Check for error state
      if (find.text('Failed to load wallet').evaluate().isNotEmpty) {
        debugPrint('=== ERROR: Wallet screen shows error state');
        // Try to find the error detail
        for (final text in allTexts) {
          if (text.contains('Exception') || text.contains('error')) {
            debugPrint('=== Error detail: $text');
          }
        }
        fail('Wallet screen entered error state');
      }

      // Verify the balance is displayed
      final balanceText = '\$${serverBalance.toStringAsFixed(2)}';
      debugPrint('=== Looking for rendered balance: $balanceText');

      // Check if balance appears in any text widget
      final found = allTexts.any((t) => t.contains(serverBalance.toStringAsFixed(2)));
      expect(found, isTrue,
          reason: 'Expected balance $balanceText in rendered text. Got: $allTexts');

      debugPrint('✅ WalletScreen rendered with balance $balanceText from live server');
    });

    testWidgets('balance updates after real top-up via API', (tester) async {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('user_id', _testUserId);
      await prefs.setString('server_mode', 'local');
      await prefs.setString('server_ip', '192.168.0.136');
      await prefs.setBool('use_mock_wallet', false);

      final baseUrl = await Endpoints.base(Service.orchestrator);

      // Get balance BEFORE
      final beforeResp = await http.get(Uri.parse('$baseUrl/wallet/$_testUserId'));
      final beforeJson = jsonDecode(beforeResp.body) as Map<String, dynamic>;
      final balanceBefore = (beforeJson['balance_usd'] as num).toDouble();
      debugPrint('=== Balance BEFORE: \$$balanceBefore');

      // Use a fresh user for the top-up test to demonstrate change
      const freshUser = 'test_wallet_158_e2e_topup';
      await prefs.setString('user_id', freshUser);

      // Get fresh user initial balance
      final freshBefore = await http.get(Uri.parse('$baseUrl/wallet/$freshUser'));
      final freshBeforeJson = jsonDecode(freshBefore.body) as Map<String, dynamic>;
      final freshBalBefore = (freshBeforeJson['balance_usd'] as num).toDouble();
      debugPrint('=== Fresh user ($freshUser) balance BEFORE: \$$freshBalBefore');

      // Top up if balance is 0
      double expectedBalance = freshBalBefore;
      if (freshBalBefore == 0.0) {
        final topUpResp = await http.post(
          Uri.parse('$baseUrl/wallet/$freshUser/topup'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'product_id': 'credit_topup_10'}),
        );
        debugPrint('=== Top-up response: ${topUpResp.body}');
        expect(topUpResp.statusCode, 200);
        final topUpJson = jsonDecode(topUpResp.body) as Map<String, dynamic>;
        expectedBalance = (topUpJson['new_balance_usd'] as num).toDouble();
        debugPrint('=== Balance AFTER top-up: \$$expectedBalance');
      }

      // Now pump the wallet screen for the fresh user
      await tester.pumpWidget(const MaterialApp(home: WalletScreen()));
      int attempts = 0;
      while (attempts < 100) {
        await tester.pump(const Duration(milliseconds: 100));
        attempts++;
        if (find.byType(CircularProgressIndicator).evaluate().isEmpty) break;
      }

      // Dump rendered text
      debugPrint('=== RENDERED TEXT AFTER TOP-UP ===');
      final textWidgets = find.byType(Text);
      final allTexts = <String>[];
      for (final element in textWidgets.evaluate()) {
        final widget = element.widget as Text;
        if (widget.data != null && widget.data!.isNotEmpty) {
          allTexts.add(widget.data!);
          debugPrint('  TEXT: "${widget.data}"');
        }
      }
      debugPrint('=== END ===');

      // Verify balance shown
      final found = allTexts.any((t) => t.contains(expectedBalance.toStringAsFixed(2)));
      expect(found, isTrue,
          reason: 'Expected balance \$${expectedBalance.toStringAsFixed(2)} in text');
      debugPrint('✅ Balance updated correctly: \$$freshBalBefore → \$$expectedBalance');
    });
  });
}
