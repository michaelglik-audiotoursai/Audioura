def get_coordinates_for_location(location):
    """Get coordinates for a location using the coordinates_fromAI service."""
    import requests
    import urllib.parse
    
    print(f"\n==== REQUESTING COORDINATES FOR: {location} ====\n")
    
    try:
        # URL-encode the location
        encoded_location = urllib.parse.quote(location)
        
        # Make the request to the coordinates_fromAI service
        # Try both the service name and the container name
        urls = [
            f"http://coordinates_fromAI:5004/coordinates/{encoded_location}",
            f"http://coordinates-fromAI:5004/coordinates/{encoded_location}"
        ]
        
        for url in urls:
            try:
                print(f"Attempting to request URL: {url}")
                response = requests.get(url, timeout=10)
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
            except Exception as e:
                print(f"Error with URL {url}: {e}")
        
        # If we get here, both URLs failed
        print(f"No coordinates found for {location}")
        return None
    except Exception as e:
        print(f"Error getting coordinates from coordinates_fromAI service: {e}")
        return None