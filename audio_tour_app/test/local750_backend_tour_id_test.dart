import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/screens/edit_tour_screen.dart';

/// LOCAL-750 (A) — the second edit of a community tour must go to its numeric
/// server id, never to the local folder name.
///
/// Report (Michael, 2026-10-23): editing community tour 716 a second time
/// failed with "tour with id … can not be found". The edit service logged
/// `POST /tour/the_episode_1_…_13ed30d1/update-multiple-stops 404` three times,
/// then `POST /tour/734/update-multiple-stops 200` (a later fallback). The
/// iPhone had re-downloaded 716 from the community page, so its folder is
/// `<safeName>_<editTourId>` whose trailing token `13ed30d1` is neither a UUID
/// nor numeric — the old path-only rule fell through to the whole folder name.
///
/// [deriveBackendTourId] is the single id source the save now uses.
void main() {
  group('deriveBackendTourId', () {
    test(
        'community tour re-downloaded from the community page → numeric '
        'server_tour_id, NOT the folder name', () {
      // Michael's record: folder ends in a non-numeric, non-UUID edit id.
      final record = <String, dynamic>{
        'path':
            '/data/tours/the_episode_1_of_season_1_biking_tour__Salem__MA_-__Tour_13ed30d1',
        'server_tour_id': '716',
        'community_id': 10,
        'tour_id': '13ed30d1',
      };

      expect(deriveBackendTourId(record), '716');
    });

    test('community_id as a numeric String still prefers server_tour_id', () {
      final record = <String, dynamic>{
        'path': '/data/tours/some_tour_13ed30d1',
        'server_tour_id': '716',
        'community_id': '10',
      };
      expect(deriveBackendTourId(record), '716');
    });

    test('a folder embedding a UUID keeps the UUID (generated tour)', () {
      final record = <String, dynamic>{
        'path':
            '/data/tours/riviera_12345678-1234-1234-1234-1234567890ab',
      };
      expect(
        deriveBackendTourId(record),
        '12345678-1234-1234-1234-1234567890ab',
      );
    });

    test('a folder ending in a numeric id keeps that numeric id', () {
      final record = <String, dynamic>{
        'path': '/data/tours/old_town_734',
      };
      expect(deriveBackendTourId(record), '734');
    });

    test(
        'non-community tour whose folder is neither UUID nor numeric falls '
        'back to server_tour_id', () {
      final record = <String, dynamic>{
        'path': '/data/tours/some_tour_13ed30d1',
        'server_tour_id': '812',
      };
      expect(deriveBackendTourId(record), '812');
    });

    test('nothing usable → null (never a folder name)', () {
      final record = <String, dynamic>{
        'path': '/data/tours/some_tour_13ed30d1',
      };
      expect(deriveBackendTourId(record), isNull);
    });
  });
}
