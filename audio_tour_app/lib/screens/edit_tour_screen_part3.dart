  
  Future<void> _updateLocalTourId(String newTourId) async {
    try {
      await DebugLogHelper.addDebugLog('DEBUG_UPDATE_ID: Starting _updateLocalTourId with newTourId: $newTourId');
      
      final tourPath = widget.tourData['path'] as String;
      final prefs = await SharedPreferences.getInstance();
      final savedTours = prefs.getStringList('saved_tours') ?? [];
      
      for (int i = 0; i < savedTours.length; i++) {
        final tourDataJson = savedTours[i];
        if (tourDataJson.isNotEmpty) {
          try {
            final tourData = jsonDecode(tourDataJson) as Map<String, dynamic>;
            if (tourData['path'] == tourPath) {
              tourData['new_tour_id'] = newTourId;
              savedTours[i] = jsonEncode(tourData);
              break;
            }
          } catch (jsonError) {
            continue;
          }
        }
      }
      
      await prefs.setStringList('saved_tours', savedTours);
      await DebugLogHelper.addDebugLog('DEBUG_UPDATE_ID: Local tour updated with new ID reference');
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
          duration: Duration(seconds: 3),
        ),
      );
    }
  }
  
  void _navigateToListenPage() {
    if (mounted) {
      Navigator.pop(context);
    }
  }
  
  void _updateUIIndicators() {
    setState(() {});
  }
  
  List<Map<String, dynamic>> _prepareStopsForBackend(List<Map<String, dynamic>> stops) {
    final cleanedStops = <Map<String, dynamic>>[];
    
    DebugLogHelper.addDebugLog('EDIT: Preparing ${stops.length} stops for backend');
    
    for (final stop in stops) {
      final cleanedStop = Map<String, dynamic>.from(stop);
      
      if (stop['action'] == 'delete') {
        cleanedStop['modified'] = false;
        cleanedStop['action'] = 'delete';
      } else if (stop['action'] == 'add' && (stop['original_text'] == null || stop['original_text'].isEmpty)) {
        cleanedStop['original_text'] = '';
        cleanedStop['action'] = 'add';
      } else if (stop['modified'] == true) {
        if (stop['original_text'] == null || stop['original_text'].isEmpty) {
          cleanedStop['original_text'] = '';
          cleanedStop['action'] = 'add';
        } else {
          cleanedStop['action'] = 'modify';
        }
      } else {
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
      DebugLogHelper.addDebugLog('CRITICAL_ADD: Added new stop $newStopNumber with action=add, modified=true');
      
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
        if (_stops[i]['action'] != 'add') {
          _stops[i]['action'] = 'unchanged';
        }
        _stops[i]['moved'] = true;
      }
    }
    
    DebugLogHelper.addDebugLog('EDIT: Reordered stops: moved $oldIndex to $newIndex');
    _updateUIIndicators();
  }