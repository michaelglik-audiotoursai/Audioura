// [LOCAL-598] Renewal UI — the sheet shown at/after a pack's anniversary and
// the one-time 3-day warning banner. SUBSCRIPTION_LEVELS.md (D613).
//
// Nothing renews automatically and there are no refunds: the copy says so in
// plain words. "Renew" takes the user to the plan screen to buy again (the
// buy buttons and the StoreKit flow live there); "Continue on the free level"
// lapses the device to L1 server-side.

import 'package:flutter/material.dart';
import '../services/entitlements_service.dart';

/// The user's choice from the renewal sheet.
enum RenewalChoice { renew, lapse }

/// Shows the modal renew-or-lapse sheet. Returns the user's choice, or null if
/// they dismissed it without choosing (treated as "ask again next open").
///
/// Dismissal is allowed (barrierDismissible/true) so a user mid-task is never
/// trapped; the server state is unchanged until they explicitly choose.
Future<RenewalChoice?> showRenewalSheet(
  BuildContext context, {
  required Entitlements entitlements,
}) {
  final anniversary = entitlements.anniversary;
  final dateStr = anniversary != null ? _formatDate(anniversary) : null;
  return showModalBottomSheet<RenewalChoice>(
    context: context,
    isScrollControlled: true,
    isDismissible: true,
    showDragHandle: true,
    builder: (ctx) => Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 8,
        bottom: 20 + MediaQuery.of(ctx).viewInsets.bottom,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Your pack\u2019s month is up',
            style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 12),
          Text(
            dateStr != null
                ? 'Your pack ran from your last purchase to $dateStr. '
                    'Nothing is charged automatically. You can renew by buying '
                    'again, or continue on the free level. There are no refunds.'
                : 'Nothing is charged automatically. You can renew by buying '
                    'again, or continue on the free level. There are no refunds.',
            style: const TextStyle(fontSize: 14, height: 1.4),
          ),
          const SizedBox(height: 20),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: () => Navigator.pop(ctx, RenewalChoice.renew),
              style: ElevatedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 14),
              ),
              child: const Text('Renew (\$10 / \$25)'),
            ),
          ),
          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton(
              onPressed: () => Navigator.pop(ctx, RenewalChoice.lapse),
              style: OutlinedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 14),
              ),
              child: const Text('Continue on the free level'),
            ),
          ),
        ],
      ),
    ),
  );
}

/// A one-time banner shown within 3 days of the anniversary. Material banners
/// are shown via ScaffoldMessenger; this helper builds and shows it with a
/// single "Got it" dismiss action.
void showRenewalWarningBanner(
  BuildContext context, {
  required Entitlements entitlements,
}) {
  final anniversary = entitlements.anniversary;
  final dateStr = anniversary != null ? _formatDate(anniversary) : 'soon';
  final messenger = ScaffoldMessenger.of(context);
  messenger.clearMaterialBanners();
  messenger.showMaterialBanner(
    MaterialBanner(
      backgroundColor: Colors.amber.shade50,
      leading: const Icon(Icons.info_outline, color: Colors.amber),
      content: Text(
        'Your pack renews on $dateStr only if you buy again \u2014 nothing is '
        'charged automatically. No refunds.',
        style: const TextStyle(fontSize: 13),
      ),
      actions: [
        TextButton(
          onPressed: () => messenger.hideCurrentMaterialBanner(),
          child: const Text('Got it'),
        ),
      ],
    ),
  );
}

/// Format a date as "6 Nov 2026" — short, locale-neutral, no time component.
String _formatDate(DateTime d) {
  const months = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];
  return '${d.day} ${months[d.month - 1]} ${d.year}';
}
