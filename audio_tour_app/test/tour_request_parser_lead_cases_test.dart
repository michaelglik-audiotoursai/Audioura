// [LOCAL-363 LEAD] Cases outside the agent's acceptance table.
//
// Written during review (2026-08-10) to check the guard against inputs whose
// answers were known in advance, rather than re-running the agent's own table.
// It found one defect: "tour of Amsterdam on a scooter" returned '' because the
// by/on/via adjacency rule did not allow an intervening article.
import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/utils/tour_request_parser.dart';

void main() {
  group('LOCAL-363 no spatial preposition — fallback path', () {
    final cases = <String, String>{
      'bike tour': 'biking',
      'biking': 'biking',
      'museum tour': 'museum',
      'safari': 'safari',
    };
    cases.forEach((input, expected) {
      test('$input -> "$expected"', () {
        expect(parseTourRequest(input)['tour_type'], expected);
      });
    });
  });

  group('LOCAL-363 mode word after the place, via by/on/via', () {
    final cases = <String, String>{
      'tour of Hyde Park by bike': 'biking',
      // Regression: the article used to break the adjacency rule.
      'tour of Amsterdam on a scooter': 'driving',
      'tour of the dunes on a bike': 'biking',
    };
    cases.forEach((input, expected) {
      test('$input -> "$expected"', () {
        expect(parseTourRequest(input)['tour_type'], expected);
      });
    });
  });

  group('LOCAL-363 place names must not hijack the type', () {
    final cases = <String, String>{
      'tour of Camelback Mountain': '',
      'tour of Scooter Alley': '',
      'tour of the Horse Museum': '',
      'tour of Car Park B': '',
      // "the" is excluded from the article allowance for exactly this reason.
      'tour of the Horse Guards Parade': '',
    };
    cases.forEach((input, expected) {
      test('$input -> "$expected"', () {
        expect(parseTourRequest(input)['tour_type'], expected);
      });
    });
  });

  group("LOCAL-363 Michael's real requests", () {
    final cases = <String, String>{
      'Museum of Fine Arts, Boston': 'museum',
      // 'exhibition' does not match \bexhibit\b; empty lets the server classify.
      'Picasso, Miro, Dali: Unbound exhibition at MFA': '',
      'French Riviera biking tour': 'biking',
      'dog sledding tour in Big Lake AK': 'dog sledding',
    };
    cases.forEach((input, expected) {
      test('$input -> "$expected"', () {
        expect(parseTourRequest(input)['tour_type'], expected);
      });
    });
  });

  group('LOCAL-363 known gap — activity trailing the place', () {
    // Documented, not fixed. Matching arbitrary trailing activity clauses is
    // what reintroduces place-name false positives. '' is the safe default:
    // the server classifies (D269 / LOCAL-358).
    test('"tour of Big Lake AK with dog sledding" degrades to empty', () {
      expect(parseTourRequest('tour of Big Lake AK with dog sledding')['tour_type'], '');
    });

    // A hyphen prefix splits the adjacency: the match starts at "bike", so the
    // preceding text ends "an e-" rather than "an ". Also degrades to empty.
    test('"tour of the dunes on an e-bike" degrades to empty', () {
      expect(parseTourRequest('tour of the dunes on an e-bike')['tour_type'], '');
    });
  });
}
