// [LOCAL-677C / D654] Stop 1 free-preview player.
//
// Streams GET /tour/<id>/preview-audio from map-delivery (ONLY Stop 1's audio)
// and plays it with flutter_sound (already a dependency — no new package). The
// stream is online only: nothing is saved to the device, no zip, no other stop.
// Used by the "▶ Preview Stop 1" button in the download dialog for an unbought
// paid tour. A single shared player so a second preview stops the first.

import 'package:flutter_sound/flutter_sound.dart';

import '../config/endpoints.dart';

class TourPreviewPlayer {
  TourPreviewPlayer._();
  static final TourPreviewPlayer instance = TourPreviewPlayer._();

  FlutterSoundPlayer? _player;
  bool _opened = false;
  bool _playing = false;

  /// The URL that streams ONLY Stop 1's audio for [tourId]. Built against
  /// map-delivery, the same service the tour is downloaded from.
  static Future<Uri> previewUrl(String tourId) =>
      Endpoints.url(Service.mapDelivery, '/tour/$tourId/preview-audio');

  /// Whether a preview is currently playing.
  bool get isPlaying => _playing;

  Future<void> _ensureOpen() async {
    _player ??= FlutterSoundPlayer();
    if (!_opened) {
      await _player!.openPlayer();
      _opened = true;
    }
  }

  /// Start (or restart) the Stop-1 preview for [tourId]. Streams from the
  /// network; nothing is saved. Throws on a network/stream error so the caller
  /// can show a message.
  Future<void> play(String tourId) async {
    await _ensureOpen();
    final uri = await previewUrl(tourId);
    if (_playing) {
      try {
        await _player!.stopPlayer();
      } catch (_) {}
      _playing = false;
    }
    await _player!.startPlayer(
      fromURI: uri.toString(),
      whenFinished: () {
        _playing = false;
      },
    );
    _playing = true;
  }

  /// Stop the current preview.
  Future<void> stop() async {
    if (_player == null) return;
    try {
      await _player!.stopPlayer();
    } catch (_) {}
    _playing = false;
  }

  Future<void> dispose() async {
    try {
      await _player?.stopPlayer();
      await _player?.closePlayer();
    } catch (_) {}
    _player = null;
    _opened = false;
    _playing = false;
  }
}
