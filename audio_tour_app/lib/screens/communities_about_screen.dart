// [LOCAL-690] "About Communities" + create form (D657 / D658 + addenda).
//
// Explains the Communities model and lets an organiser CREATE a community
// (the Generate tab's "Community" option routes here too). On create the server
// returns a ready invite message the organiser copies (D658 addendum §:
// "organisers … get a ready invite message").
//
// A waiver community is always Private (the form forces it, matching the
// server). A Listed community needs a location. A paid community needs at least
// one pass selected.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import '../services/communities_service.dart';
import '../services/iap_service.dart';
import '../services/device_service.dart';
import '../services/document_acceptance_service.dart';
import 'community_page_screen.dart';

class CommunitiesAboutScreen extends StatelessWidget {
  const CommunitiesAboutScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Communities')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('What is a community?',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          const Text(
            'A community is a group an organiser runs inside Audioura. The '
            'organiser publishes their OWN audio (links or an RSS feed they '
            'host) to members. Audioura plays it; it never stores the files.\n\n'
            'Communities can be free (like a book club) or paid. A paid '
            'membership is a pass you buy — a day, a week, a month, or a year. '
            'Nothing renews automatically: when a pass ends we remind you, and '
            'you can buy again. Audio you have already downloaded stays with you.',
            style: TextStyle(fontSize: 14),
          ),
          const SizedBox(height: 20),
          const Text('Join a community',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          const Text(
            'Paste an invite code into the Search box on the Home page. If you '
            'are a member the tour opens; if not, you will see the community '
            'page where you can join.',
            style: TextStyle(fontSize: 14),
          ),
          const SizedBox(height: 24),
          ElevatedButton.icon(
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const CreateCommunityScreen()),
              );
            },
            icon: const Icon(Icons.add),
            label: const Text('Create a community'),
            style: ElevatedButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 14),
            ),
          ),
        ],
      ),
    );
  }
}

class CreateCommunityScreen extends StatefulWidget {
  const CreateCommunityScreen({super.key});

  @override
  State<CreateCommunityScreen> createState() => _CreateCommunityScreenState();
}

class _CreateCommunityScreenState extends State<CreateCommunityScreen> {
  final _name = TextEditingController();
  final _description = TextEditingController();
  final _organiserName = TextEditingController();
  final _organiserBio = TextEditingController();
  final _organiserContact = TextEditingController();
  final _rules = TextEditingController();
  final _waiver = TextEditingController();
  final _lat = TextEditingController();
  final _lng = TextEditingController();
  final _feedUrl = TextEditingController();

  bool _isPaid = false;
  bool _listed = false;
  bool _submitting = false;
  // [LOCAL-691] Required Organiser Terms acceptance before creating.
  bool _organiserTermsAccepted = false;

  // [LOCAL-690C] The pass catalogue is ONE product per PRICE (the 34 ladder
  // prices, kPassLadderDollars); the LENGTH is chosen per community. The owner
  // picks one or more PRICES (quick-pick chips off the ladder + a Custom field
  // that snaps to the nearest ladder dollar) and one or more LENGTHS; the
  // offered options are every selected price × selected length.
  //
  // Quick-pick prices: the same handful the tour control leads with, all real
  // ladder steps. Custom snaps to the nearest of kPassLadderDollars.
  static const List<int> _quickPickDollars = [2, 3, 5, 10, 20, 50];
  final Set<int> _selectedDollars = <int>{};
  final _customPrice = TextEditingController();
  // The four pass lengths (day|week|month|year), default a single 'month'.
  final Map<String, bool> _lengthSelection = {
    'day': false,
    'week': false,
    'month': true,
    'year': false,
  };

  /// Snap a typed whole-dollar [amount] to the NEAREST ladder price
  /// (kPassLadderDollars), mirroring TourPricingService.snapToLadder: ties round
  /// DOWN, below the floor → the lowest step, above the ceiling → the highest.
  static int snapDollarsToLadder(double amount) {
    const ladder = kPassLadderDollars;
    if (amount <= ladder.first) return ladder.first;
    if (amount >= ladder.last) return ladder.last;
    int best = ladder.first;
    double bestDist = (amount - best).abs();
    for (final d in ladder.skip(1)) {
      final dist = (amount - d).abs();
      if (dist < bestDist) {
        best = d;
        bestDist = dist;
      }
    }
    return best;
  }

  /// The offered options as [{product_id, length}] — every selected price ×
  /// every selected length. Empty when nothing is selected.
  List<Map<String, String>> _passOptions() {
    final lengths =
        _lengthSelection.entries.where((e) => e.value).map((e) => e.key);
    final options = <Map<String, String>>[];
    for (final d in _selectedDollars) {
      for (final len in lengths) {
        options.add({'product_id': passProductForDollars(d), 'length': len});
      }
    }
    return options;
  }

  bool get _hasWaiver => _waiver.text.trim().isNotEmpty;

  @override
  Widget build(BuildContext context) {
    // A waiver community is always Private — reflect it in the UI.
    final effectiveListed = _hasWaiver ? false : _listed;

    return Scaffold(
      appBar: AppBar(title: const Text('Create a community')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _field(_name, 'Community name *'),
          _field(_description, 'Description', maxLines: 3),
          const Divider(),
          const Text('Organiser', style: TextStyle(fontWeight: FontWeight.bold)),
          _field(_organiserName, 'Organiser name'),
          _field(_organiserBio, 'Bio', maxLines: 2),
          _field(_organiserContact, 'Contact (email / link)'),
          const Divider(),
          _field(_rules, 'Rules', maxLines: 3),
          _field(_waiver, 'Waiver (optional)', maxLines: 3,
              onChanged: (_) => setState(() {})),
          if (_hasWaiver)
            const Padding(
              padding: EdgeInsets.only(bottom: 8),
              child: Text(
                'A community with a waiver is always Private (not shown on the map).',
                style: TextStyle(color: Colors.deepOrange, fontSize: 12),
              ),
            ),
          const Divider(),
          SwitchListTile(
            title: const Text('Paid community'),
            subtitle: const Text('Members buy a pass to join'),
            value: _isPaid,
            onChanged: (v) => setState(() => _isPaid = v),
          ),
          if (_isPaid) ...[
            const Padding(
              padding: EdgeInsets.only(left: 16, top: 4),
              child: Text('Pass price',
                  style: TextStyle(fontWeight: FontWeight.bold)),
            ),
            const Padding(
              padding: EdgeInsets.only(left: 16, bottom: 4),
              child: Text('Pick one or more prices. The length is set below.',
                  style: TextStyle(fontSize: 12, color: Colors.grey)),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Wrap(
                spacing: 8,
                children: _quickPickDollars
                    .map((d) => FilterChip(
                          label: Text('\$$d'),
                          selected: _selectedDollars.contains(d),
                          onSelected: (v) => setState(() {
                            if (v) {
                              _selectedDollars.add(d);
                            } else {
                              _selectedDollars.remove(d);
                            }
                          }),
                        ))
                    .toList(),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _customPrice,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(
                        labelText: 'Custom price (\$)',
                        helperText: 'Snaps to the nearest step',
                        border: OutlineInputBorder(),
                        isDense: true,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  OutlinedButton(
                    onPressed: () {
                      final typed = double.tryParse(_customPrice.text.trim());
                      if (typed == null) {
                        _snack('Enter a dollar amount to snap.');
                        return;
                      }
                      final snapped = snapDollarsToLadder(typed);
                      setState(() {
                        _selectedDollars.add(snapped);
                        _customPrice.clear();
                      });
                      _snack('Added \$$snapped pass price.');
                    },
                    child: const Text('Add'),
                  ),
                ],
              ),
            ),
            if (_selectedDollars.isNotEmpty)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                child: Text(
                  'Prices: ${(_selectedDollars.toList()..sort()).map((d) => '\$$d').join(', ')}',
                  style: const TextStyle(fontSize: 12, color: Colors.grey),
                ),
              ),
            const Padding(
              padding: EdgeInsets.only(left: 16, top: 12),
              child: Text('Pass length',
                  style: TextStyle(fontWeight: FontWeight.bold)),
            ),
            ..._lengthSelection.keys.map((len) => CheckboxListTile(
                  dense: true,
                  title: Text('Per $len'),
                  value: _lengthSelection[len],
                  onChanged: (v) =>
                      setState(() => _lengthSelection[len] = v ?? false),
                )),
          ],
          SwitchListTile(
            title: const Text('Listed on the Home map'),
            subtitle: Text(_hasWaiver
                ? 'Disabled — a waiver community is always Private'
                : 'Shown with a community badge (needs a location)'),
            value: effectiveListed,
            onChanged: _hasWaiver ? null : (v) => setState(() => _listed = v),
          ),
          if (effectiveListed) ...[
            _field(_lat, 'Latitude *'),
            _field(_lng, 'Longitude *'),
          ],
          const Divider(),
          _field(_feedUrl, 'RSS feed URL (optional)'),
          const SizedBox(height: 16),
          // [LOCAL-691] Required Organiser Terms acceptance.
          CheckboxListTile(
            contentPadding: EdgeInsets.zero,
            dense: true,
            value: _organiserTermsAccepted,
            onChanged: (v) =>
                setState(() => _organiserTermsAccepted = v ?? false),
            title: Wrap(
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                const Text('I accept the ', style: TextStyle(fontSize: 13)),
                InkWell(
                  onTap: () async {
                    final uri = Uri.parse(legalDocUrl(LegalDoc.organiserTerms));
                    if (await canLaunchUrl(uri)) {
                      await launchUrl(uri,
                          mode: LaunchMode.externalApplication);
                    }
                  },
                  child: const Text('Organiser Terms',
                      style: TextStyle(
                        fontSize: 13,
                        color: Color(0xFF3A3AC0),
                        decoration: TextDecoration.underline,
                      )),
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          ElevatedButton(
            onPressed: (_submitting || !_organiserTermsAccepted) ? null : _submit,
            child: _submitting
                ? const SizedBox(
                    height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Create community'),
          ),
        ],
      ),
    );
  }

  Future<void> _submit() async {
    final name = _name.text.trim();
    if (name.isEmpty) {
      _snack('Please enter a community name.');
      return;
    }
    final listed = _hasWaiver ? false : _listed;
    if (listed && (_lat.text.trim().isEmpty || _lng.text.trim().isEmpty)) {
      _snack('A listed community needs a latitude and longitude.');
      return;
    }
    final passes = _passOptions();
    if (_isPaid && passes.isEmpty) {
      _snack('A paid community needs at least one price and one length.');
      return;
    }

    setState(() => _submitting = true);
    final prefs = await SharedPreferences.getInstance();
    final userId = prefs.getString('user_id') ?? await DeviceService.getUserId();
    // [LOCAL-691] Record the Organiser Terms acceptance (required to create).
    await DocumentAcceptanceService.record(userId, LegalDoc.organiserTerms);
    final body = <String, dynamic>{
      'owner_user_id': userId,
      'name': name,
      if (_description.text.trim().isNotEmpty) 'description': _description.text.trim(),
      if (_organiserName.text.trim().isNotEmpty) 'organiser_name': _organiserName.text.trim(),
      if (_organiserBio.text.trim().isNotEmpty) 'organiser_bio': _organiserBio.text.trim(),
      if (_organiserContact.text.trim().isNotEmpty) 'organiser_contact': _organiserContact.text.trim(),
      if (_rules.text.trim().isNotEmpty) 'rules_text': _rules.text.trim(),
      if (_waiver.text.trim().isNotEmpty) 'waiver_text': _waiver.text.trim(),
      'is_paid': _isPaid,
      'visibility': listed ? 'listed' : 'private',
      if (listed) 'latitude': double.tryParse(_lat.text.trim()),
      if (listed) 'longitude': double.tryParse(_lng.text.trim()),
      if (_feedUrl.text.trim().isNotEmpty) 'feed_url': _feedUrl.text.trim(),
      'pass_products': passes,
    };

    final community = await CommunitiesService.create(body);
    if (!mounted) return;
    setState(() => _submitting = false);
    if (community == null) {
      _snack('Could not create the community. Please check your details.');
      return;
    }
    _showInvite(community);
  }

  void _showInvite(Community c) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Community created'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Share this invite with your members:'),
            const SizedBox(height: 8),
            SelectableText(c.inviteMessage ?? 'Code: ${c.joinCode}'),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () {
              if (c.inviteMessage != null) {
                Clipboard.setData(ClipboardData(text: c.inviteMessage!));
              }
            },
            child: const Text('Copy'),
          ),
          TextButton(
            onPressed: () {
              Navigator.pop(ctx);
              Navigator.pushReplacement(
                context,
                MaterialPageRoute(
                    builder: (_) => CommunityPageScreen(communityId: c.id)),
              );
            },
            child: const Text('Open'),
          ),
        ],
      ),
    );
  }

  void _snack(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  Widget _field(TextEditingController c, String label,
      {int maxLines = 1, void Function(String)? onChanged}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: TextField(
        controller: c,
        maxLines: maxLines,
        onChanged: onChanged,
        decoration: InputDecoration(
          labelText: label,
          border: const OutlineInputBorder(),
        ),
      ),
    );
  }
}
