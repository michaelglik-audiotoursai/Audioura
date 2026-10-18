import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:path_provider/path_provider.dart';
import 'dart:async';
import 'voice_methods.dart';
import 'debug_log_viewer_screen.dart';
import 'tour_map_screen.dart';
import '../widgets/swipe_feedback_widget.dart';
import '../services/webview_console_logger.dart';
import '../widgets/share_tour_sheet.dart';
import '../widgets/rate_tour_dialog.dart';
import '../services/tour_listen_service.dart';
import '../services/playback_accumulator.dart';
import '../services/tour_pricing_service.dart';
import '../services/downloaded_tour_meta.dart';
import '../widgets/tour_buy_sheet.dart';
import '../services/single_playback_controller.dart';

class TourPlayerScreen extends StatefulWidget {
  final String tourPath;
  final String tourTitle;
  final String? tourId;
  final String? jobId;
  /// Stored track that produced this tour ('beta'|'storied'); null/unknown ⇒
  /// Stable. Display-only; drives the provenance label. See wdvrdaxxmb.
  final String? track;
  /// Build number stored on the tour record; null when the tour predates the
  /// field. Rendered as "(vNNN)" when present, omitted when absent.
  final int? buildNumber;

  /// [LOCAL-677B] The NUMERIC server tour id the pricing/unlock endpoints key
  /// on. Distinct from [tourId] (the editable id, often non-numeric). When
  /// provided, the player asks `/tour/<serverTourId>/unlock-state` with the
  /// RIGHT id — the fix for the Bounce (a downloaded tour opened by path used to
  /// have only a non-numeric id, so the player never asked and every stop
  /// played). When null, the player recovers it from the local saved_tours
  /// record (by [tourPath]) so every entry path works.
  final String? serverTourId;

  /// [LOCAL-677B] The tour's original language code (e.g. 'en', 'ru'), shown in
  /// the player header as "Original: <Language>" like the found-tour dialog.
  final String? originalLanguage;

  const TourPlayerScreen({
    super.key,
    required this.tourPath,
    required this.tourTitle,
    this.tourId,
    this.jobId,
    this.track,
    this.buildNumber,
    this.serverTourId,
    this.originalLanguage,
  });

  @override
  State<TourPlayerScreen> createState() => _TourPlayerScreenState();
}

class _TourPlayerScreenState extends State<TourPlayerScreen> with VoiceMethods {
  InAppWebViewController? _controller;
  int _currentStopIndex = 0;
  // [LOCAL-670] Current stop's display name (for the per-stop thumbs label),
  // reported from the WebView. _ratePrompted guards the end-of-tour "Rate this
  // tour" prompt so it fires at most once.
  String? _currentStopName;
  bool _ratePrompted = false;
  // [LOCAL-670B] Total stops in the tour, reported by the WebView, used to
  // compute the listened-stops threshold (a short tour needs all its stops).
  int? _totalStops;

  // [LOCAL-670C] One playback-time accumulator per stop index. Fed raw
  // play/pause/seek/rate/tick/ended events from the WebView; verifies "listened"
  // from genuinely played time so a scrub never fakes it. A stop that has
  // already been recorded listened is dropped from the map so we stop counting.
  final Map<int, PlaybackAccumulator> _accumulators = {};
  final Set<int> _listenedRecorded = {};

  // LOCAL-483: forward the tour player WebView's JS console into the debug log.
  final WebViewConsoleLogger _consoleLogger =
      WebViewConsoleLogger(source: 'tour-player');

  // [LOCAL-677] Paid-tour preview/lock state. Null until the first fetch; a
  // free tour resolves to an unlocked state so the banner never shows. When the
  // tour is paid and NOT unlocked, Stop 1 plays as a preview and a "Buy for $X"
  // banner invites the listener to unlock the rest.
  TourUnlockState? _unlockState;

  // [LOCAL-677B] The resolved NUMERIC server tour id (widget.serverTourId →
  // numeric widget.tourId → the server id stored on the local record). Null when
  // the tour has no numeric id at all (e.g. a brand-new local-only tour).
  String? _serverTourId;

  // [LOCAL-677B] The offline snapshot read from the local saved_tours record.
  // Used to gate playback when the server cannot be reached (D647 add. 2:
  // fail closed for a tour stored paid, free stays free), and to show the header.
  DownloadedTourMeta? _localMeta;

  // [LOCAL-677B] How many opening stops play free as a preview on a locked tour.
  int _freePreviewStops = 1;

  @override
  void initState() {
    super.initState();
    _initializeWebView();
    initializeVoiceControl();
    _loadUnlockState();
  }

  /// [LOCAL-677 / 677B / 677C] Resolve the tour's unlock/preview state.
  ///
  /// [LOCAL-677C / D654] Pay BEFORE download: a downloaded tour has already been
  /// paid for (the server 402-gated the download) or was free/grandfathered, so
  /// it PLAYS FULLY — there is no in-player preview lock and no Buy banner for a
  /// downloaded tour. The only remaining in-player check is one QUIET online
  /// re-check for a REFUND (LOCAL-672): if, and ONLY if, the server is reached
  /// and explicitly says this tour is paid AND not unlocked (and not
  /// grandfathered), the tour locks on that check. Offline, or any inconclusive
  /// answer, leaves the tour fully playable.
  Future<void> _loadUnlockState() async {
    // 1. Local snapshot (never throws; returns a free/unlocked default).
    final meta = await DownloadedTourStore.metaForPath(widget.tourPath);

    // 2. Resolve the numeric server id from the best available source.
    final serverId = DownloadedTourMeta.resolveServerTourId(
      serverTourId: widget.serverTourId,
      widgetTourId: widget.tourId,
      metaServerTourId: meta.serverTourId,
    );

    // 3. Default: a downloaded tour is PLAYABLE (D654). Offline = always
    //    playable; we never gate a downloaded tour from the local snapshot.
    TourUnlockState resolved = TourUnlockState.free();

    // 4. One quiet online re-check for a refund. Only an EXPLICIT server answer
    //    (answered == true) that the tour is paid AND locked flips it to locked;
    //    an offline/failed check leaves it playable. Grandfathering is honoured
    //    from the LOCAL snapshot: a tour downloaded while FREE was stamped
    //    is_paid:false (677B), so we never lock it even if the row is now priced
    //    — the refund lock applies only to a tour this device actually bought
    //    (stored paid).
    if (serverId != null &&
        int.tryParse(serverId) != null &&
        meta.isPaid) {
      final check = await TourPricingService.unlockStateChecked(serverId);
      if (check.answered && check.state.isPaid && check.state.locked) {
        // The server says: paid and NOT unlocked for this device (a refund, or
        // the unlock was revoked). Lock the tour on this online check.
        resolved = check.state;
        // Reflect the revocation in the local snapshot so a later offline open
        // stays locked too (the purchase is gone).
        await DownloadedTourStore.markLockedForPath(widget.tourPath);
      } else if (check.answered && check.state.isPaid && check.state.unlocked) {
        // Confirmed still owned — keep the local snapshot in sync.
        if (!meta.unlocked) {
          await DownloadedTourStore.markUnlockedForPath(widget.tourPath);
        }
      }
    }

    if (mounted) {
      setState(() {
        _localMeta = meta;
        _serverTourId = serverId;
        _unlockState = resolved;
        _freePreviewStops = resolved.freePreviewStops;
      });
    }
    // Enforce the lock inside the WebView ONLY in the refund case; a playable
    // tour lifts any guard.
    await _applyLockToWebView();
  }

  /// [LOCAL-677B] Enforce the lock inside the WebView: when the tour is locked,
  /// block the audio of every stop at/after the free-preview count (Stop 1 plays
  /// as a preview; the rest are paused and rewound if play is attempted). When
  /// unlocked, the block is lifted. Safe to call before the page loads (the
  /// injected guard installs itself and also runs on the next load).
  Future<void> _applyLockToWebView() async {
    final controller = _controller;
    if (controller == null) return;
    final locked = _unlockState?.locked == true;
    final freeStops = _freePreviewStops;
    try {
      await controller.evaluateJavascript(source: """
        (function() {
          window.__audiouraLocked = $locked;
          window.__audiouraFreeStops = $freeStops;
          if (window.__audiouraLockInstalled) { return; }
          window.__audiouraLockInstalled = true;
          var audios = document.querySelectorAll('audio');
          audios.forEach(function(audio, idx) {
            audio.addEventListener('play', function() {
              if (window.__audiouraLocked && idx >= window.__audiouraFreeStops) {
                try { audio.pause(); audio.currentTime = 0; } catch (e) {}
              }
            });
          });
        })();
      """);
    } catch (_) {
      // A gate that cannot inject must not crash the player; the banner still
      // shows and the server-side gate remains authoritative.
    }
  }

  /// [LOCAL-677] Offer the Buy / TEST PURCHASE sheet; on unlock, refresh state.
  Future<void> _offerBuy() async {
    final s = _unlockState;
    if (s == null || !s.locked || s.priceTier == null) return;
    final tourId = _serverTourId ?? widget.serverTourId ?? widget.tourId ?? _deriveTourId();
    final unlocked = await TourBuySheet.show(
      context,
      tourId: tourId,
      tier: s.priceTier!,
      priceLabel: s.priceLabel,
      tourTitle: widget.tourTitle,
    );
    if (unlocked) {
      // [LOCAL-677B] Write the unlock to the LOCAL record at once so the lock
      // lifts OFFLINE immediately (it also synced to the server through the
      // purchase path). Then refresh and lift the WebView block.
      await DownloadedTourStore.markUnlockedForPath(widget.tourPath);
      await _loadUnlockState();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Tour unlocked — enjoy the full tour!')),
        );
      }
    }
  }

  /// [LOCAL-677] The preview/lock banner over the player: "Stop 1 is a free
  /// preview" + a "Buy for $X" button that opens the buy/TEST PURCHASE sheet.
  Widget _buildBuyBanner() {
    final s = _unlockState!;
    return Material(
      color: Colors.orange.shade50,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Row(
          children: [
            Icon(Icons.lock_outline, color: Colors.orange.shade800, size: 20),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                'Stop 1 is a free preview. Unlock the full tour.',
                style: TextStyle(fontSize: 13, color: Colors.orange.shade900),
              ),
            ),
            const SizedBox(width: 8),
            ElevatedButton(
              onPressed: _offerBuy,
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF1B6B2E),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                minimumSize: const Size(0, 36),
              ),
              child: Text('Buy for ${s.priceLabel}'),
            ),
          ],
        ),
      ),
    );
  }

  /// [LOCAL-677B] The player header line "Original: <Language> · v12", shown
  /// above the WebView like the found-tour dialog. The original language comes
  /// from widget.originalLanguage, else the local snapshot. The version comes
  /// from widget.buildNumber (stored on the tour record). Returns an empty box
  /// when there is nothing to show, so an old tour renders no header.
  Widget _buildOriginalHeader() {
    final lang = widget.originalLanguage ?? _localMeta?.originalLanguage;
    final version = widget.buildNumber ?? _localMeta?.tourVersion;
    final parts = <String>[];
    if (lang != null && lang.trim().isNotEmpty) {
      parts.add('Original: ${_languageName(lang.trim())}');
    }
    if (version != null && version > 1) {
      parts.add('v$version');
    }
    if (parts.isEmpty) return const SizedBox.shrink();
    return Material(
      color: const Color(0xFFF2F4F6),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        child: Row(
          children: [
            Icon(Icons.language, size: 16, color: Colors.grey.shade700),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                parts.join(' · '),
                style: TextStyle(
                  fontSize: 12.5,
                  color: Colors.grey.shade800,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Human language name for a code (shared with the found-tour dialog's set).
  String _languageName(String code) {
    switch (code.toLowerCase()) {
      case 'en':
        return 'English';
      case 'es':
        return 'Spanish';
      case 'fr':
        return 'French';
      case 'de':
        return 'German';
      case 'ru':
        return 'Russian';
      case 'zh':
        return 'Chinese';
      default:
        return code.toUpperCase();
    }
  }

  @override
  void dispose() {
    disposeVoice();
    _consoleLogger.flush();
    super.dispose();
  }

  void _initializeWebView() {
    // InAppWebView will be initialized in the build method
  }
  
  Future<String> _getIndexUrl() async {
    // Mobile platform only: use file URL.
    // A#56: heal stale container path. iOS reassigns the app container UUID on
    // reinstall, so the stored tour path can point at an old container that is
    // now outside the sandbox (white screen). Re-anchor it to the current
    // Documents directory before building the file URL.
    String tourPath = widget.tourPath;
    const docsMarker = '/Documents/';
    final mi = tourPath.indexOf(docsMarker);
    if (mi != -1) {
      final docsDir = await getApplicationDocumentsDirectory();
      final healedPath =
          '${docsDir.path}/${tourPath.substring(mi + docsMarker.length)}';
      if (healedPath != tourPath) {
        await DebugLogHelper.addDebugLog('TOUR_PLAYER: Healed stale container path');
        tourPath = healedPath;
      }
    }
    final fileUrl = 'file://$tourPath/index.html';
    await DebugLogHelper.addDebugLog('TOUR_PLAYER: Using mobile file URL: $fileUrl');
    return fileUrl;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.tourTitle),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
        actions: [
          // Track/release provenance is intentionally NOT shown here — a
          // visible "Stable"/"Preview" mark confuses testers. Provenance is
          // available on demand via the "Version" item in the ⋮ menu on the
          // tour list. See wdvrdaxxmb.
          IconButton(
            icon: Icon(Icons.help_outline),
            onPressed: _showTourHelpDialog,
            tooltip: 'Voice Commands Help',
          ),
          IconButton(
            icon: const Icon(Icons.ios_share),
            onPressed: _shareTour,
            tooltip: 'Share this tour',
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => _controller?.reload(),
          ),
        ],
      ),
      body: FutureBuilder<String>(
        future: _getIndexUrl(),
        builder: (context, snapshot) {
          if (snapshot.hasData) {
            return Column(
              children: [
                // [LOCAL-677B] Listen/player header: "Original: <Language>" and
                // the version, matching the found-tour dialog. Hidden when the
                // tour carries neither (an old tour with no original_language and
                // no version field shows no header).
                _buildOriginalHeader(),
                // [LOCAL-677] Paid-tour preview banner. Stop 1 plays free; the
                // rest is locked until the listener buys. Shown only while the
                // tour is paid and not yet unlocked.
                if (_unlockState?.locked == true) _buildBuyBanner(),
                Expanded(
                  child: InAppWebView(
                    initialUrlRequest: URLRequest(url: WebUri(snapshot.data!)),
                    initialSettings: InAppWebViewSettings(
                      javaScriptEnabled: true,
                      mediaPlaybackRequiresUserGesture: false, // CRITICAL: Enable audio autoplay
                      useShouldOverrideUrlLoading: false,
                      useOnLoadResource: false,
                      useHybridComposition: true,
                      allowContentAccess: true,
                      allowFileAccess: true,
                      allowsInlineMediaPlayback: true,
                      allowsAirPlayForMediaPlayback: true,
                    ),
                    onConsoleMessage: (controller, consoleMessage) {
                      _consoleLogger.onConsoleMessage(consoleMessage);
                    },
                    onWebViewCreated: (InAppWebViewController controller) async {
                      _controller = controller;
                      webController = controller;
                      await DebugLogHelper.addDebugLog('VOICE: InAppWebView created, controller set');
                      // [LOCAL-698] Install the single-playback controller at
                      // document start on EVERY load, so no stop audio (native
                      // control, JS helper, autoplay) can start without first
                      // stopping the one already playing. Covers downloaded
                      // tours and translations (their HTML is already on-device,
                      // so only an injected guard can fix them).
                      try {
                        await controller.addUserScript(
                          userScript: UserScript(
                            source: kSinglePlaybackControllerJs,
                            injectionTime:
                                UserScriptInjectionTime.AT_DOCUMENT_START,
                          ),
                        );
                      } catch (e) {
                        await DebugLogHelper.addDebugLog(
                            'TOUR_PLAYER: single-playback user script registration failed: $e');
                      }
                      controller.addJavaScriptHandler(
                        handlerName: 'openMap',
                        callback: (args) async {
                          final stopArg = args.isNotEmpty && args[0] is Map ? args[0]['stop'] : null;
                          final stopIndex = stopArg is int ? stopArg : int.tryParse('$stopArg');
                          await DebugLogHelper.addDebugLog('MAP: openMap handler fired for stop $stopIndex');
                          if (!mounted) return;
                          Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (_) => TourMapScreen(
                                tourPath: widget.tourPath,
                                tourTitle: widget.tourTitle,
                                focusStopIndex: stopIndex,
                              ),
                            ),
                          );
                        },
                      );
                      // Track current stop index for swipe feedback
                      controller.addJavaScriptHandler(
                        handlerName: 'onStopChanged',
                        callback: (args) {
                          // args: [index, stopName?, totalStops?]
                          final idx = args.isNotEmpty ? (args[0] is int ? args[0] : int.tryParse('${args[0]}') ?? 0) : 0;
                          String? name;
                          if (args.length > 1 && args[1] != null && '${args[1]}'.trim().isNotEmpty) {
                            name = '${args[1]}'.trim();
                          }
                          int? total;
                          if (args.length > 2 && args[2] != null) {
                            total = args[2] is int
                                ? args[2]
                                : int.tryParse('${args[2]}');
                          }
                          if (mounted) {
                            setState(() {
                              _currentStopIndex = idx;
                              if (name != null) _currentStopName = name;
                              if (total != null && total > 0) _totalStops = total;
                            });
                          }
                        },
                      );
                      // [LOCAL-670] Fired by the WebView when the final stop's
                      // audio ends — offer the per-TOUR 1–10 rating once.
                      controller.addJavaScriptHandler(
                        handlerName: 'onTourEnded',
                        callback: (args) {
                          _maybePromptEndOfTourRating();
                        },
                      );
                      // [LOCAL-670C] Raw playback events from the WebView, fed
                      // into a per-stop PlaybackAccumulator so "listened" is
                      // verified from ACTUAL played time (a scrub to 85% does
                      // NOT count). args: [stopIndex, kind, currentTime,
                      // duration, rate]. kind ∈ play|pause|seek|rate|tick|ended.
                      controller.addJavaScriptHandler(
                        handlerName: 'onPlaybackEvent',
                        callback: (args) {
                          _onPlaybackEvent(args);
                        },
                      );
                    },
                    onLoadStop: (InAppWebViewController controller, WebUri? url) async {
                      await DebugLogHelper.addDebugLog('VOICE: WebView loaded: $url');
                      // [LOCAL-698] Safety net: ensure the single-playback
                      // controller is installed before anything can auto-start.
                      // Idempotent — a no-op if the document-start user script
                      // already installed it.
                      try {
                        await controller.evaluateJavascript(
                            source: kSinglePlaybackControllerJs);
                      } catch (e) {
                        await DebugLogHelper.addDebugLog(
                            'TOUR_PLAYER: single-playback re-inject failed: $e');
                      }
                      await DebugLogHelper.addDebugLog('VOICE: Getting tour info');
                      getTourInfo();

                      // Inject stop-change listener so we track which stop is playing
                      try {
                        await controller.evaluateJavascript(source: """
                          (function() {
                            // Hook into stop navigation to report current stop index
                            var origNextStop = window.nextStop;
                            var origPreviousStop = window.previousStop;
                            var origGoToStop = window.goToStop;
                            var currentIdx = 0;
                            var audios = document.querySelectorAll('audio');
                            var totalStops = audios.length;
                            // [LOCAL-670] Best-effort stop name for the index: prefer an
                            // element with id stopTitle<n>/stop-title-<n>, else the nth
                            // heading, else null. Never throws — a missing name just
                            // yields the generic "This stop:" label.
                            function stopNameFor(idx) {
                              try {
                                var byId = document.getElementById('stopTitle' + (idx + 1))
                                        || document.getElementById('stop-title-' + (idx + 1))
                                        || document.getElementById('stop' + (idx + 1) + 'Title');
                                if (byId && byId.textContent) return byId.textContent.trim();
                                var headings = document.querySelectorAll('h1,h2,h3,.stop-title,.stop-name');
                                if (headings && headings.length > idx && headings[idx].textContent) {
                                  return headings[idx].textContent.trim();
                                }
                              } catch (e) {}
                              return null;
                            }
                            function reportStop(idx) {
                              currentIdx = idx;
                              if (window.flutter_inappwebview) {
                                window.flutter_inappwebview.callHandler('onStopChanged', idx, stopNameFor(idx), totalStops);
                              }
                            }
                            if (typeof origNextStop === 'function') {
                              window.nextStop = function() {
                                origNextStop();
                                currentIdx++;
                                reportStop(currentIdx);
                              };
                            }
                            if (typeof origPreviousStop === 'function') {
                              window.previousStop = function() {
                                origPreviousStop();
                                if (currentIdx > 0) currentIdx--;
                                reportStop(currentIdx);
                              };
                            }
                            if (typeof origGoToStop === 'function') {
                              window.goToStop = function(n) {
                                origGoToStop(n);
                                currentIdx = n - 1;
                                reportStop(currentIdx);
                              };
                            }
                            // Also hook audio 'ended'/'play' events.
                            audios.forEach(function(audio, idx) {
                              audio.addEventListener('play', function() {
                                if (idx !== currentIdx) {
                                  currentIdx = idx;
                                  reportStop(currentIdx);
                                }
                              });
                              // [LOCAL-670B] Mark a stop LISTENED when its audio
                              // crosses 80% of its duration or ends. Fire the
                              // handler at most once per stop per load (guarded
                              // by a data flag) so we don't spam the bridge.
                              // [LOCAL-670C] Emit RAW playback events; the Dart
                              // PlaybackAccumulator decides "listened" from the
                              // real played time, so a scrub to 85% adds nothing.
                              function emit(kind) {
                                if (!window.flutter_inappwebview) return;
                                var d = audio.duration;
                                window.flutter_inappwebview.callHandler(
                                  'onPlaybackEvent', idx, kind,
                                  audio.currentTime || 0,
                                  (d && isFinite(d)) ? d : 0,
                                  audio.playbackRate || 1.0
                                );
                              }
                              audio.addEventListener('play', function() { emit('play'); });
                              audio.addEventListener('pause', function() { emit('pause'); });
                              audio.addEventListener('seeking', function() { emit('seek'); });
                              audio.addEventListener('seeked', function() { emit('seek'); });
                              audio.addEventListener('ratechange', function() { emit('rate'); });
                              audio.addEventListener('timeupdate', function() { emit('tick'); });
                              audio.addEventListener('ended', function() { emit('ended'); });
                              // [LOCAL-670] When the LAST stop's audio ends, the tour
                              // is over — tell Flutter to offer the rating prompt.
                              if (idx === totalStops - 1) {
                                audio.addEventListener('ended', function() {
                                  if (window.flutter_inappwebview) {
                                    window.flutter_inappwebview.callHandler('onTourEnded', idx);
                                  }
                                });
                              }
                            });
                            // Report initial state
                            reportStop(0);
                          })();
                        """);
                      } catch (e) {
                        await DebugLogHelper.addDebugLog('SWIPE: Failed to inject stop listener: $e');
                      }

                      // [LOCAL-677B] Install the paid-tour lock gate on the real
                      // audio elements now that the page has loaded. A locked tour
                      // plays Stop 1 as a preview and blocks the paid stops; the
                      // banner alone never stopped playback (the Bounce: all 5
                      // stops played). Re-applied after a purchase lifts the lock.
                      await _applyLockToWebView();

                      // Auto-start tour playback
                      await Future.delayed(Duration(milliseconds: 2000)); // Wait longer for page to fully load
                      try {
                        await controller.evaluateJavascript(source: """
                          console.log('Attempting auto-start...');
                          if (typeof startTour === 'function') {
                            console.log('Found startTour function, calling it');
                            startTour();
                          } else {
                            console.log('No startTour function, trying audio1');
                            var audio1 = document.getElementById('audio1');
                            if (audio1) {
                              console.log('Found audio1 element, playing');
                              audio1.play().then(() => {
                                console.log('Audio1 started successfully');
                              }).catch(e => {
                                console.log('Audio1 play failed:', e);
                              });
                            } else {
                              console.log('No audio1 element found');
                              var firstAudio = document.querySelector('audio');
                              if (firstAudio) {
                                console.log('Found first audio element, playing');
                                firstAudio.play();
                              }
                            }
                          }
                        """);
                        await DebugLogHelper.addDebugLog('TOUR_PLAYER: Auto-start command executed');
                      } catch (e) {
                        await DebugLogHelper.addDebugLog('TOUR_PLAYER: Auto-start failed: $e');
                      }
                    },
                    onReceivedError: (InAppWebViewController controller, WebResourceRequest request, WebResourceError error) {
                      unawaited(DebugLogHelper.addDebugLog('VOICE: WebView load error: ${error.description} for URL: ${request.url}')); // WebView callback
                    },
                  ),
                ),
                // Swipe feedback widget — always visible at bottom
                SwipeFeedbackWidget(
                  currentStopIndex: _currentStopIndex,
                  tourId: widget.tourId ?? _deriveTourId(),
                  jobId: widget.jobId,
                  tourPath: widget.tourPath,
                  stopName: _currentStopName,
                  onSwipe: (swipe) {
                    // Light haptic feedback on swipe
                    HapticFeedback.lightImpact();
                  },
                ),
              ],
            );
          } else {
            return Center(child: CircularProgressIndicator());
          }
        },
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () async {
          await DebugLogHelper.addDebugLog('VOICE: Mic button pressed - starting voice recognition');
          voiceService.startVoiceListening();
        },
        backgroundColor: const Color(0xFF3498db),
        child: const Icon(Icons.mic, color: Colors.white),
      ),
    );
  }
  /// Derive tour_id from the tour path (last segment of path).
  String _deriveTourId() {
    final segments = widget.tourPath.split('/');
    return segments.isNotEmpty ? segments.last : 'unknown';
  }

  /// [LOCAL-670C] Handle one raw playback event from the WebView and update the
  /// stop's [PlaybackAccumulator]. When the accumulator confirms the stop was
  /// genuinely listened (≥ 80% actually played, or the end reached after ≥ 80%),
  /// record it locally + enqueue it for sync — exactly once per stop.
  ///
  /// args: [stopIndex, kind, currentTime, duration, rate].
  void _onPlaybackEvent(List<dynamic> args) {
    if (args.length < 5) return;
    final idx = args[0] is int ? args[0] as int : int.tryParse('${args[0]}') ?? -1;
    if (idx < 0) return;
    final kind = '${args[1]}';
    final pos = (args[2] is num) ? (args[2] as num).toDouble() : double.tryParse('${args[2]}') ?? 0.0;
    final dur = (args[3] is num) ? (args[3] as num).toDouble() : double.tryParse('${args[3]}') ?? 0.0;
    final rate = (args[4] is num) ? (args[4] as num).toDouble() : double.tryParse('${args[4]}') ?? 1.0;

    if (dur <= 0) return; // duration not known yet; can't verify against it
    if (_listenedRecorded.contains(idx)) return; // already counted

    final acc = _accumulators.putIfAbsent(
      idx,
      () => PlaybackAccumulator(durationSeconds: dur),
    );
    final now = DateTime.now();
    switch (kind) {
      case 'play':
        acc.onPlay(pos, atWallClock: now);
        break;
      case 'pause':
        acc.onPause(pos, atWallClock: now);
        break;
      case 'seek':
        acc.onSeek(pos, atWallClock: now);
        break;
      case 'rate':
        acc.onRateChange(rate, positionSeconds: pos, atWallClock: now);
        break;
      case 'tick':
        acc.onTick(pos, atWallClock: now);
        break;
      case 'ended':
        acc.onEnded(pos, atWallClock: now);
        break;
    }

    if (acc.isListened && !_listenedRecorded.contains(idx)) {
      _listenedRecorded.add(idx);
      unawaited(_recordStopListened(idx));
    }
  }

  /// [LOCAL-670C] Persist that a stop was genuinely listened (local record with
  /// timestamp) and enqueue a `listened` item in the outbox for idempotent
  /// server sync when a connection returns. The listened key is the numeric
  /// tour id when we have one (what the server gate keys on), else the local
  /// path-derived id so the UI gate still works offline.
  Future<void> _recordStopListened(int stopIndex) async {
    final tourId = widget.tourId ?? _deriveTourId();
    try {
      await TourListenService.recordListened(
        tourId: tourId,
        stopIndex: stopIndex,
      );
      await DebugLogHelper.addDebugLog(
        'LISTEN: stop $stopIndex of tour $tourId verified listened (played-time)',
      );
    } catch (_) {
      // never surface a tracking failure to the listener
    }
  }

  /// [LOCAL-670] Offer the per-TOUR 1–10 rating after the last stop finishes.
  /// Fires at most once per player session. Only shown for a tour we can
  /// identify by numeric id (what the rating endpoint keys on); tours opened
  /// by local path only are skipped silently.
  Future<void> _maybePromptEndOfTourRating() async {
    if (_ratePrompted || !mounted) return;
    _ratePrompted = true;

    final tourId = widget.tourId;
    if (tourId == null || int.tryParse(tourId) == null) {
      await DebugLogHelper.addDebugLog(
        'RATING: end-of-tour reached but no numeric tourId — skipping prompt',
      );
      return;
    }

    // [LOCAL-670B] Only offer the rating once the listener has heard enough
    // stops (>= 2, or all stops on a short tour). On a normal multi-stop tour
    // reaching the END means they've heard several, so this virtually always
    // passes; it correctly suppresses the prompt for someone who skipped
    // straight to the final stop.
    final enough = await TourListenService.hasListenedEnough(
      tourId,
      totalStops: _totalStops,
    );
    if (!enough) {
      await DebugLogHelper.addDebugLog(
        'RATING: end-of-tour reached but not enough stops listened — skipping prompt',
      );
      return;
    }

    await DebugLogHelper.addDebugLog('RATING: end-of-tour — offering 1–10 rating');
    if (!mounted) return;
    await showRateTourDialog(
      context,
      tourId: tourId,
      tourTitle: widget.tourTitle,
      totalStops: _totalStops,
    );
  }

  /// [LOCAL-579] Share the tour currently open in the player. Uses the tour's
  /// numeric id (passed in as [widget.tourId]); the share service rejects a
  /// null/non-numeric id with a clear message and maps server/offline errors to
  /// a SnackBar, so this never crashes the player.
  void _shareTour() {
    // [LOCAL-710 / D672] Hand the sharing flow what the player already holds:
    // the downloaded tour's path (for the first stop's name + address), the
    // known stop count, and the paid snapshot (is_paid + price label).
    final meta = _localMeta;
    shareTour(
      context,
      audioTourId: widget.tourId,
      tourName: widget.tourTitle,
      tourPath: widget.tourPath,
      stopCount: _totalStops,
      isPaid: meta?.isPaid ?? false,
      price: (meta != null && meta.isPaid) ? meta.priceLabel : null,
    );
  }

  void _showTourHelpDialog() {
    showDialog(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          title: Text('🎤 Tour Voice Commands'),
          content: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'Audio Control:',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                ),
                SizedBox(height: 4),
                Text('• Say "Play" to start or resume audio'),
                Text('• Say "Pause" to stop audio'),
                Text('• Say "Repeat" to restart current stop'),
                SizedBox(height: 12),
                Text(
                  'Navigation:',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                ),
                SizedBox(height: 4),
                Text('• Say "Next stop" to move forward'),
                Text('• Say "Previous stop" to move back'),
                Text('• Say "Go to stop [number]" to jump to specific stop'),
                SizedBox(height: 12),
                Text(
                  'Seeking:',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                ),
                SizedBox(height: 4),
                Text('• Say "Forward 10 seconds" to skip ahead'),
                Text('• Say "Backward 5 seconds" to skip back'),
                SizedBox(height: 12),
                Text(
                  'Tour Switching:',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                ),
                SizedBox(height: 4),
                Text('• Say "Next tour" to switch tours'),
                Text('• Say "Previous tour" to go back'),
                SizedBox(height: 12),
                Text(
                  'Activation:',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14, color: Colors.blue),
                ),
                SizedBox(height: 4),
                Text('• Press microphone button or triple-press volume buttons'),
                Text('• Speak clearly after the beep'),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: Text('Cancel'),
            ),
          ],
        );
      },
    );
  }

}