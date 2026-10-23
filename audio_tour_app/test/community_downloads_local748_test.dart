// [LOCAL-748] Pure unit tests for the community-tour "on the phone" helpers:
//   * communityTourSourceItem — the sourceItem a community-page Download passes
//     so the saved record is stamped with community_id/version/updated_at;
//   * stampCommunityIdOnSavedRecords — repairs records already on the phone
//     (no community_id) so the held-tour refresh can see them;
//   * planNewTourAnnouncements + newTourMessage — which new tours to announce
//     (once per tour, never the user's own) and the exact wording.
//
// These assertions FAIL on 7332bfb5 (the helpers do not exist yet) — the red
// tests the ticket requires.

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/community_downloads.dart';

void main() {
  group('communityTourSourceItem', () {
    test('always carries community_id and version', () {
      final s = communityTourSourceItem(communityId: 10, version: 2);
      expect(s['community_id'], 10);
      expect(s['version'], 2);
      expect(s.containsKey('updated_at'), isFalse);
    });

    test('version defaults to 1; updated_at included when non-empty', () {
      final s =
          communityTourSourceItem(communityId: 10, updatedAt: '2026-10-23');
      expect(s['community_id'], 10);
      expect(s['version'], 1);
      expect(s['updated_at'], '2026-10-23');
    });

    test('a blank updated_at is dropped', () {
      final s = communityTourSourceItem(communityId: 10, updatedAt: '');
      expect(s.containsKey('updated_at'), isFalse);
    });
  });

  group('stampCommunityIdOnSavedRecords', () {
    String rec(Map<String, dynamic> m) => jsonEncode(m);

    test('stamps community_id (and version 1) onto a matching bare record', () {
      final saved = [
        rec({'title': 'Salem Walk', 'tour_id': 'abc', 'server_tour_id': '716'}),
      ];
      final out = stampCommunityIdOnSavedRecords(
        savedToursJson: saved,
        communityId: 10,
        communityTourIds: {'716'},
      );
      expect(out, isNotNull);
      final m = jsonDecode(out!.single) as Map<String, dynamic>;
      expect(m['community_id'], 10);
      expect(m['version'], 1);
    });

    test('matches by tour_id too', () {
      final saved = [
        rec({'title': 'Salem Walk', 'tour_id': '716'}),
      ];
      final out = stampCommunityIdOnSavedRecords(
        savedToursJson: saved,
        communityId: 10,
        communityTourIds: {'716'},
      );
      final m = jsonDecode(out!.single) as Map<String, dynamic>;
      expect(m['community_id'], 10);
    });

    test('leaves a record that already carries a community_id untouched', () {
      final saved = [
        rec({'server_tour_id': '716', 'community_id': 10, 'version': 2}),
      ];
      final out = stampCommunityIdOnSavedRecords(
        savedToursJson: saved,
        communityId: 10,
        communityTourIds: {'716'},
      );
      // No change → null.
      expect(out, isNull);
    });

    test('does not overwrite an existing version', () {
      final saved = [
        rec({'server_tour_id': '716', 'version': 3}),
      ];
      final out = stampCommunityIdOnSavedRecords(
        savedToursJson: saved,
        communityId: 10,
        communityTourIds: {'716'},
      );
      final m = jsonDecode(out!.single) as Map<String, dynamic>;
      expect(m['community_id'], 10);
      expect(m['version'], 3); // untouched
    });

    test('does not touch a record whose id is not in the community', () {
      final saved = [
        rec({'server_tour_id': '999'}),
      ];
      final out = stampCommunityIdOnSavedRecords(
        savedToursJson: saved,
        communityId: 10,
        communityTourIds: {'716'},
      );
      expect(out, isNull);
    });

    test('empty community tour set → no change', () {
      final saved = [rec({'server_tour_id': '716'})];
      expect(
        stampCommunityIdOnSavedRecords(
          savedToursJson: saved,
          communityId: 10,
          communityTourIds: const {},
        ),
        isNull,
      );
    });
  });

  group('newTourMessage + planNewTourAnnouncements', () {
    NewCommunityTour tour(int id, {int communityId = 10, String title = 'Salem TV tour'}) =>
        NewCommunityTour(
          communityId: communityId,
          tourId: id,
          languages: const ['en'],
          originalLanguage: 'en',
          communityName: 'Salem TV show funs',
          shortTitle: title,
        );

    test('message wording is "New tour in <community>: <tour>"', () {
      expect(
        newTourMessage('Salem TV show funs', 'Salem TV tour'),
        'New tour in Salem TV show funs: Salem TV tour',
      );
    });

    test('announces a new tour once; carries community + title', () {
      final out = planNewTourAnnouncements(
        newTours: [tour(733)],
        ownedCommunityIds: const {},
        announcedTourIds: const {},
        autoDownloadedTourIds: const {},
      );
      expect(out.length, 1);
      expect(out.single.tourId, 733);
      expect(out.single.communityName, 'Salem TV show funs');
      expect(out.single.tourName, 'Salem TV tour');
      expect(out.single.autoDownloaded, isFalse);
    });

    test('NEVER announces a tour in a community the user owns', () {
      final out = planNewTourAnnouncements(
        newTours: [tour(733, communityId: 10)],
        ownedCommunityIds: const {10},
        announcedTourIds: const {},
        autoDownloadedTourIds: const {},
      );
      expect(out, isEmpty);
    });

    test('already-announced tour is not announced again (once per tour)', () {
      final out = planNewTourAnnouncements(
        newTours: [tour(733)],
        ownedCommunityIds: const {},
        announcedTourIds: {'733'},
        autoDownloadedTourIds: const {},
      );
      expect(out, isEmpty);
    });

    test('autoDownloaded flag set when the tour was downloaded this run', () {
      final out = planNewTourAnnouncements(
        newTours: [tour(733)],
        ownedCommunityIds: const {},
        announcedTourIds: const {},
        autoDownloadedTourIds: {733},
      );
      expect(out.single.autoDownloaded, isTrue);
    });
  });
}
