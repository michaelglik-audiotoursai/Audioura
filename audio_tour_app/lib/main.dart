import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'screens/main_screen.dart';

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
  } catch (e) {
    print('Warning: Could not clear cache: $e');
  }
  
  // Initialize InAppWebView (debugging enabled by default in debug mode)
  
  runApp(const AudioTourApp());
}

class AudioTourApp extends StatelessWidget {
  const AudioTourApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Audio Tour Generator',
      theme: ThemeData(
        primarySwatch: Colors.blue,
        useMaterial3: true,
      ),
      home: const MainScreen(),
      routes: {
        '/treats': (context) => const MainScreenWithTreatsTab(),
      },
    );
  }
}