#!/usr/bin/env python3
"""
Script to directly modify the tour orchestrator service file.
"""
import sys

def fix_tour_orchestrator():
    """Fix the tour orchestrator service to always call the coordinates service."""
    try:
        # Read the current tour_orchestrator_service.py file
        with open("tour_orchestrator_service.py", "r") as f:
            service_py = f.read()
        
        # Make a backup of the original file
        with open("tour_orchestrator_service.py.bak_simple", "w") as f:
            f.write(service_py)
        
        print("Created backup at tour_orchestrator_service.py.bak_simple")
        
        # Add a simple function to get coordinates directly
        new_function = """
def get_coordinates_direct(location):
    # Get coordinates directly from the coordinates-fromai service
    import requests
    import urllib.parse
    
    print(f"\\n==== DIRECT COORDINATES REQUEST FOR: {location} ====\\n")
    
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
"""
        
        # Add the new function to the file
        new_service_py = service_py + new_function
        
        # Replace the coordinates retrieval in orchestrate_tour_async
        new_service_py = new_service_py.replace(
            "coords = get_coordinates_for_location(location)",
            "print(\"Calling get_coordinates_direct instead of get_coordinates_for_location\")\n            coords = get_coordinates_direct(location)"
        )
        
        # Replace the coordinates retrieval in store_audio_tour
        new_service_py = new_service_py.replace(
            "coords = get_coordinates_for_location(request_string or tour_name)",
            "print(\"Calling get_coordinates_direct instead of get_coordinates_for_location\")\n            coords = get_coordinates_direct(request_string or tour_name)"
        )
        
        # Write the updated service file
        with open("tour_orchestrator_service.py", "w") as f:
            f.write(new_service_py)
        
        print("Updated tour_orchestrator_service.py with direct coordinates function")
        
        return True
    except Exception as e:
        print(f"Error fixing tour orchestrator: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Fixing Tour Orchestrator (Simple Approach) =====\n")
    
    success = fix_tour_orchestrator()
    
    if success:
        print("\nTour orchestrator fixed successfully!")
        print("\nNow restart the tour orchestrator service with:")
        print("docker-compose restart tour-orchestrator")
        print("\nThen generate a tour for a location like:")
        print("\"Boston Public Library, Boston, MA\"")
        print("\nAnd check the logs:")
        print("docker-compose logs tour-orchestrator")
        print("docker-compose logs coordinates-fromai")
    else:
        print("\nFailed to fix tour orchestrator")
        sys.exit(1)

if __name__ == "__main__":
    main()