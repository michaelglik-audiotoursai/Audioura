import 'package:flutter/material.dart';
import 'dart:async';
import '../services/stop_feedback_service.dart';
import '../screens/debug_log_viewer_screen.dart';

/// Swipe-to-rate overlay for the tour player.
///
/// Renders like/dislike buttons at the bottom of the screen. On tap:
/// 1. Records the swipe optimistically (queue + retry).
/// 2. Shows a brief confirmation with undo affordance.
/// 3. Fades back to the idle state after 4 seconds.
///
/// Why buttons instead of a gesture:
/// - Discoverability: a swipe gesture on a WebView is invisible and conflicts
///   with scroll. Buttons are always visible and tap-targetable.
/// - One-handed use: large thumb targets at bottom of screen, reachable while
///   walking and holding the phone in one hand.
/// - Accessibility: buttons have semantics, labels, and haptic feedback.
///   A swipe gesture cannot be discovered by screen readers.
///
/// The user swipes on THE STOP, not on a category. The three-class taxonomy
/// is how we interpret the signal — it never appears in the UI.
class SwipeFeedbackWidget extends StatefulWidget {
  /// Current stop index (0-based, matches WebView's currentStopIndex).
  final int currentStopIndex;

  /// Tour ID for this tour (from saved_tours entry).
  final String tourId;

  /// Optional job ID for this tour.
  final String? jobId;

  /// Path to the tour directory (for loading stop_metrics.json).
  final String tourPath;

  /// [LOCAL-670] Human-readable name of the current stop, shown in the "This
  /// stop:" label and the confirmation toast so the thumbs read clearly as a
  /// PER-STOP judgement (distinct from the per-TOUR 1–10 rating). Null/empty
  /// falls back to a generic phrasing; behaviour is otherwise unchanged.
  final String? stopName;

  /// [LOCAL-907E] Title of the region topic playing between two stops, or null
  /// when a stop is playing. While set, the label reads "Topic · <title>" (not
  /// "This stop"), because the audio now playing is not the stop.
  final String? topicTitle;

  /// Called when a swipe is registered (for parent notification, e.g. haptics).
  final void Function(int swipe)? onSwipe;

  const SwipeFeedbackWidget({
    super.key,
    required this.currentStopIndex,
    required this.tourId,
    this.jobId,
    required this.tourPath,
    this.stopName,
    this.topicTitle,
    this.onSwipe,
  });

  /// [LOCAL-907E] The label above the thumbs.
  static String labelFor({String? stopName, String? topicTitle}) {
    final t = topicTitle?.trim() ?? '';
    if (t.isNotEmpty) return 'Topic · $t';
    final n = stopName?.trim() ?? '';
    return n.isNotEmpty ? 'This stop: $n' : 'This stop:';
  }

  @override
  State<SwipeFeedbackWidget> createState() => SwipeFeedbackWidgetState();
}

/// Visible for testing — allows test code to access state directly.
class SwipeFeedbackWidgetState extends State<SwipeFeedbackWidget>
    with SingleTickerProviderStateMixin {
  final StopFeedbackService _feedbackService = StopFeedbackService();

  /// Tracks the last swipe per stop index to prevent double-swiping.
  final Map<int, int> _swipedStops = {};

  /// State for the confirmation/undo display.
  _FeedbackState _state = _FeedbackState.idle;
  int? _lastSwipe;
  Timer? _undoTimer;

  /// [LOCAL-877] The listener closed the thumbs (x). Sticky for this player.
  bool _dismissed = false;

  /// [LOCAL-877] The collapsed "thanks · change" chip was opened to change.
  bool _changing = false;

  /// Metrics cache (loaded once per tour).
  Map<int, Map<String, double>>? _stopMetrics;

  @override
  void initState() {
    super.initState();
    _loadMetrics();
  }

  @override
  void didUpdateWidget(covariant SwipeFeedbackWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    // [LOCAL-877] A new stop is a fresh question; a confirmation or chip that
    // belongs to the previous stop must not linger.
    if (oldWidget.currentStopIndex != widget.currentStopIndex) {
      _undoTimer?.cancel();
      _changing = false;
      _state = _swipedStops.containsKey(widget.currentStopIndex)
          ? _FeedbackState.answered
          : _FeedbackState.idle;
    }
  }

  @override
  void dispose() {
    _undoTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadMetrics() async {
    _stopMetrics = await StopFeedbackService.loadStopMetrics(widget.tourPath);
    if (_stopMetrics != null) {
      await DebugLogHelper.addDebugLog(
        'SWIPE: Loaded stop_metrics.json with ${_stopMetrics!.length} stops',
      );
    }
  }

  /// Called when the user taps like (+1) or dislike (-1).
  Future<void> _handleSwipe(int swipe) async {
    final stopIndex = widget.currentStopIndex;

    // [LOCAL-877] Same answer again: nothing to do. A DIFFERENT answer changes
    // the earlier one (an update, never a second thumb).
    final earlier = _swipedStops[stopIndex];
    if (earlier == swipe) {
      await DebugLogHelper.addDebugLog(
        'SWIPE: Stop $stopIndex already rated $swipe — ignoring duplicate',
      );
      if (mounted) setState(() => _changing = false);
      return;
    }

    // Record optimistically
    _swipedStops[stopIndex] = swipe;
    _lastSwipe = swipe;

    // Get metrics for this stop (or null for defaults)
    final metrics = _stopMetrics?[stopIndex];

    if (earlier != null) {
      await _feedbackService.changeSwipe(
        stopIndex: stopIndex,
        swipe: swipe,
        tourId: widget.tourId,
        jobId: widget.jobId,
        stopMetrics: metrics,
      );
    } else {
      await _feedbackService.recordSwipe(
        stopIndex: stopIndex,
        swipe: swipe,
        tourId: widget.tourId,
        jobId: widget.jobId,
        stopMetrics: metrics,
      );
    }

    // Notify parent (for haptic feedback, etc.)
    widget.onSwipe?.call(swipe);

    // Show confirmation + undo
    if (mounted) {
      setState(() {
        _state = _FeedbackState.confirmed;
        _changing = false;
      });
    }

    // [LOCAL-877] After 4 seconds collapse to the small "thanks · change" chip
    // (it used to fall back to the big thumbs, which never went away).
    _undoTimer?.cancel();
    _undoTimer = Timer(const Duration(seconds: 4), () {
      if (mounted) {
        setState(() => _state = _FeedbackState.answered);
      }
    });
  }

  /// Undo the most recent swipe.
  Future<void> _handleUndo() async {
    final stopIndex = widget.currentStopIndex;
    _undoTimer?.cancel();

    final originalSwipe = _swipedStops[stopIndex] ?? 1;
    final removed = await _feedbackService.undoLastSwipe(
      stopIndex: stopIndex,
      tourId: widget.tourId,
    );

    _swipedStops.remove(stopIndex);
    _lastSwipe = null;

    if (mounted) {
      setState(() => _state = _FeedbackState.undone);
    }

    await DebugLogHelper.addDebugLog(
      'SWIPE: Undo for stop $stopIndex — ${removed ? "removed from queue" : "reversal queued"}',
    );

    // If the swipe was already sent, queue a reversal
    if (!removed) {
      // The original swipe was already flushed; queue opposite swipe
      await _feedbackService.recordSwipe(
        stopIndex: stopIndex,
        swipe: -originalSwipe,
        tourId: widget.tourId,
        jobId: widget.jobId,
        stopMetrics: _stopMetrics?[stopIndex],
      );
    }

    // Return to idle after brief confirmation
    Timer(const Duration(seconds: 2), () {
      if (mounted) {
        setState(() => _state = _FeedbackState.idle);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_dismissed) return const SizedBox.shrink(key: ValueKey('feedback_dismissed'));
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 300),
      child: _buildContent(),
    );
  }

  Widget _buildContent() {
    switch (_state) {
      case _FeedbackState.idle:
        return _buildSwipeButtons();
      case _FeedbackState.answered:
        // The collapsed chip, or the thumbs again once "change" is tapped.
        return _changing ? _buildSwipeButtons() : _buildAnsweredChip();
      case _FeedbackState.confirmed:
        return _buildConfirmation();
      case _FeedbackState.undone:
        return _buildUndoneConfirmation();
    }
  }

  Widget _buildSwipeButtons() {
    final answer = _swipedStops[widget.currentStopIndex];
    final alreadySwiped = answer != null;

    return Container(
      key: const ValueKey('swipe_buttons'),
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // [LOCAL-670] Make clear these thumbs rate THIS STOP, not the whole
          // tour (the tour has its own 1–10 rating). Show the stop name when we
          // have it so there is no ambiguity about what is being rated.
          Row(
            children: [
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.only(bottom: 4, left: 32),
                  child: Text(
                    SwipeFeedbackWidget.labelFor(
                        stopName: widget.stopName,
                        topicTitle: widget.topicTitle),
                    key: const ValueKey('swipe_label'),
                    textAlign: TextAlign.center,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: Color(0xFF7F8C8D),
                    ),
                  ),
                ),
              ),
              _buildDismissButton(),
            ],
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // Dislike button
              _FeedbackButton(
                icon: Icons.thumb_down_outlined,
                activeIcon: Icons.thumb_down,
                color: const Color(0xFFE74C3C),
                label: 'Not for me',
                isActive: alreadySwiped && _swipedStops[widget.currentStopIndex] == -1,
                isDisabled: false,
                onTap: () => _handleSwipe(-1),
                semanticLabel: 'Dislike this stop',
              ),
              const SizedBox(width: 48),
              // Like button
              _FeedbackButton(
                icon: Icons.thumb_up_outlined,
                activeIcon: Icons.thumb_up,
                color: const Color(0xFF27AE60),
                label: 'More like this',
                isActive: alreadySwiped && _swipedStops[widget.currentStopIndex] == 1,
                isDisabled: false,
                onTap: () => _handleSwipe(1),
                semanticLabel: 'Like this stop',
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildDismissButton() {
    return IconButton(
      key: const ValueKey('feedback_dismiss'),
      tooltip: 'Hide',
      icon: const Icon(Icons.close, size: 18, color: Color(0xFF7F8C8D)),
      visualDensity: VisualDensity.compact,
      constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
      padding: EdgeInsets.zero,
      onPressed: () {
        _undoTimer?.cancel();
        setState(() => _dismissed = true);
      },
    );
  }

  /// [LOCAL-877] Small collapsed state after a choice: "✓ Thanks · change" and
  /// a dismiss (x). Tapping "change" re-opens the thumbs so the other one can
  /// be picked.
  Widget _buildAnsweredChip() {
    final isLike = _swipedStops[widget.currentStopIndex] == 1;
    return Padding(
      key: const ValueKey('answered_chip'),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            padding: const EdgeInsets.only(left: 12, right: 4),
            decoration: BoxDecoration(
              color: const Color(0xFFEFF3F5),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(isLike ? Icons.thumb_up : Icons.thumb_down,
                    size: 14,
                    color: isLike
                        ? const Color(0xFF27AE60)
                        : const Color(0xFFE74C3C)),
                const SizedBox(width: 6),
                const Text('✓ Thanks · ',
                    style: TextStyle(fontSize: 13, color: Color(0xFF2c3e50))),
                InkWell(
                  key: const ValueKey('feedback_change'),
                  onTap: () => setState(() => _changing = true),
                  child: const Padding(
                    padding: EdgeInsets.symmetric(vertical: 8),
                    child: Text('change',
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: Color(0xFF3498DB),
                        )),
                  ),
                ),
                _buildDismissButton(),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildConfirmation() {
    final isLike = _lastSwipe == 1;
    // [LOCAL-670] Name the stop in the confirmation so the listener sees the
    // judgement was recorded against THIS stop, not the whole tour.
    final hasName = widget.stopName != null && widget.stopName!.trim().isNotEmpty;
    final suffix = hasName ? ' for "${widget.stopName}"' : ' for this stop';
    final message = isLike
        ? 'Noted — more like this$suffix'
        : 'Noted — less like this$suffix';
    return Container(
      key: const ValueKey('confirmation'),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            isLike ? Icons.thumb_up : Icons.thumb_down,
            color: isLike ? const Color(0xFF27AE60) : const Color(0xFFE74C3C),
            size: 20,
          ),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              message,
              style: TextStyle(
                color: isLike ? const Color(0xFF27AE60) : const Color(0xFFE74C3C),
                fontWeight: FontWeight.w500,
                fontSize: 14,
              ),
            ),
          ),
          const SizedBox(width: 16),
          TextButton(
            onPressed: _handleUndo,
            style: TextButton.styleFrom(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              minimumSize: const Size(60, 32),
            ),
            child: const Text(
              'Undo',
              style: TextStyle(
                color: Color(0xFF3498DB),
                fontWeight: FontWeight.w600,
                fontSize: 14,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildUndoneConfirmation() {
    return Container(
      key: const ValueKey('undone'),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: const Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.undo, color: Color(0xFF7F8C8D), size: 20),
          SizedBox(width: 8),
          Text(
            'Rating removed',
            style: TextStyle(
              color: Color(0xFF7F8C8D),
              fontWeight: FontWeight.w500,
              fontSize: 14,
            ),
          ),
        ],
      ),
    );
  }
}

/// Internal state machine for the feedback widget.
enum _FeedbackState { idle, confirmed, undone, answered }

/// A single like/dislike button with proper touch targets and semantics.
class _FeedbackButton extends StatelessWidget {
  final IconData icon;
  final IconData activeIcon;
  final Color color;
  final String label;
  final bool isActive;
  final bool isDisabled;
  final VoidCallback onTap;
  final String semanticLabel;

  const _FeedbackButton({
    required this.icon,
    required this.activeIcon,
    required this.color,
    required this.label,
    required this.isActive,
    required this.isDisabled,
    required this.onTap,
    required this.semanticLabel,
  });

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: semanticLabel,
      button: true,
      enabled: !isDisabled,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: isDisabled ? null : onTap,
          borderRadius: BorderRadius.circular(24),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  isActive ? activeIcon : icon,
                  color: isDisabled
                      ? color.withValues(alpha: 0.4)
                      : color,
                  size: 28,
                ),
                const SizedBox(height: 4),
                Text(
                  label,
                  style: TextStyle(
                    color: isDisabled
                        ? color.withValues(alpha: 0.4)
                        : color,
                    fontSize: 11,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
