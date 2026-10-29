/// [LOCAL-807B] Plans-screen live-proof harness for the iOS simulator.
///
/// The LOCAL-807 reveal screen (PlansScreen, lib/screens/plans_screen.dart) is a
/// new, standalone screen that is not yet wired into the app's menus (every
/// menu still opens the older PlanScreen). This tiny entrypoint — modelled on
/// main_wallet_proof.dart (LOCAL-158) — launches PlansScreen DIRECTLY against
/// the local LOCAL-807 user-api container, so the reveal flow, the auto-renewal
/// terms and the active-plan banner can be driven on the simulator with the
/// Xcode StoreKit configuration file (ios/Audioura.storekit) loaded by the
/// scheme. It touches NO production navigation.
///
/// Usage (iOS simulator, StoreKit config attached via the Runner scheme):
///   flutter run -t lib/main_plans_proof.dart -d <sim-id> \
///     --dart-define=DEBUG_SERVER_IP=127.0.0.1
///
/// DEBUG_SERVER_IP forces local mode -> http://127.0.0.1:5003 (Endpoints
/// _localPorts[userDb]); on the iOS simulator 127.0.0.1 is the Mac host, where
/// the proof container publishes the user-api on 5003.
library;

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'screens/plans_screen.dart';
import 'services/iap_service.dart';

/// The device id the proof uses. The server-side proof (docs/local807/
/// server_proof.py) drives THIS same id to the Weekly subscription, so the
/// active-plan banner reads "Weekly — renews … · N new tours left".
const _proofUserId = 'sim-live807';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final prefs = await SharedPreferences.getInstance();
  await prefs.setString('user_id', _proofUserId);
  await prefs.setString('server_mode', 'local');
  await prefs.setString('server_ip', '127.0.0.1');
  await prefs.setBool('onboarding_complete', true);

  // Start listening to the StoreKit purchase stream at launch (StoreKit 2 on
  // iOS), exactly as the real app does, so the purchase sheet + restore work.
  await IapService.initAtStartup();

  runApp(const PlansProofApp());
}

class PlansProofApp extends StatelessWidget {
  const PlansProofApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Plans Proof — LOCAL-807B',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(primarySwatch: Colors.blue, useMaterial3: true),
      home: const PlansScreen(),
    );
  }
}
