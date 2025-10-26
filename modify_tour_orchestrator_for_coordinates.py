#!/usr/bin/env python3
"""
Script to modify the tour orchestrator service to use the coordinates endpoint.
"""
import subprocess
import sys
import time

def modify_tour_orchestrator():
    """Modify the tour orchestrator service to use the coordinates endpoint."""
    try:
        # Create the code to add to the tour orchestrator
        code_to_add = """
def get_coordinates_from_generator(location):
    \"\"\"Get coordinates for a location from the tour-generator service.\"\"\"
    import requests
    import urllib.parse
    
    try:
        # Log the request
        print(f"\\n==== REQUESTING COORDINATES FOR: {location} ====\\n")
        
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
"""
        
        # Write the code to a temporary file
        with open("coordinates_code.py", "w") as f:
            f.write(code_to_add)
        
        print("Created coordinates_code.py")
        
        # Copy the code to the tour orchestrator container
        result = subprocess.run(
            ["docker", "cp", "coordinates_code.py", "development-tour-orchestrator-1:/app/"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error copying code to container: {result.stderr}")
            return False
        
        print("Copied code to container")
        
        # Create a script to add the code to tour_orchestrator_service.py
        apply_script = """#!/bin/bash
echo "Adding coordinates code to tour_orchestrator_service.py"
cat /app/coordinates_code.py >> /app/tour_orchestrator_service.py

# Now modify the store_audio_tour function to use the new function
sed -i 's/coords = get_coordinates_for_location(request_string or tour_name)/coords = get_coordinates_from_generator(request_string or tour_name)/' /app/tour_orchestrator_service.py

echo "Code added and function modified"
"""
        
        # Write the apply script to a temporary file
        with open("add_code.sh", "w") as f:
            f.write(apply_script)
        
        print("Created add_code.sh")
        
        # Copy the apply script to the tour orchestrator container
        result = subprocess.run(
            ["docker", "cp", "add_code.sh", "development-tour-orchestrator-1:/app/"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error copying apply script to container: {result.stderr}")
            return False
        
        print("Copied apply script to container")
        
        # Make the apply script executable
        result = subprocess.run(
            ["docker", "exec", "development-tour-orchestrator-1", "chmod", "+x", "/app/add_code.sh"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error making apply script executable: {result.stderr}")
            return False
        
        print("Made apply script executable")
        
        # Run the apply script
        result = subprocess.run(
            ["docker", "exec", "development-tour-orchestrator-1", "/app/add_code.sh"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error applying code: {result.stderr}")
            return False
        
        print("Applied code:")
        print(result.stdout)
        
        # Restart the tour orchestrator service
        print("Restarting tour orchestrator service...")
        result = subprocess.run(
            ["docker", "restart", "development-tour-orchestrator-1"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error restarting service: {result.stderr}")
            return False
        
        print("Tour orchestrator service restarted")
        
        # Wait for the service to start
        print("Waiting for service to start...")
        time.sleep(5)
        
        return True
    except Exception as e:
        print(f"Error modifying tour orchestrator: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Modifying Tour Orchestrator Service =====\n")
    
    success = modify_tour_orchestrator()
    
    if success:
        print("\nTour orchestrator service modified successfully!")
    else:
        print("\nFailed to modify tour orchestrator service")
        sys.exit(1)

if __name__ == "__main__":
    main()