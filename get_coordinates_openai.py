import requests
import sys

def get_coordinates_from_openai(location, api_key):
    """Get coordinates for a location using OpenAI API."""
    print(f"Requesting coordinates for '{location}' from OpenAI API")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Create a prompt that asks for coordinates
    prompt = f"What are the latitude and longitude coordinates for {location}? Please respond with only the decimal coordinates in the format 'latitude, longitude' without any other text."
    
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that provides precise geographic coordinates."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data
        )
        
        if response.status_code == 200:
            result = response.json()
            coordinates_text = result["choices"][0]["message"]["content"].strip()
            
            # Try to parse the coordinates
            try:
                # Handle various formats
                coordinates_text = coordinates_text.replace("Latitude: ", "").replace("Longitude: ", "")
                parts = coordinates_text.split(",")
                if len(parts) >= 2:
                    lat = float(parts[0].strip())
                    lng = float(parts[1].strip())
                    print(f"Found coordinates: lat={lat}, lng={lng}")
                    return (lat, lng)
                else:
                    print(f"Could not parse coordinates from: {coordinates_text}")
                    return None
            except Exception as e:
                print(f"Error parsing coordinates: {e}")
                print(f"Raw response: {coordinates_text}")
                return None
        else:
            print(f"OpenAI API error: {response.status_code}")
            print(f"Response: {response.text}")
            return None
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python get_coordinates_openai.py <location> <openai_api_key>")
        print("Example: python get_coordinates_openai.py \"Hall Memorial Library, Ellington CT\" sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        sys.exit(1)
    
    location = sys.argv[1]
    api_key = sys.argv[2]
    
    coordinates = get_coordinates_from_openai(location, api_key)
    
    if coordinates:
        lat, lng = coordinates
        print(f"\nCoordinates for {location}:")
        print(f"Latitude: {lat}")
        print(f"Longitude: {lng}")
    else:
        print(f"\nFailed to get coordinates for {location}")
        sys.exit(1)