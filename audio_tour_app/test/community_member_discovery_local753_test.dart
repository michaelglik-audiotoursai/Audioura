// [LOCAL-753 / D706, D707] App-side pure unit tests (no running app, no network).
//
//   * OwnedCommunity now carries its community visibility ('listed' | 'private')
//     so the Generate "For:" selector can preselect PUBLIC for a listed
//     community (D706) — members-only stays selectable; a private community
//     keeps the members default.
//   * CommunityTourRules.initialVisibilityFor(community) is the pure rule:
//       listed  → 'public'   (D706 app-side default);
//       private → 'members'  (unchanged);
//   * CommunityInviteTourOption now parses the server's `languages` list
//     (LOCAL-752 A2) so the community page can show one row per tour with its
//     languages and offer a Translate for the ones not yet present.
//   * CommunityTourRules.translateCandidates(present) returns the translation
//     languages NOT already present (D707 community-page Translate), drawn from
//     the SAME canonical list Listen → Translate uses.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/community_tour_models.dart';
import 'package:audio_tour_app_dev/services/communities_models.dart';

void main() {
  group('OwnedCommunity visibility + Generate preselect (D706)', () {
    test('OwnedCommunity carries listed/private visibility', () {
      const listed = OwnedCommunity(id: 1, name: 'Danvers', visibility: 'listed');
      const private = OwnedCommunity(id: 2, name: 'Owls', visibility: 'private');
      expect(listed.visibility, 'listed');
      expect(private.visibility, 'private');
    });

    test('default visibility is private (safe) when unspecified', () {
      const c = OwnedCommunity(id: 3, name: 'X');
      expect(c.visibility, 'private');
    });

    test('initialVisibilityFor: listed → public, private → members', () {
      const listed = OwnedCommunity(id: 1, name: 'Danvers', visibility: 'listed');
      const private = OwnedCommunity(id: 2, name: 'Owls', visibility: 'private');
      expect(CommunityTourRules.initialVisibilityFor(listed), 'public');
      expect(CommunityTourRules.initialVisibilityFor(private), 'members');
    });

    test('a listed community target still allows a members-only choice', () {
      // D706: public is the default, but the organiser may still choose members.
      const t = CommunityTourTarget(
        community: OwnedCommunity(id: 1, name: 'Danvers', visibility: 'listed'),
        visibility: 'members',
      );
      expect(t.generateFields()['community_visibility'], 'members');
    });
  });

  group('CommunityInviteTourOption languages (LOCAL-752 A2 → app)', () {
    test('parses the server languages list, original first', () {
      final t = CommunityInviteTourOption.fromJson(const {
        'id': 736,
        'name': 'Danvers Loop',
        'languages': ['en', 'ru', 'fr'],
      });
      expect(t.languages, ['en', 'ru', 'fr']);
    });

    test('missing languages → empty list (defensive)', () {
      final t = CommunityInviteTourOption.fromJson(const {
        'id': 1,
        'name': 'X',
      });
      expect(t.languages, isEmpty);
    });
  });

  group('Community-page Translate candidates (D707)', () {
    test('offers only languages not already present', () {
      // present: English original + an existing Russian translation.
      final cand = CommunityTourRules.translateCandidates(const ['en', 'ru']);
      expect(cand.contains('ru'), isFalse,
          reason: 'an existing language must not be re-offered');
      expect(cand.contains('en'), isFalse,
          reason: 'English (the original) is never a translation target');
      expect(cand.contains('fr'), isTrue);
      // Every candidate is one of the canonical translation languages.
      for (final c in cand) {
        expect(CommunityTourRules.translateLanguageCodes.contains(c), isTrue);
      }
    });

    test('all candidates offered when only the original exists', () {
      final cand = CommunityTourRules.translateCandidates(const ['en']);
      // 10 canonical languages, none present yet.
      expect(cand.length, CommunityTourRules.translateLanguageCodes.length);
    });
  });
}
