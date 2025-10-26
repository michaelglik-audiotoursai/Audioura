import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'my_tours_screen.dart';
import 'my_news_screen.dart';

class ListenScreen extends StatefulWidget {
  const ListenScreen({super.key});

  @override
  State<ListenScreen> createState() => _ListenScreenState();
}

class _ListenScreenState extends State<ListenScreen> {
  String _appMode = 'Tours';

  @override
  void initState() {
    super.initState();
    _loadAppMode();
  }

  Future<void> _loadAppMode() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _appMode = prefs.getString('app_mode') ?? 'Tours';
    });
  }

  @override
  Widget build(BuildContext context) {
    // Reload app mode on every build (like tour generator does)
    _loadAppMode();
    
    // Return the appropriate screen based on current mode
    return _appMode == 'Articles' ? const MyNewsScreen() : const MyToursScreen();
  }
}