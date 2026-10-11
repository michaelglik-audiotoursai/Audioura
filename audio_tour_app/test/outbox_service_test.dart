import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/services/outbox_service.dart';
import 'package:audio_tour_app_dev/services/tour_listen_service.dart';

/// LOCAL-670C — the offline outbox and the local rating gate.
///
///   * ordering: listens come before the rating that depends on them,
///   * retry: a failed flush (no network) KEEPS every item,
///   * expiry: an item older than 90 days is dropped,
///   * durability: items survive a reload (same storage key),
///   * local gate: hasListenedEnough / requiredThreshold read the LOCAL record,
///   * listened record stores a timestamp and dedupes per stop.
void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({'user_id': 'u-test'});
    OutboxService.instance.enableTestMode();
    await OutboxService.instance.resetForTest();
  });

  group('outbox ordering', () {
    test('listens are ordered before the rating that depends on them', () async {
      await OutboxService.instance
          .enqueueRating(userId: 'u', tourId: '42', rating: 9);
      await OutboxService.instance
          .enqueueListened(userId: 'u', tourId: '42', stopIndex: 0);
      await OutboxService.instance
          .enqueueThumb(userId: 'u', tourId: '42', stopIndex: 1, swipe: 1);
      await OutboxService.instance
          .enqueueListened(userId: 'u', tourId: '42', stopIndex: 1);

      final items = await OutboxService.instance.pendingItems();
      final ordered = OutboxService.instance.orderedForTest(items);
      final types = ordered.map((i) => i.type).toList();

      // Both listens precede the rating; the rating is last.
      final firstRating = types.indexOf('rating');
      final lastListen = types.lastIndexOf('listened');
      expect(lastListen, lessThan(firstRating));
      expect(types.last, 'rating');
    });
  });

  group('outbox retry (no network)', () {
    test('a failed flush keeps every item for a later retry', () async {
      await OutboxService.instance
          .enqueueListened(userId: 'u', tourId: '7', stopIndex: 0);
      await OutboxService.instance
          .enqueueListened(userId: 'u', tourId: '7', stopIndex: 1);
      expect(await OutboxService.instance.pendingCount, 2);

      // No server reachable in a unit test → flush returns false, keeps items.
      final emptied = await OutboxService.instance.flush();
      expect(emptied, isFalse);
      expect(await OutboxService.instance.pendingCount, 2);
    });

    test('items survive a reload (durable across restart/update)', () async {
      await OutboxService.instance
          .enqueueRating(userId: 'u', tourId: '7', rating: 8);
      final before = await OutboxService.instance.pendingItems();
      expect(before.length, 1);

      // A fresh read from the same storage key (simulating a restart) still
      // sees the item — the outbox is persisted, not in-memory.
      final after = await OutboxService.instance.pendingItems();
      expect(after.length, 1);
      expect(after.first.payload['rating'], 8);
      expect(after.first.clientUuid, isNotEmpty);
    });
  });

  group('outbox 90-day expiry', () {
    test('an item older than 90 days is dropped with a log line', () async {
      // Enqueue one fresh and one ancient item.
      await OutboxService.instance
          .enqueueListened(userId: 'u', tourId: '7', stopIndex: 0);
      await OutboxService.instance.enqueueListened(
        userId: 'u',
        tourId: '7',
        stopIndex: 1,
        createdAt: DateTime.now().toUtc().subtract(const Duration(days: 100)),
      );

      final items = await OutboxService.instance.pendingItems();
      final kept = OutboxService.instance.dropExpiredForTest(items);
      expect(items.length, 2);
      expect(kept.length, 1);
      expect(
        OutboxService.instance.log.any((l) => l.contains('expired')),
        isTrue,
      );
    });
  });

  group('local rating gate', () {
    test('requiredThreshold: 2 normally, min(2,n) for short tours', () {
      expect(TourListenService.requiredThreshold(null), 2);
      expect(TourListenService.requiredThreshold(5), 2);
      expect(TourListenService.requiredThreshold(2), 2);
      expect(TourListenService.requiredThreshold(1), 1);
      expect(TourListenService.requiredThreshold(0), 2); // unknown-ish → full
    });

    test('hasListenedEnough flips to true at the 2nd distinct stop', () async {
      await OutboxService.instance.resetForTest();
      expect(await TourListenService.hasListenedEnough('99'), isFalse);

      await TourListenService.recordListened(tourId: '99', stopIndex: 0);
      expect(await TourListenService.hasListenedEnough('99'), isFalse);
      expect(await TourListenService.listenedCount('99'), 1);

      await TourListenService.recordListened(tourId: '99', stopIndex: 3);
      expect(await TourListenService.hasListenedEnough('99'), isTrue);
      expect(await TourListenService.listenedCount('99'), 2);
    });

    test('a 1-stop tour unlocks after its single stop', () async {
      await TourListenService.recordListened(tourId: '77', stopIndex: 0);
      expect(
        await TourListenService.hasListenedEnough('77', totalStops: 1),
        isTrue,
      );
    });

    test('re-recording the same stop does not double-count', () async {
      await TourListenService.recordListened(tourId: '55', stopIndex: 2);
      await TourListenService.recordListened(tourId: '55', stopIndex: 2);
      expect(await TourListenService.listenedCount('55'), 1);
    });

    test('a listened record enqueues one listened item for sync', () async {
      await OutboxService.instance.resetForTest();
      await TourListenService.recordListened(tourId: '42', stopIndex: 0);
      final items = await OutboxService.instance.pendingItems();
      final listens = items.where((i) => i.type == 'listened').toList();
      expect(listens.length, 1);
      expect(listens.first.payload['tour_id'], '42');
      expect(listens.first.payload['stop_index'], 0);
      // Carries a timestamp (ISO-8601) for server-side skew checks + expiry.
      expect(listens.first.createdAt, isNotEmpty);
    });
  });
}
