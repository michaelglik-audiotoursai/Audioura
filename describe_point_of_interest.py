"""
Generate detailed descriptions for Points of Interest (POI) using OpenAI API.
Extracted from generate_tour_text.py for modular use.
"""
import os
import json
import requests


def describe_point_of_interest(poi_name, artist="", year="", location="", tour_type="", 
                             word_count=300, api_key=None, model="gpt-3.5-turbo"):
    """
    Generate a detailed description for a Point of Interest using OpenAI API.
    
    Args:
        poi_name (str): Name of the exhibit/artwork
        artist (str, optional): Artist/creator name
        year (str, optional): Year created or acquired
        location (str, optional): Location context (e.g., "deCordova Sculpture Park")
        tour_type (str, optional): Type of tour (e.g., "sculpture", "architecture")
        word_count (int, optional): Target word count for description (default: 300)
        api_key (str, optional): OpenAI API key. If None, will try environment variable
        model (str, optional): OpenAI model to use (default: "gpt-3.5-turbo")
    
    Returns:
        dict: Contains 'orientation', 'description', 'word_count', 'cost', 'tokens_used'
              Returns None if API call fails
    
    Example:
        result = describe_point_of_interest(
            poi_name="The Thinker",
            artist="Auguste Rodin",
            year="1904",
            location="Museum of Fine Arts",
            tour_type="sculpture"
        )
        if result:
            print(f"Orientation: {result['orientation']}")
            print(f"Description: {result['description']}")
            print(f"Cost: ${result['cost']:.4f}")
    """
    
    # Get API key
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            api_key = input("Enter your OpenAI API key: ")
            if not api_key:
                print("Error: OpenAI API key is required")
                return None
    
    # Build the prompt
    poi_info = poi_name
    if artist and artist.lower() != "unknown artist":
        poi_info += f" by {artist}"
    if year:
        poi_info += f", {year}"
    
    context_info = ""
    if location and tour_type:
        context_info = f" in a walking tour of {location} focusing on {tour_type}"
    elif location:
        context_info = f" at {location}"
    elif tour_type:
        context_info = f" in a {tour_type} tour"
    
    description_prompt = f"""Create a detailed description for: {poi_info}{context_info}.

Start with an orientation section that explains where the visitor should position themselves to best view and appreciate this exhibit.

Then provide a detailed description of the exhibit that is EXACTLY {word_count} words long. Include:
- The artistic, historical, and cultural significance of the work
- Information about the artist and their creative process
- How this piece fits into the broader context{f" of {tour_type}" if tour_type else ""}
- Interesting details that would engage visitors

Format your response as follows:
Orientation: [Brief orientation text explaining the best viewing position]

[Detailed {word_count}-word description of the exhibit]

DO NOT include any section headers other than "Orientation:" - the description should flow naturally after the orientation section.
DO NOT include directions to the next stop - these will be added separately.
"""
    
    # Prepare API request
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    description_data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a knowledgeable museum guide with expertise in art, architecture, and history."},
            {"role": "user", "content": description_prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 1000
    }
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            data=json.dumps(description_data)
        )
        
        if response.status_code == 200:
            result = response.json()
            description_text = result["choices"][0]["message"]["content"]
            
            # Calculate cost (GPT-3.5-turbo pricing)
            tokens_used = result["usage"]["total_tokens"]
            cost = tokens_used / 1000 * 0.002  # $0.002 per 1K tokens
            
            # Parse orientation and description
            parts = description_text.split("Orientation:", 1)
            if len(parts) > 1:
                orientation_text = parts[1].strip()
                description_parts = orientation_text.split("\n\n", 1)
                if len(description_parts) > 1:
                    orientation = description_parts[0].strip()
                    description = description_parts[1].strip()
                else:
                    orientation = orientation_text
                    description = ""
            else:
                orientation = "Position yourself directly in front of the exhibit for the best view."
                description = description_text.strip()
            
            # Count actual words in description
            actual_word_count = len(description.split())
            
            return {
                "orientation": orientation,
                "description": description,
                "word_count": actual_word_count,
                "cost": cost,
                "tokens_used": tokens_used,
                "success": True
            }
        
        else:
            print(f"Error: API returned status code {response.status_code}")
            print(response.text)
            return None
    
    except Exception as e:
        print(f"Error calling OpenAI API: {str(e)}")
        return None


def describe_multiple_pois(poi_list, location="", tour_type="", word_count=300, 
                          api_key=None, model="gpt-3.5-turbo", delay=1):
    """
    Generate descriptions for multiple POIs with cost tracking.
    
    Args:
        poi_list (list): List of POI dictionaries with keys: 'name', 'artist', 'year'
        location (str, optional): Location context
        tour_type (str, optional): Type of tour
        word_count (int, optional): Target word count per description
        api_key (str, optional): OpenAI API key
        model (str, optional): OpenAI model to use
        delay (int, optional): Delay between API calls in seconds
    
    Returns:
        dict: Contains 'results' list and 'total_cost', 'total_tokens'
    
    Example:
        pois = [
            {"name": "The Thinker", "artist": "Auguste Rodin", "year": "1904"},
            {"name": "Venus de Milo", "artist": "Unknown", "year": "130-100 BC"}
        ]
        results = describe_multiple_pois(pois, location="Museum", tour_type="sculpture")
    """
    import time
    
    results = []
    total_cost = 0
    total_tokens = 0
    
    for i, poi in enumerate(poi_list):
        print(f"Generating description {i+1}/{len(poi_list)}: {poi.get('name', 'Unknown')}")
        
        result = describe_point_of_interest(
            poi_name=poi.get('name', ''),
            artist=poi.get('artist', ''),
            year=poi.get('year', ''),
            location=location,
            tour_type=tour_type,
            word_count=word_count,
            api_key=api_key,
            model=model
        )
        
        if result:
            results.append(result)
            total_cost += result['cost']
            total_tokens += result['tokens_used']
            print(f"  Generated {result['word_count']} words, cost: ${result['cost']:.4f}")
        else:
            print(f"  Failed to generate description")
            results.append(None)
        
        # Add delay between requests to avoid rate limits
        if i < len(poi_list) - 1 and delay > 0:
            time.sleep(delay)
    
    return {
        "results": results,
        "total_cost": total_cost,
        "total_tokens": total_tokens
    }


if __name__ == "__main__":
    print("=== POI Description Generator ===\n")
    
    # Get parameters from user
    poi_name = input("Enter POI name (e.g., 'The Thinker'): ")
    if not poi_name:
        poi_name = "The Thinker"
        print(f"Using default: {poi_name}")
    
    artist = input("Enter artist name (optional): ")
    year = input("Enter year (optional): ")
    location = input("Enter location (e.g., 'deCordova Sculpture Park'): ")
    tour_type = input("Enter tour type (e.g., 'sculpture'): ")
    
    word_count_input = input("Enter target word count (default: 300): ")
    word_count = int(word_count_input) if word_count_input else 300
    
    print(f"\nGenerating description for: {poi_name}...")
    
    result = describe_point_of_interest(
        poi_name=poi_name,
        artist=artist,
        year=year,
        location=location,
        tour_type=tour_type,
        word_count=word_count
    )
    
    if result:
        print(f"\n=== Generated Description ===\n")
        print(f"Orientation: {result['orientation']}\n")
        print(f"Description ({result['word_count']} words):\n{result['description']}")
        print(f"\nAPI Cost: ${result['cost']:.4f} ({result['tokens_used']} tokens)")
    else:
        print("Failed to generate description")