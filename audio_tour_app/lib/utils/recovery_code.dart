// [LOCAL-695] Pure helpers for the anonymous recovery code UI.
//
// The server (recovery_code_service.py) is the source of truth: it generates the
// code (16 Crockford-base32 chars, grouped 4×4) and verifies a NORMALIZED form
// (strip hyphens/spaces, uppercase, map the look-alikes I/L→1, O→0, U→V). These
// helpers mirror that normalization so the app can give the listener immediate
// feedback and send a clean code, and so the behaviour is unit-testable without
// a running server.

/// Canonicalise a user-entered recovery code for sending/comparison: trim,
/// uppercase, drop hyphens and spaces, and map the visually ambiguous
/// characters the server also maps (I/L→1, O→0, U→V). Returns '' for null/empty.
String normalizeRecoveryCode(String? code) {
  if (code == null) return '';
  var s = code.trim().toUpperCase();
  s = s.replaceAll('-', '').replaceAll(' ', '');
  final buf = StringBuffer();
  for (final ch in s.split('')) {
    switch (ch) {
      case 'I':
      case 'L':
        buf.write('1');
        break;
      case 'O':
        buf.write('0');
        break;
      case 'U':
        buf.write('V');
        break;
      default:
        buf.write(ch);
    }
  }
  return buf.toString();
}

/// The canonical alphabet after normalization (Crockford base32 minus I,L,O,U).
const String _recoveryAlphabet = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

/// True if [code] is a plausible recovery code: exactly 16 symbols from the
/// canonical alphabet after normalization. This is a client-side shape check to
/// enable the Restore button and catch typos early — the server still has the
/// final say (it checks the hash).
bool isPlausibleRecoveryCode(String? code) {
  final n = normalizeRecoveryCode(code);
  if (n.length != 16) return false;
  for (final ch in n.split('')) {
    if (!_recoveryAlphabet.contains(ch)) return false;
  }
  return true;
}

/// Format a (possibly unformatted) code for display as four hyphen-joined groups
/// of four, e.g. 'ABCDEFGHJKMNPQRS' -> 'ABCD-EFGH-JKMN-PQRS'. A code that is not
/// 16 chars after normalization is returned trimmed/uppercased as-is (we never
/// hide what the server sent).
String formatRecoveryCodeForDisplay(String? code) {
  final n = normalizeRecoveryCode(code);
  if (n.length != 16) return (code ?? '').trim();
  return '${n.substring(0, 4)}-${n.substring(4, 8)}-'
      '${n.substring(8, 12)}-${n.substring(12, 16)}';
}

/// [LOCAL-740 / B5] The fixed subject of the "email it to myself" message. The
/// app opens the device mail composer with this — it NEVER sends mail itself.
const String kRecoveryEmailSubject = 'My Audioura recovery code';

/// [LOCAL-740 / B5] The body text that accompanies the code in the email / share
/// sheet. [code] is interpolated as-is (already display-formatted by the caller).
String recoveryShareBody(String code) =>
    'Keep this Audioura recovery code somewhere outside your phone. If this '
    'phone is lost, stolen or broken, it restores your Listen page — your '
    'tours, paid tours and articles — on a new phone.\n\n'
    'Recovery code: $code';

/// [LOCAL-740 / B5] Build the `mailto:` URI that opens the device mail composer
/// pre-filled with the recovery code (subject [kRecoveryEmailSubject], the code
/// in the body). No recipient — the listener emails it to whoever they like
/// (usually themselves). The app opens this with url_launcher; it never sends
/// mail itself, so the code never leaves the phone through us.
///
/// Pure + testable: the widget test asserts the built intent CARRIES the code.
Uri recoveryEmailUri(String code) {
  return Uri(
    scheme: 'mailto',
    query: _encodeMailtoQuery({
      'subject': kRecoveryEmailSubject,
      'body': recoveryShareBody(code),
    }),
  );
}

/// mailto query encoding: `+` must mean a literal plus in a mail body, so encode
/// spaces as %20 (Uri.encodeQueryComponent would turn them into '+').
String _encodeMailtoQuery(Map<String, String> params) {
  return params.entries
      .map((e) =>
          '${Uri.encodeComponent(e.key)}=${Uri.encodeComponent(e.value)}')
      .join('&');
}
