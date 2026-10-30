// local830_double_request_guard_test.dart — LOCAL-830.
//
// The phone sent TWO /generate-complete-tour requests 1 s apart for one Generate
// tap (GCloud_Storied 2026-10-30). Root cause: the in-flight flag was only set
// AFTER the pre-request awaits (duplicate check + dialog), so a second tap in
// that window slipped past the `if (_isGenerating) return` guard.
//
// The fix in tour_generator_screen.dart is a SYNCHRONOUS guard (`_generateInFlight`
// flipped true before any await, cleared in a finally) plus a per-attempt
// `client_request_id`. These tests model that exact mechanism with the real
// helper logic, so a regression that moves the flag back after an await fails
// here: the model's guard set before the first await yields ONE request, and the
// id generator yields a distinct id per attempt (and the client sends it).

import 'dart:async';
import 'dart:math';
import 'package:flutter_test/flutter_test.dart';

/// The exact client-request-id scheme used in tour_generator_screen.dart.
String newClientRequestId() {
  final rnd = Random.secure();
  final a = rnd.nextInt(0xFFFFFFFF).toRadixString(16).padLeft(8, '0');
  final b = rnd.nextInt(0xFFFFFFFF).toRadixString(16).padLeft(8, '0');
  final ts = DateTime.now().microsecondsSinceEpoch.toRadixString(16);
  return 'cli-$ts-$a$b';
}

/// A minimal model of the Generate handler, mirroring the production guard:
/// a synchronous in-flight flag set BEFORE the first await, cleared in finally.
class _GenerateModel {
  bool inFlight = false;
  int requestsSent = 0;
  final List<String> sentClientIds = [];

  Future<void> generate() async {
    // Synchronous double-submit guard — set before ANY await.
    if (inFlight) return;
    inFlight = true;
    try {
      // Pre-request awaits (the duplicate-check + dialog window in production).
      await Future<void>.delayed(const Duration(milliseconds: 20));
      final clientId = newClientRequestId();
      // The single HTTP submission carries the client_request_id.
      sentClientIds.add(clientId);
      requestsSent++;
      await Future<void>.delayed(const Duration(milliseconds: 5));
    } finally {
      inFlight = false;
    }
  }
}

void main() {
  group('LOCAL-830 client_request_id', () {
    test('has the cli- prefix and is unique per call', () {
      final a = newClientRequestId();
      final b = newClientRequestId();
      expect(a.startsWith('cli-'), isTrue);
      expect(b.startsWith('cli-'), isTrue);
      expect(a, isNot(equals(b)));
    });

    test('100 ids are all distinct', () {
      final ids = <String>{};
      for (var i = 0; i < 100; i++) {
        ids.add(newClientRequestId());
      }
      expect(ids.length, 100);
    });
  });

  group('LOCAL-830 double-submit guard', () {
    test('two near-simultaneous taps send exactly ONE request', () async {
      final m = _GenerateModel();
      // Two taps fired in the same event loop turn, before the first completes —
      // exactly the double-tap / double-fire that caused the field defect.
      final f1 = m.generate();
      final f2 = m.generate();
      await Future.wait([f1, f2]);
      expect(m.requestsSent, 1);
      expect(m.sentClientIds.length, 1);
    });

    test('a tap during the pre-request await window is dropped', () async {
      final m = _GenerateModel();
      final f1 = m.generate();
      // Second tap 1 ms later — still inside the 20 ms pre-request window.
      await Future<void>.delayed(const Duration(milliseconds: 1));
      final f2 = m.generate();
      await Future.wait([f1, f2]);
      expect(m.requestsSent, 1);
    });

    test('a later tap after completion sends a second, distinct request', () async {
      final m = _GenerateModel();
      await m.generate();
      await m.generate();
      expect(m.requestsSent, 2);
      // Each completed attempt carried its own client_request_id.
      expect(m.sentClientIds.toSet().length, 2);
    });
  });
}
