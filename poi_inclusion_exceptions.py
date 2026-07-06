"""
POI Inclusion Exception Table
Defines establishments that should be included in restaurant tours despite not being traditional restaurants.
"""

# Establishments that serve food with seating and should be included in restaurant tours
RESTAURANT_TOUR_INCLUSIONS = {
    # Food establishments with seating that function as restaurants
    "bakery": ["bakery", "pastry shop", "patisserie", "bread shop"],
    "cafe": ["cafe", "coffee shop", "coffeehouse", "espresso bar", "tea house"],
    "diner": ["diner", "diner-style restaurant", "classic diner", "american diner"],
    "bistro": ["bistro", "wine bar", "tapas bar"],
    "pub": ["pub", "gastropub", "tavern", "public house"],
    "bar": ["sports bar", "wine bar", "cocktail bar", "lounge"] # only if they serve food
}

# Locations that are suitable for walking tours
WALKING_TOUR_INCLUSIONS = {
    "farm": ["farm", "farmers market", "orchard", "vineyard", "winery"],
    "nature": ["arboretum", "botanical garden", "park", "nature reserve", "pond", "lake", "beach", "waterfront"],
    "historic": ["historic site", "museum", "monument", "landmark", "cemetery", "temple", "pagoda", "cathedral", "church"],
    "cultural": ["gallery", "art center", "library", "theater", "cultural center", "market", "bazaar"],
    "recreational": ["trail", "path", "overlook", "viewpoint", "recreation area"],
    "urban": ["bridge", "square", "plaza", "district", "quarter", "street", "avenue", "promenade"],
    "tourist": ["attraction", "landmark", "viewpoint", "observation deck", "scenic area"]
}

# Keywords that indicate food service with seating
FOOD_SERVICE_INDICATORS = [
    "serves food", "dining", "seating", "tables", "eat-in", "dine-in",
    "breakfast", "lunch", "dinner", "menu", "cuisine", "dishes"
]

# Keywords that indicate walking tour suitability
WALKING_TOUR_INDICATORS = [
    "walking", "trail", "path", "visit", "explore", "scenic", "historic",
    "nature", "outdoor", "attraction", "landmark", "destination"
]

def should_include_in_restaurant_tour(poi_name, poi_description, verification_reason):
    """
    Check if a POI should be included in restaurant tours despite initial verification failure.
    
    Args:
        poi_name: Name of the POI
        poi_description: Description of the POI
        verification_reason: Reason why it was initially excluded
        
    Returns:
        tuple: (should_include: bool, inclusion_reason: str)
    """
    poi_name_lower = poi_name.lower()
    poi_description_lower = poi_description.lower()
    reason_lower = verification_reason.lower()
    
    # Check if it's in our inclusion exceptions
    for category, keywords in RESTAURANT_TOUR_INCLUSIONS.items():
        for keyword in keywords:
            if keyword in poi_name_lower or keyword in reason_lower:
                # Additional check for food service indicators
                has_food_service = any(indicator in poi_description_lower 
                                     for indicator in FOOD_SERVICE_INDICATORS)
                
                if has_food_service or category in ["bakery", "cafe", "diner", "bistro"]:
                    return True, f"{poi_name} is a {category} that serves food with seating, suitable for restaurant tours"
    
    # Special case: if verification mentions it's a food establishment
    food_establishment_keywords = ["bakery", "cafe", "diner", "bistro", "pub", "bar"]
    if any(keyword in reason_lower for keyword in food_establishment_keywords):
        return True, f"{poi_name} is a food establishment suitable for restaurant tours"
    
    return False, "Not a food establishment suitable for restaurant tours"

def should_include_in_walking_tour(poi_name, poi_description, verification_reason):
    """
    Check if a POI should be included in walking tours despite initial verification failure.
    
    Args:
        poi_name: Name of the POI
        poi_description: Description of the POI
        verification_reason: Reason why it was initially excluded
        
    Returns:
        tuple: (should_include: bool, inclusion_reason: str)
    """
    poi_name_lower = poi_name.lower()
    poi_description_lower = poi_description.lower()
    reason_lower = verification_reason.lower()
    
    # Check if it's in our walking tour inclusion exceptions
    for category, keywords in WALKING_TOUR_INCLUSIONS.items():
        for keyword in keywords:
            if keyword in poi_name_lower or keyword in reason_lower:
                # Additional check for walking tour indicators
                has_walking_suitability = any(indicator in poi_description_lower 
                                            for indicator in WALKING_TOUR_INDICATORS)
                
                if has_walking_suitability or category in ["nature", "historic", "cultural"]:
                    return True, f"{poi_name} is a {category} location suitable for walking tours"
    
    # Special case: if verification mentions it's a tourist attraction or landmark
    walking_establishment_keywords = ["farm", "arboretum", "garden", "winery", "museum", "park", "historic", "market", "bridge", "beach", "temple", "cathedral", "landmark", "attraction"]
    if any(keyword in reason_lower for keyword in walking_establishment_keywords):
        return True, f"{poi_name} is an attraction suitable for walking tours"
    
    return False, "Not a location suitable for walking tours"

def get_inclusion_categories():
    """Get all POI categories that should be included in restaurant tours."""
    return list(RESTAURANT_TOUR_INCLUSIONS.keys())

def get_walking_tour_categories():
    """Get all POI categories that should be included in walking tours."""
    return list(WALKING_TOUR_INCLUSIONS.keys())
