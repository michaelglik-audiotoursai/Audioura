// [LOCAL-755] RED tests for organiser-audio tour UPDATES on the member side.
//
// Organiser-audio tours (source_kind='organiser_audio', LOCAL-754B) are edited
// on the organiser's own site, never through our voice pipeline, and members are
// NEVER pushed an update (even with auto-download on). Instead a member opts in
// by tapping "Re-download". So:
//
//   Rule 1 — the Listen ⋮ Edit is HIDDEN for an organiser-audio tour
//            (canEditTour returns false, even for the owner).
//   Rule 3 — RefreshPlanner SKIPS organiser-audio held tours (they are never
//            auto-re-downloaded), while a generated community tour at a higher
//            server version is still planned (today's behaviour, Rule 4).
//   Rule 3 — the Listen/community row offers "Updated by the organiser —
//            Re-download" when the server version rose above the saved one.
//
// These assertions FAIL on 1942ea37: HeldCommunityTour has no isOrganiserAudio
// field (RefreshPlanner cannot skip them), canEditTour does not consider
// source_kind, and organiserAudioUpdateLabel does not exist. They pass once
// LOCAL-755 lands.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/community_downloads.dart';
import 'package:audio_tour_app_dev/screens/my_tours_screen.dart'
    show canEditTour, isOrganiserAudioTour, organiserAudioReDownloadLabel;

void main() {
  group('RefreshPlanner skips organiser-audio tours (LOCAL-755 Rule 3)', () {
    HeldCommunityTour held({
      required bool isOrganiserAudio,
      int savedVersion = 1,
      int serverVersion = 2,
    }) =>
        HeldCommunityTour(
          tourId: 10,
          communityId: 1,
          savedVersion: savedVersion,
          serverVersion: serverVersion,
          language: 'en',
          isCommunityTour: true,
          isOrganiserAudio: isOrganiserAudio,
          name: 'Salem Audio Walk',
        );

    test('organiser-audio held tour v1→v2 is NOT planned (never pushed)', () {
      final plan = RefreshPlanner.plan(
        held: [held(isOrganiserAudio: true)],
        activeCommunityIds: const {1},
        connection: SyncConnection.unmetered,
        cellularAllowed: false,
        deletedTourIds: const {},
      );
      expect(plan, isEmpty,
          reason: 'a member is never pushed an organiser-audio update');
    });

    test('a GENERATED community tour v1→v2 is still planned (Rule 4)', () {
      final plan = RefreshPlanner.plan(
        held: [held(isOrganiserAudio: false)],
        activeCommunityIds: const {1},
        connection: SyncConnection.unmetered,
        cellularAllowed: false,
        deletedTourIds: const {},
      );
      expect(plan.length, 1);
      expect(plan.first.tourId, 10);
    });

    test('mixed: only the generated tour is planned', () {
      final generated = HeldCommunityTour(
        tourId: 20,
        communityId: 1,
        savedVersion: 1,
        serverVersion: 3,
        language: 'en',
        isCommunityTour: true,
        isOrganiserAudio: false,
        name: 'Generated Tour',
      );
      final plan = RefreshPlanner.plan(
        held: [held(isOrganiserAudio: true), generated],
        activeCommunityIds: const {1},
        connection: SyncConnection.unmetered,
        cellularAllowed: false,
        deletedTourIds: const {},
      );
      expect(plan.map((p) => p.tourId), [20]);
    });
  });

  group('canEditTour hides Edit for organiser-audio (LOCAL-755 Rule 1)', () {
    test('organiser-audio tour is NOT editable even by the owner', () {
      final tour = {
        'community_id': 7,
        'source_kind': 'organiser_audio',
      };
      expect(
        canEditTour(tour, ownedCommunityIds: {7}),
        isFalse,
        reason: 'editing an organiser-audio tour never goes through our pipeline',
      );
    });

    test('a generated community tour stays editable by its owner', () {
      final tour = {'community_id': 7};
      expect(canEditTour(tour, ownedCommunityIds: {7}), isTrue);
    });

    test('isOrganiserAudioTour recognises the source marker', () {
      expect(isOrganiserAudioTour({'source_kind': 'organiser_audio'}), isTrue);
      expect(isOrganiserAudioTour({'source_kind': ''}), isFalse);
      expect(isOrganiserAudioTour(const {}), isFalse);
    });
  });

  group('organiserAudioUpdateLabel — the Re-download row (LOCAL-755 Rule 3)',
      () {
    test('shows the Re-download label when the server version rose', () {
      expect(
        organiserAudioUpdateLabel(savedVersion: 1, serverVersion: 2),
        'Updated by the organiser — Re-download',
      );
    });

    test('no label when the server version is unchanged', () {
      expect(
        organiserAudioUpdateLabel(savedVersion: 2, serverVersion: 2),
        isNull,
      );
    });

    test('no label when the server version is lower (never a downgrade)', () {
      expect(
        organiserAudioUpdateLabel(savedVersion: 3, serverVersion: 2),
        isNull,
      );
    });
  });

  group('OrganiserAudioUpdatePlanner — opt-in, never pushed (LOCAL-755 Rule 3)',
      () {
    HeldCommunityTour oa({
      int savedVersion = 1,
      int serverVersion = 2,
      bool isOrganiserAudio = true,
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
          isOrganiserAudio: isOrganiserAudio,
          name: 'Salem Audio Walk',
        );

    test('an organiser-audio tour whose version rose is OFFERED (not pushed)',
        () {
      final offers = OrganiserAudioUpdatePlanner.plan(
        held: [oa()],
        activeCommunityIds: const {1},
        deletedTourIds: const {},
      );
      expect(offers.length, 1);
      expect(offers.first.tourId, 10);
      expect(offers.first.serverVersion, 2);
      expect(offers.first.name, 'Salem Audio Walk');
    });

    test('a GENERATED tour is NOT an organiser-audio offer (it auto-refreshes)',
        () {
      final offers = OrganiserAudioUpdatePlanner.plan(
        held: [oa(isOrganiserAudio: false)],
        activeCommunityIds: const {1},
        deletedTourIds: const {},
      );
      expect(offers, isEmpty);
    });

    test('no offer when the version is unchanged', () {
      final offers = OrganiserAudioUpdatePlanner.plan(
        held: [oa(savedVersion: 2, serverVersion: 2)],
        activeCommunityIds: const {1},
        deletedTourIds: const {},
      );
      expect(offers, isEmpty);
    });

    test('no offer when the membership lapsed', () {
      final offers = OrganiserAudioUpdatePlanner.plan(
        held: [oa()],
        activeCommunityIds: const {},
        deletedTourIds: const {},
      );
      expect(offers, isEmpty);
    });

    test('no offer for a tour the user deleted', () {
      final offers = OrganiserAudioUpdatePlanner.plan(
        held: [oa()],
        activeCommunityIds: const {1},
        deletedTourIds: const {'10'},
      );
      expect(offers, isEmpty);
    });
  });

  group('organiserAudioReDownloadLabel — Listen row (LOCAL-755 Rule 3)', () {
    test('organiser-audio tour with a higher pending version shows the label',
        () {
      final tour = {
        'source_kind': 'organiser_audio',
        'version': 1,
        'pending_organiser_version': 2,
        'server_tour_id': '10',
      };
      expect(organiserAudioReDownloadLabel(tour),
          'Updated by the organiser — Re-download');
    });

    test('no label when there is no pending version', () {
      final tour = {'source_kind': 'organiser_audio', 'version': 2};
      expect(organiserAudioReDownloadLabel(tour), isNull);
    });

    test('a generated tour never shows the organiser label', () {
      final tour = {'version': 1, 'pending_organiser_version': 2};
      expect(organiserAudioReDownloadLabel(tour), isNull);
    });
  });
}
