#!/usr/bin/env python3
"""
Script to modify the tour orchestrator service to call the coordinates-fromai service.
"""
import subprocess
import sys

def modify_orchestrate_tour_async():
    """Modify the orchestrate_tour_async function to call the coordinates-fromai service."""
    try:
        # Create a patch file
        patch_content = """
# Add this code to the orchestrate_tour_async function right before storing in database
print("\\n==== FORCING COORDINATES RETRIEVAL BEFORE DATABASE STORAGE ====\\n")
print(f"Location: {location}")

# Call the coordinates-fromai service directly
try:
    import requests
    import urllib.parse
    
    # URL-encode the location
    encoded_location = urllib.parse.quote(location)
    
    # Make the request to the coordinates-fromai service
    url = f"http://coordinates-fromai:5004/coordinates/{encoded_location}"
    print(f"Requesting coordinates from: {url}")
    
    response = requests.get(url, timeout=30)
    
    print(f"Response status code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        
        if "coordinates" in data and len(data["coordinates"]) >= 2:
            lat, lng = data["coordinates"][0], data["coordinates"][1]
            print(f"Received coordinates: lat={lat}, lng={lng}")
            # Override any previous coordinates
            coordinates = [lat, lng]
        else:
            print(f"Invalid response format: {data}")
    else:
        print(f"Error response: {response.text}")
except Exception as e:
    print(f"Error calling coordinates service: {e}")
"""
        
        with open("coordinates_patch.txt", "w") as f:
            f.write(patch_content)
        
        print("Created coordinates_patch.txt")
        
        # Copy the patch file to the container
        result = subprocess.run(
            ["docker", "cp", "coordinates_patch.txt", "development-tour-orchestrator-1:/app/"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error copying patch file: {result.stderr}")
            return False
        
        print("Copied patch file to container")
        
        # Create a script to apply the patch
        apply_script = """#!/bin/bash
# Make a backup of the original file
cp /app/tour_orchestrator_service.py /app/tour_orchestrator_service.py.bak_patch

# Find the line before "# Step 8: Store in database"
line_num=$(grep -n "# Step 8: Store in database" /app/tour_orchestrator_service.py | cut -d: -f1)

# Insert the patch before that line
head -n $line_num /app/tour_orchestrator_service.py > /app/tour_orchestrator_service.py.new
cat /app/coordinates_patch.txt >> /app/tour_orchestrator_service.py.new
tail -n +$line_num /app/tour_orchestrator_service.py >> /app/tour_orchestrator_service.py.new

# Replace the original file
mv /app/tour_orchestrator_service.py.new /app/tour_orchestrator_service.py

echo "Patch applied successfully"
"""
        
        with open("apply_patch.sh", "w") as f:
            f.write(apply_script)
        
        print("Created apply_patch.sh")
        
        # Copy the apply script to the container
        result = subprocess.run(
            ["docker", "cp", "apply_patch.sh", "development-tour-orchestrator-1:/app/"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error copying apply script: {result.stderr}")
            return False
        
        print("Copied apply script to container")
        
        # Make the apply script executable
        result = subprocess.run(
            ["docker", "exec", "development-tour-orchestrator-1", "chmod", "+x", "/app/apply_patch.sh"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error making apply script executable: {result.stderr}")
            return False
        
        print("Made apply script executable")
        
        # Run the apply script
        result = subprocess.run(
            ["docker", "exec", "development-tour-orchestrator-1", "/app/apply_patch.sh"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error applying patch: {result.stderr}")
            return False
        
        print("Patch applied:")
        print(result.stdout)
        
        # Restart the tour orchestrator service
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
        print(f"Error modifying orchestrate_tour_async: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Modifying Tour Orchestrator to Call Coordinates Service =====\n")
    
    success = modify_orchestrate_tour_async()
    
    if success:
        print("\nTour orchestrator modified successfully!")
        print("\nNow when you generate a tour, the tour orchestrator will:")
        print("1. Call the coordinates-fromai service before storing in the database")
        print("2. Log the request and response in detail")
        print("3. Store the coordinates in the database")
        print("\nTo test it, generate a tour for a location like:")
        print("\"Boston Public Library, Boston, MA\"")
        print("\nThen check the logs:")
        print("docker-compose logs tour-orchestrator")
        print("docker-compose logs coordinates-fromai")
    else:
        print("\nFailed to modify tour orchestrator")
        sys.exit(1)

if __name__ == "__main__":
    main()