// [LOCAL-598] Plan screen — Settings → "Your plan".
//
// SUBSCRIPTION_LEVELS.md (D613). Shows, from /entitlements/me:
//   • the current level (plain words),
//   • the allowances left,
//   • the anniversary date,
//   • buy buttons for L3 ($10 Pack) and L4 (Curator, $25) — ALWAYS visible on
//     BOTH iOS and Android ([LOCAL-699]); in stub mode they run a TEST PURCHASE
//     (no real charge) and show a banner, otherwise they drive the real store.
//   • the five-level table in plain words.
//
// This screen replaces the old wallet / PPU / Unlimited UI (wallet_screen.dart),
// which is no longer reachable from Settings (see about_screen.dart).

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import '../services/entitlements_service.dart';
import '../services/iap_service.dart';
import '../services/pass_expiry_format.dart';
import '../utils/plan_left_summary.dart';

class PlanScreen extends StatefulWidget {
  const PlanScreen({super.key, this.initialEntitlements, this.initialStubMode});

  /// [LOCAL-610] Test seam only: when provided, the screen renders this
  /// snapshot immediately and skips the network load, so widget tests can
  /// exercise the level-aware Free/code card and the rules text at any level
  /// without a running user-api. Null in production (the default), where the
  /// screen loads from EntitlementsService.me() as before.
  final Entitlements? initialEntitlements;

  /// [LOCAL-699] Test seam only: when provided, the screen uses this value for
  /// the stub/real purchase mode and skips the GET /purchases/mode call, so a
  /// widget test can render either the TEST PURCHASE banner (true) or the real
  /// Buy buttons (false) with no running user-api. Null in production (the
  /// default), where the screen asks the server via purchasesModeIsStub().
  final bool? initialStubMode;

  @override
  State<PlanScreen> createState() => _PlanScreenState();
}

class _PlanScreenState extends State<PlanScreen> {
  Entitlements _ent = Entitlements.unknown;
  bool _loading = true;
  // True when the last load found no network at all (Wi-Fi and mobile off).
  bool _offline = false;
  bool _buying = false;
  bool _claiming = false;

  // [LOCAL-699] Whether the server verifies purchases in stub mode (asked via
  // GET /purchases/mode). When true the Buy buttons run a TEST PURCHASE on BOTH
  // platforms and the card shows a clearly-labelled TEST PURCHASE banner; when
  // false they drive the real store (StoreKit on iOS, Play billing on Android).
  // Null until resolved; the buttons are shown regardless (never gated on it).
  bool _stubMode = false;

  // [LOCAL-604 / LOCAL-735] The single code box on the "Upgrade your plan" card.
  final TextEditingController _codeController = TextEditingController();

  @override
  void dispose() {
    _codeController.dispose();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    final seed = widget.initialEntitlements;
    // [LOCAL-699] Resolve the purchase mode. Honour the test seam when given;
    // otherwise ask the server (purchasesModeIsStub) without blocking the
    // initial paint — the buttons are shown regardless and simply re-label when
    // the mode arrives.
    final seedStub = widget.initialStubMode;
    if (seedStub != null) {
      _stubMode = seedStub;
    } else {
      _resolveStubMode();
    }
    if (seed != null) {
      // Test seam: render the injected snapshot without any network call.
      _ent = seed;
      _loading = false;
    } else {
      _load();
    }
  }

  /// [LOCAL-699] Ask the server whether it verifies purchases in stub mode and
  /// update the card (never blocks the buttons from showing). No-op in a test
  /// that passed initialStubMode.
  Future<void> _resolveStubMode() async {
    final stub = await IapService.instance.purchasesModeIsStub();
    if (!mounted) return;
    setState(() => _stubMode = stub);
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final ent = await EntitlementsService.me();
    var offline = false;
    if (ent.levels.isEmpty) {
      try {
        // Bounded: the check must never keep the screen on its spinner.
        final results = await Connectivity()
            .checkConnectivity()
            .timeout(const Duration(seconds: 2));
        offline = results.every((r) => r == ConnectivityResult.none);
      } catch (_) {}
    }
    if (!mounted) return;
    setState(() {
      _ent = ent;
      _offline = offline;
      _loading = false;
    });
  }

  Future<void> _buy(IapProduct product) async {
    if (_buying) return;
    setState(() => _buying = true);
    try {
      // [LOCAL-699] In stub mode (a LOCAL/Mac Mini server, IAP_VERIFY_MODE=stub,
      // no Apple/Google pack products yet) run a TEST PURCHASE on BOTH
      // platforms; otherwise drive the real store (StoreKit on iOS, Play billing
      // on Android).
      final result = _stubMode
          ? await IapService.instance.testPurchasePack(product)
          : await IapService.instance.buy(product);
      if (!mounted) return;
      final messenger = ScaffoldMessenger.of(context);
      switch (result.status) {
        case IapResultStatus.granted:
          // [LOCAL-733 / D703] Refresh first so the message reflects the NEW
          // balance (carry-over may have ADDED to what was left), then say what
          // the member now has and until when, e.g. "You now have 8 new tours
          // and 6 edits until 22 Nov 2026."
          await _load();
          if (!mounted) break;
          final endLocal = PassExpiryFormat.parse(_ent.anniversaryAt);
          final endText = endLocal != null
              ? PassExpiryFormat.formatDate(endLocal)
              : null;
          final whatsLeft =
              PlanLeftSummary.purchaseMessage(_ent, endDate: endText);
          messenger.showSnackBar(SnackBar(
            content: Text(_stubMode
                ? 'Test purchase complete. $whatsLeft'
                : whatsLeft),
            backgroundColor: Colors.green,
          ));
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
          // [LOCAL-699] Show the SPECIFIC reason the service returned (e.g.
          // "This pack isn't available on this store yet.") instead of a single
          // generic line, so a missing store product reads as a clear
          // store-not-ready message rather than a silent failure.
          messenger.showSnackBar(SnackBar(
            content: Text(result.message ??
                'In-app purchases are not available on this device.'),
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
                  // [LOCAL-735] Order (Michael, 2026-10-22): the current plan on
                  // top, then "Upgrade your plan" (the code box) on EVERY level,
                  // then "Apply for the Free plan" ONLY on Introduction, then
                  // "Buy a pack" and "The plans" unchanged.
                  _currentPlanCard(),
                  const SizedBox(height: 16),
                  _upgradeCard(),
                  if (_ent.level == 'l1') ...[
                    const SizedBox(height: 16),
                    _applyFreeCard(),
                  ],
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

    // [LOCAL-733 / D703] One block at the top of the card that tells the member
    // what is left and when the pack ends, e.g.
    //   "$10 Pack · 8 new tours and 6 stop-adding edits left · until 22 Nov 2026".
    // Introduction shows nothing here (cardLine returns null); Free shows the
    // day/month count. The date reuses PassExpiryFormat.formatDate (LOCAL-731).
    final endDateLocal = PassExpiryFormat.parse(_ent.anniversaryAt);
    final endDateText =
        endDateLocal != null ? PassExpiryFormat.formatDate(endDateLocal) : null;
    final leftLine = PlanLeftSummary.cardLine(_ent, endDate: endDateText);

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
            if (leftLine != null) ...[
              const SizedBox(height: 8),
              Text(
                leftLine,
                key: const Key('plan_left_line'),
                style: const TextStyle(
                    fontSize: 14, fontWeight: FontWeight.w600),
              ),
            ],
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
    // [LOCAL-699] Buy buttons are ALWAYS visible on BOTH iOS and Android for the
    // $10 Pack and Curator — never gated on platform or a billing flag (the
    // Pixel build that hid them predated kAndroidBillingEnabled going true).
    // In stub mode the buttons run a TEST PURCHASE (see _buy / _stubMode) and
    // the card shows a clearly-labelled banner so a tester knows no real charge
    // is made; a missing store product on a real server surfaces a clear
    // "not available on this store yet" message rather than failing silently.
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
              'Packs are one-time purchases. Nothing renews automatically. '
              'Refunds are handled by Apple or Google.',
              style: TextStyle(fontSize: 12, color: Colors.black54),
            ),
            if (_stubMode) ...[
              const SizedBox(height: 12),
              _testPurchaseBanner(),
            ],
            const SizedBox(height: 14),
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
        ),
      ),
    );
  }

  // [LOCAL-699] The amber TEST PURCHASE banner shown on a stub-verification
  // server, mirroring the tour Buy sheet's banner (tour_buy_sheet.dart).
  Widget _testPurchaseBanner() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: Colors.amber.shade100,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.amber.shade700),
      ),
      child: Row(
        children: [
          Icon(Icons.science, color: Colors.amber.shade900, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'TEST PURCHASE — no real charge. These buttons complete a fake '
              'purchase on the local server so the plan buy flow can be tested '
              'end to end.',
              style: TextStyle(fontSize: 12, color: Colors.amber.shade900),
            ),
          ),
        ],
      ),
    );
  }

  // [LOCAL-735] "Upgrade your plan" — shown on EVERY level (Michael,
  // 2026-10-22). Directly beneath the current-plan card: one short line and the
  // single code box. One box accepts every code kind (an Audioura level code, a
  // friend's invitation, or a Free-plan queue code); the server decides which
  // and switches the plan. This replaces the old level-aware "Get the Free
  // plan" / "Have a code?" framing — the queue action moved to _applyFreeCard.
  Widget _upgradeCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Upgrade your plan',
                key: Key('upgrade_card_title'),
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            const Text(
              'Have a code from Audioura, a friend\u2019s invitation or the '
              'Free-plan queue? Enter it here to switch your plan.',
              style: TextStyle(fontSize: 13, height: 1.3),
            ),
            const SizedBox(height: 12),
            _codeBox(),
          ],
        ),
      ),
    );
  }

  // [LOCAL-735] "Apply for the Free plan" — shown ONLY on Introduction (l1).
  // Explains the generation allowance the Free plan grants (from the plan data
  // the screen already loaded, not hard-coded) and carries the existing queue
  // action and queue-position / pending-offer text. Hidden on Free, paid,
  // tester and admin — those levels either already have a seat or cannot join
  // the queue, so inviting them to "apply" makes no sense.
  Widget _applyFreeCard() {
    final pos = _ent.queuePosition;
    final pending = _ent.pendingOfferCode;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Apply for the Free plan',
                key: Key('apply_free_card_title'),
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text(
              _freePlanAllowanceText(),
              key: const Key('apply_free_allowance_text'),
              style: const TextStyle(fontSize: 13, height: 1.3),
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
                  'Enter it in "Upgrade your plan" above within 10 minutes to '
                  'claim the Free plan.',
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
          ],
        ),
      ),
    );
  }

  // [LOCAL-735] The Free-plan generation allowance, in plain words. The numbers
  // come from the plan data the screen already loads — the Free (l2) level's
  // max_stops — not hard-coded, with the stated sentence as the fallback when
  // the server did not send the l2 row (older payload / offline).
  String _freePlanAllowanceText() {
    int? maxStops;
    for (final l in _ent.levels) {
      if (l.planId == 'l2') {
        maxStops = l.maxStops;
        break;
      }
    }
    final stops = maxStops ?? 5;
    return 'On the Free plan you can generate your own tours: 1 new tour a day, '
        '3 a month, up to $stops stops. Free seats are limited, so we keep a '
        'queue. Join it and we email you a code when a seat opens.';
  }

  // The shared code box + "Use code" button, used by "Upgrade your plan".
  Widget _codeBox() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
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
              Text(
                _offline
                    ? 'This device has no Internet connection, so we can\u2019t '
                        'reach our servers and the plan details aren\u2019t '
                        'available right now. Please connect to the Internet, '
                        'then pull down to refresh.'
                    : 'We can\u2019t reach our servers, so the plan details '
                        'aren\u2019t available right now. Please make sure you '
                        'are connected to the Internet, then pull down to '
                        'refresh.',
                key: const Key('plan_details_unavailable'),
                style: const TextStyle(fontSize: 13, color: Colors.black54),
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
          'expires, and you can buy another pack at any time. Buying another '
          'pack adds it to what\u2019s left and starts a new month. Nothing '
          'renews automatically.',
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
            'Lets you generate your own tours: 1 new tour a day, 3 a month, up '
            'to ${lvl.maxStops ?? 5} stops. Downloads from the Home page and '
            'translations stay free, as in the Introduction.');
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
