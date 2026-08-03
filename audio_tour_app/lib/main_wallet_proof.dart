/// Minimal wallet-only app for LOCAL-158 runtime proof.
/// Runs on Chrome or macOS without needing mobile-only plugins.
///
/// Usage:
///   flutter run -t lib/main_wallet_proof.dart -d chrome \
///     --dart-define=WALLET_DEBUG_PORT=5102 \
///     --dart-define=DEBUG_SERVER_IP=192.168.0.136
library;

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'screens/wallet_screen.dart';

const _testUserId = 'test_wallet_158_3be66f6ee87e';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  print('=== WALLET PROOF (LOCAL-158) ===');
  print('Test user: $_testUserId');

  // Set user_id so WalletService fetches for our test user
  final prefs = await SharedPreferences.getInstance();
  await prefs.setString('user_id', _testUserId);
  await prefs.setString('server_mode', 'local');
  await prefs.setString('server_ip', '192.168.0.136');
  await prefs.setBool('use_mock_wallet', false);
  await prefs.setBool('onboarding_complete', true);

  print('SharedPreferences set: user_id=$_testUserId, server_mode=local');
  print('Launching WalletScreen...');

  runApp(const WalletProofApp());
}

class WalletProofApp extends StatelessWidget {
  const WalletProofApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Wallet Proof — LOCAL-158',
      theme: ThemeData(primarySwatch: Colors.blue, useMaterial3: true),
      home: const WalletScreen(),
    );
  }
}
