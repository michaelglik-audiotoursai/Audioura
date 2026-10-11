import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../config/endpoints.dart';

/// A single durable outbox item: one offline-recorded fact waiting to reach the
/// server. Identified by a client-generated UUID so the server can accept a
/// batch idempotently (a retry of an already-applied item is a no-op).
class OutboxItem {
  /// Client-generated unique id. The server dedupes on this, so re-sending the
  /// same item after a dropped connection never double-counts.
  final String clientUuid;

  /// One of: `listened`, `rating`, `review`, `thumb`.
  final String type;

  /// When the fact happened on the device (ISO-8601 UTC). Carried to the server
  /// so a listen recorded underground keeps its real time, and used both for
  /// 90-day expiry and server-side future-skew rejection.
  final String createdAt;

  /// Type-specific fields (user_id, tour_id, stop_index, rating, …).
  final Map<String, dynamic> payload;

  /// Local retry counter (drives exponential backoff; never sent to the server).
  int retries;

  OutboxItem({
    required this.clientUuid,
    required this.type,
    required this.createdAt,
    required this.payload,
    this.retries = 0,
  });

  Map<String, dynamic> toJson() => {
        'client_uuid': clientUuid,
        'type': type,
        'created_at': createdAt,
        'payload': payload,
        'retries': retries,
      };

  factory OutboxItem.fromJson(Map<String, dynamic> json) => OutboxItem(
        clientUuid: json['client_uuid'] as String,
        type: json['type'] as String,
        createdAt: json['created_at'] as String,
        payload: (json['payload'] as Map).cast<String, dynamic>(),
        retries: (json['retries'] as num?)?.toInt() ?? 0,
      );

  /// The wire form sent inside the `/sync` batch (no local-only `retries`).
  Map<String, dynamic> toWire() => {
        'client_uuid': clientUuid,
        'type': type,
        'created_at': createdAt,
        ...payload,
      };
}

/// Offline-first outbox for listened events, tour ratings, text reviews and
/// per-stop thumbs (LOCAL-670C).
///
/// Michael (2026-10-10): "Audioura must do some storage and verification
/// locally, and send info to a server only that was valid and when it had
/// connection." Every mutation that must reach the server is written here FIRST
/// (durable, survives restart and app update because it lives in the same
/// shared storage as downloaded-tour state), then flushed opportunistically.
///
/// Sync policy (per the ticket):
///   * Triggered on app start, on resume, and on a connectivity change
///     (wired by [AppSyncCoordinator]), plus an internal exponential-backoff
///     retry while items remain.
///   * Sent as ONE batch to `POST /sync {user_id, items:[…]}`, idempotent on
///     the client UUID.
///   * Ordered: `listened` items before `rating` items, so an offline
///     listen-then-rate pair is accepted together (the server gate counts the
///     listens in the same batch).
///   * An item is removed only after the server ACCEPTS or explicitly REJECTS
///     it (a 4xx-style per-item verdict → dropped and logged locally). A 5xx,
///     network error or no connection keeps every item for a later retry.
///   * An item older than 90 days is dropped with a log line.
class OutboxService {
  OutboxService._();
  static final OutboxService instance = OutboxService._();

  static const String _storageKey = 'outbox_v1';

  /// Items older than this are dropped (with a log line) rather than retried
  /// forever.
  static const Duration maxItemAge = Duration(days: 90);

  /// Backoff schedule base; the nth consecutive failed flush waits
  /// min(base * 2^n, [_maxBackoff]).
  static const Duration _baseBackoff = Duration(seconds: 5);
  static const Duration _maxBackoff = Duration(minutes: 15);

  Timer? _retryTimer;
  bool _flushing = false;
  int _consecutiveFailures = 0;
  bool _testMode = false;

  /// Collected drop/accept log lines (also printed). Exposed for tests and
  /// diagnostics; the ticket requires an invalid item be "dropped and logged".
  final List<String> log = <String>[];

  /// Disable the internal retry timer (tests drive [flush] directly).
  void enableTestMode() {
    _testMode = true;
    _retryTimer?.cancel();
    _retryTimer = null;
  }

  // ─── Enqueue API (one method per fact kind) ─────────────────────────────────

  Future<void> enqueueListened({
    required String userId,
    required String tourId,
    required int stopIndex,
    DateTime? createdAt,
  }) async {
    await _enqueue(OutboxItem(
      clientUuid: _uuid(),
      type: 'listened',
      createdAt: _stamp(createdAt),
      payload: {'user_id': userId, 'tour_id': tourId, 'stop_index': stopIndex},
    ));
  }

  Future<void> enqueueRating({
    required String userId,
    required String tourId,
    required int rating,
    DateTime? createdAt,
  }) async {
    await _enqueue(OutboxItem(
      clientUuid: _uuid(),
      type: 'rating',
      createdAt: _stamp(createdAt),
      payload: {'user_id': userId, 'tour_id': tourId, 'rating': rating},
    ));
  }

  Future<void> enqueueReview({
    required String userId,
    required String tourId,
    required String review,
    DateTime? createdAt,
  }) async {
    await _enqueue(OutboxItem(
      clientUuid: _uuid(),
      type: 'review',
      createdAt: _stamp(createdAt),
      payload: {'user_id': userId, 'tour_id': tourId, 'review': review},
    ));
  }

  Future<void> enqueueThumb({
    required String userId,
    required String tourId,
    required int stopIndex,
    required int swipe,
    Map<String, dynamic>? extra,
    DateTime? createdAt,
  }) async {
    await _enqueue(OutboxItem(
      clientUuid: _uuid(),
      type: 'thumb',
      createdAt: _stamp(createdAt),
      payload: {
        'user_id': userId,
        'tour_id': tourId,
        'stop_index': stopIndex,
        'swipe': swipe,
        if (extra != null) ...extra,
      },
    ));
  }

  // ─── Diagnostics ────────────────────────────────────────────────────────────

  Future<int> get pendingCount async => (await _load()).length;
  Future<List<OutboxItem>> pendingItems() async => _load();

  // ─── Flush ──────────────────────────────────────────────────────────────────

  /// Attempt to flush all pending items as one ordered batch. Safe to call
  /// often (re-entry guarded). Returns true if, after this attempt, the outbox
  /// is empty.
  Future<bool> flush() async {
    if (_flushing) return false;
    _flushing = true;
    try {
      var items = await _load();
      items = _dropExpired(items);

      if (items.isEmpty) {
        await _save(items);
        _consecutiveFailures = 0;
        _retryTimer?.cancel();
        return true;
      }

      final ordered = _ordered(items);
      final userId = _batchUserId(ordered);

      final result = await _postBatch(userId, ordered);
      if (result == null) {
        // No connection / network error / 5xx → keep everything, back off.
        await _save(items);
        _consecutiveFailures += 1;
        _scheduleRetry();
        return false;
      }

      // The server returned a per-item verdict. Keep only items it told us to
      // retry; remove accepted ones and drop+log invalid (4xx) ones.
      final remaining = <OutboxItem>[];
      for (final item in ordered) {
        final verdict = result[item.clientUuid];
        if (verdict == _ItemVerdict.accepted) {
          continue; // done
        } else if (verdict == _ItemVerdict.invalid) {
          _logLine(
              'DROP invalid ${item.type} uuid=${item.clientUuid} payload=${jsonEncode(item.payload)}');
        } else {
          // retry (explicit) or missing from the response → keep.
          item.retries += 1;
          remaining.add(item);
        }
      }

      await _save(remaining);
      if (remaining.isEmpty) {
        _consecutiveFailures = 0;
        _retryTimer?.cancel();
        return true;
      }
      _consecutiveFailures += 1;
      _scheduleRetry();
      return false;
    } finally {
      _flushing = false;
    }
  }

  // ─── Internals ───────────────────────────────────────────────────────────────

  Future<void> _enqueue(OutboxItem item) async {
    final items = await _load();
    items.add(item);
    await _save(items);
    if (!_testMode) {
      unawaited(flush());
    }
  }

  /// Order a batch so listens precede the ratings that depend on them, then by
  /// creation time within each kind. `listened` (0) < `thumb`/`review` (1) <
  /// `rating` (2) guarantees the server gate sees this batch's listens before
  /// it evaluates the rating.
  List<OutboxItem> _ordered(List<OutboxItem> items) {
    int rank(String type) {
      switch (type) {
        case 'listened':
          return 0;
        case 'rating':
          return 2;
        default:
          return 1;
      }
    }

    final sorted = [...items];
    sorted.sort((a, b) {
      final r = rank(a.type).compareTo(rank(b.type));
      if (r != 0) return r;
      return a.createdAt.compareTo(b.createdAt);
    });
    return sorted;
  }

  List<OutboxItem> _dropExpired(List<OutboxItem> items) {
    final now = DateTime.now().toUtc();
    final kept = <OutboxItem>[];
    var changed = false;
    for (final item in items) {
      final created = DateTime.tryParse(item.createdAt)?.toUtc();
      if (created != null && now.difference(created) > maxItemAge) {
        _logLine(
            'DROP expired(${maxItemAge.inDays}d) ${item.type} uuid=${item.clientUuid} created=${item.createdAt}');
        changed = true;
        continue;
      }
      kept.add(item);
    }
    if (changed) {
      // Caller saves; nothing else to do here.
    }
    return kept;
  }

  /// The user_id for the batch. All items for a device share one user; we read
  /// it from the first item that carries one.
  String _batchUserId(List<OutboxItem> items) {
    for (final item in items) {
      final u = item.payload['user_id'];
      if (u is String && u.isNotEmpty) return u;
    }
    return 'unknown';
  }

  /// POST the batch. Returns a per-item verdict map on a 2xx, or null on no
  /// connection / network error / 5xx (caller keeps everything and backs off).
  Future<Map<String, _ItemVerdict>?> _postBatch(
    String userId,
    List<OutboxItem> items,
  ) async {
    final body = {
      'user_id': userId,
      'items': items.map((i) => i.toWire()).toList(),
    };
    try {
      final response = await Endpoints.post(
        Service.orchestrator,
        '/sync',
        body: body,
        timeout: const Duration(seconds: 20),
      );
      if (response.statusCode >= 200 && response.statusCode < 300) {
        return _parseVerdicts(response.body, items);
      }
      if (response.statusCode >= 400 && response.statusCode < 500) {
        // A 4xx on the WHOLE batch (e.g. malformed) — without per-item detail
        // we cannot tell which item is bad, so keep and back off rather than
        // silently losing good items. Per-item invalids come back inside a 2xx.
        _logLine('batch 4xx ${response.statusCode}: ${response.body}');
        return null;
      }
      return null; // 5xx → keep + backoff
    } on SocketException catch (_) {
      return null; // offline
    } on TimeoutException catch (_) {
      return null;
    } on http.ClientException catch (_) {
      return null;
    } catch (_) {
      return null;
    }
  }

  Map<String, _ItemVerdict> _parseVerdicts(
    String responseBody,
    List<OutboxItem> items,
  ) {
    final verdicts = <String, _ItemVerdict>{};
    try {
      final decoded = jsonDecode(responseBody);
      final results = (decoded is Map) ? decoded['results'] : null;
      if (results is List) {
        for (final r in results) {
          if (r is Map) {
            final uuid = r['client_uuid']?.toString();
            final status = r['status']?.toString();
            if (uuid == null) continue;
            if (status == 'accepted' || status == 'ok' || status == 'duplicate') {
              verdicts[uuid] = _ItemVerdict.accepted;
            } else if (status == 'invalid' || status == 'rejected') {
              verdicts[uuid] = _ItemVerdict.invalid;
            } else {
              verdicts[uuid] = _ItemVerdict.retry;
            }
          }
        }
      }
    } catch (_) {
      // Unparseable 2xx body: treat as "accepted all" would risk data loss on a
      // partial failure, so treat as retry-all (safe — idempotent re-send).
      for (final item in items) {
        verdicts[item.clientUuid] = _ItemVerdict.retry;
      }
    }
    return verdicts;
  }

  void _scheduleRetry() {
    if (_testMode) return;
    _retryTimer?.cancel();
    final exp = math.min(_consecutiveFailures, 20);
    final millis = math.min(
      _baseBackoff.inMilliseconds * math.pow(2, exp).toInt(),
      _maxBackoff.inMilliseconds,
    );
    _retryTimer = Timer(Duration(milliseconds: millis), () => unawaited(flush()));
  }

  Future<List<OutboxItem>> _load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_storageKey);
    if (raw == null || raw.isEmpty) return <OutboxItem>[];
    try {
      final list = jsonDecode(raw) as List<dynamic>;
      return list
          .whereType<Map>()
          .map((m) => OutboxItem.fromJson(m.cast<String, dynamic>()))
          .toList();
    } catch (_) {
      return <OutboxItem>[];
    }
  }

  Future<void> _save(List<OutboxItem> items) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
        _storageKey, jsonEncode(items.map((i) => i.toJson()).toList()));
  }

  void _logLine(String line) {
    log.add(line);
    // ignore: avoid_print
    print('[OUTBOX] $line');
  }

  static String _stamp(DateTime? at) =>
      (at ?? DateTime.now()).toUtc().toIso8601String();

  /// RFC-4122 v4 UUID using the platform RNG (no extra dependency).
  static String _uuid() {
    final rnd = math.Random.secure();
    final bytes = List<int>.generate(16, (_) => rnd.nextInt(256));
    bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
    bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant 10
    String hex(int b) => b.toRadixString(16).padLeft(2, '0');
    final h = bytes.map(hex).toList();
    return '${h[0]}${h[1]}${h[2]}${h[3]}-${h[4]}${h[5]}-${h[6]}${h[7]}-'
        '${h[8]}${h[9]}-${h[10]}${h[11]}${h[12]}${h[13]}${h[14]}${h[15]}';
  }

  /// Testing hook: clear all persisted outbox state and in-memory counters.
  Future<void> resetForTest() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_storageKey);
    _consecutiveFailures = 0;
    _flushing = false;
    log.clear();
    _retryTimer?.cancel();
    _retryTimer = null;
  }
}

enum _ItemVerdict { accepted, invalid, retry }
