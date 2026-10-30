import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// [LOCAL-841] One in-flight tour-generation request the app is waiting on.
///
/// Michael's coffee tour (503, "coffee… Vườn Thiên Giới", Vietnam) was generated
/// and stored on the cloud, but the app never downloaded it: he switched away
/// and iOS suspended the app while the Generate screen was polling, so the in-
/// screen poll loop died (`mounted == false`) and the job id was lost. Nothing
/// resumed it. GCloud_Storied had to hand him the files.
///
/// The foreground Generate path never persisted its job. This record is written
/// the MOMENT `/generate-complete-tour` returns a `job_id`, so a suspend/kill
/// can no longer lose it: a resume handler reads these entries on app start and
/// on resume and finishes the download.
///
/// Immutable value object; (de)serialised as a JSON map for the SharedPreferences
/// string list. Unknown/missing fields decode to safe defaults so an older entry
/// written by a previous build still loads.
class PendingTourRequest {
  const PendingTourRequest({
    required this.jobId,
    required this.title,
    required this.startedAt,
    this.clientRequestId,
    this.languages = const [],
    this.stopCount,
  });

  /// The orchestrator job id (`/status/<job_id>`, `/download/<job_id>`). The
  /// durable key that survives an app kill and even an orchestrator restart
  /// (LOCAL-821 orchestrator_jobs store).
  final String jobId;

  /// The user-facing request text (e.g. the location), shown in messages.
  final String title;

  /// When the POST returned, in UTC. Used for the stale cutoff.
  final DateTime startedAt;

  /// [LOCAL-830] The idempotency key sent with the request. Kept for
  /// correlation/debugging; the server maps it to a job id only briefly, so the
  /// durable handle is [jobId].
  final String? clientRequestId;

  /// Requested listening languages (for parity with the foreground path). May
  /// be empty (English-only / unspecified).
  final List<String> languages;

  /// Requested stop count, as the original string (the foreground save stores a
  /// string). Null when unknown.
  final String? stopCount;

  Map<String, dynamic> toJson() => {
        'jobId': jobId,
        'title': title,
        'startedAt': startedAt.toUtc().toIso8601String(),
        if (clientRequestId != null) 'clientRequestId': clientRequestId,
        if (languages.isNotEmpty) 'languages': languages,
        if (stopCount != null) 'stopCount': stopCount,
      };

  static PendingTourRequest? fromJson(Map<String, dynamic> json) {
    final jobId = json['jobId'];
    if (jobId is! String || jobId.isEmpty) return null;
    final startedRaw = json['startedAt'];
    final startedAt = startedRaw is String
        ? (DateTime.tryParse(startedRaw)?.toUtc() ?? DateTime.now().toUtc())
        : DateTime.now().toUtc();
    final langsRaw = json['languages'];
    final languages = langsRaw is List
        ? langsRaw.whereType<String>().toList(growable: false)
        : const <String>[];
    return PendingTourRequest(
      jobId: jobId,
      title: json['title'] is String ? json['title'] as String : '',
      startedAt: startedAt,
      clientRequestId:
          json['clientRequestId'] is String ? json['clientRequestId'] as String : null,
      languages: languages,
      stopCount: json['stopCount'] is String ? json['stopCount'] as String : null,
    );
  }

  /// Age of this request relative to [now].
  Duration ageAt(DateTime now) => now.toUtc().difference(startedAt);
}

/// [LOCAL-841] Durable store of in-flight tour-generation requests.
///
/// Backed by a single SharedPreferences string list under [key]. This is
/// deliberately SEPARATE from the legacy `pending_background_tours` list used by
/// the explicit "Generate in Background" path (background_service.dart /
/// background_tour_monitor.dart): that list drives the Generate tab's own
/// pending UI and a 15-minute stale rule, while this one persists EVERY
/// foreground generation and is swept by [PendingTourResumeHandler] with the
/// 2-hour rule LOCAL-841 asks for. Keeping them apart means the resume fix never
/// disturbs the existing background flow.
///
/// All methods re-read the list before writing so a concurrent writer is not
/// clobbered within the main isolate.
class PendingTourRequestsStore {
  PendingTourRequestsStore._();

  /// The SharedPreferences key holding the pending-requests list.
  static const String key = 'pending_tour_requests';

  /// Read all pending requests. Malformed entries are skipped (never throws).
  static Future<List<PendingTourRequest>> load(SharedPreferences prefs) async {
    final raw = prefs.getStringList(key) ?? const <String>[];
    final out = <PendingTourRequest>[];
    for (final s in raw) {
      try {
        final decoded = jsonDecode(s);
        if (decoded is Map<String, dynamic>) {
          final req = PendingTourRequest.fromJson(decoded);
          if (req != null) out.add(req);
        }
      } catch (_) {
        // Skip a corrupt entry rather than losing the whole list.
      }
    }
    return out;
  }

  /// Persist [requests], replacing the stored list.
  static Future<void> saveAll(
    SharedPreferences prefs,
    List<PendingTourRequest> requests,
  ) async {
    await prefs.setStringList(
      key,
      requests.map((r) => jsonEncode(r.toJson())).toList(growable: false),
    );
  }

  /// Add [request] if its [PendingTourRequest.jobId] is not already present
  /// (idempotent: a retried submission that reused the job id does not double it).
  static Future<void> add(
    SharedPreferences prefs,
    PendingTourRequest request,
  ) async {
    final current = await load(prefs);
    if (current.any((r) => r.jobId == request.jobId)) return;
    current.add(request);
    await saveAll(prefs, current);
  }

  /// Remove the entry whose job id is [jobId]. No-op if absent.
  static Future<void> remove(SharedPreferences prefs, String jobId) async {
    final current = await load(prefs);
    final next = current.where((r) => r.jobId != jobId).toList(growable: false);
    if (next.length != current.length) {
      await saveAll(prefs, next);
    }
  }
}
