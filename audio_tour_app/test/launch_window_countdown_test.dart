// [LOCAL-703 / D664] Launch-window countdown — pure helper + parsing tests.
//
// These cover the Flutter-side launch rules without a running app or network:
//   * launchCountdown copy: the EXACT organiser countdown line, paid vs free,
//     and the green "Launched 🎉" once the bar is met.
//   * createLaunchRule: the one-week / two-members rule stated on the Create
//     screen (paid vs free wording).
//   * communityClosed: the exact "This community has closed." message for a
//     410 community_closed.
//   * CommunityLaunch parsing from the server `launch` block, and a
//     CodeResolution distinguishing found / closed / not-found.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/communities_models.dart';

void main() {
  group('CommunityCopy.launchCountdown', () {
    test('paid, before launch — exact spec wording', () {
      expect(
        CommunityCopy.launchCountdown(
          launched: false,
          paid: true,
          hoursLeft: 152,
          membersSoFar: 1,
          membersNeeded: 2,
        ),
        '152 h left to get 2 paid members — 1 of 2 so far',
      );
    });

    test('free, before launch — "members" (no "paid")', () {
      expect(
        CommunityCopy.launchCountdown(
          launched: false,
          paid: false,
          hoursLeft: 152,
          membersSoFar: 1,
          membersNeeded: 2,
        ),
        '152 h left to get 2 members — 1 of 2 so far',
      );
    });

    test('zero members so far reads "0 of 2"', () {
      expect(
        CommunityCopy.launchCountdown(
          launched: false,
          paid: true,
          hoursLeft: 168,
          membersSoFar: 0,
          membersNeeded: 2,
        ),
        '168 h left to get 2 paid members — 0 of 2 so far',
      );
    });

    test('launched — green success line, paid/free irrelevant', () {
      expect(
        CommunityCopy.launchCountdown(
          launched: true,
          paid: true,
          hoursLeft: 0,
          membersSoFar: 2,
          membersNeeded: 2,
        ),
        'Launched 🎉',
      );
      expect(
        CommunityCopy.launchCountdown(
          launched: true,
          paid: false,
          hoursLeft: 10,
          membersSoFar: 3,
          membersNeeded: 2,
        ),
        'Launched 🎉',
      );
    });
  });

  group('CommunityCopy.createLaunchRule', () {
    test('paid mentions "paid members"', () {
      final r = CommunityCopy.createLaunchRule(paid: true);
      expect(r.contains('paid members'), isTrue);
      expect(r.contains('one week'), isTrue);
      expect(r.contains('2'), isTrue);
    });

    test('free mentions "members" but not "paid members"', () {
      final r = CommunityCopy.createLaunchRule(paid: false);
      expect(r.contains('members'), isTrue);
      expect(r.contains('paid members'), isFalse);
    });
  });

  test('CommunityCopy.communityClosed is the exact message', () {
    expect(CommunityCopy.communityClosed, 'This community has closed.');
  });

  group('CommunityLaunch.fromJson', () {
    test('parses a full launch block', () {
      final l = CommunityLaunch.fromJson({
        'deadline': '2026-10-22T17:00:00+00:00',
        'hours_left': 152,
        'members_needed': 2,
        'members_so_far': 1,
        'launched': false,
        'launched_at': null,
      });
      expect(l.hoursLeft, 152);
      expect(l.membersNeeded, 2);
      expect(l.membersSoFar, 1);
      expect(l.launched, isFalse);
      expect(l.deadline, '2026-10-22T17:00:00+00:00');
    });

    test('null block degrades to sane defaults (needed=2)', () {
      final l = CommunityLaunch.fromJson(null);
      expect(l.hoursLeft, 0);
      expect(l.membersNeeded, 2);
      expect(l.membersSoFar, 0);
      expect(l.launched, isFalse);
    });

    test('Community.fromJson wires the launch block through', () {
      final c = Community.fromJson({
        'id': 7,
        'name': 'TEST Launch',
        'is_paid': true,
        'launch': {
          'deadline': '2026-10-22T17:00:00+00:00',
          'hours_left': 100,
          'members_needed': 2,
          'members_so_far': 2,
          'launched': true,
          'launched_at': '2026-10-16T09:00:00+00:00',
        },
      });
      expect(c.launch.launched, isTrue);
      expect(c.launch.membersSoFar, 2);
      // And the countdown renders the success line for a launched community.
      expect(
        CommunityCopy.launchCountdown(
          launched: c.launch.launched,
          paid: c.isPaid,
          hoursLeft: c.launch.hoursLeft,
          membersSoFar: c.launch.membersSoFar,
          membersNeeded: c.launch.membersNeeded,
        ),
        'Launched 🎉',
      );
    });
  });

  group('CodeResolution', () {
    test('found carries the community', () {
      final r = CodeResolution(
          community: Community.fromJson({'id': 1, 'name': 'X'}));
      expect(r.found, isTrue);
      expect(r.closed, isFalse);
    });

    test('closed is the 410 state (no community)', () {
      const r = CodeResolution(closed: true);
      expect(r.found, isFalse);
      expect(r.closed, isTrue);
    });

    test('default is not-found', () {
      const r = CodeResolution();
      expect(r.found, isFalse);
      expect(r.closed, isFalse);
    });
  });
}
