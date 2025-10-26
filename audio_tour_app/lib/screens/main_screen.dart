import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'tour_generator_screen.dart';
import 'my_tours_screen.dart';
import 'treats_screen.dart';
import 'about_screen.dart';
import 'home_screen.dart';
import '../services/notification_service.dart';
import '../services/background_service.dart';

class MainScreen extends StatefulWidget {
  final int initialTab;
  const MainScreen({super.key, this.initialTab = 0});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> with WidgetsBindingObserver {
  late int _selectedIndex;

  final List<Widget> _screens = [
    const HomeScreen(),
    const TourGeneratorScreen(),
    const MyToursScreen(),
    const TreatsScreen(),
    const AboutScreen(),
  ];

  @override
  void initState() {
    super.initState();
    _selectedIndex = widget.initialTab;
    WidgetsBinding.instance.addObserver(this);
    _initializeNotifications();
    BackgroundService.startBackgroundMonitoring();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    BackgroundService.stopBackgroundMonitoring();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      BackgroundService.startBackgroundMonitoring();
      
      // Refresh Home, My Tours, or Treats screen when app is resumed
      if (_selectedIndex == 0 || _selectedIndex == 2 || _selectedIndex == 3) {
        setState(() {});
      }
    }
  }

  Future<void> _initializeNotifications() async {
    await NotificationService.initialize((NotificationResponse response) {
      // Navigate to My Tours tab when notification is tapped
      setState(() {
        _selectedIndex = 2; // My Tours tab index (unchanged)
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _screens[_selectedIndex],
      bottomNavigationBar: BottomNavigationBar(
        type: BottomNavigationBarType.fixed,
        currentIndex: _selectedIndex,
        onTap: (index) => setState(() => _selectedIndex = index),
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.home),
            label: 'Home',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.add),
            label: 'Generate Tour',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.library_music),
            label: 'Listen',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.local_cafe),
            label: 'Treats',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.info),
            label: 'About',
          ),
        ],
      ),
    );
  }
}