// [LOCAL-716B / D358] Tests for the pure View-after-download planner.
//
// Michael's Pixel-4 field test on 2.4.30+72: downloaded ONE tour with its
// Russian translation; "View" opened nothing. These goldens pin the decision
// the planner now makes so that regression cannot return silently:
//   * one tour + one translation  → open the translation;
//   * one tour + two translations → open the listening-language one, else the
//     first downloaded;
//   * one tour, no translation     → open the original;
//   * several tours / no id / miss → highlight the newest (never open).
// Plus the matcher: a translation's saved entry (server_tour_id = the ORIGINAL
// id, tour_id = its own translated id) is matched from the id the snackbar
// offers (the original server id).

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/utils/view_after_download.dart';

/// A saved ORIGINAL (English) entry: server_tour_id is the numeric server id,
/// tour_id is the non-numeric edit id, no is_translation, no language.
Map<String, dynamic> original({
  required String serverId,
  String editId = 'edit-abc',
  String created = '2026-10-19T10:00:00Z',
}) =>
    {
      'title': 'Freedom Trail',
      'path': '/tmp/ft',
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
      // server_tour_id, and is opened.
      final entries = [
        translation(originalServerId: '42', ownId: '1042', language: 'ru'),
      ];
      final plan = planViewAfterDownload(
        entries: entries,
        downloadedTourCount: 1,
        wantedServerId: '42',
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
        downloadedTourCount: 1,
        wantedServerId: '42',
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
        downloadedTourCount: 1,
        wantedServerId: '42',
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
        downloadedTourCount: 1,
        wantedServerId: '42',
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
        downloadedTourCount: 1,
        wantedServerId: '42',
        listeningLanguage: 'ru',
      );
      expect(plan, const ViewAfterDownloadPlan.openEntry(0));
    });
  });

  group('planViewAfterDownload — matcher from the offered id', () {
    test("a translation's saved entry is matched from the id the snackbar "
        'offers (the original server id)', () {
      // The snackbar offers the ORIGINAL server id (42). The saved entry is the
      // translation, whose tour_id/server_tour_id are its OWN id (1042) and
      // whose parent_server_tour_id is 42. The matcher must find it via
      // parent_server_tour_id (the Pixel-4 miss was that no stored field linked
      // the translation back to the offered 117).
      final entries = [
        translation(originalServerId: '42', ownId: '1042', language: 'ru'),
      ];
      final plan = planViewAfterDownload(
        entries: entries,
        downloadedTourCount: 1,
        wantedServerId: '42', // the original id, NOT 1042
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
        downloadedTourCount: 1,
        wantedServerId: '42',
        listeningLanguage: 'ru',
      );
      expect(plan, const ViewAfterDownloadPlan.openEntry(1));
    });
  });

  group('planViewAfterDownload — highlight (no open)', () {
    test('several tours downloaded → highlight newest, never open', () {
      final entries = [
        original(serverId: '42'),
        original(serverId: '43'),
      ];
      final plan = planViewAfterDownload(
        entries: entries,
        downloadedTourCount: 2,
        wantedServerId: null,
        listeningLanguage: 'ru',
      );
      expect(plan, const ViewAfterDownloadPlan.highlightNewest());
    });

    test('no id offered → highlight newest', () {
      final plan = planViewAfterDownload(
        entries: [original(serverId: '42')],
        downloadedTourCount: 1,
        wantedServerId: null,
        listeningLanguage: 'ru',
      );
      expect(plan, const ViewAfterDownloadPlan.highlightNewest());
    });

    test('offered id matches NOTHING → highlight newest (no silent miss path)',
        () {
      final entries = [original(serverId: '7')];
      final plan = planViewAfterDownload(
        entries: entries,
        downloadedTourCount: 1,
        wantedServerId: '42', // not among the saved entries
        listeningLanguage: 'ru',
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
