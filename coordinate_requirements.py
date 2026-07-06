"""
Enhanced coordinate requirement logic for different tour types
"""

def get_coordinate_requirement(location, tour_type, intent=None):
    """
    Determine if tour needs coordinates for all stops or first only.
    
    Returns: "ALL_STOPS" or "FIRST_STOP_ONLY"
    """
    location_lower = location.lower()
    tour_type_lower = tour_type.lower()
    
    # Check for plural forms indicating multiple locations
    plural_indicators = ['galleries', 'museums', 'restaurants', 'shops', 'stores', 'cafes', 'bars']
    if any(plural in location_lower for plural in plural_indicators):
        return "ALL_STOPS"
    
    # Single building indicators - generic patterns for single buildings
    single_building_patterns = [
        r'\b\w+\s+museum\b',  # "MFA Museum", "Science Museum", etc.
        r'\bmuseum\s+of\s+\w+\b',  # "Museum of Science", "Museum of Art"
        r'\b\w+\s+center\b',  # "Prudential Center", "Convention Center"
        r'\b\w+\s+library\b',  # "Public Library", "Boston Library"
        r'\b\w+\s+hall\b'  # "Faneuil Hall", "Symphony Hall"
    ]
    
    # Check if location matches single building patterns
    import re
    for pattern in single_building_patterns:
        if re.search(pattern, location_lower):
            return "FIRST_STOP_ONLY"
    
    # Default to all stops for safety
    return "ALL_STOPS"

def get_coordinate_instruction(coordinate_requirement):
    """
    Get the appropriate instruction text for coordinate requirements.
    """
    if coordinate_requirement == "FIRST_STOP_ONLY":
        return "**GPS coordinates** (required for first location only - entrance coordinates)"
    else:
        return "**GPS coordinates** (required for ALL locations)"

# Test cases
def test_coordinate_requirements():
    """Test the coordinate requirement logic"""
    
    test_cases = [
        # Single building tours - should be FIRST_STOP_ONLY
        ("MFA Boston", "art", "FIRST_STOP_ONLY"),
        ("Museum of Science", "science", "FIRST_STOP_ONLY"),
        ("Boston Public Library", "architecture", "FIRST_STOP_ONLY"),
        ("Prudential Center", "shopping", "FIRST_STOP_ONLY"),
        
        # Multi-location tours - should be ALL_STOPS
        ("art galleries in Boston, MA", "art", "ALL_STOPS"),
        ("museums in Boston", "art", "ALL_STOPS"),
        ("restaurants in North End, Boston", "culinary", "ALL_STOPS"),
        ("downtown Boston", "walking", "ALL_STOPS"),
        ("sculpture garden", "art", "ALL_STOPS"),
        ("shops in Harvard Square", "shopping", "ALL_STOPS"),
        ("Harry Potter filming locations", "movie", "ALL_STOPS"),
        ("bookstores in Cambridge", "literary", "ALL_STOPS"),
        ("cafes in Back Bay", "food", "ALL_STOPS"),
    ]
    
    print("=== Coordinate Requirement Test Results ===")
    for location, tour_type, expected in test_cases:
        result = get_coordinate_requirement(location, tour_type)
        status = "PASS" if result == expected else "FAIL"
        print(f"{status} {location} + {tour_type} -> {result} (expected {expected})")
    
    return test_cases

if __name__ == "__main__":
    test_coordinate_requirements()
