// [LOCAL-726 item 2 — lawyer review item 2] The first-run informational notice.
//
// Shown ONCE per device: on a new install's first launch, and ONCE after this
// update for an existing install (both lack the versioned ack key below until
// they tap "Got it"). Short, calm and friendly — not a legalese wall. It states
// the four things the lawyer asked for:
//   * tours are written with AI and may contain errors;
//   * they are for information and entertainment, not navigation or safety
//     advice;
//   * follow local signs and laws, and walk, ride or drive at your own risk;
//   * a link to the Terms (https://audioura.com/terms).
//
// The ack is stored per device in SharedPreferences under a VERSIONED key, so
// bumping the version in a future release could re-show a materially changed
// notice. main.dart gates the app on [InformationalNoticeScreen.seen]; tapping
// "Got it" calls [InformationalNoticeScreen.markSeen] and continues to the app.

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

class InformationalNoticeScreen extends StatelessWidget {
  final VoidCallback onAcknowledged;

  const InformationalNoticeScreen({super.key, required this.onAcknowledged});

  /// The per-device ack key. Versioned so a future, materially different notice
  /// can be re-shown by bumping the suffix. v1 is the LOCAL-726 first-run notice.
  static const String ackKey = 'info_notice_ack_v1';

  /// The published Terms page (lawyer review item 13: exact, consistent URL).
  static const String termsUrl = 'https://audioura.com/terms';

  /// Has this device already acknowledged the notice? main.dart calls this to
  /// decide whether to show the screen. A device that has never seen it (new
  /// install OR an existing install updating to this version) returns false.
  static Future<bool> seen() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(ackKey) ?? false;
  }

  /// Record the acknowledgement (per device). Idempotent.
  static Future<void> markSeen() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(ackKey, true);
  }

  Future<void> _openTerms() async {
    final uri = Uri.parse(termsUrl);
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }

  Future<void> _acknowledge() async {
    await markSeen();
    onAcknowledged();
  }

  Widget _point(IconData icon, String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: Colors.white70, size: 22),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              text,
              style: const TextStyle(
                  fontSize: 15, color: Colors.white, height: 1.35),
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF2c3e50),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 32),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 8),
              const Text(
                'A quick note before you explore',
                style: TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                    color: Colors.white),
              ),
              const SizedBox(height: 20),
              Expanded(
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _point(Icons.auto_awesome,
                          'Tours are written with AI. They can get things '
                          'wrong, so enjoy them as stories, not as fact-checked '
                          'guides.'),
                      _point(Icons.menu_book_outlined,
                          'They are for information and entertainment — not '
                          'navigation, directions, or safety advice.'),
                      _point(Icons.directions_walk,
                          'Follow local signs and laws. Watch where you are '
                          'going, and walk, ride or drive at your own risk.'),
                      const SizedBox(height: 4),
                      InkWell(
                        onTap: _openTerms,
                        child: const Padding(
                          padding: EdgeInsets.symmetric(vertical: 8),
                          child: Row(
                            children: [
                              Icon(Icons.open_in_new,
                                  size: 18, color: Colors.white70),
                              SizedBox(width: 8),
                              Text(
                                'Read the Terms',
                                style: TextStyle(
                                  fontSize: 15,
                                  color: Colors.white,
                                  decoration: TextDecoration.underline,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  key: const Key('info_notice_got_it'),
                  onPressed: _acknowledge,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.white,
                    foregroundColor: const Color(0xFF2c3e50),
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                  child: const Text('Got it',
                      style: TextStyle(
                          fontSize: 17, fontWeight: FontWeight.bold)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
