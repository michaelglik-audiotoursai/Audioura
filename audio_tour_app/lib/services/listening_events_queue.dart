// [LOCAL-908] Offline queue for `POST /listening-events` (LOCAL-907).
//
// Events: start | skip (with at_sec) | finish | choose. The queue
//   * persists every event BEFORE any network use (SharedPreferences), so a
//     killed app or a tunnel does not lose it;
//   * [enqueue] returns as soon as the event is stored — it never awaits the
//     network, so playback is never blocked (the flush is fire-and-forget);
//   * flushes FIFO; the first event that cannot be delivered stops the flush
//     and a retry is scheduled with exponential backoff (5 s … 15 min);
//   * drops an event only when the server definitively refuses it (400, or a
//     404 that is the service's own "segment not found") or it is older than
//     [maxAge]; a network error, 5xx, 401/408/429, or a missing route keeps it.
//
// The server (907) does not dedupe, so an event whose response was lost may be
// delivered twice. The weight effect of one duplicate is small (±1 clamp ±5).
library listening_events_queue;

import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:shared_preferences/shared_preferences.dart';

import '../config/endpoints.dart';

const List<String> kListeningActions = ['start', 'skip', 'finish', 'choose'];

class ListeningEvent {
  final String clientUuid;
  final String userId;
  final String tourId;
  final int segmentId;
  final String action;
  final double atSec;
  final String createdAt; // ISO-8601 UTC, when it happened on the device
  int retries;

  ListeningEvent({
    required this.clientUuid,
    required this.userId,
    required this.tourId,
    required this.segmentId,
    required this.action,
    required this.atSec,
    required this.createdAt,
    this.retries = 0,
  });

  /// The body 907's `POST /listening-events` accepts.
  Map<String, dynamic> toWire() => {
        'user_id': userId,
        'tour_id': tourId,
        'segment_id': segmentId,
        'action': action,
        'at_sec': atSec,
      };

  Map<String, dynamic> toJson() => {
        'client_uuid': clientUuid,
        ...toWire(),
        'created_at': createdAt,
        'retries': retries,
      };

  static ListeningEvent? tryFromJson(dynamic j) {
    try {
      final m = (j as Map).cast<String, dynamic>();
      return ListeningEvent(
        clientUuid: m['client_uuid'] as String,
        userId: m['user_id'] as String,
        tourId: m['tour_id'] as String,
        segmentId: (m['segment_id'] as num).toInt(),
        action: m['action'] as String,
        atSec: (m['at_sec'] as num).toDouble(),
        createdAt: m['created_at'] as String,
        retries: (m['retries'] as num?)?.toInt() ?? 0,
      );
    } catch (_) {
      return null;
    }
  }
}

/// What the sender learned about one event.
enum SendVerdict {
  /// Stored by the server.
  delivered,

  /// The server refused it for good (invalid / unknown segment): drop it.
  rejected,

  /// Could not deliver (offline, 5xx, throttled, route missing): keep it.
  retry,
}

typedef EventSender = Future<SendVerdict> Function(ListeningEvent event);

/// The production sender: POST /listening-events on the user API. Routed
/// through [Endpoints.postOrFeatureUnavailable] (D661): a server that does not
/// have the route yet (Beta/Storied, or 907 not deployed) is "retry later", not
/// an error.
Future<SendVerdict> sendListeningEventHttp(ListeningEvent e) async {
  try {
    final r = await Endpoints.postOrFeatureUnavailable(
      Service.userDb,
      '/listening-events',
      body: e.toWire(),
      timeout: const Duration(seconds: 8),
    );
    final c = r.statusCode;
    if (c >= 200 && c < 300) return SendVerdict.delivered;
    // 400 invalid, 404 = the service's own "segment not found" (a missing route
    // was already turned into FeatureUnavailableException): will never succeed.
    if (c == 400 || c == 404) return SendVerdict.rejected;
    return SendVerdict.retry;
  } on FeatureUnavailableException {
    return SendVerdict.retry;
  } catch (_) {
    return SendVerdict.retry;
  }
}

class ListeningEventsQueue {
  ListeningEventsQueue({
    EventSender? sender,
    DateTime Function()? now,
    String storageKey = defaultStorageKey,
    this.maxAge = const Duration(days: 14),
    this.maxQueued = 500,
    this.baseBackoff = const Duration(seconds: 5),
    this.maxBackoff = const Duration(minutes: 15),
    this.autoRetry = true,
    this.flushOnEnqueue = true,
  })  : _sender = sender ?? sendListeningEventHttp,
        _now = now ?? DateTime.now,
        _key = storageKey;

  static const String defaultStorageKey = 'listening_events_queue_v1';
  static final ListeningEventsQueue instance = ListeningEventsQueue();

  final EventSender _sender;
  final DateTime Function() _now;
  final String _key;
  final Duration maxAge;
  final int maxQueued;
  final Duration baseBackoff;
  final Duration maxBackoff;
  final bool autoRetry;

  /// Start a background flush after every [enqueue] (production). Tests that
  /// need to count deliveries exactly turn it off and call [flush] themselves.
  final bool flushOnEnqueue;

  Timer? _retryTimer;
  Future<bool>? _running;
  bool _rerun = false;
  int _failures = 0;
  Future<void> _storeChain = Future.value();

  /// Human-readable diagnostics (drops, expiries).
  final List<String> log = <String>[];

  /// Store one event and return. The network is touched only by a background,
  /// un-awaited flush.
  Future<void> enqueue({
    required String userId,
    required String tourId,
    required int segmentId,
    required String action,
    double atSec = 0,
  }) async {
    if (!kListeningActions.contains(action)) return;
    final e = ListeningEvent(
      clientUuid: _uuid(),
      userId: userId,
      tourId: tourId,
      segmentId: segmentId,
      action: action,
      atSec: atSec < 0 ? 0 : atSec,
      createdAt: _now().toUtc().toIso8601String(),
    );
    await _mutate((list) {
      list.add(e);
      while (list.length > maxQueued) {
        list.removeAt(0);
        log.add('queue full: dropped oldest event');
      }
      return list;
    });
    if (flushOnEnqueue) unawaited(flush());
  }

  Future<List<ListeningEvent>> pending() async => _read();
  Future<int> get pendingCount async => (await _read()).length;

  /// Deliver queued events in order. Returns true when the queue is empty
  /// afterwards. Never throws.
  Future<bool> flush() async {
    final running = _running;
    if (running != null) {
      _rerun = true; // an event arrived mid-flush: the running flush rechecks
      return running;
    }
    final f = _doFlush();
    _running = f;
    try {
      return await f;
    } finally {
      _running = null;
    }
  }

  Future<bool> _doFlush() async {
    try {
      // Expire first, so a month-old event never goes out.
      await _mutate((list) {
        final cutoff = _now().toUtc().subtract(maxAge);
        return list.where((e) {
          final t = DateTime.tryParse(e.createdAt);
          final old = t != null && t.isBefore(cutoff);
          if (old) log.add('expired: ${e.action} seg ${e.segmentId}');
          return !old;
        }).toList();
      });
      while (true) {
        final list = await _read();
        if (list.isEmpty) {
          if (_rerun) {
            _rerun = false;
            continue;
          }
          _failures = 0;
          _cancelRetry();
          return true;
        }
        final head = list.first;
        SendVerdict verdict;
        try {
          verdict = await _sender(head);
        } catch (_) {
          verdict = SendVerdict.retry;
        }
        if (verdict == SendVerdict.retry) {
          await _mutate((l) {
            for (final e in l) {
              if (e.clientUuid == head.clientUuid) e.retries++;
            }
            return l;
          });
          _failures++;
          _scheduleRetry();
          return false;
        }
        if (verdict == SendVerdict.rejected) {
          log.add('rejected by server: ${head.action} seg ${head.segmentId}');
        }
        await _mutate(
            (l) => l.where((e) => e.clientUuid != head.clientUuid).toList());
        _failures = 0;
      }
    } catch (_) {
      return false;
    }
  }

  Duration get nextBackoff {
    final n = math.min(_failures, 12);
    final ms = baseBackoff.inMilliseconds * math.pow(2, math.max(0, n - 1));
    return Duration(milliseconds: math.min(ms.toInt(), maxBackoff.inMilliseconds));
  }

  void _scheduleRetry() {
    if (!autoRetry) return;
    _retryTimer?.cancel();
    _retryTimer = Timer(nextBackoff, () => unawaited(flush()));
  }

  void _cancelRetry() {
    _retryTimer?.cancel();
    _retryTimer = null;
  }

  void dispose() => _cancelRetry();

  // ── storage (serialised so concurrent enqueue/flush never lose writes) ────
  Future<List<ListeningEvent>> _read() async {
    final p = await SharedPreferences.getInstance();
    final raw = p.getString(_key);
    if (raw == null || raw.isEmpty) return <ListeningEvent>[];
    try {
      final j = jsonDecode(raw);
      if (j is! List) return <ListeningEvent>[];
      return j
          .map(ListeningEvent.tryFromJson)
          .whereType<ListeningEvent>()
          .toList();
    } catch (_) {
      return <ListeningEvent>[];
    }
  }

  Future<void> _mutate(
      List<ListeningEvent> Function(List<ListeningEvent>) change) {
    final run = _storeChain.then((_) async {
      final next = change(await _read());
      final p = await SharedPreferences.getInstance();
      await p.setString(_key, jsonEncode(next.map((e) => e.toJson()).toList()));
    });
    _storeChain = run.catchError((_) {});
    return run;
  }

  static String _uuid() {
    final rnd = math.Random.secure();
    final b = List<int>.generate(16, (_) => rnd.nextInt(256));
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    String h(int v) => v.toRadixString(16).padLeft(2, '0');
    final x = b.map(h).toList();
    return '${x[0]}${x[1]}${x[2]}${x[3]}-${x[4]}${x[5]}-${x[6]}${x[7]}-'
        '${x[8]}${x[9]}-${x[10]}${x[11]}${x[12]}${x[13]}${x[14]}${x[15]}';
  }
}
