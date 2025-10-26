#!/usr/bin/env python3
"""
Script to directly modify the tour orchestrator service to use the coordinates endpoint.
"""
import subprocess
import sys
import time

def modify_tour_orchestrator_direct():
    """Directly modify the tour orchestrator service to use the coordinates endpoint."""
    try:
        print("Creating coordinates function code...")
        
        # Create the function code
        function_code = """
# Function to get coordinates from tour-generator service
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
        
        # Write the function code to a file
        with open("coordinates_function.py", "w") as f:
            f.write(function_code)
        
        print("Created coordinates_function.py")
        
        # Get the current tour_orchestrator_service.py file from the container
        print("Getting current tour_orchestrator_service.py from container...")
        result = subprocess.run(
            ["docker", "cp", "development-tour-orchestrator-1:/app/tour_orchestrator_service.py", "./tour_orchestrator_service.py.backup"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error getting tour_orchestrator_service.py: {result.stderr}")
            return False
        
        print("Got tour_orchestrator_service.py.backup")
        
        # Read the current tour_orchestrator_service.py file
        with open("tour_orchestrator_service.py.backup", "r") as f:
            service_py = f.read()
        
        # Check if the function already exists
        if "def get_coordinates_from_generator" in service_py:
            print("Coordinates function already exists in tour_orchestrator_service.py")
        else:
            # Add the function to the service file
            with open("tour_orchestrator_service.py.new", "w") as f:
                f.write(service_py)
                f.write("\n\n# Added coordinates function\n")
                f.write(function_code)
            
            print("Created tour_orchestrator_service.py.new with coordinates function")
            
            # Copy the new service file to the container
            result = subprocess.run(
                ["docker", "cp", "./tour_orchestrator_service.py.new", "development-tour-orchestrator-1:/app/tour_orchestrator_service.py"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print(f"Error copying tour_orchestrator_service.py to container: {result.stderr}")
                return False
            
            print("Copied tour_orchestrator_service.py to container")
        
        # Now modify the store_audio_tour function to use the new function
        print("Creating sed script to modify store_audio_tour function...")
        
        sed_script = """#!/bin/bash
echo "Modifying store_audio_tour function..."
sed -i 's/coords = get_coordinates_for_location(request_string or tour_name)/coords = get_coordinates_from_generator(request_string or tour_name)/' /app/tour_orchestrator_service.py
echo "Function modified"
"""
        
        # Write the sed script to a file
        with open("modify_function.sh", "w") as f:
            f.write(sed_script)
        
        print("Created modify_function.sh")
        
        # Copy the sed script to the container
        result = subprocess.run(
            ["docker", "cp", "./modify_function.sh", "development-tour-orchestrator-1:/app/"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error copying sed script to container: {result.stderr}")
            return False
        
        print("Copied sed script to container")
        
        # Make the sed script executable
        result = subprocess.run(
            ["docker", "exec", "development-tour-orchestrator-1", "chmod", "+x", "/app/modify_function.sh"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error making sed script executable: {result.stderr}")
            return False
        
        print("Made sed script executable")
        
        # Run the sed script
        result = subprocess.run(
            ["docker", "exec", "development-tour-orchestrator-1", "/app/modify_function.sh"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error running sed script: {result.stderr}")
            return False
        
        print("Ran sed script:")
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
        time.sleep(10)
        
        return True
    except Exception as e:
        print(f"Error modifying tour orchestrator: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Directly Modifying Tour Orchestrator Service =====\n")
    
    success = modify_tour_orchestrator_direct()
    
    if success:
        print("\nTour orchestrator service modified successfully!")
    else:
        print("\nFailed to modify tour orchestrator service")
        sys.exit(1)

if __name__ == "__main__":
    main()