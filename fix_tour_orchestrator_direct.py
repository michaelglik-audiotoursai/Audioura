#!/usr/bin/env python3
"""
Script to fix the tour orchestrator service with improved logging and ensure it calls the coordinates service.
"""
import subprocess
import sys
import re

def fix_tour_orchestrator_direct():
    """Fix the tour orchestrator service directly."""
    try:
        # Get the current tour_orchestrator_service.py file
        print("Getting current tour_orchestrator_service.py...")
        
        # Read the current tour_orchestrator_service.py file
        with open("tour_orchestrator_service.py", "r") as f:
            service_py = f.read()
        
        # Make a backup of the original file
        with open("tour_orchestrator_service.py.bak2", "w") as f:
            f.write(service_py)
        
        print("Created backup at tour_orchestrator_service.py.bak2")
        
        # Find the store_audio_tour function
        store_audio_tour_match = re.search(r"def store_audio_tour\(.*?\):(.*?)return True", service_py, re.DOTALL)
        
        if not store_audio_tour_match:
            print("Could not find store_audio_tour function")
            return False
        
        store_audio_tour_body = store_audio_tour_match.group(1)
        
        # Add detailed logging to the store_audio_tour function
        new_store_audio_tour_body = store_audio_tour_body.replace(
            "# If coordinates not provided, try to get them",
            "# If coordinates not provided, try to get them\n        print(f\"\\n==== COORDINATES CHECK FOR: {request_string or tour_name} ====\\n\")\n        print(f\"Initial coordinates: lat={lat}, lng={lng}\")"
        )
        
        # Replace the coordinates retrieval code
        new_store_audio_tour_body = new_store_audio_tour_body.replace(
            "coords = get_coordinates_for_location(request_string or tour_name)",
            """print(f"\\n==== CALLING COORDINATES SERVICE FOR: {request_string or tour_name} ====\\n")
            # Call the coordinates-fromai service directly
            try:
                import requests
                import urllib.parse
                
                # URL-encode the location
                location = request_string or tour_name
                encoded_location = urllib.parse.quote(location)
                
                # Make the request to the coordinates-fromai service
                url = f"http://coordinates-fromai:5004/coordinates/{encoded_location}"
                print(f"Requesting URL: {url}")
                
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
        
        print("Updated tour_orchestrator_service.py with improved logging and direct coordinates service call")
        
        # Update the coordinates-fromai service with improved logging
        print("Updating coordinates-fromai service with improved logging...")
        
        # Read the app.py file
        with open("coordinates_fromAI/app.py", "r") as f:
            app_py = f.read()
        
        # Make a backup of the original file
        with open("coordinates_fromAI/app.py.bak2", "w") as f:
            f.write(app_py)
        
        print("Created backup at coordinates_fromAI/app.py.bak2")
        
        # Add more detailed logging
        new_app_py = app_py.replace(
            '@app.route(\'/coordinates/<path:location>\', methods=[\'GET\'])',
            '@app.route(\'/coordinates/<path:location>\', methods=[\'GET\'])\n@app.route(\'/coordinates/<path:location>/\', methods=[\'GET\'])'
        )
        
        new_app_py = new_app_py.replace(
            'logging.info(f"\\n==== COORDINATES REQUEST: {location} ====\\n")',
            'print(f"\\n==== COORDINATES REQUEST RECEIVED: {location} ====\\n")\n        logging.info(f"\\n==== COORDINATES REQUEST RECEIVED: {location} ====\\n")'
        )
        
        new_app_py = new_app_py.replace(
            'logging.info(f"Sending request to OpenAI API for: {location}")',
            'print(f"Sending request to OpenAI API for: {location}")\n        logging.info(f"Sending request to OpenAI API for: {location}")'
        )
        
        new_app_py = new_app_py.replace(
            'logging.info(f"OpenAI response: {coordinates_text}")',
            'print(f"OpenAI response: {coordinates_text}")\n        logging.info(f"OpenAI response: {coordinates_text}")'
        )
        
        new_app_py = new_app_py.replace(
            'logging.info(f"Parsed coordinates: lat={lat}, lng={lng}")',
            'print(f"Parsed coordinates for {location}: lat={lat}, lng={lng}")\n            logging.info(f"Parsed coordinates for {location}: lat={lat}, lng={lng}")'
        )
        
        # Write the updated app.py file
        with open("coordinates_fromAI/app.py", "w") as f:
            f.write(new_app_py)
        
        print("Updated coordinates_fromAI/app.py with improved logging")
        
        # Restart both services
        print("Restarting services...")
        
        result = subprocess.run(
            ["docker-compose", "restart", "coordinates-fromai", "tour-orchestrator"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error restarting services: {result.stderr}")
            return False
        
        print("Services restarted")
        
        # Update the Gale Free Library tour with coordinates
        print("Updating tour for Gale Free Library with coordinates...")
        
        # Execute SQL command
        result = subprocess.run(
            ["docker", "exec", "development-postgres-2-1", "psql", "-U", "admin", "-d", "audiotours", "-c",
             "UPDATE audio_tours SET lat = 42.3506, lng = -71.8656 WHERE request_string = 'Gale Free Library, Holden MA';"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error updating database: {result.stderr}")
            return False
        
        print("Database updated")
        
        # Verify the update
        result = subprocess.run(
            ["docker", "exec", "development-postgres-2-1", "psql", "-U", "admin", "-d", "audiotours", "-c",
             "SELECT id, tour_name, request_string, lat, lng FROM audio_tours WHERE request_string = 'Gale Free Library, Holden MA';"],
            capture_output=True,
            text=True
        )
        
        print("Database verification:")
        print(result.stdout)
        
        return True
    except Exception as e:
        print(f"Error fixing tour orchestrator: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Fixing Tour Orchestrator Service (Direct) =====\n")
    
    success = fix_tour_orchestrator_direct()
    
    if success:
        print("\nTour orchestrator service fixed successfully!")
        print("\nNow when you generate a tour, the tour orchestrator will:")
        print("1. Call the coordinates-fromai service directly")
        print("2. Log the request and response in detail")
        print("3. Store the coordinates in the database")
        print("\nThe coordinates-fromai service will also log all requests and responses.")
        print("\nTo test it, generate a tour for a location like:")
        print("\"Boston Public Library, Boston, MA\"")
        print("\nThen check the logs:")
        print("docker-compose logs tour-orchestrator")
        print("docker-compose logs coordinates-fromai")
        print("\nAnd check the database:")
        print("docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c \"SELECT tour_name, lat, lng FROM audio_tours ORDER BY id DESC LIMIT 5;\"")
    else:
        print("\nFailed to fix tour orchestrator service")
        sys.exit(1)

if __name__ == "__main__":
    main()