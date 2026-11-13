// [LOCAL-908] TopicAudioOutput backed by the tour page's WebView (see
// on_the_way_js.dart). Kept tiny: all logic lives in OnTheWayController.
library webview_topic_audio;

import 'dart:convert';

import '../config/endpoints.dart';
import 'fillings_model.dart';
import 'on_the_way_controller.dart';

/// `audio_url` from 907 may be relative ("/topic-audio/..."): join it to the
/// map-delivery base (LOCAL-907E serves GET /topic-audio/<path> there; absolute
/// and file:// URLs pass through unchanged).
String joinTopicAudioUrl(String base, String raw) {
  final r = raw.trim();
  // Any absolute URL (https://, http://, or file:// for audio kept on the
  // device) is used as is.
  if (RegExp(r'^[a-zA-Z][a-zA-Z0-9+.\-]*://').hasMatch(r)) return r;
  final b = base.endsWith('/') ? base.substring(0, base.length - 1) : base;
  return r.startsWith('/') ? '$b$r' : '$b/$r';
}

typedef JsRunner = Future<void> Function(String source);

class WebViewTopicAudio implements TopicAudioOutput {
  final JsRunner run;
  final Future<String> Function() baseUrl;
  WebViewTopicAudio({required this.run, Future<String> Function()? baseUrl})
      : baseUrl = baseUrl ?? (() => Endpoints.base(Service.mapDelivery));

  @override
  Future<void> play(FillingItem item, {double startSec = 0}) async {
    final url = joinTopicAudioUrl(await baseUrl(), item.audioUrl);
    await run('window.__audTopic && window.__audTopic.play('
        '${jsonEncode(url)}, $startSec, ${jsonEncode(item.title)})');
  }

  @override
  Future<void> fadeOutAndStop(Duration fade) async {
    await run('window.__audTopic && '
        'window.__audTopic.fadeOut(${fade.inMilliseconds})');
    // Resolve when the fade is done, so the stop that follows never overlaps it.
    await Future<void>.delayed(fade + const Duration(milliseconds: 80));
  }

  @override
  Future<void> stop() => run('window.__audTopic && window.__audTopic.stop()');
}
