// [LOCAL-739 / SUBSCRIBED C0] The ONE Communities page.
//
// Michael's ruling (review 2026-10-22): a listener had no visible way back to a
// community they joined — the list hid behind a small icon in the Listen app
// bar. There is now a single page, reached from where people look:
//   • the About tab button "Communities" (everyone), and
//   • for members/organisers only: a Home-map chip, a Generate link, and a
//     visible "My communities (N)" row at the top of Listen.
//
// The page has four parts (D658 / LOCAL-700/738 pieces, reused — NO second copy
// of any list):
//   (1) Your communities — the communities the user BELONGS TO or ORGANISES,
//       each with its status/expiry ("Member until 22 Nov" via the shared
//       JoinedCommunitySubtitle, or "You are the organizer"); tap → the
//       community page.
//   (2) Join with a code — the SAME resolver as the Home search
//       (CommunitiesService.resolveByCode).
//   (3) Start a community — opens the LOCAL-738 create form.
//   (4) About communities — the explanation (CommunityCopy), behind a link at
//       the bottom (the full About → Communities screen).

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/communities_service.dart';
import '../services/community_tour_service.dart';
import '../services/app_sync_coordinator.dart';
import '../widgets/pass_expiry_display.dart';
import 'communities_about_screen.dart';
import 'community_page_screen.dart';

/// [LOCAL-739 §2] The visible "My communities (N)" row placed at the top of the
/// Listen tours view. It is MEMBERS-ONLY: it renders the row only when [count]
/// is greater than zero (a user who belongs to or organises at least one
/// community); a non-member (count 0) gets an empty box and sees nothing. This
/// replaces the old hidden app-bar icon. Extracted as its own widget so the
/// "hidden for a non-member / shown for a member" behaviour is widget-tested
/// offline (the RED test), the same way JoinedCommunitySubtitle is tested.
class ListenMyCommunitiesRow extends StatelessWidget {
  /// The number of communities the user belongs to or organises. The row shows
  /// only when this is > 0.
  final int count;

  /// Called when the row is tapped (opens the Communities page).
  final VoidCallback onTap;

  const ListenMyCommunitiesRow({
    super.key,
    required this.count,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    if (count <= 0) return const SizedBox.shrink();
    return Material(
      color: Colors.deepPurple.shade50,
      child: ListTile(
        key: const Key('listen_my_communities_row'),
        leading: const Icon(Icons.groups, color: Colors.deepPurple),
        title: Text('My communities ($count)'),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }
}

class CommunitiesHubScreen extends StatefulWidget {
  const CommunitiesHubScreen({super.key});

  @override
  State<CommunitiesHubScreen> createState() => _CommunitiesHubScreenState();
}

class _CommunitiesHubScreenState extends State<CommunitiesHubScreen> {
  bool _loading = true;
  // [LOCAL-694] false when the Communities backend (Service.userDb) is not on
  // the current server (Storied). Drives the explanatory empty state.
  bool _featureAvailable = true;
  List<YourCommunity> _yours = const [];

  final _codeController = TextEditingController();
  bool _joining = false;

  @override
  void initState() {
    super.initState();
    // [LOCAL-750 C] Opening the Communities hub kicks off a community sync so
    // new/updated tours show up without waiting for the next app resume.
    AppSyncCoordinator.instance.syncNow();
    _load();
  }

  @override
  void dispose() {
    _codeController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final prefs = await SharedPreferences.getInstance();
    final userId = prefs.getString('user_id');
    if (userId == null || userId.isEmpty) {
      if (!mounted) return;
      setState(() {
        _yours = const [];
        _loading = false;
      });
      return;
    }
    // Probe once: if Communities is not offered here, show the Preview note
    // rather than a misleading "you have not joined any" message.
    final available = await CommunitiesService.isAvailable();
    // Member communities (/communities/mine) AND owned communities
    // (/communities/mine-owned), merged into the single "Your communities"
    // list. Both calls swallow transport errors and return an empty list.
    final joined = available
        ? await CommunitiesService.mine(userId)
        : const <JoinedCommunity>[];
    final owned = available
        ? await CommunityTourService.ownedCommunities(userId)
        : const <OwnedCommunity>[];
    if (!mounted) return;
    setState(() {
      _featureAvailable = available;
      _yours = YourCommunity.merge(
        joined: joined,
        owned: owned
            .map((o) => OwnedCommunityRef(id: o.id, name: o.name))
            .toList(growable: false),
      );
      _loading = false;
    });
  }

  Future<void> _join() async {
    final code = _codeController.text.trim();
    if (code.isEmpty) {
      _snack('Enter an invite code first.');
      return;
    }
    setState(() => _joining = true);
    final prefs = await SharedPreferences.getInstance();
    final userId = prefs.getString('user_id');
    // [LOCAL-700 §2] The SAME resolver as the Home search.
    final community =
        await CommunitiesService.resolveByCode(code, userId: userId);
    if (!mounted) return;
    setState(() => _joining = false);
    if (community == null) {
      _snack(CommunityCopy.noCommunityForCode);
      return;
    }
    _codeController.clear();
    // Member or non-member: either way open the community page (join framing /
    // content), then refresh the list after a possible join.
    await Navigator.push(
      context,
      MaterialPageRoute(
          builder: (_) => CommunityPageScreen(communityId: community.id)),
    );
    if (mounted) _load();
  }

  void _openCommunity(int id) async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => CommunityPageScreen(communityId: id)),
    );
    if (mounted) _load();
  }

  void _snack(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Communities'),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : !_featureAvailable
              ? const Center(
                  child: Padding(
                    padding: EdgeInsets.all(32),
                    child: Text(
                      'Communities is available in Preview only.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.grey),
                    ),
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(
                    padding: const EdgeInsets.only(bottom: 24),
                    children: [
                      _buildYourCommunities(),
                      const Divider(height: 1),
                      _buildJoinWithCode(),
                      const Divider(height: 1),
                      _buildStartCommunity(),
                      const Divider(height: 1),
                      _buildAboutLink(),
                    ],
                  ),
                ),
    );
  }

  // ── (1) Your communities ───────────────────────────────────────────────────
  Widget _buildYourCommunities() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.fromLTRB(16, 16, 16, 4),
          child: Text('Your communities',
              key: Key('hub_your_communities_header'),
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
        ),
        if (_yours.isEmpty)
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 4, 16, 12),
            child: Text(
              'You have not joined or started any communities yet.\n'
              'Enter an invite code below, or start your own.',
              key: Key('hub_your_communities_empty'),
              style: TextStyle(color: Colors.grey),
            ),
          )
        else
          ..._yours.map(_buildCommunityRow),
      ],
    );
  }

  Widget _buildCommunityRow(YourCommunity yc) {
    // An organiser row shows "You are the organizer" (D736). A member row shows
    // the shared JoinedCommunitySubtitle (status + readable expiry). When a user
    // both owns AND holds a membership, show the organiser line but keep the
    // expiry subtitle below it.
    final Widget subtitle;
    if (yc.isOrganiser && yc.joined == null) {
      subtitle = const Text('You are the organizer',
          key: Key('hub_organizer_subtitle'));
    } else if (yc.isOrganiser && yc.joined != null) {
      subtitle = Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('You are the organizer',
              key: Key('hub_organizer_subtitle')),
          JoinedCommunitySubtitle(community: yc.joined!),
        ],
      );
    } else {
      subtitle = JoinedCommunitySubtitle(community: yc.joined!);
    }
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      child: ListTile(
        key: Key('hub_community_${yc.id}'),
        leading: Icon(
          yc.isOrganiser ? Icons.campaign : Icons.groups,
          color: Colors.deepPurple,
        ),
        title: Text(yc.name),
        subtitle: subtitle,
        trailing: const Icon(Icons.chevron_right),
        onTap: () => _openCommunity(yc.id),
      ),
    );
  }

  // ── (2) Join with a code ────────────────────────────────────────────────────
  Widget _buildJoinWithCode() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Join with a code',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          const SizedBox(height: 6),
          const Text(
            'Enter the invite code an organiser gave you. (You can also paste '
            'it into Search on the Home page.)',
            style: TextStyle(fontSize: 13, color: Colors.grey),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _codeController,
                  decoration: const InputDecoration(
                    labelText: 'Invite code',
                    border: OutlineInputBorder(),
                    isDense: true,
                  ),
                  textInputAction: TextInputAction.go,
                  onSubmitted: (_) => _join(),
                ),
              ),
              const SizedBox(width: 8),
              ElevatedButton(
                onPressed: _joining ? null : _join,
                child: _joining
                    ? const SizedBox(
                        height: 18,
                        width: 18,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Join'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  // ── (3) Start a community ────────────────────────────────────────────────────
  Widget _buildStartCommunity() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Start a community',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          const SizedBox(height: 6),
          const Text(
            'Run your own community: publish your audio and tours made with '
            'Audioura to your members.',
            style: TextStyle(fontSize: 13, color: Colors.grey),
          ),
          const SizedBox(height: 8),
          ElevatedButton.icon(
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                    builder: (_) => const CreateCommunityScreen()),
              );
            },
            icon: const Icon(Icons.add),
            label: const Text('Start a community'),
            style: ElevatedButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 14),
            ),
          ),
        ],
      ),
    );
  }

  // ── (4) About communities ────────────────────────────────────────────────────
  Widget _buildAboutLink() {
    return ListTile(
      key: const Key('hub_about_communities'),
      leading: const Icon(Icons.info_outline, color: Colors.deepPurple),
      title: const Text('About communities'),
      subtitle: const Text('How communities work, and the rules.'),
      trailing: const Icon(Icons.chevron_right),
      onTap: () {
        Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => const CommunitiesAboutScreen()),
        );
      },
    );
  }
}
