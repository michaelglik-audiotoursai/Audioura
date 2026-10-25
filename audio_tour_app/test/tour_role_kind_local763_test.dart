// [LOCAL-763 / D711 §2] Unit tests for the role line's COLOUR KIND — the bright
// chip's colour family depends on the relationship (Michael 2026-10-25: "make
// it in colour and bright; colours may depend on what it says"). These pin the
// pure mapping in tourRoleLabel so a widget never has to re-derive it.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/utils/tour_role_label.dart';

void main() {
  const me = 'USER-41659366';

  group('[LOCAL-763] tourRoleLabel colour kind', () {
    test('your own plain tour → ownBlue', () {
      expect(tourRoleLabel({'is_owner': true}, me).kind, TourRoleKind.ownBlue);
    });

    test('your community tour, you are the organiser → organiserGreen', () {
      final r = tourRoleLabel({
        'is_owner': true,
        'is_community': true,
        'is_organiser': true,
        'community_name': 'Salem TV show funs',
      }, me);
      expect(r.kind, TourRoleKind.organiserGreen);
    });

    test('a community tour you did not create → communityGreen (outline)', () {
      final r = tourRoleLabel({
        'is_owner': false,
        'is_community': true,
        'is_organiser': false,
        'community_id': 10,
        'community_name': 'Salem TV show funs',
        'community_visibility': 'members',
      }, me);
      expect(r.kind, TourRoleKind.communityGreen);
    });

    test('a community tour where you ARE the organiser → organiserGreen', () {
      final r = tourRoleLabel({
        'is_owner': false,
        'is_community': true,
        'is_organiser': true,
        'community_id': 10,
        'community_name': 'Salem TV show funs',
      }, me);
      expect(r.kind, TourRoleKind.organiserGreen);
    });

    test('your own community tour, not organiser → communityGreen', () {
      final r = tourRoleLabel({
        'is_owner': true,
        'is_community': true,
        'is_organiser': false,
        'community_name': 'Owls',
      }, me);
      expect(r.kind, TourRoleKind.communityGreen);
    });

    test('a broadcast tour → broadcastPurple', () {
      final r = tourRoleLabel({
        'source_kind': 'organiser_audio',
        'community_name': 'Owls',
      }, me);
      expect(r.kind, TourRoleKind.broadcastPurple);
    });

    test('a plain Audioura tour → audiouraGrey', () {
      expect(tourRoleLabel({}, me).kind, TourRoleKind.audiouraGrey);
    });
  });
}
