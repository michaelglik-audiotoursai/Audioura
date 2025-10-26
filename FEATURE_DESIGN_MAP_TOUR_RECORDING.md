# Audio Tour Recording Feature - Design Document
**Version**: 1.0  
**Target Release**: Post v1.2.6+396  
**Status**: Design Complete - Ready for Implementation  

## Overview
Allow users to create tours by pointing stops on a map instead of describing them in text, then generate AI-powered descriptions for each stop.

## User Flow

### 1. Entry Point
- **Generate Page**: Add "Point Stops on Map" button (Tours mode only)
- **Validation**: Requires number of stops to be set first

### 2. Map Selection Process
- **New Screen**: `MapStopSelectorScreen` 
- **Base**: Reuse existing Home page map component
- **Interaction**: Tap map → Enter stop name → Add numbered marker
- **Limit**: Up to specified number of stops from Generate page
- **Return**: List of coordinates + names back to Generate page

### 3. Tour Generation
- **Display**: Show selected stops list on Generate page
- **Generate**: Use new coordinate-based service instead of text-based
- **Result**: Standard tour HTML format → Listen page → Edit as normal

## Technical Implementation

### Frontend Changes

#### 1. Modified Generate Page (`tour_generator_screen.dart`)
```dart
// Add to state
List<Map<String, dynamic>> _selectedStops = [];

// Add button (Tours mode only)
ElevatedButton.icon(
  onPressed: _openMapStopSelector,
  icon: Icon(Icons.map),
  label: Text('Point Stops on Map'),
)

// Show selected stops list
if (_selectedStops.isNotEmpty) {
  // Display numbered list of stop names
}
```

#### 2. New Map Selector Screen (`map_stop_selector_screen.dart`)
```dart
class MapStopSelectorScreen extends StatefulWidget {
  final int maxStops;
  final List<Map<String, dynamic>> existingStops;
}

// Features:
// - Flutter map with tap-to-add stops
// - Stop name input dialog on tap
// - Numbered markers (1, 2, 3...)
// - Clear/undo functionality
// - Return coordinates + names
```

#### 3. Stop Data Structure
```dart
{
  'name': 'Museum of Fine Arts',
  'latitude': 42.3398,
  'longitude': -71.0942,
  'order': 1
}
```

### Backend Changes

#### 1. New Service (`coordinate_tour_generator_service.py`)
```python
# Endpoint: /generate-tour-from-coordinates
# Input: {
#   'stops': [{'name': str, 'lat': float, 'lng': float, 'order': int}],
#   'tour_description': str,
#   'total_stops': int
# }
# 
# Process:
# 1. For each stop: Generate description using name + coordinates
# 2. Generate route/directions between consecutive stops  
# 3. Create standard tour HTML format
# 4. Return job_id for polling
```

#### 2. Modified Tour Orchestrator (`tour_orchestrator_service.py`)
```python
# Add new endpoint route
@app.route('/generate-tour-from-coordinates', methods=['POST'])
def generate_coordinate_tour():
    # Route to coordinate_tour_generator_service
    # Return job_id for standard polling workflow
```

#### 3. OpenAI Integration
```python
# For each stop:
prompt = f"""
Generate a 2-3 minute audio tour stop description for:
Location: {stop_name}
Coordinates: {latitude}, {longitude}
Context: This is stop {order} of {total_stops} in a tour

Include:
1. Welcome/orientation (30 seconds)
2. Main description (90-120 seconds) 
3. Directions to next stop (30 seconds)
"""
```

## Data Flow

### 1. Map Selection Flow
```
Generate Page → MapStopSelector → User taps map → 
Name input dialog → Add to stops list → Return to Generate
```

### 2. Generation Flow  
```
Generate button → coordinate_tour_generator_service → 
OpenAI API calls → Standard tour HTML → Listen page
```

### 3. Editing Flow
```
Listen page → Edit button → Existing tour editing system
(No changes to editing - works exactly as current tours)
```

## UI Components

### 1. Generate Page Additions
- **Button**: "Point Stops on Map" (purple, map icon)
- **List**: Selected stops display with numbers
- **Validation**: Ensure stops ≤ specified number

### 2. Map Selector Screen
- **Map**: Flutter map (reuse Home page component)
- **Markers**: Numbered circles (1, 2, 3...)
- **Dialog**: Stop name input on tap
- **Controls**: Done/Cancel buttons
- **Optional**: Connecting lines between stops

### 3. Stop Name Input Dialog
```dart
AlertDialog(
  title: Text('Name this stop'),
  content: TextField(
    hintText: 'e.g., Museum of Fine Arts, Boston'
  ),
  actions: [Cancel, Add]
)
```

## Integration Points

### 1. Existing Systems
- **Map Component**: Reuse from Home page
- **Tour Generation**: Same polling/download workflow  
- **Tour Storage**: Same format as text-generated tours
- **Tour Editing**: No changes needed

### 2. New Dependencies
- **Coordinate Service**: New microservice
- **Route Calculation**: Optional (connecting lines)
- **POI Validation**: None (user names stops)

## File Structure
```
audio_tour_app/lib/screens/
├── map_stop_selector_screen.dart     # NEW
├── tour_generator_screen.dart        # MODIFIED

backend/
├── coordinate_tour_generator_service.py  # NEW  
├── tour_orchestrator_service.py         # MODIFIED
├── requirements-coordinate.txt           # NEW
├── Dockerfile.coordinate                 # NEW
```

## Implementation Priority

### Phase 1 (MVP)
1. Map selector screen with basic tap-to-add
2. Coordinate generation service  
3. Integration with existing tour workflow

### Phase 2 (Enhancements)
1. Connecting lines between stops
2. Distance calculations
3. Route optimization
4. POI auto-suggestions

## Success Criteria
- User can create tours by pointing on map
- Generated tours have same quality as text-based tours
- Editing works identically to existing tours
- No disruption to current text-based generation

## Implementation Notes for Services Amazon-Q

### Backend Service Requirements
1. **Port Assignment**: Use next available port (likely 5019)
2. **Docker Integration**: Add to docker-compose.yml
3. **Service Communication**: Follow existing pattern with tour_orchestrator_service.py
4. **Error Handling**: Match existing service error patterns
5. **Logging**: Use same logging format as other services

### Frontend Integration Points
1. **Navigation**: Use existing Navigator.push pattern
2. **State Management**: Follow existing SharedPreferences pattern
3. **Map Component**: Reference home_screen.dart map implementation
4. **Styling**: Match existing Color(0xFF9b59b6) purple theme

### Testing Strategy
1. **Unit Tests**: Test coordinate validation and stop ordering
2. **Integration Tests**: Test full workflow from map selection to tour generation
3. **User Testing**: Validate map interaction UX matches expectations

This design maintains minimal changes to existing systems while adding the new map-based creation workflow.