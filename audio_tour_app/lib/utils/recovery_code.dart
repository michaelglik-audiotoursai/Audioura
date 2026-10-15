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
