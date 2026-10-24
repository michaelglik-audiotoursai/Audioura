// [LOCAL-752 D] Voice control must work with NO internet. The on-device command
// PARSING is already local; the gap is that `_speechToText.listen(...)` is called
// WITHOUT on-device recognition, so iOS/Android may ship audio to Apple/Google
// and fail offline. The fix passes SpeechListenOptions(onDevice: true) when the
// platform reports on-device support for the locale, falling back to the current
// (server-capable) behaviour otherwise, and LOGS which mode was used.
//
// The decision is a pure, dependency-free helper so it is unit-tested without a
// running app or the speech_to_text plugin:
//   * buildVoiceListenOptions(onDeviceSupported: bool) → SpeechListenOptions with
//     onDevice set accordingly (partialResults stays true as today);
//   * voiceListenMode(onDeviceSupported: bool) → 'on-device' | 'network' for the
//     single log line.

import 'package:flutter_test/flutter_test.dart';
import 'package:speech_to_text/speech_to_text.dart';
import 'package:audio_tour_app_dev/services/voice_listen_options.dart';

void main() {
  group('buildVoiceListenOptions', () {
    test('onDevice=true when the platform supports on-device for the locale', () {
      final opts = buildVoiceListenOptions(onDeviceSupported: true);
      expect(opts, isA<SpeechListenOptions>());
      expect(opts.onDevice, isTrue,
          reason: 'offline voice needs onDevice recognition (LOCAL-752 D).');
      expect(opts.partialResults, isTrue);
    });

    test('onDevice=false (fallback) when on-device is not supported', () {
      final opts = buildVoiceListenOptions(onDeviceSupported: false);
      expect(opts.onDevice, isFalse);
      expect(opts.partialResults, isTrue);
    });
  });

  group('voiceListenMode (for the log line)', () {
    test('reports on-device when supported', () {
      expect(voiceListenMode(onDeviceSupported: true), 'on-device');
    });

    test('reports network when not supported', () {
      expect(voiceListenMode(onDeviceSupported: false), 'network');
    });
  });
}
