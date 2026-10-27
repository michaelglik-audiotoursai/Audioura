// [LOCAL-787] The regression guard that keeps the Listen-page refresh bug from
// coming back. Michael saw a downloaded/translated tour take ~30 s to appear
// because many writers of the `saved_tours` pref did not notify the Listen page.
//
// The fix funnels EVERY write of `saved_tours` through SavedToursStore.save,
// which writes the list and bumps SavedToursRefresh in one step. This test
// scans every lib/**.dart file and FAILS if any file other than the helper
// itself calls `setStringList('saved_tours', …)` directly — i.e. a new writer
// that forgot to go through the helper (and would therefore not refresh Listen).
//
// Only line/block COMMENTS are stripped before scanning, so a doc comment that
// mentions the call never counts. String literals are left intact because the
// call we are hunting for, `setStringList('saved_tours'`, literally contains a
// string literal — blanking strings would hide the very thing we check.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// A raw write of the saved_tours pref: `setStringList('saved_tours', …)` or
/// the double-quoted form. The helper uses the `SavedToursStore.key` constant
/// instead of the literal, so it never matches even before the exemption.
final RegExp _rawSavedToursWrite =
    RegExp('''setStringList\\(\\s*['"]saved_tours['"]''');

/// The ONE file allowed to be the raw writer of saved_tours. Everything else
/// must call SavedToursStore.save.
const String _helperRelPath = 'services/saved_tours_store.dart';

void main() {
  final libDir = Directory('lib');

  test(
      'only SavedToursStore writes saved_tours directly — every other writer '
      'goes through the helper (LOCAL-787 guard)', () {
    expect(libDir.existsSync(), isTrue,
        reason: 'run from the audio_tour_app package root');

    final offenders = <String>[];
    for (final entity in libDir.listSync(recursive: true)) {
      if (entity is! File || !entity.path.endsWith('.dart')) continue;
      final rel = _rel(entity.path);
      if (rel == _helperRelPath) continue; // the one allowed raw writer
      final code = _stripComments(entity.readAsStringSync());
      if (_rawSavedToursWrite.hasMatch(code)) offenders.add(rel);
    }

    expect(
      offenders,
      isEmpty,
      reason: 'These files write the saved_tours pref directly with '
          "setStringList('saved_tours', …) instead of SavedToursStore.save. A "
          'direct write does NOT bump SavedToursRefresh, so the Listen page '
          'will not refresh until some later unrelated event (LOCAL-787). Route '
          'the write through SavedToursStore.save:\n  ${offenders.join('\n  ')}',
    );
  });
}

/// Path relative to lib/, with forward slashes (stable across platforms).
String _rel(String path) {
  var p = path.replaceAll('\\', '/');
  final idx = p.indexOf('/lib/');
  if (idx >= 0) p = p.substring(idx + '/lib/'.length);
  if (p.startsWith('lib/')) p = p.substring('lib/'.length);
  return p;
}

/// Remove `//` line comments and `/* */` block comments, leaving code and
/// string literals intact. Good enough for this guard: a `//` or `/*` inside a
/// string literal is rare in this codebase and would only ever cause a FALSE
/// offender (never hide a real one), which a maintainer would notice at once.
String _stripComments(String src) {
  final out = StringBuffer();
  int i = 0;
  final n = src.length;
  while (i < n) {
    final two = i + 1 < n ? src.substring(i, i + 2) : '';
    if (two == '//') {
      while (i < n && src[i] != '\n') {
        i++;
      }
      continue;
    }
    if (two == '/*') {
      i += 2;
      while (i < n && !(i + 1 < n && src[i] == '*' && src[i + 1] == '/')) {
        i++;
      }
      i += 2;
      continue;
    }
    // Keep string literals intact so `setStringList('saved_tours'` still shows.
    if (src[i] == '\'' || src[i] == '"') {
      final quote = src[i];
      out.write(quote);
      i++;
      while (i < n && src[i] != quote) {
        if (src[i] == '\\' && i + 1 < n) {
          out.write(src.substring(i, i + 2));
          i += 2;
          continue;
        }
        out.write(src[i]);
        i++;
      }
      if (i < n) {
        out.write(quote);
        i++;
      }
      continue;
    }
    out.write(src[i]);
    i++;
  }
  return out.toString();
}
