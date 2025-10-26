
def get_coordinates_from_generator(location):
    """Get coordinates for a location from the tour-generator service."""
    import requests
    import urllib.parse
    
    try:
        # Log the request
        print(f"\n==== REQUESTING COORDINATES FOR: {location} ====\n")
        
        # URL-encode the location
        encoded_location = urllib.parse.quote(location)
        
        # Make the request to the tour-generator service
        url = f"http://tour-generator:5000/coordinates/{encoded_location}"
        print(f"Requesting URL: {url}")
        
        response = requests.get(url, timeout=30)
        
        print(f"Response status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            if "coordinates" in data and len(data["coordinates"]) >= 2:
                lat, lng = data["coordinates"]
                print(f"Received coordinates: lat={lat}, lng={lng}")
                return (lat, lng)
            else:
                print(f"Invalid response format: {data}")
        else:
            print(f"Error response: {response.text}")
        
        return None
    except Exception as e:
        print(f"Error getting coordinates from generator: {e}")
        return None
