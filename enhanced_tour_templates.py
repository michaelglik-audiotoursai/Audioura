"""
Enhanced Tour Templates System
Addresses generic naming and fictional content issues
"""
import re

from coordinate_requirements import get_coordinate_requirement, get_coordinate_instruction

def get_enhanced_tour_template(location, tour_type, total_stops, intent=None):
    """
    Enhanced template system with specialized handling for literary, retail, and product tours.
    """
    if intent:
        theme_type = intent.get("theme_type", "STANDARD")
        theme_name = intent.get("theme_name", "")
        poi_type = intent.get("poi_type", tour_type)
        
        # 3.1 LITERARY TOURS (Books, Movies, Podcasts, Local News)
        if theme_type == "BOOK" and theme_name:
            return f"""CRITICAL: You are being asked about locations from the book "{theme_name}" in {location}.

IF YOU DO NOT HAVE SPECIFIC KNOWLEDGE about real locations mentioned in "{theme_name}" that are actually in {location}, you MUST respond with:
"I don't have sufficient knowledge about specific locations from '{theme_name}' that are located in {location}."

DO NOT:
- Create fictional locations, sculptures, or murals
- Invent connections that don't exist
- Use generic names like "Walking Tour 1" or "Book Location 1"
- Make up street art or monuments

ONLY proceed if you have genuine knowledge about:
1. Actual places mentioned in "{theme_name}"
2. Real locations in {location} connected to the book
3. Author's documented connections to {location}

If you have real knowledge, provide {total_stops} locations with:
- Exact location name and address
- Specific quote/page reference from "{theme_name}"
- Real connection (not invented)
- GPS coordinates

Format: "1. [Real Location Name]\\nBook Reference: [Actual quote from book]\\nConnection: [Real documented connection]\\nCoordinates: [Lat, Lng]"

Remember: It's better to admit insufficient knowledge than create fiction."""
        
        # 3.2 RETAIL TOURS (Restaurants, Stores, Cafes, Services with operational details)
        elif any(keyword in poi_type.lower() for keyword in ['restaurant', 'store', 'shop', 'cafe', 'coffee', 'bakery', 'market', 'boutique', 'salon', 'spa', 'gym', 'fitness', 'repair', 'service', 'clinic', 'pharmacy', 'bank', 'hotel', 'inn', 'bar', 'pub', 'brewery', 'winery']):
            # Determine coordinate requirement
            coord_req = get_coordinate_requirement(location, tour_type, intent)
            coord_instruction = get_coordinate_instruction(coord_req)
            
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

Example Formats by Business Type:

**Restaurant Example:**
Stop 1: West on Centre
Address: 1732 Centre Street, West Roxbury, MA 02132
Description: Popular American restaurant and bar with cozy lounge area and fireplace
Specialties: New American cuisine, weekend brunch, craft cocktails. Known for grilled filet mignon, chicken marsala, artisanal pizzas, and seasonal specials
Operational Details:
- Hours: Mon-Thu 11:30am-10pm, Fri-Sat 11:30am-11pm, Sun 10am-9pm (brunch starts 10am)
- Price Range: $$$ (entrees $18-32, brunch $12-18)
- Busy Times: Weekend evenings 6-8pm, Sunday brunch 11am-2pm - reservations recommended
- Features: Full bar, outdoor seating, cozy fireplace lounge, private event space
Customer Experience: Known for excellent service and consistent quality, popular for date nights and family celebrations
Community Role: Neighborhood gathering place for West Roxbury residents, supports local events
Directions: Located on Centre Street in the heart of West Roxbury's dining district
Coordinates: 42.2799, -71.1597

**Retail Store Example:**
Stop 1: The Book Nook
Address: 456 Main Street, Cambridge, MA 02138
Description: Independent bookstore with cozy reading nooks and local author events
Specialties: Literary fiction, local authors, rare books, book clubs, author readings
Operational Details:
- Hours: Mon-Sat 9am-9pm, Sun 11am-6pm
- Price Range: $$ (books $10-30, rare books $50-200)
- Busy Times: Weekend afternoons, evening events - call ahead for event tickets
- Features: Reading chairs, coffee corner, event space, special orders, gift wrapping
Customer Experience: Knowledgeable staff recommendations, personal service, literary community hub
Community Role: Supports local authors, hosts book clubs, literary events for Cambridge readers

**Service Business Example:**
Stop 1: Elite Fitness Center
Address: 789 Fitness Way, Newton, MA 02459
Description: Full-service gym with personal training and group fitness classes
Specialties: Personal training, yoga classes, strength training, cardio equipment, nutrition counseling
Operational Details:
- Hours: Mon-Fri 5am-11pm, Sat-Sun 6am-9pm
- Price Range: $$$ (monthly membership $80-120, personal training $75/session)
- Busy Times: Early morning 6-8am, evening 5-7pm - book classes in advance
- Features: Pool, sauna, childcare, parking, locker rooms, smoothie bar
Customer Experience: Professional trainers, clean facilities, supportive community atmosphere
Community Role: Health and wellness hub for Newton residents, sponsors local sports teams

CRITICAL: Use ONLY real, operating businesses with specific names and authentic operational details. Include actual products/services, real hours, genuine pricing, and true community connections."""
        
        # 3.3 PRODUCT TOURS (Cheese, Wine, Souvenirs with cultural context)
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
7. **GPS coordinates** (required for first location)

Example for "artisanal cheese":
1. Formaggio Kitchen
   Address: 244 Huron Ave, Cambridge, MA
   Specialties: 200+ artisanal cheeses, local New England varieties, European imports
   Cultural Context: Cambridge's cheese culture reflects academic community's international tastes
   Expert Knowledge: Staff trained in cheese pairing, offers classes
   Price Range: $8-50 per pound, tastings available
   Coordinates: 42.3875, -71.1355

Focus on the cultural significance of {theme_name} in {location}'s food/retail landscape."""
        
        # STANDARD TOURS with strict naming requirements
        else:
            # Determine coordinate requirement
            coord_req = get_coordinate_requirement(location, tour_type, intent)
            coord_instruction = get_coordinate_instruction(coord_req)
            
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

Example Format:
1. Harvard Yard
   Type: Historic university campus
   Significance: Founded 1636, oldest higher education institution in US
   Year: 1636
   Directions: From Harvard Square T station, walk north on Massachusetts Avenue
   Coordinates: 42.3744, -71.1169

2. Widener Library
   Type: Academic library
   Significance: Memorial to Harry Elkins Widener, largest academic library
   Year: 1915
   Directions: From Harvard Yard, walk to the center of the Yard
   Coordinates: 42.3745, -71.1170

REMEMBER: Every location must have a real, specific name - no generic placeholders."""
    
    # Fallback for non-intent based requests
    coord_req = get_coordinate_requirement(location, tour_type, intent)
    coord_instruction = get_coordinate_instruction(coord_req)
    
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

Example Format:
1. Harvard Yard
   Address: Cambridge, MA 02138
   Type: Historic university campus
   Significance: Founded 1636, oldest higher education institution in US
   Year: 1636
   Directions: From Harvard Square T station, walk north on Massachusetts Avenue
   Coordinates: 42.3744, -71.1169

2. Widener Library
   Address: Harvard Yard, Cambridge, MA 02138
   Type: Academic library
   Significance: Memorial to Harry Elkins Widener, largest academic library
   Year: 1915
   Directions: From Harvard Yard, walk to the center of the Yard
   Coordinates: 42.3745, -71.1170

REMEMBER: Every location must have a real, specific name and {coord_instruction.lower()}."""

def validate_enhanced_poi_knowledge(poi_list, intent, location):
    """
    Enhanced validation with strict generic name detection for all retail categories.
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
    
    # Fictional content patterns for all business types
    fictional_patterns = [
        r'mural titled.*?Tomorrow.*?Tomorrow.*?Tomorrow',
        r'sculpture titled.*?Tomorrow.*?Tomorrow.*?Tomorrow',
        r'Created by.*?renowned.*?artist\s*,',  # Missing artist name
        r'street artist\s*,',  # Missing name after comma
        r'monumental work.*?artistic.*?significance',
        r'fictional.*?establishment',
        r'imaginary.*?business',
        r'hypothetical.*?store'
    ]
    
    generic_count = 0
    fictional_count = 0
    
    for poi in poi_list:
        poi_name = poi.get('name', '')
        poi_description = poi.get('description', '')
        
        # Check for generic names
        for pattern in generic_patterns:
            if re.match(pattern, poi_name, re.IGNORECASE):
                generic_count += 1
                print(f"❌ Generic name detected: {poi_name}")
                break
        
        # Check for fictional content
        full_text = f"{poi_name} {poi_description}"
        for pattern in fictional_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                fictional_count += 1
                print(f"❌ Fictional content detected in: {poi_name}")
                break
    
    # Fail if ANY generic names or fictional content
    if generic_count > 0:
        return False, f"Generic placeholder names detected (e.g., 'Store 1', 'Restaurant 1'). System lacks specific knowledge about operating businesses in {location}."
    
    if fictional_count > 0:
        theme_name = intent.get('theme_name', '') if intent else ''
        if theme_name:
            return False, f"AI generated fictional content about '{theme_name}'. System lacks authentic knowledge about this theme in {location}."
        else:
            return False, f"AI generated fictional businesses instead of real operating establishments in {location}."
    
    return True, "Knowledge validation passed"