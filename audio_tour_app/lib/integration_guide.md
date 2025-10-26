# Tour Status Update Integration Guide

## Overview
This guide explains how to integrate the `TourStatusService` to fix the issue where tour status is not being updated in the database.

## Problem
Tours are being generated successfully, but their status remains "started" in the database instead of changing to "completed" when finished.

## Solution
The `TourStatusService` class provides two key methods:
1. `trackTourRequest()` - Creates a tour request and stores its ID
2. `updateTourStatus()` - Updates a tour's status using the stored ID

## Integration Steps

### 1. Import the Service
Add this import to the top of `main.dart`:

```dart
import 'tour_status_service.dart';
```

### 2. Update Foreground Tour Generation
In the `_TourGeneratorScreenState` class, modify the `_generateTour()` method:

```dart
Future<void> _generateTour() async {
  // ... existing code ...
  
  // Step 1: Start tour generation
  final response = await http.post(
    Uri.parse('$_apiBaseUrl/generate-complete-tour'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode(tourData),
  );

  if (response.statusCode != 200) {
    throw Exception('Failed to start tour generation');
  }

  Map<String, dynamic> result = jsonDecode(response.body);
  String jobId = result['job_id'];
  
  // Track the tour request and get the tour_id
  await TourStatusService.trackTourRequest(_tourRequestController.text, jobId);
  
  // Step 2: Poll for completion and auto-download
  await _pollAndAutoDownload(jobId, tourData['location']);
}
```

### 3. Replace Status Update Method
Replace the `_updateTourRequestStatus()` method:

```dart
Future<void> _updateTourRequestStatus(String jobId, String status) async {
  await TourStatusService.updateTourStatus(jobId, status);
}
```

### 4. Update Background Tour Generation
In the `_TourGeneratorScreenState` class, modify the `_generateTourBackground()` method:

```dart
Future<void> _generateTourBackground() async {
  // ... existing code ...
  
  final response = await http.post(
    Uri.parse('$_apiBaseUrl/generate-complete-tour'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode(tourData),
  );

  if (response.statusCode != 200) {
    throw Exception('Failed to start tour generation');
  }

  Map<String, dynamic> result = jsonDecode(response.body);
  String jobId = result['job_id'];
  
  // Track the tour request and get the tour_id
  await TourStatusService.trackTourRequest(_tourRequestController.text, jobId);
  
  // ... rest of the code ...
}
```

### 5. Replace Background Status Update Method
In the `_MainScreenState` class, replace the `_updateBackgroundTourStatus()` method:

```dart
Future<void> _updateBackgroundTourStatus(String jobId, String status) async {
  await TourStatusService.updateTourStatus(jobId, status);
}
```

## Testing
After implementing these changes:
1. Generate a tour in the foreground
2. Generate a tour in the background
3. Check the database to verify that both tours' status is updated to "completed"

## Troubleshooting
If status updates still don't work:
1. Check the logs for any errors
2. Verify that the tour_id is being stored correctly
3. Confirm that the user_id is correct
4. Make sure the server IP is configured properly