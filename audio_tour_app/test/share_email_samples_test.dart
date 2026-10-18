import 'package:flutter_test/flutter_test.dart';
import '../lib/utils/share_code.dart';
import '../lib/services/communities_models.dart';

/// [LOCAL-710 / D672 → LOCAL-711 / D673] Prints the EXACT subject + body the real
/// code produces for Michael's four samples, built from the real DB tour names +
/// stops, now with the SERVER short_title passed in (D673) and the translation
/// offer line in every message:
///   • FREE tour FFush25U — Faneuil Hall Marketplace (server tour 365, 3 stops,
///     first stop "Quincy Market", 4 S Market St, Boston, MA 02109).
///   • PAID tour Wo8Oj8lA — $4.99 (server tour 557, 5 stops, first stop
///     "Old State House", 206 Washington St, Boston, MA 02109, price_tier 3).
///   • COMMUNITY tour from community 2 "Demo Boston Walkers" (real Faneuil Hall
///     stops, shared as a community tour).
///   • The COMMUNITY 2 invite (0 members in the DB → no member-count line).
///
/// The SHORT TITLES used here are the ones tour_short_title.py produced in the
/// LOCAL-711 live test (read-only, one cheap call each) — see
/// SUBMISSION_LOCAL-711.md. Where the server has none, the app falls back to
/// shortTourTitle(); that fallback is covered in share_code_test.dart.
///
/// The output of this test is pasted verbatim into SHARE_EMAIL_SAMPLES_LOCAL-711.md.
/// Run:
///   flutter test test/share_email_samples_test.dart --plain-name 'PRINT SAMPLES'
void main() {
  // Raw names exactly as stored in audio_tours (verified by SELECT).
  const faneuilRaw =
      'Faneuil Hall Marketplace, Boston MA, with a stop at Quincy Market and a '
      'stop at the Samuel Adams statue and a stop at the Boston Massacre site '
      '- Walking Tour';
  const politicsRaw =
      'Walking tour in Boston dedicated to Massachusetts politics and current '
      'affairs, Boston, MA - walking Tour';

  // [LOCAL-711 / D673] The server-written short titles for these two tours,
  // from the live make_short_title run (gpt-4o-mini). Passed in as the title —
  // buildShareTourDetails prefers a non-empty server short_title over
  // shortTourTitle(rawName). Fill these with the live values in the submission.
  const faneuilShort = 'Faneuil Hall Marketplace — Walking Tour';
  const politicsShort = 'Massachusetts Politics — Walking Tour';

  final free = ShareTourDetails(
    title: faneuilShort,
    code: 'FFush25U',
    kind: ShareTourKind.free,
    stopCount: 3,
    firstStopName: 'Quincy Market',
    firstStopLocation: '4 S Market St, Boston, MA 02109',
    city: cityFromLocation('4 S Market St, Boston, MA 02109', faneuilRaw),
    tourType: tourTypeFromName(faneuilRaw),
  );

  final paid = ShareTourDetails(
    title: politicsShort,
    code: 'Wo8Oj8lA',
    kind: ShareTourKind.paid,
    price: '\$4.99',
    stopCount: 5,
    firstStopName: 'Old State House',
    firstStopLocation: '206 Washington St, Boston, MA 02109',
    city: cityFromLocation('206 Washington St, Boston, MA 02109', politicsRaw),
    tourType: tourTypeFromName(politicsRaw),
  );

  final community = ShareTourDetails(
    title: faneuilShort,
    code: 'FFush25U',
    kind: ShareTourKind.community,
    communityName: 'Demo Boston Walkers',
    stopCount: 3,
    firstStopName: 'Quincy Market',
    firstStopLocation: '4 S Market St, Boston, MA 02109',
    city: cityFromLocation('4 S Market St, Boston, MA 02109', faneuilRaw),
    tourType: tourTypeFromName(faneuilRaw),
  );

  void dump(String label, ShareTourDetails d) {
    // ignore: avoid_print
    print('\n===== $label =====');
    // ignore: avoid_print
    print('SUBJECT: ${buildShareSubject(d)}');
    // ignore: avoid_print
    print('BODY:\n${buildShareMessage(d)}');
  }

  test('PRINT SAMPLES', () {
    dump('FREE — FFush25U (Faneuil Hall)', free);
    dump('PAID — Wo8Oj8lA (\$4.99)', paid);
    dump('COMMUNITY — from "Demo Boston Walkers" (community 2)', community);

    // ── [LOCAL-710B / D672 addenda 1 + 2] The SELF-EXPLAINING community invites,
    //    built from the communities' REAL DB settings (read-only SELECT):
    //      • community 2 "Demo Boston Walkers": is_paid, LISTED, no waiver,
    //        rules "Members only. Share the invite code …", cheapest pass
    //        $5 / week, join code 0tdZGgXg, 0 members, NO tours.
    //      • community 1 "Demo Book Club — The Art of War": is_paid, PRIVATE,
    //        no waiver, rules "Be kind in discussions. One chapter per week.",
    //        cheapest pass $1 / month, join code 1v7UDLsL, 0 members, NO tours.
    //    Neither community has any audio_tours (community_id all NULL), so the
    //    tour line is omitted for both — exactly the "no tours → line left out"
    //    rule. A picked-tour sample follows as a labelled FIXTURE.

    // Community 2 — Demo Boston Walkers (paid, listed, rules, $5/week).
    final invite2 = CommunityCopy.emailInviteBody(
      communityName: 'Demo Boston Walkers',
      description:
          'A demo PAID community: weekly walking stories around Boston. '
          'Try a pass with TEST PURCHASE.',
      organiserName: 'Michael (demo)',
      code: '0tdZGgXg',
      memberCount: 0,
      isPaid: true,
      visibility: 'listed',
      hasWaiver: false,
      rulesText: 'Members only. Share the invite code with friends who joined.',
      cheapestPassPrice: '\$5',
      cheapestPassLength: 'week',
    );
    // ignore: avoid_print
    print('\n===== COMMUNITY 2 INVITE — "Demo Boston Walkers" (0 members, no tours) =====');
    // ignore: avoid_print
    print('SUBJECT: ${CommunityCopy.emailInviteSubject("Demo Boston Walkers")}');
    // ignore: avoid_print
    print('EMAIL BODY:\n$invite2');

    // Community 1 — Demo Book Club (paid, private, rules, $1/month).
    final invite1 = CommunityCopy.emailInviteBody(
      communityName: 'Demo Book Club — The Art of War',
      description:
          "A demo free community: listen to Sun Tzu's The Art of War "
          'together, one chapter a week.',
      organiserName: 'Michael (demo)',
      code: '1v7UDLsL',
      memberCount: 0,
      isPaid: true,
      visibility: 'private',
      hasWaiver: false,
      rulesText: 'Be kind in discussions. One chapter per week.',
      cheapestPassPrice: '\$1',
      cheapestPassLength: 'month',
    );
    // ignore: avoid_print
    print('\n===== COMMUNITY 1 INVITE — "Demo Book Club — The Art of War" (0 members, no tours) =====');
    // ignore: avoid_print
    print('SUBJECT: ${CommunityCopy.emailInviteSubject("Demo Book Club — The Art of War")}');
    // ignore: avoid_print
    print('EMAIL BODY:\n$invite1');

    // Picked-/latest-tour sample. NO real community tour exists in the DB
    // (every audio_tours.community_id is NULL), so this is a LABELLED FIXTURE:
    // community 2 with a latest tour included. The tour's share code TourFix1
    // is a fixture (in production it comes from TourShareService.share).
    final inviteWithTour = CommunityCopy.emailInviteBody(
      communityName: 'Demo Boston Walkers',
      description:
          'A demo PAID community: weekly walking stories around Boston. '
          'Try a pass with TEST PURCHASE.',
      organiserName: 'Michael (demo)',
      code: '0tdZGgXg',
      memberCount: 0,
      isPaid: true,
      visibility: 'listed',
      hasWaiver: false,
      rulesText: 'Members only. Share the invite code with friends who joined.',
      cheapestPassPrice: '\$5',
      cheapestPassLength: 'week',
      tour: const CommunityInviteTour(
        title: 'Faneuil Hall Marketplace — Walking Tour',
        code: 'TourFix1',
        stopCount: 3,
        picked: false,
      ),
    );
    // ignore: avoid_print
    print('\n===== COMMUNITY 2 INVITE WITH LATEST TOUR (FIXTURE — no real community tour in DB) =====');
    // ignore: avoid_print
    print('EMAIL BODY:\n$inviteWithTour');

    // Sanity: subjects match, each invite round-trips its JOIN code out.
    expect(CommunityCopy.emailInviteSubject('Demo Boston Walkers'),
        'Join "Demo Boston Walkers" on Audioura');
    // Every tour sample still round-trips the code out.
    for (final d in [free, paid, community]) {
      expect(extractShareCode(buildShareMessage(d)), d.code);
    }
    expect(extractShareCode(invite2), '0tdZGgXg');
    expect(extractShareCode(invite1), '1v7UDLsL');
    // With a tour, the LAST code-shaped token is still the join code.
    expect(extractShareCode(inviteWithTour), '0tdZGgXg');
    // The invites explain themselves and quote the real cheapest pass.
    expect(invite2.contains(kCommunityExplanation), isTrue);
    expect(invite2.contains(
        'Membership is paid: a pass starts at \$5 for a week, bought in the app.'),
        isTrue);
    expect(invite1.contains(
        'Membership is paid: a pass starts at \$1 for a month, bought in the app.'),
        isTrue);
    expect(inviteWithTour.contains(
        'Latest tour: "Faneuil Hall Marketplace — Walking Tour", 3 stops: https://audioura.com/t/TourFix1'),
        isTrue);
  });
}
