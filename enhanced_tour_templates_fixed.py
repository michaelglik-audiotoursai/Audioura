"""
Enhanced Tour Templates System - FIXED
Addresses coordinate requirement logic properly
"""
import re

from coordinate_requirements import get_coordinate_requirement, get_coordinate_instruction

def get_enhanced_tour_template(location, tour_type, total_stops, intent=None):
    """
    Fixed template system that properly uses coordinate requirement logic.
    """
    # Always determine coordinate requirement first
    coord_req = get_coordinate_requirement(location, tour_type, intent)
    coord_instruction = get_coordinate_instruction(coord_req)
    
    if intent:
        theme_type = intent.get("theme_type", "STANDARD")
        theme_name = intent.get("theme_name", "")
        poi_type = intent.get("poi_type", tour_type)
        
        # Use coordinate requirement logic for all templates
        if theme_type == "BOOK" and theme_name:
            return f"""Create a thematic tour of {location} inspired by the book "{theme_name}" by {intent.get('author', 'the author')}.

Approach: Find real locations in {location} that connect thematically to "{theme_name}" - places that capture the book's spirit, themes, atmosphere, or would appeal to readers of the work.

For each of the {total_stops} stops, provide:
1. **Stop Number and Location Name** (format: "Stop 1: [Real Location Name]")
2. **Full Street Address** with street number and zip code
3. **Location Type** (restaurant, bookstore, park, cafe, etc.)
4. **Thematic Connection** to "{theme_name}":
   - How this place embodies themes from the book
   - Atmosphere or mood that matches the work
   - Why readers of "{theme_name}" would appreciate this location
5. **Practical Details**:
   - Hours of operation
   - What to expect when visiting
   - Special features or recommendations
6. **Walking directions** from previous location
7. {coord_instruction}

Create meaningful thematic connections between real {location} locations and the essence of "{theme_name}"."""
        
        elif any(keyword in poi_type.lower() for keyword in ['restaurant', 'store', 'shop', 'cafe', 'coffee', 'bakery', 'market', 'boutique', 'salon', 'spa', 'gym', 'fitness', 'repair', 'service', 'clinic', 'pharmacy', 'bank', 'hotel', 'inn', 'bar', 'pub', 'brewery', 'winery']):
            return f"""Create a detailed {poi_type} tour of {location} with {total_stops} REAL, OPERATING businesses.

For each {poi_type.rstrip('s')}, provide:
1. **Stop Number and Business Name** (format: "Stop 1: [Business Name]")
2. **Full Street Address** with street number and zip code
3. **Business Description** (what type of establishment, atmosphere, notable features)
4. **Specialties/Products/Services** (specific offerings, signature items, unique services)
5. **Operational Details**:
   - Hours of operation (specific times, days closed)
   - Price range ($ to $$$$) with typical costs
   - Busy times and appointment/reservation recommendations
   - Special features (parking, accessibility, outdoor space, delivery, etc.)
6. **Customer Experience**:
   - What makes this business special or unique
   - Target clientele or typical customers
   - Notable reviews or recognition
7. **Community Role/Cultural Significance** for {location}
8. **Walking directions** from previous location (or starting point for first stop)
9. {coord_instruction}

CRITICAL: Use ONLY real, operating businesses with specific names and authentic operational details. Include actual products/services, real hours, genuine pricing, and true community connections."""
        
        elif theme_type == "PRODUCT" and theme_name:
            return f"""Create a specialized tour of businesses selling {theme_name} in {location}.

For each business specializing in {theme_name}, provide:
1. **Business Name** (real establishment)
2. **Address** with street details
3. **Product Specialties**:
   - Specific {theme_name} varieties/brands carried
   - Unique or rare items
   - Local vs imported selection
4. **Cultural Context**:
   - Why {theme_name} is significant in {location}
   - Regional preferences or traditions
   - Historical connection to the area
5. **Expert Knowledge**:
   - Staff expertise level
   - Tasting opportunities
   - Educational aspects
6. **Practical Details**:
   - Price ranges
   - Best times to visit
   - Special events or classes
7. {coord_instruction}

Focus on the cultural significance of {theme_name} in {location}'s food/retail landscape."""
        
        else:
            return f"""Create a {poi_type} tour of {location} with {total_stops} stops.

CRITICAL NAMING REQUIREMENTS:
- Use REAL, SPECIFIC location names (e.g., "Harvard Yard", "MIT Building 32", "Faneuil Hall")
- NEVER use generic names like "Walking Tour 1", "Stop 1", "Location 1", "Building 1"
- Each stop must have an actual, verifiable name

For each stop, provide:
1. **Real Location Name** (specific, not generic)
2. **What it is** (building, park, monument, etc.)
3. **Historical/Cultural significance**
4. **Year built/established** (if known)
5. **Walking directions** from previous location
6. {coord_instruction}

REMEMBER: Every location must have a real, specific name - no generic placeholders."""
    
    # Fallback template with coordinate requirement logic
    return f"""Create a tour of {location} with {total_stops} real locations.

Each location must have a SPECIFIC, REAL name - not generic placeholders.
Provide historical context, walking directions, and {coord_instruction.lower()}.

For each location, include:
1. **Real Location Name** (specific, not generic)
2. **Full street address** with city, state, ZIP code
3. **What it is** (building, park, monument, etc.)
4. **Historical/Cultural significance**
5. **Year built/established** (if known)
6. **Walking directions** from previous location
7. {coord_instruction}

REMEMBER: Every location must have a real, specific name and {coord_instruction.lower()}."""

def validate_enhanced_poi_knowledge(poi_list, intent, location):
    """
    Enhanced validation with lenient approach for partial success.
    Checks both POI names and descriptions for generic/fictional content.
    """
    if not poi_list or len(poi_list) == 0:
        return False, "No POIs were generated"
    
    # Strict generic patterns detection for all business types
    generic_patterns = [
        r'^(Walking Tour|Book Location|Store|Shop|Restaurant|Location|Exhibit|Building|Stop|Business|Place)\s+\d+$',
        r'^(Tour Stop|Point|Cafe|Market|Salon|Gym|Service)\s+\d+$',
        r'^(Fitness Center|Coffee Shop|Repair Shop|Boutique)\s+\d+$',
        r'^\w+\s+\d+$'  # Any single word + number
    ]
    
    # Fictional content patterns “Çö checked against BOTH name and description
    fictional_patterns = [
        r'mural titled.*?Tomorrow.*?Tomorrow.*?Tomorrow',
        r'sculpture titled.*?Tomorrow.*?Tomorrow.*?Tomorrow',
        r'Created by.*?renowned.*?artist\s*,',  # Missing artist name
        r'street artist\s*,',  # Missing name after comma
        r'monumental work.*?artistic.*?significance',
        r'fictional.*?establishment',
        r'imaginary.*?business',
        r'hypothetical.*?store',
        # Description-level hallucination patterns
        r'miniature replica of .{3,60} that does not exist',
        r'on (permanent |long-term )?loan from .{3,60} museum',  # fabricated loan claims
        r'recently acquired from .{3,60} collection',            # fabricated acquisition
    ]
    
    generic_count = 0
    fictional_count = 0
    valid_count = 0
    
    for poi in poi_list:
        poi_name = poi.get('name', '')
        poi_description = poi.get('description', '') or ''
        
        # Check for generic names
        is_generic = False
        for pattern in generic_patterns:
            if re.match(pattern, poi_name, re.IGNORECASE):
                generic_count += 1
                is_generic = True
                print(f"\u274c Generic name detected: {poi_name}")
                break
        
        # Check for fictional content in BOTH name and description
        if not is_generic:
            full_text = f"{poi_name} {poi_description}"
            is_fictional = False
            for pattern in fictional_patterns:
                if re.search(pattern, full_text, re.IGNORECASE):
                    fictional_count += 1
                    is_fictional = True
                    print(f"\u274c Fictional content detected in: {poi_name} [pattern: {pattern[:60]}]")
                    break
            
            if not is_fictional:
                valid_count += 1
    
    # Calculate success rate
    total_pois = len(poi_list)
    valid_percentage = valid_count / total_pois if total_pois > 0 else 0
    
    # Accept if we have at least some valid POIs (more lenient approach)
    if valid_count == 0:
        return False, f"No valid locations found in {location}. All generated content appears to be generic or fictional."
    
    # Accept if we have at least 30% valid content
    if valid_percentage < 0.3:
        return False, f"Insufficient quality data available for {location}. Most generated content appears to be generic placeholders."
    
    # Success with details about what was found
    if generic_count > 0 or fictional_count > 0:
        return True, f"Knowledge validation passed with {valid_count} valid locations (excluded {generic_count} generic, {fictional_count} fictional)"
    else:
        return True, "Knowledge validation passed"
