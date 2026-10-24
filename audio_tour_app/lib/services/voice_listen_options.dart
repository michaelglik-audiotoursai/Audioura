// [LOCAL-752 D] Offline voice control — on-device speech recognition options.
//
// Voice command PARSING is already on-device (VoiceControlService
// ._processAdvancedCommand); the gap was that `_speechToText.listen(...)` was
// called WITHOUT on-device recognition, so iOS/Android could ship audio to
// Apple/Google and FAIL with no internet. This file is the ONE source of truth
// for the SpeechListenOptions a listen() call uses, so every voice surface
// (VoiceControlService, VoiceControlServiceNews, MyToursScreen) behaves
// identically and the choice is unit-tested without a running app.
//
// Rule: use on-device recognition when the platform reports it is available for
// the locale; otherwise fall back to the previous (server-capable) behaviour. A
// single log line (voiceListenMode) records which mode was used so a field run
// can be verified.

import 'package:speech_to_text/speech_to_text.dart';

/// The SpeechListenOptions a listen() call should use. When [onDeviceSupported]
/// is true the session recognises LOCALLY (no network — works in airplane mode);
/// otherwise onDevice is false and the platform may use its network recogniser,
/// exactly as before. partialResults stays true (the callers rely on the final
/// result flag). cancelOnError stays true so a failed session ends cleanly.
SpeechListenOptions buildVoiceListenOptions({required bool onDeviceSupported}) {
  return SpeechListenOptions(
    onDevice: onDeviceSupported,
    partialResults: true,
    cancelOnError: true,
  );
}

/// A short human-readable mode string for the single log line a listen() call
/// emits — 'on-device' when offline recognition is used, 'network' otherwise.
String voiceListenMode({required bool onDeviceSupported}) =>
    onDeviceSupported ? 'on-device' : 'network';
