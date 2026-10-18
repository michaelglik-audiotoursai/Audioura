/// [LOCAL-709 / D671] Deep-link handling for tour/community share links.
///
/// A share link is `https://audioura.com/t/<CODE>` (optionally `?n=<name>`).
/// With Audioura installed it is an Android App Link / iOS Universal Link:
/// opening it brings the app to Home → Search with the code filled in and the
/// search run — the SAME path a pasted code takes (`home_screen`'s share-code
/// branch via [PendingShareSearch]). We never build a second resolver here;
/// this file only turns a URI into a code and hands that code to Home.
///
/// Three entry points feed one mechanism ([PendingShareSearch.offer]):
///   1. Cold start  — the link that launched the app (`getInitialLink`).
///   2. Warm start  — links that arrive while running (`uriLinkStream`).
///   3. Deferred    — the FIRST launch after an install, when the link could
///      not open the app because it was not installed yet:
///        • Android: the Play Install Referrer carries `audioura_code=<CODE>`.
///        • iOS: the landing page's store button copied the code to the
///          clipboard; we offer once to open it.
///
/// Everything here is defensive: a plugin/platform error never crashes startup
/// and never blocks the normal app.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:app_links/app_links.dart';
import 'package:android_play_install_referrer/android_play_install_referrer.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../utils/share_code.dart';

/// The one place a pending share-code search is parked between "a link/referrer/
/// clipboard produced a code" and "Home ran the search". Home listens to
/// [code]; when it becomes non-null Home fills Search and dispatches it through
/// its normal share-code branch, then calls [consume] so a rebuild does not run
/// the search twice.
///
/// A plain [ValueNotifier] (not a stream) so a widget test can set a code and
/// assert Home reacts, with no plugins involved.
class PendingShareSearch {
  PendingShareSearch._();
  static final PendingShareSearch instance = PendingShareSearch._();

  final ValueNotifier<String?> code = ValueNotifier<String?>(null);

  /// Offer a raw code to Home. Ignored when null/empty so callers can pass the
  /// result of [DeepLinkService.codeFromUri] straight through.
  void offer(String? value) {
    if (value == null || value.isEmpty) return;
    code.value = value;
  }

  /// Clear the pending code once Home has acted on it.
  void consume() {
    code.value = null;
  }
}

/// SharedPreferences key: set true after the one-and-only deferred-link check,
/// so the Install Referrer / clipboard prompt runs exactly once, ever (D671 §4:
/// "one paste prompt, once, never again").
const String kDeferredLinkCheckedKey = 'deferred_share_link_checked_v1';

/// Asks the user whether to open the tour the clipboard suggests (iOS deferred
/// link). Returns true for "Open", false/null for "Not now" — the caller treats
/// anything but true as "do not open". A typedef so a test can inject a
/// decision without a BuildContext.
typedef DeferredPrompt = Future<bool> Function(String code);

class DeepLinkService {
  DeepLinkService._();
  static final DeepLinkService instance = DeepLinkService._();

  AppLinks? _appLinks;
  StreamSubscription<Uri>? _sub;

  /// PURE: map an incoming URI to a share code, or null when it is not one of
  /// our links. The rule (D671 §2): scheme http(s), host `audioura.com` (any
  /// case, optional leading `www.`), first path segment `t`, and the segment
  /// after it a valid share-code shape. A non-`/t/` path is ignored (returns
  /// null) so the home page or a legal page never triggers a search.
  ///
  /// This is the only parser; tests drive it directly (no plugins).
  static String? codeFromUri(Uri uri) {
    if (uri.scheme != 'https' && uri.scheme != 'http') return null;
    final host = uri.host.toLowerCase();
    if (host != kShareLinkHost && host != 'www.$kShareLinkHost') return null;
    final segs = uri.pathSegments.where((s) => s.isNotEmpty).toList();
    if (segs.length < 2) return null;
    if (segs[0] != 't') return null;
    final candidate = segs[1];
    return isShareCodeShape(candidate) ? candidate : null;
  }

  /// PURE: pull `audioura_code=<CODE>` out of a Play Install Referrer string
  /// (a URL-query-shaped blob like `utm_source=x&audioura_code=FFush25U`).
  /// Returns the code only when it is a valid share-code shape. Null otherwise.
  static String? codeFromInstallReferrer(String? referrer) {
    if (referrer == null || referrer.isEmpty) return null;
    final params = Uri.splitQueryString(referrer);
    final raw = params['audioura_code'];
    if (raw == null) return null;
    final code = raw.trim();
    return isShareCodeShape(code) ? code : null;
  }

  /// Wire up cold- and warm-start links. Call once, early (e.g. from `main`).
  /// Every incoming link that resolves to a code is parked in
  /// [PendingShareSearch]; Home consumes it. Safe to call when the plugin is
  /// unavailable (desktop/test) — it simply no-ops.
  Future<void> init() async {
    try {
      _appLinks ??= AppLinks();
    } catch (_) {
      return; // plugin not available on this platform/build.
    }
    final appLinks = _appLinks!;

    // Cold start: the link that launched the app, if any.
    try {
      final initial = await appLinks.getInitialLink();
      if (initial != null) {
        PendingShareSearch.instance.offer(codeFromUri(initial));
      }
    } catch (_) {
      // No initial link, or the platform cannot provide one — ignore.
    }

    // Warm start: links while the app runs.
    try {
      _sub = appLinks.uriLinkStream.listen(
        (uri) => PendingShareSearch.instance.offer(codeFromUri(uri)),
        onError: (Object _) {},
      );
    } catch (_) {
      // Stream unavailable — cold start alone still works.
    }
  }

  /// Run the DEFERRED-link check at most once in the app's lifetime (D671 §4).
  ///
  /// [readInstallReferrer] returns the Android Play Install Referrer string (or
  /// null off-Android / on failure). [readClipboardCode] returns a code-shaped
  /// clipboard string for the iOS branch (or null). [prompt] asks the iOS user
  /// once. All three are injected so this method is unit-testable with no
  /// plugins; [init]-time callers pass the real implementations.
  ///
  /// Order: Android referrer first (unambiguous, no prompt). If it yields a
  /// code, run it and mark done. Otherwise, if the clipboard holds a code and
  /// the user says yes, run it. Either way the one-shot flag is set so this
  /// never runs again.
  Future<void> runDeferredCheckOnce({
    required Future<String?> Function() readInstallReferrer,
    required Future<String?> Function() readClipboardCode,
    required DeferredPrompt prompt,
    SharedPreferences? prefs,
  }) async {
    final store = prefs ?? await SharedPreferences.getInstance();
    if (store.getBool(kDeferredLinkCheckedKey) ?? false) return;
    // Mark BEFORE doing anything that could throw: the guarantee is "never
    // twice", so a partial run must still consume the one shot.
    await store.setBool(kDeferredLinkCheckedKey, true);

    // Android: Install Referrer (no prompt).
    try {
      final code = codeFromInstallReferrer(await readInstallReferrer());
      if (code != null) {
        PendingShareSearch.instance.offer(code);
        return;
      }
    } catch (_) {
      // fall through to the clipboard branch.
    }

    // iOS (and anywhere the referrer had nothing): clipboard one-shot prompt.
    try {
      final code = await readClipboardCode();
      if (code == null) return; // nothing code-shaped on the clipboard.
      final open = await prompt(code);
      if (open) PendingShareSearch.instance.offer(code);
    } catch (_) {
      // No clipboard / user cancelled — leave it; the shot is already spent.
    }
  }

  /// Real Android Install Referrer read, used by [init]-time callers. Returns
  /// null off-Android or when Play services are unavailable.
  static Future<String?> readPlayInstallReferrer() async {
    if (defaultTargetPlatform != TargetPlatform.android) return null;
    try {
      final details = await AndroidPlayInstallReferrer.installReferrer;
      return details.installReferrer;
    } catch (_) {
      return null;
    }
  }

  /// Real clipboard read, guarded by [Clipboard.hasStrings] first so that, with
  /// nothing on the clipboard, NO paste prompt appears (D671 §4). Returns a
  /// code-shaped string or null.
  static Future<String?> readClipboardShareCode() async {
    try {
      final has = await Clipboard.hasStrings();
      if (!has) return null;
      final data = await Clipboard.getData(Clipboard.kTextPlain);
      final text = data?.text;
      if (text == null) return null;
      return extractShareCode(text);
    } catch (_) {
      return null;
    }
  }

  void dispose() {
    _sub?.cancel();
    _sub = null;
  }
}
