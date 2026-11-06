// [LOCAL-877] Persistent bottom player bar.
//
// Sophia: "I want a bigger play pause button at the bottom of the app anytime
// audio is playing." Shown above the tab bar on EVERY screen whenever a tour's
// audio is playing or paused mid-stop. Hidden when idle.
//
// Contents: stop title, progress bar, previous / BIG play-pause / next. Tapping
// the title area opens the tour at the current stop. After a cold start (no live
// player) it reads "Resume <tour>, stop N" and play re-opens the tour there.

import 'package:flutter/material.dart';

import '../services/player_session.dart';

/// Diameter of the play/pause button, in dp. Spec: >= 64.
const double kPlayPauseSize = 64;

const Key kPlayerBarKey = ValueKey('persistent_player_bar');
const Key kPlayerBarPlayPauseKey = ValueKey('player_bar_play_pause');
const Key kPlayerBarNextKey = ValueKey('player_bar_next');
const Key kPlayerBarPrevKey = ValueKey('player_bar_prev');
const Key kPlayerBarOpenKey = ValueKey('player_bar_open');
const Key kPlayerBarProgressKey = ValueKey('player_bar_progress');
const Key kPlayerBarDismissKey = ValueKey('player_bar_dismiss');

class PersistentPlayerBar extends StatelessWidget {
  final PlayerSession session;

  /// Open the tour at its current stop (tap on the bar / resume).
  final void Function(PlayerSnapshot snapshot) onOpen;

  const PersistentPlayerBar({
    super.key,
    required this.session,
    required this.onOpen,
  });

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<PlayerSnapshot?>(
      valueListenable: session.snapshot,
      builder: (context, s, _) {
        if (s == null || !s.started) return const SizedBox.shrink();
        return _Bar(session: session, s: s, onOpen: onOpen);
      },
    );
  }
}

class _Bar extends StatelessWidget {
  final PlayerSession session;
  final PlayerSnapshot s;
  final void Function(PlayerSnapshot) onOpen;
  const _Bar({required this.session, required this.s, required this.onOpen});

  String get _title {
    final n = s.stopIndex + 1;
    if (!s.live) return 'Resume ${s.tourTitle}, stop $n';
    final name = (s.stopName ?? '').trim();
    return name.isNotEmpty ? name : 'Stop $n';
  }

  String get _subtitle {
    final n = s.stopIndex + 1;
    final of = s.totalStops != null ? ' of ${s.totalStops}' : '';
    return s.live ? '${s.tourTitle} · Stop $n$of' : 'Tap play to continue';
  }

  @override
  Widget build(BuildContext context) {
    final cmds = session.commands;
    final live = s.live && cmds != null;

    Future<void> toggle() async {
      if (!live) {
        onOpen(s); // cold start / player gone: reopen at the saved stop.
        return;
      }
      if (s.playing) {
        await cmds.pause();
      } else {
        await cmds.play();
      }
    }

    return Material(
      key: kPlayerBarKey,
      color: const Color(0xFF2c3e50),
      elevation: 8,
      child: SafeArea(
        top: false,
        bottom: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Progress bar (thin, full width, on top of the controls).
            LinearProgressIndicator(
              key: kPlayerBarProgressKey,
              value: s.progress,
              minHeight: 3,
              backgroundColor: Colors.white24,
              valueColor: const AlwaysStoppedAnimation(Color(0xFF3498db)),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              child: Row(
                children: [
                  // Title area: tap opens the tour at the current stop.
                  Expanded(
                    child: Semantics(
                      button: true,
                      label: 'Open tour at current stop',
                      child: InkWell(
                        key: kPlayerBarOpenKey,
                        onTap: () => onOpen(s),
                        child: Padding(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 4),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(
                                _title,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w600,
                                  fontSize: 15,
                                ),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                _subtitle,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                    color: Colors.white70, fontSize: 12),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                  IconButton(
                    key: kPlayerBarPrevKey,
                    tooltip: 'Previous stop',
                    iconSize: 32,
                    color: Colors.white,
                    disabledColor: Colors.white30,
                    onPressed:
                        live && s.hasPrevious ? () => cmds.previous() : null,
                    icon: const Icon(Icons.skip_previous),
                  ),
                  SizedBox(
                    width: kPlayPauseSize,
                    height: kPlayPauseSize,
                    child: Semantics(
                      button: true,
                      label: s.playing && live ? 'Pause' : 'Play',
                      child: Material(
                        color: const Color(0xFF3498db),
                        shape: const CircleBorder(),
                        child: InkWell(
                          key: kPlayerBarPlayPauseKey,
                          customBorder: const CircleBorder(),
                          onTap: toggle,
                          child: Icon(
                            s.playing && live
                                ? Icons.pause
                                : Icons.play_arrow,
                            color: Colors.white,
                            size: 40,
                          ),
                        ),
                      ),
                    ),
                  ),
                  IconButton(
                    key: kPlayerBarNextKey,
                    tooltip: 'Next stop',
                    iconSize: 32,
                    color: Colors.white,
                    disabledColor: Colors.white30,
                    onPressed: live && s.hasNext ? () => cmds.next() : null,
                    icon: const Icon(Icons.skip_next),
                  ),
                  if (!s.live)
                    IconButton(
                      key: kPlayerBarDismissKey,
                      tooltip: 'Dismiss',
                      color: Colors.white70,
                      onPressed: () => session.clear(),
                      icon: const Icon(Icons.close),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
