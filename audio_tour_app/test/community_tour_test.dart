// [LOCAL-701 / D663 §3] Community tour models + Generate-tab rules — pure unit
// tests (no running app, no network).
//
//   * CommunityTourTarget.generateFields: "Just me" adds nothing; a community
//     target adds community_id + community_visibility.
//   * CommunityTourRules: selector shows only for an organiser; the labels and
//     visibility hints; a public tour needs a location to generate.
//   * CommunityTour / CommunityTourList JSON parsing is defensive.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/community_tour_models.dart';

void main() {
  group('CommunityTourTarget.generateFields', () {
    test('"Just me" default adds no fields (ordinary generation)', () {
      expect(CommunityTourTarget.justMe.generateFields(), isEmpty);
      expect(CommunityTourTarget.justMe.isCommunity, isFalse);
    });

    test('a members target adds community_id + members visibility', () {
      const t = CommunityTourTarget(
        community: OwnedCommunity(id: 7, name: 'The Owls'),
        visibility: 'members',
      );
      expect(t.isCommunity, isTrue);
      expect(t.isPublic, isFalse);
      expect(t.generateFields(),
          {'community_id': 7, 'community_visibility': 'members'});
    });

    test('a public target adds community_id + public visibility', () {
      const t = CommunityTourTarget(
        community: OwnedCommunity(id: 9, name: 'Ramblers'),
        visibility: 'public',
      );
      expect(t.isPublic, isTrue);
      expect(t.generateFields(),
          {'community_id': 9, 'community_visibility': 'public'});
    });

    test('an unknown visibility is coerced to members (safe default)', () {
      const t = CommunityTourTarget(
        community: OwnedCommunity(id: 3, name: 'X'),
        visibility: 'nonsense',
      );
      expect(t.generateFields()['community_visibility'], 'members');
    });
  });

  group('CommunityTourRules', () {
    test('selector hidden with no owned communities, shown with ≥ 1', () {
      expect(CommunityTourRules.selectorVisible(const []), isFalse);
      expect(
          CommunityTourRules.selectorVisible(
              const [OwnedCommunity(id: 1, name: 'A')]),
          isTrue);
    });

    test('labels', () {
      expect(CommunityTourRules.justMeLabel, 'Just me / public as usual');
      expect(CommunityTourRules.communityLabel('The Owls'),
          'For: my community The Owls');
    });

    test('visibility hints differ for members vs public', () {
      expect(CommunityTourRules.visibilityHint('members'),
          contains('community page'));
      expect(CommunityTourRules.visibilityHint('public'), contains('map'));
    });

    test('canGenerate: Just me always; public needs a location', () {
      expect(
          CommunityTourRules.canGenerate(CommunityTourTarget.justMe,
              hasLocation: false),
          isTrue);
      const members = CommunityTourTarget(
          community: OwnedCommunity(id: 1, name: 'A'), visibility: 'members');
      expect(CommunityTourRules.canGenerate(members, hasLocation: false),
          isTrue);
      const public = CommunityTourTarget(
          community: OwnedCommunity(id: 1, name: 'A'), visibility: 'public');
      expect(CommunityTourRules.canGenerate(public, hasLocation: false),
          isFalse);
      expect(CommunityTourRules.canGenerate(public, hasLocation: true), isTrue);
    });
  });

  group('CommunityTour / CommunityTourList JSON', () {
    test('CommunityTour parses and reports public', () {
      final t = CommunityTour.fromJson({
        'id': 42,
        'name': 'Harbour Walk',
        'request_string': 'harbour walk',
        'lat': 43.7,
        'lng': 7.26,
        'visibility': 'public',
        'content_rating': 'general',
      });
      expect(t.id, 42);
      expect(t.isPublic, isTrue);
      expect(t.contentRating, 'general');
    });

    test('missing fields never throw; defaults applied', () {
      final t = CommunityTour.fromJson(const {});
      expect(t.id, 0);
      expect(t.visibility, 'members');
      expect(t.isPublic, isFalse);
      expect(t.contentRating, 'general');
    });

    test('CommunityTourList gates on isMember', () {
      final list = CommunityTourList.fromJson({
        'community_id': 7,
        'is_member': true,
        'tours': [
          {'id': 1, 'name': 'A', 'visibility': 'members'},
          {'id': 2, 'name': 'B', 'visibility': 'public'},
        ],
      });
      expect(list.communityId, 7);
      expect(list.isMember, isTrue);
      expect(list.tours.map((t) => t.id), [1, 2]);
    });

    test('a non-member list is empty', () {
      final list = CommunityTourList.fromJson(
          {'community_id': 7, 'is_member': false, 'tours': []});
      expect(list.isMember, isFalse);
      expect(list.tours, isEmpty);
    });
  });
}
