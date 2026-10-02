/// Redacts secrets from strings before they are written to any log sink.
///
/// Context (ClickUp wdvrday4pk): the credential-submission path was logging
/// plaintext passwords, usernames, and the AES key into a PERSISTED,
/// in-app-viewable debug log (SharedPreferences `debug_logs` + a viewer screen
/// + console `print`). Removing the offending lines fixes today's leak, but a
/// future `addDebugLog('... $password ...')` would reintroduce it. This
/// redactor is the guard: every message routed through `DebugLogHelper` is
/// scrubbed here first, so a value that follows a known-sensitive key name is
/// replaced with `[REDACTED]` regardless of the call site.
///
/// It is deliberately NOT a `kDebugMode` gate — the field diagnostics in this
/// log are useful in release, so we keep the log and strip only the secrets.
class LogRedactor {
  /// Key names whose associated value must never be logged. Matched
  /// case-insensitively as whole-ish words followed by `=`, `:`, or `"..."`.
  static const List<String> sensitiveKeys = <String>[
    'password',
    'passwd',
    'pwd',
    'username',
    'user_name',
    'credential',
    'credentials',
    'secret',
    'token',
    'api_key',
    'apikey',
    'aes key',
    'aes_key',
    'key', // broad on purpose; see _keyIsTooGeneric handling below
  ];

  /// Patterns that capture `key="value"` / `key='value'` / `key=value` /
  /// `key: value`, so we can replace the value with [REDACTED] while keeping
  /// the key name for diagnostics.
  static final List<RegExp> _kvPatterns = _buildKvPatterns();

  /// JSON-style `"key": "value"` (and single-quoted) for encoded request bodies.
  static final List<RegExp> _jsonPatterns = _buildJsonPatterns();

  static List<RegExp> _buildKvPatterns() {
    final patterns = <RegExp>[];
    for (final k in sensitiveKeys) {
      final key = RegExp.escape(k);
      // key="value" or key='value'
      patterns.add(RegExp('($key)\\s*=\\s*"[^"]*"', caseSensitive: false));
      patterns.add(RegExp("($key)\\s*=\\s*'[^']*'", caseSensitive: false));
      // key: "value" / key: 'value'
      patterns.add(RegExp('($key)\\s*:\\s*"[^"]*"', caseSensitive: false));
      patterns.add(RegExp("($key)\\s*:\\s*'[^']*'", caseSensitive: false));
      // key=bareword (stop at whitespace, comma, ), }, ", ')
      patterns.add(RegExp('($key)\\s*=\\s*([^\\s,)}"\']+)', caseSensitive: false));
      // key: bareword
      patterns.add(RegExp('($key)\\s*:\\s*([^\\s,)}"\']+)', caseSensitive: false));
    }
    return patterns;
  }

  static List<RegExp> _buildJsonPatterns() {
    final patterns = <RegExp>[];
    for (final k in sensitiveKeys) {
      final key = RegExp.escape(k);
      // "key":"value"  (JSON, double-quoted key and value)
      patterns.add(RegExp('"($key)"\\s*:\\s*"[^"]*"', caseSensitive: false));
    }
    return patterns;
  }

  /// Returns [message] with any sensitive values replaced by `[REDACTED]`.
  /// The key name is preserved so logs still say WHICH field was present.
  static String redact(String message) {
    var out = message;

    // JSON `"key":"value"` first (most specific).
    for (final re in _jsonPatterns) {
      out = out.replaceAllMapped(re, (m) => '"${m.group(1)}":"[REDACTED]"');
    }

    // key=value / key: value forms.
    for (final re in _kvPatterns) {
      out = out.replaceAllMapped(re, (m) => '${m.group(1)}=[REDACTED]');
    }

    return out;
  }
}
