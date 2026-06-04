def detect_tour_type(request_string):
    """
    Detects whether a tour requires contextual information (books, movies, history)
    or operational information (restaurants, museums, shops).
    
    Returns: "CONTEXTUAL" or "OPERATIONAL"
    """
    request_lower = request_string.lower()
    
    # Keywords that indicate contextual/reference tours
    contextual_keywords = [
        'book', 'novel', 'movie', 'film', 'podcast', 'historic figure', 
        'history', 'mentioned in', 'featured in', 'inspired by',
        'character', 'scene', 'episode', 'chapter', 'story',
        'literary', 'historical', 'filming location', 'setting'
    ]
    
    # Keywords that indicate operational tours
    operational_keywords = [
        'restaurant', 'museum', 'gallery', 'shop', 'store', 'cafe',
        'bakery', 'bar', 'pub', 'hotel', 'theater', 'market',
        'boutique', 'diner', 'bistro', 'brewery', 'winery'
    ]
    
    # Check for contextual keywords first (more specific)
    contextual_score = sum(1 for keyword in contextual_keywords if keyword in request_lower)
    operational_score = sum(1 for keyword in operational_keywords if keyword in request_lower)
    
    if contextual_score > 0:
        return "CONTEXTUAL"
    elif operational_score > 0:
        return "OPERATIONAL"
    else:
        # Default to operational for safety
        return "OPERATIONAL"

# Test the detector
if __name__ == "__main__":
    test_cases = [
        "restaurant tour in West Roxbury, MA",
        "Walking tour in Cambridge, MA among areas mentioned in the book tomorrow, tomorrow, and tomorrow",
        "art galleries in Boston, MA",
        "Harry Potter filming locations in London",
        "historic sites from the Revolutionary War"
    ]
    
    for test in test_cases:
        result = detect_tour_type(test)
        print(f"'{test}' -> {result}")