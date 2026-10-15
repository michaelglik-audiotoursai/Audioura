// [LOCAL-695] Recovery code + Restore my Listen page.
//
// Two sections, reachable from About:
//   1. "Recovery code" — generate (server-side) and COPY a one-time anonymous
//      code, with a one-line explanation. The code is shown ONCE here; it is
//      stored only hashed on the server. Offered proactively right after the
//      listener's FIRST purchase (see maybeOfferRecoveryCode), and always
//      available from About.
//   2. "Restore my Listen page" — enter a code on a NEW phone; the server links
//      this device to the profile, unlinks the old one, and returns the Listen-
//      page list (free tours, paid tours re-download WITHOUT paying again, news
//      articles). The app then re-downloads them.
//
// Anonymity is preserved: the code is not an email/password, and it never leaves
// the device except to the restore endpoint. "Save this code. On a new phone, it
// restores your Listen page."

import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../config/endpoints.dart';
import '../utils/recovery_code.dart';

/// SharedPreferences key: have we proactively offered the recovery code after
/// the first purchase yet? Set once so we never nag.
const String kRecoveryOfferedKey = 'recovery_code_offered';

/// Call this right after a purchase completes. The FIRST time it is called it
/// routes the user to the Recovery code screen with a short explanation, then
/// records that we have offered it so it never happens again. Safe to call on
/// every purchase. Returns true if it navigated.
Future<bool> maybeOfferRecoveryCode(BuildContext context) async {
  final prefs = await SharedPreferences.getInstance();
  if (prefs.getBool(kRecoveryOfferedKey) == true) return false;
  await prefs.setBool(kRecoveryOfferedKey, true);
  if (!context.mounted) return false;
  await Navigator.push(
    context,
    MaterialPageRoute(
      builder: (_) => const RecoveryCodeScreen(offeredAfterPurchase: true),
    ),
  );
  return true;
}

class RecoveryCodeScreen extends StatefulWidget {
  /// When true, the screen opens with a short banner explaining why it appeared
  /// (shown once, right after the first purchase).
  final bool offeredAfterPurchase;
  const RecoveryCodeScreen({super.key, this.offeredAfterPurchase = false});

  @override
  State<RecoveryCodeScreen> createState() => _RecoveryCodeScreenState();
}

class _RecoveryCodeScreenState extends State<RecoveryCodeScreen> {
  String? _code; // the plaintext code, shown once after generation
  bool _generating = false;
  bool _restoring = false;
  final TextEditingController _restoreController = TextEditingController();
  String? _restoreMessage;
  Color _restoreMessageColor = Colors.black87;

  Future<String> _userId() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('user_id') ?? '';
  }

  Future<void> _generate() async {
    setState(() {
      _generating = true;
      _restoreMessage = null;
    });
    try {
      final userId = await _userId();
      if (userId.isEmpty) {
        _snack('No user id yet — open the app fully first.', Colors.red);
        return;
      }
      // LOCAL-705 (D661): route through the storied-compat helper so a server
      // that does not offer recovery codes (Storied/Stable — a route-missing
      // 404 or the whole service absent) shows the "Preview only" line instead
      // of a raw "(404)" / exception. A present route behaves exactly as before.
      final resp = await Endpoints.postOrFeatureUnavailable(
        Service.orchestrator,
        '/recovery-code/generate',
        body: {'user_id': userId},
        timeout: const Duration(seconds: 15),
      );
      if (resp.statusCode == 201) {
        final body = Endpoints.tryDecodeMap(resp.body) ?? const {};
        setState(() {
          _code = formatRecoveryCodeForDisplay(body['code']?.toString());
        });
      } else {
        _snack('Could not create a recovery code (${resp.statusCode}).', Colors.red);
      }
    } on FeatureUnavailableException catch (e) {
      _snack(e.message, Colors.red);
    } catch (e) {
      _snack('Could not create a recovery code: $e', Colors.red);
    } finally {
      if (mounted) setState(() => _generating = false);
    }
  }

  Future<void> _copy() async {
    if (_code == null) return;
    await Clipboard.setData(ClipboardData(text: _code!));
    _snack('Recovery code copied. Save it somewhere safe.', Colors.green);
  }

  Future<void> _restore() async {
    final entered = _restoreController.text;
    if (!isPlausibleRecoveryCode(entered)) {
      setState(() {
        _restoreMessage = 'That does not look like a complete recovery code.';
        _restoreMessageColor = Colors.red;
      });
      return;
    }
    setState(() {
      _restoring = true;
      _restoreMessage = null;
    });
    try {
      final userId = await _userId();
      if (userId.isEmpty) {
        _setRestoreMessage('No user id yet — open the app fully first.', Colors.red);
        return;
      }
      // LOCAL-705 (D661): helper-routed — a Storied server without the restore
      // route (route-missing 404 / absent service) shows "Preview only" rather
      // than a raw status/exception. Present-route handling is unchanged.
      final resp = await Endpoints.postOrFeatureUnavailable(
        Service.orchestrator,
        '/recovery-code/restore',
        body: {
          'user_id': userId,
          'code': normalizeRecoveryCode(entered),
        },
        timeout: const Duration(seconds: 20),
      );
      final body = _tryDecode(resp.body);
      if (resp.statusCode == 200) {
        final listen = (body?['listen_page'] as Map<String, dynamic>?) ?? {};
        final paid = (listen['paid_tours'] as List?)?.length ?? 0;
        final free = (listen['free_tours'] as List?)?.length ?? 0;
        final news = (listen['news_articles'] as List?)?.length ?? 0;
        _setRestoreMessage(
          'Listen page restored: $paid paid tour(s), $free free tour(s), '
          '$news news article(s). They will re-download — paid tours without '
          'paying again.',
          Colors.green,
        );
        // Persist the restored list so the Listen page re-downloads it. The
        // Listen page reads these keys on next open (best-effort hand-off).
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString('restore_listen_page', jsonEncode(listen));
      } else if (resp.statusCode == 401) {
        _setRestoreMessage('That recovery code was not recognised.', Colors.red);
      } else if (resp.statusCode == 429) {
        _setRestoreMessage(
          'Too many attempts. Please wait an hour and try again.', Colors.orange);
      } else if (resp.statusCode == 409) {
        _setRestoreMessage(
          'This profile has been restored too many times recently. '
          'Please contact support.',
          Colors.orange,
        );
      } else {
        _setRestoreMessage('Could not restore (${resp.statusCode}).', Colors.red);
      }
    } on FeatureUnavailableException catch (e) {
      _setRestoreMessage(e.message, Colors.red);
    } catch (e) {
      _setRestoreMessage('Could not restore: $e', Colors.red);
    } finally {
      if (mounted) setState(() => _restoring = false);
    }
  }

  Map<String, dynamic>? _tryDecode(String s) {
    try {
      return jsonDecode(s) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }

  void _setRestoreMessage(String msg, Color color) {
    if (!mounted) return;
    setState(() {
      _restoreMessage = msg;
      _restoreMessageColor = color;
    });
  }

  void _snack(String msg, Color color) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(msg), backgroundColor: color));
  }

  @override
  void dispose() {
    _restoreController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Recovery code'),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (widget.offeredAfterPurchase)
            Container(
              width: double.infinity,
              margin: const EdgeInsets.only(bottom: 16),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.amber.shade50,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.amber.shade300),
              ),
              child: const Text(
                "You just made your first purchase. Save a recovery code now so "
                "you can get your Listen page back if you lose or replace your "
                "phone.",
                style: TextStyle(fontSize: 13),
              ),
            ),
          // ── Section 1: Recovery code ──────────────────────────────────────
          _sectionCard(
            icon: Icons.vpn_key,
            color: Colors.teal,
            title: 'Your recovery code',
            children: [
              const Text(
                'Save this code. On a new phone, it restores your Listen page '
                '(your tours and news). It is anonymous — not an email or '
                'password — and we only ever store a scrambled (hashed) copy, '
                'never the code itself.',
                style: TextStyle(fontSize: 13),
              ),
              const SizedBox(height: 12),
              if (_code != null) ...[
                SelectableText(
                  _code!,
                  style: const TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 2,
                    fontFamily: 'monospace',
                  ),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    ElevatedButton.icon(
                      onPressed: _copy,
                      icon: const Icon(Icons.copy),
                      label: const Text('Copy'),
                    ),
                    const SizedBox(width: 10),
                    OutlinedButton.icon(
                      onPressed: _generating ? null : _generate,
                      icon: const Icon(Icons.refresh),
                      label: const Text('New code'),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                const Text(
                  'Generating a new code replaces the old one — the old code '
                  'will stop working.',
                  style: TextStyle(fontSize: 11, color: Colors.black54),
                ),
              ] else
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: _generating ? null : _generate,
                    icon: _generating
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.vpn_key),
                    label: Text(_generating ? 'Creating…' : 'Create my recovery code'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.teal,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 20),
          // ── Section 2: Restore my Listen page ─────────────────────────────
          _sectionCard(
            icon: Icons.restore,
            color: Colors.indigo,
            title: 'Restore my Listen page',
            children: [
              const Text(
                'Got a new phone? Enter your recovery code to bring back your '
                'Listen page. Your paid tours re-download without paying again. '
                'This moves your profile here and signs it out of your old phone.',
                style: TextStyle(fontSize: 13),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _restoreController,
                textCapitalization: TextCapitalization.characters,
                decoration: const InputDecoration(
                  labelText: 'Recovery code',
                  hintText: 'ABCD-EFGH-JKMN-PQRS',
                  border: OutlineInputBorder(),
                ),
                style: const TextStyle(fontFamily: 'monospace', letterSpacing: 1.5),
              ),
              const SizedBox(height: 10),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: _restoring ? null : _restore,
                  icon: _restoring
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.restore),
                  label: Text(_restoring ? 'Restoring…' : 'Restore my Listen page'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.indigo,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                  ),
                ),
              ),
              if (_restoreMessage != null) ...[
                const SizedBox(height: 10),
                Text(
                  _restoreMessage!,
                  style: TextStyle(fontSize: 13, color: _restoreMessageColor),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }

  Widget _sectionCard({
    required IconData icon,
    required Color color,
    required String title,
    required List<Widget> children,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 28, color: color),
              const SizedBox(width: 10),
              Text(
                title,
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  color: color,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          ...children,
        ],
      ),
    );
  }
}
