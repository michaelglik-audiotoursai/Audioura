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
  // LOCAL-694: false when the Communities backend (Service.userDb) is not on
  // the current server (Storied). Drives an explanatory empty state.
  bool _featureAvailable = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    final userId = prefs.getString('user_id');
    if (userId == null) {
      setState(() => _loading = false);
      return;
    }
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
              : _communities.isEmpty
              ? const Center(
                  child: Text(
                    'You have not joined any communities yet.\n'
                    'Paste an invite code into Search on the Home page.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.grey),
                  ),
                )
              : ListView.builder(
                  itemCount: _communities.length,
                  itemBuilder: (context, i) {
                    final c = _communities[i];
                    return Card(
                      margin: const EdgeInsets.all(8),
                      child: ListTile(
                        leading: const Icon(Icons.groups, color: Colors.deepPurple),
                        title: Text(c.name),
                        subtitle: Text(c.active
                            ? 'Active member'
                            : 'Expired — renew to listen to new content'),
                        trailing: PopupMenuButton<String>(
                          onSelected: (v) {
                            if (v == 'origin') _showOrigin(c);
                            if (v == 'open') {
                              Navigator.push(
                                context,
                                MaterialPageRoute(
                                    builder: (_) =>
                                        CommunityPageScreen(communityId: c.id)),
                              );
                            }
                          },
                          itemBuilder: (_) => const [
                            PopupMenuItem(value: 'origin', child: Text('Origin')),
                            PopupMenuItem(value: 'open', child: Text('Open community')),
                          ],
                        ),
                        onTap: () {
                          Navigator.push(
                            context,
                            MaterialPageRoute(
                                builder: (_) =>
                                    CommunityPageScreen(communityId: c.id)),
                          );
                        },
                      ),
                    );
                  },
                ),
    );
  }
}
