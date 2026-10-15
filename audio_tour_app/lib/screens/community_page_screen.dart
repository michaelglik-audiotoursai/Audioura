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
    setState(() {
      _community = c;
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

          // Membership options / join.
          if (!canListen) ...[
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
        ],
      ),
    );
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
