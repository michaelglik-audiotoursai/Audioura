import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:archive/archive.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../config/endpoints.dart';
import '../screens/debug_log_viewer_screen.dart';
import 'pending_tour_requests_store.dart';
import 'saved_tours_refresh.dart';
import 'saved_tours_store.dart';

/// [LOCAL-841] What to do with a pending request after looking at the server.
enum ResumeAction {
  /// Server says completed → download, save, show on Listen.
  download,

  /// Server says failed → drop it and tell the user why.
  removeFailed,

  /// Older than the stale cutoff and the server does not know it → drop quietly.
  removeStale,

  /// Still processing (or a transient blip) → leave it for the next pass.
  keepWaiting,
}

/// [LOCAL-841] PURE decision: given a status lookup outcome and the request's
/// age, decide what the handler should do. Kept free of IO so the completed /
/// failed / stale / waiting policy is unit-testable without a server or disk.
///
///   * [httpOk] — true when GET /status returned 200 with a body.
///   * [serverStatus] — the body's `status` ('completed' | 'error' | 'processing'
///     | …) when [httpOk]; ignored otherwise.
///   * [notFound] — true when the server returned 404 (job unknown to it).
///   * [age] — how long since the request was submitted.
///   * [staleCutoff] — the age beyond which an unknown/unresolved request is
///     dropped (LOCAL-841: 2 hours).
class ResumeDecision {
  const ResumeDecision._();

  static ResumeAction decide({
    required bool httpOk,
    String? serverStatus,
    required bool notFound,
    required Duration age,
    Duration staleCutoff = PendingTourResumeHandler.staleCutoff,
  }) {
    if (httpOk) {
      final s = (serverStatus ?? '').toLowerCase();
      if (s == 'completed') return ResumeAction.download;
      if (s == 'error' || s == 'failed') return ResumeAction.removeFailed;
      // processing / queued / anything else → still cooking.
      return age >= staleCutoff
          ? ResumeAction.removeStale
          : ResumeAction.keepWaiting;
    }
    // No usable answer from the server.
    //  * 404 and old  → the job is gone and we have waited long enough: drop.
    //  * 404 but young → the durable row may not be visible yet; keep briefly.
    //  * other errors (network/5xx) → keep unless we are past the cutoff.
    if (age >= staleCutoff) return ResumeAction.removeStale;
    return ResumeAction.keepWaiting;
  }
}

/// Outcome of a single resume pass, returned for logging/tests.
class ResumeResult {
  const ResumeResult({
    this.downloaded = 0,
    this.failed = 0,
    this.stale = 0,
    this.kept = 0,
  });
  final int downloaded;
  final int failed;
  final int stale;
  final int kept;

  ResumeResult copyWith({int? downloaded, int? failed, int? stale, int? kept}) =>
      ResumeResult(
        downloaded: downloaded ?? this.downloaded,
        failed: failed ?? this.failed,
        stale: stale ?? this.stale,
        kept: kept ?? this.kept,
      );
}

/// [LOCAL-841] Resumes pending tour downloads after the app was suspended.
///
/// On app start AND on `AppLifecycleState.resumed` (both wired through
/// [AppSyncCoordinator]), for every [PendingTourRequest]:
///   * ask the orchestrator `GET /status/<job_id>` (durable after a restart,
///     LOCAL-821);
///   * completed → download `GET /download/<final_tour_id|job_id>`, extract to
///     `tours/<id>`, add to `saved_tours`, bump the Listen page, and surface a
///     "Your tour is ready" message;
///   * error → remove it and show the server's reason;
///   * older than 2 h and still unknown/unresolved → remove quietly.
///
/// It NEVER blocks the UI (LOCAL-794's rule): it runs in the background off a
/// lifecycle trigger, puts nothing up as a spinner gate, and swallows its own
/// errors. Overlapping passes are coalesced by an in-flight guard.
///
/// IO is injected so the whole thing is unit-testable: [httpGet] for the two
/// GETs, [docsDirPath] for the tours directory, [now] for the clock, and
/// [onReady] for the "ready" surface.
class PendingTourResumeHandler {
  PendingTourResumeHandler._();
  static final PendingTourResumeHandler instance = PendingTourResumeHandler._();

  /// LOCAL-841: drop an unresolved/unknown pending request after this long.
  static const Duration staleCutoff = Duration(hours: 2);

  bool _inFlight = false;

  /// Run one resume pass. Safe to call from app start and from every resume;
  /// an overlapping call while one is already running is a no-op. Never throws.
  Future<ResumeResult> run({
    SharedPreferences? prefs,
    Future<http.Response> Function(Uri url, {Map<String, String>? headers})? httpGet,
    String? docsDirPath,
    DateTime Function()? now,
    void Function(PendingTourRequest request)? onReady,
    void Function(PendingTourRequest request, String reason)? onFailed,
  }) async {
    if (_inFlight) return const ResumeResult();
    _inFlight = true;
    try {
      return await _runOnce(
        prefs: prefs,
        httpGet: httpGet,
        docsDirPath: docsDirPath,
        now: now,
        onReady: onReady,
        onFailed: onFailed,
      );
    } catch (e) {
      await DebugLogHelper.addDebugLog('RESUME: pass error: $e');
      return const ResumeResult();
    } finally {
      _inFlight = false;
    }
  }

  Future<ResumeResult> _runOnce({
    SharedPreferences? prefs,
    Future<http.Response> Function(Uri url, {Map<String, String>? headers})? httpGet,
    String? docsDirPath,
    DateTime Function()? now,
    void Function(PendingTourRequest request)? onReady,
    void Function(PendingTourRequest request, String reason)? onFailed,
  }) async {
    final sp = prefs ?? await SharedPreferences.getInstance();
    // A background isolate may have written saved_tours / pending list — see
    // the freshest copy.
    try {
      await sp.reload();
    } catch (_) {}

    final pending = await PendingTourRequestsStore.load(sp);
    if (pending.isEmpty) return const ResumeResult();

    final clock = now ?? () => DateTime.now();
    final get = httpGet ?? _defaultGet;
    final docs = docsDirPath ?? (await getApplicationDocumentsDirectory()).path;

    var result = const ResumeResult();

    for (final req in pending) {
      bool httpOk = false;
      bool notFound = false;
      Map<String, dynamic>? status;
      try {
        final resp = await get(
          await Endpoints.url(Service.orchestrator, '/status/${req.jobId}'),
          headers: await Endpoints.apiHeaders(Service.orchestrator),
        );
        if (resp.statusCode == 200) {
          final decoded = jsonDecode(resp.body);
          if (decoded is Map<String, dynamic>) {
            status = decoded;
            httpOk = true;
          }
        } else if (resp.statusCode == 404) {
          notFound = true;
        }
      } catch (e) {
        await DebugLogHelper.addDebugLog('RESUME: status check ${req.jobId}: $e');
      }

      final action = ResumeDecision.decide(
        httpOk: httpOk,
        serverStatus: status?['status'] as String?,
        notFound: notFound,
        age: req.ageAt(clock()),
      );

      switch (action) {
        case ResumeAction.download:
          final ok = await _downloadCompleted(sp, docs, get, req, status!);
          if (ok) {
            await PendingTourRequestsStore.remove(sp, req.jobId);
            SavedToursRefresh.instance.bump();
            _surfaceReady(req, onReady);
            result = result.copyWith(downloaded: result.downloaded + 1);
          } else {
            // Download failed this pass — keep it for a retry next resume.
            result = result.copyWith(kept: result.kept + 1);
          }
          break;
        case ResumeAction.removeFailed:
          await PendingTourRequestsStore.remove(sp, req.jobId);
          final reason = (status?['message'] ?? status?['error'] ?? 'Generation failed')
              .toString();
          await DebugLogHelper.addDebugLog('RESUME: ${req.jobId} failed: $reason');
          if (onFailed != null) {
            onFailed(req, reason);
          }
          result = result.copyWith(failed: result.failed + 1);
          break;
        case ResumeAction.removeStale:
          await PendingTourRequestsStore.remove(sp, req.jobId);
          await DebugLogHelper.addDebugLog(
              'RESUME: ${req.jobId} dropped (stale, age ${req.ageAt(clock()).inMinutes}m)');
          result = result.copyWith(stale: result.stale + 1);
          break;
        case ResumeAction.keepWaiting:
          result = result.copyWith(kept: result.kept + 1);
          break;
      }
    }

    await DebugLogHelper.addDebugLog(
        'RESUME: pass done — downloaded=${result.downloaded} failed=${result.failed} '
        'stale=${result.stale} kept=${result.kept}');
    return result;
  }

  /// Surface the "your tour is ready" message. Tests pass [onReady]; otherwise
  /// the injectable [readyRouter] (wired in main() to the in-app/system router)
  /// runs. Never throws.
  void _surfaceReady(
    PendingTourRequest req,
    void Function(PendingTourRequest request)? onReady,
  ) {
    try {
      (onReady ?? readyRouter)(req);
    } catch (_) {}
  }

  static Future<http.Response> _defaultGet(Uri url,
          {Map<String, String>? headers}) =>
      http.get(url, headers: headers);

  /// Download a completed job, extract it, and add it to saved_tours, matching
  /// the shape the foreground path writes (id = final_tour_id when present, else
  /// job_id; directory tours/<id>). Returns true on success.
  Future<bool> _downloadCompleted(
    SharedPreferences prefs,
    String docsDirPath,
    Future<http.Response> Function(Uri url, {Map<String, String>? headers}) get,
    PendingTourRequest req,
    Map<String, dynamic> status,
  ) async {
    try {
      // The server downloads by final_tour_id when it has assigned one (the
      // foreground path's rule); fall back to the job id otherwise.
      final finalTourId = status['final_tour_id'];
      final downloadId =
          (finalTourId != null && finalTourId.toString().isNotEmpty)
              ? finalTourId.toString()
              : req.jobId;

      final resp = await get(
        await Endpoints.url(Service.orchestrator, '/download/$downloadId'),
        headers: await Endpoints.apiHeaders(Service.orchestrator),
      );
      if (resp.statusCode != 200) {
        await DebugLogHelper.addDebugLog(
            'RESUME: download $downloadId HTTP ${resp.statusCode}');
        return false;
      }

      final toursDir = Directory('$docsDirPath/tours');
      if (!await toursDir.exists()) {
        await toursDir.create(recursive: true);
      }

      final extractPath = '${toursDir.path}/$downloadId';
      final extractDir = Directory(extractPath);
      if (await extractDir.exists()) {
        await extractDir.delete(recursive: true);
      }
      await extractDir.create(recursive: true);

      final archive = ZipDecoder().decodeBytes(resp.bodyBytes);
      for (final file in archive) {
        if (file.isFile) {
          final data = file.content as List<int>;
          final extractedFile = File('${extractDir.path}/${file.name}');
          await extractedFile.create(recursive: true);
          await extractedFile.writeAsBytes(data);
        }
      }

      // Coordinates, if the server reported them.
      double? lat;
      double? lng;
      final coords = status['coordinates'];
      if (coords is List && coords.length >= 2) {
        lat = (coords[0] as num?)?.toDouble();
        lng = (coords[1] as num?)?.toDouble();
      }

      final title = (status['tour_title'] is String &&
              (status['tour_title'] as String).isNotEmpty)
          ? status['tour_title'] as String
          : (req.title.isNotEmpty ? req.title : 'Your tour');

      final tours = prefs.getStringList(SavedToursStore.key) ?? <String>[];
      // Idempotency: if this tour id is already saved (an earlier pass or the
      // foreground path beat us to it), do not add a duplicate — just succeed.
      final alreadySaved = tours.any((t) {
        try {
          final m = jsonDecode(t);
          return m is Map && (m['tour_id'] == downloadId || m['id'] == downloadId);
        } catch (_) {
          return false;
        }
      });
      if (!alreadySaved) {
        tours.add(jsonEncode({
          'tour_id': downloadId,
          'id': downloadId,
          'title': title,
          'original_request': req.title,
          'path': extractPath,
          'created': DateTime.now().toIso8601String(),
          'stops': req.stopCount ?? '10',
          'editable': false,
          'is_translation': false,
          'lat': lat,
          'lng': lng,
          // Mark provenance so Listen can tell it came from the resume path.
          'resumed': true,
        }));
        await SavedToursStore.save(prefs, tours, bumpRefresh: false);
      }

      await DebugLogHelper.addDebugLog(
          'RESUME: downloaded + saved "$title" (id $downloadId, job ${req.jobId})');
      return true;
    } catch (e) {
      await DebugLogHelper.addDebugLog('RESUME: download error ${req.jobId}: $e');
      return false;
    }
  }

  /// Injectable for tests; defaults to the real router set in [main].
  void Function(PendingTourRequest request) readyRouter = (req) {};
}
