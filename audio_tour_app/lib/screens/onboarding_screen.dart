import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Single-question onboarding shown on first launch.
/// "What brings you here?" → 4 emoji choices → sets default narrative tone.
class OnboardingScreen extends StatelessWidget {
  final VoidCallback onComplete;

  const OnboardingScreen({super.key, required this.onComplete});

  static const _choices = [
    {'emoji': '🎨', 'label': 'Art & Culture', 'tone': 'art'},
    {'emoji': '📖', 'label': 'History', 'tone': 'history'},
    {'emoji': '👨\u200d👩\u200d👧', 'label': 'Family Fun', 'tone': 'family'},
    {'emoji': '✈️', 'label': 'First-time Visitor', 'tone': 'firsttime'},
  ];

  Future<void> _selectTone(BuildContext context, String tone) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('narrative_tone', tone);
    await prefs.setBool('onboarding_complete', true);
    onComplete();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF2c3e50),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 48),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Text(
                'Welcome to Audioura',
                style: TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
              const SizedBox(height: 16),
              const Text(
                'What brings you here?',
                style: TextStyle(
                  fontSize: 20,
                  color: Colors.white70,
                ),
              ),
              const SizedBox(height: 48),
              ...(_choices.map((choice) => Padding(
                padding: const EdgeInsets.only(bottom: 16),
                child: SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    onPressed: () => _selectTone(context, choice['tone']!),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.white,
                      foregroundColor: const Color(0xFF2c3e50),
                      padding: const EdgeInsets.symmetric(vertical: 18),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    child: Text(
                      '${choice['emoji']}  ${choice['label']}',
                      style: const TextStyle(fontSize: 18),
                    ),
                  ),
                ),
              ))),
              const SizedBox(height: 24),
              TextButton(
                onPressed: () => _selectTone(context, 'general'),
                child: const Text(
                  'Skip',
                  style: TextStyle(color: Colors.white54, fontSize: 16),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
