import requests
import sys

def test_mapbox_geocoding(location, token):
    """Test the Mapbox Geocoding API with the provided token."""
    print(f"Testing Mapbox Geocoding API for: {location}")
    print(f"Using token: {token[:5]}...{token[-5:]}")
    
    # Format the location for the API request
    formatted_location = location.replace(' ', '%20')
    
    # Make request to Mapbox Geocoding API
    geocoding_url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{formatted_location}.json?access_token={token}&limit=1"
    
    print(f"Requesting URL: {geocoding_url[:60]}...")
    
    try:
        response = requests.get(geocoding_url, timeout=10)
        
        print(f"Response status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            # Check if we got any features back
            if data.get('features') and len(data['features']) > 0:
                # Get coordinates [longitude, latitude]
                coordinates = data['features'][0]['center']
                # Mapbox returns [lng, lat] but we want [lat, lng]
                lng, lat = coordinates
                
                print(f"SUCCESS! Found coordinates:")
                print(f"  Latitude: {lat}")
                print(f"  Longitude: {lng}")
                print(f"  Place name: {data['features'][0].get('place_name', 'Unknown')}")
                return True
            else:
                print("ERROR: No results found in the API response")
                print(f"API Response: {data}")
                return False
        else:
            print(f"ERROR: API request failed with status code {response.status_code}")
            print(f"Response body: {response.text[:200]}...")
            return False
    except Exception as e:
        print(f"ERROR: Exception occurred: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_mapbox.py <location> <mapbox_token>")
        print("Example: python test_mapbox.py \"Hall Memorial Library, Ellington CT\" pk.eyJ1IjoieW91cnVzZXJuYW1lIiwiYSI6ImNqeHh4eHh4eHh4eHh4eHh4eHh4eHh4In0.xxxxxxxxxxxxxxxxxxxxxxxx")
        sys.exit(1)
    
    location = sys.argv[1]
    token = sys.argv[2]
    
    success = test_mapbox_geocoding(location, token)
    
    if success:
        print("\nTest completed successfully!")
    else:
        print("\nTest failed!")
        sys.exit(1)