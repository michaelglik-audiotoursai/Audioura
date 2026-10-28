// [LOCAL-794] Background translate-and-download, with a persistent progress row
// instead of an app-blocking modal spinner.
//
// Michael (iPhone TestFlight 83, 2026-10-27): Home → tour 465 → download in
// Russian "takes way too long … about 3 minutes, and the spinning wheel does
// not let me go anywhere in the app." The server needed ~17 s; ~150 s were
// spent inside the app, and after a successful download the spinner NEVER
// ended (a post-save step awaited a context that was gone, with no timeout).
//
// This manager runs the whole flow OFF any screen's BuildContext, driven by a
// global [TranslateDownloadController] (a ValueNotifier the size of one row,
// hosted by MainScreen OUTSIDE the tab stack like the bottom bar). While a job
// runs the user can switch tabs and keep using the app; a Cancel stops it. On
// completion a SnackBar ("Russian version ready — Play") is shown through the
// global messenger, and because every write of `saved_tours` goes through
// [SavedToursStore.save] (which bumps [SavedToursRefresh]), the Listen page
// updates WITHOUT a manual refresh (LOCAL-787).
//
// Every await here has a timeout, and EVERY exit path (success, error, timeout,
// cancel) calls [TranslateDownloadController.finish] exactly once, so the
// progress row can never be left up forever (the LOCAL-794 addenda hang).

import 'dart:async';

import 'package:flutter/material.dart';

import '../screens/debug_log_viewer_screen.dart';
import '../utils/organiser_audio_notices.dart' show translationFailureMessage;
import 'deep_link_service.dart' show PendingListenOpen;
import 'foreground_community_messages.dart'
    show communityScaffoldMessengerKey;
import 'tour_translation_helper.dart';

/// The phase a background translate-download job is in, for the progress row.
enum TranslateDownloadPhase {
  /// Pulling the English tour to the phone (only when English was selected).
  downloadingEnglish,

  /// Asking the server to translate + produce audio (the translate POST).
  translating,

  /// Downloading and saving each translated ZIP.
  savingTranslations,
}

/// One in-flight job's immutable snapshot, rendered by the progress banner.
@immutable
class TranslateDownloadJob {
  /// Server tour id being downloaded/translated.
  final int tourId;

  /// Best display name for the tour (from the tapped row), for messages.
  final String? tourName;

  /// The non-English language codes requested (e.g. ['ru']).
  final List<String> languages;

  /// The current phase, driving the row label.
  final TranslateDownloadPhase phase;

  const TranslateDownloadJob({
    required this.tourId,
    required this.tourName,
    required this.languages,
    required this.phase,
  });

  TranslateDownloadJob copyWith({TranslateDownloadPhase? phase}) =>
      TranslateDownloadJob(
        tourId: tourId,
        tourName: tourName,
        languages: languages,
        phase: phase ?? this.phase,
      );

  /// Full language names for the row ("Russian", or "Russian, French").
  String get languageNames => languages
      .map((l) => TourTranslationHelper.availableLanguages[l] ?? l.toUpperCase())
      .join(', ');

  /// The one-line label shown in the progress row for [phase].
  String get label {
    switch (phase) {
      case TranslateDownloadPhase.downloadingEnglish:
        return 'Downloading tour…';
      case TranslateDownloadPhase.translating:
        return 'Translating to $languageNames…';
      case TranslateDownloadPhase.savingTranslations:
        return 'Saving $languageNames version…';
    }
  }
}

/// A plain cancel flag the background flow polls between steps. A cancel never
/// kills an in-flight HTTP call mid-stream, but it stops the flow at the next
/// checkpoint and guarantees the progress row is cleared.
class TranslateDownloadCancelToken {
  bool _cancelled = false;
  bool get isCancelled => _cancelled;
  void cancel() => _cancelled = true;
}

/// The global, single-job progress controller. A [ValueNotifier] (no streams,
/// no plugins) exactly like [PendingListenOpen]/[SavedToursRefresh], so a
/// widget test can observe it and MainScreen can host one banner for the whole
/// app. `active == null` means no job (the row is hidden).
class TranslateDownloadController {
  TranslateDownloadController._();
  static final TranslateDownloadController instance =
      TranslateDownloadController._();

  final ValueNotifier<TranslateDownloadJob?> active =
      ValueNotifier<TranslateDownloadJob?>(null);

  TranslateDownloadCancelToken? _token;

  /// True while a job is running (used to refuse a second concurrent job).
  bool get isBusy => active.value != null;

  /// Show the row for a new job and return its cancel token.
  TranslateDownloadCancelToken start(TranslateDownloadJob job) {
    final token = TranslateDownloadCancelToken();
    _token = token;
    active.value = job;
    return token;
  }

  /// Move the running job to a new phase (updates the row label). No-op when no
  /// job is active.
  void setPhase(TranslateDownloadPhase phase) {
    final cur = active.value;
    if (cur == null) return;
    active.value = cur.copyWith(phase: phase);
  }

  /// Request cancellation of the running job. The flow clears the row itself at
  /// its next checkpoint; this does not hide the row directly so a half-written
  /// save can finish cleanly.
  void cancel() => _token?.cancel();

  /// Hide the row. Idempotent — safe to call from any exit path.
  void finish() {
    _token = null;
    active.value = null;
  }
}

/// Injectable completion sink so unit tests can assert what the user is told
/// without a widget tree. The default routes to the global SnackBar + Listen.
typedef TranslateDownloadNotify = void Function(
  String message, {
  int? tourId,
  String? language,
  bool isError,
});

/// Runs the background translate-download flow and drives the controller.
///
/// All of the heavy lifting lives in [TourTranslationHelper] and
/// [TourDownloadService] (the ONE download+save path). This class only
/// sequences those steps off the UI, puts timeouts on every await, and
/// guarantees the progress row is cleared on every exit path.
class TranslateDownloadManager {
  TranslateDownloadManager._();
  static final TranslateDownloadManager instance =
      TranslateDownloadManager._();

  /// Overall ceiling for one job. Even if an inner timeout is somehow bypassed,
  /// the whole job is abandoned (and the row cleared) after this.
  static const Duration jobTimeout = Duration(minutes: 6);

  /// The English-download + per-language ZIP GETs already time out at 120 s in
  /// the helper; the translate POST at 5 min. This is the ceiling for the
  /// resolve/attestation/save glue that previously had NONE.
  static const Duration stepTimeout = Duration(seconds: 20);

  /// The English GET timeout (matches the existing helper/home behaviour).
  static const Duration englishDownloadTimeout = Duration(seconds: 120);

  /// Download English (optional) + translate + save translations, in the
  /// background. [downloadEnglish] saves the English copy; it is skipped when
  /// English was not selected. [resolveParentEditTourId] resolves the parent
  /// edit id (its own http.get previously had no timeout — bounded here).
  /// [translate] runs [TourTranslationHelper.downloadTranslatedVersions] (which
  /// itself translates, downloads each ZIP with a 120 s timeout, and saves via
  /// SavedToursStore — so Listen refreshes). All three are injected so tests
  /// drive the sequence with fakes.
  ///
  /// Returns the list of language codes that failed (empty = all succeeded).
  /// Never throws; a thrown step is caught, reported, and the row cleared.
  Future<List<String>> run({
    required TranslateDownloadJob job,
    required bool downloadEnglish,
    required Future<void> Function() downloadEnglishStep,
    required Future<String> Function() resolveParentEditTourId,
    required Future<List<String>> Function(String parentEditTourId) translate,
    TranslateDownloadController? controller,
    TranslateDownloadNotify? notify,
  }) async {
    final ctrl = controller ?? TranslateDownloadController.instance;
    final tell = notify ?? _defaultNotify;

    if (ctrl.isBusy) {
      // One job at a time — never stack two progress rows or two translate
      // POSTs. Tell the user and leave the running job alone.
      tell('A download is already in progress — please wait for it to finish.',
          isError: true);
      return List<String>.from(job.languages);
    }

    final token = ctrl.start(job);
    try {
      return await _runInner(
        job: job,
        downloadEnglish: downloadEnglish,
        downloadEnglishStep: downloadEnglishStep,
        resolveParentEditTourId: resolveParentEditTourId,
        translate: translate,
        ctrl: ctrl,
        tell: tell,
        token: token,
      ).timeout(jobTimeout);
    } on TimeoutException {
      await DebugLogHelper.addDebugLog(
          'TDM: job timed out after ${jobTimeout.inSeconds}s (tour ${job.tourId})');
      tell('Download timed out — please try again.', isError: true);
      return List<String>.from(job.languages);
    } catch (e) {
      await DebugLogHelper.addDebugLog('TDM: job error (tour ${job.tourId}): $e');
      tell('Error downloading tour: $e', isError: true);
      return List<String>.from(job.languages);
    } finally {
      // The one guarantee: every exit path hides the row exactly once.
      ctrl.finish();
    }
  }

  Future<List<String>> _runInner({
    required TranslateDownloadJob job,
    required bool downloadEnglish,
    required Future<void> Function() downloadEnglishStep,
    required Future<String> Function() resolveParentEditTourId,
    required Future<List<String>> Function(String parentEditTourId) translate,
    required TranslateDownloadController ctrl,
    required TranslateDownloadNotify tell,
    required TranslateDownloadCancelToken token,
  }) async {
    if (token.isCancelled) return List<String>.from(job.languages);

    // 1) English copy (only when selected). 120 s like every other download.
    if (downloadEnglish) {
      ctrl.setPhase(TranslateDownloadPhase.downloadingEnglish);
      await DebugLogHelper.addDebugLog('TDM: download English (tour ${job.tourId})');
      await downloadEnglishStep().timeout(englishDownloadTimeout);
    }

    if (token.isCancelled) return List<String>.from(job.languages);

    // 2) Resolve the parent edit id. This http.get previously had NO timeout —
    // a cold tour-id-resolution start could stall the whole flow (a candidate
    // for the 2.5-min gap). Bounded here; a failure/timeout is non-fatal (the
    // translation still saves, just without the parent link).
    String parentEditTourId = '';
    try {
      parentEditTourId =
          await resolveParentEditTourId().timeout(stepTimeout);
    } on TimeoutException {
      await DebugLogHelper.addDebugLog(
          'TDM: resolve parent edit id timed out (${stepTimeout.inSeconds}s) — continuing');
    } catch (e) {
      await DebugLogHelper.addDebugLog('TDM: resolve parent edit id failed: $e — continuing');
    }

    if (token.isCancelled) return List<String>.from(job.languages);

    // No non-English languages → a plain English download, already done above.
    // Nothing to translate; announce and return.
    if (job.languages.isEmpty) {
      _announce(job: job, failures: const <String>[], tell: tell);
      return const <String>[];
    }

    // 3) Translate → download each ZIP → save. As soon as the translate
    // response says "completed" the helper starts the ZIP GET immediately (no
    // timer, no poll). The translate POST times out at 5 min and each ZIP GET
    // at 120 s inside the helper.
    ctrl.setPhase(TranslateDownloadPhase.translating);
    await DebugLogHelper.addDebugLog(
        'TDM: translate+download (tour ${job.tourId}) → ${job.languageNames}');
    final failures = await translate(parentEditTourId);
    // The save phase is the tail of the helper; reflect it for any onlooker.
    ctrl.setPhase(TranslateDownloadPhase.savingTranslations);

    _announce(job: job, failures: failures, tell: tell);
    return failures;
  }

  /// Build and route the completion message. English-only → "Tour downloaded";
  /// all languages ok → the "ready — Play" line with a View/Play action; some
  /// failed → the shared failure wording; the broadcast-tour refusal → its own
  /// message.
  void _announce({
    required TranslateDownloadJob job,
    required List<String> failures,
    required TranslateDownloadNotify tell,
  }) {
    if (job.languages.isEmpty) {
      tell('Tour downloaded — Play',
          tourId: job.tourId, language: 'en', isError: false);
      return;
    }
    if (failures.isEmpty) {
      final lang = job.languages.isNotEmpty ? job.languages.first : null;
      final name = job.languageNames;
      tell('$name version ready — Play',
          tourId: job.tourId, language: lang, isError: false);
      return;
    }
    final failedNames = failures
        .map((l) => TourTranslationHelper.availableLanguages[l] ?? l)
        .join(', ');
    final notOffered = TourTranslationHelper.lastTranslationNotOffered;
    final msg = translationFailureMessage(
      translationNotOffered: notOffered,
      failedLanguageNames: failedNames,
    );
    tell(msg, isError: true);
  }

  /// Default sink: show a SnackBar through the global messenger (works from any
  /// tab/context, even after the originating screen is gone), with a Play/View
  /// action on success that opens the tour on Listen.
  static void _defaultNotify(
    String message, {
    int? tourId,
    String? language,
    bool isError = false,
  }) {
    final messenger = communityScaffoldMessengerKey.currentState;
    if (messenger == null) return;
    try {
      messenger.showSnackBar(
        SnackBar(
          content: Text(message),
          duration: Duration(seconds: isError ? 8 : 6),
          action: (!isError && tourId != null)
              ? SnackBarAction(
                  label: 'Play',
                  onPressed: () => PendingListenOpen.instance
                      .offer(tourId.toString(), language),
                )
              : null,
        ),
      );
    } catch (_) {
      // Never let a messaging failure crash the background job.
    }
  }
}
