"""
Generate audio tour text with custom path through predefined POIs.
Uses describe_point_of_interest.py for POI descriptions.
"""
import os
import sys
import json
import time
import requests
from datetime import datetime
import re

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from describe_point_of_interest import describe_point_of_interest
except ImportError:
    print("Warning: Could not import describe_point_of_interest module.")
    print("Make sure describe_point_of_interest.py is in the same directory.")
    print("Using fallback POI description function.")
    
    def describe_point_of_interest(poi_name, artist="", year="", location="", tour_type="", 
                                 word_count=300, api_key=None, model="gpt-3.5-turbo"):
        """Fallback POI description function."""
        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                api_key = input("Enter your OpenAI API key: ")
                if not api_key:
                    return None
        
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
        
        prompt = f"""Create a detailed description for: {poi_info}{context_info}.

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
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a knowledgeable museum guide with expertise in art, architecture, and history."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 1000
        }
        
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                data=json.dumps(data)
            )
            
            if response.status_code == 200:
                result = response.json()
                description_text = result["choices"][0]["message"]["content"]
                tokens_used = result["usage"]["total_tokens"]
                cost = tokens_used / 1000 * 0.002
                
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
                return None
        except Exception as e:
            print(f"Error calling OpenAI API: {str(e)}")
            return None


def parse_poi_list(poi_text):
    """Parse POI list from text input."""
    pois = []
    lines = poi_text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or line.upper().startswith('ARTIST'):
            continue
            
        # Try to parse numbered format: "1 Fletcher Benton Donut with 3 Balls; 2002"
        match = re.match(r'^(\d+)\s+(.+)', line)
        if match:
            number = int(match.group(1))
            rest = match.group(2).strip()
            
            # Split by semicolon to separate name/artist from year
            parts = rest.split(';')
            name_artist = parts[0].strip()
            year = parts[1].strip() if len(parts) > 1 else ""
            
            # Try to separate artist and artwork name
            # Look for patterns like "Artist Name Title" or "Title by Artist"
            if ' by ' in name_artist:
                parts = name_artist.split(' by ', 1)
                name = parts[0].strip()
                artist = parts[1].strip()
            else:
                # Assume first word(s) are artist, rest is title
                words = name_artist.split()
                if len(words) >= 3:
                    # Try to find where artist name ends and title begins
                    # This is a heuristic - look for capitalized words that might be title
                    artist_words = []
                    title_words = []
                    found_title_start = False
                    
                    for i, word in enumerate(words):
                        if not found_title_start and i < len(words) - 1:
                            artist_words.append(word)
                        else:
                            found_title_start = True
                            title_words.append(word)
                    
                    if not title_words:  # Fallback
                        artist_words = words[:2] if len(words) >= 2 else words[:1]
                        title_words = words[len(artist_words):]
                    
                    artist = ' '.join(artist_words)
                    name = ' '.join(title_words)
                else:
                    artist = words[0] if words else ""
                    name = ' '.join(words[1:]) if len(words) > 1 else name_artist
            
            pois.append({
                'number': number,
                'name': name,
                'artist': artist,
                'year': year
            })
    
    return pois


def get_directions_between_pois(poi_from, poi_to, location, api_key):
    """Get directions between two POIs using OpenAI."""
    prompt = f"""Provide walking directions from "{poi_from['name']}" to "{poi_to['name']}" at {location}.

Give specific, detailed directions that mention landmarks and clear navigation points. 
ALWAYS end the directions by mentioning the destination by name: "...until you reach '{poi_to['name']}'."

Keep the directions concise but clear (2-3 sentences maximum)."""
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": "You are a knowledgeable tour guide providing walking directions."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 200
    }
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            data=json.dumps(data)
        )
        
        if response.status_code == 200:
            result = response.json()
            directions = result["choices"][0]["message"]["content"].strip()
            tokens_used = result["usage"]["total_tokens"]
            cost = tokens_used / 1000 * 0.002
            return directions, cost, tokens_used
        else:
            return f"Continue to '{poi_to['name']}'.", 0, 0
    except:
        return f"Continue to '{poi_to['name']}'.", 0, 0


def generate_tour_path(location, tour_type, output_file=None):
    """Generate audio tour with custom path through predefined POIs."""
    
    # Get API key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        api_key = input("Enter your OpenAI API key: ")
        if not api_key:
            print("Error: OpenAI API key is required")
            return
    
    # Get number of stops
    total_stops = int(input("How many total stops would you like in the tour? (default: 10): ") or "10")
    
    # Get POI source
    print(f"\nPOI Source Options:")
    print("1. Enter URL to POI list (default: deCordova map)")
    print("2. Enter POI list manually")
    print("3. Generate POI list using AI")
    
    choice = input("Choose option (1/2/3, default: 1): ").strip() or "1"
    
    all_pois = []
    
    if choice == "1":
        url = input("Enter URL (press Enter for default deCordova map): ").strip()
        if not url:
            url = "https://thetrustees.org/wp-content/uploads/2025/04/deCordovaParkMap_May2025.pdf"
        
        print(f"Note: URL parsing not implemented. Please enter POI list manually.")
        print("Example format:")
        print("1 Fletcher Benton Donut with 3 Balls; 2002")
        print("2 John Buck Dream World; 1988")
        print()
        poi_input = input("Enter POI list (press Enter to use AI generation): ").strip()
        
        if poi_input:
            all_pois = parse_poi_list(poi_input)
            print(f"Parsed {len(all_pois)} POIs from manual input.")
        else:
            choice = "3"  # Fall back to AI generation
    
    elif choice == "2":
        print("Enter POI list (one per line, format: 'Number Artist Name Title; Year'):")
        print("Example: 1 Fletcher Benton Donut with 3 Balls; 2002")
        print("Press Enter twice when done:")
        
        poi_lines = []
        while True:
            line = input()
            if not line:
                break
            poi_lines.append(line)
        
        if poi_lines:
            all_pois = parse_poi_list('\n'.join(poi_lines))
        else:
            choice = "3"  # Fall back to AI generation
    
    if choice == "3" and not all_pois:
        print(f"\nGenerating POI list using AI for {location}...")
        # Use the same logic as generate_tour_text.py
        poi_info_prompt = f"""For a walking tour of {location} focusing on {tour_type}, please provide information about 15-20 significant exhibits or points of interest.

Format your response as a numbered list:
1. [Name of POI 1] by [Artist 1], [Year]
2. [Name of POI 2] by [Artist 2], [Year]
... and so on.

Include only real, significant exhibits or artworks that would be featured in a tour."""
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "You are a knowledgeable museum guide."},
                {"role": "user", "content": poi_info_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 2000
        }
        
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                data=json.dumps(data)
            )
            
            if response.status_code == 200:
                result = response.json()
                poi_text = result["choices"][0]["message"]["content"]
                print("\n=== Generated POI List ===")
                print(poi_text)
                print("========================\n")
                
                # Parse the AI-generated list
                lines = poi_text.strip().split('\n')
                for i, line in enumerate(lines):
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Remove number prefix
                    match = re.match(r'^\d+\.?\s*(.+)', line)
                    if match:
                        content = match.group(1)
                        
                        # Parse "Name by Artist, Year" format
                        name = ""
                        artist = ""
                        year = ""
                        
                        if ' by ' in content:
                            parts = content.split(' by ', 1)
                            name = parts[0].strip()
                            rest = parts[1].strip()
                            
                            # Extract year
                            year_match = re.search(r',\s*(\d{4})', rest)
                            if year_match:
                                year = year_match.group(1)
                                artist = rest[:year_match.start()].strip()
                            else:
                                artist = rest
                        else:
                            name = content
                        
                        all_pois.append({
                            'number': i + 1,
                            'name': name,
                            'artist': artist,
                            'year': year
                        })
            else:
                print("Error generating POI list. Using fallback.")
                for i in range(15):
                    all_pois.append({
                        'number': i + 1,
                        'name': f"Exhibit {i + 1}",
                        'artist': "Unknown Artist",
                        'year': ""
                    })
        except Exception as e:
            print(f"Error: {e}")
            return
    
    if not all_pois:
        print("No POIs available. Exiting.")
        return
    
    # Display available POIs
    print(f"\n=== Available POIs ({len(all_pois)} total) ===")
    for poi in all_pois:
        print(f"{poi['number']}. {poi['name']} by {poi['artist']}, {poi['year']}")
    print("=" * 40)
    
    # Get path selection
    while True:
        path_input = input(f"\nEnter path of {total_stops} exhibits (comma-separated numbers, e.g., 1,3,5,7): ").strip()
        
        if not path_input:
            print("Path is required.")
            continue
        
        try:
            path_numbers = [int(x.strip()) for x in path_input.split(',')]
            
            if len(path_numbers) != total_stops:
                print(f"Error: Expected {total_stops} POIs, but got {len(path_numbers)}. Please try again.")
                continue
            
            # Validate all numbers exist
            invalid_numbers = [n for n in path_numbers if not any(poi['number'] == n for poi in all_pois)]
            if invalid_numbers:
                available_numbers = [poi['number'] for poi in all_pois]
                print(f"Error: Invalid POI numbers: {invalid_numbers}")
                print(f"Available numbers: {sorted(available_numbers)}")
                continue
            
            break
            
        except ValueError:
            print("Error: Please enter valid numbers separated by commas.")
            print(f"Example: {','.join(str(i) for i in range(1, min(9, len(all_pois)+1)))}")
    
    # Create selected POI list in order
    selected_pois = []
    for i, num in enumerate(path_numbers):
        poi = next(poi for poi in all_pois if poi['number'] == num)
        selected_pois.append({
            'stop_number': i + 1,
            'name': poi['name'],
            'artist': poi['artist'],
            'year': poi['year'],
            'original_number': poi['number']
        })
    
    print(f"\n=== Selected Tour Path ===")
    for poi in selected_pois:
        print(f"Stop {poi['stop_number']}: {poi['name']} by {poi['artist']}, {poi['year']}")
    print("=" * 30)
    
    # Track costs
    total_cost = 0
    total_tokens = 0
    
    # Generate descriptions for each POI
    print(f"\nGenerating descriptions for {len(selected_pois)} POIs...")
    
    for poi in selected_pois:
        print(f"\nGenerating description for Stop {poi['stop_number']}: {poi['name']}...")
        
        result = describe_point_of_interest(
            poi_name=poi['name'],
            artist=poi['artist'],
            year=poi['year'],
            location=location,
            tour_type=tour_type,
            word_count=300,
            api_key=api_key
        )
        
        if result:
            poi['orientation'] = result['orientation']
            poi['description'] = result['description']
            poi['word_count'] = result['word_count']
            total_cost += result['cost']
            total_tokens += result['tokens_used']
            print(f"Generated {result['word_count']} words, cost: ${result['cost']:.4f}")
        else:
            poi['orientation'] = "Position yourself directly in front of the exhibit for the best view."
            poi['description'] = f"[Description for {poi['name']} could not be generated.]"
            poi['word_count'] = 0
        
        time.sleep(1)  # Rate limiting
    
    # Generate directions between POIs
    print(f"\nGenerating directions between POIs...")
    
    for i in range(len(selected_pois) - 1):
        current_poi = selected_pois[i]
        next_poi = selected_pois[i + 1]
        
        print(f"Getting directions from Stop {current_poi['stop_number']} to Stop {next_poi['stop_number']}...")
        
        if i == 0:
            # First POI - directions from entrance
            directions = f"From the main entrance, head to '{current_poi['name']}'."
            current_poi['directions'] = directions
        
        # Directions to next POI
        directions, cost, tokens = get_directions_between_pois(current_poi, next_poi, location, api_key)
        next_poi['directions'] = directions
        total_cost += cost
        total_tokens += tokens
        
        time.sleep(0.5)  # Rate limiting
    
    # Assemble the complete tour (same format as generate_tour_text.py)
    print(f"\nAssembling the complete tour...")
    
    if tour_type.lower() in location.lower():
        tour_title = f"Step-by-Step Audio Guided Tour: {location}"
    else:
        tour_title = f"Step-by-Step Audio Guided Tour: {location} - {tour_type.title()} Tour"
    
    complete_tour = tour_title + "\n\n"
    
    for i, poi in enumerate(selected_pois):
        # Format POI header
        poi_header = f"Stop {poi['stop_number']}: {poi['name']}"
        if poi['artist'] and poi['artist'].lower() != "unknown artist":
            poi_header += f" by {poi['artist']}"
        if poi['year']:
            poi_header += f", {poi['year']}"
        
        poi_content = poi_header + "\n\n"
        
        # Add orientation
        poi_content += "Orientation: "
        if i == 0 and poi.get('directions'):
            poi_content += poi['directions'] + " "
        poi_content += poi['orientation'] + "\n\n"
        
        # Add description
        poi_content += poi['description'] + "\n\n"
        
        # Add directions to next stop or conclusion
        if i < len(selected_pois) - 1:
            next_poi = selected_pois[i + 1]
            poi_content += "Please resume the tour at the next stop once you reach it by following these directions: "
            poi_content += next_poi.get('directions', f"Continue to '{next_poi['name']}'.")
        else:
            if tour_type.lower() in location.lower():
                conclusion = f"Thank you for joining this tour of {location}. We hope you have enjoyed the journey through art, history, and nature, and that you leave inspired by the beauty and creativity that surrounds you."
            else:
                conclusion = f"Thank you for joining this {tour_type} tour of {location}. We hope you have enjoyed the journey through art, history, and nature, and that you leave inspired by the beauty and creativity that surrounds you."
            poi_content += conclusion
        
        complete_tour += poi_content + "\n\n"
    
    # Print statistics
    print("\n=== Word Count Statistics ===")
    for poi in selected_pois:
        print(f"Stop {poi['stop_number']}: {poi['name']} - {poi['word_count']} words")
    print("===========================")
    
    print(f"\nTotal API cost: ${total_cost:.4f} ({total_tokens} tokens)")
    
    # Save to file
    if not output_file:
        safe_location = ''.join(c if c.isalnum() else '_' for c in location)
        safe_tour_type = ''.join(c if c.isalnum() else '_' for c in tour_type)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{safe_location}_{safe_tour_type}_path_tour_{timestamp}.txt"
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(complete_tour)
    
    print(f"\nTour text generated successfully!")
    print(f"Saved to: {output_file}")
    
    # Show preview
    preview_length = min(500, len(complete_tour))
    print(f"\nPreview of the generated tour:\n")
    print(complete_tour[:preview_length] + "...\n")
    
    return complete_tour, output_file


if __name__ == "__main__":
    print("=== Audio Tour Path Generator ===\n")
    
    # Get location
    location = input("Enter the location (e.g., 'deCordova Sculpture Park in Lincoln, MA'): ")
    if not location:
        location = "deCordova Sculpture Park in Lincoln, MA"
        print(f"Using default location: {location}")
    
    # Get tour type
    tour_type = input("Enter the tour focus (e.g., 'sculpture', 'architecture'): ")
    if not tour_type:
        tour_type = "sculpture"
        print(f"Using default tour focus: {tour_type}")
    
    # Get output file (optional)
    output_file = input("Enter output file name (press Enter for auto-generated): ")
    
    # Generate the tour
    generate_tour_path(location, tour_type, output_file)