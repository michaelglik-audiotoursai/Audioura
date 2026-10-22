// [LOCAL-731 / D701] The member-facing pass-expiry UI, factored out of
// community_page_screen so it can be widget-tested WITHOUT standing up the
// network layer (the screen loads its Community over HTTP, which the offline
// tests cannot drive). Both the screen and the tests build these widgets
// directly from a [MyStatus].
//
// It uses the shared, Flutter-free [PassExpiryFormat] (unit-tested separately)
// for the actual text.

import 'package:flutter/material.dart';
import '../services/communities_models.dart';
import '../services/pass_expiry_format.dart';
/// The "My status" body on the community page: the membership line, the
/// readable expiry line (D701), and — for an ACTIVE member of a PAID community —
/// the grey "Buying another pass adds its days to your remaining time." note
/// that sits just above the pass list (D701: renewing adds days).
///
/// [now] is injectable so widget tests are deterministic.
class CommunityMyStatus extends StatelessWidget {
  final MyStatus myStatus;

  /// Whether the community sells passes. The adds-days note only makes sense
  /// for a paid community (a free one has no passes to buy).
  final bool isPaid;

  /// The owner is not a member and never sees an expiry or the note.
  final bool isOwner;

  final DateTime? now;

  const CommunityMyStatus({
    super.key,
    required this.myStatus,
    required this.isPaid,
    this.isOwner = false,
    this.now,
  });

  @override
  Widget build(BuildContext context) {
    final expiryLine = isOwner ? null : PassExpiryFormat.format(myStatus.expiresAt, now: now);
    final showAddsDays = !isOwner && isPaid && myStatus.isMember && myStatus.active;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(myStatus.isMember
            ? (myStatus.active
                ? 'Active member'
                : 'Membership expired — renew to listen to new content')
            : 'Not a member'),
        if (expiryLine != null)
          Text(
            expiryLine,
            key: const Key('my_status_expiry'),
            style: TextStyle(
              color: myStatus.active ? Colors.grey : Theme.of(context).colorScheme.error,
            ),
          ),
        if (showAddsDays)
          const Padding(
            padding: EdgeInsets.only(top: 4),
            child: Text(
              'Buying another pass adds its days to your remaining time.',
              key: Key('adds_days_note'),
              style: TextStyle(color: Colors.grey, fontStyle: FontStyle.italic),
            ),
          ),
      ],
    );
  }
}

/// [LOCAL-731 / D701] The subtitle for a My-communities list row: the
/// membership/member-count line, then the readable expiry (grey when active,
/// the theme error colour when expired). Shared with the screen so the tests
/// exercise the real markup.
class JoinedCommunitySubtitle extends StatelessWidget {
  final JoinedCommunity community;
  final DateTime? now;

  const JoinedCommunitySubtitle({super.key, required this.community, this.now});

  @override
  Widget build(BuildContext context) {
    final c = community;
    final expiryLine = PassExpiryFormat.format(c.expiresAt, now: now);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '${c.active ? 'Active member' : 'Expired — renew to listen to new content'}'
          ' · ${CommunityCopy.memberCountLabel(c.memberCount)}',
        ),
        if (expiryLine != null)
          Text(
            expiryLine,
            key: Key('my_communities_expiry_${c.id}'),
            style: TextStyle(
              color: c.active
                  ? Colors.grey
                  : Theme.of(context).colorScheme.error,
            ),
          ),
      ],
    );
  }
}
