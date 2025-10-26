"""
Generate audio tour text using OpenAI API with a two-phase approach:
1. First get POI information and directions between them
2. Then generate detailed descriptions for each POI
"""
import os
import sys
import json
import time
import requests
from datetime import datetime
import re

def generate_tour_text(location, tour_type, output_file=None):
    """
    Generate audio tour text using OpenAI API.
    
    Args:
        location: Location for the tour
        tour_type: Type of tour (e.g., "sculpture", "architecture")
        output_file: File to save the tour text (optional)
    """
    # Get API key from environment variable or prompt user
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        api_key = input("Enter your OpenAI API key: ")
        if not api_key:
            print("Error: OpenAI API key is required")
            return

    # Headers for API calls
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Get number of stops
    total_stops = int(input("How many total stops would you like in the tour? (default: 10): ") or "10")
    
    # Track API costs
    total_tokens = 0
    total_cost = 0
    
    # PHASE 1: Get POI information and directions
    print(f"\nPHASE 1: Getting information for {total_stops} POIs and directions between them...")
    
    poi_info_prompt = f"""For a walking tour of {location} focusing on {tour_type}, please provide information about {total_stops} significant exhibits or points of interest.

For each POI, include:
1. Name of the exhibit/artwork
2. Artist/creator name
3. Year the museum acquired it (if known)
4. Directions to reach this POI from the previous one (for the first POI, provide directions from the main entrance)
5. GPS coordinates (if known, otherwise omit)

Format your response as a numbered list:

1. [Name of POI 1] by [Artist 1], [Year acquired]
   Directions from entrance: [Detailed directions from the main entrance to reach POI 1 by name]
   Coordinates: [Latitude, Longitude] (if known)

2. [Name of POI 2] by [Artist 2], [Year acquired]
   Directions from previous: [Detailed directions from POI 1 to reach POI 2 by name]
   Coordinates: [Latitude, Longitude] (if known)

... and so on.

IMPORTANT:
- Include only real, significant exhibits or artworks that would be featured in a tour
- Provide specific, detailed directions between each POI
- ALWAYS mention the name of the destination POI in the directions (e.g., "...until you reach 'The Grand Sculpture'" instead of "...until you reach the sculpture")
- Make sure the route forms a logical walking path through {location}
- If you don't know the exact year acquired, you can provide an estimate or the creation year
"""
    
    poi_info_data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": "You are a knowledgeable museum guide with expertise in art, architecture, and history."},
            {"role": "user", "content": poi_info_prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 2000
    }
    
    poi_list = []
    try:
        info_response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            data=json.dumps(poi_info_data)
        )
        
        if info_response.status_code == 200:
            info_result = info_response.json()
            info_text = info_result["choices"][0]["message"]["content"]
            
            # Track tokens and cost
            tokens_used = info_result["usage"]["total_tokens"]
            total_tokens += tokens_used
            call_cost = tokens_used / 1000 * 0.002  # $0.002 per 1K tokens for GPT-3.5-turbo
            total_cost += call_cost
            
            print(f"API call cost: ${call_cost:.4f} ({tokens_used} tokens)")
            
            # Print the raw response
            print("\n=== Generated POI Information ===")
            print(info_text)
            print("===============================\n")
            
            # Parse the response to extract POI information
            # First, try to split by numbered list items
            poi_blocks = re.split(r'\n\s*\d+\.', info_text)
            if poi_blocks and not poi_blocks[0].strip():
                poi_blocks = poi_blocks[1:]  # Remove empty first block if present
                
            # If we didn't get enough blocks, try an alternative approach
            if len(poi_blocks) < total_stops / 2:  # If we got less than half the expected stops
                print("Using alternative parsing method for POI information...")
                # Try to extract each numbered item
                poi_blocks = []
                matches = re.finditer(r'(\d+)\.\s+(.*?)(?=\n\s*\d+\.|$)', info_text, re.DOTALL)
                for match in matches:
                    poi_blocks.append(match.group(2).strip())
            
            # Process each POI block
            for i, block in enumerate(poi_blocks):
                if not block.strip():
                    continue
                
                poi = {
                    "stop_number": i + 1,
                    "name": "",
                    "artist": "",
                    "year": "",
                    "directions": "",
                    "coordinates": ""
                }
                
                # Extract name, artist, and year
                first_line = block.strip().split('\n')[0].strip()
                name_match = re.search(r'^(.*?)(?:\s+by\s+|$)', first_line)
                if name_match:
                    poi["name"] = name_match.group(1).strip().strip('"\'')
                
                artist_match = re.search(r'by\s+(.*?)(?:,|\s+\(|\s*$)', first_line)
                if artist_match:
                    poi["artist"] = artist_match.group(1).strip()
                
                year_match = re.search(r',\s*(\d{4}|\w+\s+\d{4})', first_line)
                if year_match:
                    poi["year"] = year_match.group(1).strip()
                
                # Extract directions - try multiple patterns
                directions = ""
                
                # Pattern 1: Standard format
                dir_match1 = re.search(r'Directions from (?:entrance|previous):\s*(.*?)(?:\n\s*Coordinates:|$)', block, re.DOTALL)
                if dir_match1:
                    directions = dir_match1.group(1).strip()
                
                # Pattern 2: With quoted POI name
                dir_match2 = re.search(r'Directions from ".*?":\s*(.*?)(?:\n\s*Coordinates:|$)', block, re.DOTALL)
                if not directions and dir_match2:
                    directions = dir_match2.group(1).strip()
                
                # Pattern 3: Any line with "Directions"
                dir_match3 = re.search(r'Directions.*?:\s*(.*?)(?:\n\s*Coordinates:|$)', block, re.DOTALL)
                if not directions and dir_match3:
                    directions = dir_match3.group(1).strip()
                
                # Store the directions
                poi["directions"] = directions
                
                # Extract coordinates if present
                coordinates_match = re.search(r'Coordinates:\s*(.*?)(?:\n|$)', block)
                if coordinates_match:
                    poi["coordinates"] = coordinates_match.group(1).strip()
                
                poi_list.append(poi)
            
            # Ensure we have the requested number of POIs
            while len(poi_list) < total_stops:
                stop_num = len(poi_list) + 1
                poi_list.append({
                    "stop_number": stop_num,
                    "name": f"Exhibit {stop_num}",
                    "artist": "Unknown Artist",
                    "year": "",
                    "directions": "",
                    "coordinates": ""
                })
            
            # Trim if we have too many
            if len(poi_list) > total_stops:
                poi_list = poi_list[:total_stops]
            
            print(f"Successfully extracted information for {len(poi_list)} POIs")
            
            # Print the extracted POI information
            print("\n=== Extracted POI Information ===")
            for poi in poi_list:
                print(f"{poi['stop_number']}. {poi['name']} by {poi['artist']}, {poi['year']}")
                print(f"   Directions: '{poi['directions']}'")
                if poi['coordinates']:
                    print(f"   Coordinates: {poi['coordinates']}")
            print("================================\n")
            
        else:
            print(f"Error: Failed to get POI information. Status code: {info_response.status_code}")
            print(info_response.text)
            # Create basic POI list as fallback
            for i in range(total_stops):
                poi_list.append({
                    "stop_number": i + 1,
                    "name": f"Exhibit {i + 1}",
                    "artist": "Unknown Artist",
                    "year": "",
                    "directions": "",
                    "coordinates": ""
                })
    
    except Exception as e:
        print(f"Error getting POI information: {str(e)}")
        # Create basic POI list as fallback
        for i in range(total_stops):
            poi_list.append({
                "stop_number": i + 1,
                "name": f"Exhibit {i + 1}",
                "artist": "Unknown Artist",
                "year": "",
                "directions": "",
                "coordinates": ""
            })
    
    # PHASE 2: Generate detailed descriptions for each POI
    print(f"\nPHASE 2: Generating detailed descriptions for each POI...")
    
    for poi in poi_list:
        stop_num = poi["stop_number"]
        poi_name = poi["name"]
        artist = poi["artist"]
        year = poi["year"]
        
        print(f"\nGenerating description for Stop {stop_num}: {poi_name} by {artist}, {year}...")
        
        description_prompt = f"""Create a detailed description for Stop {stop_num}: {poi_name} by {artist}, {year} in a walking tour of {location} focusing on {tour_type}.

Start with an orientation section that explains where the visitor should position themselves to best view and appreciate this exhibit.

Then provide a detailed description of the exhibit that is EXACTLY 300 words long. Include:
- The artistic, historical, and cultural significance of the work
- Information about the artist and their creative process
- How this piece fits into the broader context of {tour_type}
- Interesting details that would engage visitors

Format your response as follows:
Orientation: [Brief orientation text explaining the best viewing position]

[Detailed 300-word description of the exhibit]

DO NOT include any section headers other than "Orientation:" - the description should flow naturally after the orientation section.
DO NOT include directions to the next stop - these will be added separately.
"""
        
        description_data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "You are a knowledgeable museum guide with expertise in art, architecture, and history."},
                {"role": "user", "content": description_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 1000
        }
        
        try:
            description_response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                data=json.dumps(description_data)
            )
            
            if description_response.status_code == 200:
                description_result = description_response.json()
                description_text = description_result["choices"][0]["message"]["content"]
                
                # Track tokens and cost
                tokens_used = description_result["usage"]["total_tokens"]
                total_tokens += tokens_used
                call_cost = tokens_used / 1000 * 0.002  # $0.002 per 1K tokens for GPT-3.5-turbo
                total_cost += call_cost
                
                print(f"API call cost: ${call_cost:.4f} ({tokens_used} tokens)")
                
                # Split into orientation and description
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
                
                # Count words
                word_count = len(description.split())
                print(f"Description word count: {word_count} words")
                
                # Store the orientation and description
                poi["orientation"] = orientation
                poi["description"] = description
                poi["word_count"] = word_count
                
            else:
                print(f"Error: API returned status code {description_response.status_code}")
                print(description_response.text)
                # Add placeholder orientation and description
                poi["orientation"] = "Position yourself directly in front of the exhibit for the best view."
                poi["description"] = f"[Description for {poi_name} could not be generated.]"
                poi["word_count"] = 0
        
        except Exception as e:
            print(f"Error: {str(e)}")
            # Add placeholder orientation and description
            poi["orientation"] = "Position yourself directly in front of the exhibit for the best view."
            poi["description"] = f"[Description for {poi_name} could not be generated.]"
            poi["word_count"] = 0
        
        # Add a small delay to avoid rate limits
        time.sleep(1)
    
    # PHASE 3: Assemble the complete tour
    print(f"\nPHASE 3: Assembling the complete tour...")
    
    # Create a better title that doesn't duplicate information
    if tour_type.lower() in location.lower():
        # If tour type is already in the location name, don't repeat it
        tour_title = f"Step-by-Step Audio Guided Tour: {location}"
    else:
        # Otherwise, create a title that incorporates the tour type naturally
        tour_title = f"Step-by-Step Audio Guided Tour: {location} - {tour_type.title()} Tour"
    
    complete_tour = tour_title + "\n\n"
    
    # Add each POI with its description and directions
    for i, poi in enumerate(poi_list):
        stop_num = poi["stop_number"]
        poi_name = poi["name"]
        artist = poi["artist"]
        year = poi["year"]
        orientation = poi["orientation"]
        description = poi["description"]
        
        # Format the POI header
        poi_header = f"Stop {stop_num}: {poi_name}"
        if artist and artist.lower() != "unknown artist":
            poi_header += f" by {artist}"
        if year:
            poi_header += f", {year}"
        
        # Start the POI content
        poi_content = poi_header + "\n\n"
        
        # Add orientation section
        poi_content += "Orientation: "
        if i == 0:
            # For the first POI, include directions from the entrance
            entrance_directions = poi["directions"]
            if entrance_directions:
                poi_content += entrance_directions + " "
        
        # Add the orientation text
        poi_content += orientation + "\n\n"
        
        # Add description
        poi_content += description + "\n\n"
        
        # Add directions to next stop or conclusion
        if i < len(poi_list) - 1:
            next_poi = poi_list[i + 1]
            directions = next_poi["directions"]
            
            # Debug: Print the directions
            print(f"DEBUG - Directions for Stop {stop_num} to {stop_num+1}: '{directions}'")
            
            # Always include the standard phrase
            poi_content += "Please resume the tour at the next stop once you reach it by following these directions: "
            
            # Add the directions if available, otherwise use a generic direction
            if directions:
                # Replace generic references with the specific POI name
                modified_directions = directions
                generic_terms = [
                    "the sculpture", "the exhibit", "the artwork", "the installation", 
                    "the piece", "the statue", "the monument", "the display"
                ]
                
                for term in generic_terms:
                    if term in modified_directions.lower():
                        modified_directions = re.sub(
                            r'(?i)(' + re.escape(term) + r')', 
                            f"'{next_poi['name']}'", 
                            modified_directions
                        )
                
                # If the POI name is still not in the directions, append it
                if next_poi['name'] not in modified_directions:
                    modified_directions += f" You will arrive at '{next_poi['name']}'."
                
                poi_content += modified_directions
            else:
                poi_content += f"Continue to the next exhibit, '{next_poi['name']}'."
        else:
            # For the last POI, add the conclusion
            if tour_type.lower() in location.lower():
                # If tour type is already in the location name, don't repeat it
                conclusion = f"Thank you for joining this tour of {location}. We hope you have enjoyed the journey through art, history, and nature, and that you leave inspired by the beauty and creativity that surrounds you."
            else:
                conclusion = f"Thank you for joining this {tour_type} tour of {location}. We hope you have enjoyed the journey through art, history, and nature, and that you leave inspired by the beauty and creativity that surrounds you."
            
            poi_content += conclusion
        
        # Add to complete tour
        complete_tour += poi_content + "\n\n"
    
    # Print word count statistics
    print("\n=== Word Count Statistics ===")
    for poi in poi_list:
        print(f"Stop {poi['stop_number']}: {poi['name']} - {poi['word_count']} words")
    print("===========================\n")
    
    # Print total cost
    print(f"\nTotal API cost: ${total_cost:.4f} ({total_tokens} tokens)")
    
    # Save to file if output_file is provided
    if not output_file:
        # Create default filename based on location and tour type
        safe_location = ''.join(c if c.isalnum() else '_' for c in location)
        safe_tour_type = ''.join(c if c.isalnum() else '_' for c in tour_type)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{safe_location}_{safe_tour_type}_tour_{timestamp}.txt"
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(complete_tour)
    
    print(f"\nTour text generated successfully!")
    print(f"Saved to: {output_file}")
    
    # Show a preview
    preview_length = min(500, len(complete_tour))
    print(f"\nPreview of the generated tour:\n")
    print(complete_tour[:preview_length] + "...\n")
    
    return complete_tour, output_file

if __name__ == "__main__":
    print("=== Audio Tour Generator ===\n")
    
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
    
    # Generate the tour text
    generate_tour_text(location, tour_type, output_file)