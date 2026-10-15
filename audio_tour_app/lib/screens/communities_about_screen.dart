// [LOCAL-690 / LOCAL-700] "About Communities" + create form (D657 / D658 +
// addenda, Michael's Pixel-4 review 2026-10-15).
//
// LOCAL-700 round 1:
//   §1 Describes BOTH kinds of community content (owner's own audio AND tours
//      made with Audioura), plus the "cannot be closed once members join"
//      warning (CommunityCopy).
//   §2 A "Have an invite code?" field + Join button on this screen (and the My
//      communities list), using the SAME resolver as Home search
//      (CommunitiesService.resolveByCode).
//   §3 Creating a community requires the free plan or above — Introduction
//      users see an explanation and a button to Your plan. The server enforces
//      it too (403 plan_required).
//   §4 The create form: required fields marked with a red *, the Create button
//      enabled only when all required fields are filled AND the Organiser Terms
//      are accepted; friendly randomised prefill with a unique generated name
//      (live name-available check); the RSS field is removed; after creation
//      (and always on the organiser's page) the invite code with Copy, Share,
//      Email and Regenerate; the close warning above the button.

import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import '../services/communities_service.dart';
import '../services/entitlements_service.dart';
import '../services/iap_service.dart';
import '../services/device_service.dart';
import '../services/document_acceptance_service.dart';
import 'community_page_screen.dart';
import 'plan_screen.dart';

class CommunitiesAboutScreen extends StatefulWidget {
  const CommunitiesAboutScreen({super.key});

  @override
  State<CommunitiesAboutScreen> createState() => _CommunitiesAboutScreenState();
}

class _CommunitiesAboutScreenState extends State<CommunitiesAboutScreen> {
  final _codeController = TextEditingController();
  bool _joining = false;

  @override
  void dispose() {
    _codeController.dispose();
    super.dispose();
  }

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
          // §1: both kinds of content, plainly.
          const Text(CommunityCopy.aboutContent,
              style: TextStyle(fontSize: 14)),
          const SizedBox(height: 16),
          // §1: the close warning.
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.orange.shade50,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: Colors.orange.shade200),
            ),
            child: const Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(Icons.info_outline, size: 20, color: Colors.deepOrange),
                SizedBox(width: 8),
                Expanded(
                  child: Text(CommunityCopy.closeWarning,
                      style: TextStyle(fontSize: 13)),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),

          // §2: Have an invite code? — join from here, same resolver as Home.
          const Text('Have an invite code?',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          const Text(
            'Enter the code an organiser gave you to open their community. '
            '(You can also paste it into Search on the Home page.)',
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

  Future<void> _join() async {
    final code = _codeController.text.trim();
    if (code.isEmpty) {
      _snack('Enter an invite code first.');
      return;
    }
    setState(() => _joining = true);
    final prefs = await SharedPreferences.getInstance();
    final userId = prefs.getString('user_id');
    // Same resolver as Home search (CommunitiesService.resolveByCode).
    final community =
        await CommunitiesService.resolveByCode(code, userId: userId);
    if (!mounted) return;
    setState(() => _joining = false);
    if (community == null) {
      // §2: unknown code wording.
      _snack(CommunityCopy.noCommunityForCode);
      return;
    }
    // Member already OR non-member: either way, open the community page (it
    // shows "join to listen" framing for a non-member, or the content for a
    // member).
    Navigator.push(
      context,
      MaterialPageRoute(
          builder: (_) => CommunityPageScreen(communityId: community.id)),
    );
  }

  void _snack(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));
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

  bool _isPaid = false;
  bool _listed = false;
  bool _submitting = false;
  // [LOCAL-691] Required Organiser Terms acceptance before creating.
  bool _organiserTermsAccepted = false;

  // [LOCAL-700 §3] The create gate. null = still loading the plan; true =
  // allowed (free plan or above); false = Introduction (show the explanation +
  // "Your plan" button instead of the form).
  bool? _canCreate;

  // [LOCAL-700 §4] Live name-available check (debounced). null = unknown / not
  // yet checked; true = ✓ free; false = taken.
  Timer? _nameDebounce;
  bool? _nameAvailable;
  bool _nameChecking = false;

  // [LOCAL-690C] The pass catalogue is ONE product per PRICE (the 34 ladder
  // prices, kPassLadderDollars); the LENGTH is chosen per community.
  static const List<int> _quickPickDollars = [2, 3, 5, 10, 20, 50];
  final Set<int> _selectedDollars = <int>{};
  final _customPrice = TextEditingController();
  final Map<String, bool> _lengthSelection = {
    'day': false,
    'week': false,
    'month': true,
    'year': false,
  };

  @override
  void initState() {
    super.initState();
    _checkPlan();
    _prefill();
    _name.addListener(_onNameChanged);
  }

  @override
  void dispose() {
    _nameDebounce?.cancel();
    _name.removeListener(_onNameChanged);
    for (final c in [
      _name, _description, _organiserName, _organiserBio, _organiserContact,
      _rules, _waiver, _lat, _lng, _customPrice,
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  /// [LOCAL-700 §3] Read the device plan; the free plan (l2) or above may
  /// create, Introduction (l1) may not.
  Future<void> _checkPlan() async {
    final ent = await EntitlementsService.me();
    if (!mounted) return;
    setState(() => _canCreate = ent.level != 'l1');
  }

  /// [LOCAL-700 §4] Fill every field with friendly, lightly-humorous sample
  /// text (random from a pool of ≥ 8) and a UNIQUE generated name (checked
  /// against the server; a short suffix is added if the plain name is taken).
  Future<void> _prefill() async {
    final rng = Random();
    String pick(List<String> pool) => pool[rng.nextInt(pool.length)];

    _description.text = pick(CommunityCopy.descriptions);
    _organiserName.text = pick(CommunityCopy.organiserNames);
    _organiserBio.text = pick(CommunityCopy.bios);
    _organiserContact.text = pick(CommunityCopy.contacts);
    _rules.text = pick(CommunityCopy.rules);

    final stem = pick(CommunityCopy.namePrefixes);
    final place = await _guessPlace();
    final unique = await _firstFreeName(stem, place);
    if (!mounted) return;
    setState(() {
      _name.text = unique;
      _nameAvailable = true; // _firstFreeName returns a name confirmed free
    });
  }

  /// A friendly place to put in the generated name. Best-effort: the saved
  /// city if we have one, else a whimsical default so the name still reads.
  Future<String> _guessPlace() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final city = prefs.getString('last_city') ?? prefs.getString('city');
      if (city != null && city.trim().isNotEmpty) return city.trim();
    } catch (_) {}
    return 'Everywhere';
  }

  /// Try the plain generated name, then suffixed variants, returning the first
  /// one the server reports free. Falls back to a suffixed name if the check is
  /// unavailable (so we never block prefill on the network).
  Future<String> _firstFreeName(String stem, String place) async {
    for (var attempt = 0; attempt <= 5; attempt++) {
      final candidate = CommunityCopy.uniqueName(stem, place, attempt: attempt);
      final free = await CommunitiesService.nameAvailable(candidate);
      if (free == true) return candidate;
      if (free == null) {
        // Can't check — use a lightly-suffixed name to avoid a likely clash.
        return CommunityCopy.uniqueName(stem, place, attempt: 1);
      }
    }
    // Everything up to 5 was taken (very unlikely) — a random higher suffix.
    return CommunityCopy.uniqueName(stem, place,
        attempt: 6 + Random().nextInt(90));
  }

  void _onNameChanged() {
    _nameDebounce?.cancel();
    final name = _name.text.trim();
    setState(() {
      _nameAvailable = null;
      _nameChecking = name.isNotEmpty;
    });
    if (name.isEmpty) {
      setState(() => _nameChecking = false);
      return;
    }
    _nameDebounce = Timer(const Duration(milliseconds: 450), () async {
      final free = await CommunitiesService.nameAvailable(name);
      if (!mounted || _name.text.trim() != name) return;
      setState(() {
        _nameAvailable = free;
        _nameChecking = false;
      });
    });
  }

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

  /// [LOCAL-700 §4] All REQUIRED fields present. Required: name, description,
  /// organiser name, rules. Location is required ONLY for a Listed community.
  bool get _requiredFilled {
    final listed = _hasWaiver ? false : _listed;
    final core = _name.text.trim().isNotEmpty &&
        _description.text.trim().isNotEmpty &&
        _organiserName.text.trim().isNotEmpty &&
        _rules.text.trim().isNotEmpty;
    if (!core) return false;
    if (listed && (_lat.text.trim().isEmpty || _lng.text.trim().isEmpty)) {
      return false;
    }
    return true;
  }

  /// [LOCAL-700 §4] The Create button is enabled only when all required fields
  /// are filled AND the Organiser Terms are accepted (and we are not mid-submit,
  /// and the name is not known-taken).
  bool get _canSubmit =>
      !_submitting &&
      _requiredFilled &&
      _organiserTermsAccepted &&
      _nameAvailable != false;

  @override
  Widget build(BuildContext context) {
    // Still loading the plan.
    if (_canCreate == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Create a community')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    // §3: Introduction users cannot create — explain + offer Your plan.
    if (_canCreate == false) {
      return _buildPlanGate();
    }
    return _buildForm();
  }

  Widget _buildPlanGate() {
    return Scaffold(
      appBar: AppBar(title: const Text('Create a community')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Icon(Icons.workspace_premium, size: 48, color: Colors.indigo),
          const SizedBox(height: 12),
          const Text('Creating a community needs a plan',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 12),
          const Text(
            'Creating a community is available on the free plan or above — not '
            'the Introduction level you are on now. Join the free queue (or buy '
            'a plan) and you can set up your community. Joining and listening to '
            'other communities does not need a plan.',
            style: TextStyle(fontSize: 14),
          ),
          const SizedBox(height: 20),
          ElevatedButton.icon(
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const PlanScreen()),
              );
            },
            icon: const Icon(Icons.workspace_premium_outlined),
            label: const Text('Your plan'),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.indigo,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 14),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildForm() {
    final effectiveListed = _hasWaiver ? false : _listed;

    return Scaffold(
      appBar: AppBar(title: const Text('Create a community')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // §1: the create intro (both content kinds).
          const Text(CommunityCopy.createIntro,
              style: TextStyle(fontSize: 13, color: Colors.black87)),
          const Divider(height: 24),

          _field(_name, 'Community name', required: true,
              suffix: _nameStatusIcon()),
          if (_nameAvailable == false)
            const Padding(
              padding: EdgeInsets.only(left: 4, bottom: 6),
              child: Text('Taken — try another name.',
                  style: TextStyle(color: Colors.redAccent, fontSize: 12)),
            ),
          _field(_description, 'Description', required: true, maxLines: 3),
          const Divider(),
          const Text('Organiser', style: TextStyle(fontWeight: FontWeight.bold)),
          _field(_organiserName, 'Organiser name', required: true),
          _field(_organiserBio, 'Bio', maxLines: 2),
          _field(_organiserContact, 'Contact (email / link)'),
          const Divider(),
          _field(_rules, 'Rules', required: true, maxLines: 3),
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
          if (_isPaid) ..._buildPaidSection(),
          SwitchListTile(
            title: const Text('Listed on the Home map'),
            subtitle: Text(_hasWaiver
                ? 'Disabled — a waiver community is always Private'
                : 'Shown with a community badge (needs a location)'),
            value: effectiveListed,
            onChanged: _hasWaiver ? null : (v) => setState(() => _listed = v),
          ),
          if (effectiveListed) ...[
            _field(_lat, 'Latitude', required: true),
            _field(_lng, 'Longitude', required: true),
          ],
          const Divider(),
          // [LOCAL-700 §4] The RSS feed URL field is REMOVED from Create —
          // content is added per tour on the Generate tab.
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
                const Text('* ',
                    style: TextStyle(fontSize: 13, color: Colors.red)),
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
          const SizedBox(height: 12),
          // §1 / §4: the close warning, shown above the Create button.
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.orange.shade50,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: Colors.orange.shade200),
            ),
            child: const Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(Icons.info_outline, size: 20, color: Colors.deepOrange),
                SizedBox(width: 8),
                Expanded(
                  child: Text(CommunityCopy.closeWarning,
                      style: TextStyle(fontSize: 13)),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          ElevatedButton(
            onPressed: _canSubmit ? _submit : null,
            child: _submitting
                ? const SizedBox(
                    height: 18,
                    width: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Create community'),
          ),
          const SizedBox(height: 8),
          if (!_canSubmit && !_submitting)
            const Text(
              'Fill the required fields (marked *) and accept the Organiser '
              'Terms to create.',
              style: TextStyle(fontSize: 12, color: Colors.grey),
            ),
        ],
      ),
    );
  }

  Widget? _nameStatusIcon() {
    if (_nameChecking) {
      return const Padding(
        padding: EdgeInsets.all(12),
        child: SizedBox(
            height: 16, width: 16, child: CircularProgressIndicator(strokeWidth: 2)),
      );
    }
    if (_nameAvailable == true) {
      return const Icon(Icons.check_circle, color: Colors.green);
    }
    if (_nameAvailable == false) {
      return const Icon(Icons.cancel, color: Colors.redAccent);
    }
    return null;
  }

  List<Widget> _buildPaidSection() {
    return [
      const Padding(
        padding: EdgeInsets.only(left: 16, top: 4),
        child: Text('Pass price', style: TextStyle(fontWeight: FontWeight.bold)),
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
        child: Text('Pass length', style: TextStyle(fontWeight: FontWeight.bold)),
      ),
      ..._lengthSelection.keys.map((len) => CheckboxListTile(
            dense: true,
            title: Text('Per $len'),
            value: _lengthSelection[len],
            onChanged: (v) =>
                setState(() => _lengthSelection[len] = v ?? false),
          )),
    ];
  }

  Future<void> _submit() async {
    final name = _name.text.trim();
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
    await DocumentAcceptanceService.record(userId, LegalDoc.organiserTerms);
    final body = <String, dynamic>{
      'owner_user_id': userId,
      'name': name,
      'description': _description.text.trim(),
      'organiser_name': _organiserName.text.trim(),
      if (_organiserBio.text.trim().isNotEmpty) 'organiser_bio': _organiserBio.text.trim(),
      if (_organiserContact.text.trim().isNotEmpty) 'organiser_contact': _organiserContact.text.trim(),
      'rules_text': _rules.text.trim(),
      if (_waiver.text.trim().isNotEmpty) 'waiver_text': _waiver.text.trim(),
      'is_paid': _isPaid,
      'visibility': listed ? 'listed' : 'private',
      if (listed) 'latitude': double.tryParse(_lat.text.trim()),
      if (listed) 'longitude': double.tryParse(_lng.text.trim()),
      'pass_products': passes,
    };

    final community = await CommunitiesService.create(body);
    if (!mounted) return;
    setState(() => _submitting = false);
    if (community == null) {
      _snack('Could not create the community. The name may be taken, or you '
          'may need a plan.');
      return;
    }
    _showInvite(community);
  }

  void _showInvite(Community c) {
    final code = c.joinCode ?? '';
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
            SelectableText(c.inviteMessage ?? 'Code: $code',
                style: const TextStyle(fontWeight: FontWeight.w600)),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Close'),
          ),
          TextButton(
            onPressed: () {
              Navigator.pop(ctx);
              // The organiser's page always carries the invite tools
              // (Copy/Share/Email/Regenerate).
              Navigator.pushReplacement(
                context,
                MaterialPageRoute(
                    builder: (_) => CommunityPageScreen(communityId: c.id)),
              );
            },
            child: const Text('Open community'),
          ),
        ],
      ),
    );
  }

  void _snack(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  /// A labelled text field. [required] appends a red `*` to the label.
  Widget _field(TextEditingController c, String label,
      {int maxLines = 1,
      bool required = false,
      Widget? suffix,
      void Function(String)? onChanged}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: TextField(
        controller: c,
        maxLines: maxLines,
        onChanged: onChanged,
        decoration: InputDecoration(
          label: required
              ? Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(label),
                    const Text(' *', style: TextStyle(color: Colors.red)),
                  ],
                )
              : Text(label),
          suffixIcon: suffix,
          border: const OutlineInputBorder(),
        ),
      ),
    );
  }
}

/// [LOCAL-700 §4] The invite tools shown after creation AND always on the
/// organiser's community page: the code with Copy, Share, Email and Regenerate.
/// Factored out so the community page can embed it. Email opens the device mail
/// composer (share sheet) pre-filled with the name, description, organiser, how
/// to get Audioura, and the join instruction with the code (never claims the
/// email was sent). Regenerate rotates the code server-side (old code dies).
class CommunityInviteTools extends StatefulWidget {
  final Community community;

  const CommunityInviteTools({super.key, required this.community});

  @override
  State<CommunityInviteTools> createState() => _CommunityInviteToolsState();
}

class _CommunityInviteToolsState extends State<CommunityInviteTools> {
  late String _code = widget.community.joinCode ?? '';
  late String _inviteMessage = widget.community.inviteMessage ??
      'Open Audioura, tap Search on the Home page and paste this code: '
          '${widget.community.joinCode ?? ''}';
  bool _regenerating = false;

  @override
  Widget build(BuildContext context) {
    if (_code.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Invite code',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
        const SizedBox(height: 4),
        SelectableText(_code,
            style: const TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.bold,
                letterSpacing: 2)),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 4,
          children: [
            OutlinedButton.icon(
              onPressed: _copy,
              icon: const Icon(Icons.copy, size: 18),
              label: const Text('Copy'),
            ),
            OutlinedButton.icon(
              onPressed: _share,
              icon: const Icon(Icons.ios_share, size: 18),
              label: const Text('Share'),
            ),
            OutlinedButton.icon(
              onPressed: _email,
              icon: const Icon(Icons.email_outlined, size: 18),
              label: const Text('Email'),
            ),
            OutlinedButton.icon(
              onPressed: _regenerating ? null : _regenerate,
              icon: _regenerating
                  ? const SizedBox(
                      height: 16,
                      width: 16,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.autorenew, size: 18),
              label: const Text('Regenerate code'),
            ),
          ],
        ),
      ],
    );
  }

  void _copy() {
    Clipboard.setData(ClipboardData(text: _inviteMessage));
    ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Invite copied.')));
  }

  Future<void> _share() async {
    await Share.share(_inviteMessage,
        subject: CommunityCopy.emailInviteSubject(widget.community.name));
  }

  /// Open the device mail composer (share sheet / mailto) with a subject + body
  /// pre-filled. Prefer the share sheet (reliable across platforms); if a
  /// mailto is needed it carries the same subject + body. NEVER claims the mail
  /// was sent.
  Future<void> _email() async {
    final c = widget.community;
    final body = CommunityCopy.emailInviteBody(
      communityName: c.name,
      description: c.description,
      organiserName: c.organiser.name,
      code: _code,
    );
    final subject = CommunityCopy.emailInviteSubject(c.name);
    final mailto = Uri(
      scheme: 'mailto',
      query: _encodeQuery({'subject': subject, 'body': body}),
    );
    try {
      if (await canLaunchUrl(mailto)) {
        await launchUrl(mailto);
        return;
      }
    } catch (_) {}
    // Fall back to the share sheet (which includes email as a target).
    await Share.share(body, subject: subject);
  }

  String _encodeQuery(Map<String, String> params) => params.entries
      .map((e) =>
          '${Uri.encodeQueryComponent(e.key)}=${Uri.encodeQueryComponent(e.value)}')
      .join('&');

  Future<void> _regenerate() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Regenerate invite code?'),
        content: const Text(
            'The current code will stop working immediately. Anyone you have '
            'already given it to will need the new code. Existing members are '
            'not affected.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          ElevatedButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Regenerate')),
        ],
      ),
    );
    if (confirmed != true) return;
    setState(() => _regenerating = true);
    final prefs = await SharedPreferences.getInstance();
    final userId = prefs.getString('user_id') ?? await DeviceService.getUserId();
    final result =
        await CommunitiesService.regenerateCode(widget.community.id, userId);
    if (!mounted) return;
    setState(() => _regenerating = false);
    if (result == null || result['join_code'] is! String) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Could not regenerate the code. Please try again.')));
      return;
    }
    setState(() {
      _code = result['join_code'] as String;
      final msg = result['invite_message'];
      if (msg is String && msg.isNotEmpty) _inviteMessage = msg;
    });
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('New invite code generated. The old code no longer works.')));
  }
}
