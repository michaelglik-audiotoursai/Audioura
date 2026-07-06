from tour_type_detector import detect_tour_type

def generate_enhanced_prompt(location, request_string, total_stops=5):
    """
    Generates appropriate prompt based on tour type detection.
    
    Args:
        location: The location for the tour
        request_string: The full user request
        total_stops: Number of stops requested (default 5)
    
    Returns:
        Complete prompt text for AI generation
    """
    
    tour_type = detect_tour_type(request_string)
    
    if tour_type == "CONTEXTUAL":
        # Use contextual template for reference tours
        template_path = "contextual_prompt_template.txt"
    else:
        # Use operational template for business/venue tours
        template_path = "generic_prompt_template.txt"
    
    # Read the appropriate template
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()
    except FileNotFoundError:
        # Fallback to generic template
        with open("generic_prompt_template.txt", 'r', encoding='utf-8') as f:
            template = f.read()
    
    # Replace placeholders
    prompt = template.replace("{LOCATION}", location)
    prompt = prompt.replace("{REQUEST_STRING}", request_string)
    prompt = prompt.replace("{TOTAL_STOPS}", str(total_stops))
    
    return prompt, tour_type

# Test the enhanced prompt generator
if __name__ == "__main__":
    test_cases = [
        ("West Roxbury, MA", "restaurant tour in West Roxbury, MA"),
        ("Cambridge, MA", "Walking tour in Cambridge, MA among areas mentioned in the book tomorrow, tomorrow, and tomorrow")
    ]
    
    for location, request in test_cases:
        prompt, tour_type = generate_enhanced_prompt(location, request)
        print(f"\nRequest: {request}")
        print(f"Detected Type: {tour_type}")
        print(f"Prompt Length: {len(prompt)} characters")
        print("=" * 50)
