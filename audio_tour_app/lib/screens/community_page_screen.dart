// [LOCAL-690] Community page (D657 / D658 (c) + addenda).
//
// Shows the organiser (name, photo, bio, contact), description, rules + waiver
// (with an accept checkbox gating a paid join), the membership options (passes),
// the episodes/tours, and the member's own status + expiry. A free community
// joins with one tap; a paid community buys a pass through IapService (the SAME
// /purchases/verify path a tour purchase takes), in LOCAL stub mode via the
// clearly-labelled test purchase. A non-member sees the "This tour belongs to
// <Community>. Join to listen" framing. A Report action routes to the owner.
//
// Community tours DOWNLOAD by default (D658 addendum §) — the episode list this
// page surfaces is consumed by the player, which downloads rather than streams
// (CommunityRules.downloadByDefault()).

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/communities_service.dart';
import '../services/community_tour_service.dart';
import '../services/iap_service.dart';
import '../services/device_service.dart';
import '../services/document_acceptance_service.dart';
import '../widgets/tour_buy_sheet.dart' show TermsAgreeLine;
import 'communities_about_screen.dart' show CommunityInviteTools;

class CommunityPageScreen extends StatefulWidget {
  /// Open by community id (from a map pin or the Listen tab) …
  final int? communityId;

  /// … or by invite code (from the Home search box — the join flow).
  final String? joinCode;

  const CommunityPageScreen({super.key, this.communityId, this.joinCode})
      : assert(communityId != null || joinCode != null);

  @override
  State<CommunityPageScreen> createState() => _CommunityPageScreenState();
}

class _CommunityPageScreenState extends State<CommunityPageScreen> {
  Community? _community;
  bool _loading = true;
  bool _waiverAccepted = false;
  String? _userId;
  String? _error;
  // [LOCAL-701 / D663 §3] Tours MADE WITH Audioura for this community, listed
  // on the page like episodes. Populated for an active member / the owner only.
  List<CommunityTour> _communityTours = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final prefs = await SharedPreferences.getInstance();
    _userId = prefs.getString('user_id');
    Community? c;
    if (widget.joinCode != null) {
      c = await CommunitiesService.resolveByCode(widget.joinCode!, userId: _userId);
      if (c == null) {
        setState(() {
          _loading = false;
          _error = 'No community with that code.';
        });
        return;
      }
    } else {
      c = await CommunitiesService.get(widget.communityId!, userId: _userId);
    }
    // [LOCAL-701 / D663 §3] Load the community's Audioura-made tours. The server
    // returns an empty list for a non-member / expired member (expiry blocks new
    // content), so this is populated only when the member is active or owner.
    List<CommunityTour> ctours = const [];
    if (c != null) {
      final list =
          await CommunityTourService.communityTours(c.id, userId: _userId);
      if (list != null) ctours = list.tours;
    }
    setState(() {
      _community = c;
      _communityTours = ctours;
      _loading = false;
    });
  }

  Future<void> _joinFree() async {
    final c = _community;
    if (c == null || _userId == null) return;
    final updated = await CommunitiesService.joinFree(c.id, _userId!);
    if (updated != null && mounted) {
      setState(() => _community = updated);
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Joined — you can listen now.')));
    }
  }

  Future<void> _buyPass(CommunityPass pass) async {
    final c = _community;
    if (c == null) return;
    final isStub = await IapService.instance.isLocalStubMode();
    final result = isStub
        ? await IapService.instance
            .testPurchaseCommunityPass(pass.productId, c.id, pass.length)
        : await IapService.instance
            .buyCommunityPass(pass.productId, c.id, pass.length);
    if (!mounted) return;
    if (result.status == IapResultStatus.granted) {
      // [LOCAL-691] Buying a pass agrees to the Terms — record the acceptance.
      final userId = _userId ?? await DeviceService.getUserId();
      await DocumentAcceptanceService.record(userId, LegalDoc.terms);
      await _load(); // refresh my_status + episodes
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text('Membership active (${pass.label}).')));
      }
    } else if (result.status != IapResultStatus.cancelled) {
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(result.message ?? 'Purchase failed.')));
    }
  }

  Future<void> _report() async {
    final c = _community;
    if (c == null) return;
    await CommunitiesService.report(c.id, userId: _userId, reason: 'Reported from app');
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Report sent to the community owner.')));
    }
  }

  // ─── [LOCAL-702 / D663 §1] Organiser step-down + hand-over actions ──────────

  /// The owner taps "Step down as organiser" — a confirmation dialog, then the
  /// community enters hand-over (closed to new members, looking for a new one).
  Future<void> _stepDown() async {
    final c = _community;
    if (c == null || _userId == null) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Step down as organiser?'),
        content: const Text(
          'Your community stays open and playable for its current members, but '
          'it will stop taking new members while it looks for a new organiser. '
          'A member can volunteer and, once you pick them and they accept, they '
          'become the organiser and the community reopens.\n\n'
          'If no one takes over within 30 days, the community is archived — '
          'members keep what they have downloaded, but nothing new is added.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Step down')),
        ],
      ),
    );
    if (confirmed != true) return;
    final updated = await CommunitiesService.stepDown(c.id, _userId!);
    if (!mounted) return;
    if (updated != null) {
      setState(() => _community = updated);
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('You stepped down. Looking for a new organiser.')));
    } else {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Could not step down. Please try again.')));
    }
  }

  /// A member volunteers to take over the community.
  Future<void> _volunteer() async {
    final c = _community;
    if (c == null || _userId == null) return;
    final updated = await CommunitiesService.offerOrganiser(c.id, _userId!);
    if (!mounted) return;
    if (updated != null) {
      setState(() => _community = updated);
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('You volunteered to organise this community.')));
    }
  }

  /// A volunteer withdraws their offer.
  Future<void> _withdraw() async {
    final c = _community;
    if (c == null || _userId == null) return;
    final ok = await CommunitiesService.withdrawOffer(c.id, _userId!);
    if (!mounted) return;
    if (ok) {
      await _load();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Offer withdrawn.')));
      }
    }
  }

  /// The owner picks a volunteer to take over.
  Future<void> _pick(String memberUserId) async {
    final c = _community;
    if (c == null || _userId == null) return;
    final updated =
        await CommunitiesService.pickOrganiser(c.id, _userId!, memberUserId);
    if (!mounted) return;
    if (updated != null) {
      setState(() => _community = updated);
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Picked. They can now accept to become organiser.')));
    }
  }

  /// The picked member accepts and becomes the new organiser; community reopens.
  Future<void> _accept() async {
    final c = _community;
    if (c == null || _userId == null) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Become the organiser?'),
        content: const Text(
          'You will take over this community and agree to the Organiser Terms. '
          'The community reopens to new members straight away.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Not yet')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Accept & agree')),
        ],
      ),
    );
    if (confirmed != true) return;
    final updated = await CommunitiesService.acceptOrganiser(c.id, _userId!);
    if (!mounted) return;
    if (updated != null) {
      setState(() => _community = updated);
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('You are now the organiser. Welcome!')));
    }
  }

  /// The owner deletes a MEMBER-LESS community (D663 §1 d).
  Future<void> _deleteCommunity() async {
    final c = _community;
    if (c == null || _userId == null) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete this community?'),
        content: const Text(
          'This community has no members, so you can delete it. This cannot be '
          'undone.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.redAccent),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    final ok = await CommunitiesService.deleteCommunity(c.id, _userId!);
    if (!mounted) return;
    if (ok) {
      Navigator.of(context).pop(); // leave the deleted community's page
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Community deleted.')));
    } else {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Could not delete. A community with members cannot be '
              'deleted — step down instead.')));
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    final c = _community;
    if (c == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Community')),
        body: Center(child: Text(_error ?? 'Community not found.')),
      );
    }

    final canListen = c.myStatus.active;
    final needsWaiver = c.hasWaiver;
    final waiverOk = !needsWaiver || _waiverAccepted;

    return Scaffold(
      appBar: AppBar(
        title: Text(c.name),
        actions: [
          IconButton(
            tooltip: 'Report to owner',
            icon: const Icon(Icons.flag_outlined),
            onPressed: _report,
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Non-member join framing (D658 addendum 2 §3).
          if (!c.myStatus.isMember)
            Card(
              color: Theme.of(context).colorScheme.surfaceContainerHighest,
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Text(
                  c.joinMessage ?? CommunityRules.joinFraming(c.name),
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
              ),
            ),

          // [LOCAL-702 / D663 §1] Hand-over + archived banners and the member's
          // volunteer / accept actions.
          ..._handoverSection(c),

          // [LOCAL-703 / D664] The organiser's live launch countdown. Shown to
          // the OWNER while the community is active (hidden once archived — the
          // hand-over/archived banners cover that). Turns green "Launched 🎉"
          // once the bar is met.
          ..._launchCountdownSection(c),

          // Organiser card.
          _section('Organiser', [
            if (c.organiser.name != null) Text(c.organiser.name!,
                style: const TextStyle(fontWeight: FontWeight.bold)),
            if (c.organiser.bio != null) Padding(
                padding: const EdgeInsets.only(top: 4), child: Text(c.organiser.bio!)),
            if (c.organiser.contact != null) Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(c.organiser.contact!,
                    style: const TextStyle(color: Colors.blueGrey))),
          ]),

          if (c.description != null && c.description!.isNotEmpty)
            _section('About', [Text(c.description!)]),

          // [LOCAL-700 §4] The organiser's page ALWAYS carries the invite tools:
          // the code with Copy, Share, Email and Regenerate (old code dies).
          if (c.isOwner && (c.joinCode != null && c.joinCode!.isNotEmpty))
            Padding(
              padding: const EdgeInsets.only(top: 16),
              child: CommunityInviteTools(community: c),
            ),

          // [LOCAL-702 / D663 §1] Owner controls: pick a volunteer (during
          // hand-over), step down (while active), or delete a member-less one.
          ..._ownerControls(c),

          if (c.rulesText != null && c.rulesText!.isNotEmpty)
            _section('Rules', [Text(c.rulesText!)]),

          // Waiver with accept checkbox (gates a paid join / listen).
          if (needsWaiver)
            _section('Waiver', [
              Text(c.waiverText ?? ''),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                value: _waiverAccepted,
                onChanged: (v) => setState(() => _waiverAccepted = v ?? false),
                title: const Text('I accept the waiver and rules'),
              ),
            ]),

          // My status.
          _section('My status', [
            Text(c.myStatus.isMember
                ? (c.myStatus.active ? 'Active member' : 'Membership expired — renew to listen to new content')
                : 'Not a member'),
            if (c.myStatus.expiresAt != null)
              Text('Expires: ${c.myStatus.expiresAt}',
                  style: const TextStyle(color: Colors.grey)),
          ]),

          // Membership options / join. Hidden while the community is closed to
          // new members (hand-over / archived) — only the banner shows then.
          if (!canListen && c.acceptsNewMembers) ...[
            if (c.isPaid) ...[
              _sectionTitle('Membership passes'),
              const Padding(
                padding: EdgeInsets.only(bottom: 4),
                child: TermsAgreeLine(),
              ),
              ...c.passes.map((p) => Card(
                    child: ListTile(
                      title: Text(p.label),
                      subtitle: Text('${p.durationDays} days'),
                      trailing: ElevatedButton(
                        onPressed: waiverOk ? () => _buyPass(p) : null,
                        child: const Text('Buy'),
                      ),
                    ),
                  )),
              if (!waiverOk)
                const Padding(
                  padding: EdgeInsets.only(top: 8),
                  child: Text('Accept the waiver above to buy a pass.',
                      style: TextStyle(color: Colors.redAccent)),
                ),
            ] else
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: ElevatedButton(
                  onPressed: waiverOk ? _joinFree : null,
                  child: const Text('Join (free)'),
                ),
              ),
          ],

          // Episodes — only when the member is active (expiry blocks new
          // content). An active member/owner sees the list; others see the
          // count only.
          _sectionTitle('Episodes (${c.episodeCount})'),
          if (canListen)
            ...c.episodes.map((e) => ListTile(
                  leading: CircleAvatar(child: Text('${e.position}')),
                  title: Text(e.title),
                  subtitle: Text(e.source == 'feed' ? 'From feed' : 'Owner link'),
                ))
          else
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Text('Join to listen to the episodes.'),
            ),

          // [LOCAL-701 / D663 §3] Tours MADE WITH Audioura for this community,
          // listed like episodes. The server only returns them to an active
          // member / the owner (expiry blocks new content), so the list is
          // empty otherwise. A public one carries a small "On the map" note.
          if (_communityTours.isNotEmpty) ...[
            _sectionTitle('Tours (${_communityTours.length})'),
            ..._communityTours.map((t) => ListTile(
                  leading: const Icon(Icons.headphones),
                  title: Text(t.name),
                  subtitle: Text(t.isPublic
                      ? 'On the map · members download free'
                      : 'Members only'),
                  trailing: t.isPublic
                      ? const Icon(Icons.public, size: 18, color: Colors.teal)
                      : null,
                )),
          ] else if (canListen) ...[
            _sectionTitle('Tours'),
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Text('No Audioura-made tours in this community yet.'),
            ),
          ],
        ],
      ),
    );
  }

  // ─── [LOCAL-702 / D663 §1] Hand-over + archived UI builders ─────────────────

  /// The member-facing hand-over state: the "Looking for a new organiser"
  /// banner with a Volunteer / Withdraw / Accept action, and the archived
  /// read-only banner. Empty list when the community is active.
  List<Widget> _handoverSection(Community c) {
    if (c.archived) {
      return [
        Card(
          color: Colors.blueGrey.shade50,
          child: const Padding(
            padding: EdgeInsets.all(12),
            child: Text(
              'This community is archived. No new organiser took over, so '
              'nothing new is added. Anything you have already downloaded stays '
              'with you.',
              style: TextStyle(fontWeight: FontWeight.w600),
            ),
          ),
        ),
      ];
    }
    if (!c.lookingForOrganiser) return const [];

    final mine = c.myOffer;
    final isMember = c.myStatus.isMember;
    return [
      Card(
        color: Colors.amber.shade50,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Looking for a new organiser',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
              const SizedBox(height: 4),
              const Text(
                'The organiser has stepped down. The community stays open for '
                'current members, but it is not taking new members until someone '
                'takes over. If no one does within 30 days, it will be archived.',
              ),
              // A member (not the owner) can volunteer / see their offer.
              if (isMember && !c.isOwner) ...[
                const SizedBox(height: 8),
                if (mine != null && mine.picked)
                  FilledButton.icon(
                    onPressed: _accept,
                    icon: const Icon(Icons.volunteer_activism),
                    label: const Text('You were picked — Accept & organise'),
                  )
                else if (mine != null && mine.status == 'offered')
                  Row(children: [
                    const Expanded(child: Text('You volunteered — waiting for '
                        'the organiser to pick.')),
                    TextButton(onPressed: _withdraw, child: const Text('Withdraw')),
                  ])
                else
                  OutlinedButton.icon(
                    onPressed: _volunteer,
                    icon: const Icon(Icons.pan_tool_alt_outlined),
                    label: const Text('Volunteer to organise'),
                  ),
              ],
            ],
          ),
        ),
      ),
    ];
  }

  /// [LOCAL-703 / D664] The organiser's live launch countdown. Shown to the
  /// OWNER only, while the community is active (an archived community shows the
  /// archived banner instead). Reads the server-computed launch block:
  /// "152 h left to get 2 paid members — 1 of 2 so far", turning into a green
  /// "Launched 🎉" once the bar is met.
  List<Widget> _launchCountdownSection(Community c) {
    if (!c.isOwner) return const [];
    if (c.status == 'archived') return const [];
    final l = c.launch;
    final text = CommunityCopy.launchCountdown(
      launched: l.launched,
      paid: c.isPaid,
      hoursLeft: l.hoursLeft,
      membersSoFar: l.membersSoFar,
      membersNeeded: l.membersNeeded,
    );
    final color = l.launched ? Colors.green.shade50 : Colors.blue.shade50;
    final fg = l.launched ? Colors.green.shade800 : Colors.blue.shade900;
    return [
      Padding(
        padding: const EdgeInsets.only(top: 12),
        child: Card(
          color: color,
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                Icon(l.launched ? Icons.celebration : Icons.timer_outlined,
                    color: fg),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    text,
                    key: const Key('launch_countdown_text'),
                    style: TextStyle(fontWeight: FontWeight.w600, color: fg),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    ];
  }

  /// The owner-facing controls: during hand-over, the volunteer list to pick
  /// from; while active, the "Step down" action; and "Delete" for a member-less
  /// community. Empty list when the caller is not the owner.
  List<Widget> _ownerControls(Community c) {
    if (!c.isOwner) return const [];
    final widgets = <Widget>[];

    if (c.lookingForOrganiser) {
      widgets.add(_sectionTitle('Volunteers'));
      if (c.organiserOffers.isEmpty) {
        widgets.add(const Padding(
          padding: EdgeInsets.symmetric(vertical: 8),
          child: Text('No one has volunteered yet. Share the community so a '
              'member can step up.'),
        ));
      } else {
        for (final o in c.organiserOffers) {
          widgets.add(Card(
            child: ListTile(
              leading: Icon(o.isPicked ? Icons.check_circle : Icons.person_outline,
                  color: o.isPicked ? Colors.teal : null),
              title: Text(o.memberUserId),
              subtitle: Text(o.isPicked
                  ? 'Picked — waiting for them to accept'
                  : 'Volunteered'),
              trailing: o.isPicked
                  ? null
                  : TextButton(
                      onPressed: () => _pick(o.memberUserId),
                      child: const Text('Pick'),
                    ),
            ),
          ));
        }
      }
    } else if (c.status == 'active') {
      // Active owner: step down, and (if member-less) delete.
      widgets.add(Padding(
        padding: const EdgeInsets.only(top: 16),
        child: OutlinedButton.icon(
          onPressed: _stepDown,
          icon: const Icon(Icons.exit_to_app),
          label: const Text('Step down as organiser'),
        ),
      ));
      // A community with no members at all can be deleted (D663 §1 d). The app
      // offers it; the server is the authority (409 has_members otherwise).
      if (!c.myStatus.isMember && c.episodeCount == 0) {
        widgets.add(Padding(
          padding: const EdgeInsets.only(top: 8),
          child: TextButton.icon(
            onPressed: _deleteCommunity,
            icon: const Icon(Icons.delete_outline, color: Colors.redAccent),
            label: const Text('Delete community',
                style: TextStyle(color: Colors.redAccent)),
          ),
        ));
      }
    }
    return widgets;
  }

  Widget _sectionTitle(String title) => Padding(
        padding: const EdgeInsets.only(top: 16, bottom: 4),
        child: Text(title,
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
      );

  Widget _section(String title, List<Widget> children) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _sectionTitle(title),
          ...children,
        ],
      );
}
