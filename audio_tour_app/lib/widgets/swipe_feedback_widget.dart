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

  /// Called when a swipe is registered (for parent notification, e.g. haptics).
  final void Function(int swipe)? onSwipe;

  const SwipeFeedbackWidget({
    super.key,
    required this.currentStopIndex,
    required this.tourId,
    this.jobId,
    required this.tourPath,
    this.onSwipe,
  });

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

  /// Metrics cache (loaded once per tour).
  Map<int, Map<String, double>>? _stopMetrics;

  @override
  void initState() {
    super.initState();
    _loadMetrics();
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

    // Prevent double-swipe on same stop
    if (_swipedStops.containsKey(stopIndex)) {
      await DebugLogHelper.addDebugLog(
        'SWIPE: Stop $stopIndex already rated — ignoring duplicate',
      );
      return;
    }

    // Record optimistically
    _swipedStops[stopIndex] = swipe;
    _lastSwipe = swipe;

    // Get metrics for this stop (or null for defaults)
    final metrics = _stopMetrics?[stopIndex];

    await _feedbackService.recordSwipe(
      stopIndex: stopIndex,
      swipe: swipe,
      tourId: widget.tourId,
      jobId: widget.jobId,
      stopMetrics: metrics,
    );

    // Notify parent (for haptic feedback, etc.)
    widget.onSwipe?.call(swipe);

    // Show confirmation + undo
    if (mounted) {
      setState(() => _state = _FeedbackState.confirmed);
    }

    // Auto-dismiss after 4 seconds
    _undoTimer?.cancel();
    _undoTimer = Timer(const Duration(seconds: 4), () {
      if (mounted) {
        setState(() => _state = _FeedbackState.idle);
      }
    });
  }

  /// Undo the most recent swipe.
  Future<void> _handleUndo() async {
    final stopIndex = widget.currentStopIndex;
    _undoTimer?.cancel();

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
      final originalSwipe = _swipedStops[stopIndex] ?? 1;
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
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 300),
      child: _buildContent(),
    );
  }

  Widget _buildContent() {
    switch (_state) {
      case _FeedbackState.idle:
        return _buildSwipeButtons();
      case _FeedbackState.confirmed:
        return _buildConfirmation();
      case _FeedbackState.undone:
        return _buildUndoneConfirmation();
    }
  }

  Widget _buildSwipeButtons() {
    final alreadySwiped = _swipedStops.containsKey(widget.currentStopIndex);

    return Container(
      key: const ValueKey('swipe_buttons'),
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // Dislike button
          _FeedbackButton(
            icon: Icons.thumb_down_outlined,
            activeIcon: Icons.thumb_down,
            color: const Color(0xFFE74C3C),
            label: 'Not for me',
            isActive: alreadySwiped && _swipedStops[widget.currentStopIndex] == -1,
            isDisabled: alreadySwiped,
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
            isDisabled: alreadySwiped,
            onTap: () => _handleSwipe(1),
            semanticLabel: 'Like this stop',
          ),
        ],
      ),
    );
  }

  Widget _buildConfirmation() {
    final isLike = _lastSwipe == 1;
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
          Text(
            isLike ? 'Noted — more like this' : 'Noted — less like this',
            style: TextStyle(
              color: isLike ? const Color(0xFF27AE60) : const Color(0xFFE74C3C),
              fontWeight: FontWeight.w500,
              fontSize: 14,
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
enum _FeedbackState { idle, confirmed, undone }

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
