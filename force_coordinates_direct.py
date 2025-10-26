#!/usr/bin/env python3
"""
Direct patch for the tour orchestrator service to force coordinates retrieval.
"""
import subprocess
import sys

def create_patch_file():
    """Create a patch file to force coordinates retrieval."""
    patch_content = """
# Force coordinates retrieval in orchestrate_tour_async function
sed -i 's/# Step 7: Get coordinates if still not available/# Step 7: ALWAYS get coordinates for every tour/g' /app/tour_orchestrator_service.py

# Replace the coordinates check to always get coordinates
sed -i 's/if coordinates and isinstance(coordinates, list) and len(coordinates) >= 2:/# Always get coordinates regardless of what was provided before\\n        print("\\\\n==== FORCING COORDINATES RETRIEVAL FOR EVERY TOUR ====\\\\n")\\n        print(f"Location: {location}")\\n        # if False:/g' /app/tour_orchestrator_service.py

# Add direct call to coordinates-fromai service
sed -i '/coords = get_coordinates_for_location(location)/c\\            # Direct call to coordinates-fromai service\\n            try:\\n                import requests\\n                import urllib.parse\\n                \\n                # URL-encode the location\\n                encoded_location = urllib.parse.quote(location)\\n                \\n                # Make the request to the coordinates-fromai service\\n                url = f"http://coordinates-fromai:5004/coordinates/{encoded_location}"\\n                print(f"Requesting coordinates from: {url}")\\n                \\n                response = requests.get(url, timeout=30)\\n                \\n                print(f"Response status code: {response.status_code}")\\n                \\n                if response.status_code == 200:\\n                    data = response.json()\\n                    \\n                    if "coordinates" in data and len(data["coordinates"]) >= 2:\\n                        coords = (data["coordinates"][0], data["coordinates"][1])\\n                        print(f"Received coordinates: lat={coords[0]}, lng={coords[1]}")\\n                    else:\\n                        print(f"Invalid response format: {data}")\\n                        coords = None\\n                else:\\n                    print(f"Error response: {response.text}")\\n                    coords = None\\n            except Exception as e:\\n                print(f"Error calling coordinates service: {e}")\\n                coords = None' /app/tour_orchestrator_service.py

# Add logging before storing in database
sed -i 's/# Step 8: Store in database/# Step 8: Store in database with coordinates\\n        print("\\\\n==== STORING TOUR WITH COORDINATES ====\\\\n")\\n        print(f"Tour name: {tour_name}")\\n        print(f"Request string: {request_string or location}")\\n        print(f"Coordinates to store: lat={lat}, lng={lng}")/g' /app/tour_orchestrator_service.py

# Add logging after storing in database
sed -i 's/if store_success:/print("\\\\n==== STORE_AUDIO_TOUR RESULT ====\\\\n")\\n        print(f"Success: {store_success}")\\n        \\n        if store_success:/g' /app/tour_orchestrator_service.py

# Force coordinates retrieval in store_audio_tour function
sed -i 's/# If coordinates not provided, try to get them/# ALWAYS get coordinates from coordinates-fromai service\\n        print("\\\\n==== FORCING COORDINATES RETRIEVAL IN STORE_AUDIO_TOUR ====\\\\n")\\n        print(f"Location: {request_string or tour_name}")/g' /app/tour_orchestrator_service.py

# Replace the coordinates check in store_audio_tour
sed -i 's/if lat is None or lng is None:/# Always get coordinates regardless of what was provided\\n            # if False:/g' /app/tour_orchestrator_service.py

# Replace the get_coordinates_for_location call in store_audio_tour
sed -i '/coords = get_coordinates_for_location(request_string or tour_name)/c\\            # Direct call to coordinates-fromai service\\n            try:\\n                import requests\\n                import urllib.parse\\n                \\n                # URL-encode the location\\n                location = request_string or tour_name\\n                encoded_location = urllib.parse.quote(location)\\n                \\n                # Make the request to the coordinates-fromai service\\n                url = f"http://coordinates-fromai:5004/coordinates/{encoded_location}"\\n                print(f"Requesting coordinates from: {url}")\\n                \\n                response = requests.get(url, timeout=30)\\n                \\n                print(f"Response status code: {response.status_code}")\\n                \\n                if response.status_code == 200:\\n                    data = response.json()\\n                    \\n                    if "coordinates" in data and len(data["coordinates"]) >= 2:\\n                        coords = (data["coordinates"][0], data["coordinates"][1])\\n                        print(f"Received coordinates: lat={coords[0]}, lng={coords[1]}")\\n                    else:\\n                        print(f"Invalid response format: {data}")\\n                        coords = None\\n                else:\\n                    print(f"Error response: {response.text}")\\n                    coords = None\\n            except Exception as e:\\n                print(f"Error calling coordinates service: {e}")\\n                coords = None' /app/tour_orchestrator_service.py
"""
    
    with open("force_coordinates_patch.sh", "w") as f:
        f.write(patch_content)
    
    print("Created force_coordinates_patch.sh")
    
    return True

def apply_patch():
    """Apply the patch to the tour orchestrator service."""
    try:
        # Copy the patch file to the container
        print("Copying patch file to container...")
        result = subprocess.run(
            ["docker", "cp", "force_coordinates_patch.sh", "development-tour-orchestrator-1:/app/"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error copying patch file: {result.stderr}")
            return False
        
        print("Patch file copied to container")
        
        # Make the patch file executable
        print("Making patch file executable...")
        result = subprocess.run(
            ["docker", "exec", "development-tour-orchestrator-1", "chmod", "+x", "/app/force_coordinates_patch.sh"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error making patch file executable: {result.stderr}")
            return False
        
        print("Patch file made executable")
        
        # Create a backup of the original file
        print("Creating backup of original file...")
        result = subprocess.run(
            ["docker", "exec", "development-tour-orchestrator-1", "cp", "/app/tour_orchestrator_service.py", "/app/tour_orchestrator_service.py.bak_direct"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error creating backup: {result.stderr}")
            return False
        
        print("Backup created")
        
        # Run the patch file
        print("Applying patch...")
        result = subprocess.run(
            ["docker", "exec", "development-tour-orchestrator-1", "bash", "/app/force_coordinates_patch.sh"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error applying patch: {result.stderr}")
            return False
        
        print("Patch applied")
        
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
        print(f"Error applying patch: {e}")
        return False

def main():
    """Main function."""
    print("\n===== Forcing Coordinates Retrieval (Direct Patch) =====\n")
    
    success = create_patch_file() and apply_patch()
    
    if success:
        print("\nDirect patch applied successfully!")
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
        print("\nFailed to apply direct patch")
        sys.exit(1)

if __name__ == "__main__":
    main()