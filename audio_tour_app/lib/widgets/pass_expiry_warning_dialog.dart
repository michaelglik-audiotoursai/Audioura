// [LOCAL-732] The one dialog that warns a member, once on entry, that one or
// more community passes end within 3 days. Factored out of MainScreen so it can
// be widget-tested WITHOUT the network layer (MainScreen loads My communities
// over HTTP; the offline test builds this dialog directly from a list of
// ExpiringPass).
//
// It uses the shared, Flutter-free PassExpiryFormat.formatShort (unit-tested
// separately) for each line's text, e.g. "Fri 24 Oct · in 2 days".
//
// Wording is plain English, no store names (the task forbids them). ONE dialog
// lists ALL qualifying communities — not one dialog per community — with a
// Renew link per row and a single Later.

import 'package:flutter/material.dart';
import '../services/pass_expiry_format.dart';
import '../services/pass_expiry_warning.dart';

class PassExpiryWarningDialog extends StatelessWidget {
  final List<ExpiringPass> passes;

  /// Called with a community id when its row's Renew link is tapped. The caller
  /// closes the dialog and opens that community's page.
  final void Function(int communityId) onRenew;

  /// Called when Later is tapped. The caller closes the dialog.
  final VoidCallback onLater;

  /// Injectable for deterministic tests; defaults to DateTime.now().
  final DateTime? now;

  const PassExpiryWarningDialog({
    super.key,
    required this.passes,
    required this.onRenew,
    required this.onLater,
    this.now,
  });

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Community pass ending soon'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // One line per qualifying community, each with its own Renew link.
          for (final p in passes)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Text(
                      '${p.name}: ends '
                      '${PassExpiryFormat.formatShort(p.expiresAt, now: now) ?? ''}',
                      key: Key('pass_warning_row_${p.id}'),
                    ),
                  ),
                  TextButton(
                    key: Key('pass_warning_renew_${p.id}'),
                    onPressed: () => onRenew(p.id),
                    child: const Text('Renew'),
                  ),
                ],
              ),
            ),
          const SizedBox(height: 4),
          const Text(
            'Renew to keep getting new episodes and tours. Buying another pass '
            'adds its days to your remaining time.',
            style: TextStyle(color: Colors.grey),
          ),
        ],
      ),
      actions: [
        TextButton(
          key: const Key('pass_warning_later'),
          onPressed: onLater,
          child: const Text('Later'),
        ),
      ],
    );
  }
}
