// LOCAL-868 (D762, app side) — "Share → Audioura".
//
// Text shared from another app (Musa.AI, Notes, ChatGPT…) arrives here and is
// parked in [PendingSharedText] until the Create Tour screen opens the paste
// box pre-filled with it. Same parked-notifier shape as `PendingShareSearch`
// (deep_link_service.dart), so a widget test sets the text with no plugin.
//
// Sources:
//   * Android — MainActivity reads an ACTION_SEND text/plain intent and
//     answers `getInitialSharedText` (cold start) / pushes `sharedText`
//     (warm start, onNewIntent) on the `com.audioura.app/share` channel.
//   * iOS — the Share Extension opens `audioura://paste?text=<percent-encoded>`;
//     DeepLinkService hands that URI to [textFromPasteUri].

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import '../utils/pasted_list.dart';

/// URL scheme the iOS Share Extension hands text over with.
const String kPasteUriScheme = 'audioura';
const String kPasteUriHost = 'paste';

class PendingSharedText {
  PendingSharedText._();
  static final PendingSharedText instance = PendingSharedText._();

  final ValueNotifier<String?> text = ValueNotifier<String?>(null);

  /// Park shared text. Blank text is ignored; very long text is cut at the
  /// server's limit so the paste box never starts over the cap.
  void offer(String? value) {
    final t = value?.trim();
    if (t == null || t.isEmpty) return;
    text.value = t.length > kMaxPasteChars ? t.substring(0, kMaxPasteChars) : t;
  }

  /// Clear once the paste box has taken the text.
  void consume() {
    text.value = null;
  }
}

/// The text carried by an `audioura://paste?text=…` URI, or null for any other
/// URI. Pure.
String? textFromPasteUri(Uri uri) {
  if (uri.scheme != kPasteUriScheme || uri.host != kPasteUriHost) return null;
  final t = uri.queryParameters['text'];
  return (t == null || t.trim().isEmpty) ? null : t;
}

class SharedTextService {
  SharedTextService._();
  static final SharedTextService instance = SharedTextService._();

  static const MethodChannel _channel = MethodChannel('com.audioura.app/share');

  /// Wire the channel. Never throws (a platform with no native side — iOS,
  /// desktop, tests — just has nothing to deliver).
  Future<void> init() async {
    try {
      _channel.setMethodCallHandler((call) async {
        if (call.method == 'sharedText') {
          PendingSharedText.instance.offer(call.arguments as String?);
        }
        return null;
      });
      final initial = await _channel.invokeMethod<String>('getInitialSharedText');
      PendingSharedText.instance.offer(initial);
    } catch (_) {
      // No native handler on this platform.
    }
  }
}
