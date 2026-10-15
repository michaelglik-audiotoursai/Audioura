// LOCAL-705 (D661) — the REGRESSION GUARD that makes "never crashes on Storied"
// impossible to lose by accident.
//
// Why this exists
// ---------------
// The Subscribed app must run against a Storied (Stable) backend that does NOT
// host every endpoint the app calls, WITHOUT crashing: a missing route must
// become "This feature is available in Preview only." (or the screen's empty
// state), never a red screen, an uncaught exception, or an infinite spinner.
//
// LOCAL-694/694B proved this for the app as it then stood. Since then new
// features (recovery code, Google Play, /purchases/mode, communities join /
// name-available / regenerate, community tours, step-down, launch window) added
// server calls. Each NEW server call is a new way to regress — unless every one
// is either (a) routed through the storied-compat helpers
// (Endpoints.getOrFeatureUnavailable / postOrFeatureUnavailable, which raise a
// FeatureUnavailableException on a missing route / absent service), or (b) a
// call whose own code already degrades safely AND is consciously recorded in
// test/storied_compat_allowlist.txt with a one-line reason.
//
// What this test does
// -------------------
// It scans every lib/**.dart file for raw server calls — bare
// `http.get/post/put/delete(...)` and `Endpoints.get/post/put/delete(...)`
// (NOT the *OrFeatureUnavailable helpers, which are the safe path) — and FAILS
// if any file containing such a call is not listed in the allow-list. A new
// feature therefore cannot ship a raw call unless the author either uses the
// helper or adds an allow-list line explaining why that file is safe.
//
// It also fails if the allow-list drifts out of date: an entry for a file that
// no longer has any raw call, so stale exemptions get cleaned up.
//
// Comments and string literals are stripped before scanning so that a URL in a
// doc comment or a log line like 'http.get' never counts as a call site.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Bare server calls that bypass the helpers. These are the regression surface.
/// `Endpoints.getOrFeatureUnavailable` / `postOrFeatureUnavailable` are the
/// SAFE path and are intentionally NOT matched (the word boundary `\b` after
/// get/post stops `get` from matching `getOrFeatureUnavailable`).
final RegExp _rawCall = RegExp(
  r'\b(?:http|Endpoints)\.(?:get|post|put|delete)\b',
);

/// The helper plumbing itself lives in endpoints.dart (the three internal
/// http.* calls that implement get/post/delete) — it is the mechanism, not a
/// feature call, so it is always exempt.
const String _endpointsRelPath = 'config/endpoints.dart';

void main() {
  final libDir = Directory('lib');
  final allowlistFile = File('test/storied_compat_allowlist.txt');

  test('every lib/ server call is helper-routed or allow-listed (D661 guard)',
      () {
    expect(libDir.existsSync(), isTrue,
        reason: 'run from the audio_tour_app package root');
    expect(allowlistFile.existsSync(), isTrue,
        reason: 'test/storied_compat_allowlist.txt must exist');

    final allow = _parseAllowlist(allowlistFile);

    // Files that still contain a raw call after comment/string stripping.
    final offenders = <String>{};
    for (final entity in libDir.listSync(recursive: true)) {
      if (entity is! File || !entity.path.endsWith('.dart')) continue;
      final rel = _rel(entity.path);
      if (rel == _endpointsRelPath) continue; // helper plumbing, always exempt
      final code = _stripCommentsAndStrings(entity.readAsStringSync());
      if (_rawCall.hasMatch(code)) offenders.add(rel);
    }

    // (1) Every offender MUST be in the allow-list.
    final unlisted = offenders.difference(allow.keys.toSet())..toList();
    expect(
      unlisted,
      isEmpty,
      reason: 'These files make a raw server call (http.* or Endpoints.get/'
          'post/put/delete) that is NOT routed through '
          'getOrFeatureUnavailable/postOrFeatureUnavailable and is NOT in '
          'test/storied_compat_allowlist.txt. Either route the call through the '
          'helper, or add an allow-list line "path | reason" explaining why the '
          'call already degrades safely on Storied:\n  ${unlisted.join('\n  ')}',
    );

    // (2) Every allow-list entry MUST correspond to a file that still has a raw
    // call — otherwise the exemption is stale and should be removed (keeps the
    // list honest and small).
    final stale = allow.keys.toSet().difference(offenders)..toList();
    expect(
      stale,
      isEmpty,
      reason: 'These allow-list entries no longer match any raw server call '
          '(the file was removed, or its calls now go through the helper). '
          'Delete the stale line(s) from test/storied_compat_allowlist.txt:\n  '
          '${stale.join('\n  ')}',
    );
  });

  test('every allow-list entry carries a non-empty one-line reason', () {
    final allow = _parseAllowlist(allowlistFile);
    expect(allow, isNotEmpty, reason: 'the allow-list should not be empty');
    allow.forEach((path, reason) {
      expect(reason.trim(), isNotEmpty,
          reason: 'allow-list entry "$path" needs a reason after the "|"');
    });
  });
}

/// Parse `path | reason` lines; ignores blank lines and `#` comments.
Map<String, String> _parseAllowlist(File f) {
  final out = <String, String>{};
  for (final raw in f.readAsLinesSync()) {
    final line = raw.trim();
    if (line.isEmpty || line.startsWith('#')) continue;
    final i = line.indexOf('|');
    final path = (i < 0 ? line : line.substring(0, i)).trim();
    final reason = i < 0 ? '' : line.substring(i + 1).trim();
    if (path.isNotEmpty) out[path] = reason;
  }
  return out;
}

/// Path relative to lib/, with forward slashes (stable across platforms).
String _rel(String path) {
  var p = path.replaceAll('\\', '/');
  final idx = p.indexOf('/lib/');
  if (idx >= 0) p = p.substring(idx + '/lib/'.length);
  if (p.startsWith('lib/')) p = p.substring('lib/'.length);
  return p;
}

/// Remove // line comments, /* block comments */ and string literals (single,
/// double, and raw) so a server-call token inside a comment or a string never
/// counts. Deliberately simple and conservative — it only needs to avoid false
/// POSITIVES (a comment/string that looks like a call); a stray false negative
/// would only ever UNDER-report, and real call sites are plain code.
String _stripCommentsAndStrings(String src) {
  final sb = StringBuffer();
  int i = 0;
  final n = src.length;
  while (i < n) {
    final c = src[i];
    final c2 = (i + 1 < n) ? src[i + 1] : '';

    // Line comment.
    if (c == '/' && c2 == '/') {
      while (i < n && src[i] != '\n') {
        i++;
      }
      continue;
    }
    // Block comment.
    if (c == '/' && c2 == '*') {
      i += 2;
      while (i < n && !(src[i] == '*' && i + 1 < n && src[i + 1] == '/')) {
        i++;
      }
      i += 2;
      continue;
    }
    // Raw string: r'...' or r"..."
    if ((c == 'r') && (c2 == '\'' || c2 == '"')) {
      final quote = c2;
      i += 2;
      while (i < n && src[i] != quote) {
        i++;
      }
      i++;
      sb.write(' ');
      continue;
    }
    // Normal string (handles escapes). Covers ' and " (triple quotes collapse
    // to the same quote char and are consumed quote-run by quote-run, which is
    // fine for our purpose of removing their contents).
    if (c == '\'' || c == '"') {
      final quote = c;
      i++;
      while (i < n) {
        if (src[i] == '\\') {
          i += 2;
          continue;
        }
        if (src[i] == quote) {
          i++;
          break;
        }
        i++;
      }
      sb.write(' ');
      continue;
    }

    sb.write(c);
    i++;
  }
  return sb.toString();
}
