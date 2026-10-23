// [LOCAL-740 / A3b] Unit tests for the shared URL-input helper.
//
// Proves the review case (`en.wikipedia.org/wiki/Boston` is accepted, not
// refused as "invalid URL") and the full rule: bare domain, domain with a path,
// http (unchanged), https (unchanged), and surrounding spaces.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/utils/url_input.dart';

void main() {
  group('normalizeUrlInput', () {
    test('bare domain gets https://', () {
      expect(normalizeUrlInput('example.com'), 'https://example.com');
    });

    test('the review case: bare domain WITH a path gets https://', () {
      expect(normalizeUrlInput('en.wikipedia.org/wiki/Boston'),
          'https://en.wikipedia.org/wiki/Boston');
    });

    test('http:// is left exactly as typed', () {
      expect(normalizeUrlInput('http://example.com'), 'http://example.com');
    });

    test('https:// is left exactly as typed', () {
      expect(normalizeUrlInput('https://example.com/a/b?c=d'),
          'https://example.com/a/b?c=d');
    });

    test('surrounding spaces are trimmed', () {
      expect(normalizeUrlInput('   example.com   '), 'https://example.com');
      expect(normalizeUrlInput('  https://example.com  '),
          'https://example.com');
    });

    test('a www. host gets https:// too', () {
      expect(normalizeUrlInput('www.example.com'), 'https://www.example.com');
    });

    test('null / blank → empty (the helper never invents a URL)', () {
      expect(normalizeUrlInput(null), '');
      expect(normalizeUrlInput(''), '');
      expect(normalizeUrlInput('    '), '');
    });

    test('a non-http scheme is left alone', () {
      expect(normalizeUrlInput('ftp://files.example.com'),
          'ftp://files.example.com');
    });
  });

  group('looksLikeUrl', () {
    test('accepts bare domains and paths', () {
      expect(looksLikeUrl('example.com'), isTrue);
      expect(looksLikeUrl('en.wikipedia.org/wiki/Boston'), isTrue);
      expect(looksLikeUrl('http://example.com'), isTrue);
    });

    test('rejects a hostless word and blanks', () {
      expect(looksLikeUrl('notaurl'), isFalse);
      expect(looksLikeUrl(''), isFalse);
      expect(looksLikeUrl(null), isFalse);
    });
  });
}
