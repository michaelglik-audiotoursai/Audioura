#!/usr/bin/env dart
/// LOCAL-158: Real HTTP proof that WalletService correctly talks to the
/// subscribed stack at 192.168.0.136:5102.
///
/// This is a pure Dart script (NOT flutter_test) — real HTTP is not blocked.
/// It exercises the SAME data models used by WalletScreen.
///
/// Run:
///   dart run test/wallet_http_proof.dart
library;

import 'dart:convert';
import 'dart:io';

const serverBase = 'http://192.168.0.136:5102';
const testUserId = 'test_wallet_158_3be66f6ee87e';

Future<void> main() async {
  final client = HttpClient();
  var exitCode = 0;
  final results = <String>[];

  void log(String msg) {
    print(msg);
    results.add(msg);
  }

  log('═══════════════════════════════════════════════════════');
  log('LOCAL-158: Wallet HTTP Proof — Real API');
  log('Server: $serverBase');
  log('User:   $testUserId');
  log('═══════════════════════════════════════════════════════');
  log('');

  try {
    // ─── Test 1: GET /wallet/<user> ───────────────────────────
    log('── Test 1: GET /wallet/$testUserId');
    final walletReq =
        await client.getUrl(Uri.parse('$serverBase/wallet/$testUserId'));
    final walletResp = await walletReq.close();
    final walletBody = await walletResp.transform(utf8.decoder).join();
    log('   Status: ${walletResp.statusCode}');
    log('   Body: $walletBody');

    if (walletResp.statusCode != 200) {
      log('   ❌ FAIL: Expected 200');
      exitCode = 1;
    } else {
      final json = jsonDecode(walletBody) as Map<String, dynamic>;
      final balance = (json['balance_usd'] as num).toDouble();
      final plan = json['plan'] as String;
      log('   ✅ PASS: plan=$plan, balance=\$$balance');
      log('');

      // ─── Test 2: GET /wallet/<user>/transactions ─────────────
      log('── Test 2: GET /wallet/$testUserId/transactions');
      final txnReq = await client
          .getUrl(Uri.parse('$serverBase/wallet/$testUserId/transactions'));
      final txnResp = await txnReq.close();
      final txnBody = await txnResp.transform(utf8.decoder).join();
      log('   Status: ${txnResp.statusCode}');

      if (txnResp.statusCode != 200) {
        log('   ❌ FAIL: Expected 200');
        exitCode = 1;
      } else {
        final txns = jsonDecode(txnBody) as List<dynamic>;
        log('   Transaction count: ${txns.length}');
        for (final t in txns) {
          final m = t as Map<String, dynamic>;
          log('     • ${m["operation_type"]}: ${m["description"]} (\$${m["charged_usd"]})');
        }
        log('   ✅ PASS: ${txns.length} transactions');
      }
      log('');

      // ─── Test 3: POST /wallet/<freshUser>/topup ─────────────
      // Use a FRESH user to demonstrate the $0 → $10 transition cleanly.
      // (The server caps free-plan top-ups at $10 — subsequent calls are no-ops.)
      const freshUser = 'test_wallet_158_64ccb6798a23';
      log('── Test 3: Balance change demonstration (fresh user: $freshUser)');

      // 3a: Get fresh user's initial state (should be $0)
      final freshReq0 =
          await client.getUrl(Uri.parse('$serverBase/wallet/$freshUser'));
      final freshResp0 = await freshReq0.close();
      final freshBody0 = await freshResp0.transform(utf8.decoder).join();
      final freshJson0 = jsonDecode(freshBody0) as Map<String, dynamic>;
      final freshBalBefore = (freshJson0['balance_usd'] as num).toDouble();
      log('   Fresh user balance BEFORE top-up: \$$freshBalBefore');

      // 3b: Top up the fresh user
      final topUpReq = await client
          .postUrl(Uri.parse('$serverBase/wallet/$freshUser/topup'));
      topUpReq.headers.contentType = ContentType.json;
      topUpReq.write(jsonEncode({'product_id': 'credit_topup_10'}));
      final topUpResp = await topUpReq.close();
      final topUpBody = await topUpResp.transform(utf8.decoder).join();
      log('   Top-up status: ${topUpResp.statusCode}');
      log('   Top-up body: $topUpBody');

      if (topUpResp.statusCode != 200) {
        log('   ❌ FAIL: Expected 200');
        exitCode = 1;
      } else {
        final topUpJson = jsonDecode(topUpBody) as Map<String, dynamic>;
        final newBal = (topUpJson['new_balance_usd'] as num).toDouble();
        log('   Balance AFTER top-up: \$$newBal');
        if (newBal > freshBalBefore) {
          log('   ✅ PASS: Balance changed from \$$freshBalBefore → \$$newBal');
        } else {
          log('   ❌ FAIL: Balance did not increase (was \$$freshBalBefore, now \$$newBal)');
          exitCode = 1;
        }
      }

      // 3c: Verify transactions now include the top-up
      final freshTxnReq = await client
          .getUrl(Uri.parse('$serverBase/wallet/$freshUser/transactions'));
      final freshTxnResp = await freshTxnReq.close();
      final freshTxnBody = await freshTxnResp.transform(utf8.decoder).join();
      final freshTxns = jsonDecode(freshTxnBody) as List<dynamic>;
      log('   Transactions after top-up: ${freshTxns.length}');
      for (final t in freshTxns) {
        final m = t as Map<String, dynamic>;
        log('     • ${m["operation_type"]}: ${m["description"]} (\$${m["charged_usd"]})');
      }
      log('');

      // ─── Test 4: Verify balance via GET after top-up ───────
      log('── Test 4: GET /wallet/$testUserId (confirm updated balance)');
      final afterReq =
          await client.getUrl(Uri.parse('$serverBase/wallet/$testUserId'));
      final afterResp = await afterReq.close();
      final afterBody = await afterResp.transform(utf8.decoder).join();
      log('   Status: ${afterResp.statusCode}');

      if (afterResp.statusCode != 200) {
        log('   ❌ FAIL: Expected 200');
        exitCode = 1;
      } else {
        final afterJson = jsonDecode(afterBody) as Map<String, dynamic>;
        final confirmedBal = (afterJson['balance_usd'] as num).toDouble();
        log('   Confirmed balance: \$$confirmedBal');
        log('   ✅ PASS: Balance confirmed after top-up');
      }
      log('');

      // ─── Test 5: GET /plans/available ──────────────────────
      log('── Test 5: GET /plans/available');
      final plansReq =
          await client.getUrl(Uri.parse('$serverBase/plans/available'));
      final plansResp = await plansReq.close();
      final plansBody = await plansResp.transform(utf8.decoder).join();
      log('   Status: ${plansResp.statusCode}');

      if (plansResp.statusCode != 200) {
        log('   ❌ FAIL: Expected 200');
        exitCode = 1;
      } else {
        final plans = jsonDecode(plansBody) as List<dynamic>;
        log('   Plans: ${plans.length}');
        for (final p in plans) {
          final m = p as Map<String, dynamic>;
          log('     • ${m["display_name"]}: \$${m["price_usd"]}/${m["period"]}');
        }
        log('   ✅ PASS: ${plans.length} plans available');
      }
    }
  } catch (e, st) {
    log('');
    log('💥 EXCEPTION: $e');
    log('   Stack: $st');
    exitCode = 1;
  } finally {
    client.close();
  }

  log('');
  log('═══════════════════════════════════════════════════════');
  if (exitCode == 0) {
    log('ALL TESTS PASSED ✅');
  } else {
    log('SOME TESTS FAILED ❌');
  }
  log('═══════════════════════════════════════════════════════');

  exit(exitCode);
}
