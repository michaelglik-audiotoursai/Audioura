// [LOCAL-762 / D711 §2] Unit tests for tourRoleLabel — one case per role line.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/utils/tour_role_label.dart';

void main() {
  const me = 'USER-41659366';

  group('[LOCAL-762] tourRoleLabel', () {
    test('your own plain tour → "Your tour"', () {
      final r = tourRoleLabel({'is_owner': true}, me);
      expect(r.text, 'Your tour');
      expect(r.icon, TourRoleIcon.person);
    });

    test('your own community tour, you are the organiser', () {
      final r = tourRoleLabel({
        'is_owner': true,
        'is_community': true,
        'is_organiser': true,
        'community_name': 'Salem TV show funs',
        'community_visibility': 'public',
      }, me);
      expect(r.text, 'Your community tour — you are the organiser');
      expect(r.icon, TourRoleIcon.group);
    });

    test('a community tour you did not create → "Community tour · <name>"', () {
      final r = tourRoleLabel({
        'is_owner': false,
        'is_community': true,
        'is_organiser': false,
        'community_id': 10,
        'community_name': 'Salem TV show funs',
        'community_visibility': 'members',
      }, me);
      expect(r.text, 'Community tour · Salem TV show funs');
      expect(r.icon, TourRoleIcon.group);
    });

    test('a broadcast tour (member view) → "Broadcast tour · <name>"', () {
      final r = tourRoleLabel({
        'is_owner': false,
        'is_community': true,
        'is_organiser': false,
        'is_broadcast': true,
        'source_kind': 'organiser_audio',
        'community_name': 'Salem TV show funs',
        'community_visibility': 'members',
      }, me);
      expect(r.text, 'Broadcast tour · Salem TV show funs');
      expect(r.icon, TourRoleIcon.broadcast);
    });

    test('a broadcast tour where you are the organiser', () {
      final r = tourRoleLabel({
        'is_owner': true,
        'is_community': true,
        'is_organiser': true,
        'is_broadcast': true,
        'source_kind': 'organiser_audio',
        'community_name': 'Salem TV show funs',
      }, me);
      expect(r.text, 'Broadcast tour · Salem TV show funs — you are the organiser');
      expect(r.icon, TourRoleIcon.broadcast);
    });

    test('a broadcast tour inferred from source_kind alone (no is_broadcast)',
        () {
      final r = tourRoleLabel({
        'source_kind': 'organiser_audio',
        'community_name': 'Owls',
      }, me);
      expect(r.text, 'Broadcast tour · Owls');
      expect(r.icon, TourRoleIcon.broadcast);
    });

    test('a plain Audioura tour (no role fields) → "Audioura tour"', () {
      final r = tourRoleLabel({}, me);
      expect(r.text, 'Audioura tour');
      expect(r.icon, TourRoleIcon.audioura);
    });

    test('a downloaded Audioura tour you did not create → "Audioura tour"', () {
      final r = tourRoleLabel({
        'is_owner': false,
        'is_community': false,
      }, me);
      expect(r.text, 'Audioura tour');
      expect(r.icon, TourRoleIcon.audioura);
    });

    test('a broadcast tour with no community name still reads sensibly', () {
      final r = tourRoleLabel({'is_broadcast': true}, me);
      expect(r.text, 'Broadcast tour');
      expect(r.icon, TourRoleIcon.broadcast);
    });

    test('never throws on odd types (defensive reads)', () {
      final r = tourRoleLabel({
        'is_owner': 'yes', // not a bool → treated as false
        'community_id': 'x',
        'community_name': 123, // not a string → ignored
      }, null);
      expect(r.text, 'Audioura tour');
    });
  });
}
