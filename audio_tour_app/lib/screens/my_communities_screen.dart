// [LOCAL-690] My Communities — the joined-communities list in the Listen tab
// (D658 addendum 2 §3). Each row carries its ORIGIN: the community name, and a
// ⋯ → Origin item showing the community + organiser ("Audioura" for the app's
// own tours, handled elsewhere; here every row is a community). An expired
// membership is shown as such but the downloaded audio stays on the device.

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/communities_service.dart';
import 'community_page_screen.dart';

class MyCommunitiesScreen extends StatefulWidget {
  const MyCommunitiesScreen({super.key});

  @override
  State<MyCommunitiesScreen> createState() => _MyCommunitiesScreenState();
}

class _MyCommunitiesScreenState extends State<MyCommunitiesScreen> {
  List<JoinedCommunity> _communities = [];
  bool _loading = true;
  String? _userId;
  // LOCAL-694: false when the Communities backend (Service.userDb) is not on
  // the current server (Storied). Drives an explanatory empty state.
  bool _featureAvailable = true;
  // [LOCAL-700 §2] Join from here with an invite code (same resolver as Home).
  final TextEditingController _codeController = TextEditingController();
  bool _joining = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _codeController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    final userId = prefs.getString('user_id');
    if (userId == null) {
      setState(() => _loading = false);
      return;
    }
    _userId = userId;
    // Probe once: if Communities is not offered here, show the Preview note
    // rather than a misleading "you haven't joined any" message.
    final available = await CommunitiesService.isAvailable();
    final list = available
        ? await CommunitiesService.mine(userId)
        : const <JoinedCommunity>[];
    if (!mounted) return;
    setState(() {
      _featureAvailable = available;
      _communities = list;
      _loading = false;
    });
  }

  Future<void> _join() async {
    final code = _codeController.text.trim();
    if (code.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Enter an invite code first.')));
      return;
    }
    setState(() => _joining = true);
    final prefs = await SharedPreferences.getInstance();
    final userId = prefs.getString('user_id');
    // [LOCAL-700 §2] Same resolver as Home search.
    final community =
        await CommunitiesService.resolveByCode(code, userId: userId);
    if (!mounted) return;
    setState(() => _joining = false);
    if (community == null) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No community with that code.')));
      return;
    }
    _codeController.clear();
    // Member or non-member: open the community page (join framing / content).
    await Navigator.push(
      context,
      MaterialPageRoute(
          builder: (_) => CommunityPageScreen(communityId: community.id)),
    );
    if (mounted) _load(); // refresh the list after a possible join
  }

  Widget _buildJoinBar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: _codeController,
              decoration: const InputDecoration(
                labelText: 'Have an invite code?',
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
    );
  }

  void _showOrigin(JoinedCommunity c) {
    // The ⋯ → Origin content (D658 addendum 2 §3): the community name and the
    // organiser. "Audioura" would be the label for the app's own tours.
    final label = CommunityRules.originLabel(
        communityName: c.name, organiserName: c.organiserName);
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Origin'),
        content: Text(label),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }

  /// [LOCAL-726 item 10] Block the organiser of a joined community from the
  /// Listen-tab ⋯ menu. JoinedCommunity does not carry the owner id, so fetch
  /// the full page (which does) and block that id. The organiser's communities
  /// and tours then disappear from this member's views; undo in Settings.
  Future<void> _blockOrganiser(JoinedCommunity c) async {
    if (_userId == null) return;
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Block this organiser?'),
        content: Text(
          "You won't see ${c.name} or this organiser's other communities and "
          'tours anymore. You can undo this later in Settings → Blocked.',
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Block')),
        ],
      ),
    );
    if (confirm != true) return;
    final full = await CommunitiesService.get(c.id, userId: _userId);
    final ownerId = full?.ownerUserId;
    var ok = false;
    if (ownerId != null) {
      ok = await CommunitiesService.blockUser(c.id, _userId!, ownerId);
    }
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(ok ? 'Organiser blocked.' : 'Could not block.')));
    if (ok) _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('My communities'),
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
              : Column(
                  children: [
                    // [LOCAL-700 §2] Join from here with an invite code.
                    _buildJoinBar(),
                    Expanded(
                      child: _communities.isEmpty
                          ? const Center(
                              child: Padding(
                                padding: EdgeInsets.all(24),
                                child: Text(
                                  'You have not joined any communities yet.\n'
                                  'Enter an invite code above, or paste it into '
                                  'Search on the Home page.',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(color: Colors.grey),
                                ),
                              ),
                            )
                          : ListView.builder(
                              itemCount: _communities.length,
                              itemBuilder: (context, i) {
                                final c = _communities[i];
                                return Card(
                                  margin: const EdgeInsets.all(8),
                                  child: ListTile(
                                    leading: const Icon(Icons.groups,
                                        color: Colors.deepPurple),
                                    title: Text(c.name),
                                    subtitle: Text(
                                        '${c.active ? 'Active member' : 'Expired — renew to listen to new content'}'
                                        ' · ${CommunityCopy.memberCountLabel(c.memberCount)}'),
                                    trailing: PopupMenuButton<String>(
                                      onSelected: (v) {
                                        if (v == 'origin') _showOrigin(c);
                                        if (v == 'block') _blockOrganiser(c);
                                        if (v == 'open') {
                                          Navigator.push(
                                            context,
                                            MaterialPageRoute(
                                                builder: (_) =>
                                                    CommunityPageScreen(
                                                        communityId: c.id)),
                                          );
                                        }
                                      },
                                      itemBuilder: (_) => const [
                                        PopupMenuItem(
                                            value: 'origin',
                                            child: Text('Origin')),
                                        PopupMenuItem(
                                            value: 'open',
                                            child: Text('Open community')),
                                        PopupMenuItem(
                                            value: 'block',
                                            child: Text('Block organiser')),
                                      ],
                                    ),
                                    onTap: () {
                                      Navigator.push(
                                        context,
                                        MaterialPageRoute(
                                            builder: (_) => CommunityPageScreen(
                                                communityId: c.id)),
                                      );
                                    },
                                  ),
                                );
                              },
                            ),
                    ),
                  ],
                ),
    );
  }
}
