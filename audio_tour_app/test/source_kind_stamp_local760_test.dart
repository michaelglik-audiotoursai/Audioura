// test/source_kind_stamp_local760_test.dart — LOCAL-760 / D708 (build item 2).
//
// The saved Listen record must KNOW a tour is organiser audio so the Listen ⋮
// menu disables Edit/Translate with an ⓘ. Two pure helpers in
// services/community_downloads.dart make that reliable:
//   * communityTourSourceItem now carries source_kind, so a member's download
//     from the community page stamps source_kind='organiser_audio' at save time
//     (the ROOT cause Michael hit: his download record had none, so the menu
//     stayed enabled);
//   * stampSourceKindOnSavedRecords repairs records ALREADY on the phone — given
//     the set of this community's organiser-audio tour ids, it stamps
//     source_kind onto the matching saved records (no re-download);
//   * isOrganiserAudioFromFiles decides from the tour folder's file list
//     (remote_audio.json present → organiser audio), so the repair can be driven
//     from what is on disk.
//
// RED on 127cd384: communityTourSourceItem has no sourceKind param and neither
// stampSourceKindOnSavedRecords nor isOrganiserAudioFromFiles exists.
//
// Run: flutter test test/source_kind_stamp_local760_test.dart

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/community_downloads.dart';

void main() {
  group('communityTourSourceItem carries source_kind', () {
    test('source_kind is included when given', () {
      final s = communityTourSourceItem(
          communityId: 10, version: 2, sourceKind: 'organiser_audio');
      expect(s['community_id'], 10);
      expect(s['version'], 2);
      expect(s['source_kind'], 'organiser_audio');
    });

    test('source_kind is dropped when null or blank', () {
      expect(
          communityTourSourceItem(communityId: 10).containsKey('source_kind'),
          isFalse);
      expect(
          communityTourSourceItem(communityId: 10, sourceKind: '')
              .containsKey('source_kind'),
          isFalse);
    });
  });

  group('isOrganiserAudioFromFiles', () {
    test('remote_audio.json present → organiser audio', () {
      expect(
          isOrganiserAudioFromFiles(
              ['index.html', 'audio_1.mp3', 'remote_audio.json']),
          isTrue);
    });

    test('a generated tour (no remote_audio.json) → not organiser audio', () {
      expect(
          isOrganiserAudioFromFiles(['index.html', 'audio_1.mp3', 'tour.zip']),
          isFalse);
    });

    test('empty list → not organiser audio', () {
      expect(isOrganiserAudioFromFiles(const []), isFalse);
    });
  });

  group('stampSourceKindOnSavedRecords', () {
    String rec(Map<String, dynamic> m) => jsonEncode(m);

    test('stamps organiser_audio onto a matching record missing it', () {
      final saved = [
        rec({'title': 'Salem Walk', 'tour_id': 'abc', 'server_tour_id': '750'}),
      ];
      final out = stampSourceKindOnSavedRecords(
        savedToursJson: saved,
        organiserAudioTourIds: {'750'},
      );
      expect(out, isNotNull);
      final m = jsonDecode(out!.single) as Map<String, dynamic>;
      expect(m['source_kind'], 'organiser_audio');
    });

    test('matches by tour_id too', () {
      final saved = [
        rec({'title': 'Salem Walk', 'tour_id': '750'}),
      ];
      final out = stampSourceKindOnSavedRecords(
        savedToursJson: saved,
        organiserAudioTourIds: {'750'},
      );
      final m = jsonDecode(out!.single) as Map<String, dynamic>;
      expect(m['source_kind'], 'organiser_audio');
    });

    test('a record that already carries organiser_audio is untouched (null)',
        () {
      final saved = [
        rec({'server_tour_id': '750', 'source_kind': 'organiser_audio'}),
      ];
      final out = stampSourceKindOnSavedRecords(
        savedToursJson: saved,
        organiserAudioTourIds: {'750'},
      );
      expect(out, isNull);
    });

    test('a non-matching record is left alone', () {
      final saved = [
        rec({'server_tour_id': '999'}),
      ];
      final out = stampSourceKindOnSavedRecords(
        savedToursJson: saved,
        organiserAudioTourIds: {'750'},
      );
      expect(out, isNull);
    });

    test('empty id set → null (nothing to do)', () {
      final saved = [
        rec({'server_tour_id': '750'}),
      ];
      expect(
          stampSourceKindOnSavedRecords(
              savedToursJson: saved, organiserAudioTourIds: const {}),
          isNull);
    });
  });
}
