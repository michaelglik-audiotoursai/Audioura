# Tour Type Detection & Template System Design

## Problem Analysis
Currently, AudioTours uses a single generic AI prompt template for all tour types, which assumes museum/exhibit-based tours. This doesn't work well for:

1. **Walking tours in cities** - Need street locations, landmarks, historical sites
2. **Museum tours** - Need exhibits, artworks, collections  
3. **Specialized tours** - Need content-specific approaches (books, movies, botanical gardens)

## Solution: Intelligent Tour Type Detection

### 1. Tour Type Detection Logic

```python
def detect_tour_type(location, tour_type):
    """
    Detect the appropriate tour template based on location and tour_type.
    
    Returns: 'walking', 'museum', or 'specialized'
    """
    location_lower = location.lower()
    tour_type_lower = tour_type.lower()
    
    # Museum indicators
    museum_keywords = ['museum', 'gallery', 'mfa', 'moma', 'exhibition', 'collection']
    if any(keyword in location_lower for keyword in museum_keywords):
        return 'museum'
    
    # Specialized tour indicators
    specialized_keywords = ['book', 'movie', 'film', 'botanical', 'garden', 'park', 'novel', 'story']
    if any(keyword in tour_type_lower for keyword in specialized_keywords):
        return 'specialized'
    
    # Walking tour indicators (default for cities, neighborhoods)
    walking_keywords = ['city', 'downtown', 'neighborhood', 'district', 'street', 'avenue']
    if any(keyword in location_lower for keyword in walking_keywords):
        return 'walking'
    
    # Default to walking tour
    return 'walking'
```

### 2. Template System

#### Template A: Walking Tour (Cities/Neighborhoods)
```python
walking_tour_template = f"""For a walking tour of {location} focusing on {tour_type}, please provide information about {total_stops} significant landmarks, historical sites, or points of interest.

For each POI, include:
1. Name of the landmark/location
2. Historical significance or interesting facts
3. Year built/established (if known)
4. Walking directions from the previous location
5. GPS coordinates (REQUIRED for the first POI)

Focus on:
- Street-level landmarks and buildings
- Historical sites and monuments
- Cultural significance to the area
- Architectural features visible from the street
- Local stories and historical events
"""
```

#### Template B: Museum Tour (Indoor Exhibits)
```python
museum_tour_template = f"""For a museum tour of {location} focusing on {tour_type}, please provide information about {total_stops} significant exhibits or artworks.

For each POI, include:
1. Name of the exhibit/artwork
2. Artist/creator name
3. Year created or acquired (if known)
4. Directions within the museum from the previous exhibit
5. GPS coordinates (REQUIRED for the first POI - museum entrance)

Focus on:
- Specific artworks and exhibits
- Artist information and techniques
- Historical and cultural context
- Museum collection significance
- Artistic movements and styles
"""
```

#### Template C: Specialized Tour (Books/Movies/Themes)
```python
specialized_tour_template = f"""For a specialized tour of {location} based on {tour_type}, please provide information about {total_stops} significant locations related to this theme.

For each POI, include:
1. Name of the location
2. Connection to {tour_type} (scenes, inspiration, historical relevance)
3. Significance in the context of {tour_type}
4. Directions from the previous location
5. GPS coordinates (REQUIRED for the first POI)

Focus on:
- Locations directly related to {tour_type}
- Behind-the-scenes information
- Historical context and inspiration
- Cultural impact and significance
- Connections between locations and theme
"""
```

### 3. Implementation Plan

#### Step 1: Modify `modified_generate_tour_text.py`
- Add `detect_tour_type()` function
- Add three template functions
- Modify `generate_tour_text()` to use appropriate template

#### Step 2: Update Tour Orchestrator
- Pass tour type detection to generator
- Log which template is being used

#### Step 3: Test Cases
- **Walking**: "Newton Center downtown walking tour"
- **Museum**: "MFA Boston sculpture tour" 
- **Specialized**: "Harry Potter filming locations tour"

### 4. Benefits

✅ **Appropriate Content**: Each tour type gets relevant POI suggestions  
✅ **Better Directions**: Walking vs indoor navigation  
✅ **Relevant Context**: Historical vs artistic vs thematic focus  
✅ **Improved Quality**: AI generates more appropriate content  
✅ **Scalable**: Easy to add new tour types  

### 5. Implementation Complexity

**Complexity**: LOW to MEDIUM  
**Time Estimate**: 2-3 hours  
**Files to Modify**: 1 main file (`modified_generate_tour_text.py`)  
**Testing Required**: 3 test cases (one per template)  

### 6. Backward Compatibility

✅ **Existing Tours**: Continue working (default to walking template)  
✅ **API Unchanged**: Same parameters, smarter processing  
✅ **Mobile App**: No changes required  

## Next Steps

1. **Approve Design**: Confirm the three tour types and templates
2. **Implement Detection**: Add tour type detection logic
3. **Create Templates**: Implement the three specialized templates
4. **Test & Deploy**: Test with representative examples
5. **Monitor Results**: Compare tour quality before/after

This solution addresses the core issue of using inappropriate templates while maintaining simplicity and backward compatibility.