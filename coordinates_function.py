def get_coordinates_for_location(location):
    """Get coordinates for a location using the coordinates-fromai service."""
    import requests
    import urllib.parse
    
    print(f"\n==== REQUESTING COORDINATES FOR: {location} ====\n")
    
    try:
        # URL-encode the location
        encoded_location = urllib.parse.quote(location)
        
        # Make the request to the coordinates-fromai service
        url = f"http://coordinates-fromai:5004/coordinates/{encoded_location}"
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
        
        print(f"No coordinates found for {location}")
        return None
    except Exception as e:
        print(f"Error getting coordinates from coordinates-fromai service: {e}")
        return None