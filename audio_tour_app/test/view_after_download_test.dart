// [LOCAL-716B / LOCAL-719 / D677 addendum 1] Tests for the pure
// View-after-download planner. "View" ALWAYS opens a player.
//
// Michael's Pixel-4 field test on 2.4.30+72 (D358): downloaded ONE tour with
// its Russian translation; "View" opened nothing. LOCAL-716B fixed the
// single-tour case. LOCAL-719 (Michael, 2026-10-19) makes the behaviour
// consistent for SEVERAL tours too: "we should start playing when multiple
// tours are downloaded too, maybe the first one."
//
// These goldens pin the decision the planner now makes:
//   * one tour + one translation  → open the translation;
//   * one tour + two translations → open the listening-language one, else the
//     first downloaded;
//   * one tour, no translation     → open the original;
//   * several tours                → open the FIRST selected tour (first id in
//     the ordered list), in the language just downloaded;
//   * several tours, first FAILED  → open the first that succeeded (the first
//     offered id with a saved entry; a failed tour's id is simply absent, but
//     we also skip an offered id that matched nothing);
//   * no ids / none match          → highlight the newest (never open).
// Plus the matcher: a translation's saved entry (server_tour_id = its OWN
// translated id, parent_server_tour_id = the ORIGINAL id) is matched from the
// original server id the snackbar offers.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/utils/view_after_download.dart';

/// A saved ORIGINAL (English) entry: server_tour_id is the numeric server id,
/// tour_id is the non-numeric edit id, no is_translation, no language.
Map<String, dynamic> original({
  required String serverId,
  String editId = 'edit-abc',
  String title = 'Freedom Trail',
  String created = '2026-10-19T10:00:00Z',
}) =>
    {
      'title': title,
      'path': '/tmp/$serverId',
      'created': created,
      'tour_id': editId,
      'server_tour_id': serverId,
    };

/// A saved TRANSLATION entry, shaped as the app actually saves it (verified on
/// the emulator, LOCAL-716B): `tour_id` AND `server_tour_id` are the
/// translation's OWN translated row id (e.g. 437), `is_translation` is true,
/// `language` is the target code, and `parent_server_tour_id` is the ORIGINAL
/// server id (e.g. 117) — the id the snackbar offers. The matcher ties the two
/// together via `parent_server_tour_id`.
Map<String, dynamic> translation({
  required String originalServerId,
  required String ownId,
  required String language,
  String created = '2026-10-19T10:01:00Z',
}) =>
    {
      'title': 'Freedom Trail ($language)',
      'path': '/tmp/ft_$language',
      'created': created,
      'tour_id': ownId,
      'server_tour_id': ownId,
      'parent_server_tour_id': originalServerId,
      'is_translation': true,
      'language': language,
    };

void main() {
  group('planViewAfterDownload — one tour', () {
    test('one tour + ONE translation → opens the translation', () {
      // English deselected (Russian only): the only saved entry is the Russian
      // translation. It still matches the offered original id via
      // parent_server_tour_id, and is opened.
      final entries = [
        translation(originalServerId: '42', ownId: '1042', language: 'ru'),
      ];
      final plan = planViewAfterDownload(
        entries: entries,
        downloadedTourIds: const ['42'],
        listeningLanguage: 'ru',
      );
      expect(plan, const ViewAfterDownloadPlan.openEntry(0));
    });

    test('one tour + original AND one translation → opens the translation', () {
      // English kept + Russian translation. Two saved entries; "the language
      // just downloaded" is the translation, so it wins over the original.
      final entries = [
        original(serverId: '42'),
        translation(originalServerId: '42', ownId: '1042', language: 'ru'),
      ];
      final plan = planViewAfterDownload(
        entries: entries,
        downloadedTourIds: const ['42'],
        listeningLanguage: 'ru',
      );
      expect(plan, const ViewAfterDownloadPlan.openEntry(1));
    });

    test('one tour + TWO translations → opens the listening-language one', () {
      final entries = [
        original(serverId: '42'),
        translation(
            originalServerId: '42',
            ownId: '1042',
            language: 'ru',
            created: '2026-10-19T10:01:00Z'),
        translation(
            originalServerId: '42',
            ownId: '1043',
            language: 'fr',
            created: '2026-10-19T10:02:00Z'),
      ];
      final plan = planViewAfterDownload(
        entries: entries,
        downloadedTourIds: const ['42'],
        listeningLanguage: 'fr',
      );
      // French is the listening language → open the French translation (index 2).
      expect(plan, const ViewAfterDownloadPlan.openEntry(2));
    });

    test('one tour + TWO translations, listening language absent → first '
        'downloaded (oldest created)', () {
      final entries = [
        original(serverId: '42'),
        // French saved SECOND (later created)…
        translation(
            originalServerId: '42',
            ownId: '1043',
            language: 'fr',
            created: '2026-10-19T10:02:00Z'),
        // …Russian saved FIRST (earlier created).
        translation(
            originalServerId: '42',
            ownId: '1042',
            language: 'ru',
            created: '2026-10-19T10:01:00Z'),
      ];
      final plan = planViewAfterDownload(
        entries: entries,
        downloadedTourIds: const ['42'],
        // Listening language is German — neither translation matches.
        listeningLanguage: 'de',
      );
      // Falls back to the FIRST downloaded (oldest created) = Russian at index 2.
      expect(plan, const ViewAfterDownloadPlan.openEntry(2));
    });

    test('one tour, NO translation → opens the original', () {
      final entries = [original(serverId: '42')];
      final plan = planViewAfterDownload(
        entries: entries,
        downloadedTourIds: const ['42'],
        listeningLanguage: 'ru',
      );
      expect(plan, const ViewAfterDownloadPlan.openEntry(0));
    });
  });

  group('planViewAfterDownload — several tours (LOCAL-719 / D677 addendum 1)',
      () {
    test('THREE tours → opens the FIRST the user selected', () {
      // Saved order is NOT selection order (tours arrive/append in any order);
      // the selection order is the ids list ['43','41','42']. The first
      // selected (43) must open, not whatever is first/newest in `entries`.
      final entries = [
        original(serverId: '41', title: 'Alpha'),
        original(serverId: '42', title: 'Beta'),
        original(serverId: '43', title: 'Gamma'),
      ];
      final plan = planViewAfterDownload(
        entries: entries,
        downloadedTourIds: const ['43', '41', '42'],
        listeningLanguage: 'en',
      );
      // 43 is first selected and sits at index 2 in `entries`.
      expect(plan, const ViewAfterDownloadPlan.openEntry(2));
    });

    test('THREE tours, FIRST selected failed to download → opens the first '
        'that SUCCEEDED', () {
      // The user selected 40, 41, 42 in that order, but 40 failed — the caller
      // never saved it and never added its id, so the offered ids are
      // ['41','42']. Even so, the planner also tolerates a stray offered id
      // that matched nothing: here only 41 and 42 have saved entries, and 41 is
      // the first that succeeded.
      final entries = [
        original(serverId: '41', title: 'Alpha'),
        original(serverId: '42', title: 'Beta'),
      ];
      final plan = planViewAfterDownload(
        entries: entries,
        // 40 absent (failed); 41 is first that succeeded.
        downloadedTourIds: const ['41', '42'],
        listeningLanguage: 'en',
      );
      expect(plan, const ViewAfterDownloadPlan.openEntry(0)); // 41 at index 0
    });

    test('several tours where the first offered id has NO saved entry → skips '
        'to the next offered id', () {
      // Belt-and-braces: even if the caller listed a tour id whose save
      // silently vanished (first id matches nothing), the planner walks on to
      // the next selected id rather than stranding View on the missing one.
      final entries = [
        original(serverId: '42', title: 'Beta'),
        original(serverId: '43', title: 'Gamma'),
      ];
      final plan = planViewAfterDownload(
        entries: entries,
        // 40 matches nothing; 42 is the next selected with a saved entry.
        downloadedTourIds: const ['40', '42', '43'],
        listeningLanguage: 'en',
      );
      expect(plan, const ViewAfterDownloadPlan.openEntry(0)); // 42 at index 0
    });

    test('several tours, first selected has a translation → opens that tour in '
        'the language just downloaded', () {
      // First selected is 42; it was downloaded with its Russian translation.
      // View opens the Russian copy of the FIRST selected tour.
      final entries = [
        original(serverId: '41', title: 'Alpha'),
        original(serverId: '42', title: 'Beta'),
        translation(originalServerId: '42', ownId: '1042', language: 'ru'),
      ];
      final plan = planViewAfterDownload(
        entries: entries,
        downloadedTourIds: const ['42', '41'],
        listeningLanguage: 'ru',
      );
      // Russian translation of 42 is at index 2.
      expect(plan, const ViewAfterDownloadPlan.openEntry(2));
    });
  });

  group('planViewAfterDownload — matcher from the offered id', () {
    test("a translation's saved entry is matched from the id the snackbar "
        'offers (the original server id)', () {
      final entries = [
        translation(originalServerId: '42', ownId: '1042', language: 'ru'),
      ];
      final plan = planViewAfterDownload(
        entries: entries,
        downloadedTourIds: const ['42'], // the original id, NOT 1042
        listeningLanguage: null,
      );
      expect(plan.action, ViewAfterDownloadAction.openEntry);
      expect(plan.entryIndex, 0);
    });

    test('unrelated saved tours are ignored; only the offered tour matches', () {
      final entries = [
        original(serverId: '7'),
        translation(originalServerId: '42', ownId: '1042', language: 'ru'),
        original(serverId: '99'),
      ];
      final plan = planViewAfterDownload(
        entries: entries,
        downloadedTourIds: const ['42'],
        listeningLanguage: 'ru',
      );
      expect(plan, const ViewAfterDownloadPlan.openEntry(1));
    });
  });

  group('planViewAfterDownload — highlight (no open)', () {
    test('no ids offered → highlight newest', () {
      final plan = planViewAfterDownload(
        entries: [original(serverId: '42')],
        downloadedTourIds: const [],
        listeningLanguage: 'ru',
      );
      expect(plan, const ViewAfterDownloadPlan.highlightNewest());
    });

    test('offered ids match NOTHING → highlight newest (no silent miss path)',
        () {
      final entries = [original(serverId: '7')];
      final plan = planViewAfterDownload(
        entries: entries,
        downloadedTourIds: const ['42', '43'], // none among the saved entries
        listeningLanguage: 'ru',
      );
      expect(plan, const ViewAfterDownloadPlan.highlightNewest());
    });

    test('blank ids are ignored; an all-blank list highlights', () {
      final plan = planViewAfterDownload(
        entries: [original(serverId: '42')],
        downloadedTourIds: const ['', '   '],
        listeningLanguage: null,
      );
      expect(plan, const ViewAfterDownloadPlan.highlightNewest());
    });
  });

  group('newestEntryIndex', () {
    test('picks the entry with the latest created timestamp', () {
      final entries = [
        original(serverId: '1', created: '2026-10-19T10:00:00Z'),
        original(serverId: '2', created: '2026-10-19T12:00:00Z'), // newest
        original(serverId: '3', created: '2026-10-19T11:00:00Z'),
      ];
      expect(newestEntryIndex(entries), 1);
    });

    test('empty list → null', () {
      expect(newestEntryIndex(const []), isNull);
    });

    test('ties keep the later index (a freshly appended entry wins)', () {
      final entries = [
        original(serverId: '1', created: '2026-10-19T10:00:00Z'),
        original(serverId: '2', created: '2026-10-19T10:00:00Z'),
      ];
      expect(newestEntryIndex(entries), 1);
    });
  });
}
