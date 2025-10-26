  
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
            duration: Duration(seconds: 4),
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
      
      DebugLogHelper.addDebugLog('CRITICAL_TOUR_ID: tourPath=$tourPath');
      DebugLogHelper.addDebugLog('CRITICAL_TOUR_ID: extracted tourId=$tourId');
      DebugLogHelper.addDebugLog('CRITICAL_TOUR_ID: sending to backend=$backendTourId');
      
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
            duration: Duration(seconds: 2),
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
          duration: Duration(seconds: 6),
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
        await _updateLocalTourId(newTourId);
        
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
      DebugLogHelper.addDebugLog('DEBUG_RESET: Processing ${_stops.length} stops');
      
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
      DebugLogHelper.addDebugLog('DEBUG_RESET: Error in _resetAllModifiedFlags: $e');
    }
  }