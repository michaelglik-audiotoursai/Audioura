// [LOCAL-598] Plan screen — Settings → "Your plan".
//
// SUBSCRIPTION_LEVELS.md (D613). Shows, from /entitlements/me:
//   • the current level (plain words),
//   • the allowances left,
//   • the anniversary date,
//   • buy buttons for L3 ($10 pack) and L4 ($25 round) — iOS only; the Android
//     buttons are hidden behind kAndroidBillingEnabled (Google Play is out of
//     scope for LOCAL-598),
//   • the five-level table in plain words.
//
// This screen replaces the old wallet / PPU / Unlimited UI (wallet_screen.dart),
// which is no longer reachable from Settings (see about_screen.dart).

import 'dart:io' show Platform;
import 'package:flutter/material.dart';
import '../services/entitlements_service.dart';
import '../services/iap_service.dart';

class PlanScreen extends StatefulWidget {
  const PlanScreen({super.key});

  @override
  State<PlanScreen> createState() => _PlanScreenState();
}

class _PlanScreenState extends State<PlanScreen> {
  Entitlements _ent = Entitlements.unknown;
  bool _loading = true;
  bool _buying = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final ent = await EntitlementsService.me();
    if (!mounted) return;
    setState(() {
      _ent = ent;
      _loading = false;
    });
  }

  Future<void> _buy(IapProduct product) async {
    if (_buying) return;
    setState(() => _buying = true);
    try {
      final result = await IapService.instance.buy(product);
      if (!mounted) return;
      final messenger = ScaffoldMessenger.of(context);
      switch (result.status) {
        case IapResultStatus.granted:
          messenger.showSnackBar(const SnackBar(
            content: Text('Purchase complete — your plan is updated.'),
            backgroundColor: Colors.green,
          ));
          await _load();
          break;
        case IapResultStatus.cancelled:
          messenger.showSnackBar(const SnackBar(
            content: Text('Purchase cancelled.'),
          ));
          break;
        case IapResultStatus.pending:
          messenger.showSnackBar(const SnackBar(
            content: Text('Purchase is pending approval.'),
            backgroundColor: Colors.orange,
          ));
          break;
        case IapResultStatus.unavailable:
          messenger.showSnackBar(const SnackBar(
            content: Text('In-app purchases are not available on this device.'),
            backgroundColor: Colors.red,
          ));
          break;
        case IapResultStatus.failed:
          messenger.showSnackBar(SnackBar(
            content: Text(result.message ??
                'The purchase could not be verified. You were not granted the pack.'),
            backgroundColor: Colors.red,
          ));
          break;
      }
    } finally {
      if (mounted) setState(() => _buying = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Your plan')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  _currentPlanCard(),
                  const SizedBox(height: 16),
                  _buyCard(),
                  const SizedBox(height: 16),
                  _levelTableCard(),
                ],
              ),
            ),
    );
  }

  Widget _currentPlanCard() {
    final a = _ent.allowances;
    final rows = <Widget>[];
    void add(String label, int? value) {
      if (value != null) rows.add(_kv(label, '$value'));
    }

    add('Tours left today', a.toursTodayLeft);
    add('Tours left this month', a.toursThisMonthLeft);
    add('Fresh tours left in pack', a.freshLeft);
    add('Stop-adding edits left', a.editsLeft);
    add('Operations left', a.opsLeft);

    final ann = _ent.anniversary;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.workspace_premium, color: Colors.indigo),
                const SizedBox(width: 10),
                Text('Current plan: ${_ent.levelLabel}',
                    style: const TextStyle(
                        fontSize: 18, fontWeight: FontWeight.bold)),
              ],
            ),
            const SizedBox(height: 12),
            if (rows.isEmpty)
              const Text(
                'Listening, downloads, articles, reusing translations and edits '
                'that only re-voice text are always free.',
                style: TextStyle(fontSize: 13),
              )
            else
              ...rows,
            if (ann != null) ...[
              const Divider(height: 24),
              _kv('Pack renews on', _formatDate(ann)),
              const SizedBox(height: 4),
              const Text(
                'Nothing is charged automatically. Renew by buying again. '
                'No refunds.',
                style: TextStyle(fontSize: 12, color: Colors.black54),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buyCard() {
    // Google Play billing is out of scope for LOCAL-598: hide the buy buttons
    // on Android behind the flag. iOS shows them (StoreKit 2).
    final androidHidden = Platform.isAndroid && !kAndroidBillingEnabled;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Buy a pack',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 4),
            const Text(
              'Packs are one-time purchases. Nothing renews automatically and '
              'there are no refunds.',
              style: TextStyle(fontSize: 12, color: Colors.black54),
            ),
            const SizedBox(height: 14),
            if (androidHidden)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: Text(
                  'In-app purchases are coming to Android soon. For now, packs '
                  'are available on iOS.',
                  style: TextStyle(fontSize: 13, color: Colors.black54),
                ),
              )
            else ...[
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: _buying ? null : () => _buy(IapProduct.l3Pack),
                  style: ElevatedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 14)),
                  child: const Text('\$10 pack — 5 fresh tours, up to 10 stops'),
                ),
              ),
              const SizedBox(height: 10),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: _buying ? null : () => _buy(IapProduct.l4Round),
                  style: ElevatedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 14)),
                  child: const Text(
                      '\$25 round — 25 operations, up to 25 stops'),
                ),
              ),
              if (_buying)
                const Padding(
                  padding: EdgeInsets.only(top: 12),
                  child: Center(child: CircularProgressIndicator()),
                ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _levelTableCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('The five levels',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            _levelRow('Install (free)',
                'Listen, download, read articles, reuse translations and '
                're-voice edits. No new tours.'),
            _levelRow('Free',
                '1 new tour a day, 3 a month, up to 5 stops, from material '
                'that already exists (no fresh research). Everything the '
                'install level has.'),
            _levelRow('\$10 pack',
                '5 fresh tours, up to 10 stops each, and 5 stop-adding edits. '
                'One-time purchase.'),
            _levelRow('\$25 round',
                '25 operations (new tours or edits, any mix), up to 25 stops '
                'each. One-time purchase.'),
            _levelRow('Tester',
                'By invitation: 10 tours a day, 50 a month, up to 5 stops.'),
            const SizedBox(height: 8),
            const Text(
              'Edits that only re-voice existing text are always free at every '
              'level.',
              style: TextStyle(fontSize: 12, color: Colors.black54),
            ),
          ],
        ),
      ),
    );
  }

  Widget _levelRow(String name, String desc) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(name,
              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
          const SizedBox(height: 2),
          Text(desc, style: const TextStyle(fontSize: 13, height: 1.3)),
        ],
      ),
    );
  }

  Widget _kv(String k, String v) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(k, style: const TextStyle(fontSize: 14)),
          Text(v,
              style:
                  const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }

  static String _formatDate(DateTime d) {
    const months = [
      'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
    ];
    return '${d.day} ${months[d.month - 1]} ${d.year}';
  }
}
