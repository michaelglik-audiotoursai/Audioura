import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/screens/wallet_screen.dart';
import 'package:audio_tour_app_dev/services/wallet_service.dart';

/// Widget tests for Wallet UI screens against the mock backend.
/// These test each visual state without requiring the real backend.
///
/// Tests run in mock mode by setting SharedPreferences 'use_mock_wallet'=true.
/// The compile-time default is live, but tests override to mock.

void main() {
  setUp(() async {
    // Force mock mode for all widget tests
    SharedPreferences.setMockInitialValues({'use_mock_wallet': true});
    WalletTestHelper.reset();
  });

  group('WalletScreen — Pay-Per-Use', () {
    testWidgets('shows balance and transactions', (tester) async {
      WalletTestHelper.setMockPlan('ppu');
      WalletTestHelper.setMockBalance(7.45);

      await tester.pumpWidget(const MaterialApp(home: WalletScreen()));
      await tester.pumpAndSettle();

      // Balance should be visible
      expect(find.text('Available Balance'), findsOneWidget);
      expect(find.textContaining('\$7.45'), findsOneWidget);

      // Plan should be visible
      expect(find.text('Pay-Per-Use'), findsOneWidget);

      // Top-up button should be visible
      expect(find.widgetWithText(ElevatedButton, 'Top Up'), findsOneWidget);

      // Transactions section should exist
      expect(find.text('Transaction History'), findsOneWidget);

      // Transaction descriptions should be user-friendly (no token counts)
      expect(find.text('Tour: French Riviera biking'), findsOneWidget);
      expect(find.text('Tour: Historic Boston walking'), findsOneWidget);

      // Cache hit should show "Downloaded — no charge"
      expect(find.text('Downloaded — no charge'), findsWidgets);
    });

    testWidgets('transactions show \$0.00 for cache hits', (tester) async {
      WalletTestHelper.setMockPlan('ppu');
      await tester.pumpWidget(const MaterialApp(home: WalletScreen()));
      await tester.pumpAndSettle();

      // Cache hits display \$0.00
      expect(find.text('\$0.00'), findsWidgets);
    });

    testWidgets('top-up button shows confirmation dialog', (tester) async {
      WalletTestHelper.setMockPlan('ppu');
      await tester.pumpWidget(const MaterialApp(home: WalletScreen()));
      await tester.pumpAndSettle();

      // Tap the Top Up elevated button
      final topUpButton = find.widgetWithText(ElevatedButton, 'Top Up');
      expect(topUpButton, findsOneWidget);
      await tester.tap(topUpButton);
      await tester.pumpAndSettle();

      // Dialog should appear
      expect(find.text('Top Up Credits'), findsOneWidget);
      expect(find.text('Cancel'), findsOneWidget);
    });

    testWidgets('low balance shows warning', (tester) async {
      WalletTestHelper.setMockPlan('ppu');
      WalletTestHelper.setMockBalance(1.50); // Below $2 threshold

      await tester.pumpWidget(const MaterialApp(home: WalletScreen()));
      await tester.pumpAndSettle();

      // Low balance warning should appear
      expect(
        find.textContaining('Low balance'),
        findsOneWidget,
      );
    });

    testWidgets('monthly fee shows as informational, not a charge (D20)', (tester) async {
      WalletTestHelper.setMockPlan('ppu');
      WalletTestHelper.setIncludeMonthlyFee(true);

      await tester.pumpWidget(const MaterialApp(home: WalletScreen()));
      await tester.pumpAndSettle();

      // Monthly fee row should say "billed by Apple", not look like a debit
      expect(
        find.text('Monthly subscription — billed by Apple'),
        findsOneWidget,
      );
    });
  });

  group('WalletScreen — Free plan', () {
    testWidgets('shows upgrade prompt, no balance', (tester) async {
      WalletTestHelper.setMockPlan('free');

      await tester.pumpWidget(const MaterialApp(home: WalletScreen()));
      await tester.pumpAndSettle();

      // Should show Free Plan card
      expect(find.text('Free Plan'), findsOneWidget);
      expect(find.text('View Plans'), findsOneWidget);

      // Should NOT show a balance amount
      expect(find.text('Available Balance'), findsNothing);

      // Should NOT show top-up button (elevated)
      expect(find.widgetWithText(ElevatedButton, 'Top Up'), findsNothing);
    });
  });

  group('WalletScreen — Unlimited plan', () {
    testWidgets('shows cost-stop progress, not balance', (tester) async {
      WalletTestHelper.setMockPlan('unlimited');

      await tester.pumpWidget(const MaterialApp(home: WalletScreen()));
      await tester.pumpAndSettle();

      // Should show Monthly Allowance (cost-stop)
      expect(find.text('Monthly Allowance'), findsOneWidget);
      expect(find.textContaining('\$18.75'), findsOneWidget);
      expect(find.textContaining('\$25.00'), findsOneWidget);
      expect(find.text('75% used'), findsOneWidget);

      // Should NOT show "Available Balance"
      expect(find.text('Available Balance'), findsNothing);

      // Should NOT show top-up button
      expect(find.widgetWithText(ElevatedButton, 'Top Up'), findsNothing);

      // Plan card should say Unlimited
      expect(find.text('Unlimited'), findsOneWidget);
    });
  });

  group('LowBalanceBanner', () {
    testWidgets('renders with warning text and top-up button', (tester) async {
      bool topUpTapped = false;
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: LowBalanceBanner(onTopUp: () => topUpTapped = true),
        ),
      ));

      expect(find.text('Low balance — top up to keep generating'), findsOneWidget);
      expect(find.text('Top Up'), findsOneWidget);

      await tester.tap(find.text('Top Up'));
      expect(topUpTapped, isTrue);
    });
  });

  group('PaywallScreen', () {
    testWidgets('shows all plans from API with prices', (tester) async {
      await tester.pumpWidget(const MaterialApp(home: PaywallScreen()));
      await tester.pumpAndSettle();

      // All three plans should be visible
      expect(find.text('Free'), findsOneWidget);
      expect(find.text('Pay-Per-Use'), findsOneWidget);
      expect(find.text('Unlimited'), findsOneWidget);

      // Prices from the mock API (NOT hardcoded)
      expect(find.text('Free forever'), findsOneWidget);
      expect(find.textContaining('/ month'), findsWidgets);

      // Features lists visible
      expect(find.text('Pay only for what you use'), findsOneWidget);

      // Subscribe buttons for paid plans
      expect(find.text('Subscribe to Pay-Per-Use'), findsOneWidget);
      expect(find.text('Subscribe to Unlimited'), findsOneWidget);
    });

    testWidgets('restore purchases link is accessible', (tester) async {
      await tester.pumpWidget(const MaterialApp(home: PaywallScreen()));
      await tester.pumpAndSettle();

      // Scroll down to find Restore Purchases
      await tester.scrollUntilVisible(
        find.text('Restore Purchases'),
        200.0,
      );
      expect(find.text('Restore Purchases'), findsOneWidget);
    });
  });

  group('Transaction rendering edge cases', () {
    testWidgets('cache-hit renders as \$0.00 with clear wording', (tester) async {
      WalletTestHelper.setMockPlan('ppu');
      await tester.pumpWidget(const MaterialApp(home: WalletScreen()));
      await tester.pumpAndSettle();

      // "Downloaded — no charge" is the API's description for cache hits
      // It must display clearly that nothing was charged
      expect(find.text('Downloaded — no charge'), findsWidgets);

      // The amount column for these rows shows $0.00
      // (verified by existence of multiple $0.00 entries)
      expect(find.text('\$0.00'), findsWidgets);
    });

    testWidgets('monthly fee does not reduce displayed balance (D20)', (tester) async {
      // The wallet balance should be $7.45 even with a monthly fee in history
      WalletTestHelper.setMockPlan('ppu');
      WalletTestHelper.setMockBalance(7.45);
      WalletTestHelper.setIncludeMonthlyFee(true);

      await tester.pumpWidget(const MaterialApp(home: WalletScreen()));
      await tester.pumpAndSettle();

      // Balance is not reduced by the monthly fee
      expect(find.textContaining('\$7.45'), findsOneWidget);
    });
  });
}
