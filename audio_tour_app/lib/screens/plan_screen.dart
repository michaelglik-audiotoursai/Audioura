// [LOCAL-598] Plan screen — Settings → "Your plan".
//
// SUBSCRIPTION_LEVELS.md (D613). Shows, from /entitlements/me:
//   • the current level (plain words),
//   • the allowances left,
//   • the anniversary date,
//   • buy buttons for L3 ($10 Pack) and L4 (Curator, $25) — iOS only; the Android
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
  bool _claiming = false;

  // [LOCAL-604] The single code box on the Free card.
  final TextEditingController _codeController = TextEditingController();

  @override
  void dispose() {
    _codeController.dispose();
    super.dispose();
  }

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
                  _freeCard(),
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
                Text('Current plan: ${_ent.displayName}',
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
                  child: const Text('\$10 Pack — 5 new tours + 5 edits, up to 10 stops'),
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
                      'Curator (\$25) — 25 tours or edits, up to 25 stops, sell your tours'),
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

  // [LOCAL-610 req 1] The Free/code card is LEVEL-AWARE. The code box is always
  // present (it is how any level switches level with a level code, and how a
  // friend's invitation or a queue offer is redeemed), but the queue and the
  // "Get the Free plan" framing only make sense for the install level:
  //
  //   • l1 (Introduction): the only level that can still JOIN the free queue.
  //     Title "Get the Free plan", show BOTH the queue action and the code box.
  //   • l2 (Free): already has a free seat — never invite it to "get" the Free
  //     plan. Title "Have a code?", code box ONLY, no queue.
  //   • paid (l3/l4), tester, admin: title "Have a code?", code box ONLY, no
  //     queue and no "Get the Free plan".
  //
  // One text box accepts any of the three code kinds; the server decides which.
  Widget _freeCard() {
    final isIntroduction = _ent.level == 'l1';
    return isIntroduction ? _freeCardIntroduction() : _codeOnlyCard();
  }

  // l1 only: the full card — ask for a queue place (with an email) OR enter a
  // code. [LOCAL-604 D619]
  Widget _freeCardIntroduction() {
    final pos = _ent.queuePosition;
    final pending = _ent.pendingOfferCode;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Get the Free plan',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            const Text(
              'Ask for a place in the queue, or enter a code. The code arrives '
              'by email and is valid for 10 minutes once the queue reaches you — '
              'or it can be an invitation from a friend on a paid plan.',
              style: TextStyle(fontSize: 13, height: 1.3),
            ),
            const SizedBox(height: 14),
            if (pending != null) ...[
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: const Color(0xFFE8F5E9),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  'A seat is ready for you. Your code: $pending\n'
                  'Enter it below within 10 minutes to claim the Free plan.',
                  style: const TextStyle(fontSize: 13),
                ),
              ),
              const SizedBox(height: 12),
            ] else if (pos != null) ...[
              Text('You are #$pos in the queue. We will email you a code when a '
                  'seat frees.',
                  style: const TextStyle(fontSize: 13, color: Colors.black54)),
              const SizedBox(height: 12),
            ],
            SizedBox(
              width: double.infinity,
              child: OutlinedButton(
                onPressed: _claiming ? null : _promptJoinQueue,
                style: OutlinedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 14)),
                child: Text(pos != null ? 'Update my queue email' : 'Join the queue'),
              ),
            ),
            const SizedBox(height: 16),
            _codeBox(withHeading: true),
          ],
        ),
      ),
    );
  }

  // l2 / paid / tester / admin: a small "Have a code?" card with the code box
  // only. No queue, no "Get the Free plan".
  Widget _codeOnlyCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Have a code?',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            const Text(
              'Enter a level code, a friend\u2019s invitation, or a queue code. '
              'This is how you switch levels.',
              style: TextStyle(fontSize: 13, height: 1.3),
            ),
            const SizedBox(height: 12),
            _codeBox(withHeading: false),
          ],
        ),
      ),
    );
  }

  // The shared code box + "Use code" button. [withHeading] adds the
  // "I have a code" label used on the l1 card above the queue action.
  Widget _codeBox({required bool withHeading}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (withHeading) ...[
          const Text('I have a code',
              style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
        ],
        TextField(
          controller: _codeController,
          enabled: !_claiming,
          textCapitalization: TextCapitalization.characters,
          decoration: const InputDecoration(
            hintText: 'Enter your code',
            border: OutlineInputBorder(),
            isDense: true,
          ),
        ),
        const SizedBox(height: 10),
        SizedBox(
          width: double.infinity,
          child: ElevatedButton(
            onPressed: _claiming ? null : _submitCode,
            style: ElevatedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 14)),
            child: _claiming
                ? const SizedBox(
                    height: 18, width: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Use code'),
          ),
        ),
      ],
    );
  }

  Future<void> _promptJoinQueue() async {
    final controller = TextEditingController();
    final email = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Join the queue'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'We will email you a code when a free seat opens up. The code is '
              'valid for 10 minutes once the queue reaches you.',
              style: TextStyle(fontSize: 13),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: controller,
              keyboardType: TextInputType.emailAddress,
              autofocus: true,
              decoration: const InputDecoration(
                labelText: 'Email address',
                border: OutlineInputBorder(),
                isDense: true,
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, controller.text.trim()),
            child: const Text('Join'),
          ),
        ],
      ),
    );
    if (email == null || email.isEmpty) return;
    if (!_looksLikeEmail(email)) {
      _snack('Please enter a valid email address.', Colors.red);
      return;
    }
    setState(() => _claiming = true);
    final updated = await EntitlementsService.joinQueue(email);
    if (!mounted) return;
    setState(() {
      _claiming = false;
      if (updated != null) _ent = updated;
    });
    _snack(
      updated != null
          ? 'You are in the queue. We will email a code when a seat frees.'
          : 'Could not join the queue. Please try again.',
      updated != null ? Colors.green : Colors.red,
    );
  }

  Future<void> _submitCode() async {
    final code = _codeController.text.trim();
    if (code.isEmpty) {
      _snack('Enter a code first.', Colors.red);
      return;
    }
    setState(() => _claiming = true);
    final result = await EntitlementsService.claim(code);
    if (!mounted) return;
    if (result.ok) {
      // Refresh from the server so the whole screen (level, allowances,
      // display name) reflects the new plan.
      _codeController.clear();
      await _load();
      if (!mounted) return;
      setState(() => _claiming = false);
      _snack('Your plan is now: ${_ent.displayName}.', Colors.green);
    } else {
      setState(() => _claiming = false);
      _snack(result.message, Colors.red);
    }
  }

  static bool _looksLikeEmail(String s) =>
      RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(s);

  void _snack(String msg, Color color) {
    ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(msg), backgroundColor: color));
  }

  Widget _levelTableCard() {
    // [LOCAL-604 D619] Render only the VISIBLE levels the server returned, in
    // plan order, with their display names. Tester and Administrator are hidden
    // server-side and never appear here. If the server sent no levels (older
    // payload), fall back to a short note rather than hardcoding a stale table.
    final levels = _ent.levels;
    final rows = <Widget>[];
    for (final lvl in levels) {
      rows.add(_levelRow(lvl.displayName, _levelBullets(lvl)));
    }
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('The plans',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            if (rows.isEmpty)
              const Text(
                'Plan details are briefly unavailable. Pull to refresh.',
                style: TextStyle(fontSize: 13, color: Colors.black54),
              )
            else
              ...rows,
            const SizedBox(height: 8),
            const Text(
              'Edits that only re-voice existing text are always free at every '
              'level.',
              style: TextStyle(fontSize: 12, color: Colors.black54),
            ),
            // [LOCAL-610 req 3] Plain rules under the levels. The Free
            // inactivity number comes from the API (plans.inactivity_days), not
            // a constant. The pack/Curator rule states the one-month, no-carry,
            // early-purchase-replaces behaviour (subscription_levels.grant_pack,
            // D613) in plain words; it changes nothing server-side.
            const Divider(height: 24),
            _rulesText(),
          ],
        ),
      ),
    );
  }

  // [LOCAL-610 req 3] The two plain-words rules shown under the level list.
  Widget _rulesText() {
    final days = _ent.freeInactivityDays;
    final ann = _ent.anniversary;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Free',
            style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold)),
        const SizedBox(height: 2),
        Text(
          'Stay active: open Audioura at least once a week. After $days days '
          'without a visit your Free plan returns to Introduction, and you can '
          'rejoin the queue.',
          style: const TextStyle(fontSize: 13, height: 1.3),
        ),
        const SizedBox(height: 12),
        const Text('\$10 Pack and Curator',
            style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold)),
        const SizedBox(height: 2),
        const Text(
          'Each purchase is good for one month. Anything unused after a month '
          'expires, and you can buy another pack at any time. Buying early '
          'starts a new month and replaces what\u2019s left. Nothing renews '
          'automatically.',
          style: TextStyle(fontSize: 13, height: 1.3),
        ),
        if (ann != null) ...[
          const SizedBox(height: 6),
          Text(
            'Your current month ends on ${_formatDate(ann)}.',
            style: const TextStyle(
                fontSize: 13, height: 1.3, fontWeight: FontWeight.w600),
          ),
        ],
      ],
    );
  }

  // Build the plain-words bullet list for a level. The headline feature leads;
  // Curator's first bullet is selling. Pack and Curator show the invitations
  // line. Everything else is derived from the server-sent fields.
  List<String> _levelBulletList(PlanLevel lvl) {
    final bullets = <String>[];
    switch (lvl.planId) {
      case 'l1': // Introduction
        bullets.add(
            'Listen, download, read articles, reuse translations and re-voice '
            'edits. No new tours.');
        break;
      case 'l2': // Free
        bullets.add(
            '1 new tour a day, 3 a month, up to ${lvl.maxStops ?? 5} stops, from '
            'material that already exists. Everything the Introduction has.');
        break;
      case 'l3': // $10 Pack
        bullets.add(
            '5 fresh tours, up to ${lvl.maxStops ?? 10} stops each, and 5 '
            'stop-adding edits. One-time purchase.');
        break;
      case 'l4': // Curator — selling is the headline feature.
        if (lvl.canSell) bullets.add('Create tours for sale.');
        bullets.add(
            '25 operations (new tours or edits, any mix), up to '
            '${lvl.maxStops ?? 25} stops each. One-time purchase.');
        break;
      default:
        bullets.add('${lvl.displayName} plan.');
    }
    // Pack and Curator can send free-subscription invitations.
    if (lvl.referralsAllowed > 0 && (lvl.planId == 'l3' || lvl.planId == 'l4')) {
      bullets.add('Send free-subscription invitations (3 lifetime / 5 per month).');
    }
    return bullets;
  }

  String _levelBullets(PlanLevel lvl) => _levelBulletList(lvl)
      .map((b) => '• $b')
      .join('\n');

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
