#!/usr/bin/env python3
"""
Script to fix the tour orchestrator to always call the coordinates service.
"""
import subprocess
import sys
import re

def fix_store_audio_tour():
    """Fix the store_audio_tour function to always call the coordinates service."""
    try:
        # Get the current tour_orchestrator_service.py file
        print("Getting current tour_orchestrator_service.py...")
        
        # Read the current tour_orchestrator_service.py file
        with open("tour_orchestrator_service.py", "r") as f:
            service_py = f.read()
        
        # Make a backup of the original file
        with open("tour_orchestrator_service.py.bak_fix", "w") as f:
            f.write(service_py)
        
        print("Created backup at tour_orchestrator_service.py.bak_fix")
        
        # Find the store_audio_tour function
        store_audio_tour_match = re.search(r"def store_audio_tour\(.*?\):(.*?)return True", service_py, re.DOTALL)
        
        if not store_audio_tour_match:
            print("Could not find store_audio_tour function")
            return False
        
        store_audio_tour_body = store_audio_tour_match.group(1)
        
        # Replace the coordinates retrieval code
        new_store_audio_tour_body = store_audio_tour_body.replace(
            "# If coordinates not provided, try to get them",
            """# Always get coordinates from the coordinates-fromai service
        print("\\n==== ALWAYS GETTING COORDINATES FROM SERVICE ====\\n")
        print(f"Location: {request_string or tour_name}")"""
        )
        
        # Replace the conditional check for coordinates
        new_store_audio_tour_body = new_store_audio_tour_body.replace(
            "if lat is None or lng is None:",
            "# Always get coordinates regardless of whether they were provided"
        )
        
        # Replace the coordinates retrieval code
        new_store_audio_tour_body = new_store_audio_tour_body.replace(
            "coords = get_coordinates_for_location(request_string or tour_name)",
            """# Call the coordinates-fromai service directly
            try:
                import requests
                import urllib.parse
                
                # URL-encode the location
                location = request_string or tour_name
                encoded_location = urllib.parse.quote(location)
                
                # Make the request to the coordinates-fromai service
                url = f"http://coordinates-fromai:5004/coordinates/{encoded_location}"
                print(f"Requesting coordinates from: {url}")
                
                response = requests.get(url, timeout=30)
                
                print(f"Response status code: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if "coordinates" in data and len(data["coordinates"]) >= 2:
                        coords = (data["coordinates"][0], data["coordinates"][1])
                        print(f"Received coordinates: lat={coords[0]}, lng={coords[1]}")
                    else:
                        print(f"Invalid response format: {data}")
                        coords = None
                else:
                    print(f"Error response: {response.text}")
                    coords = None
            except Exception as e:
                print(f"Error calling coordinates service: {e}")
                coords = None"""
        )
        
        # Replace the store_audio_tour function in the file
        new_service_py = service_py.replace(store_audio_tour_body, new_store_audio_tour_body)
        
        # Write the updated service file
        with open("tour_orchestrator_service.py", "w") as f:
            f.write(new_service_py)
        
        print("Updated tour_orchestrator_service.py to always call the coordinates service")
        
        # Restart the tour orchestrator service
        print("Restarting tour orchestrator service...")
        
        result = subprocess.run(
            ["docker-compose", "restart", "tour-orchestrator"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error restarting service: {result.stderr}")
            return False
        
        print("Tour orchestrator service restarted")
        
        return True
    except Exception as e:
        print(f"Error fixing store_audio_tour: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Fixing Tour Orchestrator to Always Call Coordinates Service =====\n")
    
    success = fix_store_audio_tour()
    
    if success:
        print("\nTour orchestrator fixed successfully!")
        print("\nNow when you generate a tour, the tour orchestrator will:")
        print("1. ALWAYS call the coordinates-fromai service for EVERY tour")
        print("2. Log the request and response in detail")
        print("3. Store the coordinates in the database")
        print("\nTo test it, generate a tour for a location like:")
        print("\"Boston Public Library, Boston, MA\"")
        print("\nThen check the logs:")
        print("docker-compose logs tour-orchestrator")
        print("docker-compose logs coordinates-fromai")
    else:
        print("\nFailed to fix tour orchestrator")
        sys.exit(1)

if __name__ == "__main__":
    main()