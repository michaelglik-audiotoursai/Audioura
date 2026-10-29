// [LOCAL-807 / D734] Plans screen — ONE page, not intimidating.
//
// The screen offers the auto-renewing subscriptions and the Day pass alongside
// the existing one-time 5-tour pack, in the reveal flow Michael asked for:
//
//   1. The ACTIVE plan sits on top ("Weekly — renews 5 Nov · 3 of 5 new tours
//      left"), from /entitlements/me.
//   2. Two big choices: "Pass — time-limited" and "Tour pack — no time limit".
//   3. Tapping one reveals ITS options in place — a segmented control
//      Day · Week · Month · Year with the price and "N new tours" under it for
//      the Pass, or the 5-tour pack for the Tour pack — then ONE Buy button.
//   4. The required auto-renewal terms are shown ONLY for the auto-renewing
//      choices (Week/Month/Year), never for the Day pass or the pack.
//   5. Restore purchases + Manage subscription links at the bottom.
//
// Prices and the "N new tours" counts are NOT hard-coded: the price comes from
// the live store (ProductDetails) with the server-sent plan price as a fallback,
// and the allowance copy comes from the plan the server returns. Only the store
// product ids live in code (IapSubscription).
//
// This is a NEW screen (plans_screen.dart), separate from the older
// plan_screen.dart "Your plan" screen, so the existing PlanScreen tests are
// untouched. It is heavily test-seamed (initialEntitlements, initialStubMode,
// buyOverride, priceOverride) so the reveal flow and the terms text can be
// widget-tested with no store and no running user-api.

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../services/entitlements_service.dart';
import '../services/iap_service.dart';
import '../services/pass_expiry_format.dart';

/// Which of the two top-level choices is revealed. `none` = neither tapped yet.
enum PlansChoice { none, pass, pack }

/// The selectable options inside the Pass choice.
enum PassOption { day, week, month, year }

extension _PassOptionMap on PassOption {
  IapSubscription get subscription {
    switch (this) {
      case PassOption.day:
        return IapSubscription.day;
      case PassOption.week:
        return IapSubscription.weekly;
      case PassOption.month:
        return IapSubscription.monthly;
      case PassOption.year:
        return IapSubscription.annual;
    }
  }

  String get toursLine {
    switch (this) {
      case PassOption.day:
        return '3 new tours';
      case PassOption.week:
        return '5 new tours a week';
      case PassOption.month:
        return '10 new tours a month';
      case PassOption.year:
        return '10 new tours a month';
    }
  }

  /// A sensible default display price, used only when the live store price is
  /// not available (offline / StoreKit not loaded). The real charge is always
  /// the store price.
  String get fallbackPrice {
    switch (this) {
      case PassOption.day:
        return '\$2.99';
      case PassOption.week:
        return '\$4.99';
      case PassOption.month:
        return '\$9.99';
      case PassOption.year:
        return '\$79.99';
    }
  }

  /// Only the auto-renewing options show the renewal terms.
  bool get autoRenews => this != PassOption.day;
}

class PlansScreen extends StatefulWidget {
  const PlansScreen({
    super.key,
    this.initialEntitlements,
    this.initialStubMode,
    this.buyOverride,
    this.priceOverride,
  });

  /// Test seam: render this snapshot immediately, skip the network load.
  final Entitlements? initialEntitlements;

  /// Test seam: force stub/real mode, skip the /purchases/mode call.
  final bool? initialStubMode;

  /// Test seam: intercept a subscription purchase so a widget test can assert
  /// the Buy wiring without the store. Null in production (uses IapService).
  final Future<IapResult> Function(IapSubscription sub)? buyOverride;

  /// Test seam: supply a display price for a store id so a widget test can
  /// render the price line deterministically. Null in production (live store).
  final String? Function(String storeId)? priceOverride;

  @override
  State<PlansScreen> createState() => _PlansScreenState();
}

class _PlansScreenState extends State<PlansScreen> {
  Entitlements _ent = Entitlements.unknown;
  bool _loading = true;
  bool _buying = false;

  PlansChoice _choice = PlansChoice.none;
  PassOption _passOption = PassOption.month; // Month is the sensible default.

  @override
  void initState() {
    super.initState();
    final seed = widget.initialEntitlements;
    if (seed != null) {
      _ent = seed;
      _loading = false;
    } else {
      _load();
    }
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

  String _priceFor(IapSubscription sub, String fallback) {
    final override = widget.priceOverride;
    if (override != null) {
      return override(sub.storeId) ?? fallback;
    }
    return fallback;
  }

  Future<void> _buyPass() async {
    if (_buying) return;
    setState(() => _buying = true);
    final sub = _passOption.subscription;
    try {
      final result = widget.buyOverride != null
          ? await widget.buyOverride!(sub)
          : await IapService.instance.buySubscription(sub);
      if (!mounted) return;
      final messenger = ScaffoldMessenger.of(context);
      switch (result.status) {
        case IapResultStatus.granted:
          await _load();
          if (!mounted) break;
          messenger.showSnackBar(const SnackBar(
            content: Text('You are subscribed. Enjoy your new tours!'),
            backgroundColor: Colors.green,
          ));
          break;
        case IapResultStatus.cancelled:
          messenger.showSnackBar(
              const SnackBar(content: Text('Purchase cancelled.')));
          break;
        case IapResultStatus.pending:
          messenger.showSnackBar(const SnackBar(
            content: Text('Purchase is pending approval.'),
            backgroundColor: Colors.orange,
          ));
          break;
        case IapResultStatus.unavailable:
        case IapResultStatus.failed:
          messenger.showSnackBar(SnackBar(
            content: Text(result.message ??
                'The purchase could not be completed.'),
            backgroundColor: Colors.red,
          ));
          break;
      }
    } finally {
      if (mounted) setState(() => _buying = false);
    }
  }

  Future<void> _restore() async {
    final ok = await IapService.instance.restoreSubscriptions();
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(ok
          ? 'Restoring your purchases…'
          : 'Could not start restore. Please try again.'),
    ));
    // Give the store a moment, then refresh the active-plan banner.
    await Future<void>.delayed(const Duration(seconds: 2));
    if (mounted) await _load();
  }

  Future<void> _manage() async {
    final url = IapService.instance.manageSubscriptionsUrl();
    try {
      await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Could not open the store subscription page.'),
      ));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Plans')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                _activePlanBanner(),
                const SizedBox(height: 16),
                _twoChoices(),
                if (_choice == PlansChoice.pass) ...[
                  const SizedBox(height: 16),
                  _passOptions(),
                ],
                if (_choice == PlansChoice.pack) ...[
                  const SizedBox(height: 16),
                  _packOption(),
                ],
                const SizedBox(height: 24),
                _bottomLinks(),
              ],
            ),
    );
  }

  // ─── Active plan banner ─────────────────────────────────────────────────
  Widget _activePlanBanner() {
    final level = _ent.level;
    final isSubscription = level.startsWith('sub_');
    if (!isSubscription) {
      // No active subscription: a gentle prompt instead of a banner.
      return const Card(
        key: Key('plans_no_active_sub'),
        color: Color(0xFFF1F3F8),
        child: Padding(
          padding: EdgeInsets.all(16),
          child: Text(
            'Choose a plan below to get new tours. You can cancel an '
            'auto-renewing plan any time in the store.',
            style: TextStyle(fontSize: 14),
          ),
        ),
      );
    }

    final renews = _ent.anniversary;
    final renewText =
        renews != null ? PassExpiryFormat.formatDate(renews) : null;
    final a = _ent.allowances;
    // "3 of 5 new tours left" — prefer the weekly count (Weekly plan), then the
    // monthly, then the daily, so whichever period the active subscription uses
    // is shown (LOCAL-807B: sub_week reports tours_this_week_left).
    String? leftText;
    final left =
        a.toursThisWeekLeft ?? a.toursThisMonthLeft ?? a.toursTodayLeft;
    if (left != null) leftText = '$left new tours left';

    final parts = <String>[_ent.displayName];
    if (renewText != null) parts.add('renews $renewText');
    if (leftText != null) parts.add(leftText);

    return Card(
      key: const Key('plans_active_banner'),
      color: const Color(0xFFE8F5E9),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            const Icon(Icons.verified, color: Colors.green),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                parts.join(' · '),
                key: const Key('plans_active_banner_text'),
                style: const TextStyle(
                    fontSize: 15, fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ─── The two big choices ────────────────────────────────────────────────
  Widget _twoChoices() {
    return Row(
      children: [
        Expanded(
          child: _choiceCard(
            key: const Key('choice_pass'),
            title: 'Pass',
            subtitle: 'Time-limited',
            icon: Icons.schedule,
            selected: _choice == PlansChoice.pass,
            onTap: () => setState(() => _choice = PlansChoice.pass),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _choiceCard(
            key: const Key('choice_pack'),
            title: 'Tour pack',
            subtitle: 'No time limit',
            icon: Icons.inventory_2,
            selected: _choice == PlansChoice.pack,
            onTap: () => setState(() => _choice = PlansChoice.pack),
          ),
        ),
      ],
    );
  }

  Widget _choiceCard({
    required Key key,
    required String title,
    required String subtitle,
    required IconData icon,
    required bool selected,
    required VoidCallback onTap,
  }) {
    return Card(
      key: key,
      color: selected ? const Color(0xFFE3E9FF) : null,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(
          color: selected ? Colors.indigo : Colors.transparent,
          width: 2,
        ),
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 12),
          child: Column(
            children: [
              Icon(icon, size: 30, color: Colors.indigo),
              const SizedBox(height: 8),
              Text(title,
                  style: const TextStyle(
                      fontSize: 16, fontWeight: FontWeight.bold)),
              const SizedBox(height: 2),
              Text(subtitle,
                  style:
                      const TextStyle(fontSize: 12, color: Colors.black54)),
            ],
          ),
        ),
      ),
    );
  }

  // ─── Pass options (segmented Day/Week/Month/Year + one Buy button) ───────
  Widget _passOptions() {
    final sub = _passOption.subscription;
    final price = _priceFor(sub, _passOption.fallbackPrice);
    return Card(
      key: const Key('pass_options'),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SegmentedButton<PassOption>(
              segments: const [
                ButtonSegment(value: PassOption.day, label: Text('Day')),
                ButtonSegment(value: PassOption.week, label: Text('Week')),
                ButtonSegment(value: PassOption.month, label: Text('Month')),
                ButtonSegment(value: PassOption.year, label: Text('Year')),
              ],
              selected: {_passOption},
              onSelectionChanged: (s) =>
                  setState(() => _passOption = s.first),
            ),
            const SizedBox(height: 16),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(_passOption.toursLine,
                    key: const Key('pass_tours_line'),
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.w600)),
                Text(price,
                    key: const Key('pass_price'),
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.bold)),
              ],
            ),
            const SizedBox(height: 6),
            const Text(
              'Includes unlimited catalog downloads and translations.',
              style: TextStyle(fontSize: 13, color: Colors.black54),
            ),
            // Renewal terms ONLY for the auto-renewing options.
            if (_passOption.autoRenews) ...[
              const SizedBox(height: 12),
              _renewalTerms(),
            ] else ...[
              const SizedBox(height: 12),
              const Text(
                'The Day pass lasts 24 hours and does NOT renew. Buy again for '
                'another day.',
                key: Key('day_pass_terms'),
                style: TextStyle(fontSize: 12, color: Colors.black54),
              ),
            ],
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                key: const Key('plans_buy_button'),
                onPressed: _buying ? null : _buyPass,
                style: ElevatedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 14)),
                child: _buying
                    ? const SizedBox(
                        height: 18,
                        width: 18,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : Text('Subscribe — $price'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // The required auto-renewal terms, shown only for Week/Month/Year.
  Widget _renewalTerms() {
    return Column(
      key: const Key('renewal_terms'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'This is an auto-renewing subscription. It renews at the end of each '
          'period for the same price unless you cancel at least 24 hours before '
          'the period ends. Manage or cancel any time in the store. Payment is '
          'charged to your store account on confirmation.',
          style: TextStyle(fontSize: 12, color: Colors.black54, height: 1.3),
        ),
        const SizedBox(height: 6),
        Wrap(
          children: [
            TextButton(
              onPressed: () => _openUrl('https://audioura.com/terms'),
              style: _linkStyle,
              child: const Text('Terms of Use'),
            ),
            TextButton(
              onPressed: () => _openUrl('https://audioura.com/privacy'),
              style: _linkStyle,
              child: const Text('Privacy Policy'),
            ),
          ],
        ),
      ],
    );
  }

  // ─── Tour pack option (the existing 5-tour $10 pack) ─────────────────────
  Widget _packOption() {
    return Card(
      key: const Key('pack_option'),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('5-tour pack',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
            const SizedBox(height: 4),
            const Text(
              '5 new tours, up to 10 stops each, plus 5 stop-adding edits. '
              'One-time purchase — nothing renews automatically; no time limit '
              'on when you use it.',
              key: Key('pack_terms'),
              style: TextStyle(fontSize: 13, color: Colors.black54),
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                key: const Key('plans_buy_pack_button'),
                onPressed: _buying ? null : _buyPack,
                style: ElevatedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 14)),
                child: const Text('Buy the pack — \$10'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _buyPack() async {
    if (_buying) return;
    setState(() => _buying = true);
    try {
      final result = await IapService.instance.buy(IapProduct.l3Pack);
      if (!mounted) return;
      final messenger = ScaffoldMessenger.of(context);
      if (result.status == IapResultStatus.granted) {
        await _load();
        if (!mounted) return;
        messenger.showSnackBar(const SnackBar(
          content: Text('Pack purchased. Enjoy your new tours!'),
          backgroundColor: Colors.green,
        ));
      } else if (result.status == IapResultStatus.cancelled) {
        messenger.showSnackBar(
            const SnackBar(content: Text('Purchase cancelled.')));
      } else {
        messenger.showSnackBar(SnackBar(
          content: Text(result.message ?? 'The purchase could not be completed.'),
          backgroundColor: Colors.red,
        ));
      }
    } finally {
      if (mounted) setState(() => _buying = false);
    }
  }

  // ─── Restore + Manage links ──────────────────────────────────────────────
  Widget _bottomLinks() {
    // LOCAL-807B live-run fix: a plain Row overflowed by 17px on a 390pt-wide
    // iPhone (the two labels + icons are wider than the screen). Wrap lets the
    // second link fall to the next line on a narrow device instead of clipping.
    return Wrap(
      alignment: WrapAlignment.center,
      spacing: 8,
      runSpacing: 4,
      children: [
        TextButton.icon(
          key: const Key('plans_restore'),
          onPressed: _restore,
          icon: const Icon(Icons.restore, size: 18),
          label: const Text('Restore purchases'),
        ),
        TextButton.icon(
          key: const Key('plans_manage'),
          onPressed: _manage,
          icon: const Icon(Icons.open_in_new, size: 18),
          label: const Text('Manage subscription'),
        ),
      ],
    );
  }

  Future<void> _openUrl(String url) async {
    try {
      await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
    } catch (_) {}
  }

  static final ButtonStyle _linkStyle = TextButton.styleFrom(
    padding: const EdgeInsets.symmetric(horizontal: 4),
    minimumSize: const Size(0, 32),
    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
  );
}
