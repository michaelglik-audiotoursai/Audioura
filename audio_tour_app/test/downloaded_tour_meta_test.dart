// [LOCAL-677B] Unit tests for the paid-tour LOCAL snapshot and the offline-
// correct lock decision — the testable core of the Bounce fix (Michael's
// iPhone, 2026-10-13). These exercise the exact logic the player uses:
//
//   * the player resolves the NUMERIC server id with
//     DownloadedTourMeta.resolveServerTourId — the fix for "no GET /unlock-state
//     request at all" (the stored generic id was non-numeric);
//   * the OFFLINE lock is DownloadedTourMeta.lockedOffline — fail closed only
//     for a tour stored paid, free (incl. grandfathered-free) stays free;
//   * grandfathering is the is_paid snapshot taken AT DOWNLOAD time;
//   * an unlock writes to the local record at once
//     (DownloadedTourStore.markUnlockedForPath);
//   * a translation's record carries the inherited PRICE but its OWN
//     unlock:false (per-language, D653).
//
// Pure model + SharedPreferences, so no WebView or live server is needed.

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/services/downloaded_tour_meta.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('server tour id resolution (the Bounce root cause)', () {
    test('explicit serverTourId wins', () {
      expect(
        DownloadedTourMeta.resolveServerTourId(
          serverTourId: '557',
          widgetTourId: 'edit_abc',
          metaServerTourId: '999',
        ),
        '557',
      );
    });

    test('falls back to a numeric widget tourId', () {
      expect(
        DownloadedTourMeta.resolveServerTourId(
          serverTourId: null,
          widgetTourId: '557',
          metaServerTourId: null,
        ),
        '557',
      );
    });

    test('falls back to the local record server id when the generic id is non-numeric', () {
      // This is the exact Bounce case: the player had only the non-numeric
      // editable id. Without the stamped server id it never asked the server.
      expect(
        DownloadedTourMeta.resolveServerTourId(
          serverTourId: null,
          widgetTourId: 'q9oSUebU', // non-numeric editable id
          metaServerTourId: '557',
        ),
        '557',
      );
    });

    test('returns null when no numeric id is available anywhere', () {
      expect(
        DownloadedTourMeta.resolveServerTourId(
          serverTourId: null,
          widgetTourId: 'q9oSUebU',
          metaServerTourId: null,
        ),
        isNull,
      );
    });

    // The player asks /tour/<id>/unlock-state only when a numeric id resolves.
    // Prove that on EACH entry path the resolver yields the server id 557, so
    // the request fires (the Bounce was that it never did).
    test('each entry path resolves the server id so unlock-state is requested', () {
      bool asks(String? id) => id != null && int.tryParse(id) != null;

      // Listen list / My tours / after-download: serverTourId passed explicitly.
      final listenList = DownloadedTourMeta.resolveServerTourId(
          serverTourId: '557', widgetTourId: 'q9oSUebU', metaServerTourId: '557');
      expect(asks(listenList), isTrue);
      expect(listenList, '557');

      // Share-code path (downloaded, then opened): server id recovered from the
      // local record even if the explicit arg was not threaded.
      final shareCode = DownloadedTourMeta.resolveServerTourId(
          serverTourId: null, widgetTourId: 'q9oSUebU', metaServerTourId: '557');
      expect(asks(shareCode), isTrue);
      expect(shareCode, '557');

      // Voice next/previous: only the path is known → recovered from local meta.
      final voiceNav = DownloadedTourMeta.resolveServerTourId(
          serverTourId: null, widgetTourId: null, metaServerTourId: '557');
      expect(asks(voiceNav), isTrue);
      expect(voiceNav, '557');
    });
  });

  group('offline-correct lock (D647 addendum 2)', () {
    DownloadedTourMeta meta({
      required bool isPaid,
      required bool unlocked,
    }) =>
        DownloadedTourMeta(
          serverTourId: '557',
          priceTier: isPaid ? 3 : null,
          isPaid: isPaid,
          unlocked: unlocked,
          priceLabel: isPaid ? '\$4.99' : 'Free',
          originalLanguage: 'en',
          tourVersion: 12,
        );

    test('a paid, NOT-unlocked tour is locked offline (fail closed)', () {
      expect(meta(isPaid: true, unlocked: false).lockedOffline, isTrue);
    });

    test('a paid, unlocked tour is NOT locked offline', () {
      expect(meta(isPaid: true, unlocked: true).lockedOffline, isFalse);
    });

    test('a FREE tour is never locked offline (fail open for free)', () {
      expect(meta(isPaid: false, unlocked: false).lockedOffline, isFalse);
      expect(meta(isPaid: false, unlocked: true).lockedOffline, isFalse);
    });
  });

  group('grandfathering (is_paid snapshot at download time)', () {
    test('a tour downloaded while FREE stays playable after a later price', () {
      // Record stamped is_paid:false at download (tour was free then). Even if
      // the curator later prices it, this LOCAL snapshot keeps it unlocked —
      // the player gates offline from here, so it is never locked.
      final grandfathered = DownloadedTourMeta.fromRecord({
        'server_tour_id': '557',
        'is_paid': false,
      });
      expect(grandfathered.isPaid, isFalse);
      expect(grandfathered.lockedOffline, isFalse);
    });

    test('a re-download after the price was set is stamped paid and locks', () {
      // The re-download stamps is_paid:true and unlocked:false → locked offline.
      final reDownloaded = DownloadedTourMeta.fromRecord({
        'server_tour_id': '557',
        'is_paid': true,
        'price_tier': 3,
        'unlocked': false,
      });
      expect(reDownloaded.isPaid, isTrue);
      expect(reDownloaded.lockedOffline, isTrue);
    });

    test('a record predating 677B (no keys) is free + unlocked', () {
      final old = DownloadedTourMeta.fromRecord({'title': 'x', 'path': '/p'});
      expect(old.isPaid, isFalse);
      expect(old.unlocked, isTrue);
      expect(old.lockedOffline, isFalse);
      expect(old.serverTourId, isNull);
    });
  });

  group('DownloadedTourStore read / merge / mark-unlocked', () {
    const path = '/docs/tours/paid_tour_557';

    setUp(() {
      SharedPreferences.setMockInitialValues({
        'saved_tours': <String>[
          json.encode({
            'title': 'Paid Tour',
            'path': path,
            'created': '2026-10-13T18:46:00.000Z',
            'tour_id': 'q9oSUebU',
            'server_tour_id': '557',
            'is_paid': true,
            'price_tier': 3,
            'price_label': '\$4.99',
            'unlocked': false,
            'original_language': 'en',
          }),
        ],
      });
    });

    test('metaForPath reads the stamped snapshot', () async {
      final m = await DownloadedTourStore.metaForPath(path);
      expect(m.serverTourId, '557');
      expect(m.isPaid, isTrue);
      expect(m.priceTier, 3);
      expect(m.priceLabel, '\$4.99');
      expect(m.unlocked, isFalse);
      expect(m.lockedOffline, isTrue);
      expect(m.originalLanguage, 'en');
    });

    test('metaForPath for an unknown path is free + unlocked', () async {
      final m = await DownloadedTourStore.metaForPath('/no/such/path');
      expect(m.isPaid, isFalse);
      expect(m.unlocked, isTrue);
      expect(m.lockedOffline, isFalse);
    });

    test('markUnlockedForPath lifts the lock on the local record at once', () async {
      await DownloadedTourStore.markUnlockedForPath(path);
      final m = await DownloadedTourStore.metaForPath(path);
      expect(m.unlocked, isTrue);
      expect(m.lockedOffline, isFalse);
      // The rest of the record is preserved.
      expect(m.isPaid, isTrue);
      expect(m.priceTier, 3);
    });

    test('mergeFieldsForPath is a no-op for an unknown path', () async {
      final changed =
          await DownloadedTourStore.mergeFieldsForPath('/no/such/path', {'unlocked': true});
      expect(changed, isFalse);
    });
  });

  group('per-language price snapshot (D653)', () {
    test('a translation record inherits the price but has its OWN locked state', () {
      // The record a translation download writes: inherited price, its own
      // server id, unlocked:false because a paid translation needs its own buy.
      final ru = DownloadedTourMeta.fromRecord({
        'server_tour_id': '558', // the translation's OWN id (not the source 557)
        'is_paid': true,
        'price_tier': 3,
        'price_label': '\$4.99',
        'unlocked': false,
        'original_language': 'en',
      });
      expect(ru.serverTourId, '558');
      expect(ru.isPaid, isTrue);
      expect(ru.priceLabel, '\$4.99'); // inherited from the source
      expect(ru.lockedOffline, isTrue); // its own unlock, starts locked
    });
  });
}
