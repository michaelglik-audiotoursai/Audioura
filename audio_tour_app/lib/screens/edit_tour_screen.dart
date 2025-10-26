import 'package:flutter/material.dart';
import 'dart:io';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:archive/archive.dart';
import 'package:path_provider/path_provider.dart';
import '../screens/debug_log_viewer_screen.dart';
import '../services/tour_editing_service.dart';
import 'edit_stop_screen.dart';

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
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error loading tour: $e'),
          backgroundColor: Colors.red,
        ),
      );
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
      final errorMsg = 'Tour editing not supported: No audio elements found in tour HTML.';
      await DebugLogHelper.addDebugLog('ERROR: $errorMsg');
      
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
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
        final textFile = File('$tourPath/audio_${stopNumber}.txt');
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

  void _editStop(Map<String, dynamic> stop) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => EditStopScreen(
          tourData: widget.tourData,
          stopData: stop,
        ),
      ),
    ).then((changesMade) {
      if (changesMade == true) {
        _updateUIIndicators();
      }
    });
  }
  
  bool _hasAnyChanges([String? callerMessage]) {
    for (int i = 0; i < _stops.length; i++) {
      final stop = _stops[i];
      final hasChange = stop['modified'] == true || 
          stop['action'] == 'add' || 
          stop['action'] == 'delete' || 
          stop['action'] == 'modify' ||
          stop['action'] == 'unchanged' ||
          stop['moved'] == true;
      
      if (hasChange) {
        return true;
      }
    }
    
    return false;
  }
  
  int _getModifiedCount() {
    return _stops.where((stop) => 
        stop['modified'] == true || 
        stop['action'] == 'add' || 
        stop['action'] == 'delete' || 
        stop['action'] == 'modify' ||
        stop['action'] == 'unchanged' ||
        stop['moved'] == true
    ).length;
  }
  
  Future<void> _saveAllChanges() async {
    await DebugLogHelper.addDebugLog('USER_ACTION: Save all changes initiated');
    
    setState(() {
      _isLoading = true;
    });
    
    try {
      final remainingStops = _stops.where((stop) => stop['action'] != 'delete').length;
      if (remainingStops == 0) {
        await DebugLogHelper.addDebugLog('ERROR: Cannot delete all stops - tour must have at least one stop');
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('A tour must have at least one stop. Cannot delete all stops.'),
            backgroundColor: Colors.red,
            duration: Duration(seconds: 4),
          ),
        );
        return;
      }
      
      final hasChanges = _hasAnyChanges();
      if (!hasChanges) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('No changes to save'),
            backgroundColor: Colors.blue,
          ),
        );
        return;
      }
      
      String? backendTourId = widget.tourData['tour_id'] as String?;
      
      // Fallback: Extract tour ID from path if not stored (for newly generated tours)
      if (backendTourId == null || backendTourId.isEmpty) {
        final tourPath = widget.tourData['path'] as String? ?? '';
        final pathSegments = tourPath.split('/');
        if (pathSegments.isNotEmpty) {
          final dirName = pathSegments.last;
          final uuidMatch = RegExp(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})').firstMatch(dirName);
          if (uuidMatch != null) {
            backendTourId = uuidMatch.group(1);
            widget.tourData['tour_id'] = backendTourId;
          }
        }
      }
      
      if (backendTourId == null || backendTourId.isEmpty) {
        throw Exception('Tour ID not found in tour data. This tour may need to be re-downloaded.');
      }
      
      final modifiedStops = _stops.where((stop) => 
          stop['modified'] == true || 
          stop['action'] != null
      ).toList();
      
      if (modifiedStops.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('No changes to save'),
            backgroundColor: Colors.blue,
          ),
        );
        return;
      }
      
      await DebugLogHelper.addDebugLog('STATUS: Saving ${modifiedStops.length} modified stops');

      final payload = _prepareStopsForBackend(modifiedStops);
      final originalTourPath = widget.tourData['path'] as String;
      widget.tourData['original_path'] = originalTourPath;
      
      Map<String, dynamic> result = await TourEditingService.updateMultipleStops(
        tourId: backendTourId,
        allStops: payload,
      );
      
      await DebugLogHelper.addDebugLog('STATUS: Tour save completed successfully');
      
      final newTourId = result['new_tour_id'];
      if (newTourId != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('${result['message'] ?? 'Tour saved'}'),
            duration: Duration(seconds: 2),
            backgroundColor: Colors.green,
          ),
        );
        
        widget.tourData['tour_id'] = newTourId;
        final oldTourId = backendTourId;
        final newTourPath = originalTourPath.replaceAll(oldTourId, newTourId);
        widget.tourData['path'] = newTourPath;
      }
      
      if (result['new_tour_id'] != null) {
        await _handleNewTourDownload(result, originalTourPath);
      } else {
        await _handleTraditionalSave(result, backendTourId);
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('ERROR: Save failed: $e');
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Save failed: $e'),
          backgroundColor: Colors.red,
          duration: Duration(seconds: 6),
        ),
      );
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  Future<void> _handleNewTourDownload(Map<String, dynamic> result, String originalTourPath) async {
    try {
      await DebugLogHelper.addDebugLog('USER_ACTION: Downloading updated tour');
      
      final newTourId = result['new_tour_id'] as String?;
      final downloadUrl = result['download_url'] as String?;
      
      if (newTourId == null || downloadUrl == null) {
        throw Exception('Invalid response: missing new_tour_id or download_url');
      }
      
      final newTourPath = widget.tourData['path'] as String;
      
      final newTourDir = Directory(newTourPath);
      if (!await newTourDir.exists()) {
        await newTourDir.create(recursive: true);
      }
      
      final downloadSuccess = await TourEditingService.downloadUpdatedTour(
        newTourId: newTourId,
        downloadUrl: downloadUrl,
        localTourPath: newTourPath,
      );
      
      if (downloadSuccess) {
        await DebugLogHelper.addDebugLog('STATUS: Tour download completed successfully');
        await _updateLocalTourId(newTourId);
        await _cleanupSpecificOldTour(originalTourPath, newTourPath);
        
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
      await DebugLogHelper.addDebugLog('ERROR: Tour download failed: $e');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Download failed: $e'),
          backgroundColor: Colors.red,
          duration: Duration(seconds: 5),
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
      DebugLogHelper.addDebugLog('ERROR: Failed to reset modified flags: $e');
    }
  }
  
  Future<void> _cleanupSpecificOldTour(String originalTourPath, String newTourPath) async {
    try {
      if (originalTourPath != newTourPath) {
        final oldTourDir = Directory(originalTourPath);
        if (await oldTourDir.exists()) {
          await oldTourDir.delete(recursive: true);
        }
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('ERROR: Cleanup failed: $e');
    }
  }
  
  String? _extractTourNameFromPath(String tourPath) {
    try {
      final dirName = tourPath.split('/').last;
      final match = RegExp(r'^(.+?)_[0-9a-f-]{36}$').firstMatch(dirName);
      return match?.group(1);
    } catch (e) {
      return null;
    }
  }
  
  Future<void> _updateLocalTourId(String newTourId) async {
    try {
      final currentTourPath = widget.tourData['path'] as String;
      final originalTourPath = widget.tourData['original_path'] as String? ?? currentTourPath;
      
      final prefs = await SharedPreferences.getInstance();
      final savedTours = prefs.getStringList('saved_tours') ?? [];
      
      bool found = false;
      for (int i = 0; i < savedTours.length; i++) {
        final tourDataJson = savedTours[i];
        if (tourDataJson.isNotEmpty) {
          try {
            final tourData = jsonDecode(tourDataJson) as Map<String, dynamic>;
            final savedPath = tourData['path'] as String?;
            final savedTitle = tourData['title'] as String?;
            final currentTitle = widget.tourData['title'] as String?;
            
            if ((savedPath != null && savedPath == originalTourPath) ||
                (savedTitle != null && currentTitle != null && savedTitle == currentTitle)) {
              
              tourData['path'] = currentTourPath;
              tourData['tour_id'] = newTourId;
              savedTours[i] = jsonEncode(tourData);
              found = true;
              break;
            }
          } catch (jsonError) {
            continue;
          }
        }
      }
      
      if (!found) {
        await DebugLogHelper.addDebugLog('WARNING: No matching tour found to update in SharedPreferences');
      }
      
      await prefs.setStringList('saved_tours', savedTours);
    } catch (e) {
      await DebugLogHelper.addDebugLog('ERROR: Failed to update local tour ID: $e');
    }
  }
  
  void _showSuccessMessage(String message) {
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(message),
          backgroundColor: Colors.green,
          duration: Duration(seconds: 3),
        ),
      );
    }
  }
  
  void _navigateToListenPage() {
    if (mounted) {
      // Return updated tour data to parent screen
      Navigator.pop(context, widget.tourData);
    }
  }
  
  static Future<List<Map<String, dynamic>>> discoverAvailableTours() async {
    final discoveredTours = <Map<String, dynamic>>[];
    
    try {
      final appDir = await getApplicationDocumentsDirectory();
      final toursDir = Directory('${appDir.path}/tours');
      
      if (!await toursDir.exists()) {
        return discoveredTours;
      }
      
      final tourDirs = await toursDir.list()
        .where((entity) => entity is Directory)
        .cast<Directory>()
        .toList();
      
      for (final dir in tourDirs) {
        try {
          final indexFile = File('${dir.path}/index.html');
          if (await indexFile.exists()) {
            final dirName = dir.path.split('/').last;
            final tourData = {
              'path': dir.path,
              'title': _extractTourTitle(dirName),
              'discovered': true,
              'last_modified': (await dir.stat()).modified.toIso8601String(),
            };
            
            discoveredTours.add(tourData);
          }
        } catch (e) {
          // Silent continue for individual directory errors
        }
      }
      
    } catch (e) {
      await DebugLogHelper.addDebugLog('ERROR: Tour discovery failed: $e');
    }
    
    return discoveredTours;
  }
  
  Future<void> _updateSharedPreferencesWithDiscoveredTour(Map<String, dynamic> tourData) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final savedTours = prefs.getStringList('saved_tours') ?? [];
      
      bool updated = false;
      for (int i = 0; i < savedTours.length; i++) {
        try {
          final existingTour = jsonDecode(savedTours[i]) as Map<String, dynamic>;
          final existingTitle = existingTour['title']?.toString() ?? '';
          final newTitle = tourData['title']?.toString() ?? '';
          
          if (existingTitle == newTitle || 
              (existingTour['path']?.toString().contains(RegExp(r'[0-9a-f-]{36}')) == true)) {
            
            existingTour['path'] = tourData['path'];
            savedTours[i] = jsonEncode(existingTour);
            updated = true;
            break;
          }
        } catch (e) {
          continue;
        }
      }
      
      if (updated) {
        await prefs.setStringList('saved_tours', savedTours);
      }
      
    } catch (e) {
      await DebugLogHelper.addDebugLog('ERROR: Failed to update SharedPreferences: $e');
    }
  }
  
  static String _extractTourTitle(String dirName) {
    try {
      // Remove UUID and convert underscores to spaces
      final nameWithoutUuid = dirName.replaceAll(RegExp(r'_[0-9a-f-]{36}$'), '');
      if (nameWithoutUuid.isEmpty || nameWithoutUuid == dirName) {
        // If no UUID pattern found, try to read from index.html or use generic name
        return 'Audio Tour';
      }
      return nameWithoutUuid.replaceAll('_', ' ').split(' ')
        .map((word) => word.isNotEmpty ? word[0].toUpperCase() + word.substring(1) : '')
        .join(' ');
    } catch (e) {
      return 'Audio Tour';
    }
  }
  
  void _updateUIIndicators() {
    setState(() {});
  }
  
  List<Map<String, dynamic>> _prepareStopsForBackend(List<Map<String, dynamic>> stops) {
    final cleanedStops = <Map<String, dynamic>>[];
    
    for (final stop in stops) {
      final cleanedStop = Map<String, dynamic>.from(stop);
      final action = stop['action'];
      final isModified = stop['modified'] == true;
      final hasOriginalText = stop['original_text']?.isNotEmpty == true;

      if (action == 'delete') {
        cleanedStop['modified'] = false;
        cleanedStop['action'] = 'delete';
      } else if (action == 'add' && !hasOriginalText) {
        cleanedStop['original_text'] = '';
        cleanedStop['action'] = 'add';
      } else if (isModified) {
        cleanedStop['original_text'] = hasOriginalText ? stop['original_text'] : '';
        cleanedStop['action'] = hasOriginalText ? 'modify' : 'add';
      } else if (action == null) {
        cleanedStop['action'] = 'unchanged';
      }
      
      cleanedStops.add(cleanedStop);
    }
    
    return cleanedStops;
  }
  
  String _newStopContent = '';
  
  void _addNewStop() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Add New Stop'),
        content: TextField(
          decoration: InputDecoration(
            labelText: 'Stop Content',
            hintText: 'Enter stop content...',
          ),
          maxLines: 3,
          onChanged: (value) => _newStopContent = value,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: _confirmAddStop,
            child: Text('Add Stop'),
          ),
        ],
      ),
    );
  }
  
  void _confirmAddStop() {
    if (_newStopContent.isNotEmpty) {
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
      
      _stops.add(newStop);
      _stops.sort((a, b) => a['stop_number'].compareTo(b['stop_number']));
      
      Navigator.pop(context);
      DebugLogHelper.addDebugLog('USER_ACTION: Added new stop $newStopNumber');
      
      _newStopContent = '';
      setState(() {});
    }
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
        if (_stops[i]['action'] == null) {
          _stops[i]['action'] = 'unchanged';
        }
        _stops[i]['moved'] = true;
      }
    }
    
    DebugLogHelper.addDebugLog('USER_ACTION: Reordered stops from position $oldIndex to $newIndex');
    _updateUIIndicators();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Edit: ${widget.tourData['title']}'),
        backgroundColor: Color(0xFF2c3e50),
        foregroundColor: Colors.white,
      ),
      body: _isLoading
          ? Center(child: CircularProgressIndicator())
          : _stops.isEmpty
              ? Center(
                  child: Text(
                    'No stops found in this tour',
                    style: TextStyle(fontSize: 18, color: Colors.grey),
                  ),
                )
              : Column(
                  children: [
                    Container(
                      padding: EdgeInsets.all(16),
                      color: Colors.blue.shade50,
                      child: Column(
                        children: [
                          Row(
                            children: [
                              Icon(Icons.info, color: Colors.blue.shade700),
                              SizedBox(width: 8),
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
                            SizedBox(height: 8),
                            Row(
                              children: [
                                Icon(Icons.warning, color: Colors.orange.shade700, size: 16),
                                SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    'You have unsaved changes. Use "Save All Changes" for bulk save.',
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
                            margin: EdgeInsets.all(8),
                            child: ListTile(
                              leading: CircleAvatar(
                                backgroundColor: stop['modified'] == true 
                                    ? Colors.orange 
                                    : stop['action'] == 'delete' 
                                        ? Colors.red
                                        : stop['action'] == 'add'
                                            ? Colors.green
                                            : Color(0xFF3498db),
                                child: Text(
                                  '${stop['stop_number']}',
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
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
                                stop['text'].length > 100
                                    ? '${stop['text'].substring(0, 100)}...'
                                    : stop['text'],
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  decoration: stop['action'] == 'delete' 
                                      ? TextDecoration.lineThrough 
                                      : null,
                                ),
                              ),
                              trailing: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  if (stop['action'] == 'add') ...[
                                    Icon(Icons.add_circle, color: Colors.green, size: 16),
                                    SizedBox(width: 4),
                                    Text('New', style: TextStyle(color: Colors.green, fontSize: 12)),
                                    SizedBox(width: 8),
                                  ],
                                  if (stop['action'] == 'delete') ...[
                                    Icon(Icons.delete, color: Colors.red, size: 16),
                                    SizedBox(width: 4),
                                    Text('Delete', style: TextStyle(color: Colors.red, fontSize: 12)),
                                    SizedBox(width: 8),
                                  ],
                                  if (stop['moved'] == true) ...[
                                    Icon(Icons.swap_vert, color: Colors.purple, size: 16),
                                    SizedBox(width: 4),
                                    Text('Moved', style: TextStyle(color: Colors.purple, fontSize: 12)),
                                    SizedBox(width: 8),
                                  ],
                                  if (stop['modified'] == true && stop['action'] != 'add' && stop['action'] != 'delete') ...[
                                    Icon(Icons.circle, color: Colors.orange, size: 12),
                                    SizedBox(width: 4),
                                    Text('Modified', style: TextStyle(color: Colors.orange, fontSize: 12)),
                                    SizedBox(width: 8),
                                  ],
                                  if (stop['action'] != 'delete') 
                                    Icon(Icons.edit, color: Colors.grey[600]),
                                  SizedBox(width: 8),
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
                      padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                      child: OutlinedButton.icon(
                        onPressed: _addNewStop,
                        icon: Icon(Icons.add, color: Colors.green),
                        label: Text('Add Stop', style: TextStyle(color: Colors.green)),
                        style: OutlinedButton.styleFrom(
                          side: BorderSide(color: Colors.green),
                        ),
                      ),
                    ),
                    Container(
                      padding: EdgeInsets.all(16),
                      child: Row(
                        children: [
                          Expanded(
                            child: OutlinedButton(
                              onPressed: () => Navigator.pop(context),
                              child: Text('Cancel'),
                            ),
                          ),
                          SizedBox(width: 16),
                          Expanded(
                            child: ElevatedButton(
                              onPressed: _hasAnyChanges() ? () async => await _saveAllChanges() : null,
                              child: Text(_hasAnyChanges() 
                                  ? 'Save All Changes (${_getModifiedCount()})' 
                                  : 'No Changes'),
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