import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/services/deep_link_service.dart';
import 'package:audio_tour_app_dev/utils/search_dispatch.dart';

/// [LOCAL-709 / D671] Tests for the deep-link handler.
///
/// These pin the two guarantees the spec cares about:
///   • a `/t/<CODE>` URI maps to the SAME search call a pasted code takes (and a
///     non-`/t/` path is ignored), and
///   • the deferred-link check is a true one-shot: it runs once, never twice.
///
/// NOTE: these can FAIL — point codeFromUri at the last path segment blindly and
/// `audioura.com/legal/terms` would yield "terms"; drop the one-shot flag write
/// and the "never twice" test goes red.
void main() {
  const code = 'FFush25U';

  group('codeFromUri — only our /t/ links, mapped to a code', () {
    test('a bare /t/<CODE> link yields the code', () {
      expect(DeepLinkService.codeFromUri(Uri.parse('https://audioura.com/t/$code')),
          code);
    });

    test('a /t/<CODE>?n=... link yields the code (query ignored)', () {
      expect(
          DeepLinkService.codeFromUri(
              Uri.parse('https://audioura.com/t/$code?n=The%20Freedom%20Trail')),
          code);
    });

    test('a trailing slash still yields the code', () {
      expect(
          DeepLinkService.codeFromUri(Uri.parse('https://audioura.com/t/$code/')),
          code);
    });

    test('www. host is accepted', () {
      expect(
          DeepLinkService.codeFromUri(Uri.parse('https://www.audioura.com/t/$code')),
          code);
    });

    test('a non-/t/ path is ignored (home, legal, etc.)', () {
      expect(DeepLinkService.codeFromUri(Uri.parse('https://audioura.com/')), isNull);
      expect(DeepLinkService.codeFromUri(Uri.parse('https://audioura.com/legal/terms')),
          isNull);
      expect(DeepLinkService.codeFromUri(Uri.parse('https://audioura.com/t/')),
          isNull);
    });

    test('a /t/ segment that is not a code shape is ignored', () {
      // 8-letter leading-capital word is a place, not a code (ST-3 rule).
      expect(DeepLinkService.codeFromUri(Uri.parse('https://audioura.com/t/Brooklyn')),
          isNull);
    });

    test('a foreign host is ignored', () {
      expect(DeepLinkService.codeFromUri(Uri.parse('https://evil.example/t/$code')),
          isNull);
    });

    test('the code from a /t/ link classifies to the SAME shareCode dispatch '
        'a pasted code takes', () {
      // The link handler extracts the code; feeding that code to the shared
      // dispatcher must land on the share-code branch — i.e. the same call a
      // pasted code produces. No second resolver.
      final linkCode =
          DeepLinkService.codeFromUri(Uri.parse('https://audioura.com/t/$code'))!;
      final pasted = classifySearchInput(code);
      final viaLink = classifySearchInput(linkCode);
      expect(viaLink.kind, SearchKind.shareCode);
      expect(viaLink.shareCode, pasted.shareCode);
      expect(viaLink.kind, pasted.kind);
    });
  });

  group('codeFromInstallReferrer — Android deferred link', () {
    test('pulls audioura_code=<CODE> out of a referrer blob', () {
      expect(
          DeepLinkService.codeFromInstallReferrer(
              'utm_source=google-play&audioura_code=$code'),
          code);
    });

    test('null / empty / missing param yields null', () {
      expect(DeepLinkService.codeFromInstallReferrer(null), isNull);
      expect(DeepLinkService.codeFromInstallReferrer(''), isNull);
      expect(DeepLinkService.codeFromInstallReferrer('utm_source=x'), isNull);
    });

    test('a non-code-shaped value is rejected', () {
      expect(
          DeepLinkService.codeFromInstallReferrer('audioura_code=Brooklyn'),
          isNull);
    });
  });

  group('PendingShareSearch.offer / consume', () {
    test('offer ignores null and empty; consume clears', () {
      final p = PendingShareSearch.instance;
      p.consume();
      p.offer(null);
      expect(p.code.value, isNull);
      p.offer('');
      expect(p.code.value, isNull);
      p.offer(code);
      expect(p.code.value, code);
      p.consume();
      expect(p.code.value, isNull);
    });
  });

  group('runDeferredCheckOnce — true one-shot (D671 §4)', () {
    setUp(() {
      TestWidgetsFlutterBinding.ensureInitialized();
      SharedPreferences.setMockInitialValues({});
      PendingShareSearch.instance.consume();
    });

    test('Android referrer runs the search once, then never again', () async {
      final prefs = await SharedPreferences.getInstance();
      var referrerReads = 0;

      Future<String?> referrer() async {
        referrerReads++;
        return 'audioura_code=$code';
      }

      Future<String?> clipboard() async => null;
      Future<bool> prompt(String _) async => true;

      // First run: consumes the referrer and parks the code.
      await DeepLinkService.instance.runDeferredCheckOnce(
        readInstallReferrer: referrer,
        readClipboardCode: clipboard,
        prompt: prompt,
        prefs: prefs,
      );
      expect(PendingShareSearch.instance.code.value, code);
      expect(referrerReads, 1);
      expect(prefs.getBool(kDeferredLinkCheckedKey), isTrue);

      // Clear the parked code and run AGAIN: must be a no-op (flag set).
      PendingShareSearch.instance.consume();
      await DeepLinkService.instance.runDeferredCheckOnce(
        readInstallReferrer: referrer,
        readClipboardCode: clipboard,
        prompt: prompt,
        prefs: prefs,
      );
      expect(PendingShareSearch.instance.code.value, isNull,
          reason: 'the one-shot must not run a second time');
      expect(referrerReads, 1, reason: 'the referrer must not be read twice');
    });

    test('iOS clipboard branch: prompt Yes parks the code, exactly once',
        () async {
      final prefs = await SharedPreferences.getInstance();
      var promptCount = 0;

      await DeepLinkService.instance.runDeferredCheckOnce(
        readInstallReferrer: () async => null, // no Android referrer
        readClipboardCode: () async => code,
        prompt: (c) async {
          promptCount++;
          return true;
        },
        prefs: prefs,
        platform: TargetPlatform.iOS,
      );
      expect(PendingShareSearch.instance.code.value, code);
      expect(promptCount, 1);

      // Second call never prompts again.
      PendingShareSearch.instance.consume();
      await DeepLinkService.instance.runDeferredCheckOnce(
        readInstallReferrer: () async => null,
        readClipboardCode: () async => code,
        prompt: (c) async {
          promptCount++;
          return true;
        },
        prefs: prefs,
        platform: TargetPlatform.iOS,
      );
      expect(promptCount, 1, reason: 'never ask again (D671 §4)');
      expect(PendingShareSearch.instance.code.value, isNull);
    });

    test('iOS clipboard branch: prompt No does not park a code, and never asks '
        'again', () async {
      final prefs = await SharedPreferences.getInstance();
      await DeepLinkService.instance.runDeferredCheckOnce(
        readInstallReferrer: () async => null,
        readClipboardCode: () async => code,
        prompt: (c) async => false, // "Not now"
        prefs: prefs,
        platform: TargetPlatform.iOS,
      );
      expect(PendingShareSearch.instance.code.value, isNull);
      expect(prefs.getBool(kDeferredLinkCheckedKey), isTrue,
          reason: 'the shot is spent even on "Not now"');
    });

    test('nothing on the clipboard → no code, no crash', () async {
      final prefs = await SharedPreferences.getInstance();
      var promptCount = 0;
      await DeepLinkService.instance.runDeferredCheckOnce(
        readInstallReferrer: () async => null,
        readClipboardCode: () async => null, // Clipboard.hasStrings == false
        prompt: (c) async {
          promptCount++;
          return true;
        },
        prefs: prefs,
        platform: TargetPlatform.iOS,
      );
      expect(promptCount, 0, reason: 'no prompt when the clipboard is empty');
      expect(PendingShareSearch.instance.code.value, isNull);
    });

    test('Android with an empty referrer never touches the clipboard '
        '(D671 §2: clipboard is iOS only)', () async {
      final prefs = await SharedPreferences.getInstance();
      var clipboardReads = 0;
      var promptCount = 0;
      await DeepLinkService.instance.runDeferredCheckOnce(
        readInstallReferrer: () async => null, // Android, nothing in referrer
        readClipboardCode: () async {
          clipboardReads++;
          return code;
        },
        prompt: (c) async {
          promptCount++;
          return true;
        },
        prefs: prefs,
        platform: TargetPlatform.android,
      );
      expect(clipboardReads, 0,
          reason: 'Android must never read the clipboard');
      expect(promptCount, 0, reason: 'Android must never prompt');
      expect(PendingShareSearch.instance.code.value, isNull);
      expect(prefs.getBool(kDeferredLinkCheckedKey), isTrue,
          reason: 'the one shot is still spent on Android');
    });
  });

  group('init — existing-install guard (D671: no paste prompt on update)', () {
    setUp(() {
      TestWidgetsFlutterBinding.ensureInitialized();
      PendingShareSearch.instance.consume();
    });

    test('existing install (onboarding_complete present, flag absent): init '
        'sets the flag so the deferred readers never run', () async {
      SharedPreferences.setMockInitialValues({'onboarding_complete': true});
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getBool(kDeferredLinkCheckedKey), isNull,
          reason: 'precondition: the one-shot flag is new/absent');

      await DeepLinkService.instance.init(prefs: prefs);

      expect(prefs.getBool(kDeferredLinkCheckedKey), isTrue,
          reason: 'init must consume the one shot for existing installs');

      // And the deferred check is now a no-op: readers are never called.
      var referrerReads = 0;
      var clipboardReads = 0;
      await DeepLinkService.instance.runDeferredCheckOnce(
        readInstallReferrer: () async {
          referrerReads++;
          return 'audioura_code=$code';
        },
        readClipboardCode: () async {
          clipboardReads++;
          return code;
        },
        prompt: (c) async => true,
        prefs: prefs,
        platform: TargetPlatform.iOS,
      );
      expect(referrerReads, 0, reason: 'referrer reader must not run');
      expect(clipboardReads, 0, reason: 'clipboard reader must not run');
      expect(PendingShareSearch.instance.code.value, isNull);
    });

    test('fresh install (no onboarding_complete, flag absent): init does NOT '
        'set the flag; the one-shot behaviour is unchanged', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      await DeepLinkService.instance.init(prefs: prefs);

      expect(prefs.getBool(kDeferredLinkCheckedKey), isNull,
          reason: 'a fresh install must keep the deferred check available');

      // The current one-shot behaviour still runs for a fresh install.
      var referrerReads = 0;
      await DeepLinkService.instance.runDeferredCheckOnce(
        readInstallReferrer: () async {
          referrerReads++;
          return 'audioura_code=$code';
        },
        readClipboardCode: () async => null,
        prompt: (c) async => true,
        prefs: prefs,
        platform: TargetPlatform.android,
      );
      expect(referrerReads, 1, reason: 'fresh install still reads the referrer');
      expect(PendingShareSearch.instance.code.value, code);
    });
  });
}
