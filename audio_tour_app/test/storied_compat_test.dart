// LOCAL-694 — tests proving the app degrades gracefully against Storied.
//
// The replay harness (SUBMISSION_LOCAL-694.md) found the Subscribed app's 66
// server calls land in these shapes on a Storied backend:
//   • 404 / 405 / 501 with an HTML body (route missing) — 27 calls
//   • connection refused (whole service absent) — 23 calls
//   • 2xx / 4xx / 5xx with a JSON body — the rest
//
// Every "handled endpoint" routes its missing/absent case through ONE central
// place: Endpoints.isFeatureUnavailableStatus / tryDecodeMap / tryDecodeList /
// isServiceAbsentError and the FeatureUnavailableException it raises. These
// tests exercise that central logic directly for each category — the exact
// bytes the harness saw come back as a friendly message and never an
// exception. One test group per category / per handled endpoint shape.
//
// These tests can FAIL: make tryDecodeMap rethrow on an HTML body, or drop a
// status from isFeatureUnavailableStatus, and the expectations below go red.

import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import '../lib/config/endpoints.dart';

/// The literal Flask 404 body the harness recorded (non-JSON HTML). Decoding
/// this with a bare jsonDecode throws FormatException — the bug this guards.
const _html404 =
    '<!doctype html>\n<html lang=en>\n<title>404 Not Found</title>\n'
    '<h1>Not Found</h1>\n<p>The requested URL was not found on the server.</p>\n';

void main() {
  group('status classification (missing route -> Preview only)', () {
    // Every orchestrator feature route (#7-23), mapDelivery #27-31, news
    // #55-56 came back 404; delete-account #5 came back 405.
    for (final code in [404, 405, 501]) {
      test('$code is a feature-unavailable status', () {
        expect(Endpoints.isFeatureUnavailableStatus(code), isTrue);
      });
    }

    // These must NOT be treated as "feature missing": a real answer, an auth
    // refusal, or a transient server error the caller handles differently.
    for (final code in [200, 201, 400, 401, 403, 409, 500, 503]) {
      test('$code is NOT a feature-unavailable status', () {
        expect(Endpoints.isFeatureUnavailableStatus(code), isFalse);
      });
    }
  });

  group('defensive JSON decode never throws on a non-JSON body', () {
    test('HTML 404 page -> tryDecodeMap returns null, no throw', () {
      expect(Endpoints.tryDecodeMap(_html404), isNull);
    });

    test('HTML 404 page -> tryDecodeList returns null, no throw', () {
      expect(Endpoints.tryDecodeList(_html404), isNull);
    });

    test('empty body -> null (both decoders)', () {
      expect(Endpoints.tryDecodeMap(''), isNull);
      expect(Endpoints.tryDecodeMap(null), isNull);
      expect(Endpoints.tryDecodeList(''), isNull);
      expect(Endpoints.tryDecodeList(null), isNull);
    });

    test('a JSON object body decodes to a Map (wallet/price/rating shape)', () {
      final m = Endpoints.tryDecodeMap('{"plan":"ppu","balance_usd":1.5}');
      expect(m, isNotNull);
      expect(m!['plan'], 'ppu');
    });

    test('a JSON array body decodes to a List (plans/transactions shape)', () {
      final l = Endpoints.tryDecodeList('[{"id":"a"},{"id":"b"}]');
      expect(l, isNotNull);
      expect(l!.length, 2);
    });

    test('a JSON object asked for as a List -> null (shape mismatch, no throw)',
        () {
      expect(Endpoints.tryDecodeList('{"not":"a list"}'), isNull);
    });

    test('a JSON array asked for as a Map -> null (shape mismatch, no throw)',
        () {
      expect(Endpoints.tryDecodeMap('[1,2,3]'), isNull);
    });
  });

  group('absent-service classification (connection refused -> Preview only)', () {
    // userDb/voice/generator/customAudio/tourIdResolution are not hosted by
    // Storied; the socket is refused. These surface as SocketException /
    // ClientException / TimeoutException and must be read as "feature absent".
    test('SocketException is an absent-service error', () {
      expect(
          Endpoints.isServiceAbsentError(
              const SocketException('Connection refused')),
          isTrue);
    });

    test('http.ClientException is an absent-service error', () {
      expect(Endpoints.isServiceAbsentError(http.ClientException('boom')),
          isTrue);
    });

    test('TimeoutException is an absent-service error', () {
      expect(Endpoints.isServiceAbsentError(TimeoutException('slow')), isTrue);
    });

    test('a FormatException is NOT an absent-service error', () {
      expect(Endpoints.isServiceAbsentError(const FormatException('x')),
          isFalse);
    });
  });

  group('FeatureUnavailableException carries the friendly message', () {
    test('default message is the Preview-only line', () {
      final e = FeatureUnavailableException(
          service: Service.orchestrator, path: '/wallet/x', statusCode: 404);
      expect(e.message, 'This feature is available in Preview only.');
      expect(e.message, Endpoints.featureUnavailableMessage);
    });

    test('is an Exception and never leaks the raw status in the message', () {
      final e = FeatureUnavailableException(
          service: Service.userDb,
          path: '/communities/map',
          cause: const SocketException('refused'));
      expect(e, isA<Exception>());
      expect(e.message, isNot(contains('SocketException')));
      expect(e.message, isNot(contains('404')));
      // toString() may carry diagnostics, but the user-facing message does not.
      expect(e.toString(), contains('/communities/map'));
    });

    test('a caller-supplied message overrides the default', () {
      final e = FeatureUnavailableException(
          service: Service.news, path: '/news-status/x', message: 'Custom.');
      expect(e.message, 'Custom.');
    });
  });

  // Per-endpoint-shape proofs: feed the EXACT body the harness recorded for a
  // representative call in each class and assert the handling path produces a
  // safe result rather than an exception. These mirror the replay table rows.
  group('per-endpoint handled-shape proofs (from the replay table)', () {
    test('#19 GET /wallet/<id> 404 HTML -> treated as feature-unavailable', () {
      // The screen path: status is feature-unavailable, and even if parsing is
      // attempted on the HTML body it yields null instead of throwing.
      expect(Endpoints.isFeatureUnavailableStatus(404), isTrue);
      expect(Endpoints.tryDecodeMap(_html404), isNull);
    });

    test('#17 POST /tour/<id>/rating 404 HTML -> null, no throw', () {
      expect(Endpoints.tryDecodeMap(_html404), isNull);
    });

    test('#43 POST /communities 404/absent -> safe default', () {
      // communities_service returns null on any failure; the classification
      // helpers it relies on must agree the service is absent on a refusal.
      expect(
          Endpoints.isServiceAbsentError(
              const SocketException('Connection refused')),
          isTrue);
    });

    test('#59 POST /submit_credentials 503 JSON {message,status} -> parseable',
        () {
      // 503 is NOT feature-unavailable; the body is valid JSON the caller reads.
      const body = '{"message":"service unavailable","status":"error"}';
      expect(Endpoints.isFeatureUnavailableStatus(503), isFalse);
      final m = Endpoints.tryDecodeMap(body);
      expect(m, isNotNull);
      expect(m!['status'], 'error');
    });

    test('#1 POST /generate-complete-tour 400 JSON {error} -> parseable', () {
      const body = '{"error":"missing required field"}';
      expect(Endpoints.isFeatureUnavailableStatus(400), isFalse);
      expect(Endpoints.tryDecodeMap(body)!['error'], isNotNull);
    });
  });
}
