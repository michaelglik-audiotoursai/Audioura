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
  // LOCAL-694B (LEAD review): a route is MISSING ("Preview only") ONLY when a
  // 404 is NOT the service's own JSON error — i.e. (a) the GCloud gateway's
  // JSON {"error":"endpoint not found","service":"api-gateway"}, (b) a non-JSON
  // (HTML) body, or (c) 405/501. A JSON 404 FROM THE SERVICE itself
  // ({"error":"not_found"}, {"error":"Job not found"}) is a NORMAL not-found
  // and must NOT be treated as feature-unavailable. Four cases, per helper.
  group('route-missing vs normal not-found (isRouteMissing)', () {
    // The exact GCloud gateway 404 envelope (api-gateway/main.py:297).
    const gateway404 =
        '{"error":"endpoint not found","service":"api-gateway"}';

    // --- Case (a): gateway JSON 404 => MISSING ---
    test('(a) gateway JSON 404 {endpoint not found, api-gateway} -> MISSING',
        () {
      expect(Endpoints.isRouteMissing(404, gateway404), isTrue);
    });

    // --- Case (b): non-JSON (HTML) 404 => MISSING ---
    test('(b) HTML 404 page (service called directly) -> MISSING', () {
      expect(Endpoints.isRouteMissing(404, _html404), isTrue);
    });
    test('(b) empty-body 404 -> MISSING (no JSON error to preserve)', () {
      expect(Endpoints.isRouteMissing(404, ''), isTrue);
      expect(Endpoints.isRouteMissing(404, null), isTrue);
    });

    // --- Case (c): 405 / 501 => MISSING regardless of body ---
    for (final code in [405, 501]) {
      test('(c) $code is MISSING regardless of body', () {
        expect(Endpoints.isRouteMissing(code), isTrue);
        expect(Endpoints.isRouteMissing(code, '{"error":"whatever"}'), isTrue);
        expect(Endpoints.isRouteMissing(code, _html404), isTrue);
      });
    }

    // --- Case (d): service's OWN JSON 404 => NORMAL not-found, NOT missing ---
    test('(d) service JSON 404 {"error":"not_found"} -> NORMAL (not missing)',
        () {
      expect(Endpoints.isRouteMissing(404, '{"error":"not_found"}'), isFalse);
    });
    test('(d) orchestrator JSON 404 {"error":"Job not found"} -> NORMAL', () {
      expect(
          Endpoints.isRouteMissing(404, '{"error":"Job not found"}'), isFalse);
    });
    test('(d) map-delivery JSON 404 {"error":"tour not found"} -> NORMAL', () {
      expect(Endpoints.isRouteMissing(404, '{"error":"tour not found"}'),
          isFalse);
    });
    test('(d) a service error that merely NAMES the gateway is still NORMAL',
        () {
      // Only the exact gateway envelope (both fields) is case (a); a service
      // 404 that happens to mention one field must stay a normal not-found.
      expect(
          Endpoints.isRouteMissing(
              404, '{"error":"not_found","service":"orchestrator"}'),
          isFalse);
      expect(
          Endpoints.isRouteMissing(404, '{"service":"api-gateway"}'), isFalse);
    });

    // --- Non-404/405/501: never missing ---
    for (final code in [200, 201, 400, 401, 403, 409, 500, 503]) {
      test('$code is NOT route-missing (any body)', () {
        expect(Endpoints.isRouteMissing(code, _html404), isFalse);
        expect(Endpoints.isRouteMissing(code, '{"error":"x"}'), isFalse);
      });
    }
  });

  group('isFeatureUnavailableStatus is now 405/501-only (deprecated)', () {
    // Status-only classifier must NO LONGER claim a 404 (needs the body).
    test('404 is NOT classifiable from status alone', () {
      expect(Endpoints.isFeatureUnavailableStatus(404), isFalse);
    });
    for (final code in [405, 501]) {
      test('$code is still a feature-unavailable status', () {
        expect(Endpoints.isFeatureUnavailableStatus(code), isTrue);
      });
    }
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
      // The screen path: an HTML 404 is route-missing, and even if parsing is
      // attempted on the HTML body it yields null instead of throwing.
      expect(Endpoints.isRouteMissing(404, _html404), isTrue);
      expect(Endpoints.tryDecodeMap(_html404), isNull);
    });

    test('#17 POST /tour/<id>/rating 404 HTML -> null, no throw', () {
      expect(Endpoints.tryDecodeMap(_html404), isNull);
    });

    test('#2 GET /status/<job> 404 JSON {error:Job not found} -> NORMAL', () {
      // LOCAL-694B: on real Storied this route EXISTS; its 404 for an unknown
      // job is the service's own JSON and must NOT read as "Preview only".
      expect(
          Endpoints.isRouteMissing(404, '{"error":"Job not found"}'), isFalse);
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
      // 503 is NOT route-missing; the body is valid JSON the caller reads.
      const body = '{"message":"service unavailable","status":"error"}';
      expect(Endpoints.isRouteMissing(503, body), isFalse);
      final m = Endpoints.tryDecodeMap(body);
      expect(m, isNotNull);
      expect(m!['status'], 'error');
    });

    test('#1 POST /generate-complete-tour 400 JSON {error} -> parseable', () {
      const body = '{"error":"missing required field"}';
      expect(Endpoints.isRouteMissing(400, body), isFalse);
      expect(Endpoints.tryDecodeMap(body)!['error'], isNotNull);
    });
  });
}
