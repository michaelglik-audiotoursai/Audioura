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
import 'dart:convert';
import '../services/communities_service.dart';
import '../services/community_tour_service.dart';
import '../services/community_downloads.dart';
import '../services/community_background.dart';
import '../services/community_notifications.dart';
import '../services/tour_download_service.dart';
import '../services/iap_service.dart';
import '../services/device_service.dart';
import '../services/document_acceptance_service.dart';
import '../services/deep_link_service.dart';
import '../utils/downloaded_message.dart';
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
  // [LOCAL-713 / D675] The server tour ids already on the phone (from the
  // saved_tours records), used to show "On this phone ✓" vs "Download".
  Set<String> _onPhoneTourIds = const {};
  // [LOCAL-715 / D675 addendum 1] The listening language for THIS community's
  // tours. `_communityLanguageChoice` is the explicit per-community choice
  // (`listening_language_<id>`), null when none is set — then the page shows
  // (and downloads in) the inherited default. `_resolvedLanguage` is what
  // languageForCommunity resolves to (the choice, else About's default, else
  // the phone locale, else English) — the Download button uses it.
  String? _communityLanguageChoice;
  String _resolvedLanguage = kDefaultListeningLanguage;
  // [LOCAL-715] About's saved Listening language (null when none saved) — the
  // DEFAULT this community inherits when it has no per-community choice. Used by
  // the picker's "Use the default" row to show the inherited value.
  String? _aboutDefaultLanguage;
  final Set<int> _downloading = {};
  // [LOCAL-714 / D675 part 2] The per-community auto-download switch (default
  // OFF) and the app-wide "Also on mobile data" switch (default OFF).
  bool _autoDownload = false;
  bool _autoDownloadCellular = false;

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
    // [LOCAL-713 / D675] The set of server tour ids already on the phone — for
    // the per-row Download / On this phone status.
    final onPhone = <String>{};
    for (final s in (prefs.getStringList('saved_tours') ?? const [])) {
      try {
        final m = json.decode(s) as Map<String, dynamic>;
        final tid = m['tour_id'];
        final sid = m['server_tour_id'];
        if (tid is String && tid.isNotEmpty) onPhone.add(tid);
        if (sid is String && sid.isNotEmpty) onPhone.add(sid);
      } catch (_) {}
    }
    // [LOCAL-715 / D675 addendum 1] The per-community listening language: the
    // explicit per-community choice (null when none), and the RESOLVED language
    // the Download button uses (via languageForCommunity — choice → About →
    // phone locale → English).
    final locale = WidgetsBinding.instance.platformDispatcher.locale.languageCode;
    final choice =
        c != null ? prefs.getString(communityLanguagePrefKey(c.id)) : null;
    final aboutDefault = prefs.getString(kListeningLanguagePrefKey);
    final resolved = c != null
        ? languageForCommunity(prefs, c.id, localeLanguageCode: locale)
        : defaultListeningLanguage(locale);
    setState(() {
      _community = c;
      _onPhoneTourIds = onPhone;
      _communityLanguageChoice = choice;
      _aboutDefaultLanguage = aboutDefault;
      _resolvedLanguage = resolved;
      _autoDownload =
          c != null ? (prefs.getBool(autoDownloadPrefKey(c.id)) ?? false) : false;
      _autoDownloadCellular =
          prefs.getBool(kAutoDownloadCellularPrefKey) ?? false;
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
      // [LOCAL-714 / D675 part 2] After a free join, ask the auto-download
      // question.
      await _askAutoDownloadQuestion(updated.id);
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
      // [LOCAL-714 / D675 part 2] After a successful pass purchase, ask the
      // auto-download question.
      await _askAutoDownloadQuestion(c.id);
    } else if (result.status != IapResultStatus.cancelled) {
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(result.message ?? 'Purchase failed.')));
    }
  }

  /// [LOCAL-728 / D691] Report this community, organiser or its tours to
  /// AUDIOURA. There is no user-level blocking: a member or organiser can only
  /// report, and Audioura reviews it (and may bar, ban or disable). Opens a
  /// short form — a reason choice plus optional free text — then POSTs it. The
  /// organiser is not notified by the app.
  Future<void> _report() async {
    final c = _community;
    if (c == null) return;
    final result = await showModalBottomSheet<_ReportResult>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => const _ReportToAudiouraSheet(),
    );
    if (result == null) return; // cancelled
    final ok = await CommunitiesService.report(
      c.id,
      userId: _userId,
      reason: result.reason,
      detail: result.detail,
    );
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(ok
            ? 'Thanks — Audioura will review this.'
            : 'Could not send the report. Please try again.')));
  }

  /// [LOCAL-714 / D675 part 2] The join question — asked on a free join and
  /// after a successful pass purchase: "Download this community's new tours
  /// automatically? Only on Wi-Fi, when your phone isn't busy." Yes / Not now.
  /// Yes sets `auto_download_<id>`, asks for notification permission (the ONLY
  /// place permission is requested), and (re)registers the background task.
  Future<void> _askAutoDownloadQuestion(int communityId) async {
    if (!mounted) return;
    final yes = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Get new tours automatically?'),
        content: const Text(
          "Download this community's new tours automatically? Only on Wi-Fi, "
          "when your phone isn't busy.",
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Not now')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Yes')),
        ],
      ),
    );
    await _setAutoDownload(communityId, yes == true);
  }

  /// Persist the per-community auto-download switch and keep the background task
  /// in sync. Turning it ON asks for notification permission (D675 part 2 §3 —
  /// only on Yes) and registers the periodic task; turning the LAST one off
  /// leaves the task registered but harmless (it finds nothing to do).
  Future<void> _setAutoDownload(int communityId, bool on) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(autoDownloadPrefKey(communityId), on);
    if (mounted) setState(() => _autoDownload = on);
    if (on) {
      // Permission is requested ONLY here (on opt-in), never at app launch.
      await CommunityNotifications.requestPermissionOnOptIn();
      await registerCommunitySyncTask();
    }
  }

  /// Persist the app-wide "Also on mobile data" switch (default OFF) and
  /// re-register the task so its network constraint matches.
  Future<void> _setAutoDownloadCellular(bool on) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(kAutoDownloadCellularPrefKey, on);
    if (mounted) setState(() => _autoDownloadCellular = on);
    await registerCommunitySyncTask();
  }

  /// [LOCAL-714 / D675 part 2] The auto-download controls shown to a member/
  /// owner: the per-community switch and the app-wide "Also on mobile data"
  /// switch (off by default). Hidden from non-members.
  List<Widget> _autoDownloadSection(Community c) {
    final canDownload = (c.myStatus.isMember && c.myStatus.active) || c.isOwner;
    if (!canDownload) return const [];
    return [
      _sectionTitle('New tours'),
      SwitchListTile(
        key: const Key('auto_download_switch'),
        contentPadding: EdgeInsets.zero,
        value: _autoDownload,
        onChanged: (v) => _setAutoDownload(c.id, v),
        title: const Text('Download new tours automatically'),
        subtitle: const Text("Only on Wi-Fi, when your phone isn't busy."),
      ),
      SwitchListTile(
        key: const Key('auto_download_cellular_switch'),
        contentPadding: EdgeInsets.zero,
        value: _autoDownloadCellular,
        onChanged: _autoDownload ? (v) => _setAutoDownloadCellular(v) : null,
        title: const Text('Also on mobile data'),
        subtitle: const Text('Off by default — uses your data allowance.'),
      ),
    ];
  }

  /// [LOCAL-715 / D675 addendum 1] The per-community listening-language row,
  /// shown to a member/owner only. It reads "Language for this community's
  /// tours" with the current value as the trailing name, and opens the SAME
  /// picker as About (the kListeningLanguages list). Until a language is chosen
  /// for this community, the value shows the INHERITED default as e.g.
  /// "Phone default (English)"; once chosen, it shows the chosen name. Tapping
  /// offers a "Use the default" choice that removes the per-community key.
  List<Widget> _languageSection(Community c) {
    final canChoose = (c.myStatus.isMember && c.myStatus.active) || c.isOwner;
    if (!canChoose) return const [];
    final chosen = _communityLanguageChoice;
    final subtitle = chosen != null
        ? listeningLanguageName(chosen)
        : 'Phone default (${listeningLanguageName(_resolvedLanguage)})';
    return [
      ListTile(
        key: const Key('community_language_row'),
        contentPadding: EdgeInsets.zero,
        leading: const Icon(Icons.translate, color: Colors.teal),
        title: const Text("Language for this community's tours"),
        subtitle: Text(subtitle),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => _pickCommunityLanguage(c),
      ),
    ];
  }

  /// [LOCAL-715 / D675 addendum 1] Open the language picker for THIS community.
  /// Lists every Audioura language (kListeningLanguages) plus a "Use the
  /// default" choice at the top that REMOVES the per-community key so the page
  /// falls back to About's Listening language (then the phone locale, then
  /// English). Picking a language stores `listening_language_<id>`.
  Future<void> _pickCommunityLanguage(Community c) async {
    final selected = await showModalBottomSheet<String?>(
      context: context,
      builder: (ctx) {
        return SafeArea(
          child: ListView(
            shrinkWrap: true,
            children: [
              const Padding(
                padding: EdgeInsets.fromLTRB(16, 16, 16, 8),
                child: Text("Language for this community's tours",
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
              ),
              // "Use the default" — removes the per-community key. The sentinel
              // empty string distinguishes it from a real language code.
              ListTile(
                key: const Key('community_language_use_default'),
                leading: const Icon(Icons.settings_backup_restore),
                title: const Text('Use the default'),
                subtitle: Text(
                    'Phone default (${listeningLanguageName(_resolvedLanguageIgnoringChoice())})'),
                trailing: _communityLanguageChoice == null
                    ? const Icon(Icons.check, color: Colors.teal)
                    : null,
                onTap: () => Navigator.pop(ctx, ''),
              ),
              const Divider(height: 1),
              ...kListeningLanguages.map((code) => ListTile(
                    key: Key('community_language_$code'),
                    title: Text(listeningLanguageName(code)),
                    trailing: _communityLanguageChoice == code
                        ? const Icon(Icons.check, color: Colors.teal)
                        : null,
                    onTap: () => Navigator.pop(ctx, code),
                  )),
            ],
          ),
        );
      },
    );
    if (selected == null) return; // dismissed without choosing
    await _setCommunityLanguage(c, selected.isEmpty ? null : selected);
  }

  /// Persist the per-community language choice (or remove the key when [code]
  /// is null — "Use the default") and refresh the resolved display.
  Future<void> _setCommunityLanguage(Community c, String? code) async {
    final prefs = await SharedPreferences.getInstance();
    if (code == null) {
      await prefs.remove(communityLanguagePrefKey(c.id));
    } else {
      await prefs.setString(communityLanguagePrefKey(c.id), code);
    }
    final locale =
        WidgetsBinding.instance.platformDispatcher.locale.languageCode;
    final resolved = languageForCommunity(prefs, c.id, localeLanguageCode: locale);
    if (!mounted) return;
    setState(() {
      _communityLanguageChoice = code;
      _resolvedLanguage = resolved;
    });
  }

  /// The language this community would resolve to with NO per-community choice —
  /// i.e. About's default (then phone locale, then English). Used by the "Use
  /// the default" row so it always shows the inherited value, even when a
  /// per-community choice is currently set.
  String _resolvedLanguageIgnoringChoice() {
    final locale =
        WidgetsBinding.instance.platformDispatcher.locale.languageCode;
    return resolveCommunityLanguage(
      aboutDefault: _aboutDefaultLanguage,
      localeLanguageCode: locale,
    );
  }

  /// [LOCAL-713 / D675 §3] Download a community tour, running the SAME download
  /// path a Home/Listen download uses (TourDownloadService — never a second
  /// path). The pass covers a member, so there is no purchase prompt here; if
  /// the server still refuses with membership_required (e.g. an expired pass),
  /// we open the community page's join/buy flow, exactly as the existing
  /// community-tour flow does. The language is pickDownloadLanguage over the
  /// tour's available languages, the listener's preferred language and the
  /// tour's original — v1 never requests a new translation.
  Future<void> _downloadCommunityTour(CommunityTour tour) async {
    if (_downloading.contains(tour.id)) return;
    setState(() => _downloading.add(tour.id));
    try {
      // The list endpoint does not carry a languages list, so `available` is
      // empty here and pickDownloadLanguage falls back to the original — the
      // tour's own row (its id) is downloaded. The sync-on-open path, which DOES
      // carry languages, picks the per-community language when available.
      // [LOCAL-715 / D675 addendum 1] The preferred language is THIS community's
      // resolved language (languageForCommunity), not a single global one.
      final _ = pickDownloadLanguage(const [], _resolvedLanguage, '');
      final result = await TourDownloadService.downloadAndSave(tour.id);
      if (!mounted) return;
      switch (result.status) {
        case TourDownloadStatus.ok:
          setState(() => _onPhoneTourIds = {..._onPhoneTourIds, tour.id.toString()});
          // [LOCAL-716] Same wording helper as Home (exactly one tour here, so
          // "1 tour downloaded and is now on your Listen page"), with a View
          // button that opens the Listen tab on this tour.
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(downloadedMessage(downloaded: 1)),
            action: SnackBarAction(
              label: 'View',
              onPressed: () =>
                  PendingListenOpen.instance.offer(tour.id.toString()),
            ),
          ));
          break;
        case TourDownloadStatus.alreadyOnPhone:
          setState(() => _onPhoneTourIds = {..._onPhoneTourIds, tour.id.toString()});
          break;
        case TourDownloadStatus.membershipRequired:
          // The pass should cover a member; an expired pass lands here. Open the
          // community join/buy flow (reload the page so the passes show).
          await _load();
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                content: Text('Join this community to download its tours.')));
          }
          break;
        case TourDownloadStatus.failed:
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
              content: Text('Download failed. Please try again.')));
          break;
      }
    } finally {
      if (mounted) setState(() => _downloading.remove(tour.id));
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
          // [LOCAL-728 / D691] One action: Report to Audioura. No user-level
          // blocking — a member or organiser can only report; Audioura
          // reviews and may bar, ban or disable.
          IconButton(
            tooltip: 'Report to Audioura',
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

          // [LOCAL-704 / D665] The member count, shown prominently near the top
          // of every community page (active members, organiser excluded).
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Row(
              children: [
                const Icon(Icons.groups, size: 18, color: Colors.deepPurple),
                const SizedBox(width: 6),
                Text(
                  CommunityCopy.memberCountLabel(c.memberCount),
                  key: const Key('member_count_label'),
                  style: const TextStyle(
                      fontWeight: FontWeight.w600, color: Colors.deepPurple),
                ),
              ],
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
          // [LOCAL-704 / D665 addendum] Also hidden from the OWNER: the
          // organiser is not a member and has full access without a pass.
          if (!c.isOwner && !canListen && c.acceptsNewMembers) ...[
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

          // [LOCAL-701 / D663 §3 + LOCAL-713 / D675 §5] Tours MADE WITH Audioura
          // for this community. Every tour gets a status: a member/owner sees a
          // "Download" button (or "On this phone ✓" when it is already in
          // Listen, any language); a non-member sees "Join to download" (D663).
          // The tours list on the page payload (c.tours) is visible to everyone
          // who can see the page, so a non-member sees the tours with the join
          // prompt. The Download button runs the SAME download path a
          // Home/Listen download uses (TourDownloadService).
          //
          // [LOCAL-714 / D675 part 2] Above the list, a member/owner sees the
          // auto-download switch + the app-wide "Also on mobile data" toggle.
          ..._autoDownloadSection(c),
          // [LOCAL-715 / D675 addendum 1] The per-community listening-language
          // row (member/owner only): choose which language THIS community's
          // tours download in, inheriting About's default until one is chosen.
          ..._languageSection(c),
          if (c.tours.isNotEmpty) ...[
            _sectionTitle('Tours (${c.tours.length})'),
            ...c.tours.map((t) => _communityTourTile(c, t)),
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

  /// [LOCAL-713 / D675 §5] One community-tour row with its Download / On this
  /// phone ✓ / Join to download status. A member or the owner can download; a
  /// non-member is prompted to join.
  Widget _communityTourTile(Community c, CommunityInviteTourOption t) {
    final status = rowStatusFor(
      tourId: t.id,
      isMember: c.myStatus.isMember && c.myStatus.active,
      isOwner: c.isOwner,
      onPhoneTourIds: _onPhoneTourIds,
    );
    final title = (t.shortTitle != null && t.shortTitle!.trim().isNotEmpty)
        ? t.shortTitle!
        : t.name;
    final isBusy = _downloading.contains(t.id);
    Widget trailing;
    switch (status) {
      case CommunityTourRowStatus.onThisPhone:
        trailing = const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.check_circle, size: 18, color: Colors.green),
            SizedBox(width: 4),
            Text('On this phone', style: TextStyle(color: Colors.green)),
          ],
        );
        break;
      case CommunityTourRowStatus.joinToDownload:
        trailing = const Text('Join to download',
            style: TextStyle(color: Colors.deepPurple, fontWeight: FontWeight.w600));
        break;
      case CommunityTourRowStatus.download:
        trailing = isBusy
            ? const SizedBox(
                width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
            : ElevatedButton.icon(
                key: Key('download_tour_${t.id}'),
                onPressed: () => _downloadCommunityTour(
                    CommunityTour(
                      id: t.id,
                      name: t.name,
                      requestString: '',
                      visibility: 'members',
                      contentRating: 'general',
                    )),
                icon: const Icon(Icons.download, size: 18),
                label: const Text('Download'),
              );
        break;
    }
    return ListTile(
      leading: const Icon(Icons.headphones),
      title: Text(title),
      subtitle: t.stopCount > 0 ? Text('${t.stopCount} stops') : null,
      trailing: trailing,
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



/// [LOCAL-728 / D691] The result of the Report-to-Audioura form: a reason code
/// and the reporter's optional free text. Null is returned when the sheet is
/// dismissed without submitting.
class _ReportResult {
  final String reason;
  final String? detail;
  const _ReportResult(this.reason, this.detail);
}

/// [LOCAL-728 / D691] The single "Report to Audioura" form, opened from the
/// community page. A member or organiser picks a short reason and may add
/// optional detail; there is NO user-level blocking. On submit it returns a
/// [_ReportResult]; the caller POSTs it and shows "Thanks — Audioura will
/// review this." The organiser is not notified by the app.
class _ReportToAudiouraSheet extends StatefulWidget {
  const _ReportToAudiouraSheet();

  @override
  State<_ReportToAudiouraSheet> createState() => _ReportToAudiouraSheetState();
}

class _ReportToAudiouraSheetState extends State<_ReportToAudiouraSheet> {
  // The reason codes the app offers. The server stores the code in `reason`.
  static const Map<String, String> _reasons = {
    'spam': 'Spam or scam',
    'offensive': 'Offensive or abusive',
    'inaccurate': 'Inaccurate or misleading',
    'inappropriate': 'Inappropriate content',
    'other': 'Something else',
  };

  String _reason = 'spam';
  final TextEditingController _detail = TextEditingController();

  @override
  void dispose() {
    _detail.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          left: 16,
          right: 16,
          top: 16,
          bottom: MediaQuery.of(context).viewInsets.bottom + 16,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Report to Audioura',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            const Text(
              'Tell us what\'s wrong. Audioura reviews every report and may '
              'remove content, bar a member, or end access. The organiser is '
              'not told who reported.',
              style: TextStyle(color: Colors.black54, fontSize: 13),
            ),
            const SizedBox(height: 12),
            for (final entry in _reasons.entries)
              RadioListTile<String>(
                key: Key('report_reason_${entry.key}'),
                value: entry.key,
                groupValue: _reason,
                onChanged: (v) => setState(() => _reason = v ?? _reason),
                title: Text(entry.value),
                contentPadding: EdgeInsets.zero,
                dense: true,
              ),
            const SizedBox(height: 8),
            TextField(
              key: const Key('report_detail'),
              controller: _detail,
              maxLines: 3,
              maxLength: 1000,
              decoration: const InputDecoration(
                labelText: 'Anything to add? (optional)',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Cancel'),
                ),
                const Spacer(),
                ElevatedButton(
                  key: const Key('report_submit'),
                  onPressed: () {
                    final text = _detail.text.trim();
                    Navigator.pop(
                        context,
                        _ReportResult(
                            _reason, text.isEmpty ? null : text));
                  },
                  child: const Text('Send report'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
