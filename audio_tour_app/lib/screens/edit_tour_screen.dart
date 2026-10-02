import 'package:flutter/material.dart';
import 'dart:async';
import 'dart:io';
import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:path_provider/path_provider.dart';
import '../screens/debug_log_viewer_screen.dart';
import '../services/tour_editing_service.dart';
import 'edit_stop_screen.dart';

/// LOCAL-475 — the edit screen and its caller must agree on the return type.
///
/// [EditStopScreen] returns the updated stop as a `Map<String, dynamic>` on
/// every save/delete path (with `modified: true` and an `action`), and returns
/// `null` when the user cancels without changes.
///
/// This function is the single place that merges that navigator result back
/// into [stops]. It enforces the invariant that **[stops] only ever contains
/// maps**: a non-map result (the old, broken `pop(context, true)` behaviour)
/// is rejected instead of corrupting the list.
///
/// Returns `true` when [stops] was mutated (caller should rebuild).
///
/// Kept as a top-level pure function so the return contract is unit-testable
/// without standing up the full [EditStopScreen] widget (AC #6, #7).
bool applyEditStopResult(
  List<Map<String, dynamic>> stops,
  Map<String, dynamic> editedStop,
  Object? result,
) {
  // Cancel / no-change path: nothing to merge, Save All stays as it was.
  if (result == null) return false;

  // Contract guard: only a Map<String, dynamic> may enter `stops`. A bool or
  // anything else is a broken return contract — reject it so a later
  // `stop['modified']` read never operates on a non-map.
  if (result is! Map<String, dynamic>) {
    assert(
      false,
      'EditStopScreen must return a Map<String, dynamic> stop, got '
      '${result.runtimeType}. See LOCAL-475.',
    );
    return false;
  }

  final index =
      stops.indexWhere((s) => s['stop_number'] == editedStop['stop_number']);
  if (index == -1) return false;

  stops[index] = result;
  return true;
}

/// LOCAL-484 — the Listen page's stop count must follow the edit.
///
/// The `saved_tours` SharedPreferences list holds one JSON entry per tour.
/// `my_tours_screen` renders `'${tour['stops']} stops • …'` straight from that
/// entry. Before this change, `'stops'` was written once at download time and
/// never updated, so adding or deleting a stop left the Listen count stale.
///
/// This is the single walk that rewrites a tour's entry after a Save All that
/// produced a new tour id. It matches on [tourPath] (the entry keeps its
/// original path even after the in-memory `widget.tourData['path']` is
/// repointed) and writes:
///   * `new_tour_id` — the id returned by the save (unchanged behaviour), and
///   * `stops`       — the fresh stop count, when [stopCount] is known.
///
/// Keeping both writes in one walk avoids a second, divergent copy of the
/// list-rewriting logic (the task's explicit constraint).
///
/// [stopCount] is nullable on purpose: if the true count could not be
/// determined we leave `'stops'` untouched rather than writing a guess — an
/// absent/old number is corrected only when we actually know the new one.
///
/// Returns a NEW list with the matched entry rewritten. Entries that don't
/// match [tourPath], and malformed JSON entries, are copied through untouched.
/// Kept as a top-level pure function so it is unit-testable without standing
/// up the widget (AC #1–#6).
List<String> applyTourEditToSavedTours(
  List<String> savedTours,
  String tourPath, {
  String? newTourId,
  int? stopCount,
}) {
  final result = List<String>.from(savedTours);

  for (int i = 0; i < result.length; i++) {
    final entryJson = result[i];
    if (entryJson.isEmpty) continue;

    Map<String, dynamic> entry;
    try {
      final decoded = jsonDecode(entryJson);
      if (decoded is! Map<String, dynamic>) continue;
      entry = decoded;
    } catch (_) {
      // Malformed entry — pass it through untouched rather than dropping it.
      continue;
    }

    if (entry['path'] == tourPath) {
      if (newTourId != null) {
        entry['new_tour_id'] = newTourId;
      }
      if (stopCount != null) {
        // Stored as a String to match the value written at download time
        // (tour_generator_screen.dart: `'stops': stops.toString()`), so the
        // Listen page reads a single consistent type.
        entry['stops'] = stopCount.toString();
      }
      result[i] = jsonEncode(entry);
      break;
    }
  }

  return result;
}

/// LOCAL-484 — count the stops actually written to disk for a tour.
///
/// WHY DISK AND NOT THE SERVER RESPONSE: the orchestrator persists
/// `stops_count` server-side, but the Save All response the app receives
/// (`/tour/<id>/update-multiple-stops`) does NOT carry it — it returns only
/// `status`, `message`, `stops` (the processed subset, not the merged total),
/// `new_tour_id` and `download_url`. So there is no authoritative count in the
/// response to prefer. The download, however, writes the complete edited tour
/// to [tourDirPath], one `audio_<n>.mp3` per stop. Counting those files is the
/// authoritative local number and is what the Listen page should show.
///
/// Returns the number of `audio_*.mp3` files directly in [tourDirPath], or
/// `null` if the directory is missing or contains none (unknown — caller must
/// not invent a count).
int? countStopsOnDisk(String tourDirPath) {
  final dir = Directory(tourDirPath);
  if (!dir.existsSync()) return null;

  final mp3Pattern = RegExp(r'audio_\d+\.mp3$');
  int count = 0;
  for (final entity in dir.listSync()) {
    if (entity is File && mp3Pattern.hasMatch(entity.uri.pathSegments.last)) {
      count++;
    }
  }
  return count > 0 ? count : null;
}

class EditScreenLogger {
  static Future<void> logFromService(String message) async {
    await DebugLogHelper.addDebugLog('SERVICE_LOG: $message');
  }
}

class SaveContextLogger {
  static List<String> messages = [];

  static void addMessage(String message) {
    messages.add(message);
  }

  static void clearMessages() {
    messages.clear();
  }
}

class EditTourScreen extends StatefulWidget {
  final Map<String, dynamic> tourData;

  /// Test-only seam (LOCAL-477). When provided, the screen renders these stops
  /// synchronously and skips the async `_loadTourStops` disk/plugin path,
  /// which cannot be driven deterministically under `flutter test`
  /// (initState-time awaits are bound to the fake-async test zone). Production
  /// call sites never pass this, so behaviour on device is unchanged.
  final List<Map<String, dynamic>>? debugInitialStops;

  const EditTourScreen({
    super.key,
    required this.tourData,
    this.debugInitialStops,
  });

  @override
  State<EditTourScreen> createState() => _EditTourScreenState();
}

class _EditTourScreenState extends State<EditTourScreen> {
  List<Map<String, dynamic>> _stops = [];
  bool _isLoading = true;
  List<Map<String, dynamic>> _originalStops = [];
  String _newStopContent = '';

  @override
  void initState() {
    super.initState();
    if (widget.debugInitialStops != null) {
      // Test seam: seed stops synchronously so the loaded list renders
      // without the async disk/plugin load. See [EditTourScreen.debugInitialStops].
      _stops = widget.debugInitialStops!
          .map((s) => Map<String, dynamic>.from(s))
          .toList();
      _originalStops = widget.debugInitialStops!
          .map((s) => Map<String, dynamic>.from(s))
          .toList();
      _isLoading = false;
      return;
    }
    _loadTourStops();
  }

  Future<void> _loadTourStops() async {
    try {
      await DebugLogHelper.addDebugLog('USER_ACTION: Loading tour for editing');

      final tourPath = widget.tourData['path'];
      final indexFile = File('$tourPath/index.html');

      if (!await indexFile.exists()) {
        throw Exception('Tour index.html not found');
      }

      final htmlContent = await indexFile.readAsString();
      final stops = await _parseStopsFromHtml(htmlContent);

      setState(() {
        _stops = stops;
        _originalStops = stops.map((stop) => Map<String, dynamic>.from(stop)).toList();
        _isLoading = false;
      });

      await DebugLogHelper.addDebugLog('STATUS: Loaded ${stops.length} stops for editing');
    } catch (e) {
      await DebugLogHelper.addDebugLog('ERROR: Failed to load tour stops: $e');
      setState(() {
        _isLoading = false;
      });

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error loading tour: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  Future<List<Map<String, dynamic>>> _parseStopsFromHtml(String htmlContent) async {
    final stops = <Map<String, dynamic>>[];
    final foundStops = <int>{};

    final newStylePattern = RegExp(r'audio_(\d+)\.mp3');
    final newStyleMatches = newStylePattern.allMatches(htmlContent);

    if (newStyleMatches.isNotEmpty) {
      for (final match in newStyleMatches) {
        try {
          final stopNumber = int.parse(match.group(1)!);
          foundStops.add(stopNumber);
        } catch (e) {
          await DebugLogHelper.addDebugLog('ERROR: Failed to parse stop number: $e');
        }
      }
    } else {
      final oldStylePattern = RegExp(r'audio-(\d+)');
      final oldStyleMatches = oldStylePattern.allMatches(htmlContent);

      if (oldStyleMatches.isNotEmpty) {
        for (final match in oldStyleMatches) {
          try {
            final stopNumber = int.parse(match.group(1)!);
            foundStops.add(stopNumber + 1);
          } catch (e) {
            await DebugLogHelper.addDebugLog('ERROR: Failed to parse old style stop: $e');
          }
        }
      }
    }

    if (foundStops.isEmpty) {
      const errorMsg = 'Tour editing not supported: No audio elements found in tour HTML.';
      await DebugLogHelper.addDebugLog('ERROR: $errorMsg');

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(errorMsg),
            backgroundColor: Colors.red,
            duration: Duration(seconds: 5),
          ),
        );
        Navigator.pop(context);
      }
      return [];
    }

    for (final stopNumber in foundStops) {
      String stopText = 'Stop $stopNumber - Edit this content to customize your tour experience.';

      try {
        final tourPath = widget.tourData['path'];
        final textFile = File('$tourPath/audio_$stopNumber.txt');
        if (await textFile.exists()) {
          final content = await textFile.readAsString();
          if (content.trim().isNotEmpty) {
            stopText = content.trim();
          }
        }
      } catch (e) {
        // Silent fallback to default text
      }

      stops.add({
        'stop_number': stopNumber,
        'title': 'Stop $stopNumber',
        'text': stopText,
        'original_text': stopText,
        'audio_file': 'audio_$stopNumber.mp3',
        'editable': true,
        'modified': false,
      });
    }

    stops.sort((a, b) => a['stop_number'].compareTo(b['stop_number']));
    return stops;
  }

  bool _hasAnyChanges([String? context]) {
    if (context != null) {
      unawaited(DebugLogHelper.addDebugLog('HAS_CHANGES_CHECK: $context')); // sync callback
    }
    for (int i = 0; i < _stops.length; i++) {
      final stop = _stops[i];
      final hasChange = stop['modified'] == true ||
          stop['action'] == 'add' ||
          stop['action'] == 'delete' ||
          stop['action'] == 'modify' ||
          stop['action'] == 'unchanged' ||
          stop['moved'] == true;
      if (hasChange) return true;
    }
    return false;
  }

  Future<void> _editStop(Map<String, dynamic> stop) async {
    final result = await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => EditStopScreen(tourData: widget.tourData, stopData: stop),
      ),
    );

    // LOCAL-475: EditStopScreen must hand back the updated stop as a
    // Map<String, dynamic>. Older code popped `true`/`false`, which put a
    // bool into _stops and silently broke _hasAnyChanges(). The merge + guard
    // is delegated to applyEditStopResult so the contract is unit-testable.
    if (result != null && result is! Map<String, dynamic>) {
      await DebugLogHelper.addDebugLog(
        'EDIT_CONTRACT_VIOLATION: EditStopScreen returned ${result.runtimeType}, expected Map<String, dynamic>. See LOCAL-475.',
      );
    }
    final merged = applyEditStopResult(_stops, stop, result);
    if (merged) {
      setState(() {});
    }
  }

  // ── part2 methods ──────────────────────────────────────────────────────────

  Future<void> _saveAllChanges() async {
    SaveContextLogger.addMessage('_saveAllChanges method started');
    SaveContextLogger.addMessage('Processing ${_stops.length} stops');

    setState(() {
      _isLoading = true;
    });

    try {
      for (int i = 0; i < _stops.length; i++) {
        final stop = _stops[i];
        await DebugLogHelper.addDebugLog('_saveAllChanges BEFORE save: Stop $i - number=${stop['stop_number']}, modified=${stop['modified']}, action=${stop['action']}, moved=${stop['moved']}');
      }

      final remainingStops = _stops.where((stop) => stop['action'] != 'delete').length;
      await DebugLogHelper.addDebugLog('CRITICAL_SAVE: Remaining stops after delete filter: $remainingStops');
      if (remainingStops == 0) {
        await DebugLogHelper.addDebugLog('CRITICAL_SAVE: All stops deleted - returning early');
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('A tour must have at least one stop. Cannot delete all stops.'),
            backgroundColor: Colors.red,
            duration: const Duration(seconds: 4),
          ),
        );
        return;
      }

      final hasChanges = _hasAnyChanges('Called from _saveAllChanges - testing message passing');

      await DebugLogHelper.addDebugLog('_saveAllChanges: _hasAnyChanges() returned: $hasChanges');
      if (!hasChanges) {
        await DebugLogHelper.addDebugLog('CRITICAL_SAVE: No changes detected - returning early');
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('No changes to save'),
            backgroundColor: Colors.blue,
          ),
        );
        return;
      }

      final tourPath = widget.tourData['path'] as String;
      final tourId = tourPath.split('/').last;
      String backendTourId = tourId;

      final uuidPattern = RegExp(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}');
      final uuidMatch = uuidPattern.firstMatch(tourId);

      if (uuidMatch != null) {
        backendTourId = uuidMatch.group(0)!;
      } else {
        final numericId = _extractTourId(tourPath);
        if (numericId != null) {
          backendTourId = numericId.toString();
        }
      }

      await DebugLogHelper.addDebugLog('EDIT: Using backend tour ID: $backendTourId');

      unawaited(DebugLogHelper.addDebugLog('CRITICAL_TOUR_ID: tourPath=$tourPath')); // sync context
      unawaited(DebugLogHelper.addDebugLog('CRITICAL_TOUR_ID: extracted tourId=$tourId')); // sync context
      unawaited(DebugLogHelper.addDebugLog('CRITICAL_TOUR_ID: sending to backend=$backendTourId')); // sync context

      final modifiedStops = _stops.where((stop) =>
          stop['modified'] == true ||
          stop['action'] != null
      ).toList();

      await DebugLogHelper.addDebugLog('CRITICAL_SAVE: Modified stops filter found: ${modifiedStops.length} stops');
      for (int i = 0; i < modifiedStops.length; i++) {
        final stop = modifiedStops[i];
        await DebugLogHelper.addDebugLog('CRITICAL_SAVE: Modified stop $i - number=${stop['stop_number']}, modified=${stop['modified']}, action=${stop['action']}');
      }

      if (modifiedStops.isEmpty) {
        await DebugLogHelper.addDebugLog('CRITICAL_SAVE: No modified stops found - returning early');
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('No changes to save'),
            backgroundColor: Colors.blue,
          ),
        );
        return;
      }

      await DebugLogHelper.addDebugLog('EDIT: Sending only ${modifiedStops.length} modified stops - backend preserves others');

      final payload = _prepareStopsForBackend(modifiedStops);
      final payloadJson = jsonEncode({'stops': payload});

      await DebugLogHelper.addDebugLog('CRITICAL_JSON: $payloadJson');

      Map<String, dynamic> result = await TourEditingService.updateMultipleStops(
        tourId: backendTourId,
        allStops: payload,
      );

      await DebugLogHelper.addDebugLog('API_CALL: TourEditingService.updateMultipleStops returned successfully');
      await DebugLogHelper.addDebugLog('API_CALL: Response keys: ${result.keys.toList()}');
      await DebugLogHelper.addDebugLog('EDIT: Save response: ${result.toString()}');

      final newTourId = result['new_tour_id'];
      if (newTourId != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('API SUCCESS: ${result['message'] ?? 'Tour saved'}'),
            duration: const Duration(seconds: 2),
            backgroundColor: Colors.green,
          ),
        );
        await DebugLogHelper.addDebugLog('CRITICAL_TOUR_ID: Backend returned new_tour_id=$newTourId');
      }

      if (result['new_tour_id'] != null) {
        await _handleNewTourDownload(result);
      } else {
        await _handleTraditionalSave(result, backendTourId);
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('EDIT: Error in save: $e');

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Save failed: $e'),
          backgroundColor: Colors.red,
          duration: const Duration(seconds: 6),
        ),
      );
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  Future<void> _handleNewTourDownload(Map<String, dynamic> result) async {
    try {
      await DebugLogHelper.addDebugLog('EDIT: Starting new tour download process');

      final newTourId = result['new_tour_id'] as String?;
      final downloadUrl = result['download_url'] as String?;

      if (newTourId == null || downloadUrl == null) {
        throw Exception('Invalid response: missing new_tour_id or download_url');
      }

      await DebugLogHelper.addDebugLog('EDIT: REQ-016 new tour created: $newTourId');

      final tourPath = widget.tourData['path'] as String;

      final downloadSuccess = await TourEditingService.downloadUpdatedTour(
        newTourId: newTourId,
        downloadUrl: downloadUrl,
        localTourPath: tourPath,
      );

      if (downloadSuccess) {
        // The download extracted the complete edited tour into `tourPath`
        // (the old path — the saved_tours entry still keys on it). Count the
        // audio_*.mp3 files there: that is the authoritative new stop count,
        // because the Save All response carries no stops_count (LOCAL-484).
        final diskStopCount = countStopsOnDisk(tourPath);
        await _updateLocalTourId(newTourId, stopCount: diskStopCount);

        final oldTourPath = widget.tourData['path'] as String;
        final newTourPath = oldTourPath.replaceAll(RegExp(r'[0-9a-f-]{36}'), newTourId);

        widget.tourData['path'] = newTourPath;

        try {
          await _loadTourStops();

          _showSuccessMessage('Tour updated successfully!');
          _resetAllModifiedFlags();
          _navigateToListenPage();
        } catch (reloadError) {
          throw Exception('Failed to reload tour data after download: $reloadError');
        }
      } else {
        throw Exception('Failed to download updated tour.');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('EDIT: Error in new tour download: $e');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Download failed: $e'),
          backgroundColor: Colors.red,
          duration: const Duration(seconds: 5),
        ),
      );
    }
  }

  Future<void> _handleTraditionalSave(Map<String, dynamic> result, String tourId) async {
    _showSuccessMessage('Changes saved successfully!');
    _resetAllModifiedFlags();
    _navigateToListenPage();
  }

  int? _extractTourId(String tourPath) {
    try {
      final parts = tourPath.split('_');
      return int.parse(parts.last);
    } catch (e) {
      return null;
    }
  }

  void _resetAllModifiedFlags() {
    try {
      unawaited(DebugLogHelper.addDebugLog('DEBUG_RESET: Processing ${_stops.length} stops')); // sync callback

      for (int i = 0; i < _stops.length; i++) {
        final stop = _stops[i];
        stop['modified'] = false;

        final textContent = stop['text'];
        String safeText = '';
        if (textContent != null && textContent.toString().isNotEmpty) {
          safeText = textContent.toString();
        }
        stop['original_text'] = safeText;
      }

      if (mounted) {
        setState(() {});
      }
    } catch (e) {
      unawaited(DebugLogHelper.addDebugLog('DEBUG_RESET: Error in _resetAllModifiedFlags: $e')); // sync callback
    }
  }

  // ── part3 methods ──────────────────────────────────────────────────────────

  Future<void> _updateLocalTourId(String newTourId, {int? stopCount}) async {
    try {
      await DebugLogHelper.addDebugLog('DEBUG_UPDATE_ID: Starting _updateLocalTourId with newTourId: $newTourId, stopCount: $stopCount');

      final tourPath = widget.tourData['path'] as String;
      final prefs = await SharedPreferences.getInstance();
      final savedTours = prefs.getStringList('saved_tours') ?? [];

      // Single walk that rewrites both new_tour_id and the stop count. See
      // applyTourEditToSavedTours — no divergent copy of this logic (LOCAL-484).
      final updated = applyTourEditToSavedTours(
        savedTours,
        tourPath,
        newTourId: newTourId,
        stopCount: stopCount,
      );

      await prefs.setStringList('saved_tours', updated);
      await DebugLogHelper.addDebugLog('DEBUG_UPDATE_ID: Local tour updated with new ID reference and stop count $stopCount');
    } catch (e) {
      await DebugLogHelper.addDebugLog('DEBUG_UPDATE_ID: ERROR in _updateLocalTourId: $e');
    }
  }

  void _showSuccessMessage(String message) {
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(message),
          backgroundColor: Colors.green,
          duration: const Duration(seconds: 3),
        ),
      );
    }
  }

  void _navigateToListenPage() {
    if (mounted) {
      Navigator.pop(context, widget.tourData);
    }
  }

  void _updateUIIndicators() {
    setState(() {});
  }

  List<Map<String, dynamic>> _prepareStopsForBackend(List<Map<String, dynamic>> stops) {
    final cleanedStops = <Map<String, dynamic>>[];

    unawaited(DebugLogHelper.addDebugLog('EDIT: Preparing ${stops.length} stops for backend')); // sync callback

    for (final stop in stops) {
      final cleanedStop = Map<String, dynamic>.from(stop);
      cleanedStops.add(cleanedStop);
    }
    return cleanedStops;
  }

  void _addNewStop() {
    final existingNumbers = _stops.map((s) => s['stop_number'] as int).toList();
    final maxNumber = existingNumbers.isEmpty ? 0 : existingNumbers.reduce((a, b) => a > b ? a : b);
    final newStopNumber = maxNumber + 1;

    final newStop = {
      'stop_number': newStopNumber,
      'title': 'Stop $newStopNumber',
      'text': _newStopContent,
      'original_text': '',
      'audio_file': 'audio_$newStopNumber.mp3',
      'editable': true,
      'modified': true,
      'action': 'add',
    };

    // Mutate _stops and refresh the list. Do NOT pop the screen — the user
    // stays on the edit screen so the new row appears and Save All enables,
    // exactly as after editing a stop's text. (LOCAL-477)
    setState(() {
      _stops.add(newStop);
      _stops.sort((a, b) => a['stop_number'].compareTo(b['stop_number']));
      _newStopContent = '';
    });

    unawaited(DebugLogHelper.addDebugLog('CRITICAL_ADD: Added new stop $newStopNumber with action=add, modified=true')); // sync callback
  }

  void _reorderStops(int oldIndex, int newIndex) {
    if (oldIndex < newIndex) {
      newIndex -= 1;
    }

    final stop = _stops.removeAt(oldIndex);
    _stops.insert(newIndex, stop);

    for (int i = 0; i < _stops.length; i++) {
      final oldStopNumber = _stops[i]['stop_number'];
      final newStopNumber = i + 1;

      _stops[i]['stop_number'] = newStopNumber;
      _stops[i]['title'] = 'Stop $newStopNumber';
      _stops[i]['audio_file'] = 'audio_$newStopNumber.mp3';

      if (oldStopNumber != newStopNumber) {
        if (_stops[i]['action'] != 'add') {
          _stops[i]['action'] = 'unchanged';
        }
        _stops[i]['moved'] = true;
      }
    }

    unawaited(DebugLogHelper.addDebugLog('EDIT: Reordered stops: moved $oldIndex to $newIndex')); // sync callback
    _updateUIIndicators();
  }

  // ── part4: build ───────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Edit: ${widget.tourData['title']}'),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _stops.isEmpty
              ? const Center(
                  child: Text(
                    'No stops found in this tour',
                    style: TextStyle(fontSize: 18, color: Colors.grey),
                  ),
                )
              : Column(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(16),
                      color: Colors.blue.shade50,
                      child: Column(
                        children: [
                          Row(
                            children: [
                              Icon(Icons.info, color: Colors.blue.shade700),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(
                                  'Individual stops save automatically. Orange stops are modified.',
                                  style: TextStyle(
                                    color: Colors.blue.shade800,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                              ),
                            ],
                          ),
                          if (_hasAnyChanges()) ...[
                            const SizedBox(height: 8),
                            Row(
                              children: [
                                Icon(Icons.warning, color: Colors.orange.shade700, size: 16),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    'You have unsaved changes. Tap Save All to push to backend.',
                                    style: TextStyle(
                                      color: Colors.orange.shade800,
                                      fontSize: 12,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ],
                      ),
                    ),
                    Expanded(
                      child: ReorderableListView.builder(
                        itemCount: _stops.length,
                        onReorder: _reorderStops,
                        itemBuilder: (context, index) {
                          final stop = _stops[index];
                          return Card(
                            key: ValueKey(stop['stop_number']),
                            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                            child: ListTile(
                              leading: CircleAvatar(
                                backgroundColor: stop['action'] == 'delete'
                                    ? Colors.red
                                    : stop['modified'] == true
                                        ? Colors.orange
                                        : Colors.blue,
                                child: Text('${stop['stop_number']}'),
                              ),
                              title: Text(
                                stop['title'],
                                style: TextStyle(
                                  decoration: stop['action'] == 'delete'
                                      ? TextDecoration.lineThrough
                                      : null,
                                ),
                              ),
                              subtitle: Text(
                                stop['text'],
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                              ),
                              trailing: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  if (stop['action'] == 'add') ...[
                                    const Icon(Icons.add_circle, color: Colors.green, size: 16),
                                    const SizedBox(width: 4),
                                    const Text('New', style: TextStyle(color: Colors.green, fontSize: 12)),
                                    const SizedBox(width: 8),
                                  ],
                                  if (stop['action'] == 'delete') ...[
                                    const Icon(Icons.delete, color: Colors.red, size: 16),
                                    const SizedBox(width: 4),
                                    const Text('Delete', style: TextStyle(color: Colors.red, fontSize: 12)),
                                    const SizedBox(width: 8),
                                  ],
                                  if (stop['moved'] == true) ...[
                                    const Icon(Icons.swap_vert, color: Colors.purple, size: 16),
                                    const SizedBox(width: 4),
                                    const Text('Moved', style: TextStyle(color: Colors.purple, fontSize: 12)),
                                    const SizedBox(width: 8),
                                  ],
                                  if (stop['modified'] == true &&
                                      stop['action'] != 'add' &&
                                      stop['action'] != 'delete') ...[
                                    const Icon(Icons.circle, color: Colors.orange, size: 12),
                                    const SizedBox(width: 4),
                                    const Text('Modified', style: TextStyle(color: Colors.orange, fontSize: 12)),
                                    const SizedBox(width: 8),
                                  ],
                                  if (stop['action'] != 'delete')
                                    Icon(Icons.edit, color: Colors.grey[600]),
                                  const SizedBox(width: 8),
                                  Icon(Icons.drag_handle, color: Colors.grey[400]),
                                ],
                              ),
                              onTap: stop['action'] == 'delete' ? null : () => _editStop(stop),
                            ),
                          );
                        },
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                      child: OutlinedButton.icon(
                        onPressed: _addNewStop,
                        icon: const Icon(Icons.add, color: Colors.green),
                        label: const Text('Add Stop', style: TextStyle(color: Colors.green)),
                        style: OutlinedButton.styleFrom(
                          side: const BorderSide(color: Colors.green),
                        ),
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.all(16),
                      child: Row(
                        children: [
                          Expanded(
                            child: OutlinedButton(
                              onPressed: () => Navigator.pop(context),
                              child: const Text('Cancel'),
                            ),
                          ),
                          const SizedBox(width: 16),
                          Expanded(
                            child: ElevatedButton(
                              onPressed: _hasAnyChanges() ? _saveAllChanges : null,
                              style: ElevatedButton.styleFrom(
                                backgroundColor: const Color(0xFF2c3e50),
                                foregroundColor: Colors.white,
                              ),
                              child: const Text('Save All'),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
    );
  }
}
