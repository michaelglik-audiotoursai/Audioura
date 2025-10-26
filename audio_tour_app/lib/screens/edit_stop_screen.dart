import 'package:flutter/material.dart';
import 'dart:io';
import 'dart:convert';
import 'package:permission_handler/permission_handler.dart';
import 'package:path_provider/path_provider.dart';
import 'package:file_picker/file_picker.dart';
import '../screens/debug_log_viewer_screen.dart';
import '../services/tour_editing_service.dart';
import '../services/html_audio_player_service.dart';
import '../services/html_audio_recorder_service.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

// Cross-platform native recording: Android MediaRecorder, iOS AVAudioRecorder
// Replaces flutter_sound due to consistent microphone access issues

class EditStopScreen extends StatefulWidget {
  final Map<String, dynamic> tourData;
  final Map<String, dynamic> stopData;

  const EditStopScreen({
    super.key,
    required this.tourData,
    required this.stopData,
  });

  @override
  State<EditStopScreen> createState() => _EditStopScreenState();
}

class _EditStopScreenState extends State<EditStopScreen> {
  late TextEditingController _textController;
  bool _hasChanges = false;
  bool _isLoading = false;
  String _progressMessage = '';
  
  // Audio services - HTML5 only for recording
  final HtmlAudioPlayerService _htmlAudioPlayer = HtmlAudioPlayerService();
  final HtmlAudioRecorderService _htmlRecorder = HtmlAudioRecorderService();
  InAppWebViewController? _audioWebViewController;
  InAppWebViewController? _recorderWebViewController;
  bool _hasCustomAudio = false;
  bool _isRecording = false;
  bool _isPausedRecording = false;
  int _recordingDuration = 0;
  bool _generateAudioFromText = true;
  
  // Redesigned audio interface
  List<String> _recordingParts = [];
  String _selectedAudioSource = 'original';
  bool _isRecordingNew = false;
  String? _newPartName;

  @override
  void initState() {
    super.initState();
    _textController = TextEditingController(text: widget.stopData['text']);
    _textController.addListener(() {
      final hasChanges = _textController.text != widget.stopData['original_text'];
      setState(() {
        _hasChanges = hasChanges;
      });
      
      // Mark stop as modified in parent data
      widget.stopData['modified'] = hasChanges;
      widget.stopData['text'] = _textController.text;
    });
    
    // Preserve existing recording parts if re-editing
    if (widget.stopData['recording_parts'] != null) {
      _recordingParts = List<String>.from(widget.stopData['recording_parts']);
      // Remove await from non-async initState method
      DebugLogHelper.addDebugLog('EDIT_STOP: Restored ${_recordingParts.length} existing recording parts');
    }
    
    // Initialize audio source based on stop state
    if (widget.stopData['action'] == 'add') {
      _selectedAudioSource = 'no_original';
    } else if (widget.stopData['has_custom_audio'] == true) {
      if (_recordingParts.isNotEmpty) {
        _selectedAudioSource = 'part_${_recordingParts.length - 1}'; // Select last part
      } else {
        _selectedAudioSource = 'custom_audio_exists';
      }
    } else {
      _selectedAudioSource = 'original';
    }
    
    _initializeAudioServices();
  }
  
  Future<void> _initializeAudioServices() async {
    _hasCustomAudio = widget.stopData['has_custom_audio'] ?? false;
    _generateAudioFromText = widget.stopData['generate_audio_from_text'] ?? true;
    
    await DebugLogHelper.addDebugLog('EDIT_STOP: HTML5 audio services initialized');
  }
  
  Future<void> _showSilentRecordingDialog() async {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Row(
          children: [
            Icon(Icons.warning, color: Colors.orange),
            SizedBox(width: 8),
            Text('Silent Recording Detected'),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'No audio was captured during recording. This usually happens when:',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 12),
            Text('• Voice Control is active (using microphone)'),
            Text('• Another app is using the microphone'),
            Text('• Microphone permission was revoked'),
            Text('• Hardware microphone issue'),
            SizedBox(height: 12),
            Text(
              'Solutions to try:',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 8),
            Text('1. Close Voice Control completely'),
            Text('2. Close other apps using microphone'),
            Text('3. Restart the AudioTours app'),
            Text('4. Check microphone permissions'),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('OK'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              _startNewRecording();
            },
            child: Text('Try Again'),
          ),
          TextButton(
            onPressed: () {
              Navigator.pop(context);
              openAppSettings();
            },
            child: Text('Settings'),
          ),
        ],
      ),
    );
  }
  
  Future<void> _showRecordingFailedDialog() async {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Row(
          children: [
            Icon(Icons.error, color: Colors.red),
            SizedBox(width: 8),
            Text('Recording Failed'),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Unable to start audio recording. Common causes:',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 12),
            Text('• Audio codec not supported on this device'),
            Text('• Microphone permission denied'),
            Text('• Hardware microphone not available'),
            Text('• System audio service unavailable'),
            SizedBox(height: 12),
            Text(
              'Try these solutions:',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 8),
            Text('1. Grant microphone permission'),
            Text('2. Restart the app'),
            Text('3. Check device audio settings'),
            Text('4. Test Voice Control (should work)'),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              _startNewRecording();
            },
            child: Text('Try Again'),
          ),
          TextButton(
            onPressed: () {
              Navigator.pop(context);
              openAppSettings();
            },
            child: Text('Permissions'),
          ),
        ],
      ),
    );
  }

  @override
  void dispose() {
    _textController.dispose();
    _htmlRecorder.dispose();
    super.dispose();
  }



  // Removed - replaced with _recordCurrentPart()
  
  void _updateRecordingDuration() {
    if (_isRecording) {
      setState(() {
        _recordingDuration = _htmlRecorder.recordingDuration;
      });
      
      Future.delayed(Duration(seconds: 1), () {
        if (_isRecording) {
          _updateRecordingDuration();
        }
      });
    }
  }
  
  // Removed - no longer needed for HTML5 recording

  Future<void> _previewRecording() async {
    // Preview HTML5 recording using HTML audio player
    await _loadSelectedAudio();
    
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Audio loaded in player above.'),
        backgroundColor: Colors.blue,
        duration: Duration(seconds: 2),
      ),
    );
  }
  
  List<DropdownMenuItem<String>> _buildNewStopAudioItems() {
    List<DropdownMenuItem<String>> items = [
      DropdownMenuItem(
        value: 'no_original',
        child: Text('No Original Audio'),
      ),
    ];
    
    for (int i = 0; i < _recordingParts.length; i++) {
      items.add(
        DropdownMenuItem(
          value: 'part_$i',
          child: Text('Part ${i + 1}'),
        ),
      );
    }
    
    if (_isRecordingNew && _newPartName != null) {
      items.add(
        DropdownMenuItem(
          value: 'new_part',
          child: Text(_newPartName!),
        ),
      );
    }
    
    return items;
  }
  
  List<DropdownMenuItem<String>> _buildAudioSourceItems() {
    List<DropdownMenuItem<String>> items = [
      DropdownMenuItem(
        value: 'original',
        child: Text('Original Audio'),
      ),
    ];
    
    // Show existing custom audio option if present
    if (widget.stopData['has_custom_audio'] == true) {
      items.add(
        DropdownMenuItem(
          value: 'custom_audio_exists',
          child: Text('Custom Audio (Replace?)'),
        ),
      );
    }
    
    for (int i = 0; i < _recordingParts.length; i++) {
      items.add(
        DropdownMenuItem(
          value: 'part_$i',
          child: Text('Part ${i + 1}'),
        ),
      );
    }
    
    // Add new part if recording
    if (_isRecordingNew && _newPartName != null) {
      items.add(
        DropdownMenuItem(
          value: 'new_part',
          child: Text(_newPartName!),
        ),
      );
    }
    
    return items;
  }
  
  Future<void> _loadSelectedAudio() async {
    if (_audioWebViewController == null) return;
    
    try {
      if (_selectedAudioSource == 'original') {
        // Load original audio
        final tourPath = widget.tourData['path'];
        final audioFile = widget.stopData['audio_file'];
        final audioPath = '$tourPath/$audioFile';
        await _htmlAudioPlayer.loadAudio(audioPath, _audioWebViewController!);
        await DebugLogHelper.addDebugLog('AUDIO_LOAD: Loaded original audio: $audioPath');
      } else if (_selectedAudioSource.startsWith('part_')) {
        // Load recording part
        final partIndex = int.parse(_selectedAudioSource.split('_')[1]);
        if (partIndex < _recordingParts.length) {
          final partPath = _recordingParts[partIndex];
          await _htmlAudioPlayer.loadAudio(partPath, _audioWebViewController!);
          await DebugLogHelper.addDebugLog('AUDIO_LOAD: Loaded part $partIndex: $partPath');
          
          // Force duration display update for custom recordings
          await Future.delayed(Duration(milliseconds: 500));
          await _audioWebViewController!.evaluateJavascript(source: """
            const audio = document.getElementById('audioPlayer');
            
            function forceUpdateDuration() {
              if (audio && audio.duration && !isNaN(audio.duration)) {
                updatePosition();
                console.log('Duration loaded:', audio.duration + 's');
                return true;
              }
              return false;
            }
            
            // Try immediate update
            if (!forceUpdateDuration()) {
              // Force load and wait for metadata
              audio.load();
              
              // Multiple retry attempts
              let attempts = 0;
              const retryUpdate = () => {
                attempts++;
                if (forceUpdateDuration() || attempts >= 5) {
                  return;
                }
                setTimeout(retryUpdate, 200);
              };
              
              setTimeout(retryUpdate, 300);
            }
          """);
        } else {
          await DebugLogHelper.addDebugLog('AUDIO_LOAD: Part index $partIndex out of range (${_recordingParts.length} parts)');
        }
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('AUDIO_LOAD: Error loading $_selectedAudioSource - $e');
    }
  }
  
  Future<void> _startNewRecording() async {
    try {
      await DebugLogHelper.addDebugLog('START_RECORDING: Attempting to start new recording');
      
      // Clean up previous recording state
      _htmlRecorder.dispose();
      await _htmlRecorder.initialize(_recorderWebViewController!);
      
      // Add small delay for initialization
      await Future.delayed(Duration(milliseconds: 300));
      
      final partNumber = _recordingParts.length + 1;
      final success = await _htmlRecorder.startRecording();
      
      if (success) {
        setState(() {
          _isRecording = true;
          _isRecordingNew = true;
          _newPartName = 'Part $partNumber (new)';
          _selectedAudioSource = 'new_part';
        });
        
        await DebugLogHelper.addDebugLog('START_RECORDING: Recording started successfully for part $partNumber');
        _updateRecordingDuration();
      } else {
        await DebugLogHelper.addDebugLog('START_RECORDING: Failed to start recording');
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to start recording. Please try again.'),
            backgroundColor: Colors.red,
          ),
        );
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('START_RECORDING: Error - $e');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Recording error: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }
  
  Future<void> _stopRecording() async {
    if (_isRecording) {
      await _htmlRecorder.stopRecording();
      
      // Wait a moment for HTML5 recorder to process
      await Future.delayed(Duration(milliseconds: 500));
      
      // Check if we have audio data, retry once if not
      if (_htmlRecorder.recordedAudioBase64 == null) {
        await DebugLogHelper.addDebugLog('STOP_RECORDING: No audio data, waiting longer...');
        await Future.delayed(Duration(milliseconds: 1000));
      }
      
      // Save the part
      if (_htmlRecorder.recordedAudioBase64 != null) {
        // Check if this is a re-recording
        bool isReRecording = _newPartName != null && _newPartName!.contains('re-recording');
        int partIndex;
        
        if (isReRecording) {
          // Extract the part index from the re-recording name
          final match = RegExp(r'Part (\d+)').firstMatch(_newPartName!);
          partIndex = match != null ? int.parse(match.group(1)!) - 1 : _recordingParts.length;
        } else {
          // New part
          partIndex = _recordingParts.length;
        }
        
        final partPath = await _saveRecordingPart(partIndex);
        
        if (partPath != null) {
          if (isReRecording && partIndex < _recordingParts.length) {
            // Replace existing part
            final oldPath = _recordingParts[partIndex];
            _recordingParts[partIndex] = partPath;
            
            // Delete old file
            try {
              final oldFile = File(oldPath);
              if (await oldFile.exists()) {
                await oldFile.delete();
              }
            } catch (e) {
              await DebugLogHelper.addDebugLog('STOP_RECORDING: Error deleting old part - $e');
            }
            
            await DebugLogHelper.addDebugLog('STOP_RECORDING: Re-recorded part $partIndex: $partPath');
          } else {
            // Add new part
            _recordingParts.add(partPath);
            await DebugLogHelper.addDebugLog('STOP_RECORDING: Added new part $partIndex: $partPath');
          }
          
          setState(() {
            _isRecording = false;
            _isRecordingNew = false;
            _selectedAudioSource = 'part_$partIndex';
            _newPartName = null;
          });
          
          await DebugLogHelper.addDebugLog('STOP_RECORDING: Auto-selected part_$partIndex in dropdown');
          
          // Force dropdown refresh and audio load
          await Future.delayed(Duration(milliseconds: 200));
          setState(() {
            // Ensure dropdown shows the new selection
          });
          
          // Load the newly recorded audio
          await _loadSelectedAudio();
          
          // Force reload audio with delay for metadata
          await Future.delayed(Duration(milliseconds: 300));
          await _loadSelectedAudio();
          
          // Force duration display update for new recordings
          await Future.delayed(Duration(milliseconds: 500));
          if (_audioWebViewController != null) {
            await _audioWebViewController!.evaluateJavascript(source: """
              const audio = document.getElementById('audioPlayer');
              if (audio) {
                audio.load();
                audio.addEventListener('loadedmetadata', function() {
                  updatePosition();
                  console.log('New recording duration loaded:', audio.duration);
                });
                // Force immediate update if already loaded
                if (audio.readyState >= 1) {
                  updatePosition();
                }
              }
            """);
          }
          
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(isReRecording 
                  ? 'Part ${partIndex + 1} re-recorded successfully!' 
                  : 'Part ${partIndex + 1} recorded successfully!'),
              backgroundColor: Colors.green,
            ),
          );
        } else {
          await DebugLogHelper.addDebugLog('STOP_RECORDING: Failed to save recording part');
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Failed to save recording. Please try again.'),
              backgroundColor: Colors.red,
            ),
          );
        }
      } else {
        await DebugLogHelper.addDebugLog('STOP_RECORDING: No audio data available after retries');
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('No audio recorded. Please try recording again.'),
            backgroundColor: Colors.orange,
          ),
        );
        
        // Reset UI state
        setState(() {
          _isRecording = false;
          _isRecordingNew = false;
          _newPartName = null;
        });
      }
    }
  }
  
  Future<void> _reRecordPart() async {
    if (_selectedAudioSource.startsWith('part_')) {
      try {
        final partIndex = int.parse(_selectedAudioSource.split('_')[1]);
        
        await DebugLogHelper.addDebugLog('RE_RECORD: Attempting to re-record part $partIndex');
        
        // Clear the HTML5 recorder first
        _htmlRecorder.dispose();
        await Future.delayed(Duration(milliseconds: 200));
        await _htmlRecorder.initialize(_recorderWebViewController!);
        
        // Add delay for proper initialization
        await Future.delayed(Duration(milliseconds: 300));
        
        final success = await _htmlRecorder.startRecording();
        
        if (success) {
          setState(() {
            _isRecording = true;
            _isRecordingNew = true;
            _newPartName = 'Part ${partIndex + 1} (re-recording)';
            _selectedAudioSource = 'new_part';
          });
          
          await DebugLogHelper.addDebugLog('RE_RECORD: Started re-recording part $partIndex');
          _updateRecordingDuration();
        } else {
          await DebugLogHelper.addDebugLog('RE_RECORD: Failed to start re-recording part $partIndex');
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Failed to start re-recording. Please try again.'),
              backgroundColor: Colors.red,
            ),
          );
        }
      } catch (e) {
        await DebugLogHelper.addDebugLog('RE_RECORD: Error - $e');
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Re-recording error: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }
  
  Future<void> _deletePart() async {
    if (_selectedAudioSource.startsWith('part_')) {
      final partIndex = int.parse(_selectedAudioSource.split('_')[1]);
      
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text('Delete Recording Part'),
          content: Text('Delete Part ${partIndex + 1}? This cannot be undone.'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: Text('Cancel'),
            ),
            ElevatedButton(
              onPressed: () => Navigator.pop(context, true),
              style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
              child: Text('Delete', style: TextStyle(color: Colors.white)),
            ),
          ],
        ),
      );
      
      if (confirmed == true) {
        // Delete the file
        try {
          final file = File(_recordingParts[partIndex]);
          if (await file.exists()) {
            await file.delete();
          }
        } catch (e) {
          await DebugLogHelper.addDebugLog('DELETE_PART: Error deleting file - $e');
        }
        
        // Remove from list
        _recordingParts.removeAt(partIndex);
        
        setState(() {
          _selectedAudioSource = 'original';
        });
        
        await _loadSelectedAudio();
        
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Part ${partIndex + 1} deleted'),
            backgroundColor: Colors.orange,
          ),
        );
      }
    }
  }
  
  void _cancelNewRecording() {
    setState(() {
      _isRecordingNew = false;
      _newPartName = null;
      _selectedAudioSource = _recordingParts.isNotEmpty ? 'part_${_recordingParts.length - 1}' : 'original';
    });
  }
  
  Future<String?> _saveRecordingPart(int partIndex) async {
    if (_htmlRecorder.recordedAudioBase64 == null) return null;
    
    try {
      final bytes = base64Decode(_htmlRecorder.recordedAudioBase64!);
      final timestamp = DateTime.now().millisecondsSinceEpoch;
      final fileName = 'recording_part_${partIndex}_$timestamp.webm';
      final filePath = '/data/data/com.audiotours.dev/cache/$fileName';
      
      final file = File(filePath);
      await file.writeAsBytes(bytes);
      
      // Verify file was written correctly
      if (await file.exists()) {
        final savedSize = await file.length();
        await DebugLogHelper.addDebugLog('PART_RECORDING: Saved part $partIndex to $filePath (${bytes.length} bytes -> $savedSize bytes on disk)');
        return filePath;
      } else {
        await DebugLogHelper.addDebugLog('PART_RECORDING: File not found after save: $filePath');
        return null;
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('PART_RECORDING: Save error - $e');
      return null;
    }
  }
  
  Future<void> _resumeRecording() async {
    await _htmlRecorder.resumeRecording();
    setState(() {
      _isPausedRecording = false;
      _isRecording = true;
    });
  }
  
  Future<void> _useMultiPartRecording() async {
    if (_recordingParts.isEmpty) return;
    
    try {
      // Smart detection: Check if user uploaded any files
      final hasUploadedParts = _recordingParts.any((path) => path.contains('uploaded_audio'));
      final hasOnlyRecordings = _recordingParts.every((path) => path.contains('recording_part'));
      
      await DebugLogHelper.addDebugLog('AUDIO_PROTOCOL: hasUploaded=$hasUploadedParts, onlyRecordings=$hasOnlyRecordings');
      
      String? audioPath;
      
      // For single uploaded file, use it directly
      if (_recordingParts.length == 1 && hasUploadedParts) {
        audioPath = _recordingParts[0];
        await DebugLogHelper.addDebugLog('AUDIO_PROTOCOL: Single uploaded file - using directly: $audioPath');
      } else if (hasUploadedParts) {
        // Mixed formats - use concatenation for now (backend multi-part not ready)
        await DebugLogHelper.addDebugLog('AUDIO_PROTOCOL: Mixed formats detected - using concatenation fallback');
        audioPath = await _concatenateRecordingParts();
      } else {
        // Same format (all recordings) - use concatenation
        await DebugLogHelper.addDebugLog('AUDIO_PROTOCOL: Same format detected - using concatenation');
        audioPath = await _concatenateRecordingParts();
      }
      
      if (audioPath == null) {
        throw Exception('Failed to process recording parts');
      }
      
      // Update UI state
      setState(() {
        _hasCustomAudio = true;
        _generateAudioFromText = false;
        _hasChanges = true;
      });
      
      // Update stop data
      widget.stopData['has_custom_audio'] = true;
      widget.stopData['audio_source'] = 'user_recorded';
      widget.stopData['generate_audio_from_text'] = false;
      widget.stopData['custom_audio_path'] = audioPath;
      widget.stopData['modified'] = true;
      widget.stopData['custom_audio_archived'] = true;
      widget.stopData['recording_parts'] = List<String>.from(_recordingParts); // Preserve parts for re-editing
      
      final protocolUsed = (_recordingParts.length == 1 && hasUploadedParts) ? 'direct file' : 
                          hasUploadedParts ? 'concatenation (fallback)' : 'concatenation';
      await DebugLogHelper.addDebugLog('MULTI_PART: Custom recording ready with ${_recordingParts.length} parts using $protocolUsed');
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Custom recording ready! (${_recordingParts.length} parts processed)'),
          backgroundColor: Colors.green,
          duration: Duration(seconds: 3),
        ),
      );
    } catch (e) {
      await DebugLogHelper.addDebugLog('MULTI_PART: Error - $e');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to prepare custom recording: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }
  
  Future<String?> _sendMultiPartAudio() async {
    try {
      await DebugLogHelper.addDebugLog('MULTI_PART: Preparing ${_recordingParts.length} parts for backend');
      
      final audioParts = await _prepareAudioParts();
      
      // This will be the actual implementation when Services Amazon-Q completes backend
      final response = await _sendMultiPartRequest(audioParts);
      
      // Handle warnings from backend response
      await _handleAudioWarnings(response);
      
      return response['audio_path'];
    } catch (e) {
      await DebugLogHelper.addDebugLog('MULTI_PART: Error - $e');
      rethrow;
    }
  }
  
  Future<List<Map<String, dynamic>>> _prepareAudioParts() async {
    final parts = <Map<String, dynamic>>[];
    
    for (int i = 0; i < _recordingParts.length; i++) {
      final partFile = File(_recordingParts[i]);
      if (await partFile.exists()) {
        final bytes = await partFile.readAsBytes();
        final format = _recordingParts[i].split('.').last.toLowerCase();
        
        parts.add({
          'part_number': i + 1,
          'format': format,
          'size_bytes': bytes.length,
          'data': base64Encode(bytes),
        });
        
        await DebugLogHelper.addDebugLog('MULTI_PART: Prepared part ${i + 1} ($format, ${bytes.length} bytes)');
      }
    }
    
    return parts;
  }
  
  Future<Map<String, dynamic>> _sendMultiPartRequest(List<Map<String, dynamic>> audioParts) async {
    try {
      await DebugLogHelper.addDebugLog('MULTI_PART_REQUEST: Sending ${audioParts.length} parts to backend');
      
      // Prepare multi-part request payload
      final requestData = {
        'stop_number': widget.stopData['stop_number'],
        'text': widget.stopData['text'],
        'audio_source': 'multi_part_custom',
        'audio_parts': audioParts,
        'part_count': audioParts.length,
      };
      
      // Send via TourEditingService (will be routed to multi-part processing)
      final tourPath = widget.tourData['path'] as String;
      final tourId = tourPath.split('/').last;
      
      // Extract backend tour ID
      String backendTourId = tourId;
      final uuidPattern = RegExp(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}');
      final uuidMatch = uuidPattern.firstMatch(tourId);
      if (uuidMatch != null) {
        backendTourId = uuidMatch.group(0)!;
      }
      
      await DebugLogHelper.addDebugLog('MULTI_PART_REQUEST: Using tour ID $backendTourId');
      
      // Use existing TourEditingService with multi-part data
      final result = await TourEditingService.updateMultipleStops(
        tourId: backendTourId,
        allStops: [requestData],
      );
      
      await DebugLogHelper.addDebugLog('MULTI_PART_RESPONSE: ${result.toString()}');
      
      // For single uploaded file, return the actual file path
      if (audioParts.length == 1 && _recordingParts.isNotEmpty) {
        return {
          'audio_path': _recordingParts[0], // Use actual uploaded file path
          'stops': result['stops'] ?? [],
          'warnings': [], // Will be populated by backend
        };
      }
      
      // For multiple parts, use concatenation fallback
      final concatenatedPath = await _concatenateRecordingParts();
      return {
        'audio_path': concatenatedPath ?? '/data/data/com.audiotours.dev/cache/multipart_${DateTime.now().millisecondsSinceEpoch}.mp3',
        'stops': result['stops'] ?? [],
        'warnings': [], // Will be populated by backend
      };
      
    } catch (e) {
      await DebugLogHelper.addDebugLog('MULTI_PART_REQUEST: Error - $e');
      rethrow;
    }
  }
  
  Future<void> _handleAudioWarnings(Map<String, dynamic> response) async {
    final stops = response['stops'] as List?;
    if (stops == null || stops.isEmpty) return;
    
    final stopData = stops[0] as Map<String, dynamic>;
    final warnings = List<String>.from(stopData['warnings'] ?? []);
    
    if (warnings.isNotEmpty) {
      await DebugLogHelper.addDebugLog('AUDIO_WARNINGS: ${warnings.length} warnings received');
      
      if (warnings.length == 1) {
        // Single warning - use snackbar
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Audio created with issue: ${warnings[0]}'),
            backgroundColor: Colors.orange,
            duration: Duration(seconds: 4),
            action: SnackBarAction(
              label: 'Retry',
              onPressed: _retryFailedParts,
            ),
          ),
        );
      } else {
        // Multiple warnings - use dialog
        await _showWarningDialog(warnings);
      }
    }
  }
  
  Future<void> _showWarningDialog(List<String> warnings) async {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Row(
          children: [
            Icon(Icons.warning, color: Colors.orange),
            SizedBox(width: 8),
            Text('Audio Processing Warnings'),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Some audio parts had issues:',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 12),
            ...warnings.map((warning) => Padding(
              padding: EdgeInsets.only(bottom: 4),
              child: Text('• $warning'),
            )),
            SizedBox(height: 16),
            Container(
              padding: EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Colors.blue.shade50,
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                'The audio was created using available parts. You can continue or retry the failed parts.',
                style: TextStyle(
                  color: Colors.blue.shade800,
                  fontSize: 12,
                ),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('Continue'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              _retryFailedParts();
            },
            child: Text('Retry Failed Parts'),
          ),
        ],
      ),
    );
  }
  
  Future<void> _retryFailedParts() async {
    try {
      await DebugLogHelper.addDebugLog('RETRY: User requested retry of failed parts');
      
      // For now, retry all parts until we can parse specific failed part numbers
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Retrying audio processing...'),
          backgroundColor: Colors.blue,
        ),
      );
      
      // Re-attempt the multi-part upload
      await _useMultiPartRecording();
      
    } catch (e) {
      await DebugLogHelper.addDebugLog('RETRY: Error - $e');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Retry failed: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }
  
  Future<String?> _concatenateRecordingParts() async {
    if (_recordingParts.isEmpty) return null;
    
    try {
      final timestamp = DateTime.now().millisecondsSinceEpoch;
      
      await DebugLogHelper.addDebugLog('CONCATENATE: Starting with ${_recordingParts.length} parts');
      for (int i = 0; i < _recordingParts.length; i++) {
        await DebugLogHelper.addDebugLog('CONCATENATE: Part $i path: ${_recordingParts[i]}');
      }
      
      if (_recordingParts.length == 1) {
        // Single part - check format and convert if needed
        final partFile = File(_recordingParts[0]);
        if (await partFile.exists()) {
          final extension = _recordingParts[0].split('.').last.toLowerCase();
          String outputPath;
          
          if (extension == 'mp3' || extension == 'wav') {
            // Already in supported format, just copy
            outputPath = '/data/data/com.audiotours.dev/cache/concatenated_$timestamp.$extension';
            await partFile.copy(outputPath);
          } else {
            // WebM or other format - keep as is but log warning
            outputPath = '/data/data/com.audiotours.dev/cache/concatenated_$timestamp.webm';
            await partFile.copy(outputPath);
            await DebugLogHelper.addDebugLog('CONCATENATE: WARNING - Single part is $extension format, backend may not support');
          }
          
          final size = await partFile.length();
          await DebugLogHelper.addDebugLog('CONCATENATE: Single part copied ($size bytes): ${_recordingParts[0]}');
          return outputPath;
        } else {
          await DebugLogHelper.addDebugLog('CONCATENATE: Single part file not found: ${_recordingParts[0]}');
          return null;
        }
      } else {
        // Multiple parts - determine output format based on first supported format
        String outputExtension = 'webm'; // Default
        for (final partPath in _recordingParts) {
          final ext = partPath.split('.').last.toLowerCase();
          if (ext == 'mp3' || ext == 'wav') {
            outputExtension = ext;
            break;
          }
        }
        
        final outputPath = '/data/data/com.audiotours.dev/cache/concatenated_$timestamp.$outputExtension';
        final outputFile = File(outputPath);
        final sink = outputFile.openWrite();
        
        int totalBytes = 0;
        for (int i = 0; i < _recordingParts.length; i++) {
          final partFile = File(_recordingParts[i]);
          if (await partFile.exists()) {
            final bytes = await partFile.readAsBytes();
            sink.add(bytes);
            totalBytes += bytes.length;
            await DebugLogHelper.addDebugLog('CONCATENATE: Added part $i (${bytes.length} bytes): ${_recordingParts[i]}');
          } else {
            await DebugLogHelper.addDebugLog('CONCATENATE: Part $i not found: ${_recordingParts[i]}');
          }
        }
        
        await sink.close();
        await DebugLogHelper.addDebugLog('CONCATENATE: Combined ${_recordingParts.length} parts into $outputPath ($totalBytes total bytes)');
        
        if (outputExtension == 'webm') {
          await DebugLogHelper.addDebugLog('CONCATENATE: WARNING - Output is WebM format, backend may not support');
        }
        
        // Verify output file exists and has content
        if (await outputFile.exists()) {
          final size = await outputFile.length();
          await DebugLogHelper.addDebugLog('CONCATENATE: Output file created successfully ($size bytes)');
          return outputPath;
        } else {
          await DebugLogHelper.addDebugLog('CONCATENATE: Output file was not created');
          return null;
        }
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('CONCATENATE: Error - $e');
      return null;
    }
  }
  
  Future<void> _pauseRecording() async {
    if (_htmlRecorder.isRecording) {
      await _htmlRecorder.pauseRecording();
      setState(() {
        _isPausedRecording = true;
      });
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('HTML5 recording paused. Press Resume to continue.'),
          backgroundColor: Colors.orange,
        ),
      );
    }
  }
  
  Future<void> _uploadAudioFile() async {
    try {
      await DebugLogHelper.addDebugLog('UPLOAD: Starting audio file upload');
      
      // Try file picker first - modern Android doesn't need storage permission for file picker
      bool canProceed = true;
      
      // Only check permissions on older Android versions
      try {
        final storageStatus = await Permission.storage.status;
        if (!storageStatus.isGranted) {
          await DebugLogHelper.addDebugLog('UPLOAD: Storage permission not granted, requesting...');
          final result = await Permission.storage.request();
          if (!result.isGranted) {
            await DebugLogHelper.addDebugLog('UPLOAD: Storage permission denied by user');
            canProceed = false;
          }
        }
      } catch (e) {
        await DebugLogHelper.addDebugLog('UPLOAD: Permission check failed (may be newer Android): $e');
        // Continue anyway - newer Android versions don't need storage permission for file picker
      }
      
      if (!canProceed) {
        await _showPermissionDeniedDialog();
        return;
      }
      
      // Show file picker dialog
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: Row(
            children: [
              Icon(Icons.upload_file, color: Colors.green),
              SizedBox(width: 8),
              Text('Upload Audio File'),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Select an audio file to upload:',
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
              SizedBox(height: 12),
              Text('• Supported formats: MP3, WAV, AAC, M4A'),
              Text('• Maximum size: 50MB'),
              Text('• Professional recordings recommended'),
              SizedBox(height: 12),
              Container(
                padding: EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: Colors.blue.shade50,
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  'Note: This will be added as a new recording part.',
                  style: TextStyle(
                    color: Colors.blue.shade800,
                    fontSize: 12,
                  ),
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: Text('Cancel'),
            ),
            ElevatedButton(
              onPressed: () => Navigator.pop(context, true),
              style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
              child: Text('Choose File', style: TextStyle(color: Colors.white)),
            ),
          ],
        ),
      );
      
      if (confirmed != true) return;
      
      // Open file picker
      await _pickAndProcessAudioFile();
      
    } catch (e) {
      await DebugLogHelper.addDebugLog('UPLOAD: Error - $e');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Upload error: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }
  
  Future<void> _pickAndProcessAudioFile() async {
    try {
      await DebugLogHelper.addDebugLog('UPLOAD: Opening file picker');
      
      // Open file picker with audio file types
      FilePickerResult? result;
      
      try {
        result = await FilePicker.platform.pickFiles(
          type: FileType.custom,
          allowedExtensions: ['mp3', 'wav', 'aac', 'm4a', 'ogg', 'flac'],
          allowMultiple: false,
        );
      } catch (e) {
        await DebugLogHelper.addDebugLog('UPLOAD: File picker failed: $e');
        
        // If file picker fails due to permissions, show helpful dialog
        if (e.toString().contains('permission') || e.toString().contains('Permission')) {
          await _showFilePickerPermissionError();
          return;
        } else {
          // Other file picker errors
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('File picker error: $e'),
              backgroundColor: Colors.red,
            ),
          );
          return;
        }
      }
      
      if (result != null && result.files.single.path != null) {
        final file = File(result.files.single.path!);
        final fileName = result.files.single.name;
        final fileSize = result.files.single.size;
        
        await DebugLogHelper.addDebugLog('UPLOAD: Selected file: $fileName (${fileSize} bytes)');
        
        // Validate file size (50MB limit)
        const maxSizeBytes = 50 * 1024 * 1024; // 50MB
        if (fileSize > maxSizeBytes) {
          await _showFileSizeError(fileSize, maxSizeBytes);
          return;
        }
        
        // Validate file format
        final extension = fileName.toLowerCase().split('.').last;
        if (!['mp3', 'wav', 'aac', 'm4a', 'ogg', 'flac'].contains(extension)) {
          await _showFormatError(extension);
          return;
        }
        
        // Show processing dialog
        showDialog(
          context: context,
          barrierDismissible: false,
          builder: (context) => AlertDialog(
            content: Row(
              children: [
                CircularProgressIndicator(),
                SizedBox(width: 16),
                Text('Processing audio file...'),
              ],
            ),
          ),
        );
        
        // Copy file to app cache directory
        final copiedPath = await _copyAudioFileToCache(file, fileName);
        
        // Close processing dialog
        Navigator.pop(context);
        
        if (copiedPath != null) {
          // Add to recording parts
          final partIndex = _recordingParts.length;
          _recordingParts.add(copiedPath);
          
          setState(() {
            _selectedAudioSource = 'part_$partIndex';
          });
          
          // Load the uploaded audio
          await _loadSelectedAudio();
          
          await DebugLogHelper.addDebugLog('UPLOAD: File uploaded successfully as part $partIndex');
          
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Audio file uploaded successfully! ($fileName)'),
              backgroundColor: Colors.green,
            ),
          );
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Failed to process audio file'),
              backgroundColor: Colors.red,
            ),
          );
        }
      } else {
        await DebugLogHelper.addDebugLog('UPLOAD: File selection cancelled or no file selected');
      }
      
    } catch (e) {
      await DebugLogHelper.addDebugLog('UPLOAD: File picker error - $e');
      
      // Close processing dialog if open
      if (Navigator.canPop(context)) {
        Navigator.pop(context);
      }
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('File selection error: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }
  
  Future<String?> _copyAudioFileToCache(File sourceFile, String fileName) async {
    try {
      final timestamp = DateTime.now().millisecondsSinceEpoch;
      final extension = fileName.split('.').last;
      final newFileName = 'uploaded_audio_${timestamp}.$extension';
      final cachePath = '/data/data/com.audiotours.dev/cache/$newFileName';
      
      final targetFile = File(cachePath);
      await sourceFile.copy(cachePath);
      
      // Verify file was copied
      if (await targetFile.exists()) {
        final copiedSize = await targetFile.length();
        await DebugLogHelper.addDebugLog('UPLOAD: File copied to $cachePath ($copiedSize bytes)');
        return cachePath;
      } else {
        await DebugLogHelper.addDebugLog('UPLOAD: File copy failed - target not found');
        return null;
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('UPLOAD: File copy error - $e');
      return null;
    }
  }
  
  Future<void> _showFileSizeError(int fileSize, int maxSize) async {
    final fileSizeMB = (fileSize / (1024 * 1024)).toStringAsFixed(1);
    final maxSizeMB = (maxSize / (1024 * 1024)).toStringAsFixed(0);
    
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Row(
          children: [
            Icon(Icons.error, color: Colors.red),
            SizedBox(width: 8),
            Text('File Too Large'),
          ],
        ),
        content: Text(
          'Selected file is ${fileSizeMB}MB. Maximum allowed size is ${maxSizeMB}MB.\n\nPlease select a smaller audio file or compress the existing one.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('OK'),
          ),
        ],
      ),
    );
  }
  
  Future<void> _showPermissionDeniedDialog() async {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Row(
          children: [
            Icon(Icons.security, color: Colors.orange),
            SizedBox(width: 8),
            Text('Storage Permission Required'),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'AudioTours needs storage permission to access your audio files.',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 16),
            Text('To grant permission manually:'),
            SizedBox(height: 8),
            Text('1. Go to Android Settings'),
            Text('2. Find "Apps" or "Application Manager"'),
            Text('3. Find "AudioTours Dev"'),
            Text('4. Tap "Permissions"'),
            Text('5. Enable "Storage" or "Files and media"'),
            SizedBox(height: 16),
            Container(
              padding: EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Colors.blue.shade50,
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                'Tip: You can also try the file picker anyway - newer Android versions may not require this permission.',
                style: TextStyle(
                  color: Colors.blue.shade800,
                  fontSize: 12,
                ),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              openAppSettings();
            },
            child: Text('Open Settings'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              _pickAndProcessAudioFile();
            },
            style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
            child: Text('Try Anyway', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
  }
  
  Future<void> _showFilePickerPermissionError() async {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Row(
          children: [
            Icon(Icons.folder_open, color: Colors.orange),
            SizedBox(width: 8),
            Text('File Access Issue'),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Unable to open file picker. This may be due to:',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 12),
            Text('• Missing storage permissions'),
            Text('• File manager not available'),
            Text('• System security restrictions'),
            SizedBox(height: 16),
            Text(
              'Solutions:',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 8),
            Text('1. Grant storage permission in Settings'),
            Text('2. Install a file manager app'),
            Text('3. Use the recording feature instead'),
            SizedBox(height: 16),
            Container(
              padding: EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Colors.green.shade50,
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                'Alternative: Use the "New" button to record audio directly in the app.',
                style: TextStyle(
                  color: Colors.green.shade800,
                  fontSize: 12,
                ),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              openAppSettings();
            },
            child: Text('App Settings'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              _startNewRecording();
            },
            style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
            child: Text('Record Instead', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
  }
  
  Future<void> _showFormatError(String extension) async {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Row(
          children: [
            Icon(Icons.error, color: Colors.red),
            SizedBox(width: 8),
            Text('Unsupported Format'),
          ],
        ),
        content: Text(
          'File format ".$extension" is not supported.\n\nSupported formats: MP3, WAV, AAC, M4A, OGG, FLAC\n\nPlease convert your audio file to a supported format.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('OK'),
          ),
        ],
      ),
    );
  }
  
  Future<void> _markCustomAudioReady() async {
    // Check if HTML5 recorder has audio data
    if (_htmlRecorder.recordedAudioBase64 == null) {
      await DebugLogHelper.addDebugLog('CUSTOM_AUDIO: No HTML5 recorded audio available');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('No recording found. Please record audio first using the HTML5 recorder above.'),
          backgroundColor: Colors.orange,
        ),
      );
      return;
    }
    
    // Save HTML5 recording to file
    final audioPath = await _htmlRecorder.saveRecordingToFile();
    if (audioPath == null) {
      await DebugLogHelper.addDebugLog('CUSTOM_AUDIO: Failed to save HTML5 recording to file');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to save recording. Please try again.'),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }
    
    await DebugLogHelper.addDebugLog('CUSTOM_AUDIO: HTML5 recording saved to $audioPath');
    
    // Update UI state
    setState(() {
      _hasCustomAudio = true;
      _generateAudioFromText = false;
      _hasChanges = true; // Mark as changed for UI - this enables "Mark Modified" button
    });
    
    // Update stop data for backend
    widget.stopData['has_custom_audio'] = true;
    widget.stopData['audio_source'] = 'user_recorded';
    widget.stopData['generate_audio_from_text'] = false;
    widget.stopData['custom_audio_path'] = audioPath;
    widget.stopData['modified'] = true;
    widget.stopData['custom_audio_archived'] = true; // Mark as having archived audio
    
    await DebugLogHelper.addDebugLog('CUSTOM_AUDIO: HTML5 audio marked as ready for bulk save, hasChanges: $_hasChanges');
    
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('HTML5 recording ready! "Mark Modified" button is now enabled.'),
        backgroundColor: Colors.green,
        duration: Duration(seconds: 3),
      ),
    );
  }
  
  // Removed - HTML5 recording uses different upload method
  
  Future<void> _handleAudioUploadError(Map<String, dynamic> error) async {
    final errorType = error['error'] ?? 'UNKNOWN_ERROR';
    final errorMessage = error['message'] ?? 'Unknown error occurred';
    
    await DebugLogHelper.addDebugLog('AUDIO_UPLOAD_ERROR: $errorType - $errorMessage');
    
    switch (errorType) {
      case 'FILE_SIZE_EXCEEDED':
        await _showFileSizeDialog(error);
        break;
      case 'CONVERSION_FAILED':
        await _showConversionErrorDialog(error);
        break;
      case 'UNSUPPORTED_FORMAT':
        await _showFormatErrorDialog(error);
        break;
      default:
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Upload failed: $errorMessage'),
            backgroundColor: Colors.red,
            duration: Duration(seconds: 4),
          ),
        );
    }
  }
  
  Future<void> _showFileSizeDialog(Map<String, dynamic> error) async {
    final details = error['details'] ?? {};
    final currentSize = details['current_size_mb'] ?? 'Unknown';
    final maxSize = details['max_size_mb'] ?? '5';
    final adminContact = details['admin_contact'] ?? 'Contact administrator for increased limits';
    
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('File Too Large'),
        content: Text(
          'Audio file is ${currentSize}MB. Maximum allowed: ${maxSize}MB.\n\n$adminContact'
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('OK'),
          ),
        ],
      ),
    );
  }
  
  Future<void> _showConversionErrorDialog(Map<String, dynamic> error) async {
    final details = error['details'] ?? {};
    final sourceFormat = details['source_format'] ?? 'unknown';
    final errorReason = details['error_reason'] ?? 'Unknown conversion error';
    
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Audio Processing Failed'),
        content: Text(
          'Unable to process $sourceFormat audio file.\n\n$errorReason\n\nPlease try recording again.'
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('OK'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              _startNewRecording();
            },
            child: Text('Record Again'),
          ),
        ],
      ),
    );
  }
  
  Future<void> _showFormatErrorDialog(Map<String, dynamic> error) async {
    final details = error['details'] ?? {};
    final detectedFormat = details['detected_format'] ?? 'unknown';
    final supportedFormats = details['supported_formats'] ?? ['MP3', 'WAV', 'AAC'];
    final recommendation = details['recommendation'] ?? 'Please record in a supported format';
    
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Unsupported Audio Format'),
        content: Text(
          'Detected format: $detectedFormat\n\nSupported formats: ${supportedFormats.join(', ')}\n\n$recommendation'
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('OK'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              _startNewRecording();
            },
            child: Text('Record Again'),
          ),
        ],
      ),
    );
  }
  
  Future<void> _removeCustomAudio() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Remove Custom Audio'),
        content: Text('Remove your custom recording and restore AI-generated audio?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            style: ElevatedButton.styleFrom(backgroundColor: Colors.orange),
            child: Text('Remove', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
    
    if (confirmed == true) {
      setState(() {
        _isLoading = true;
        _progressMessage = 'Removing custom audio...';
      });
      
      try {
        final tourPath = widget.tourData['path'] as String;
        final tourId = tourPath.split('/').last;
        final stopNumber = widget.stopData['stop_number'];
        
        // For HTML5 recordings, just clear the data
        final success = true; // Always succeed for HTML5 cleanup
        
        if (success) {
          setState(() {
            _hasCustomAudio = false;
            _generateAudioFromText = true;
          });
          
          widget.stopData['has_custom_audio'] = false;
          widget.stopData['audio_source'] = 'tts_generated';
          widget.stopData['generate_audio_from_text'] = true;
          
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Custom audio removed. AI audio restored.'),
              backgroundColor: Colors.orange,
            ),
          );
        }
      } catch (e) {
        await DebugLogHelper.addDebugLog('CUSTOM_AUDIO: Remove error - $e');
      } finally {
        setState(() {
          _isLoading = false;
          _progressMessage = '';
        });
      }
    }
  }
  
  Future<void> _toggleAudioGeneration(bool value) async {
    setState(() {
      _generateAudioFromText = value;
    });
    
    widget.stopData['generate_audio_from_text'] = value;
    
    if (value && _hasCustomAudio) {
      // User wants to restore AI audio - confirm action
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text('Restore AI Audio'),
          content: Text('Replace custom recording with AI-generated audio from current text?'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: Text('Cancel'),
            ),
            ElevatedButton(
              onPressed: () => Navigator.pop(context, true),
              style: ElevatedButton.styleFrom(backgroundColor: Colors.blue),
              child: Text('Restore AI Audio', style: TextStyle(color: Colors.white)),
            ),
          ],
        ),
      );
      
      if (confirmed == true) {
        // Remove custom audio and restore AI generation
        setState(() {
          _hasCustomAudio = false;
        });
        
        widget.stopData['has_custom_audio'] = false;
        widget.stopData['audio_source'] = 'tts_generated';
        
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('AI audio will be generated from current text on save.'),
            backgroundColor: Colors.blue,
          ),
        );
      } else {
        // User cancelled - revert flag
        setState(() {
          _generateAudioFromText = false;
        });
        widget.stopData['generate_audio_from_text'] = false;
      }
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(value 
              ? 'Audio will be generated from text on save'
              : 'Current audio will be preserved on text changes'),
          backgroundColor: value ? Colors.blue : Colors.orange,
        ),
      );
    }
  }

  Future<void> _markAsModified() async {
    if (!_hasChanges && !_hasCustomAudio) {
      Navigator.pop(context);
      return;
    }

    try {
      // Check for conflicting settings: Auto Generate ON + Custom Audio
      if (_generateAudioFromText && _hasCustomAudio) {
        final confirmed = await _showAutoGenerateWarning();
        if (!confirmed) {
          return; // User cancelled
        }
        // Clear conflicting state - user chose to continue with TTS
        _hasCustomAudio = false;
        widget.stopData['custom_audio_path'] = null;
      }
      
      await DebugLogHelper.addDebugLog('EDIT: Marking stop ${widget.stopData['stop_number']} as modified');
      
      // Mark stop as modified
      widget.stopData['modified'] = true;
      widget.stopData['text'] = _textController.text;
      
      // Clean payload logic (no conflicts possible after warning dialog)
      if (_hasCustomAudio) {
        // Custom audio mode - preserve action='add' for new stops
        if (widget.stopData['action'] != 'add') {
          widget.stopData['action'] = 'modify';
        }
        widget.stopData['generate_audio_from_text'] = false;
        widget.stopData['has_custom_audio'] = true;
        widget.stopData['audio_source'] = 'user_recorded';
        await DebugLogHelper.addDebugLog('EDIT: Custom audio mode - using recorded audio, action preserved: ${widget.stopData['action']}');
      } else {
        // TTS mode - generate only if text changed
        if (_hasChanges) {
          // Preserve action='add' for new stops
          if (widget.stopData['action'] != 'add') {
            widget.stopData['action'] = 'modify';
          }
          widget.stopData['generate_audio_from_text'] = _generateAudioFromText;
        } else {
          // No changes - preserve action for new stops
          if (widget.stopData['action'] != 'add') {
            widget.stopData['action'] = 'unchanged';
          }
          widget.stopData['generate_audio_from_text'] = false; // Preserve existing
        }
        widget.stopData['has_custom_audio'] = false;
        widget.stopData['audio_source'] = 'tts_generated';
        await DebugLogHelper.addDebugLog('EDIT: TTS mode - text changed: $_hasChanges, will generate: ${widget.stopData['generate_audio_from_text']}, action preserved: ${widget.stopData['action']}');
      }
      
      String changeType = _getChangeDescription();
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Stop marked as modified ($changeType). Use "Save All Changes" to commit.'),
          backgroundColor: Colors.orange,
        ),
      );
      
      Navigator.pop(context, true);
    } catch (e) {
      await DebugLogHelper.addDebugLog('EDIT: Error marking stop: $e');
    }
  }
  
  Future<bool> _showAutoGenerateWarning() async {
    return await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Row(
          children: [
            Icon(Icons.warning, color: Colors.orange),
            SizedBox(width: 8),
            Text('Auto Generate Mode Conflict'),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'You have both:',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 8),
            Text('• Auto Generate Mode: ON'),
            Text('• Custom audio recording'),
            Text('• Text changes'),
            SizedBox(height: 12),
            Container(
              padding: EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Colors.orange.shade50,
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                'Your custom recording will be IGNORED and audio will be regenerated from the new text.',
                style: TextStyle(
                  color: Colors.orange.shade800,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
            SizedBox(height: 8),
            Text('To keep your custom recording, turn OFF Auto Generate Mode first.'),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            style: ElevatedButton.styleFrom(backgroundColor: Colors.orange),
            child: Text('Continue (Ignore Recording)', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    ) ?? false;
  }
  
  String _getChangeDescription() {
    if (_generateAudioFromText) {
      if (_hasChanges && _hasCustomAudio) {
        return 'text (custom audio ignored)';
      } else if (_hasChanges) {
        return 'text (audio will be regenerated)';
      } else {
        return 'audio regeneration';
      }
    } else {
      if (_hasChanges && _hasCustomAudio) {
        return 'text and custom audio';
      } else if (_hasChanges) {
        return 'text (audio preserved)';
      } else if (_hasCustomAudio) {
        return 'custom audio';
      }
    }
    return 'changes';
  }
  
  Future<void> _saveChanges_REMOVED() async {
    if (!_hasChanges) {
      Navigator.pop(context);
      return;
    }

    setState(() {
      _isLoading = true;
    });

    try {
      await DebugLogHelper.addDebugLog('EDIT: Saving changes for stop ${widget.stopData['stop_number']}');
      
      // Extract tour ID from path
      final tourPath = widget.tourData['path'] as String;
      final tourId = tourPath.split('/').last;
      
      // Check if we have a title to construct proper directory name
      String backendTourId = tourId;
      if (widget.tourData['title'] != null) {
        final title = widget.tourData['title'] as String;
        // Convert title to backend format: lowercase, spaces to underscores, remove special chars
        final cleanTitle = title.toLowerCase()
            .replaceAll(RegExp(r'[^a-z0-9\s]'), '')
            .replaceAll(RegExp(r'\s+'), '_');
        // Extract UUID from path
        final uuid = tourId.replaceAll(RegExp(r'^.*_'), '');
        backendTourId = '${cleanTitle}_$uuid';
      }
      
      await DebugLogHelper.addDebugLog('EDIT: Tour path: $tourPath');
      await DebugLogHelper.addDebugLog('EDIT: Extracted UUID: $tourId');
      await DebugLogHelper.addDebugLog('EDIT: Backend tour ID: $backendTourId');
      await DebugLogHelper.addDebugLog('EDIT: Tour data keys: ${widget.tourData.keys.toList()}');
      
      // Call backend to update stop
      final result = await TourEditingService.updateStop(
        tourId: backendTourId,
        stopNumber: widget.stopData['stop_number'],
        newText: _textController.text,
      );
      
      // Update progress and log
      setState(() {
        _progressMessage = 'Text saved. Generating audio...';
      });
      await DebugLogHelper.addDebugLog('EDIT: Text saved, audio generation job: ${result['job_id']}');
      
      // Track audio generation and refresh tour data
      if (result['job_id'] != null) {
        await _trackAudioGenerationAndRefresh(backendTourId, result['job_id']);
      } else {
        await _refreshTourData();
        _showCompletionMessage('Changes saved successfully!');
      }
      
      Navigator.pop(context, true); // Return true to indicate changes were made
    } catch (e) {
      await DebugLogHelper.addDebugLog('EDIT: Error saving changes: $e');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error saving: $e'),
          backgroundColor: Colors.red,
        ),
      );
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }
  
  Future<void> _trackAudioGenerationAndRefresh(String tourId, String jobId) async {
    try {
      await DebugLogHelper.addDebugLog('EDIT: Tracking audio generation job $jobId');
      
      // Check job status periodically with progress updates (reduced to 15 checks)
      for (int i = 0; i < 15; i++) {
        await Future.delayed(Duration(seconds: 2));
        
        if (mounted) {
          setState(() {
            _progressMessage = 'Generating audio... (${i * 2}s)';
          });
        }
        
        final status = await TourEditingService.checkJobStatus(
          tourId: tourId,
          jobId: jobId,
        );
        
        await DebugLogHelper.addDebugLog('EDIT: Job status check ${i + 1}: ${status['status']}');
        
        if (status['status'] == 'completed') {
          await DebugLogHelper.addDebugLog('EDIT: Audio generation completed successfully');
          if (mounted) {
            setState(() {
              _progressMessage = 'Audio generated. Refreshing tour...';
            });
          }
          await _refreshTourData();
          _showCompletionMessage('Tour updated successfully!');
          // Return to tour editing screen after success
          if (mounted) {
            Navigator.pop(context, true);
          }
          return; // Exit function after success
        } else if (status['status'] == 'failed' || status['status'] == 'error') {
          final errorMsg = status['error'] ?? status['message'] ?? 'Unknown error';
          await DebugLogHelper.addDebugLog('EDIT: Audio generation failed: $errorMsg');
          _showCompletionMessage('Audio generation failed: $errorMsg', isError: true);
          // Return to tour editing screen even on error
          Navigator.pop(context, true);
          return; // Exit function after error
        }
      }
      
      // If we reach here, audio generation timed out
      await DebugLogHelper.addDebugLog('EDIT: Audio generation timed out after 30 seconds');
      _showCompletionMessage('Audio generation is taking longer than expected. Text saved successfully.', isError: false);
      Navigator.pop(context, true);
      
    } catch (e) {
      await DebugLogHelper.addDebugLog('EDIT: Error tracking audio generation: $e');
      _showCompletionMessage('Update error: $e', isError: true);
      Navigator.pop(context, true);
    }
  }
  
  void _showCompletionMessage(String message, {bool isError = false}) {
    if (mounted) {
      setState(() {
        _progressMessage = '';
      });
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(message),
          backgroundColor: isError ? Colors.red : Colors.green,
          duration: Duration(seconds: 3),
        ),
      );
    }
  }
  
  Future<void> _invalidateWebViewCache() async {
    try {
      await DebugLogHelper.addDebugLog('EDIT: Invalidating WebView cache for updated audio');
      
      // Note: WebView cache invalidation would need to be implemented
      // in the voice control service or tour playback system
      // This is a placeholder for the cache invalidation logic
      
      await DebugLogHelper.addDebugLog('EDIT: WebView cache invalidation requested');
    } catch (e) {
      await DebugLogHelper.addDebugLog('EDIT: Error invalidating WebView cache: $e');
    }
  }
  
  Future<void> _refreshTourData() async {
    try {
      await DebugLogHelper.addDebugLog('EDIT: Refreshing tour data after save');
      
      // Re-read the text file to get updated content
      final tourPath = widget.tourData['path'];
      final stopNumber = widget.stopData['stop_number'];
      final textFile = File('$tourPath/audio_$stopNumber.txt');
      
      if (await textFile.exists()) {
        final updatedText = await textFile.readAsString();
        
        // Update the stop data with new content
        widget.stopData['text'] = updatedText.trim();
        widget.stopData['original_text'] = updatedText.trim(); // Reset original text
        widget.stopData['modified'] = false; // Mark as no longer modified
        
        // Update the text controller to show new content
        if (mounted) {
          setState(() {
            _textController.text = updatedText.trim();
            _hasChanges = false;
          });
        }
        
        await DebugLogHelper.addDebugLog('EDIT: Tour data refreshed - text: ${updatedText.substring(0, 50)}...');
      } else {
        await DebugLogHelper.addDebugLog('EDIT: Text file not found: $textFile');
      }
      
      // Also check if audio file was updated
      final audioFile = File('$tourPath/audio_$stopNumber.mp3');
      if (await audioFile.exists()) {
        final audioStats = await audioFile.stat();
        await DebugLogHelper.addDebugLog('EDIT: Audio file updated - size: ${audioStats.size} bytes, modified: ${audioStats.modified}');
      }
      
      await DebugLogHelper.addDebugLog('EDIT: Tour refresh completed successfully');
      
      // Force WebView cache invalidation for updated audio
      await _invalidateWebViewCache();
    } catch (e) {
      await DebugLogHelper.addDebugLog('EDIT: Error refreshing tour data: $e');
    }
  }

  Future<void> _deleteStop() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Delete Stop'),
        content: Text('Are you sure you want to delete this stop? This action cannot be undone.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
            child: Text('Delete', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      widget.stopData['action'] = 'delete';
      
      DebugLogHelper.addDebugLog('USER_ACTION: Marked stop ${widget.stopData['stop_number']} for deletion');
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Stop marked for deletion. Use "Save All Changes" to apply.'),
          backgroundColor: Colors.red,
        ),
      );
      
      Navigator.pop(context, true);
    }
  }
  
  Future<void> _resetToOriginal() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Reset to Original'),
        content: Text('Reset this stop to its original content?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text('Reset', style: TextStyle(color: Colors.orange)),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      setState(() {
        _textController.text = widget.stopData['text'];
        _hasChanges = false;
      });
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Reset to original content'),
          backgroundColor: Colors.orange,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Edit ${widget.stopData['title']}'),
        backgroundColor: Color(0xFF2c3e50),
        foregroundColor: Colors.white,
        actions: [
          if (_hasChanges)
            IconButton(
              icon: Icon(Icons.refresh),
              onPressed: _resetToOriginal,
              tooltip: 'Reset to Original',
            ),
          IconButton(
            icon: Icon(Icons.delete, color: Colors.red),
            onPressed: _deleteStop,
            tooltip: 'Delete Stop',
          ),
        ],
      ),
      body: _isLoading
          ? Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  CircularProgressIndicator(),
                  if (_progressMessage.isNotEmpty) ...[
                    SizedBox(height: 16),
                    Text(
                      _progressMessage,
                      style: TextStyle(fontSize: 16, color: Colors.grey[600]),
                    ),
                  ]
                ],
              ),
            )
          : SingleChildScrollView(
              padding: EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Text Content Section
                  Card(
                    child: Padding(
                      padding: EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Icon(Icons.text_fields, color: Color(0xFF3498db)),
                              SizedBox(width: 8),
                              Text(
                                'TEXT CONTENT',
                                style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.bold,
                                  color: Color(0xFF2c3e50),
                                ),
                              ),
                            ],
                          ),
                          SizedBox(height: 16),
                          TextField(
                            controller: _textController,
                            maxLines: 8,
                            decoration: InputDecoration(
                              hintText: 'Enter the content for this stop...',
                              border: OutlineInputBorder(),
                              helperText: _generateAudioFromText 
                                  ? 'This text will be converted to speech (Auto Generation is ON)'
                                  : 'This text will NOT be converted to speech (Auto Generation is OFF)',
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  
                  SizedBox(height: 16),
                  
                  // Audio Section
                  Card(
                    child: Padding(
                      padding: EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Icon(
                                _hasCustomAudio ? Icons.mic : Icons.audiotrack,
                                color: _hasCustomAudio ? Colors.green : Color(0xFF27ae60),
                              ),
                              SizedBox(width: 8),
                              Text(
                                'AUDIO EDITING: Multi-Part Recording',
                                style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.bold,
                                  color: Color(0xFF2c3e50),
                                ),
                              ),
                              if (_hasCustomAudio)
                                Container(
                                  margin: EdgeInsets.only(left: 8),
                                  padding: EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                  decoration: BoxDecoration(
                                    color: Colors.green,
                                    borderRadius: BorderRadius.circular(10),
                                  ),
                                  child: Text(
                                    '🎤',
                                    style: TextStyle(fontSize: 12, color: Colors.white),
                                  ),
                                ),
                            ],
                          ),
                          SizedBox(height: 16),
                          
                          // Unified Audio Editing Interface - always show for all stops
                          if (true) // Show audio interface for all stops including new ones
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                // Audio Source Dropdown with New Button
                                Row(
                                  children: [
                                    Expanded(
                                      child: Container(
                                        padding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                        decoration: BoxDecoration(
                                          border: Border.all(color: Colors.grey.shade300),
                                          borderRadius: BorderRadius.circular(8),
                                        ),
                                        child: DropdownButton<String>(
                                          value: _selectedAudioSource,
                                          isExpanded: true,
                                          underline: SizedBox(),
                                          items: widget.stopData['action'] == 'add' ? _buildNewStopAudioItems() : _buildAudioSourceItems(),
                                          onChanged: _isRecordingNew ? null : (value) {
                                            if (value != null) {
                                              setState(() {
                                                _selectedAudioSource = value;
                                              });
                                              _loadSelectedAudio();
                                              DebugLogHelper.addDebugLog('DROPDOWN: Selected $value');
                                            }
                                          },
                                        ),
                                      ),
                                    ),
                                    SizedBox(width: 8),
                                    ElevatedButton(
                                      onPressed: _isRecording ? _stopRecording : (_isRecordingNew ? null : _startNewRecording),
                                      style: ElevatedButton.styleFrom(
                                        backgroundColor: _isRecording ? Colors.red : Colors.blue,
                                        foregroundColor: Colors.white,
                                      ),
                                      child: Text(_isRecording ? 'Stop Recording' : 'New'),
                                    ),
                                    SizedBox(width: 8),
                                    ElevatedButton(
                                      onPressed: _isRecordingNew ? null : _uploadAudioFile,
                                      style: ElevatedButton.styleFrom(
                                        backgroundColor: Colors.green,
                                        foregroundColor: Colors.white,
                                      ),
                                      child: Text('Upload'),
                                    ),
                                  ],
                                ),
                                SizedBox(height: 12),
                                
                                // Recording Status (only when recording)
                                if (_isRecording) ...[
                                  Container(
                                    padding: EdgeInsets.all(12),
                                    decoration: BoxDecoration(
                                      color: Colors.red.shade50,
                                      borderRadius: BorderRadius.circular(8),
                                      border: Border.all(color: Colors.red.shade200),
                                    ),
                                    child: Row(
                                      children: [
                                        Icon(Icons.fiber_manual_record, color: Colors.red, size: 16),
                                        SizedBox(width: 8),
                                        Text(
                                          'Recording... ${_recordingDuration}s',
                                          style: TextStyle(
                                            color: Colors.red.shade800,
                                            fontWeight: FontWeight.bold,
                                          ),
                                        ),
                                        Spacer(),
                                        if (_isPausedRecording)
                                          ElevatedButton(
                                            onPressed: _resumeRecording,
                                            style: ElevatedButton.styleFrom(
                                              backgroundColor: Colors.green,
                                              foregroundColor: Colors.white,
                                            ),
                                            child: Text('Resume'),
                                          )
                                        else
                                          ElevatedButton(
                                            onPressed: _pauseRecording,
                                            style: ElevatedButton.styleFrom(
                                              backgroundColor: Colors.orange,
                                              foregroundColor: Colors.white,
                                            ),
                                            child: Text('Pause'),
                                          ),
                                      ],
                                    ),
                                  ),
                                  SizedBox(height: 12),
                                ],
                                
                                // Audio Player
                                Container(
                                  height: 200,
                                  decoration: BoxDecoration(
                                    color: _isRecordingNew ? Colors.grey.shade200 : 
                                           (_selectedAudioSource == 'no_original' ? Colors.grey.shade300 : Colors.grey.shade100),
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  child: _isRecordingNew 
                                      ? Center(
                                          child: Column(
                                            mainAxisAlignment: MainAxisAlignment.center,
                                            children: [
                                              Icon(Icons.mic, size: 48, color: Colors.grey.shade500),
                                              SizedBox(height: 8),
                                              Text(
                                                'Audio player disabled during recording',
                                                style: TextStyle(color: Colors.grey.shade600),
                                              ),
                                            ],
                                          ),
                                        )
                                      : (_selectedAudioSource == 'no_original' || (widget.stopData['action'] == 'add' && _selectedAudioSource == 'no_original'))
                                          ? Container(
                                              decoration: BoxDecoration(
                                                color: Colors.grey.shade300,
                                                borderRadius: BorderRadius.circular(8),
                                              ),
                                              child: Center(
                                                child: Column(
                                                  mainAxisAlignment: MainAxisAlignment.center,
                                                  children: [
                                                    Icon(Icons.volume_off, size: 48, color: Colors.grey.shade500),
                                                    SizedBox(height: 8),
                                                    Text(
                                                      'No Original Audio Available',
                                                      style: TextStyle(color: Colors.grey.shade600, fontWeight: FontWeight.bold),
                                                    ),
                                                    SizedBox(height: 4),
                                                    Text(
                                                      'Record custom audio or select existing recording',
                                                      style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
                                                    ),
                                                  ],
                                                ),
                                              ),
                                            )
                                          : InAppWebView(
                                          initialSettings: InAppWebViewSettings(
                                            mediaPlaybackRequiresUserGesture: false,
                                            allowsInlineMediaPlayback: true,
                                            javaScriptEnabled: true,
                                          ),
                                          onWebViewCreated: (controller) async {
                                            _audioWebViewController = controller;
                                            await _loadSelectedAudio();
                                          },
                                          onLoadStop: (controller, url) async {
                                            // Force immediate metadata loading and duration display
                                            await Future.delayed(Duration(milliseconds: 500));
                                            await controller.evaluateJavascript(source: """
                                              const audio = document.getElementById('audioPlayer');
                                              if (audio) {
                                                audio.addEventListener('loadedmetadata', function() {
                                                  console.log('Metadata loaded, duration:', this.duration);
                                                  updatePosition();
                                                });
                                                audio.addEventListener('canplay', function() {
                                                  console.log('Can play, forcing position update');
                                                  updatePosition();
                                                });
                                                // Force load and update
                                                audio.load();
                                                setTimeout(() => {
                                                  if (audio.readyState >= 1) {
                                                    updatePosition();
                                                  }
                                                }, 1000);
                                              }
                                            """);
                                          },
                                        ),
                                ),
                                
                                SizedBox(height: 12),
                                
                                // Context-Sensitive Action Buttons
                                if (!_isRecording && !_isRecordingNew && _selectedAudioSource.startsWith('part_')) ...[
                                  Row(
                                    children: [
                                      Expanded(
                                        child: OutlinedButton.icon(
                                          onPressed: _reRecordPart,
                                          icon: Icon(Icons.mic),
                                          label: Text('Re-Record'),
                                          style: OutlinedButton.styleFrom(
                                            side: BorderSide(color: Colors.blue),
                                            foregroundColor: Colors.blue,
                                          ),
                                        ),
                                      ),
                                      SizedBox(width: 8),
                                      Expanded(
                                        child: OutlinedButton.icon(
                                          onPressed: _deletePart,
                                          icon: Icon(Icons.delete),
                                          label: Text('Delete'),
                                          style: OutlinedButton.styleFrom(
                                            side: BorderSide(color: Colors.red),
                                            foregroundColor: Colors.red,
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                ],
                              ],
                            ),
                          
                          SizedBox(height: 16),
                          
                          // Hidden HTML5 Recorder (background only)
                          if (!_hasCustomAudio)
                            Container(
                              height: 0,
                              child: InAppWebView(
                                initialSettings: InAppWebViewSettings(
                                  mediaPlaybackRequiresUserGesture: false,
                                  allowsInlineMediaPlayback: true,
                                  javaScriptEnabled: true,
                                ),
                                onWebViewCreated: (controller) async {
                                  _recorderWebViewController = controller;
                                  await _htmlRecorder.initialize(controller);
                                },
                                onPermissionRequest: (controller, request) async {
                                  return PermissionResponse(
                                    resources: request.resources,
                                    action: PermissionResponseAction.GRANT,
                                  );
                                },
                              ),
                            ),
                          
                          if (!_hasCustomAudio) SizedBox(height: 16),
                          
                          // Custom Audio Recording Section
                          Container(
                            padding: EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: _hasCustomAudio ? Colors.green.shade50 : Colors.orange.shade50,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Column(
                              children: [
                                Row(
                                  children: [
                                    Icon(
                                      _hasCustomAudio ? Icons.mic : Icons.mic_none,
                                      color: _hasCustomAudio ? Colors.green.shade700 : Colors.orange.shade700,
                                    ),
                                    SizedBox(width: 8),
                                    Expanded(
                                      child: Text(
                                        _hasCustomAudio 
                                            ? 'Custom audio active'
                                            : 'Record or upload audio for this stop',
                                        style: TextStyle(
                                          color: _hasCustomAudio ? Colors.green.shade800 : Colors.orange.shade800,
                                          fontWeight: FontWeight.bold,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                                
                                if (!_hasCustomAudio) ...[
                                  SizedBox(height: 12),
                                  Text(
                                    'Record audio in parts or upload professional recordings (MP3, WAV, AAC). Parts will be concatenated into one custom recording.',
                                    style: TextStyle(
                                      color: Colors.blue.shade700,
                                      fontSize: 14,
                                    ),
                                  ),
                                  SizedBox(height: 12),
                                  ElevatedButton.icon(
                                    onPressed: _recordingParts.isNotEmpty ? _useMultiPartRecording : null,
                                    icon: Icon(Icons.check),
                                    label: Text(_recordingParts.isNotEmpty ? 'Use Custom Recording (${_recordingParts.length} parts)' : 'Record Parts First'),
                                    style: ElevatedButton.styleFrom(
                                      backgroundColor: _recordingParts.isNotEmpty ? Colors.green : Colors.grey,
                                      foregroundColor: Colors.white,
                                    ),
                                  ),
                                ],
                                
                                if (_hasCustomAudio) ...[
                                  SizedBox(height: 12),
                                  Row(
                                    children: [
                                      Expanded(
                                        child: OutlinedButton.icon(
                                          onPressed: _removeCustomAudio,
                                          icon: Icon(Icons.delete_outline),
                                          label: Text('Remove Custom Audio'),
                                          style: OutlinedButton.styleFrom(
                                            side: BorderSide(color: Colors.orange),
                                            foregroundColor: Colors.orange,
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                ],
                              ],
                            ),
                          ),
                          
                          SizedBox(height: 16),
                          
                          // Audio Generation Info
                          if (!_hasCustomAudio)
                            Container(
                              padding: EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: Colors.blue.shade50,
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Row(
                                children: [
                                  Icon(Icons.info, color: Colors.blue.shade700),
                                  SizedBox(width: 8),
                                  Expanded(
                                    child: Text(
                                      'Audio will be automatically generated from your text using AI voice synthesis.',
                                      style: TextStyle(color: Colors.blue.shade800),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          
                          // Audio Generation Flag Toggle
                          Container(
                            padding: EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: _generateAudioFromText ? Colors.blue.shade50 : Colors.orange.shade50,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Column(
                              children: [
                                Row(
                                  children: [
                                    Icon(
                                      _generateAudioFromText ? Icons.auto_awesome : Icons.lock,
                                      color: _generateAudioFromText ? Colors.blue.shade700 : Colors.orange.shade700,
                                    ),
                                    SizedBox(width: 8),
                                    Expanded(
                                      child: Text(
                                        'Audio Generation Mode',
                                        style: TextStyle(
                                          fontWeight: FontWeight.bold,
                                          color: _generateAudioFromText ? Colors.blue.shade800 : Colors.orange.shade800,
                                        ),
                                      ),
                                    ),
                                    Switch(
                                      value: _generateAudioFromText,
                                      onChanged: _toggleAudioGeneration,
                                    ),
                                  ],
                                ),
                                SizedBox(height: 8),
                                Text(
                                  _generateAudioFromText 
                                      ? 'Generate Audio from Text: Audio will be regenerated when text changes'
                                      : 'Keep the Audio as is: Text changes will not affect audio',
                                  style: TextStyle(
                                    color: _generateAudioFromText ? Colors.blue.shade700 : Colors.orange.shade700,
                                    fontSize: 12,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          
                          SizedBox(height: 16),
                          
                          // Text-Audio Mismatch Warning - only show when BOTH conditions are true
                          if (!_generateAudioFromText && _hasChanges && _textController.text != widget.stopData['original_text'])
                            Container(
                              padding: EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: Colors.amber.shade50,
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Row(
                                children: [
                                  Icon(Icons.warning, color: Colors.amber.shade700),
                                  SizedBox(width: 8),
                                  Expanded(
                                    child: Text(
                                      'Warning: Text modified but audio will not be regenerated. To regenerate audio from text, change flag to "Generate Audio from Text".',
                                      style: TextStyle(color: Colors.amber.shade800),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                        ],
                      ),
                    ),
                  ),
                  
                  SizedBox(height: 24),
                  
                  // Action Buttons
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton(
                          onPressed: () => Navigator.pop(context),
                          child: Text('Cancel'),
                        ),
                      ),
                      SizedBox(width: 8),
                      Expanded(
                        child: OutlinedButton(
                          onPressed: _deleteStop,
                          style: OutlinedButton.styleFrom(
                            side: BorderSide(color: Colors.red),
                          ),
                          child: Text('Delete', style: TextStyle(color: Colors.red)),
                        ),
                      ),
                      SizedBox(width: 8),
                      Expanded(
                        child: ElevatedButton(
                          onPressed: (_hasChanges || _hasCustomAudio) ? _markAsModified : null,
                          child: Text((_hasChanges || _hasCustomAudio) ? 'Mark Modified' : 'No Changes'),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
    );
  }
}