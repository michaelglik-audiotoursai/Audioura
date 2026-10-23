// [LOCAL-746 / D675 §4 addendum] RED tests for the version-aware RE-DOWNLOAD
// planner — the pure policy behind "a member's phone picks up the organiser's
// edit of a community tour it already has".
//
// SUBMISSION_LOCAL-745 §Req 3 found: the sync-on-open never re-downloads a tour
// already on the phone (SyncPlanner.plan skips held ids; downloadAndSave returns
// alreadyOnPhone). An organiser's edit replaces the tour in place and bumps the
// server version (LOCAL-657 / LOCAL-745) — the member keeps the OLD audio.
//
// RefreshPlanner.plan is the pure fix: given the community tours ALREADY on the
// phone (each with its saved version and the server's current version), it
// returns exactly the ones to re-download — only when the server version rose,
// the member is still active (or owner), the tour was not deleted, and the
// connection allows it. Ordinary (non-community) tours are never re-downloaded.
//
// These assertions FAIL today (RefreshPlanner does not exist yet) — that is the
// red test the ticket requires.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/community_downloads.dart';

void main() {
  group('RefreshPlanner.plan — version-aware re-download (LOCAL-746)', () {
    // A held community tour at v1 whose community is active; the server now
    // reports v2 (the organiser edited it). community 1, tour 10.
    HeldCommunityTour heldSalem({
      int savedVersion = 1,
      int serverVersion = 2,
      bool isCommunityTour = true,
      int communityId = 1,
    }) =>
        HeldCommunityTour(
          tourId: 10,
          communityId: communityId,
          savedVersion: savedVersion,
          serverVersion: serverVersion,
          language: 'en',
          isCommunityTour: isCommunityTour,
          name: 'Salem Witch Walk',
        );

    test('held community tour at v1, server v2 → plans a re-download', () {
      final plan = RefreshPlanner.plan(
        held: [heldSalem()],
        activeCommunityIds: const {1},
        connection: SyncConnection.unmetered,
        cellularAllowed: false,
        deletedTourIds: const {},
      );
      expect(plan.length, 1);
      expect(plan.first.tourId, 10);
      expect(plan.first.serverVersion, 2);
      expect(plan.first.language, 'en');
      expect(plan.first.name, 'Salem Witch Walk');
    });

    test('same tour at v2/v2 → no re-download', () {
      final plan = RefreshPlanner.plan(
        held: [heldSalem(savedVersion: 2, serverVersion: 2)],
        activeCommunityIds: const {1},
        connection: SyncConnection.unmetered,
        cellularAllowed: false,
        deletedTourIds: const {},
      );
      expect(plan, isEmpty);
    });

    test('ordinary (non-community) tour v1→v2 → unchanged (never re-downloaded)',
        () {
      final plan = RefreshPlanner.plan(
        held: [heldSalem(isCommunityTour: false, communityId: 0)],
        activeCommunityIds: const {1},
        connection: SyncConnection.unmetered,
        cellularAllowed: false,
        deletedTourIds: const {},
      );
      expect(plan, isEmpty);
    });

    test('expired membership (community not active) → no re-download', () {
      final plan = RefreshPlanner.plan(
        held: [heldSalem()],
        activeCommunityIds: const {}, // membership lapsed
        connection: SyncConnection.unmetered,
        cellularAllowed: false,
        deletedTourIds: const {},
      );
      expect(plan, isEmpty);
    });

    test('owner (community id in the active/owned set) → re-download', () {
      final plan = RefreshPlanner.plan(
        held: [heldSalem()],
        activeCommunityIds: const {1}, // owner's community id is in the set
        connection: SyncConnection.unmetered,
        cellularAllowed: false,
        deletedTourIds: const {},
      );
      expect(plan.map((d) => d.tourId), [10]);
    });

    test('a tour the user deleted is never re-downloaded', () {
      final plan = RefreshPlanner.plan(
        held: [heldSalem()],
        activeCommunityIds: const {1},
        connection: SyncConnection.unmetered,
        cellularAllowed: false,
        deletedTourIds: const {'10'},
      );
      expect(plan, isEmpty);
    });

    test('nothing on a metered connection unless cellular is allowed', () {
      final blocked = RefreshPlanner.plan(
        held: [heldSalem()],
        activeCommunityIds: const {1},
        connection: SyncConnection.metered,
        cellularAllowed: false,
        deletedTourIds: const {},
      );
      expect(blocked, isEmpty);

      final allowed = RefreshPlanner.plan(
        held: [heldSalem()],
        activeCommunityIds: const {1},
        connection: SyncConnection.metered,
        cellularAllowed: true,
        deletedTourIds: const {},
      );
      expect(allowed.length, 1);
    });

    test('nothing when offline', () {
      final plan = RefreshPlanner.plan(
        held: [heldSalem()],
        activeCommunityIds: const {1},
        connection: SyncConnection.none,
        cellularAllowed: true,
        deletedTourIds: const {},
      );
      expect(plan, isEmpty);
    });

    test('a server version LOWER than saved is ignored (never downgrade)', () {
      final plan = RefreshPlanner.plan(
        held: [heldSalem(savedVersion: 3, serverVersion: 2)],
        activeCommunityIds: const {1},
        connection: SyncConnection.unmetered,
        cellularAllowed: false,
        deletedTourIds: const {},
      );
      expect(plan, isEmpty);
    });
  });

  group('refreshedMessage (LOCAL-746 Req 3)', () {
    test('one short message names the tour and the organiser', () {
      expect(
        refreshedMessage('Salem Witch Walk'),
        'Salem Witch Walk was updated by the organiser.',
      );
    });
  });
}
