import 'package:flutter/material.dart';
import 'dart:io';
import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:path_provider/path_provider.dart';
import '../screens/debug_log_viewer_screen.dart';
import '../services/tour_editing_service.dart';
import 'edit_stop_screen.dart';

part 'edit_tour_screen_part2.dart';
part 'edit_tour_screen_part3.dart';
part 'edit_tour_screen_part4.dart';

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

  const EditTourScreen({
    super.key,
    required this.tourData,
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
      DebugLogHelper.addDebugLog('HAS_CHANGES_CHECK: $context');
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
        builder: (context) => EditStopScreen(stop: stop),
      ),
    );
    
    if (result != null) {
      setState(() {
        final index = _stops.indexWhere((s) => s['stop_number'] == stop['stop_number']);
        if (index != -1) {
          _stops[index] = result;
        }
      });
    }
  }
}