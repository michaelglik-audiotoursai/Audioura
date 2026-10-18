import 'package:flutter_test/flutter_test.dart';
import '../lib/utils/share_code.dart';
import '../lib/services/communities_models.dart';

/// [LOCAL-710 / D672] Prints the EXACT subject + body the real code produces for
/// Michael's four samples, built from the real DB tour names + stops:
///   • FREE tour FFush25U — Faneuil Hall Marketplace (server tour 365, 3 stops,
///     first stop "Quincy Market", 4 S Market St, Boston, MA 02109).
///   • PAID tour Wo8Oj8lA — $4.99 (server tour 557, 5 stops, first stop
///     "Old State House", 206 Washington St, Boston, MA 02109, price_tier 3).
///   • COMMUNITY tour from community 2 "Demo Boston Walkers" (real Faneuil Hall
///     stops, shared as a community tour).
///   • The COMMUNITY 2 invite (0 members in the DB → no member-count line).
///
/// The output of this test is pasted verbatim into SHARE_EMAIL_SAMPLES_LOCAL-710.md.
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

  final free = ShareTourDetails(
    title: shortTourTitle(faneuilRaw),
    code: 'FFush25U',
    kind: ShareTourKind.free,
    stopCount: 3,
    firstStopName: 'Quincy Market',
    firstStopLocation: '4 S Market St, Boston, MA 02109',
    city: cityFromLocation('4 S Market St, Boston, MA 02109', faneuilRaw),
    tourType: tourTypeFromName(faneuilRaw),
  );

  final paid = ShareTourDetails(
    title: shortTourTitle(politicsRaw),
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
    title: shortTourTitle(faneuilRaw),
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

    // Community 2 invite. The DB shows 0 members → no member-count line.
    const inviteSubject0 = 'Join "Demo Boston Walkers" on Audioura';
    final invite0 =
        buildCommunityInviteMessage('Demo Boston Walkers', 'FFush25U');
    final inviteBody0 = CommunityCopy.emailInviteBody(
      communityName: 'Demo Boston Walkers',
      description: null,
      organiserName: null,
      code: 'FFush25U',
      memberCount: 0,
    );
    // ignore: avoid_print
    print('\n===== COMMUNITY 2 INVITE (0 members) =====');
    // ignore: avoid_print
    print('SUBJECT: ${CommunityCopy.emailInviteSubject("Demo Boston Walkers")}');
    // ignore: avoid_print
    print('SHARE MESSAGE (buildCommunityInviteMessage):\n$invite0');
    // ignore: avoid_print
    print('\nEMAIL BODY (CommunityCopy.emailInviteBody):\n$inviteBody0');

    // Sanity: subject helper matches.
    expect(CommunityCopy.emailInviteSubject('Demo Boston Walkers'),
        inviteSubject0);
    // Every sample still round-trips the code out.
    for (final d in [free, paid, community]) {
      expect(extractShareCode(buildShareMessage(d)), d.code);
    }
    expect(extractShareCode(invite0), 'FFush25U');
    expect(extractShareCode(inviteBody0), 'FFush25U');
  });
}
