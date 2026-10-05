import 'package:flutter_test/flutter_test.dart';
import '../lib/utils/share_code.dart';

/// [LOCAL-579] Tests for the share-code extractor.
///
/// The sending side builds the message
///   Listen to my Audioura tour "X". Open Audioura, tap Search on the Home page
///   and paste this code: <CODE>
/// and the Home search box must pull <CODE> back out whether the listener pastes
/// the bare code, that whole message, a share link, or any of those with stray
/// whitespace — while a place name like "Boston" or "Newton MA" must NOT be
/// mistaken for a code (ST-3's digit/internal-capital discriminator).
///
/// NOTE: these tests can FAIL — point extractShareCode at a weaker rule (e.g.
/// `return null;` or dropping the shape check) and the groups below go red.
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
      final msg = buildShareMessage('The Freedom Trail', code);
      expect(extractShareCode(msg), code);
    });

    test('the full share message with trailing/leading whitespace', () {
      final msg = '\n  ${buildShareMessage("Harvard Yard", code)}  \t';
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
      // No digits, but a capital after the first char → still a code shape.
      expect(extractShareCode('abcdWxyz'), 'abcdWxyz');
    });
  });

  group('extractShareCode rejects place names and plain text', () {
    test('a short place name', () {
      expect(extractShareCode('Boston'), isNull);
    });

    test('a place with a space (Newton MA)', () {
      expect(extractShareCode('Newton MA'), isNull);
    });

    test('an 8-letter Capitalised single word (Brooklyn)', () {
      // 8 chars, but capital only at position 0 and no digit → a place.
      expect(extractShareCode('Brooklyn'), isNull);
    });

    test('an 8-letter Capitalised single word (Portland)', () {
      expect(extractShareCode('Portland'), isNull);
    });

    test('a lower-case 8-letter word', () {
      expect(extractShareCode('elephant'), isNull);
    });

    test('a multi-word place query', () {
      expect(extractShareCode('San Francisco California'), isNull);
    });

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
      expect(isShareCodeShape('Boston'), isFalse); // too short
      expect(isShareCodeShape('Brooklyn'), isFalse); // leading capital only
      expect(isShareCodeShape('elephant'), isFalse); // all lower-case
      expect(isShareCodeShape('FFush25UX'), isFalse); // 9 chars
    });
  });

  group('buildShareMessage', () {
    test('contains the tour name and the code verbatim', () {
      final msg = buildShareMessage('My Tour', code);
      expect(msg.contains('My Tour'), isTrue);
      expect(msg.contains(code), isTrue);
      expect(msg.contains('paste this code: $code'), isTrue);
    });
  });

  test('LEAD: a code-shaped word in the tour name does not shadow the real code', () {
    final msg = buildShareMessage('McDonald Farm and Brooklyn loop', 'AzuwQYnf');
    expect(extractShareCode(msg), 'AzuwQYnf');
  });
  test('LEAD: never a slice of a longer word', () {
    expect(extractShareCode('Commonwealth Avenue Mall'), isNull);
    expect(extractShareCode('Brooklyn'), isNull);
    expect(extractShareCode('Montreal, Quebec'), isNull);
  });
}
