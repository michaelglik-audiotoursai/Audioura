#!/usr/bin/env python3
"""
Script to test the coordinates_fromAI service.
"""
import requests
import sys
import urllib.parse
import subprocess

def test_coordinates_service(location):
    """Test the coordinates_fromAI service."""
    try:
        print(f"Testing coordinates_fromAI service for: {location}")
        
        # First check if the service is running
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=coordinates-fromai"],
            capture_output=True,
            text=True
        )
        
        if "coordinates-fromai" not in result.stdout:
            print("ERROR: coordinates-fromai service is not running!")
            print("Please run: docker-compose up -d coordinates-fromai")
            return False
        
        print("coordinates-fromai service is running.")
        
        # URL-encode the location
        encoded_location = urllib.parse.quote(location)
        
        # Make the request to the coordinates_fromAI service
        url = f"http://localhost:5005/coordinates/{encoded_location}"
        print(f"Requesting URL: {url}")
        
        response = requests.get(url, timeout=30)
        
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
        
        return False
    except Exception as e:
        print(f"Error testing coordinates service: {e}")
        return False

def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python test_coordinates_service_v2.py \"Location Name\"")
        print("Example: python test_coordinates_service_v2.py \"Keene Public Library, Keene, NH\"")
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