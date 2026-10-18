import 'package:flutter_test/flutter_test.dart';

import '../lib/utils/share_code.dart';
import '../lib/widgets/share_tour_sheet.dart';

/// [LOCAL-711 / D673] buildShareTourDetails picks the SERVER short_title for the
/// email title + subject when it is present, and otherwise falls back to the
/// app's own shortTourTitle() of the raw name. These are pure assertions on the
/// builder (no widgets, no sharing I/O).
void main() {
  const rawName =
      'Faneuil Hall Marketplace, Boston MA, with a stop at Quincy Market '
      '- Walking Tour';

  test('server short_title present → it is used verbatim as the title', () {
    final d = buildShareTourDetails(
      rawTourName: rawName,
      code: 'FFush25U',
      serverShortTitle: 'Faneuil Hall Market — Walking Tour',
    );
    expect(d.title, 'Faneuil Hall Market — Walking Tour');
    // And it reaches the email body + subject.
    expect(
      buildShareMessage(d).contains('"Faneuil Hall Market — Walking Tour"'),
      isTrue,
    );
  });

  test('server short_title absent → falls back to shortTourTitle(rawName)', () {
    final d = buildShareTourDetails(rawTourName: rawName, code: 'FFush25U');
    expect(d.title, shortTourTitle(rawName));
    expect(d.title, 'Faneuil Hall Marketplace — Walking Tour');
  });

  test('server short_title empty / whitespace → treated as absent', () {
    for (final v in ['', '   ', null]) {
      final d = buildShareTourDetails(
        rawTourName: rawName, code: 'FFush25U', serverShortTitle: v);
      expect(d.title, shortTourTitle(rawName));
    }
  });

  test('kind + subject are unaffected by the short_title source', () {
    final withServer = buildShareTourDetails(
      rawTourName: rawName,
      code: 'FFush25U',
      serverShortTitle: 'Quincy Market — Walking Tour',
      firstStopLocation: '4 S Market St, Boston, MA 02109',
    );
    // Subject still derives city + type from the raw name / first-stop location.
    expect(buildShareSubject(withServer), 'A Boston walking tour for you');
  });
}
