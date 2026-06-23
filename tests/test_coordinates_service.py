#!/usr/bin/env python3
"""
Script to test the coordinates_fromAI service.
"""
import requests
import sys
import urllib.parse

def test_coordinates_service(location):
    """Test the coordinates_fromAI service."""
    try:
        print(f"Testing coordinates_fromAI service for: {location}")
        
        # URL-encode the location
        encoded_location = urllib.parse.quote(location)
        
        # Try multiple URLs to access the service
        urls = [
            f"http://localhost:5005/coordinates/{encoded_location}",
            f"http://coordinates_fromAI:5004/coordinates/{encoded_location}"
        ]
        
        for url in urls:
            try:
                print(f"\nAttempting to request URL: {url}")
                response = requests.get(url, timeout=10)
                
                print(f"Response status code: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if "coordinates" in data and len(data["coordinates"]) >= 2:
                        lat, lng = data["coordinates"]
                        print(f"Received coordinates: lat={lat}, lng={lng}")
                        return True
                    else:
                        print(f"Invalid response format: {data}")
                else:
                    print(f"Error response: {response.text}")
            except Exception as e:
                print(f"Error with URL {url}: {e}")
        
        # If we get here, all URLs failed
        return False
    except Exception as e:
        print(f"Error testing coordinates service: {e}")
        return False

def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python test_coordinates_service.py \"Location Name\"")
        print("Example: python test_coordinates_service.py \"Keene Public Library, Keene, NH\"")
        sys.exit(1)
    
    location = sys.argv[1]
    
    print("\n===== Testing Coordinates from AI Service =====\n")
    
    success = test_coordinates_service(location)
    
    if success:
        print("\nCoordinates service test successful!")
    else:
        print("\nCoordinates service test failed")
        sys.exit(1)

if __name__ == "__main__":
    main()