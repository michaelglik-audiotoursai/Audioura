import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'screens/main_screen.dart';
import 'screens/onboarding_screen.dart';

class MainScreenWithTreatsTab extends StatelessWidget {
  const MainScreenWithTreatsTab({super.key});

  @override
  Widget build(BuildContext context) {
    return const MainScreen(initialTab: 3); // Treats tab index
  }
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  print('=== AUDIOTOURS DEV v1.2.9+61 STARTING ===');
  
  // Clear old article cache to fix 404 errors
  try {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('cached_articles');
    print('🗑️ Cleared old article cache to fix 404 errors');

    // SECURITY (wdvrday4pk): one-time purge of the persisted debug log.
    // Builds before 2.3.2 wrote plaintext credentials and the AES key into
    // SharedPreferences 'debug_logs'. Any device that ran an affected build
    // still has those secrets on disk. Clear them once on first launch of the
    // fixed version. Keyed so it runs exactly once (and again if we ever bump
    // the guard key for a future incident).
    const purgeFlag = 'debug_logs_security_purged_v2';
    if (!(prefs.getBool(purgeFlag) ?? false)) {
      await prefs.remove('debug_logs');
      await prefs.setBool(purgeFlag, true);
      print('🔒 Purged legacy debug_logs (one-time security cleanup)');
    }
  } catch (e) {
    print('Warning: Could not clear cache: $e');
  }
  
  // Initialize InAppWebView (debugging enabled by default in debug mode)
  
  runApp(const AudioTourApp());
}

class AudioTourApp extends StatefulWidget {
  const AudioTourApp({super.key});

  @override
  State<AudioTourApp> createState() => _AudioTourAppState();
}

class _AudioTourAppState extends State<AudioTourApp> {
  bool _onboardingComplete = true; // assume complete until loaded

  @override
  void initState() {
    super.initState();
    _checkOnboarding();
  }

  Future<void> _checkOnboarding() async {
    final prefs = await SharedPreferences.getInstance();
    final complete = prefs.getBool('onboarding_complete') ?? false;
    if (mounted) setState(() { _onboardingComplete = complete; });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Audioura',
      theme: ThemeData(
        primarySwatch: Colors.blue,
        useMaterial3: true,
      ),
      home: _onboardingComplete
          ? const MainScreen()
          : OnboardingScreen(onComplete: () {
              setState(() { _onboardingComplete = true; });
            }),
      routes: {
        '/treats': (context) => const MainScreenWithTreatsTab(),
      },
    );
  }
}