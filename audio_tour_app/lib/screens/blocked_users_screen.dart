// [LOCAL-726 item 10 — Apple Guideline 1.2] Settings → Blocked.
//
// Everything this device has blocked within communities: a member's blocks of
// organisers/members (kind member_block) and, for an organiser, the members
// they have barred (kind organiser_bar). Each row has an Unblock action that
// lifts the one block server-side. Lifting an organiser_bar does NOT auto-
// rejoin the member — it just allows them to buy a pass again.
//
// This is the required "ability to block abusive users" surface's undo half:
// Apple wants the block reversible and discoverable, so it lives in Settings.

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/communities_service.dart';

class BlockedUsersScreen extends StatefulWidget {
  const BlockedUsersScreen({super.key});

  @override
  State<BlockedUsersScreen> createState() => _BlockedUsersScreenState();
}

class _BlockedUsersScreenState extends State<BlockedUsersScreen> {
  List<CommunityBlock> _blocks = const [];
  bool _loading = true;
  String? _userId;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    final userId = prefs.getString('user_id');
    _userId = userId;
    final blocks = userId == null
        ? const <CommunityBlock>[]
        : await CommunitiesService.myBlocks(userId);
    if (!mounted) return;
    setState(() {
      _blocks = blocks;
      _loading = false;
    });
  }

  Future<void> _unblock(CommunityBlock b) async {
    if (_userId == null) return;
    final ok = await CommunitiesService.unblockUser(
        b.communityId, _userId!, b.blockedUserId,
        kind: b.kind);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(ok ? 'Unblocked.' : 'Could not unblock.')));
    if (ok) _load();
  }

  String _label(CommunityBlock b) {
    final where = (b.communityName != null && b.communityName!.isNotEmpty)
        ? b.communityName!
        : 'a community';
    return b.isOrganiserBar
        ? 'Barred from $where'
        : 'Blocked in $where';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Blocked'),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _blocks.isEmpty
              ? const Center(
                  child: Padding(
                    padding: EdgeInsets.all(32),
                    child: Text(
                      "You haven't blocked anyone.\n\nWhen you block an "
                      'organiser or a member, they appear here and you can '
                      'unblock them at any time.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.grey),
                    ),
                  ),
                )
              : ListView.builder(
                  itemCount: _blocks.length,
                  itemBuilder: (context, i) {
                    final b = _blocks[i];
                    return Card(
                      margin: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 4),
                      child: ListTile(
                        leading: const Icon(Icons.block, color: Colors.redAccent),
                        title: Text(b.blockedUserId,
                            overflow: TextOverflow.ellipsis),
                        subtitle: Text(_label(b)),
                        trailing: TextButton(
                          onPressed: () => _unblock(b),
                          child: const Text('Unblock'),
                        ),
                      ),
                    );
                  },
                ),
    );
  }
}
