import 'package:flutter_test/flutter_test.dart';
import '../lib/services/log_redactor.dart';

/// Security regression tests for wdvrday4pk.
///
/// The credential-submission path once wrote plaintext passwords, usernames,
/// and the AES key into a persisted, in-app-viewable debug log. LogRedactor is
/// the guard that scrubs secrets out of every message routed through
/// DebugLogHelper. These tests assert known secrets never survive redaction.
///
/// NOTE (acceptance criterion #3): these tests must be able to FAIL. To prove
/// it, weaken LogRedactor.redact (e.g. `return message;`) and the assertions
/// below go red — a redaction test that cannot fail is not evidence.
void main() {
  const secretPassword = 'S3cr3t-Boston-Globe-Pass!';
  const secretUser = 'michael@example.com';
  const secretKey = 'a1b2c3d4e5f60718293a4b5c6d7e8f90';

  group('LogRedactor scrubs credential values', () {
    test('plaintext password in key="value" form is removed', () {
      final input =
          'SUBSCRIPTION: Calling encryptCredentials with username="$secretUser", password="$secretPassword", domain="bostonglobe.com"';
      final out = LogRedactor.redact(input);

      expect(out.contains(secretPassword), isFalse,
          reason: 'password value must not survive redaction');
      expect(out.contains(secretUser), isFalse,
          reason: 'username value must not survive redaction');
      // The domain is not sensitive and should remain for diagnostics.
      expect(out.contains('bostonglobe.com'), isTrue);
      // Key names are preserved so we still know which fields were present.
      expect(out.toLowerCase().contains('password'), isTrue);
      expect(out.contains('[REDACTED]'), isTrue);
    });

    test('AES key in key: value / key=value forms is removed', () {
      expect(LogRedactor.redact('AES key: $secretKey').contains(secretKey),
          isFalse);
      expect(LogRedactor.redact('key=$secretKey').contains(secretKey), isFalse);
      expect(LogRedactor.redact('token="$secretKey"').contains(secretKey),
          isFalse);
      expect(
          LogRedactor.redact('secret=$secretKey').contains(secretKey), isFalse);
    });

    test('JSON-encoded request body has credential values removed', () {
      final body =
          '{"article_id":"a1","encrypted_password":"x","password":"$secretPassword","username":"$secretUser","device_id":"d1"}';
      final out = LogRedactor.redact(body);

      expect(out.contains(secretPassword), isFalse);
      expect(out.contains(secretUser), isFalse);
      // Non-sensitive fields remain.
      expect(out.contains('article_id'), isTrue);
      expect(out.contains('device_id'), isTrue);
    });

    test('non-sensitive text is left unchanged', () {
      const msg = 'SUBSCRIPTION: Response status: 200 for article a1';
      expect(LogRedactor.redact(msg), msg);
    });

    test('case-insensitive key matching', () {
      final out = LogRedactor.redact('Password="$secretPassword"');
      expect(out.contains(secretPassword), isFalse);
    });
  });
}
