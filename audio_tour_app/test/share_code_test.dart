import 'package:flutter_test/flutter_test.dart';
import '../lib/utils/share_code.dart';

/// [LOCAL-579 / LOCAL-709 / LOCAL-710] Tests for the share-code helpers.
///
/// The sending side builds a message that leads with the short link
/// (https://audioura.com/t/<CODE>) and keeps the code as a fallback; the Home
/// search box must pull <CODE> back out whether the listener pastes the bare
/// code, the whole message, a share link, or any of those with stray whitespace
/// — while a place name like "Boston" or "Newton MA" must NOT be mistaken for a
/// code (ST-3's digit/internal-capital discriminator).
///
/// [LOCAL-710 / D672] Adds: shortTourTitle on ≥ 10 REAL names (from the DB,
/// incl. Russian), the message golden for free / paid / community / no-stops,
/// and the community invite at 0 / 1 / 2 / 12 members.
void main() {
  // A realistic generated 8-char base62 code (has internal capitals + a digit).
  const code = 'FFush25U';

  group('extractShareCode accepts a code', () {
    test('bare code', () {
      expect(extractShareCode(code), code);
    });

    test('bare code with surrounding whitespace', () {
      expect(extractShareCode('   $code  \n'), code);
    });

    test('the full share message', () {
      final msg = buildShareMessage(const ShareTourDetails(
        title: 'The Freedom Trail — Walking Tour',
        code: code,
        kind: ShareTourKind.free,
      ));
      expect(extractShareCode(msg), code);
    });

    test('the full share message with trailing/leading whitespace', () {
      final msg = '\n  ${buildShareMessage(const ShareTourDetails(title: "Harvard Yard", code: code, kind: ShareTourKind.free))}  \t';
      expect(extractShareCode(msg), code);
    });

    test('a share link', () {
      expect(extractShareCode('https://audioura.io/tour/$code'), code);
    });

    test('a share link embedded in a sentence', () {
      expect(
        extractShareCode('Check this out https://audioura.io/tour/$code thanks'),
        code,
      );
    });

    test('an all-digits code (no letters) is still a code', () {
      expect(extractShareCode('12345678'), '12345678');
    });

    test('a code whose only distinguishing mark is an internal capital', () {
      expect(extractShareCode('abcdWxyz'), 'abcdWxyz');
    });
  });

  group('extractShareCode rejects place names and plain text', () {
    test('a short place name', () => expect(extractShareCode('Boston'), isNull));
    test('a place with a space (Newton MA)',
        () => expect(extractShareCode('Newton MA'), isNull));
    test('an 8-letter Capitalised single word (Brooklyn)',
        () => expect(extractShareCode('Brooklyn'), isNull));
    test('an 8-letter Capitalised single word (Portland)',
        () => expect(extractShareCode('Portland'), isNull));
    test('a lower-case 8-letter word',
        () => expect(extractShareCode('elephant'), isNull));
    test('a multi-word place query',
        () => expect(extractShareCode('San Francisco California'), isNull));
    test('empty / whitespace-only input', () {
      expect(extractShareCode(''), isNull);
      expect(extractShareCode('    '), isNull);
    });
  });

  group('isShareCodeShape discriminator', () {
    test('accepts codes with a digit or internal capital', () {
      expect(isShareCodeShape('FFush25U'), isTrue);
      expect(isShareCodeShape('abcdWxyz'), isTrue);
      expect(isShareCodeShape('12345678'), isTrue);
    });
    test('rejects wrong length and plain Capitalised words', () {
      expect(isShareCodeShape('Boston'), isFalse);
      expect(isShareCodeShape('Brooklyn'), isFalse);
      expect(isShareCodeShape('elephant'), isFalse);
      expect(isShareCodeShape('FFush25UX'), isFalse);
    });
  });

  // ── [LOCAL-710 / D672] buildShareLink — short, no ?n= ──────────────────────
  group('buildShareLink (D672: short link, no name)', () {
    test('canonical shape: https://audioura.com/t/<CODE> and nothing else', () {
      expect(buildShareLink(code), 'https://audioura.com/t/$code');
    });
    test('no query string is ever appended', () {
      expect(buildShareLink(code).contains('?'), isFalse);
      expect(buildShareLink(code).contains('n='), isFalse);
    });
    test('extractShareCode reads the bare link + trailing slash + legacy ?n=', () {
      expect(extractShareCode('https://audioura.com/t/$code'), code);
      expect(extractShareCode('https://audioura.com/t/$code/'), code);
      // A legacy message that still carries ?n= must still resolve.
      expect(
          extractShareCode('https://audioura.com/t/$code?n=The%20Freedom%20Trail'),
          code);
    });
  });

  // ── [LOCAL-710 / D672] shortTourTitle on ≥ 10 REAL names from the DB ────────
  group('shortTourTitle on real DB names (D672)', () {
    // These are verbatim from `SELECT tour_name FROM audio_tours ORDER BY id
    // DESC` on the local DB (audiotours), including the Russian one.
    final cases = <String, String>{
      'Faneuil Hall Marketplace, Boston MA, with a stop at Quincy Market and a '
          'stop at the Samuel Adams statue and a stop at the Boston Massacre '
          'site - Walking Tour': 'Faneuil Hall Marketplace — Walking Tour',
      'Walking tour in Boston dedicated to Massachusetts politics and current '
          'affairs, Boston, MA - walking Tour':
          'Walking tour in Boston dedicated to Massachusetts politics and '
              'current affairs — Walking Tour',
      'Newton Centre, Newton, MA - walking Tour': 'Newton Centre — Walking Tour',
      'Cleveland Museum of Art, Cleveland, USA - museum Tour':
          'Cleveland Museum of Art — Museum Tour',
      'Museum of Fine Arts, Boston, USA - museum Tour':
          'Museum of Fine Arts — Museum Tour',
      'State Hermitage Museum, Saint Petersburg, Russia - museum Tour':
          'State Hermitage Museum — Museum Tour',
      'Musée des Beaux-Arts de Bordeaux, Bordeaux, France - museum Tour':
          'Musée des Beaux-Arts de Bordeaux — Museum Tour',
      'Metropolitan Museum of Art, New York, USA - museum Tour':
          'Metropolitan Museum of Art — Museum Tour',
      'Galleria Borghese, Rome, Italy - museum Tour':
          'Galleria Borghese — Museum Tour',
      'Petit Palais, Paris, France - Museum Tour': 'Petit Palais — Museum Tour',
      'Wallace Collection, London, United Kingdom - Museum Tour':
          'Wallace Collection — Museum Tour',
    };

    cases.forEach((raw, expected) {
      test('"${raw.substring(0, raw.length > 40 ? 40 : raw.length)}…"', () {
        expect(shortTourTitle(raw), expected);
      });
    });

    test('a Russian name never returns empty and loses its city tail', () {
      const ru =
          'Пешеходная экскурсия по Бостону, посвященная политике и текущим '
          'делам Массачусетса, Бостон, MA - пешеходная экскурсия';
      final out = shortTourTitle(ru);
      expect(out.isNotEmpty, isTrue);
      // The repeated ", Бостон, MA" tail is dropped.
      expect(out.contains(', MA'), isFalse);
      expect(out.contains('Бостону'), isTrue); // body preserved
    });

    test('empty type "-  Tour" normalises to " — Tour"', () {
      expect(shortTourTitle('Harbor Loop -  Tour'), 'Harbor Loop — Tour');
    });

    test('never returns empty: a bare name falls through trimmed', () {
      expect(shortTourTitle('  Just A Name  '), 'Just A Name');
    });

    test('type is capitalised in the normalised suffix', () {
      expect(shortTourTitle('X - walking Tour'), 'X — Walking Tour');
      expect(shortTourTitle('Y - BIKING Tour'), 'Y — BIKING Tour');
    });
  });

  // ── [LOCAL-710 / D672] buildShareMessage goldens ───────────────────────────
  group('buildShareMessage goldens (D672 order + wording)', () {
    // Faneuil Hall free tour (server tour 365 / share FFush25U), REAL stops.
    const free = ShareTourDetails(
      title: 'Faneuil Hall Marketplace — Walking Tour',
      code: 'FFush25U',
      kind: ShareTourKind.free,
      stopCount: 3,
      firstStopName: 'Quincy Market',
      firstStopLocation: '4 S Market St, Boston, MA 02109',
      city: 'Boston',
      tourType: 'walking',
    );

    test('free tour — exact golden', () {
      expect(
        buildShareMessage(free),
        'Welcome to my free tour "Faneuil Hall Marketplace — Walking Tour" on Audioura.\n'
        '\n'
        'Hands-free audio: press play and walk.\n'
        '\n'
        '3 stops, starting at Quincy Market (4 S Market St, Boston, MA 02109).\n'
        '\n'
        'https://audioura.com/t/FFush25U\n'
        '\n'
        '(Or open Audioura, tap Search and paste FFush25U.)',
      );
      expect(extractShareCode(buildShareMessage(free)), 'FFush25U');
    });

    // Paid tour (server tour 557 / share Wo8Oj8lA, price_tier 3 = $4.99).
    const paid = ShareTourDetails(
      title: 'Boston politics & current affairs — Walking Tour',
      code: 'Wo8Oj8lA',
      kind: ShareTourKind.paid,
      price: '\$4.99',
      stopCount: 5,
      firstStopName: 'Old State House',
      firstStopLocation: '206 Washington St, Boston, MA 02109',
      city: 'Boston',
      tourType: 'walking',
    );

    test('paid tour — price line LAST', () {
      final msg = buildShareMessage(paid);
      expect(
        msg,
        'Welcome to my tour "Boston politics & current affairs — Walking Tour" on Audioura.\n'
        '\n'
        'Hands-free audio: press play and walk.\n'
        '\n'
        '5 stops, starting at Old State House (206 Washington St, Boston, MA 02109).\n'
        '\n'
        'https://audioura.com/t/Wo8Oj8lA\n'
        '\n'
        '(Or open Audioura, tap Search and paste Wo8Oj8lA.)\n'
        '\n'
        'The tour price is \$4.99.',
      );
      // The price line is the LAST paragraph.
      expect(msg.trimRight().endsWith('The tour price is \$4.99.'), isTrue);
    });

    // Community tour (from community 2 "Demo Boston Walkers"), real stops.
    const community = ShareTourDetails(
      title: 'Faneuil Hall Marketplace — Walking Tour',
      code: 'FFush25U',
      kind: ShareTourKind.community,
      communityName: 'Demo Boston Walkers',
      stopCount: 3,
      firstStopName: 'Quincy Market',
      firstStopLocation: '4 S Market St, Boston, MA 02109',
      city: 'Boston',
      tourType: 'walking',
    );

    test('community tour — community opening + join-to-download line', () {
      expect(
        buildShareMessage(community),
        'Welcome to my tour "Faneuil Hall Marketplace — Walking Tour" from the Demo Boston Walkers community on Audioura.\n'
        '\n'
        'Hands-free audio: press play and walk.\n'
        '\n'
        '3 stops, starting at Quincy Market (4 S Market St, Boston, MA 02109).\n'
        '\n'
        'https://audioura.com/t/FFush25U\n'
        '\n'
        '(Or open Audioura, tap Search and paste FFush25U.)\n'
        '\n'
        'Join the Demo Boston Walkers community in Audioura to download it.',
      );
    });

    test('a tour WITHOUT stops data — stops line omitted, no "null"', () {
      const noStops = ShareTourDetails(
        title: 'Mystery Walk — Walking Tour',
        code: 'FFush25U',
        kind: ShareTourKind.free,
      );
      final msg = buildShareMessage(noStops);
      expect(msg.contains('null'), isFalse);
      expect(msg.contains('stops'), isFalse);
      expect(
        msg,
        'Welcome to my free tour "Mystery Walk — Walking Tour" on Audioura.\n'
        '\n'
        'Hands-free audio: press play and walk.\n'
        '\n'
        'https://audioura.com/t/FFush25U\n'
        '\n'
        '(Or open Audioura, tap Search and paste FFush25U.)',
      );
    });

    test('first stop with no location → "starting at X." (no empty parens)', () {
      const d = ShareTourDetails(
        title: 'T', code: 'FFush25U', kind: ShareTourKind.free,
        stopCount: 4, firstStopName: 'Trailhead',
      );
      expect(buildShareMessage(d).contains('starting at Trailhead.'), isTrue);
      expect(buildShareMessage(d).contains('()'), isFalse);
    });

    test('a single stop reads "1 stop"', () {
      const d = ShareTourDetails(
        title: 'T', code: 'FFush25U', kind: ShareTourKind.free,
        stopCount: 1, firstStopName: 'Only Stop',
      );
      expect(buildShareMessage(d).contains('1 stop,'), isTrue);
    });

    test('no double spaces anywhere in a message', () {
      for (final d in [free, paid, community]) {
        expect(buildShareMessage(d).contains('  '), isFalse);
      }
    });
  });

  // ── [LOCAL-710 / D672] buildShareSubject ───────────────────────────────────
  group('buildShareSubject (D672)', () {
    test('city + type → "A <city> <type> tour for you"', () {
      expect(
        buildShareSubject(const ShareTourDetails(
            title: 'X', code: code, kind: ShareTourKind.free,
            city: 'Boston', tourType: 'Walking')),
        'A Boston walking tour for you',
      );
    });
    test('missing city OR type → generic subject', () {
      expect(
        buildShareSubject(const ShareTourDetails(
            title: 'X', code: code, kind: ShareTourKind.free, tourType: 'walking')),
        'An Audioura tour for you',
      );
      expect(
        buildShareSubject(const ShareTourDetails(
            title: 'X', code: code, kind: ShareTourKind.free, city: 'Boston')),
        'An Audioura tour for you',
      );
    });
  });

  // ── [LOCAL-710 / D672] Community invite at 0 / 1 / 2 / 12 members ──────────
  group('buildCommunityInviteMessage (D672 member-count gating)', () {
    test('invite link has no ?n= and carries the code', () {
      expect(buildCommunityInviteLink('AzuwQYnf'),
          'https://audioura.com/t/AzuwQYnf');
    });

    test('0 members — no member-count line', () {
      final msg = buildCommunityInviteMessage('Demo Boston Walkers', 'AzuwQYnf',
          memberCount: 0);
      expect(msg.contains('member'), isFalse);
      expect(extractShareCode(msg), 'AzuwQYnf');
    });

    test('1 member — still no member-count line (< 2)', () {
      final msg = buildCommunityInviteMessage('Demo Boston Walkers', 'AzuwQYnf',
          memberCount: 1);
      expect(msg.contains('member'), isFalse);
    });

    test('2 members — "2 members." shown', () {
      final msg = buildCommunityInviteMessage('Demo Boston Walkers', 'AzuwQYnf',
          memberCount: 2);
      expect(msg.contains('2 members.'), isTrue);
    });

    test('12 members — "12 members." shown', () {
      final msg = buildCommunityInviteMessage('Demo Boston Walkers', 'AzuwQYnf',
          memberCount: 12);
      expect(msg.contains('12 members.'), isTrue);
    });

    test('null member count — no member-count line; no store/how-to lines', () {
      final msg = buildCommunityInviteMessage('Demo Boston Walkers', 'AzuwQYnf');
      expect(msg.contains('member'), isFalse);
      expect(msg.contains('How to get Audioura'), isFalse);
      expect(msg.contains('coming soon'), isFalse);
      expect(extractShareCode(msg), 'AzuwQYnf');
    });

    test('golden: 12-member invite', () {
      expect(
        buildCommunityInviteMessage('Demo Boston Walkers', 'AzuwQYnf',
            memberCount: 12),
        'Join "Demo Boston Walkers" on Audioura.\n'
        '\n'
        '12 members.\n'
        '\n'
        'https://audioura.com/t/AzuwQYnf\n'
        '\n'
        '(Or open Audioura, tap Search and paste AzuwQYnf.)',
      );
    });
  });

  test('LEAD: a code-shaped word in the tour name does not shadow the real code', () {
    final msg = buildShareMessage(const ShareTourDetails(
      title: 'McDonald Farm and Brooklyn loop',
      code: 'AzuwQYnf',
      kind: ShareTourKind.free,
    ));
    expect(extractShareCode(msg), 'AzuwQYnf');
  });

  test('LEAD: never a slice of a longer word', () {
    expect(extractShareCode('Commonwealth Avenue Mall'), isNull);
    expect(extractShareCode('Brooklyn'), isNull);
    expect(extractShareCode('Montreal, Quebec'), isNull);
  });
}
