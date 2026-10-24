// [LOCAL-760 build item 1] One persistent download-progress indicator.
//
// Michael (iPhone, 2026-10-24): while an organiser-audio tour downloaded, "the
// status message appeared and disappeared and then appeared, etc. The status
// message is good, but it should not disappear." The previous flow (LOCAL-759
// A3) rendered every RemoteAudioProgress tick as a fresh SnackBar
// (messenger.clearSnackBars() + showSnackBar()), so the line flashed on each
// byte update.
//
// This replaces that with ONE widget that stays mounted for the whole download:
// an inline banner carrying a LinearProgressIndicator, the shared
// downloadingAudioLabel line ("Downloading audio — stop 2 of 3 · 45 / 81 MB")
// and a Cancel. It is NOT a SnackBar, so nothing clears/re-shows it; it is shown
// while [DownloadProgressController.visible] is true and removed only when the
// controller is finished (success / cancel / the named failure).
//
// The controller is a ChangeNotifier so the hosting screen drives it from the
// download's onAudioProgress callback and the banner rebuilds in place. Pure of
// any I/O — a widget test pumps ticks and asserts exactly one bar, never a
// SnackBar.

import 'package:flutter/material.dart';

import '../services/remote_audio_fetcher.dart';

/// Drives a single persistent progress banner for one download.
///
/// Lifecycle: [start] → zero or more [update] (each a RemoteAudioProgress tick)
/// → [finish] (on success, cancel or failure). [visible] is true between start
/// and finish; [label] is the shared downloadingAudioLabel line for the latest
/// tick. The "of N" count is the highest stop number seen, so it only ever
/// grows (a later stop never makes the total shrink).
class DownloadProgressController extends ChangeNotifier {
  bool _visible = false;
  int _maxStop = 1;
  int _stop = 1;
  int _received = 0;
  int? _total;

  bool get visible => _visible;

  /// The user-facing line for the current tick, from the one shared helper so
  /// the wording matches every other download site.
  String get label => downloadingAudioLabel(
        stopIndex: _stop,
        stopCount: _maxStop,
        receivedBytes: _received,
        totalBytes: _total,
      );

  /// Begin a download: show the banner, reset the counters.
  void start() {
    _visible = true;
    _maxStop = 1;
    _stop = 1;
    _received = 0;
    _total = null;
    notifyListeners();
  }

  /// Apply one progress tick. The banner stays mounted; only its text/bar move.
  void update(RemoteAudioProgress p) {
    if (!_visible) _visible = true;
    _stop = p.stopNumber;
    if (p.stopNumber > _maxStop) _maxStop = p.stopNumber;
    _received = p.receivedBytes;
    _total = p.totalBytes;
    notifyListeners();
  }

  /// End the download — the banner disappears (success / cancel / failure).
  void finish() {
    if (!_visible) return;
    _visible = false;
    notifyListeners();
  }

  /// The fraction complete for the current stop, or null when the total is
  /// unknown (the bar is then indeterminate).
  double? get fraction {
    final t = _total;
    if (t == null || t <= 0) return null;
    final f = _received / t;
    return f.isNaN ? null : f.clamp(0.0, 1.0);
  }
}

/// The persistent banner. Renders nothing when the controller is not visible,
/// so the host can place it unconditionally (e.g. above a tour list). When
/// visible it shows the progress line, a determinate-or-indeterminate
/// LinearProgressIndicator and a Cancel button wired to [onCancel].
class DownloadProgressBanner extends StatelessWidget {
  final DownloadProgressController controller;
  final VoidCallback onCancel;

  const DownloadProgressBanner({
    super.key,
    required this.controller,
    required this.onCancel,
  });

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        if (!controller.visible) return const SizedBox.shrink();
        return Material(
          color: const Color(0xFFEFF4FF),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        controller.label,
                        key: const Key('download_progress_label'),
                        style: const TextStyle(
                            fontWeight: FontWeight.w600,
                            color: Color(0xFF1B3A7A)),
                      ),
                    ),
                    TextButton(
                      key: const Key('download_progress_cancel'),
                      onPressed: onCancel,
                      child: const Text('Cancel'),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                LinearProgressIndicator(
                  key: const Key('download_progress_bar'),
                  value: controller.fraction,
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
