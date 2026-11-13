import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/services/listening_events_queue.dart';

void main() {
  late List<ListeningEvent> delivered;
  late SendVerdict nextVerdict;
  late DateTime clock;

  ListeningEventsQueue makeQueue({EventSender? sender, bool auto = false}) =>
      ListeningEventsQueue(
        flushOnEnqueue: auto,
        sender: sender ??
            (e) async {
              if (nextVerdict == SendVerdict.delivered) delivered.add(e);
              return nextVerdict;
            },
        now: () => clock,
        autoRetry: false,
      );

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    delivered = [];
    nextVerdict = SendVerdict.delivered;
    clock = DateTime.utc(2026, 11, 13, 12);
  });

  Future<void> add(ListeningEventsQueue q, String action,
          {int seg = 12, double at = 0}) =>
      q.enqueue(
          userId: 'u1', tourId: 't9', segmentId: seg, action: action, atSec: at);

  test('wire body is exactly what 907 POST /listening-events accepts', () async {
    final q = makeQueue();
    await add(q, 'skip', at: 42.5);
    await q.flush();
    expect(delivered.single.toWire(), {
      'user_id': 'u1',
      'tour_id': 't9',
      'segment_id': 12,
      'action': 'skip',
      'at_sec': 42.5,
    });
  });

  test('offline: events stay queued, in order, and survive a restart', () async {
    nextVerdict = SendVerdict.retry; // no network
    final q = makeQueue();
    await add(q, 'start');
    await add(q, 'skip', at: 30);
    await add(q, 'choose', seg: 14);
    await q.flush();
    expect(await q.pendingCount, 3);
    expect(delivered, isEmpty);

    // "Restart": a new queue object over the same storage.
    final q2 = makeQueue();
    expect((await q2.pending()).map((e) => e.action), ['start', 'skip', 'choose']);

    // Back online: everything goes out FIFO and the queue empties.
    nextVerdict = SendVerdict.delivered;
    expect(await q2.flush(), isTrue);
    expect(delivered.map((e) => e.action), ['start', 'skip', 'choose']);
    expect(await q2.pendingCount, 0);
  });

  test('a failed head blocks the rest (order is kept) and counts retries',
      () async {
    nextVerdict = SendVerdict.retry;
    final q = makeQueue();
    await add(q, 'start');
    await add(q, 'finish');
    await q.flush();
    await q.flush();
    final p = await q.pending();
    expect(p.length, 2);
    expect(p.first.retries, 2);
    expect(p.last.retries, 0);
  });

  test('a definitive refusal drops only that event', () async {
    final q = makeQueue(sender: (e) async {
      if (e.segmentId == 99) return SendVerdict.rejected;
      delivered.add(e);
      return SendVerdict.delivered;
    });
    await add(q, 'start', seg: 99);
    await add(q, 'start', seg: 1);
    await q.flush();
    expect(delivered.single.segmentId, 1);
    expect(await q.pendingCount, 0);
    expect(q.log.single, contains('rejected'));
  });

  test('a sender that throws is treated as offline (kept)', () async {
    final q = makeQueue(sender: (e) async => throw StateError('boom'));
    await add(q, 'finish');
    await q.flush();
    expect(await q.pendingCount, 1);
  });

  test('events older than the max age are dropped, not sent', () async {
    nextVerdict = SendVerdict.retry;
    final q = makeQueue();
    await add(q, 'start');
    clock = clock.add(const Duration(days: 15));
    nextVerdict = SendVerdict.delivered;
    await q.flush();
    expect(delivered, isEmpty);
    expect(await q.pendingCount, 0);
    expect(q.log.single, contains('expired'));
  });

  test('NEVER BLOCKS PLAYBACK: enqueue returns while the network hangs',
      () async {
    final hang = Completer<SendVerdict>();
    final q = makeQueue(sender: (e) => hang.future, auto: true);
    final sw = Stopwatch()..start();
    await add(q, 'start');
    await add(q, 'skip', at: 5);
    sw.stop();
    expect(sw.elapsedMilliseconds, lessThan(1000));
    expect(await q.pendingCount, 2); // stored, flush still hanging in background
    hang.complete(SendVerdict.retry);
  });

  test('an event added while a flush is running is not stranded', () async {
    final gate = Completer<void>();
    var first = true;
    final q = makeQueue(sender: (e) async {
      if (first) {
        first = false;
        await gate.future;
      }
      delivered.add(e);
      return SendVerdict.delivered;
    }, auto: true);
    await add(q, 'start');
    await Future<void>.delayed(const Duration(milliseconds: 20));
    await add(q, 'finish'); // arrives mid-flush
    gate.complete();
    for (var i = 0; i < 50 && await q.pendingCount > 0; i++) {
      await Future<void>.delayed(const Duration(milliseconds: 10));
    }
    expect(delivered.map((e) => e.action), ['start', 'finish']);
  });

  test('backoff doubles from 5 s up to the 15 min cap', () async {
    nextVerdict = SendVerdict.retry;
    final q = makeQueue();
    await add(q, 'start');
    final waits = <int>[];
    for (var i = 0; i < 12; i++) {
      await q.flush();
      waits.add(q.nextBackoff.inSeconds);
    }
    expect(waits.take(4), [5, 10, 20, 40]);
    expect(waits.last, 900);
  });

  test('unknown actions are ignored', () async {
    final q = makeQueue();
    await add(q, 'dance');
    expect(await q.pendingCount, 0);
  });
}
