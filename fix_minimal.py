#!/usr/bin/env python3
"""
Script to directly modify the tour orchestrator service to call the coordinates-fromai service.
"""
import sys

def fix_tour_orchestrator():
    """Fix the tour orchestrator service to call the coordinates-fromai service."""
    try:
        # Read the current tour_orchestrator_service.py file
        with open("tour_orchestrator_service.py", "r") as f:
            service_py = f.read()
        
        # Make a backup of the original file
        with open("tour_orchestrator_service.py.bak_minimal", "w") as f:
            f.write(service_py)
        
        print("Created backup at tour_orchestrator_service.py.bak_minimal")
        
        # Add a simple function to directly call the coordinates-fromai service
        direct_call_function = """
# Direct function to call coordinates-fromai service
def call_coordinates_service(location):
    # Get coordinates directly from the coordinates-fromai service
    import requests
    import urllib.parse
    
    print(f"\\n==== DIRECT CALL TO COORDINATES-FROMAI SERVICE ====\\n")
    print(f"Location: {location}")
    
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
        
        # Add the direct call function to the end of the file
        new_service_py = service_py + direct_call_function
        
        # Find the store_audio_tour function
        store_audio_tour_start = new_service_py.find("def store_audio_tour(")
        
        # Find the part where coordinates are retrieved
        coords_check_start = new_service_py.find("# If coordinates not provided, try to get them", store_audio_tour_start)
        coords_check_end = new_service_py.find("if coords:", coords_check_start)
        
        # Replace the coordinates check with a direct call
        direct_call_code = """
        # Always call coordinates-fromai service directly
        print("\\n==== FORCING COORDINATES RETRIEVAL FROM COORDINATES-FROMAI ====\\n")
        print(f"Location: {request_string or tour_name}")
        coords = call_coordinates_service(request_string or tour_name)
        print(f"Result from call_coordinates_service: {coords}")
"""
        
        # Replace the coordinates check
        new_service_py = new_service_py[:coords_check_start] + direct_call_code + new_service_py[coords_check_end:]
        
        # Write the updated file
        with open("tour_orchestrator_service.py", "w") as f:
            f.write(new_service_py)
        
        print("Updated tour_orchestrator_service.py with direct call to coordinates-fromai service")
        
        return True
    except Exception as e:
        print(f"Error fixing tour orchestrator: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Minimal Fix for Tour Orchestrator =====\n")
    
    success = fix_tour_orchestrator()
    
    if success:
        print("\nTour orchestrator fixed successfully!")
        print("\nNow restart the tour orchestrator service with:")
        print("docker-compose restart tour-orchestrator")
    else:
        print("\nFailed to fix tour orchestrator")
        sys.exit(1)

if __name__ == "__main__":
    main()