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
import 'package:geolocator/geolocator.dart';
import 'package:share_plus/share_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import '../services/communities_service.dart';
import '../utils/share_code.dart';
import '../services/tour_share_service.dart';
import '../services/entitlements_service.dart';
import '../services/device_service.dart';
import '../services/document_acceptance_service.dart';
import 'community_page_screen.dart';
import 'tour_generator_screen.dart';
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

  // [LOCAL-704 / D665] Every community is paid — there is no Free option. Kept
  // as a const so the launch-rule copy ("paid members") and the submit body
  // stay correct.
  static const bool _isPaid = true;
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

  // [LOCAL-738 §1+§2 / Michael's review C2/C2b/C2d] ONE PRICE PER LENGTH. For
  // each length the organiser ticks it ON and picks exactly ONE price for it
  // (no cross-product of every price × every length, which let "$15/month AND
  // $15/year" through meaninglessly). The price chips come from the SERVER
  // (CommunitiesService.passPrices → APPLE_LIVE_PASS_PRODUCTS, the one list) —
  // there is no "Custom price" any more, so what is shown selected is exactly
  // what is sent. The app falls back to $1/$5/$10/$20 only if the call fails.
  static const List<String> _lengths = ['day', 'week', 'month', 'year'];
  // The server-supplied prices (empty until loaded / on failure → fallback).
  List<PassPrice> _passPrices = const [];
  bool _pricesLoading = true;
  // Per length: is it offered, and which ONE product_id is its price.
  final Map<String, bool> _lengthEnabled = {
    'day': false,
    'week': false,
    'month': true,
    'year': false,
  };
  final Map<String, String?> _lengthPrice = {
    'day': null,
    'week': null,
    'month': null,
    'year': null,
  };

  // [LOCAL-738 §4 / C2c] How often members get new tours — required single
  // select, default 'week'.
  String _releaseCadence = 'week';

  // [LOCAL-738 §5] Listed location WITHOUT typing numbers: "Use my location"
  // (device GPS) fills the lat/lng controllers; manual entry stays as a
  // fallback (the controllers remain the single source for the submitted
  // coordinates). _locating guards the GPS button's spinner.
  bool _locating = false;

  @override
  void initState() {
    super.initState();
    _checkPlan();
    _prefill();
    _loadPrices();
    _name.addListener(_onNameChanged);
  }

  @override
  void dispose() {
    _nameDebounce?.cancel();
    _name.removeListener(_onNameChanged);
    for (final c in [
      _name, _description, _organiserName, _organiserBio, _organiserContact,
      _rules, _waiver, _lat, _lng,
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  /// [LOCAL-738 §2] Load the allowed pass PRICES from the server (the single
  /// APPLE_LIVE_PASS_PRODUCTS list). On failure, fall back to the documented
  /// $1/$5/$10/$20 set so the form still works offline. The default month price
  /// is seeded to the first (cheapest) price once prices are known.
  Future<void> _loadPrices() async {
    final prices = await CommunitiesService.passPrices();
    if (!mounted) return;
    setState(() {
      _passPrices = prices.isNotEmpty ? prices : _fallbackPrices;
      _pricesLoading = false;
      // Seed every enabled length that has no price yet with the cheapest.
      final cheapest = _passPrices.first.productId;
      for (final len in _lengths) {
        if (_lengthEnabled[len] == true && _lengthPrice[len] == null) {
          _lengthPrice[len] = cheapest;
        }
      }
    });
  }

  /// The offline fallback price list — used ONLY when the server call fails.
  /// Matches APPLE_LIVE_PASS_PRODUCTS ($1/$5/$10/$20) so a fallback create still
  /// sends a product the server accepts.
  static const List<PassPrice> _fallbackPrices = [
    PassPrice(productId: 'audioura.pass.usd1', priceUsd: 1, label: '\$1'),
    PassPrice(productId: 'audioura.pass.usd5', priceUsd: 5, label: '\$5'),
    PassPrice(productId: 'audioura.pass.usd10', priceUsd: 10, label: '\$10'),
    PassPrice(productId: 'audioura.pass.usd20', priceUsd: 20, label: '\$20'),
  ];

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

  /// [LOCAL-738 §1] Exactly one `{product_id, length}` per TICKED length, using
  /// that length's ONE chosen price, filtered to the server's allowed prices so
  /// an off-list price can never be sent. Delegates to the pure helper so the
  /// UI and the unit tests run the same logic.
  List<Map<String, String>> _passOptions() => CommunityPassForm.passOptions(
        enabled: _lengthEnabled,
        price: _lengthPrice,
        allowed: _allowedProductIds,
      );

  /// Every ticked length has an allowed price chosen, and at least one length
  /// is on — the condition the Create button needs.
  bool get _passesValid => CommunityPassForm.passesValid(
        enabled: _lengthEnabled,
        price: _lengthPrice,
        allowed: _allowedProductIds,
      );

  /// The product ids currently offered to the organiser (server prices, or the
  /// fallback). Empty while loading — the gate stays closed until prices load.
  Set<String> get _allowedProductIds =>
      _passPrices.map((p) => p.productId).toSet();

  bool get _hasWaiver => _waiver.text.trim().isNotEmpty;

  /// [LOCAL-700 §4] All REQUIRED fields present. Required: name, description,
  /// organiser name, rules. Location is required ONLY for a Listed community.
  bool get _requiredFilled => CommunityCopy.requiredFieldsFilled(
        name: _name.text,
        description: _description.text,
        organiserName: _organiserName.text,
        rules: _rules.text,
        listed: _hasWaiver ? false : _listed,
        latitude: _lat.text,
        longitude: _lng.text,
      );

  /// [LOCAL-700 §4] The Create button is enabled only when all required fields
  /// are filled AND the Organiser Terms are accepted (and we are not mid-submit,
  /// and the name is not known-taken).
  bool get _canSubmit =>
      !_submitting &&
      _passesValid &&
      CommunityCopy.createEnabled(
        requiredFilled: _requiredFilled,
        termsAccepted: _organiserTermsAccepted,
        nameAvailable: _nameAvailable,
      );

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
          // [LOCAL-704 / D665] No free communities — every community charges at
          // least $1 to join (the commitment fee). [LOCAL-738 §1] ONE price per
          // length: tick a length and pick ONE price for it; at least one
          // length must be on.
          const Text('Membership',
              style: TextStyle(fontWeight: FontWeight.bold)),
          const Padding(
            padding: EdgeInsets.only(top: 2, bottom: 4),
            child: Text(
              'Every member pays at least \$1 to join. Tick each pass length you '
              'offer and pick one price for it.',
              style: TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ),
          ..._buildPaidSection(),
          // [LOCAL-738 §4 / C2c] How often members get new tours.
          ..._buildReleaseCadenceSection(),
          const Divider(),
          SwitchListTile(
            title: const Text('Listed on the Home map'),
            subtitle: Text(_hasWaiver
                ? 'Disabled — a waiver community is always Private'
                : 'Shown with a community badge (needs a location)'),
            value: effectiveListed,
            onChanged: _hasWaiver ? null : (v) => setState(() => _listed = v),
          ),
          // [LOCAL-738 §5] Listed location via GPS ("Use my location") with
          // manual entry as a fallback — no more typing numbers by hand.
          if (effectiveListed) ..._buildLocationSection(),
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
          // [LOCAL-703 / D664] The launch-window rule, stated BEFORE the Create
          // button so the organiser knows the one-week / two-members deal (and
          // whether it's "paid members" or "members") before committing.
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.blue.shade50,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: Colors.blue.shade200),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.timer_outlined, size: 20, color: Colors.blue),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(CommunityCopy.createLaunchRule(paid: _isPaid),
                      style: const TextStyle(fontSize: 13)),
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
    if (_pricesLoading) {
      return const [
        Padding(
          padding: EdgeInsets.all(16),
          child: Center(
            child: SizedBox(
                height: 20, width: 20,
                child: CircularProgressIndicator(strokeWidth: 2)),
          ),
        ),
      ];
    }
    // One row per length: a tick to offer it, and — when ticked — a single-
    // select of ONE server price for that length. What is shown is what is sent.
    return _lengths.map((len) {
      final enabled = _lengthEnabled[len] == true;
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              title: Text('Per $len'),
              subtitle: enabled
                  ? const Text('Pick one price for this length')
                  : null,
              value: enabled,
              onChanged: (v) => setState(() {
                final on = v ?? false;
                _lengthEnabled[len] = on;
                if (on && _lengthPrice[len] == null && _passPrices.isNotEmpty) {
                  // Default to the cheapest price so a ticked length is valid.
                  _lengthPrice[len] = _passPrices.first.productId;
                }
                if (!on) _lengthPrice[len] = null;
              }),
            ),
            if (enabled)
              Padding(
                padding: const EdgeInsets.only(left: 16, bottom: 8),
                child: Wrap(
                  spacing: 8,
                  children: _passPrices.map((p) {
                    final selected = _lengthPrice[len] == p.productId;
                    return ChoiceChip(
                      label: Text(p.label),
                      selected: selected,
                      onSelected: (_) =>
                          setState(() => _lengthPrice[len] = p.productId),
                    );
                  }).toList(),
                ),
              ),
          ],
        ),
      );
    }).toList();
  }

  /// [LOCAL-738 §4 / C2c] The "How often will members get new tours?" single
  /// select — day / week / month / year, default week.
  List<Widget> _buildReleaseCadenceSection() {
    return [
      const Divider(),
      const Text('How often will members get new tours?',
          style: TextStyle(fontWeight: FontWeight.bold)),
      const Padding(
        padding: EdgeInsets.only(top: 2, bottom: 4),
        child: Text(
          'Tell members how often to expect a new tour.',
          style: TextStyle(fontSize: 12, color: Colors.grey),
        ),
      ),
      Wrap(
        spacing: 8,
        children: _lengths.map((len) {
          return ChoiceChip(
            label: Text(_cadenceLabel(len)),
            selected: _releaseCadence == len,
            onSelected: (_) => setState(() => _releaseCadence = len),
          );
        }).toList(),
      ),
    ];
  }

  static String _cadenceLabel(String len) {
    switch (len) {
      case 'day':
        return 'Daily';
      case 'week':
        return 'Weekly';
      case 'month':
        return 'Monthly';
      case 'year':
        return 'Yearly';
      default:
        return len;
    }
  }

  /// [LOCAL-738 §5] The Listed-community location block: "Use my location" (GPS)
  /// fills the coordinates, with manual lat/lng fields as a fallback.
  List<Widget> _buildLocationSection() {
    final hasCoords =
        _lat.text.trim().isNotEmpty && _lng.text.trim().isNotEmpty;
    return [
      Padding(
        padding: const EdgeInsets.only(top: 8, bottom: 4),
        child: Row(
          children: [
            ElevatedButton.icon(
              onPressed: _locating ? null : _useMyLocation,
              icon: _locating
                  ? const SizedBox(
                      height: 16,
                      width: 16,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.my_location, size: 18),
              label: const Text('Use my location'),
            ),
            const SizedBox(width: 12),
            if (hasCoords)
              Expanded(
                child: Text(
                  'Pinned: ${_lat.text.trim()}, ${_lng.text.trim()}',
                  style: const TextStyle(fontSize: 12, color: Colors.green),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
          ],
        ),
      ),
      const Padding(
        padding: EdgeInsets.only(bottom: 4),
        child: Text(
          'Or enter coordinates manually:',
          style: TextStyle(fontSize: 12, color: Colors.grey),
        ),
      ),
      _field(_lat, 'Latitude', required: true, onChanged: (_) => setState(() {})),
      _field(_lng, 'Longitude', required: true, onChanged: (_) => setState(() {})),
    ];
  }

  /// [LOCAL-738 §5] Fill the latitude/longitude from the device GPS. Follows the
  /// same permission/best-effort pattern as NavigationService: if permission is
  /// denied or the fix fails, show a short message and leave manual entry.
  Future<void> _useMyLocation() async {
    setState(() => _locating = true);
    try {
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        if (!mounted) return;
        setState(() => _locating = false);
        _snack('Location permission denied. You can enter coordinates manually.');
        return;
      }
      final pos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 8),
        ),
      );
      if (!mounted) return;
      setState(() {
        _lat.text = pos.latitude.toStringAsFixed(6);
        _lng.text = pos.longitude.toStringAsFixed(6);
        _locating = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _locating = false);
      _snack('Could not get your location. You can enter coordinates manually.');
    }
  }

  Future<void> _submit() async {
    final name = _name.text.trim();
    final listed = _hasWaiver ? false : _listed;
    if (listed && (_lat.text.trim().isEmpty || _lng.text.trim().isEmpty)) {
      _snack('A listed community needs a location. Tap "Use my location" or '
          'enter coordinates.');
      return;
    }
    final passes = _passOptions();
    if (passes.isEmpty) {
      _snack('Tick at least one pass length and pick a price for it.');
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
      // [LOCAL-738 §4 / C2c] How often members get new tours.
      'release_cadence': _releaseCadence,
    };

    // [LOCAL-738 §3] Use the server's real error + message on failure, instead
    // of the old generic "the name may be taken, or you may need a plan" guess.
    final result = await CommunitiesService.createResult(body);
    if (!mounted) return;
    setState(() => _submitting = false);
    if (!result.ok) {
      _snack(result.message ?? 'Could not create the community.');
      return;
    }
    _showInvite(result.community!);
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
            const SizedBox(height: 12),
            // [LOCAL-703 / D664] The launch countdown, shown right on the
            // creation confirmation so the clock is visible from the first
            // moment ("152 h left to get 2 paid members — 0 of 2 so far").
            Row(
              children: [
                const Icon(Icons.timer_outlined, size: 18, color: Colors.blue),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    CommunityCopy.launchCountdown(
                      launched: c.launch.launched,
                      paid: c.isPaid,
                      hoursLeft: c.launch.hoursLeft,
                      membersSoFar: c.launch.membersSoFar,
                      membersNeeded: c.launch.membersNeeded,
                    ),
                    style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: Colors.blue.shade900),
                  ),
                ),
              ],
            ),
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
          // [LOCAL-742, LEAD] The organiser's first job is a tour (Michael
          // 2026-10-23): go straight to Generate with this community chosen.
          FilledButton(
            key: const Key('create_first_tour_button'),
            onPressed: () {
              Navigator.pop(ctx);
              Navigator.pushReplacement(
                context,
                MaterialPageRoute(
                    builder: (_) => TourGeneratorScreen(initialCommunityId: c.id)),
              );
            },
            child: const Text('Create your first tour'),
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
  bool _regenerating = false;
  bool _building = false;

  // [LOCAL-710B / D672 addendum 1] The tour the organiser chooses to include in
  // the invite. null = "Latest tour" (the default — the newest tour), which is
  // only offered when the community actually has tours. A specific id means the
  // organiser PICKED that tour to send.
  int? _selectedTourId;

  List<CommunityInviteTourOption> get _tours => widget.community.tours;

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
        // [LOCAL-710B / D672 addendum 1] "Tour to include" — only when the
        // community has tours. Default "Latest tour"; the organiser may pick a
        // specific one instead. No tours → no picker (and the invite leaves the
        // tour line out).
        if (_tours.isNotEmpty) ...[
          const SizedBox(height: 12),
          const Text('Tour to include',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold)),
          const SizedBox(height: 4),
          DropdownButton<int?>(
            isExpanded: true,
            value: _selectedTourId,
            onChanged: (v) => setState(() => _selectedTourId = v),
            items: <DropdownMenuItem<int?>>[
              const DropdownMenuItem<int?>(
                value: null,
                child: Text('Latest tour'),
              ),
              for (final t in _tours)
                DropdownMenuItem<int?>(
                  value: t.id,
                  child: Text(
                    shortTourTitle(t.name),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
            ],
          ),
        ],
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 4,
          children: [
            OutlinedButton.icon(
              onPressed: _building ? null : _copy,
              icon: const Icon(Icons.copy, size: 18),
              label: const Text('Copy'),
            ),
            OutlinedButton.icon(
              onPressed: _building ? null : _share,
              icon: const Icon(Icons.ios_share, size: 18),
              label: const Text('Share'),
            ),
            OutlinedButton.icon(
              onPressed: _building ? null : _email,
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

  /// [LOCAL-710B / D672 addenda 1 + 2] Build the full self-explaining invite
  /// body from the community's REAL settings, resolving the chosen/latest
  /// tour's share code via the EXISTING share endpoint (never a second code
  /// system, D671). Returns null if the widget was disposed mid-await.
  Future<String?> _buildInviteBody() async {
    final c = widget.community;
    final tour = await _resolveInviteTour();
    if (!mounted) return null;
    final pass = c.cheapestPass;
    return CommunityCopy.emailInviteBody(
      communityName: c.name,
      description: c.description,
      organiserName: c.organiser.name,
      code: _code,
      memberCount: c.memberCount,
      isPaid: c.isPaid,
      visibility: c.visibility,
      hasWaiver: c.hasWaiver,
      rulesText: c.rulesText,
      cheapestPassPrice: pass?.label,
      cheapestPassLength: pass?.length,
      tour: tour,
    );
  }

  /// Resolve the tour line's data: the picked tour, else the latest (the first,
  /// since the server returns tours newest-first). Fetches the 8-char share
  /// code via TourShareService.share. Returns null when there are no tours or
  /// the share request fails (the invite simply omits the tour line).
  Future<CommunityInviteTour?> _resolveInviteTour() async {
    if (_tours.isEmpty) return null;
    final bool picked = _selectedTourId != null;
    final CommunityInviteTourOption t = picked
        ? _tours.firstWhere((e) => e.id == _selectedTourId,
            orElse: () => _tours.first)
        : _tours.first; // newest-first → first is the latest
    final res = await TourShareService.share(t.id);
    if (!res.ok || res.code == null || res.code!.isEmpty) return null;
    // [LOCAL-711 / D673] Prefer the server short title when the listing carries
    // one; else fall back to the app's shortTourTitle of the raw name.
    final serverShort = (t.shortTitle ?? '').trim();
    return CommunityInviteTour(
      title: serverShort.isNotEmpty ? serverShort : shortTourTitle(t.name),
      code: res.code!,
      stopCount: t.stopCount,
      picked: picked,
    );
  }

  Future<void> _copy() async {
    setState(() => _building = true);
    final body = await _buildInviteBody();
    if (!mounted) return;
    setState(() => _building = false);
    if (body == null) return;
    await Clipboard.setData(ClipboardData(text: body));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Invite copied.')));
  }

  Future<void> _share() async {
    setState(() => _building = true);
    final body = await _buildInviteBody();
    if (!mounted) return;
    setState(() => _building = false);
    if (body == null) return;
    await Share.share(body,
        subject: CommunityCopy.emailInviteSubject(widget.community.name));
  }

  /// Open the device mail composer (share sheet / mailto) with a subject + body
  /// pre-filled. Prefer the share sheet (reliable across platforms); if a
  /// mailto is needed it carries the same subject + body. NEVER claims the mail
  /// was sent.
  Future<void> _email() async {
    final c = widget.community;
    setState(() => _building = true);
    final body = await _buildInviteBody();
    if (!mounted) return;
    setState(() => _building = false);
    if (body == null) return;
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
      // The invite body is rebuilt on demand from _code (+ the community's real
      // settings and the chosen tour), so there is no cached message to refresh
      // here (D672 addenda).
    });
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('New invite code generated. The old code no longer works.')));
  }
}
